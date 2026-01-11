#!/usr/bin/env python3
"""
SMTP 隧道客户端 - 快速二进制模式

版本: 1.3.0

功能概述:
本程序是一个 SMTP 隧道客户端，通过伪装成 SMTP 协议与服务器通信，
然后切换到高效二进制模式进行数据传输。它提供了一个本地 SOCKS5 代理，
允许任何支持 SOCKS5 的应用程序通过隧道连接到远程服务器。

工作原理:
1. 连接到 SMTP 隧道服务器
2. 执行标准 SMTP 握手（EHLO, STARTTLS, AUTH）
3. 发送 "BINARY" 命令切换到二进制协议模式
4. 启动本地 SOCKS5 代理服务器
5. 将 SOCKS5 客户端的连接请求通过隧道转发到服务器
6. 在 SOCKS 客户端和隧道服务器之间双向转发数据

协议说明:
- SMTP 握手阶段: 使用标准 SMTP 协议，看起来像正常的 SMTP 客户端
- 二进制模式阶段: 使用自定义二进制协议，支持多通道并发传输

二进制协议帧格式:
[类型(1B)] [通道ID(2B, 大端序)] [载荷长度(2B, 大端序)] [载荷数据]

帧类型:
- FRAME_DATA (0x01): 数据帧，用于传输实际数据
- FRAME_CONNECT (0x02): 连接请求帧
- FRAME_CONNECT_OK (0x03): 连接成功响应帧
- FRAME_CONNECT_FAIL (0x04): 连接失败响应帧
- FRAME_CLOSE (0x05): 关闭通道帧

特性:
- 多用户支持（用户名 + 密钥认证）
- TLS 加密通信
- 自动重连机制（指数退避）
- 支持 IPv4、IPv6 和域名地址
- 多通道并发传输
- 完整的错误处理和日志记录

使用方法:
1. 配置 config.yaml 文件或使用命令行参数
2. 运行: python client.py --config config.yaml
3. 配置应用程序使用 SOCKS5 代理（默认 127.0.0.1:1080）

命令行参数:
--config, -c: 配置文件路径（默认: config.yaml）
--server: 服务器域名
--server-port: 服务器端口（默认: 587）
--socks-port, -p: SOCKS5 代理端口（默认: 1080）
--username, -u: 认证用户名
--secret, -s: 认证密钥
--ca-cert: CA 证书路径
--debug, -d: 启用调试日志

依赖:
- Python 3.7+
- asyncio
- ssl
- struct
- socket
- dataclasses
"""

import asyncio
import ssl
import logging
import argparse
import struct
import time
import os
import socket
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

from common import TunnelCrypto, load_config, ClientConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('smtp-tunnel-client')


# ============================================================================
# 二进制协议
# ============================================================================

# 帧类型定义
FRAME_DATA = 0x01           # 数据帧 - 用于在通道上传输实际数据
FRAME_CONNECT = 0x02        # 连接请求帧 - 客户端请求服务器建立到目标主机的连接
FRAME_CONNECT_OK = 0x03     # 连接成功响应帧 - 服务器确认连接已建立
FRAME_CONNECT_FAIL = 0x04   # 连接失败响应帧 - 服务器报告连接失败
FRAME_CLOSE = 0x05          # 关闭帧 - 通知对方关闭通道
FRAME_HEADER_SIZE = 5       # 帧头大小（字节）- 1字节类型 + 2字节通道ID + 2字节载荷长度

def make_frame(frame_type: int, channel_id: int, payload: bytes = b'') -> bytes:
    """
    构造二进制协议帧
    
    帧格式: [类型(1B)] [通道ID(2B, 大端序)] [载荷长度(2B, 大端序)] [载荷数据]
    
    Args:
        frame_type: 帧类型（FRAME_DATA, FRAME_CONNECT 等）
        channel_id: 通道标识符，用于区分不同的连接
        payload: 帧载荷数据，默认为空
    
    Returns:
        完整的二进制帧字节数组
    """
    return struct.pack('>BHH', frame_type, channel_id, len(payload)) + payload

