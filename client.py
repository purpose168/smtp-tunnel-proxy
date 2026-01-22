#!/usr/bin/env python3
"""
SMTP 隧道客户端 - 快速二进制模式

版本: 1.3.0

协议说明:
1. SMTP 握手 (EHLO, STARTTLS, AUTH) - 模拟真实 SMTP 协议
2. AUTH 完成后,发送 "BINARY" 切换到流式传输模式
3. 全双工二进制协议 - 数据以 TCP 允许的最快速度传输

功能特点:
- 多用户支持 (用户名 + 密钥认证)
- 支持 SOCKS5 代理协议
- 自动重连机制
- TLS 加密传输
- 高性能全双工数据传输
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

# 配置日志格式,输出时间、日志级别和消息内容
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
# 获取客户端专用的日志记录器
logger = logging.getLogger('smtp-tunnel-client')


# ============================================================================
# 二进制协议定义
# ============================================================================

# 帧类型常量定义
FRAME_DATA = 0x01        # 数据帧 - 用于传输实际数据
FRAME_CONNECT = 0x02     # 连接帧 - 用于建立新连接
FRAME_CONNECT_OK = 0x03  # 连接成功帧 - 服务器确认连接成功
FRAME_CONNECT_FAIL = 0x04 # 连接失败帧 - 服务器拒绝连接
FRAME_CLOSE = 0x05       # 关闭帧 - 用于关闭连接
FRAME_HEADER_SIZE = 5     # 帧头大小 - 1字节帧类型 + 2字节通道ID + 2字节载荷长度

def make_frame(frame_type: int, channel_id: int, payload: bytes = b'') -> bytes:
    """
    创建二进制协议帧
    
    参数:
        frame_type: 帧类型 (数据/连接/关闭等)
        channel_id: 通道ID,用于标识不同的连接
        payload: 载荷数据 (可选)
        
    返回:
        完整的二进制帧,格式为: 帧类型(1B) + 通道ID(2B) + 载荷长度(2B) + 载荷数据
    """
    return struct.pack('>BHH', frame_type, channel_id, len(payload)) + payload

def make_connect_payload(host: str, port: int) -> bytes:
    """
    创建连接请求载荷
    
    参数:
        host: 目标主机名
        port: 目标端口
        
    返回:
        连接载荷二进制数据,格式为: 主机名长度(1B) + 主机名 + 端口(2B)
    """
    host_bytes = host.encode('utf-8')
    return struct.pack('>B', len(host_bytes)) + host_bytes + struct.pack('>H', port)


# ============================================================================
# SOCKS5 协议定义
# ============================================================================

class SOCKS5:
    """SOCKS5 代理协议常量定义"""
    VERSION = 0x05        # SOCKS5 协议版本
    AUTH_NONE = 0x00      # 无需认证
    CMD_CONNECT = 0x01    # 连接命令
    ATYP_IPV4 = 0x01      # IPv4 地址类型
    ATYP_DOMAIN = 0x03    # 域名地址类型
    ATYP_IPV6 = 0x04      # IPv6 地址类型
    REP_SUCCESS = 0x00    # 成功响应
    REP_FAILURE = 0x01    # 失败响应


@dataclass
class Channel:
    """
    通道数据类
    
    用于维护每个 SOCKS5 连接的状态和 I/O 流
    """
    channel_id: int                    # 通道唯一标识符
    reader: asyncio.StreamReader      # 异步读取流
    writer: asyncio.StreamWriter      # 异步写入流
    host: str                          # 目标主机名
    port: int                          # 目标端口号
    connected: bool = False           # 连接状态标志


# ============================================================================
# 隧道客户端
# ============================================================================

class TunnelClient:
    """
    SMTP 隧道客户端
    
    负责与服务端建立 SMTP 连接,完成握手和认证,然后切换到二进制模式进行数据传输
    支持多通道并发,每个通道对应一个 SOCKS5 连接
    """
    
    def __init__(self, config: ClientConfig, ca_cert: str = None):
        """
        初始化隧道客户端
        
        参数:
            config: 客户端配置对象,包含服务器地址、端口、用户名等信息
            ca_cert: CA 证书路径,用于 TLS 验证 (可选)
        """
        self.config = config
        self.ca_cert = ca_cert

        # 与服务端的连接流
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.connected = False

        # 通道管理
        self.channels: Dict[int, Channel] = {}      # 所有活跃通道
        self.next_channel_id = 1                     # 下一个通道ID
        self.channel_lock = asyncio.Lock()          # 通道ID分配锁
        # 添加通道ID回收机制
        self.available_channel_ids = []             # 可用的通道ID列表
        self.max_channel_id = 1000                 # 最大通道ID

        # 连接事件管理 - 用于等待服务器响应
        self.connect_events: Dict[int, asyncio.Event] = {}    # 通道连接事件
        self.connect_results: Dict[int, bool] = {}            # 连接结果缓存

        # 写入锁 - 防止并发写入导致数据混乱
        self.write_lock = asyncio.Lock()

        # 添加资源监控
        self.max_channels = 1000  # 最大通道数
        self.max_buffer_size = 10 * 1024 * 1024  # 最大缓冲区大小: 10MB

        # 添加连接统计
        self.total_connections = 0
        self.failed_connections = 0
        self.closed_connections = 0

    async def connect(self) -> bool:
        """
        连接到服务器并完成 SMTP 握手,然后切换到二进制模式
        
        返回:
            bool: 连接成功返回 True,失败返回 False
        """
        try:
            logger.info(f"正在连接到 {self.config.server_host}:{self.config.server_port}")

            # 建立与服务器的 TCP 连接,超时时间 30 秒
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.config.server_host, self.config.server_port),
                timeout=30.0
            )

            # 执行 SMTP 握手流程
            if not await self._smtp_handshake():
                return False

            self.connected = True
            logger.info("已连接 - 二进制模式已激活")
            return True

        except Exception as e:
            logger.error(f"连接失败: {e}")
            return False

    async def _smtp_handshake(self) -> bool:
        """
        执行 SMTP 握手流程,然后切换到二进制模式
        
        流程:
        1. 接收服务器欢迎消息
        2. 发送 EHLO 命令
        3. 发送 STARTTLS 命令并升级 TLS
        4. 再次发送 EHLO 命令
        5. 进行身份认证
        6. 发送 BINARY 命令切换到二进制模式
        
        返回:
            bool: 握手成功返回 True,失败返回 False
        """
        try:
            logger.info("开始 SMTP 握手流程")
            
            # 等待服务器欢迎消息 (220)
            logger.debug("等待服务器欢迎消息 (220)")
            line = await self._read_line()
            if not line or not line.startswith('220'):
                logger.error(f"未收到有效的欢迎消息: {line}")
                return False
            logger.info(f"收到服务器欢迎消息: {line}")

            # 发送 EHLO 命令
            logger.debug("发送 EHLO 命令")
            await self._send_line("EHLO tunnel-client.local")
            if not await self._expect_250():
                logger.error("EHLO 命令响应错误")
                return False
            logger.info("EHLO 命令成功")

            # 发送 STARTTLS 命令
            logger.debug("发送 STARTTLS 命令")
            await self._send_line("STARTTLS")
            line = await self._read_line()
            if not line or not line.startswith('220'):
                logger.error(f"STARTTLS 命令响应错误: {line}")
                return False
            logger.info(f"STARTTLS 命令成功: {line}")

            # 升级到 TLS 加密连接
            logger.info("开始 TLS 升级")
            await self._upgrade_tls()
            logger.info("TLS 升级完成")

            # TLS 升级后再次发送 EHLO
            logger.debug("TLS 升级后再次发送 EHLO 命令")
            await self._send_line("EHLO tunnel-client.local")
            if not await self._expect_250():
                logger.error("TLS 升级后 EHLO 命令响应错误")
                return False
            logger.info("TLS 升级后 EHLO 命令成功")

            # 进行身份认证
            logger.info(f"开始身份认证,用户名: {self.config.username}")
            timestamp = int(time.time())
            crypto = TunnelCrypto(self.config.secret, is_server=False)
            token = crypto.generate_auth_token(timestamp, self.config.username)

            logger.debug("发送 AUTH PLAIN 命令")
            await self._send_line(f"AUTH PLAIN {token}")
            line = await self._read_line()
            if not line or not line.startswith('235'):
                logger.error(f"认证失败: {line}")
                return False
            logger.info(f"身份认证成功: {line}")

            # 切换到二进制模式
            logger.debug("发送 BINARY 命令切换到二进制模式")
            await self._send_line("BINARY")
            line = await self._read_line()
            if not line or not line.startswith('299'):
                logger.error(f"切换二进制模式失败: {line}")
                return False
            logger.info(f"成功切换到二进制模式: {line}")

            logger.info("SMTP 握手流程完成")
            return True

        except Exception as e:
            logger.error(f"握手错误: {e}")
            return False

    async def _upgrade_tls(self):
        """
        将连接升级为 TLS 加密
        
        使用系统默认的 SSL 上下文,如果提供了 CA 证书则使用证书验证
        """
        logger.debug("创建 SSL 上下文")
        ssl_context = ssl.create_default_context()
        if self.ca_cert and os.path.exists(self.ca_cert):
            # 使用自定义 CA 证书进行验证
            logger.info(f"使用自定义 CA 证书: {self.ca_cert}")
            ssl_context.load_verify_locations(self.ca_cert)
        else:
            # 跳过主机名验证和证书验证 (用于自签名证书)
            logger.warning("未提供 CA 证书或证书不存在,跳过证书验证")
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        # 获取现有的传输层和协议对象
        logger.debug("获取现有传输层和协议对象")
        transport = self.writer.transport
        protocol = self.writer._protocol
        loop = asyncio.get_event_loop()

        # 启动 TLS 握手,返回新的传输层
        logger.debug("启动 TLS 握手")
        new_transport = await loop.start_tls(
            transport, protocol, ssl_context,
            server_hostname=self.config.server_host
        )

        # 更新 writer 和 reader 的传输层引用
        self.writer._transport = new_transport
        self.reader._transport = new_transport
        logger.debug("TLS 加密已建立")

    async def _send_line(self, line: str):
        """
        发送一行文本数据
        
        参数:
            line: 要发送的文本,会自动添加 CRLF 换行符
        """
        logger.debug(f"发送行: {line}")
        self.writer.write(f"{line}\r\n".encode())
        await self.writer.drain()

    async def _read_line(self) -> Optional[str]:
        """
        读取一行文本数据
        
        返回:
            str: 读取的文本行,去除首尾空白
            None: 超时或连接断开
        """
        try:
            # 读取一行,超时时间 60 秒
            data = await asyncio.wait_for(self.reader.readline(), timeout=60.0)
            if not data:
                logger.debug("读取行失败: 连接断开")
                return None
            line = data.decode('utf-8', errors='replace').strip()
            logger.debug(f"读取行: {line}")
            return line
        except Exception as e:
            logger.debug(f"读取行超时或错误: {e}")
            return None

    async def _expect_250(self) -> bool:
        """
        期望并跳过 SMTP 多行响应,直到收到 250 成功响应
        
        SMTP 命令可能返回多行响应,每行以 250- 开头,最后一行以 250 开头
        
        返回:
            bool: 收到 250 响应返回 True,否则返回 False
        """
        while True:
            line = await self._read_line()
            if not line:
                return False
            if line.startswith('250 '):
                return True
            if line.startswith('250-'):
                continue
            return False

    async def start_receiver(self):
        """启动后台任务,持续接收来自服务器的帧"""
        logger.info("启动帧接收器")
        asyncio.create_task(self._receiver_loop())
        asyncio.create_task(self._report_stats())
        asyncio.create_task(self._cleanup_zombie_channels())

    async def _receiver_loop(self):
        """
        接收并分发来自服务器的帧
        
        持续读取二进制数据,解析帧,并根据帧类型进行相应处理
        """
        buffer = b''  # 接收缓冲区
        logger.debug("帧接收器循环开始")

        while self.connected:
            try:
                # 读取数据,超时时间 300 秒 (5分钟)
                chunk = await asyncio.wait_for(self.reader.read(65536), timeout=300.0)
                if not chunk:
                    logger.info("服务器连接已断开")
                    break
                buffer += chunk
                logger.debug(f"接收到数据块: {len(chunk)} 字节")

                # 检查缓冲区大小
                if len(buffer) > self.max_buffer_size:
                    logger.error(f"缓冲区大小超过限制: {len(buffer)} > {self.max_buffer_size}")
                    logger.error("可能收到恶意数据或协议错误，断开连接")
                    break

                # 处理缓冲区中的完整帧
                while len(buffer) >= FRAME_HEADER_SIZE:
                    # 解析帧头: 帧类型(1B) + 通道ID(2B) + 载荷长度(2B)
                    frame_type, channel_id, payload_len = struct.unpack('>BHH', buffer[:5])
                    total_len = FRAME_HEADER_SIZE + payload_len

                    # 检查载荷长度是否合理
                    if payload_len > self.max_buffer_size:
                        logger.error(f"载荷长度过大: {payload_len} > {self.max_buffer_size}")
                        break

                    # 如果数据不足一个完整帧,等待更多数据
                    if len(buffer) < total_len:
                        logger.debug(f"数据不足一个完整帧,需要 {total_len} 字节,当前 {len(buffer)} 字节")
                        break

                    # 提取载荷并从缓冲区移除
                    payload = buffer[FRAME_HEADER_SIZE:total_len]
                    buffer = buffer[total_len:]

                    # 处理该帧
                    logger.debug(f"处理帧: 类型={frame_type}, 通道ID={channel_id}, 载荷长度={payload_len}")
                    await self._handle_frame(frame_type, channel_id, payload)

            except asyncio.TimeoutError:
                # 超时继续循环,保持连接活跃
                logger.debug("接收数据超时,继续等待")
                continue
            except Exception as e:
                logger.error(f"接收器错误: {e}")
                break

        # 连接断开
        logger.info("帧接收器循环结束")
        self.connected = False

    async def _handle_frame(self, frame_type: int, channel_id: int, payload: bytes):
        """
        处理接收到的帧
        
        参数:
            frame_type: 帧类型 (数据/连接成功/连接失败/关闭)
            channel_id: 通道ID
            payload: 帧载荷数据
        """
        if frame_type == FRAME_CONNECT_OK:
            # 连接成功 - 唤醒等待该通道连接的事件
            logger.info(f"通道 {channel_id} 连接成功")
            if channel_id in self.connect_events:
                self.connect_results[channel_id] = True
                self.connect_events[channel_id].set()

        elif frame_type == FRAME_CONNECT_FAIL:
            # 连接失败 - 唤醒等待该通道连接的事件
            logger.warning(f"通道 {channel_id} 连接失败")
            if channel_id in self.connect_events:
                self.connect_results[channel_id] = False
                self.connect_events[channel_id].set()

        elif frame_type == FRAME_DATA:
            # 数据帧 - 将数据转发到对应的通道
            channel = self.channels.get(channel_id)
            if channel and channel.connected:
                try:
                    channel.writer.write(payload)
                    await channel.writer.drain()
                    logger.debug(f"通道 {channel_id} 转发数据: {len(payload)} 字节")
                except Exception as e:
                    # 写入失败,关闭通道
                    logger.error(f"通道 {channel_id} 写入数据失败: {e}")
                    await self._close_channel(channel)

        elif frame_type == FRAME_CLOSE:
            # 关闭帧 - 关闭对应的通道
            logger.info(f"收到通道 {channel_id} 关闭帧")
            channel = self.channels.get(channel_id)
            if channel:
                await self._close_channel(channel)

    async def send_frame(self, frame_type: int, channel_id: int, payload: bytes = b''):
        """
        向服务器发送帧
        
        参数:
            frame_type: 帧类型
            channel_id: 通道ID
            payload: 载荷数据
        """
        if not self.connected or not self.writer:
            logger.warning("未连接到服务器,无法发送帧")
            return
        async with self.write_lock:
            try:
                frame = make_frame(frame_type, channel_id, payload)
                self.writer.write(frame)
                await self.writer.drain()
                logger.debug(f"发送帧: 类型={frame_type}, 通道ID={channel_id}, 载荷长度={len(payload)}")
            except Exception as e:
                # 发送失败,标记连接断开
                logger.error(f"发送帧失败: {e}")
                self.connected = False

    async def open_channel(self, host: str, port: int) -> Tuple[int, bool]:
        """
        打开一个隧道通道
        
        向服务器发送连接请求,等待服务器响应
        
        参数:
            host: 目标主机名
            port: 目标端口
            
        返回:
            Tuple[int, bool]: (通道ID, 是否成功)
        """
        self.total_connections += 1
        
        if not self.connected:
            logger.warning("未连接到服务器,无法打开通道")
            return 0, False

        # 检查通道数量限制
        if len(self.channels) >= self.max_channels:
            logger.error(f"通道数量超过限制: {len(self.channels)} >= {self.max_channels}")
            return 0, False

        # 分配新的通道ID（优先回收）
        async with self.channel_lock:
            if self.available_channel_ids:
                channel_id = self.available_channel_ids.pop()
                logger.debug(f"回收通道ID: {channel_id}")
            else:
                channel_id = self.next_channel_id
                self.next_channel_id += 1
                if self.next_channel_id > self.max_channel_id:
                    self.next_channel_id = 1  # 循环使用
                    logger.debug(f"通道ID循环到 1")

        logger.info(f"打开通道 {channel_id}: {host}:{port}")

        # 创建事件用于等待服务器响应
        event = asyncio.Event()
        self.connect_events[channel_id] = event
        self.connect_results[channel_id] = False

        # 发送连接请求
        try:
            payload = make_connect_payload(host, port)
            await self.send_frame(FRAME_CONNECT, channel_id, payload)
            logger.debug(f"已发送通道 {channel_id} 连接请求")
        except Exception as e:
            logger.error(f"发送通道 {channel_id} 连接请求失败: {e}")
            # 清理事件和结果
            self.connect_events.pop(channel_id, None)
            self.connect_results.pop(channel_id, None)
            self.failed_connections += 1
            return channel_id, False

        # 减少超时时间: 30 秒 -> 10 秒
        try:
            await asyncio.wait_for(event.wait(), timeout=10.0)
            success = self.connect_results.get(channel_id, False)
            if success:
                logger.info(f"通道 {channel_id} 打开成功")
            else:
                logger.warning(f"通道 {channel_id} 打开失败")
                self.failed_connections += 1
                # 注意：不清理通道对象，因为通道对象可能还没有被创建
                # 通道对象会在SOCKS5连接成功后被创建，并在SOCKS5连接失败时被清理
        except asyncio.TimeoutError:
            logger.error(f"通道 {channel_id} 打开超时")
            success = False
            self.failed_connections += 1
            # 通知服务器关闭连接
            try:
                await self.send_frame(FRAME_CLOSE, channel_id, b'')
                logger.debug(f"已通知服务器关闭通道 {channel_id}")
            except Exception as e:
                logger.error(f"发送关闭帧失败: {e}")
            # 注意：不清理通道对象，因为通道对象可能还没有被创建
            # 通道对象会在SOCKS5连接成功后被创建，并在SOCKS5连接失败时被清理

        # 清理事件和结果
        self.connect_events.pop(channel_id, None)
        self.connect_results.pop(channel_id, None)

        return channel_id, success

    async def send_data(self, channel_id: int, data: bytes):
        """
        在通道上发送数据
        
        参数:
            channel_id: 通道ID
            data: 要发送的数据
        """
        logger.debug(f"通道 {channel_id} 发送数据: {len(data)} 字节")
        await self.send_frame(FRAME_DATA, channel_id, data)

    async def close_channel_remote(self, channel_id: int):
        """
        通知服务器关闭通道
        
        参数:
            channel_id: 要关闭的通道ID
        """
        logger.info(f"通知服务器关闭通道 {channel_id}")
        await self.send_frame(FRAME_CLOSE, channel_id)

    async def _close_channel(self, channel: Channel):
        """
        关闭本地通道
        
        参数:
            channel: 要关闭的通道对象
        """
        if not channel:
            logger.debug("通道对象为空，跳过关闭")
            return
        
        if not channel.connected:
            logger.debug(f"通道 {channel.channel_id} 已断开，跳过关闭")
            return
        
        logger.info(f"关闭本地通道 {channel.channel_id}")
        channel.connected = False
        self.closed_connections += 1

        # 关闭写入流
        try:
            if hasattr(channel, 'writer') and channel.writer:
                channel.writer.close()
                await asyncio.wait_for(channel.writer.wait_closed(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning(f"关闭通道 {channel.channel_id} writer 超时,强制关闭")
            try:
                if hasattr(channel.writer, 'transport'):
                    channel.writer.transport.abort()
            except Exception as e:
                logger.error(f"强制关闭 transport 失败: {e}")
        except Exception as e:
            logger.error(f"关闭通道 {channel.channel_id} writer 失败: {e}")
            try:
                if hasattr(channel.writer, 'transport'):
                    channel.writer.transport.abort()
            except Exception as e2:
                logger.error(f"强制关闭 transport 失败: {e2}")
        finally:
            # 最后的手段：强制关闭Socket
            try:
                if (hasattr(channel, 'writer') and 
                    channel.writer and 
                    hasattr(channel.writer, 'transport') and 
                    channel.writer.transport and 
                    hasattr(channel.writer.transport, '_sock') and 
                    channel.writer.transport._sock is not None):
                    channel.writer.transport._sock.close()
            except Exception as e:
                logger.error(f"强制关闭 Socket 失败: {e}")

        # 从通道列表中移除
        if channel.channel_id in self.channels:
            self.channels.pop(channel.channel_id)
            logger.debug(f"已从通道列表中移除通道 {channel.channel_id}")

        # 清理连接事件和结果
        if channel.channel_id in self.connect_events:
            self.connect_events.pop(channel.channel_id)
            logger.debug(f"已清理通道 {channel.channel_id} 事件对象")
        
        if channel.channel_id in self.connect_results:
            self.connect_results.pop(channel.channel_id)
            logger.debug(f"已清理通道 {channel.channel_id} 结果对象")

        # 回收通道ID
        if channel.channel_id not in self.available_channel_ids:
            self.available_channel_ids.append(channel.channel_id)
            logger.debug(f"回收通道ID: {channel.channel_id}")

    async def _report_stats(self):
        """定期报告连接统计"""
        while self.connected:
            try:
                await asyncio.sleep(60)  # 每分钟报告一次
                import asyncio
                task_count = len(asyncio.all_tasks())
                
                # 添加文件描述符监控
                try:
                    import psutil
                    import os
                    proc = psutil.Process(os.getpid())
                    num_fds = proc.num_fds() if hasattr(proc, 'num_fds') else 0
                    memory_mb = proc.memory_info().rss / 1024 / 1024
                    cpu_percent = proc.cpu_percent(interval=0.1)
                except ImportError:
                    num_fds = 0
                    memory_mb = 0
                    cpu_percent = 0
                
                logger.info(f"连接统计: 总计={self.total_connections}, "
                           f"失败={self.failed_connections}, "
                           f"关闭={self.closed_connections}, "
                           f"活跃={len(self.channels)}, "
                           f"事件={len(self.connect_events)}, "
                           f"结果={len(self.connect_results)}, "
                           f"任务={task_count}, "
                           f"可用ID={len(self.available_channel_ids)}, "
                           f"下一个ID={self.next_channel_id}, "
                           f"文件描述符={num_fds}, "
                           f"内存={memory_mb:.1f}MB, "
                           f"CPU={cpu_percent:.1f}%")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"报告连接统计时出错: {e}")

    async def _cleanup_zombie_channels(self):
        """清理僵尸连接"""
        while self.connected:
            try:
                await asyncio.sleep(30)  # 每 30 秒检查一次
                
                zombie_channels = []
                for channel_id, channel in self.channels.items():
                    try:
                        # 检查连接是否仍然活跃
                        if channel.writer.is_closing():
                            zombie_channels.append(channel_id)
                            logger.warning(f"发现僵尸连接: 通道 {channel_id}")
                    except Exception as e:
                        zombie_channels.append(channel_id)
                        logger.warning(f"检查通道 {channel_id} 时出错: {e}")
                
                # 清理僵尸连接
                for channel_id in zombie_channels:
                    if channel_id in self.channels:
                        channel = self.channels[channel_id]
                        await self._close_channel(channel)
                        logger.info(f"已清理僵尸连接: 通道 {channel_id}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"清理僵尸连接时出错: {e}")

    async def disconnect(self):
        """断开连接并清理所有资源"""
        logger.info("开始断开连接")
        self.connected = False
        
        # 关闭所有通道
        channel_count = len(self.channels)
        logger.info(f"关闭 {channel_count} 个活跃通道")
        for channel in list(self.channels.values()):
            await self._close_channel(channel)
        
        # 关闭与服务器的连接
        if self.writer:
            try:
                self.writer.close()
                await asyncio.wait_for(self.writer.wait_closed(), timeout=2.0)
                logger.info("与服务器的连接已关闭")
            except Exception as e:
                logger.error(f"关闭与服务器的连接失败: {e}")
        
        # 清理所有事件和结果
        event_count = len(self.connect_events)
        result_count = len(self.connect_results)
        if event_count > 0 or result_count > 0:
            logger.warning(f"清理 {event_count} 个连接事件和 {result_count} 个连接结果")
        self.connect_events.clear()
        self.connect_results.clear()
        
        # 清理所有资源
        self.reader = None
        self.writer = None
        self.channels.clear()
        logger.info("连接断开,所有资源已清理")


# ============================================================================
# SOCKS5 代理服务器
# ============================================================================

class SOCKS5Server:
    """
    SOCKS5 代理服务器
    
    在本地监听 SOCKS5 连接,将连接请求通过隧道转发到远程服务器
    充当本地 SOCKS5 代理和隧道客户端之间的桥梁
    """
    
    def __init__(self, tunnel: TunnelClient, host: str = '127.0.0.1', port: int = 1080):
        """
        初始化 SOCKS5 服务器
        
        参数:
            tunnel: 隧道客户端实例,用于转发连接
            host: 监听地址 (默认: 127.0.0.1)
            port: 监听端口 (默认: 1080)
        """
        self.tunnel = tunnel
        self.host = host
        self.port = port
        # 添加连接速率限制
        self.max_connections = 100  # 最大并发连接数
        self.current_connections = 0
        self.connection_semaphore = asyncio.Semaphore(self.max_connections)

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """
        处理 SOCKS5 客户端连接
        
        流程:
        1. 握手阶段 - 确认 SOCKS5 版本,选择认证方式
        2. 请求阶段 - 解析连接请求,获取目标地址和端口
        3. 连接阶段 - 通过隧道建立连接
        4. 转发阶段 - 在客户端和隧道之间转发数据
        
        参数:
            reader: 客户端读取流
            writer: 客户端写入流
        """
        # 使用信号量限制并发连接
        async with self.connection_semaphore:
            channel = None
            try:
                self.current_connections += 1
                logger.info(f"当前连接数: {self.current_connections}/{self.max_connections}")

                # 检查隧道是否已连接
                if not self.tunnel.connected:
                    logger.warning("隧道未连接,拒绝客户端请求")
                    writer.close()
                    await writer.wait_closed()
                    return

                # SOCKS5 握手 - 读取客户端版本和认证方法
                logger.debug("开始 SOCKS5 握手")
                # 添加超时: 10 秒
                data = await asyncio.wait_for(reader.read(2), timeout=10.0)
                if len(data) < 2 or data[0] != SOCKS5.VERSION:
                    logger.warning(f"无效的 SOCKS5 版本: {data[0] if data else 'None'}")
                    writer.close()
                    await writer.wait_closed()
                    return

                nmethods = data[1]
                logger.debug(f"客户端支持的认证方法数量: {nmethods}")
                # 添加超时: 10 秒
                await asyncio.wait_for(reader.read(nmethods), timeout=10.0)

                # 响应握手 - 选择无需认证
                logger.debug("发送握手响应: 选择无需认证")
                writer.write(bytes([SOCKS5.VERSION, SOCKS5.AUTH_NONE]))
                await writer.drain()

                # 读取连接请求
                logger.debug("等待连接请求")
                # 添加超时: 10 秒
                data = await asyncio.wait_for(reader.read(4), timeout=10.0)
                if len(data) < 4:
                    logger.warning("未收到完整的连接请求")
                    writer.close()
                    await writer.wait_closed()
                    return

                version, cmd, _, atyp = data
                logger.debug(f"连接请求: 版本={version}, 命令={cmd}, 地址类型={atyp}")

                # 只支持 CONNECT 命令
                if cmd != SOCKS5.CMD_CONNECT:
                    logger.warning(f"不支持的命令: {cmd}")
                    writer.write(bytes([SOCKS5.VERSION, 0x07, 0, 1, 0, 0, 0, 0, 0, 0]))
                    await writer.drain()
                    writer.close()
                    await writer.wait_closed()
                    return

                # 解析目标地址
                if atyp == SOCKS5.ATYP_IPV4:
                    # IPv4 地址 (4字节)
                    addr_data = await reader.read(4)
                    host = socket.inet_ntoa(addr_data)
                    logger.debug(f"解析 IPv4 地址: {host}")
                elif atyp == SOCKS5.ATYP_DOMAIN:
                    # 域名 (1字节长度 + 域名)
                    # 添加超时: 10 秒
                    length = (await asyncio.wait_for(reader.read(1), timeout=10.0))[0]
                    # 添加超时: 10 秒
                    host = (await asyncio.wait_for(reader.read(length), timeout=10.0)).decode()
                    logger.debug(f"解析域名: {host}")
                elif atyp == SOCKS5.ATYP_IPV6:
                    # IPv6 地址 (16字节)
                    addr_data = await reader.read(16)
                    host = socket.inet_ntop(socket.AF_INET6, addr_data)
                    logger.debug(f"解析 IPv6 地址: {host}")
                else:
                    logger.warning(f"不支持的地址类型: {atyp}")
                    writer.close()
                    await writer.wait_closed()
                    return

                # 读取目标端口 (2字节大端序)
                port_data = await reader.read(2)
                port = struct.unpack('>H', port_data)[0]

                logger.info(f"SOCKS5 连接请求: {host}:{port}")

                # 通过隧道打开连接
                channel_id, success = await self.tunnel.open_channel(host, port)

                if success:
                    # 连接成功 - 响应客户端
                    logger.info(f"SOCKS5 连接成功: {host}:{port} -> 通道 {channel_id}")
                    writer.write(bytes([SOCKS5.VERSION, SOCKS5.REP_SUCCESS, 0, 1, 0, 0, 0, 0, 0, 0]))
                    await writer.drain()

                    # 创建通道对象并注册
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
                    logger.debug(f"启动通道 {channel_id} 数据转发循环")
                    await self._forward_loop(channel)
                else:
                    # 连接失败 - 通知客户端
                    logger.warning(f"SOCKS5 连接失败: {host}:{port}")
                    writer.write(bytes([SOCKS5.VERSION, SOCKS5.REP_FAILURE, 0, 1, 0, 0, 0, 0, 0, 0]))
                    await writer.drain()
                    # 注意：不清理通道对象，因为通道对象可能还没有被创建
                    # 通道对象只有在连接成功时才会被创建
                    return

            except asyncio.TimeoutError:
                logger.warning("SOCKS5 客户端操作超时")
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                logger.debug(f"SOCKS 错误: {e}")
            finally:
                # 清理: 通知服务器关闭通道,关闭客户端连接
                if channel:
                    logger.debug(f"清理通道 {channel.channel_id}")
                    await self.tunnel.close_channel_remote(channel.channel_id)
                    await self.tunnel._close_channel(channel)

                # 确保在所有情况下都关闭 writer
                try:
                    writer.close()
                    await asyncio.wait_for(writer.wait_closed(), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("关闭 writer 超时,强制关闭")
                    try:
                        writer.transport.abort()
                    except Exception as e:
                        logger.error(f"强制关闭 transport 失败: {e}")
                except Exception as e:
                    logger.debug(f"关闭客户端连接失败: {e}")
                    try:
                        writer.transport.abort()
                    except Exception as e2:
                        logger.error(f"强制关闭 transport 失败: {e2}")
                finally:
                    # 最后的手段：强制关闭Socket
                    try:
                        if (hasattr(writer, 'transport') and 
                            writer.transport and 
                            hasattr(writer.transport, '_sock') and 
                            writer.transport._sock is not None):
                            writer.transport._sock.close()
                    except Exception as e:
                        logger.error(f"强制关闭 Socket 失败: {e}")

                # 确保计数器被减少
                self.current_connections -= 1
                logger.debug(f"连接已关闭,当前连接数: {self.current_connections}/{self.max_connections}")

    async def _forward_loop(self, channel: Channel):
        """
        数据转发循环
        
        从 SOCKS5 客户端读取数据,通过隧道发送到服务器
        
        参数:
            channel: 通道对象
        """
        try:
            while channel.connected and self.tunnel.connected:
                try:
                    data = await asyncio.wait_for(channel.reader.read(32768), timeout=0.1)
                    if data:
                        await self.tunnel.send_data(channel.channel_id, data)
                        logger.debug(f"通道 {channel.channel_id} 转发数据到隧道: {len(data)} 字节")
                    elif data == b'':
                        logger.info(f"通道 {channel.channel_id} 客户端断开连接")
                        break
                except asyncio.TimeoutError:
                    continue
        except Exception as e:
            logger.error(f"通道 {channel.channel_id} 转发循环异常: {e}")
            if channel.connected:
                channel.connected = False

    async def start(self):
        """
        启动 SOCKS5 服务器
        
        在指定地址和端口上监听并接受客户端连接
        """
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        addr = server.sockets[0].getsockname()
        logger.info(f"SOCKS5 代理服务已启动: {addr[0]}:{addr[1]}")

        async with server:
            await server.serve_forever()


# ============================================================================
# 主程序
# ============================================================================

async def run_client(config: ClientConfig, ca_cert: str):
    """
    运行客户端,支持自动重连
    
    参数:
        config: 客户端配置对象
        ca_cert: CA 证书路径
    """
    reconnect_delay = 2      # 重连尝试间隔 (秒)
    max_reconnect_delay = 30  # 最大重连延迟 (秒)
    current_delay = reconnect_delay
    socks_server = None       # 跟踪 SOCKS5 服务器实例

    while True:
        logger.info("创建新的隧道客户端实例")
        tunnel = TunnelClient(config, ca_cert)

        # 尝试连接
        logger.info("尝试连接到服务器")
        if not await tunnel.connect():
            logger.warning(f"连接失败,{current_delay}秒后重试...")
            await asyncio.sleep(current_delay)
            current_delay = min(current_delay * 2, max_reconnect_delay)
            continue

        # 连接成功 - 重置延迟
        current_delay = reconnect_delay

        # 在后台启动接收器
        logger.info("启动后台接收器任务")
        receiver_task = asyncio.create_task(tunnel._receiver_loop())

        # 启动 SOCKS 服务器
        logger.info(f"创建 SOCKS5 服务器: {config.socks_host}:{config.socks_port}")
        socks = SOCKS5Server(tunnel, config.socks_host, config.socks_port)

        try:
            # 关闭旧的服务器 (如果存在)
            if socks_server:
                logger.info("关闭旧的 SOCKS5 服务器")
                socks_server.close()
                await socks_server.wait_closed()

            # 创建 SOCKS 服务器但不阻塞
            socks_server = await asyncio.start_server(
                socks.handle_client,
                socks.host,
                socks.port,
                reuse_address=True  # 允许重启后快速重新绑定端口
            )
            addr = socks_server.sockets[0].getsockname()
            logger.info(f"SOCKS5 代理服务已启动: {addr[0]}:{addr[1]}")

            # 等待以下任一事件: 接收器结束 (连接丢失) 或键盘中断
            async with socks_server:
                try:
                    # 等待接收器完成 (意味着连接丢失)
                    logger.info("等待接收器任务完成...")
                    await receiver_task
                except asyncio.CancelledError:
                    logger.debug("接收器任务被取消")
                    pass

            # 连接丢失 - 立即重连
            if tunnel.connected:
                tunnel.connected = False

            logger.warning("连接丢失,正在重新连接...")
            current_delay = reconnect_delay  # 为下次失败重置延迟

        except KeyboardInterrupt:
            logger.info("正在关闭...")
            await tunnel.disconnect()
            # 关闭 SOCKS5 服务器
            if socks_server:
                logger.info("关闭 SOCKS5 服务器")
                socks_server.close()
                await socks_server.wait_closed()
            return 0
        except OSError as e:
            if "Address already in use" in str(e):
                logger.error(f"端口 {socks.port} 已被占用,等待中...")
                await asyncio.sleep(2)
            else:
                logger.error(f"SOCKS 服务器错误: {e}")
        finally:
            logger.info("清理资源")
            await tunnel.disconnect()
            
            # 取消并等待接收器任务
            if not receiver_task.done():
                receiver_task.cancel()
                try:
                    await asyncio.wait_for(receiver_task, timeout=5.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    logger.debug("接收器任务取消超时")

        # 连接丢失后不延迟 - 仅在连接失败时延迟 (在循环顶部处理)


def main():
    """
    主函数 - 解析命令行参数并启动客户端
    
    命令行参数:
        --config, -c: 配置文件路径 (默认: config.yaml)
        --server: 服务器域名 (TLS 需要 FQDN)
        --server-port: 服务器端口
        --socks-port, -p: SOCKS5 代理端口
        --username, -u: 认证用户名
        --secret, -s: 认证密钥
        --ca-cert: CA 证书路径
        --debug, -d: 启用调试模式
    """
    logger.info("启动 SMTP 隧道客户端")
    parser = argparse.ArgumentParser(description='SMTP 隧道客户端 (快速模式)')
    parser.add_argument('--config', '-c', default='config.yaml', help='配置文件路径')
    parser.add_argument('--server', default=None, help='服务器域名 (TLS 需要完全限定域名)')
    parser.add_argument('--server-port', type=int, default=None, help='服务器端口')
    parser.add_argument('--socks-port', '-p', type=int, default=None, help='SOCKS5 代理端口')
    parser.add_argument('--username', '-u', default=None, help='认证用户名')
    parser.add_argument('--secret', '-s', default=None, help='认证密钥')
    parser.add_argument('--ca-cert', default=None, help='CA 证书路径')
    parser.add_argument('--debug', '-d', action='store_true', help='启用调试模式')
    args = parser.parse_args()

    # 启用调试模式
    if args.debug:
        logger.info("启用调试模式")
        logging.getLogger().setLevel(logging.DEBUG)

    # 加载配置文件
    logger.info(f"加载配置文件: {args.config}")
    try:
        config_data = load_config(args.config)
        logger.info("配置文件加载成功")
    except FileNotFoundError:
        logger.warning(f"配置文件 {args.config} 未找到,使用默认配置")
        config_data = {}

    client_conf = config_data.get('client', {})

    # 创建客户端配置 - 命令行参数优先于配置文件
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

    # 验证必需配置
    if not config.username:
        logger.error("未配置用户名!")
        return 1

    if not config.secret:
        logger.error("未配置密钥!")
        return 1

    logger.info(f"客户端配置: 服务器={config.server_host}:{config.server_port}, "
                f"SOCKS5={config.socks_host}:{config.socks_port}, 用户名={config.username}")

    # 运行客户端
    try:
        logger.info("开始运行客户端")
        return asyncio.run(run_client(config, ca_cert))
    except KeyboardInterrupt:
        logger.info("收到键盘中断信号")
        return 0


if __name__ == '__main__':
    exit(main())
