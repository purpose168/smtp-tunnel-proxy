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
        while True:
            line = await self.read_smtp_line()
            if not line:
                return False
            if line.startswith('250 '):
                return True
            if line.startswith('250-'):
                continue
            return False
    
    async def upgrade_tls(self, ssl_context, server_side: bool = False, server_hostname: str = None):
        """
        将现有 TCP 连接升级到 TLS 加密连接
        
        Args:
            ssl_context: SSL 上下文
            server_side: 是否为服务器端
            server_hostname: 服务器主机名（客户端使用）
        """
        transport = self.writer.transport
        protocol = self.writer._protocol
        loop = asyncio.get_event_loop()
        
        if server_side:
            new_transport = await loop.start_tls(
                transport, protocol, ssl_context, server_side=True
            )
        else:
            new_transport = await loop.start_tls(
                transport, protocol, ssl_context,
                server_hostname=server_hostname
            )
        
        self.writer._transport = new_transport
        self.reader._transport = new_transport
    
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
            return
        
        async with self.write_lock:
            try:
                frame = make_frame(frame_type, channel_id, payload)
                self.writer.write(frame)
                await self.writer.drain()
            except Exception as e:
                logging.error(f"发送帧失败: {e}")
    
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
        buffer = b''
        
        while True:
            try:
                chunk = await asyncio.wait_for(self.reader.read(65536), timeout=timeout)
                if not chunk:
                    break
                buffer += chunk
    
                while len(buffer) >= FRAME_HEADER_SIZE:
                    header = self._parse_frame_header(buffer)
                    if not header:
                        break
    
                    frame_type, channel_id, payload_len = header
                    total_len = FRAME_HEADER_SIZE + payload_len
    
                    if len(buffer) < total_len:
                        break
    
                    payload = buffer[FRAME_HEADER_SIZE:total_len]
                    buffer = buffer[total_len:]
    
                    await self.process_frame(frame_type, channel_id, payload)
    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logging.error(f"二进制模式错误: {e}")
                break
    
    def set_reader_writer(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """
        设置读写器
        
        Args:
            reader: 异步流读取器
            writer: 异步流写入器
        """
        self.reader = reader
        self.writer = writer