def make_connect_payload(host: str, port: int) -> bytes:
    """
    构造连接请求的载荷
    
    载荷格式: [主机名长度(1B)] [主机名(UTF-8编码)] [端口(2B, 大端序)]
    
    Args:
        host: 目标主机名或IP地址
        port: 目标端口号
    
    Returns:
        连接请求载荷字节数组
    """
    host_bytes = host.encode('utf-8')
    return struct.pack('>B', len(host_bytes)) + host_bytes + struct.pack('>H', port)


# ============================================================================
# SOCKS5
# ============================================================================

class SOCKS5:
    """
    SOCKS5 协议常量定义
    
    SOCKS5 是一种网络协议，客户端通过代理服务器与任意服务器进行通信。
    本实现支持 CONNECT 命令，用于建立 TCP 隧道。
    """
    VERSION = 0x05            # SOCKS5 协议版本号
    AUTH_NONE = 0x00          # 无需认证
    CMD_CONNECT = 0x01        # CONNECT 命令 - 建立 TCP 连接
    ATYP_IPV4 = 0x01          # 地址类型: IPv4 地址（4字节）
    ATYP_DOMAIN = 0x03        # 地址类型: 域名（首字节为长度）
    ATYP_IPV6 = 0x04          # 地址类型: IPv6 地址（16字节）
    REP_SUCCESS = 0x00        # 响应: 成功
    REP_FAILURE = 0x01        # 响应: 一般性失败


@dataclass
class Channel:
    """
    隧道通道数据类
    
    表示一个通过隧道建立的连接通道，包含通道的所有状态信息。
    每个通道对应一个通过 SOCKS5 代理的 TCP 连接。
    
    Attributes:
        channel_id: 通道唯一标识符
        reader: 异步流读取器，用于从 SOCKS 客户端读取数据
        writer: 异步流写入器，用于向 SOCKS 客户端写入数据
        host: 目标主机地址
        port: 目标端口
        connected: 通道连接状态，True 表示连接活跃
    """
    channel_id: int
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    host: str
    port: int
    connected: bool = False


# ============================================================================
# 隧道客户端
# ============================================================================

