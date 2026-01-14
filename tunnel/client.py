"""
隧道客户端模块

本模块定义了 SMTP 隧道客户端，负责与 SMTP 隧道服务器建立连接，
执行 SMTP 握手协议，然后切换到高效二进制模式进行数据传输。
"""

import asyncio
import ssl
import logging
import struct
import time
import os
from typing import Dict, Optional, Tuple

from common import TunnelCrypto, ClientConfig
from protocol import (
    FRAME_DATA, FRAME_CONNECT, FRAME_CONNECT_OK,
    FRAME_CONNECT_FAIL, FRAME_CLOSE, FRAME_HEADER_SIZE,
    make_connect_payload
)
from connection import Channel

from .base import BaseTunnel

logger = logging.getLogger('smtp-tunnel-client')


class TunnelClient(BaseTunnel):
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
        connected: 与服务器的连接状态
        next_channel_id: 下一个可用的通道 ID
        channel_lock: 用于保护通道 ID 分配的锁
        connect_events: 连接事件字典，用于等待连接结果
        connect_results: 连接结果字典，存储连接成功/失败状态
        receiver_task: 后台接收任务，负责从服务器接收帧
    """
    
    def __init__(self, config: ClientConfig, ca_cert: str = None):
        """
        初始化隧道客户端
        
        Args:
            config: 客户端配置对象
            ca_cert: CA 证书路径
        """
        super().__init__(None, None)
        
        self.config = config
        self.ca_cert = ca_cert
        self.connected = False
        
        self.next_channel_id = 1
        self.channel_lock = asyncio.Lock()
        
        self.connect_events: Dict[int, asyncio.Event] = {}
        self.connect_results: Dict[int, bool] = {}
        
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
    
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.config.server_host, self.config.server_port),
                timeout=30.0
            )
    
            self.set_reader_writer(reader, writer)
    
            if not await self.smtp_handshake():
                return False
    
            self.connected = True
            logger.info("已连接 - 二进制模式激活")
            return True
    
        except Exception as e:
            logger.error(f"连接失败: {e}")
            return False
    
    async def smtp_handshake(self) -> bool:
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
            line = await self.read_smtp_line()
            if not line or not line.startswith('220'):
                return False
    
            await self.send_smtp_line("EHLO tunnel-client.local")
            if not await self.expect_250():
                return False
    
            await self.send_smtp_line("STARTTLS")
            line = await self.read_smtp_line()
            if not line or not line.startswith('220'):
                return False
    
            await self._upgrade_tls_client()
    
            await self.send_smtp_line("EHLO tunnel-client.local")
            if not await self.expect_250():
                return False
    
            timestamp = int(time.time())
            crypto = TunnelCrypto(self.config.secret, is_server=False)
            token = crypto.generate_auth_token(timestamp, self.config.username)
    
            await self.send_smtp_line(f"AUTH PLAIN {token}")
            line = await self.read_smtp_line()
            if not line or not line.startswith('235'):
                logger.error(f"认证失败: {line}")
                return False
    
            await self.send_smtp_line("BINARY")
            line = await self.read_smtp_line()
            if not line or not line.startswith('299'):
                logger.error(f"二进制模式失败: {line}")
                return False
    
            return True
    
        except Exception as e:
            logger.error(f"握手错误: {e}")
            return False
    
    async def _upgrade_tls_client(self):
        """
        将现有 TCP 连接升级到 TLS 加密连接
        
        使用 asyncio.start_tls 在现有传输上启动 TLS 握手。
        如果提供了 CA 证书，则验证服务器证书；否则跳过验证（仅用于测试）。
        """
        ssl_context = ssl.create_default_context()
        
        if self.ca_cert and os.path.exists(self.ca_cert):
            ssl_context.load_verify_locations(self.ca_cert)
        else:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
    
        await self.upgrade_tls(ssl_context, server_side=False, server_hostname=self.config.server_host)
        logger.debug("TLS 已建立")
    
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
        
        超时设置: 300 秒无数据则继续等待（保持连接活跃）
        """
        await self.binary_mode_loop(timeout=300.0)
        self.connected = False
    
    async def process_frame(self, frame_type: int, channel_id: int, payload: bytes):
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
            if channel_id in self.connect_events:
                self.connect_results[channel_id] = True
                self.connect_events[channel_id].set()
    
        elif frame_type == FRAME_CONNECT_FAIL:
            if channel_id in self.connect_events:
                self.connect_results[channel_id] = False
                self.connect_events[channel_id].set()
    
        elif frame_type == FRAME_DATA:
            channel = self.channels.get(channel_id)
            if channel and channel.connected:
                try:
                    channel.writer.write(payload)
                    await channel.writer.drain()
                except:
                    await self.close_channel(channel)
    
        elif frame_type == FRAME_CLOSE:
            channel = self.channels.get(channel_id)
            if channel:
                await self.close_channel(channel)
    
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
    
        async with self.channel_lock:
            channel_id = self.next_channel_id
            self.next_channel_id += 1
    
        event = asyncio.Event()
        self.connect_events[channel_id] = event
        self.connect_results[channel_id] = False
    
        try:
            payload = make_connect_payload(host, port)
            await self.send_frame(FRAME_CONNECT, channel_id, payload)
        except Exception:
            return channel_id, False
    
        try:
            await asyncio.wait_for(event.wait(), timeout=30.0)
            success = self.connect_results.get(channel_id, False)
        except asyncio.TimeoutError:
            success = False
    
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
    
    async def close_channel(self, channel: Channel):
        """
        关闭本地通道
        
        关闭与 SOCKS 客户端的连接，并从通道字典中移除。
        
        Args:
            channel: 要关闭的通道对象
        """
        if not channel.connected:
            return
        channel.connected = False
    
        try:
            channel.writer.close()
            await channel.writer.wait_closed()
        except:
            pass
    
        self.channels.pop(channel.channel_id, None)
    
    async def cleanup(self):
        """
        断开与服务器的连接并清理资源
        
        执行完整的清理流程:
        1. 关闭所有活跃通道
        2. 关闭与服务器的连接
        3. 清理所有字典和任务引用
        """
        self.connected = False
        
        for channel in list(self.channels.values()):
            await self.close_channel(channel)
        
        if self.writer:
            try:
                self.writer.close()
                await asyncio.wait_for(self.writer.wait_closed(), timeout=2.0)
            except:
                pass
        
        self.reader = None
        self.writer = None
        self.channels.clear()
        self.connect_events.clear()
        self.connect_results.clear()
        
        if self.receiver_task:
            self.receiver_task.cancel()
            try:
                await self.receiver_task
            except asyncio.CancelledError:
                pass
            self.receiver_task = None
    
    async def disconnect(self):
        """
        断开与服务器的连接并清理资源
        
        执行完整的清理流程:
        1. 关闭所有活跃通道
        2. 关闭与服务器的连接
        3. 清理所有字典和任务引用
        """
        await self.cleanup()