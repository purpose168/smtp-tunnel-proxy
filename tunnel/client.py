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
    
    def __init__(self, config, ca_cert: str = None):
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
        
        # 流量整形器（可选）
        self.traffic_shaper = None
        if hasattr(config, 'traffic_enabled') and config.traffic_enabled:
            try:
                from traffic import TrafficShaper
                self.traffic_shaper = TrafficShaper(
                    min_delay_ms=getattr(config, 'traffic_min_delay', 50),
                    max_delay_ms=getattr(config, 'traffic_max_delay', 500),
                    dummy_probability=getattr(config, 'traffic_dummy_probability', 0.1)
                )
                logger.debug(f"流量整形已启用: min_delay={self.traffic_shaper.min_delay_ms}ms, max_delay={self.traffic_shaper.max_delay_ms}ms")
            except ImportError:
                logger.warning("traffic.py 模块未找到，流量整形功能不可用")
    
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
            logger.debug(f"连接配置: username={self.config.username}, ca_cert={self.ca_cert}")
    
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.config.server_host, self.config.server_port),
                timeout=30.0
            )
            
            logger.info(f"TCP 连接建立成功: {self.config.server_host}:{self.config.server_port}")
    
            self.set_reader_writer(reader, writer)
    
            if not await self.smtp_handshake():
                logger.error("SMTP 握手失败")
                return False
    
            self.connected = True
            logger.info("已连接 - 二进制模式激活")
            return True
    
        except asyncio.TimeoutError:
            logger.error(f"连接超时: {self.config.server_host}:{self.config.server_port}")
            return False
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
            logger.debug("等待服务器 220 问候响应...")
            line = await self.read_smtp_line()
            if not line or not line.startswith('220'):
                logger.error(f"未收到 220 响应，收到: {line}")
                return False
            logger.debug(f"收到 220 响应: {line}")
    
            logger.debug("发送 EHLO 命令...")
            await self.send_smtp_line("EHLO tunnel-client.local")
            if not await self.expect_250():
                logger.error("EHLO 命令失败")
                return False
    
            logger.debug("发送 STARTTLS 命令...")
            await self.send_smtp_line("STARTTLS")
            line = await self.read_smtp_line()
            if not line or not line.startswith('220'):
                logger.error(f"STARTTLS 失败，收到: {line}")
                return False
            logger.debug(f"收到 STARTTLS 响应: {line}")
    
            logger.debug("升级到 TLS 连接...")
            await self._upgrade_tls_client()
    
            logger.debug("在 TLS 通道上发送 EHLO 命令...")
            await self.send_smtp_line("EHLO tunnel-client.local")
            if not await self.expect_250():
                logger.error("TLS 通道上的 EHLO 命令失败")
                return False
    
            timestamp = int(time.time())
            from tunnel.crypto import TunnelCrypto
            crypto = TunnelCrypto(self.config.secret, is_server=False)
            token = crypto.generate_auth_token(timestamp, self.config.username)
            
            logger.debug(f"生成认证令牌: timestamp={timestamp}, username={self.config.username}")
    
            logger.debug("发送 AUTH PLAIN 命令...")
            await self.send_smtp_line(f"AUTH PLAIN {token}")
            line = await self.read_smtp_line()
            if not line or not line.startswith('235'):
                logger.error(f"认证失败: {line}")
                return False
            logger.debug(f"收到认证成功响应: {line}")
    
            logger.debug("发送 BINARY 命令...")
            await self.send_smtp_line("BINARY")
            line = await self.read_smtp_line()
            if not line or not line.startswith('299'):
                logger.error(f"二进制模式失败: {line}")
                return False
            logger.debug(f"收到 BINARY 响应: {line}")
    
            logger.info("SMTP 握手成功，切换到二进制模式")
            return True
    
        except Exception as e:
            logger.error(f"握手错误: {e}")
            return False
    
    async def _upgrade_tls_client(self):
        """
        将现有 TCP 连接升级到 TLS 加密连接

        使用 SSL 套接字包装和手动握手在现有传输上启动 TLS 握手。
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
        logger.info("启动后台接收任务...")
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
        logger.debug("进入接收循环...")
        await self.binary_mode_loop(timeout=300.0)
        self.connected = False
        logger.info("接收循环已退出，连接已断开")
    
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
        frame_type_name = self._get_frame_type_name(frame_type)
        logger.debug(f"处理帧: type={frame_type_name}({frame_type}), channel_id={channel_id}, payload_len={len(payload)}")
        
        if frame_type == FRAME_CONNECT_OK:
            logger.debug(f"通道 {channel_id} 连接成功")
            if channel_id in self.connect_events:
                self.connect_results[channel_id] = True
                self.connect_events[channel_id].set()
    
        elif frame_type == FRAME_CONNECT_FAIL:
            logger.warning(f"通道 {channel_id} 连接失败")
            if channel_id in self.connect_events:
                self.connect_results[channel_id] = False
                self.connect_events[channel_id].set()
    
        elif frame_type == FRAME_DATA:
            channel = self.channels.get(channel_id)
            if channel and channel.connected:
                try:
                    # 应用流量整形（如果启用）
                    if self.traffic_shaper:
                        # 添加随机延迟
                        await self.traffic_shaper.delay()
                        
                        # 填充数据到标准大小
                        payload = self.traffic_shaper.pad_data(payload)
                        logger.debug(f"流量整形: 延迟已应用，数据已填充到 {len(payload)} 字节")
                    
                    channel.writer.write(payload)
                    await channel.writer.drain()
                    logger.debug(f"通道 {channel_id} 转发数据: {len(payload)} 字节")
                except Exception as e:
                    logger.error(f"通道 {channel_id} 转发数据失败: {e}")
                    await self.close_channel(channel)
            else:
                logger.warning(f"通道 {channel_id} 不存在或未连接")
    
        elif frame_type == FRAME_CLOSE:
            logger.debug(f"收到关闭帧: channel_id={channel_id}")
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
            logger.warning("尝试打开通道，但隧道未连接")
            return 0, False
    
        async with self.channel_lock:
            channel_id = self.next_channel_id
            self.next_channel_id += 1
            logger.debug(f"分配通道 ID: {channel_id}")
    
        event = asyncio.Event()
        self.connect_events[channel_id] = event
        self.connect_results[channel_id] = False
    
        try:
            payload = make_connect_payload(host, port)
            logger.debug(f"发送连接请求: channel_id={channel_id}, host={host}, port={port}")
            await self.send_frame(FRAME_CONNECT, channel_id, payload)
        except Exception as e:
            logger.error(f"发送连接请求失败: channel_id={channel_id}, error={e}")
            return channel_id, False
    
        try:
            logger.debug(f"等待通道 {channel_id} 连接结果...")
            await asyncio.wait_for(event.wait(), timeout=30.0)
            success = self.connect_results.get(channel_id, False)
        except asyncio.TimeoutError:
            logger.warning(f"通道 {channel_id} 连接超时（30秒）")
            success = False
    
        self.connect_events.pop(channel_id, None)
        self.connect_results.pop(channel_id, None)
    
        if success:
            logger.info(f"通道 {channel_id} 打开成功: {host}:{port}")
        else:
            logger.warning(f"通道 {channel_id} 打开失败: {host}:{port}")
    
        return channel_id, success
    
    async def send_data(self, channel_id: int, data: bytes):
        """
        在指定通道上发送数据
        
        将数据封装为 DATA 帧发送到服务器，服务器会将数据转发到目标主机。
        如果启用了流量整形，会在发送数据前应用延迟和填充。
        
        Args:
            channel_id: 通道标识符
            data: 要发送的数据
        """
        # 应用流量整形（如果启用）
        if self.traffic_shaper:
            # 添加随机延迟
            await self.traffic_shaper.delay()
            
            # 填充数据到标准大小
            data = self.traffic_shaper.pad_data(data)
            logger.debug(f"流量整形: 延迟已应用，数据已填充到 {len(data)} 字节")
        
        logger.debug(f"发送数据到通道 {channel_id}: {len(data)} 字节")
        await self.send_frame(FRAME_DATA, channel_id, data)
    
    async def close_channel_remote(self, channel_id: int):
        """
        通知服务器关闭指定通道
        
        发送 CLOSE 帧到服务器，服务器将关闭对应的连接。
        
        Args:
            channel_id: 要关闭的通道标识符
        """
        logger.debug(f"发送远程关闭请求: channel_id={channel_id}")
        await self.send_frame(FRAME_CLOSE, channel_id)
    
    async def close_channel(self, channel: Channel):
        """
        关闭本地通道
        
        关闭与 SOCKS 客户端的连接，并从通道字典中移除。
        
        Args:
            channel: 要关闭的通道对象
        """
        if not channel.connected:
            logger.debug(f"通道 {channel.channel_id} 已关闭，跳过")
            return
        channel.connected = False
    
        logger.debug(f"关闭本地通道: channel_id={channel.channel_id}")
        try:
            channel.writer.close()
            await channel.writer.wait_closed()
            logger.debug(f"通道 {channel.channel_id} 本地连接已关闭")
        except Exception as e:
            logger.error(f"关闭通道 {channel.channel_id} 失败: {e}")
    
        self.channels.pop(channel.channel_id, None)
        logger.debug(f"通道 {channel.channel_id} 已从字典中移除")
    
    async def cleanup(self):
        """
        断开与服务器的连接并清理资源
        
        执行完整的清理流程:
        1. 关闭所有活跃通道
        2. 关闭与服务器的连接
        3. 清理所有字典和任务引用
        """
        logger.info("开始清理资源...")
        self.connected = False
        
        active_channels = len(self.channels)
        logger.debug(f"关闭 {active_channels} 个活跃通道...")
        
        for channel in list(self.channels.values()):
            await self.close_channel(channel)
        
        if self.writer:
            try:
                logger.debug("关闭与服务器的连接...")
                self.writer.close()
                await asyncio.wait_for(self.writer.wait_closed(), timeout=2.0)
                logger.info("与服务器的连接已关闭")
            except Exception as e:
                logger.error(f"关闭服务器连接失败: {e}")
        
        self.reader = None
        self.writer = None
        self.channels.clear()
        self.connect_events.clear()
        self.connect_results.clear()
        
        logger.info("资源清理完成")
        
        if self.receiver_task:
            logger.debug("取消后台接收任务...")
            self.receiver_task.cancel()
            try:
                await self.receiver_task
            except asyncio.CancelledError:
                logger.debug("后台接收任务已取消")
            self.receiver_task = None
    
    async def disconnect(self):
        """
        断开与服务器的连接并清理资源
        
        执行完整的清理流程:
        1. 关闭所有活跃通道
        2. 关闭与服务器的连接
        3. 清理所有字典和任务引用
        """
        logger.info("断开与服务器的连接...")
        await self.cleanup()
    
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