class TunnelClient:
    """
    SMTP 隧道客户端
    
    负责与 SMTP 隧道服务器建立连接，执行 SMTP 握手协议，
    然后切换到高效二进制模式进行数据传输。
    
    工作流程:
    1. 连接到服务器
    2. 执行 SMTP 握手（EHLO -> STARTTLS -> AUTH -> BINARY）
    3. 切换到二进制协议模式
    4. 管理多个通道，每个通道对应一个 TCP 连接
    5. 在 SOCKS5 代理和隧道服务器之间转发数据
    
    Attributes:
        config: 客户端配置对象，包含服务器地址、端口、认证信息等
        ca_cert: CA 证书路径，用于 TLS 证书验证
        reader: 从服务器读取数据的异步流读取器
        writer: 向服务器写入数据的异步流写入器
        connected: 与服务器的连接状态
        channels: 活跃通道字典，key 为 channel_id
        next_channel_id: 下一个可用的通道 ID
        channel_lock: 用于保护通道 ID 分配的锁
        connect_events: 连接事件字典，用于等待连接结果
        connect_results: 连接结果字典，存储连接成功/失败状态
        write_lock: 写入锁，确保向服务器发送帧的原子性
        receiver_task: 后台接收任务，负责从服务器接收帧
    """
    def __init__(self, config: ClientConfig, ca_cert: str = None):
        self.config = config
        self.ca_cert = ca_cert

        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.connected = False

        self.channels: Dict[int, Channel] = {}
        self.next_channel_id = 1
        self.channel_lock = asyncio.Lock()

        self.connect_events: Dict[int, asyncio.Event] = {}
        self.connect_results: Dict[int, bool] = {}

        self.write_lock = asyncio.Lock()
        
        # 任务引用
        self.receiver_task: Optional[asyncio.Task] = None

    async def connect(self) -> bool:
        """
        连接到 SMTP 隧道服务器并执行握手
        
        执行完整的连接流程:
        1. 建立 TCP 连接到服务器
        2. 执行 SMTP 握手协议
        3. 切换到二进制模式
        
        Returns:
            bool: 连接成功返回 True，失败返回 False
        """
        try:
            logger.info(f"正在连接到 {self.config.server_host}:{self.config.server_port}")

            # 建立到服务器的 TCP 连接，超时时间 30 秒
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.config.server_host, self.config.server_port),
                timeout=30.0
            )

            # 执行 SMTP 握手协议
            if not await self._smtp_handshake():
                return False

            self.connected = True
            logger.info("已连接 - 二进制模式激活")
            return True

        except Exception as e:
            logger.error(f"连接失败: {e}")
            return False

    async def _smtp_handshake(self) -> bool:
        """
        执行 SMTP 握手协议并切换到二进制模式
        
        SMTP 握手流程:
        1. 等待服务器 220 问候响应
        2. 发送 EHLO 命令，期望 250 响应
        3. 发送 STARTTLS 命令，升级到 TLS 加密连接
        4. 再次发送 EHLO 命令（在 TLS 通道上）
        5. 发送 AUTH PLAIN 命令进行身份验证
        6. 发送 BINARY 命令切换到二进制协议模式
        
        Returns:
            bool: 握手成功返回 True，失败返回 False
        """
        try:
            # 步骤 1: 等待服务器问候（220 响应）
            line = await self._read_line()
            if not line or not line.startswith('220'):
                return False

            # 步骤 2: 发送 EHLO 命令，标识客户端身份
            await self._send_line("EHLO tunnel-client.local")
            if not await self._expect_250():
                return False

            # 步骤 3: 请求升级到 TLS 加密连接
            await self._send_line("STARTTLS")
            line = await self._read_line()
            if not line or not line.startswith('220'):
                return False

            # 升级连接到 TLS
            await self._upgrade_tls()

            # 步骤 4: 在 TLS 通道上再次发送 EHLO
            await self._send_line("EHLO tunnel-client.local")
            if not await self._expect_250():
                return False

            # 步骤 5: 使用 PLAIN 机制进行身份验证
            # 生成认证令牌: base64(\0username\0timestamp_hmac)
            timestamp = int(time.time())
            crypto = TunnelCrypto(self.config.secret, is_server=False)
            token = crypto.generate_auth_token(timestamp, self.config.username)

            await self._send_line(f"AUTH PLAIN {token}")
            line = await self._read_line()
            if not line or not line.startswith('235'):
                logger.error(f"认证失败: {line}")
                return False

            # 步骤 6: 切换到二进制协议模式
            await self._send_line("BINARY")
            line = await self._read_line()
            if not line or not line.startswith('299'):
                logger.error(f"二进制模式失败: {line}")
                return False

            return True

        except Exception as e:
            logger.error(f"握手错误: {e}")
            return False

    async def _upgrade_tls(self):
        """
        将现有 TCP 连接升级到 TLS 加密连接
        
        使用 asyncio.start_tls 在现有传输上启动 TLS 握手。
        如果提供了 CA 证书，则验证服务器证书；否则跳过验证（仅用于测试）。
        """
        # 创建默认 SSL 上下文
        ssl_context = ssl.create_default_context()
        
        # 如果提供了 CA 证书文件，加载它进行证书验证
        if self.ca_cert and os.path.exists(self.ca_cert):
            ssl_context.load_verify_locations(self.ca_cert)
        else:
            # 没有提供 CA 证书时，跳过主机名验证和证书验证
            # 注意: 这仅适用于测试环境，生产环境应始终验证证书
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        # 获取当前传输和协议对象
        transport = self.writer.transport
        protocol = self.writer._protocol
        loop = asyncio.get_event_loop()

        # 在现有传输上启动 TLS 握手
        new_transport = await loop.start_tls(
            transport, protocol, ssl_context,
            server_hostname=self.config.server_host
        )

        # 更新 reader 和 writer 的传输对象
        self.writer._transport = new_transport
        self.reader._transport = new_transport
        logger.debug("TLS 已建立")

    async def _send_line(self, line: str):
        """
        发送 SMTP 协议行
        
        Args:
            line: 要发送的 SMTP 命令或数据行（不包含 CRLF）
        """
        self.writer.write(f"{line}\r\n".encode())
        await self.writer.drain()

    async def _read_line(self) -> Optional[str]:
        """
        读取 SMTP 协议行
        
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

    async def _expect_250(self) -> bool:
        """
        读取 SMTP 响应直到收到 250 响应
        
        SMTP EHLO 命令会返回多行响应，以 "250-" 开头，
        最后一行以 "250 "（空格）开头。
        
        Returns:
            bool: 收到 250 响应返回 True，否则返回 False
        """
        while True:
            line = await self._read_line()
            if not line:
                return False
            # 检查是否是最后一行响应（250 空格）
            if line.startswith('250 '):
                return True
            # 中间行响应（250-），继续读取
            if line.startswith('250-'):
                continue
            # 收到其他响应，失败
            return False

    async def start_receiver(self):
        """
        启动后台接收任务
        
        创建并启动一个后台任务，持续从服务器接收帧并分发处理。
        该任务在连接建立后启动，在连接断开时自动结束。
        """
        self.receiver_task = asyncio.create_task(self._receiver_loop())

    async def _receiver_loop(self):
        """
        接收并分发来自服务器的帧
        
        这是一个后台循环，持续从服务器读取二进制帧数据。
        处理流程:
        1. 从服务器读取数据块（最多 65536 字节）
        2. 将数据累积到缓冲区
        3. 解析缓冲区中的完整帧
        4. 将每个帧分发给对应的处理器
        
        帧格式: [类型(1B)] [通道ID(2B)] [载荷长度(2B)] [载荷数据]
        
        超时设置: 300 秒无数据则继续等待（保持连接活跃）
        """
        buffer = b''  # 接收缓冲区，用于处理不完整的帧

        while self.connected:
            try:
                # 从服务器读取数据，超时 300 秒
                chunk = await asyncio.wait_for(self.reader.read(65536), timeout=300.0)
                if not chunk:
                    # 服务器关闭连接
                    break
                buffer += chunk

                # 处理缓冲区中的完整帧
                while len(buffer) >= FRAME_HEADER_SIZE:
                    # 解析帧头
                    frame_type, channel_id, payload_len = struct.unpack('>BHH', buffer[:5])
                    total_len = FRAME_HEADER_SIZE + payload_len

                    # 如果缓冲区数据不足一个完整帧，等待更多数据
                    if len(buffer) < total_len:
                        break

                    # 提取载荷数据
                    payload = buffer[FRAME_HEADER_SIZE:total_len]
                    buffer = buffer[total_len:]

                    # 分发帧到对应的处理器
                    await self._handle_frame(frame_type, channel_id, payload)

            except asyncio.TimeoutError:
                # 超时继续等待，保持连接活跃
                continue
            except Exception as e:
                logger.error(f"接收器错误: {e}")
                break

        # 连接已断开
        self.connected = False

    async def _handle_frame(self, frame_type: int, channel_id: int, payload: bytes):
        """
        处理从服务器接收到的帧
        
        根据帧类型执行不同的处理逻辑:
        - FRAME_CONNECT_OK: 通知等待的连接请求已成功
        - FRAME_CONNECT_FAIL: 通知等待的连接请求已失败
        - FRAME_DATA: 将数据转发到对应的 SOCKS 客户端
        - FRAME_CLOSE: 关闭对应的通道
        
        Args:
            frame_type: 帧类型（FRAME_DATA, FRAME_CONNECT_OK 等）
            channel_id: 通道标识符
            payload: 帧载荷数据
        """
        if frame_type == FRAME_CONNECT_OK:
            # 连接成功响应 - 唤醒等待的连接请求
            if channel_id in self.connect_events:
                self.connect_results[channel_id] = True
                self.connect_events[channel_id].set()

        elif frame_type == FRAME_CONNECT_FAIL:
            # 连接失败响应 - 唤醒等待的连接请求
            if channel_id in self.connect_events:
                self.connect_results[channel_id] = False
                self.connect_events[channel_id].set()

        elif frame_type == FRAME_DATA:
            # 数据帧 - 将数据转发到对应的 SOCKS 客户端
            channel = self.channels.get(channel_id)
            if channel and channel.connected:
                try:
                    channel.writer.write(payload)
                    await channel.writer.drain()
                except:
                    # 写入失败，关闭通道
                    await self._close_channel(channel)

        elif frame_type == FRAME_CLOSE:
            # 关闭帧 - 服务器通知关闭通道
            channel = self.channels.get(channel_id)
            if channel:
                await self._close_channel(channel)

    async def send_frame(self, frame_type: int, channel_id: int, payload: bytes = b''):
        """
        向服务器发送帧
        
        使用写入锁确保多线程/协程环境下的线程安全。
        如果连接断开或写入失败，将 connected 设置为 False。
        
        Args:
            frame_type: 帧类型（FRAME_DATA, FRAME_CONNECT 等）
            channel_id: 通道标识符
            payload: 帧载荷数据，默认为空
        """
        if not self.connected or not self.writer:
            return
        async with self.write_lock:
            try:
                frame = make_frame(frame_type, channel_id, payload)
                self.writer.write(frame)
                await self.writer.drain()
            except Exception:
                # 写入失败，标记连接已断开
                self.connected = False

    async def open_channel(self, host: str, port: int) -> Tuple[int, bool]:
        """
        打开一个新的隧道通道
        
        向服务器发送连接请求，等待服务器响应。
        使用事件和结果字典实现异步等待模式。
        
        Args:
            host: 目标主机地址
            port: 目标端口号
        
        Returns:
            Tuple[int, bool]: (通道ID, 连接是否成功)
        """
        if not self.connected:
            return 0, False

        # 分配新的通道 ID
        async with self.channel_lock:
            channel_id = self.next_channel_id
            self.next_channel_id += 1

        # 创建事件和结果存储，用于等待连接结果
        event = asyncio.Event()
        self.connect_events[channel_id] = event
        self.connect_results[channel_id] = False

        # 发送 CONNECT 请求
        try:
            payload = make_connect_payload(host, port)
            await self.send_frame(FRAME_CONNECT, channel_id, payload)
        except Exception:
            return channel_id, False

        # 等待服务器响应，超时时间 30 秒
        try:
            await asyncio.wait_for(event.wait(), timeout=30.0)
            success = self.connect_results.get(channel_id, False)
        except asyncio.TimeoutError:
            success = False

        # 清理事件和结果
        self.connect_events.pop(channel_id, None)
        self.connect_results.pop(channel_id, None)

        return channel_id, success

    async def send_data(self, channel_id: int, data: bytes):
        """
        在指定通道上发送数据
        
        将数据封装为 DATA 帧发送到服务器，服务器会将数据转发到目标主机。
        
        Args:
            channel_id: 通道标识符
            data: 要发送的数据
        """
        await self.send_frame(FRAME_DATA, channel_id, data)

    async def close_channel_remote(self, channel_id: int):
        """
        通知服务器关闭指定通道
        
        发送 CLOSE 帧到服务器，服务器将关闭对应的连接。
        
        Args:
            channel_id: 要关闭的通道标识符
        """
        await self.send_frame(FRAME_CLOSE, channel_id)

    async def _close_channel(self, channel: Channel):
        """
        关闭本地通道
        
        关闭与 SOCKS 客户端的连接，并从通道字典中移除。
        
        Args:
            channel: 要关闭的通道对象
        """
        if not channel.connected:
            return
        channel.connected = False

        # 关闭与 SOCKS 客户端的连接
        try:
            channel.writer.close()
            await channel.writer.wait_closed()
        except:
            pass

        # 从通道字典中移除
        self.channels.pop(channel.channel_id, None)

    async def disconnect(self):
        """
        断开与服务器的连接并清理资源
        
        执行完整的清理流程:
        1. 关闭所有活跃通道
        2. 关闭与服务器的连接
        3. 清理所有字典和任务引用
        """
        self.connected = False
        
        # 关闭所有通道
        for channel in list(self.channels.values()):
            await self._close_channel(channel)
        
        # 关闭与服务器的连接
        if self.writer:
            try:
                self.writer.close()
                await asyncio.wait_for(self.writer.wait_closed(), timeout=2.0)
            except:
                pass
        
        # 清理所有引用
        self.reader = None
        self.writer = None
        self.channels.clear()
        self.connect_events.clear()
        self.connect_results.clear()
        
        # 取消接收器任务
        if self.receiver_task:
            self.receiver_task.cancel()
            try:
                await self.receiver_task
            except asyncio.CancelledError:
                pass
            self.receiver_task = None


# ============================================================================
# SOCKS5 服务器
# ============================================================================

class SOCKS5Server:
    """
    SOCKS5 代理服务器
    
    监听本地端口，接受 SOCKS5 客户端连接，将请求通过隧道转发到远程服务器。
    实现了 SOCKS5 协议的基本功能，支持 IPv4、IPv6 和域名地址类型。
    
    工作流程:
    1. 接受 SOCKS5 客户端连接
    2. 执行 SOCKS5 握手（版本协商、认证协商）
    3. 解析 CONNECT 请求，提取目标地址和端口
    4. 通过隧道打开到目标主机的通道
    5. 在 SOCKS 客户端和隧道之间双向转发数据
    
    Attributes:
        tunnel: 隧道客户端实例，用于与远程服务器通信
        host: SOCKS5 服务器监听地址
        port: SOCKS5 服务器监听端口
    """
    def __init__(self, tunnel: TunnelClient, host: str = '127.0.0.1', port: int = 1080):
        self.tunnel = tunnel
        self.host = host
        self.port = port

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """
        处理 SOCKS5 客户端连接
        
        完整的 SOCKS5 代理处理流程:
        1. 检查隧道连接状态
        2. 执行 SOCKS5 握手（版本协商）
        3. 解析 CONNECT 请求
        4. 根据地址类型解析目标地址（IPv4/IPv6/域名）
        5. 通过隧道建立到目标主机的连接
        6. 启动数据转发循环
        
        Args:
            reader: 从 SOCKS 客户端读取数据的异步流读取器
            writer: 向 SOCKS 客户端写入数据的异步流写入器
        """
        channel = None
        try:
            # 检查隧道是否已连接
            if not self.tunnel.connected:
                writer.close()
                return

            # SOCKS5 握手 - 版本协商
            # 读取版本和认证方法数量
            data = await reader.read(2)
            if len(data) < 2 or data[0] != SOCKS5.VERSION:
                return

            # 读取并忽略认证方法列表
            nmethods = data[1]
            await reader.read(nmethods)

            # 响应: 选择无需认证的方法
            writer.write(bytes([SOCKS5.VERSION, SOCKS5.AUTH_NONE]))
            await writer.drain()

            # 读取 CONNECT 请求
            data = await reader.read(4)
            if len(data) < 4:
                return

            version, cmd, _, atyp = data

            # 只支持 CONNECT 命令
            if cmd != SOCKS5.CMD_CONNECT:
                writer.write(bytes([SOCKS5.VERSION, 0x07, 0, 1, 0, 0, 0, 0, 0, 0]))
                await writer.drain()
                return

            # 根据地址类型解析目标地址
            if atyp == SOCKS5.ATYP_IPV4:
                # IPv4 地址（4字节）
                addr_data = await reader.read(4)
                host = socket.inet_ntoa(addr_data)
            elif atyp == SOCKS5.ATYP_DOMAIN:
                # 域名（首字节为长度）
                length = (await reader.read(1))[0]
                host = (await reader.read(length)).decode()
            elif atyp == SOCKS5.ATYP_IPV6:
                # IPv6 地址（16字节）
                addr_data = await reader.read(16)
                host = socket.inet_ntop(socket.AF_INET6, addr_data)
            else:
                # 不支持的地址类型
                return

            # 读取目标端口（2字节，大端序）
            port_data = await reader.read(2)
            port = struct.unpack('>H', port_data)[0]

            logger.info(f"CONNECT {host}:{port}")

            # 通过隧道打开到目标主机的通道
            channel_id, success = await self.tunnel.open_channel(host, port)

            if success:
                # 连接成功，发送成功响应
                writer.write(bytes([SOCKS5.VERSION, SOCKS5.REP_SUCCESS, 0, 1, 0, 0, 0, 0, 0, 0]))
                await writer.drain()

                # 创建通道对象并注册到隧道
                channel = Channel(
                    channel_id=channel_id,
                    reader=reader,
                    writer=writer,
                    host=host,
                    port=port,
                    connected=True
                )
                self.tunnel.channels[channel_id] = channel

                # 启动数据转发循环
                await self._forward_loop(channel)
            else:
                # 连接失败，发送失败响应
                writer.write(bytes([SOCKS5.VERSION, SOCKS5.REP_FAILURE, 0, 1, 0, 0, 0, 0, 0, 0]))
                await writer.drain()

        except Exception as e:
            logger.debug(f"SOCKS 错误: {e}")
        finally:
            # 清理资源
            if channel:
                await self.tunnel.close_channel_remote(channel.channel_id)
                await self.tunnel._close_channel(channel)
            try:
                writer.close()
                await writer.wait_closed()
            except:
                pass

    async def _forward_loop(self, channel: Channel):
        """
        从 SOCKS 客户端转发数据到隧道
        
        持续从 SOCKS 客户端读取数据，并通过隧道发送到服务器。
        使用短超时（0.1秒）实现非阻塞读取，允许及时检测连接断开。
        
        Args:
            channel: 通道对象，包含 SOCKS 客户端的读写流
        """
        try:
            while channel.connected and self.tunnel.connected:
                try:
                    # 从 SOCKS 客户端读取数据，超时 0.1 秒
                    data = await asyncio.wait_for(channel.reader.read(32768), timeout=0.1)
                    if data:
                        # 有数据，通过隧道发送到服务器
                        await self.tunnel.send_data(channel.channel_id, data)
                    elif data == b'':
                        # 对端关闭连接
                        break
                except asyncio.TimeoutError:
                    # 超时继续，实现非阻塞读取
                    continue
        except:
            # 发生异常，退出循环
            pass

    async def start(self):
        """
        启动 SOCKS5 服务器
        
        创建异步 TCP 服务器，监听指定地址和端口。
        服务器将持续运行，接受客户端连接。
        """
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        addr = server.sockets[0].getsockname()
        logger.info(f"SOCKS5 代理在 {addr[0]}:{addr[1]}")

        async with server:
            await server.serve_forever()


# ============================================================================
# 主函数
# ============================================================================

async def run_client(config: ClientConfig, ca_cert: str):
    """
    运行客户端并实现自动重连机制
    
    主循环逻辑:
    1. 尝试连接到隧道服务器
    2. 如果连接失败，等待后重试（使用指数退避）
    3. 如果连接成功，启动 SOCKS5 代理服务器
    4. 等待连接断开或用户中断
    5. 清理资源并重新开始循环
    
    重连策略:
    - 初始延迟: 2 秒
    - 最大延迟: 30 秒
    - 连接失败时延迟翻倍（指数退避）
    - 连接成功后重置延迟
    
    Args:
        config: 客户端配置对象
        ca_cert: CA 证书路径
    """
    reconnect_delay = 2  # 重连尝试之间的秒数
    max_reconnect_delay = 30  # 最大延迟
    current_delay = reconnect_delay

    while True:
        # 创建隧道客户端实例
        tunnel = TunnelClient(config, ca_cert)

        # 尝试连接到服务器
        if not await tunnel.connect():
            logger.warning(f"连接失败，{current_delay}秒后重试...")
            await asyncio.sleep(current_delay)
            current_delay = min(current_delay * 2, max_reconnect_delay)
            continue

        # 已连接 - 重置延迟
        current_delay = reconnect_delay
        
        # 在后台启动接收器任务
        receiver_task = asyncio.create_task(tunnel._receiver_loop())
        tunnel.receiver_task = receiver_task

        # 启动 SOCKS5 代理服务器
        socks = SOCKS5Server(tunnel, config.socks_host, config.socks_port)

        try:
            # 创建 SOCKS5 服务器但不阻塞
            socks_server = await asyncio.start_server(
                socks.handle_client,
                socks.host,
                socks.port,
                reuse_address=True  # 允许重启后快速重新绑定
            )
            addr = socks_server.sockets[0].getsockname()
            logger.info(f"SOCKS5 代理在 {addr[0]}:{addr[1]}")

            # 等待: 接收器死亡（连接丢失）或 KeyboardInterrupt
            async with socks_server:
                try:
                    # 等待接收器完成（意味着连接丢失）
                    await receiver_task
                except asyncio.CancelledError:
                    pass

            # 连接丢失 - 立即重连
            if tunnel.connected:
                tunnel.connected = False

            logger.warning("连接丢失，正在重连...")
            current_delay = reconnect_delay  # 为下一次失败重置延迟

        except KeyboardInterrupt:
            # 用户中断，优雅退出
            logger.info("正在关闭...")
            await tunnel.disconnect()
            return 0
        except OSError as e:
            # 处理端口占用等操作系统错误
            if "Address already in use" in str(e):
                logger.error(f"端口 {socks.port} 已被占用，等待中...")
                await asyncio.sleep(2)
            else:
                logger.error(f"SOCKS 服务器错误: {e}")
        finally:
            # 清理资源
            await tunnel.disconnect()
            # 取消接收器任务
            if tunnel.receiver_task:
                tunnel.receiver_task.cancel()
                try:
                    await tunnel.receiver_task
                except asyncio.CancelledError:
                    pass
                tunnel.receiver_task = None

        # 连接丢失后不延迟 - 仅在连接失败时延迟（在循环顶部处理）


def main():
    """
    主函数 - 程序入口点
    
    解析命令行参数，加载配置文件，启动客户端。
    
    命令行参数:
    --config, -c: 配置文件路径（默认: config.yaml）
    --server: 服务器域名（TLS 需要 FQDN）
    --server-port: 服务器端口
    --socks-port, -p: SOCKS5 代理端口
    --username, -u: 认证用户名
    --secret, -s: 认证密钥
    --ca-cert: CA 证书路径
    --debug, -d: 启用调试日志
    
    配置优先级（从高到低）:
    1. 命令行参数
    2. 配置文件中的设置
    3. 默认值
    """
    parser = argparse.ArgumentParser(description='SMTP 隧道客户端（快速模式）')
    parser.add_argument('--config', '-c', default='config.yaml')
    parser.add_argument('--server', default=None, help='服务器域名（TLS 需要 FQDN）')
    parser.add_argument('--server-port', type=int, default=None)
    parser.add_argument('--socks-port', '-p', type=int, default=None)
    parser.add_argument('--username', '-u', default=None, help='认证用户名')
    parser.add_argument('--secret', '-s', default=None)
    parser.add_argument('--ca-cert', default=None)
    parser.add_argument('--debug', '-d', action='store_true')
    args = parser.parse_args()

    # 如果启用了调试模式，设置日志级别为 DEBUG
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # 尝试加载配置文件
    try:
        config_data = load_config(args.config)
    except FileNotFoundError:
        config_data = {}

    # 从配置文件中获取客户端配置
    client_conf = config_data.get('client', {})

    # 创建客户端配置对象，优先使用命令行参数
    config = ClientConfig(
        server_host=args.server or client_conf.get('server_host', 'localhost'),
        server_port=args.server_port or client_conf.get('server_port', 587),
        socks_port=args.socks_port or client_conf.get('socks_port', 1080),
        socks_host=client_conf.get('socks_host', '127.0.0.1'),
        username=args.username or client_conf.get('username', ''),
        secret=args.secret or client_conf.get('secret', ''),
    )

    # 获取 CA 证书路径
    ca_cert = args.ca_cert or client_conf.get('ca_cert')

    # 检查用户名是否配置
    if not config.username:
        logger.error("错误: 未配置用户名。请使用 --username 参数或在配置文件中设置 'username' 字段。")
        return 1

    # 检查密钥是否配置
    if not config.secret:
        logger.error("错误: 未配置密钥。请使用 --secret 参数或在配置文件中设置 'secret' 字段。")
        return 1

    # 运行客户端
    try:
        return asyncio.run(run_client(config, ca_cert))
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    exit(main())
