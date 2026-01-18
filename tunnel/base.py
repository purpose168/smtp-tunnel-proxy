"""
隧道基础类

本模块定义了 SMTP 隧道客户端和服务器共享的核心功能，包括：
- SMTP 命令处理
- TLS 连接升级
- 二进制帧发送
- 通道管理
- 资源清理

客户端和服务器通过继承此类，实现各自特定的功能。
"""

import asyncio
import ssl
import logging
import struct
import os
from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple

from protocol import (
    FRAME_DATA, FRAME_CONNECT, FRAME_CONNECT_OK,
    FRAME_CONNECT_FAIL, FRAME_CLOSE, FRAME_HEADER_SIZE,
    make_frame
)

logger = logging.getLogger('smtp-tunnel-base')


class BaseTunnel(ABC):
    """
    隧道基础类，包含客户端和服务器共享的核心功能
    
    Attributes:
        reader: 异步流读取器
        writer: 异步流写入器
        channels: 通道字典，key 为 channel_id
        write_lock: 写入锁，确保多协程环境下的线程安全
    """
    
    def __init__(self, reader: Optional[asyncio.StreamReader] = None, 
                 writer: Optional[asyncio.StreamWriter] = None):
        """
        初始化隧道基础类
        
        Args:
            reader: 异步流读取器
            writer: 异步流写入器
        """
        self.reader = reader
        self.writer = writer
        self.channels: Dict[int, object] = {}
        self.write_lock = asyncio.Lock()
        
    async def send_smtp_line(self, line: str):
        """
        发送 SMTP 命令行
        
        Args:
            line: 要发送的 SMTP 命令或数据行（不包含 CRLF）
        """
        self.writer.write(f"{line}\r\n".encode())
        await self.writer.drain()
    
    async def read_smtp_line(self) -> Optional[str]:
        """
        读取 SMTP 响应行
        
        Returns:
            Optional[str]: 读取到的行（已去除 CRLF），失败或超时返回 None
        """
        try:
            data = await asyncio.wait_for(self.reader.readline(), timeout=60.0)
            if not data:
                return None
            return data.decode('utf-8', errors='replace').strip()
        except:
            return None
    
    async def expect_250(self) -> bool:
        """
        读取 SMTP 响应直到收到 250 响应
        
        SMTP EHLO 命令会返回多行响应，以 "250-" 开头，
        最后一行以 "250 "（空格）开头。
        
        Returns:
            bool: 收到 250 响应返回 True，否则返回 False
        """
        logger.debug("等待 250 响应...")
        while True:
            line = await self.read_smtp_line()
            if not line:
                logger.warning("等待 250 响应失败：连接已关闭")
                return False
            if line.startswith('250 '):
                logger.debug(f"收到 250 响应: {line}")
                return True
            if line.startswith('250-'):
                logger.debug(f"收到 250- 响应: {line}")
                continue
            logger.warning(f"收到非 250 响应: {line}")
            return False
    
    async def upgrade_tls(self, ssl_context, server_side: bool = False, server_hostname: str = None):
        """
        将现有 TCP 连接升级到 TLS 加密连接

        Args:
            ssl_context: SSL 上下文
            server_side: 是否为服务器端
            server_hostname: 服务器主机名（客户端使用）
        """
        logger.info(f"升级到 TLS 连接（server_side={server_side}, server_hostname={server_hostname}）")

        try:
            reader = self.reader
            writer = self.writer

            # 获取底层 socket
            sock = writer.transport.get_extra_info('socket')
            if not sock:
                raise Exception("无法获取底层 socket")

            # 创建 SSLObject 和 MemoryBIO
            incoming_bio = ssl.MemoryBIO()
            outgoing_bio = ssl.MemoryBIO()

            ssl_obj = ssl_context.wrap_bio(
                incoming_bio,
                outgoing_bio,
                server_side=server_side,
                server_hostname=server_hostname
            )

            # 执行 SSL 握手
            loop = asyncio.get_event_loop()
            while True:
                try:
                    ssl_obj.do_handshake()
                    break
                except ssl.SSLWantReadError:
                    # 需要从 socket 读取数据
                    data = await loop.sock_recv(sock, 4096)
                    if not data:
                        raise Exception("连接已关闭")
                    incoming_bio.write(data)
                except ssl.SSLWantWriteError:
                    # 需要向 socket 写入数据
                    data = outgoing_bio.read(4096)
                    if data:
                        await loop.sock_sendall(sock, data)

            # 创建自定义的 TLS 流
            class TLSStreamReader:
                def __init__(self, ssl_obj, sock, incoming_bio, outgoing_bio, loop):
                    self.ssl_obj = ssl_obj
                    self.sock = sock
                    self.incoming_bio = incoming_bio
                    self.outgoing_bio = outgoing_bio
                    self.loop = loop
                    self.buffer = b''

                async def read(self, n=-1):
                    while True:
                        try:
                            data = self.ssl_obj.read(n)
                            if data:
                                return data
                            # 需要从 socket 读取更多数据
                            sock_data = await self.loop.sock_recv(self.sock, 4096)
                            if not sock_data:
                                return b''
                            self.incoming_bio.write(sock_data)
                        except ssl.SSLWantReadError:
                            sock_data = await self.loop.sock_recv(self.sock, 4096)
                            if not sock_data:
                                return b''
                            self.incoming_bio.write(sock_data)
                        except ssl.SSLWantWriteError:
                            data = self.outgoing_bio.read(4096)
                            if data:
                                await self.loop.sock_sendall(self.sock, data)

                async def readline(self):
                    while True:
                        if b'\n' in self.buffer:
                            line, self.buffer = self.buffer.split(b'\n', 1)
                            return line
                        data = await self.read(1024)
                        if not data:
                            line = self.buffer
                            self.buffer = b''
                            return line
                        self.buffer += data

            class TLSStreamWriter:
                def __init__(self, ssl_obj, sock, outgoing_bio, loop):
                    self.ssl_obj = ssl_obj
                    self.sock = sock
                    self.outgoing_bio = outgoing_bio
                    self.loop = loop

                def write(self, data):
                    self.ssl_obj.write(data)

                async def drain(self):
                    while True:
                        try:
                            data = self.outgoing_bio.read(4096)
                            if data:
                                await self.loop.sock_sendall(self.sock, data)
                            else:
                                break
                        except ssl.SSLWantWriteError:
                            data = self.outgoing_bio.read(4096)
                            if data:
                                await self.loop.sock_sendall(self.sock, data)
                            else:
                                break

                def close(self):
                    try:
                        self.ssl_obj.unwrap()
                    except:
                        pass

                async def wait_closed(self):
                    pass

                def get_extra_info(self, name, default=None):
                    if name == 'socket':
                        return self.sock
                    return default

            new_reader = TLSStreamReader(ssl_obj, sock, incoming_bio, outgoing_bio, loop)
            new_writer = TLSStreamWriter(ssl_obj, sock, outgoing_bio, loop)

            self.reader = new_reader
            self.writer = new_writer
            logger.info("TLS 连接升级成功")
        except Exception as e:
            logger.error(f"TLS 连接升级失败: {e}")
            raise
    
    async def send_frame(self, frame_type: int, channel_id: int, payload: bytes = b''):
        """
        向对方发送二进制帧
        
        使用写入锁确保多线程/协程环境下的线程安全。
        
        Args:
            frame_type: 帧类型（FRAME_DATA, FRAME_CONNECT 等）
            channel_id: 通道标识符
            payload: 帧载荷数据，默认为空
        """
        if not self.writer:
            logger.warning("无法发送帧：writer 不存在")
            return
        
        frame_type_name = self._get_frame_type_name(frame_type)
        logger.debug(f"发送帧: type={frame_type_name}({frame_type}), channel_id={channel_id}, payload_len={len(payload)}")
        
        async with self.write_lock:
            try:
                frame = make_frame(frame_type, channel_id, payload)
                self.writer.write(frame)
                await self.writer.drain()
                logger.debug(f"帧发送成功: type={frame_type_name}({frame_type}), channel_id={channel_id}")
            except Exception as e:
                logger.error(f"发送帧失败: type={frame_type_name}({frame_type}), channel_id={channel_id}, error={e}")
    
    @abstractmethod
    async def smtp_handshake(self) -> bool:
        """
        执行 SMTP 握手协议
        
        Returns:
            bool: 握手成功返回 True，失败返回 False
        """
        pass
    
    @abstractmethod
    async def process_frame(self, frame_type: int, channel_id: int, payload: bytes):
        """
        处理收到的二进制帧
        
        Args:
            frame_type: 帧类型
            channel_id: 通道ID
            payload: 帧载荷
        """
        pass
    
    @abstractmethod
    async def close_channel(self, channel: object):
        """
        关闭本地通道
        
        Args:
            channel: 要关闭的通道对象
        """
        pass
    
    @abstractmethod
    async def cleanup(self):
        """
        清理资源
        """
        pass
    
    def _get_frame_type_name(self, frame_type: int) -> str:
        """
        获取帧类型名称
        
        Args:
            frame_type: 帧类型
            
        Returns:
            str: 帧类型名称
        """
        frame_names = {
            FRAME_DATA: 'DATA',
            FRAME_CONNECT: 'CONNECT',
            FRAME_CONNECT_OK: 'CONNECT_OK',
            FRAME_CONNECT_FAIL: 'CONNECT_FAIL',
            FRAME_CLOSE: 'CLOSE'
        }
        return frame_names.get(frame_type, f'UNKNOWN({frame_type})')
    
    def _parse_frame_header(self, data: bytes) -> Optional[Tuple[int, int, int]]:
        """
        解析帧头
        
        Args:
            data: 原始字节数据
            
        Returns:
            Optional[Tuple[int, int, int]]: (frame_type, channel_id, payload_len) 或 None
        """
        if len(data) < FRAME_HEADER_SIZE:
            return None
        
        try:
            version, msg_type, channel_id, payload_len = struct.unpack('>BBHH', data[:FRAME_HEADER_SIZE])
            return msg_type, channel_id, payload_len
        except struct.error:
            return None
    
    async def binary_mode_loop(self, timeout: float = 60.0):
        """
        二进制模式循环，处理接收到的帧
        
        Args:
            timeout: 读取超时时间
        """
        logger.info(f"进入二进制模式循环（timeout={timeout}秒）")
        buffer = b''
        
        while True:
            try:
                chunk = await asyncio.wait_for(self.reader.read(65536), timeout=timeout)
                if not chunk:
                    logger.info("连接已关闭（读取到空数据）")
                    break
                buffer += chunk
                logger.debug(f"接收到数据块: {len(chunk)} 字节，缓冲区大小: {len(buffer)} 字节")
    
                while len(buffer) >= FRAME_HEADER_SIZE:
                    header = self._parse_frame_header(buffer)
                    if not header:
                        logger.debug(f"缓冲区数据不足（{len(buffer)} 字节），等待更多数据...")
                        break
    
                    frame_type, channel_id, payload_len = header
                    total_len = FRAME_HEADER_SIZE + payload_len
                    frame_type_name = self._get_frame_type_name(frame_type)
                    logger.debug(f"解析帧头: type={frame_type_name}({frame_type}), channel_id={channel_id}, payload_len={payload_len}")
    
                    if len(buffer) < total_len:
                        logger.debug(f"缓冲区数据不足（{len(buffer)}/{total_len} 字节），等待更多数据...")
                        break
    
                    payload = buffer[FRAME_HEADER_SIZE:total_len]
                    buffer = buffer[total_len:]
                    logger.debug(f"处理帧: type={frame_type_name}({frame_type}), channel_id={channel_id}, payload_len={len(payload)}")
    
                    await self.process_frame(frame_type, channel_id, payload)
    
            except asyncio.TimeoutError:
                logger.debug(f"读取超时（{timeout}秒），继续等待...")
                continue
            except Exception as e:
                logger.error(f"二进制模式错误: {e}")
                break
        
        logger.info("退出二进制模式循环")
    
    def set_reader_writer(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """
        设置读写器
        
        Args:
            reader: 异步流读取器
            writer: 异步流写入器
        """
        self.reader = reader
        self.writer = writer