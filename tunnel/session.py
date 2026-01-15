"""
隧道服务器模块

本模块定义了 TunnelSession 类，负责处理从客户端连接建立到关闭的完整生命周期，
包括 SMTP 握手、TLS 升级、用户认证、二进制模式切换以及多通道数据转发。
"""

import asyncio
import logging
import socket
import struct
from typing import Dict, Optional

from protocol import (
    FRAME_DATA,
    FRAME_CONNECT,
    FRAME_CONNECT_OK,
    FRAME_CONNECT_FAIL,
    FRAME_CLOSE,
    FRAME_HEADER_SIZE,
    make_frame,
    parse_frame_header
)
from connection import Channel, IPv4_FALLBACK_POOL

from .base import BaseTunnel

logger = logging.getLogger('smtp-tunnel-server')


class TunnelSession(BaseTunnel):
    """
    隧道会话类 - 处理单个客户端的 SMTP 隧道连接
    
    TunnelSession 负责处理从客户端连接建立到关闭的完整生命周期，
    包括 SMTP 握手、TLS 升级、用户认证、二进制模式切换以及
    多通道数据转发。
    
    工作流程:
    1. 接受客户端连接
    2. 执行 SMTP 握手（模拟真实 SMTP 服务器）
    3. 升级到 TLS 加密连接
    4. 执行用户认证（多用户支持）
    5. 切换到二进制模式
    6. 处理多通道数据转发
    7. 清理资源并关闭连接
    
    安全特性:
    - TLS 加密通信
    - 多用户认证（每个用户独立密钥）
    - IP 白名单验证
    - 可选的日志记录（每用户配置）
    
    Attributes:
        config: 服务器配置对象
        ssl_context: ssl.SSLContext，SSL/TLS 上下文
        users: 用户配置字典
        authenticated: bool，认证状态标志
        binary_mode: bool，二进制模式标志
        username: Optional[str]，已认证的用户名
        user_config: 已认证用户的配置
        client_ip: str，客户端 IP 地址
        peer_str: str，客户端地址字符串（IP:端口）
        connect_stats: dict，连接统计信息
    """
    
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        config,
        ssl_context,
        users
    ):
        """
        初始化隧道会话
        
        Args:
            reader: asyncio.StreamReader，用于从客户端读取数据
            writer: asyncio.StreamWriter，用于向客户端写入数据
            config: ServerConfig，服务器配置对象，包含主机名等配置
            ssl_context: ssl.SSLContext，SSL/TLS 上下文，用于升级连接到 TLS
            users: Dict[str, UserConfig]，用户配置字典，键为用户名，值为用户配置
        """
        super().__init__(reader, writer)
        
        self.config = config
        self.ssl_context = ssl_context
        self.users = users
        self.authenticated = False
        self.binary_mode = False
        
        # 用户信息（认证后设置）
        self.username: Optional[str] = None
        self.user_config = None
        
        # 从连接中提取客户端地址信息
        peer = writer.get_extra_info('peername')
        self.client_ip = peer[0] if peer else "unknown"
        self.peer_str = f"{peer[0]}:{peer[1]}" if peer else "unknown"
        
        # 连接统计信息
        self.connect_stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'by_strategy': {}
        }
        
        logger.debug(f"初始化隧道会话: peer={self.peer_str}, client_ip={self.client_ip}")
    
    def _log(self, level: int, msg: str):
        """
        记录日志消息，可选包含用户信息
        
        此方法根据用户配置决定是否记录日志。如果用户配置中禁用了日志记录，
        则此方法会直接返回而不记录任何内容。否则，会根据是否已认证用户
        来决定日志消息的格式。
        
        Args:
            level: 日志级别，使用 logging 模块常量（如 logging.INFO、logging.ERROR）
            msg: 日志消息内容
        """
        if self.user_config and not self.user_config.logging:
            return
        
        if self.username:
            logger.log(level, f"[{self.username}] {msg}")
        else:
            logger.log(level, msg)
    
    async def run(self):
        """
        主会话处理器 - 处理完整的客户端连接生命周期
        
        此方法是隧道会话的入口点，负责协调整个连接处理流程。
        它按顺序执行以下阶段：
        1. SMTP 握手阶段 - 模拟真实 SMTP 服务器行为以欺骗 DPI
        2. TLS 升级阶段 - 建立加密连接
        3. 用户认证阶段 - 验证客户端身份（多用户支持）
        4. 二进制模式阶段 - 处理多通道数据转发
        
        Returns:
            None（此方法不返回值）
        """
        logger.info(f"来自 {self.peer_str} 的连接")
        
        try:
            # 阶段 1: SMTP 握手
            if not await self.smtp_handshake():
                return
            
            # 阶段 2: TLS 升级后
            self._log(logging.INFO, f"已认证，进入二进制模式: {self.peer_str}")
            
            # 阶段 3: 二进制流模式
            await self.binary_mode_loop()
            
        except asyncio.CancelledError:
            logger.debug(f"会话被取消: {self.peer_str}")
        except Exception as e:
            self._log(logging.ERROR, f"会话错误: {e}")
        finally:
            await self.cleanup()
            self._log(logging.INFO, f"会话结束: {self.peer_str}")
    
    async def smtp_handshake(self) -> bool:
        """
        执行 SMTP 握手 - 模拟真实 SMTP 服务器行为以欺骗 DPI
        
        此方法执行完整的 SMTP 握手流程，包括 EHLO、STARTTLS、AUTH 等步骤。
        这个过程是为了让深度包检测（DPI）系统认为这是一个正常的 SMTP 连接，
        从而避免被识别为隧道流量。
        
        Returns:
            bool: True 表示握手成功，False 表示握手失败
        """
        logger.debug(f"开始 SMTP 握手: peer={self.peer_str}")
        
        try:
            # 发送问候 - 模拟 Postfix SMTP 服务器
            logger.debug(f"发送 220 问候: {self.config.hostname}")
            await self.send_smtp_line(f"220 {self.config.hostname} ESMTP Postfix (Ubuntu)")
            
            # 等待 EHLO - 客户端发送扩展 Hello
            logger.debug("等待 EHLO 命令...")
            line = await self.read_smtp_line()
            if not line or not line.upper().startswith(('EHLO', 'HELO')):
                logger.warning(f"未收到 EHLO/HELO 命令: {line}")
                return False
            logger.debug(f"收到 EHLO/HELO 命令: {line}")
            
            # 发送能力列表 - 声明支持 STARTTLS 和 AUTH
            logger.debug(f"发送 250 能力列表: {self.config.hostname}")
            await self.send_smtp_line(f"250-{self.config.hostname}")
            await self.send_smtp_line("250-STARTTLS")
            await self.send_smtp_line("250-AUTH PLAIN LOGIN")
            await self.send_smtp_line("250 8BITMIME")
            
            # 等待 STARTTLS - 客户端请求 TLS 升级
            logger.debug("等待 STARTTLS 命令...")
            line = await self.read_smtp_line()
            if not line or line.upper() != 'STARTTLS':
                logger.warning(f"未收到 STARTTLS 命令: {line}")
                return False
            logger.debug(f"收到 STARTTLS 命令: {line}")
            
            # 发送 220 响应 - 准备开始 TLS
            logger.debug(f"发送 220 响应: Ready to start TLS")
            await self.send_smtp_line("220 2.0.0 Ready to start TLS")
            
            # 升级到 TLS - 建立加密连接
            logger.debug(f"升级到 TLS 连接: peer={self.peer_str}")
            await self.upgrade_tls(self.ssl_context, server_side=True)
            logger.debug(f"TLS 已建立: peer={self.peer_str}")
            
            # 等待 EHLO - TLS 加密后的第二个 Hello
            logger.debug("等待 TLS 加密后的 EHLO 命令...")
            line = await self.read_smtp_line()
            if not line or not line.upper().startswith(('EHLO', 'HELO')):
                logger.warning(f"未收到 TLS 加密后的 EHLO/HELO 命令: {line}")
                return False
            logger.debug(f"收到 TLS 加密后的 EHLO/HELO 命令: {line}")
            
            # 发送能力列表 - 加密后的能力声明
            logger.debug(f"发送 250 能力列表: {self.config.hostname}")
            await self.send_smtp_line(f"250-{self.config.hostname}")
            await self.send_smtp_line("250-AUTH PLAIN LOGIN")
            await self.send_smtp_line("250 8BITMIME")
            
            # 等待 AUTH - 客户端发送认证令牌
            logger.debug("等待 AUTH 命令...")
            line = await self.read_smtp_line()
            if not line or not line.upper().startswith('AUTH'):
                logger.warning(f"未收到 AUTH 命令: {line}")
                return False
            logger.debug(f"收到 AUTH 命令: {line}")
            
            # 解析认证令牌 - 格式: AUTH PLAIN <base64_token>
            parts = line.split(' ', 2)
            if len(parts) < 3:
                logger.warning(f"AUTH 命令格式错误: {line}")
                await self.send_smtp_line("535 5.7.8 Authentication failed")
                return False
            
            token = parts[2]
            logger.debug(f"解析认证令牌: {token}")
            
            # 多用户认证 - 验证令牌并获取用户名
            from tunnel.crypto import TunnelCrypto
            valid, username = TunnelCrypto.verify_auth_token_multi_user(token, self.users)
            
            if not valid or not username:
                logger.warning(f"来自 {self.peer_str} 的认证失败")
                await self.send_smtp_line("535 5.7.8 Authentication failed")
                return False
            
            logger.info(f"认证成功: username={username}, peer={self.peer_str}")
            
            # 获取用户配置
            self.username = username
            self.user_config = self.users.get(username)
            
            # 检查每用户 IP 白名单
            if self.user_config and self.user_config.whitelist:
                from common import IPWhitelist
                user_whitelist = IPWhitelist(self.user_config.whitelist)
                if not user_whitelist.is_allowed(self.client_ip):
                    logger.warning(f"用户 {username} 不允许从 IP {self.client_ip} 连接")
                    await self.send_smtp_line("535 5.7.8 Authentication failed")
                    return False
                logger.debug(f"IP 白名单检查通过: {self.client_ip}")
            
            # 发送认证成功响应
            logger.debug(f"发送 235 认证成功响应: {username}")
            await self.send_smtp_line("235 2.7.0 Authentication successful")
            self.authenticated = True
            
            # 等待 BINARY - 客户端请求切换到二进制模式
            logger.debug("等待 BINARY 命令...")
            line = await self.read_smtp_line()
            if line != "BINARY":
                logger.warning(f"未收到 BINARY 命令: {line}")
                return False
            logger.debug(f"收到 BINARY 命令: {line}")
            
            # 发送 299 响应 - 激活二进制模式
            logger.debug(f"发送 299 二进制模式激活响应")
            await self.send_smtp_line("299 Binary mode activated")
            self.binary_mode = True
            
            logger.info(f"SMTP 握手成功: peer={self.peer_str}, username={username}")
            return True
            
        except Exception as e:
            logger.error(f"握手错误: {e}")
            return False
    
    async def process_frame(self, frame_type: int, channel_id: int, payload: bytes):
        """
        处理二进制帧 - 根据帧类型分发到相应的处理方法
        
        此方法根据帧类型将帧分发到相应的处理方法。
        支持的帧类型包括：
        - FRAME_CONNECT: 连接请求，建立到目标主机的连接
        - FRAME_DATA: 数据帧，转发数据到目标主机
        - FRAME_CLOSE: 关闭帧，关闭指定的通道
        
        Args:
            frame_type: 帧类型，取值为 FRAME_CONNECT、FRAME_DATA 或 FRAME_CLOSE
            channel_id: 通道ID，用于标识不同的隧道连接
            payload: 帧负载数据，内容取决于帧类型
        """
        if frame_type == FRAME_CONNECT:
            logger.debug(f"处理 CONNECT 帧: channel_id={channel_id}")
            await self._handle_connect(channel_id, payload)
        elif frame_type == FRAME_DATA:
            channel = self.channels.get(channel_id)
            if channel:
                logger.debug(f"处理 DATA 帧: channel_id={channel_id}, payload_len={len(payload)}")
            await self._handle_data(channel_id, payload)
        elif frame_type == FRAME_CLOSE:
            logger.debug(f"处理 CLOSE 帧: channel_id={channel_id}")
            await self._handle_close(channel_id)
    
    async def _handle_connect(self, channel_id: int, payload: bytes):
        """
        处理 CONNECT 请求 - 建立到目标主机的连接
        
        此方法处理客户端发送的 CONNECT 帧，建立到目标主机的 TCP 连接。
        支持多种连接策略，包括 IPv6、IPv4、自动地址族选择和回退机制。
        
        Args:
            channel_id: 通道ID，用于标识这个连接
            payload: 连接请求数据，包含主机名和端口
        """
        logger.debug(f"处理 CONNECT 请求: channel_id={channel_id}, payload_len={len(payload)}")
        
        try:
            # 解析负载: host_len(1) + host + port(2)
            host_len = payload[0]
            host = payload[1:1+host_len].decode('utf-8')
            port = struct.unpack('>H', payload[1+host_len:3+host_len])[0]
            
            logger.debug(f"解析连接请求: host={host}, port={port}")
            
            # 处理IPv6地址格式
            is_ipv6 = ':' in host and '.' not in host
            original_host = host
            
            # 修复IPv6地址格式错误
            if is_ipv6:
                while ':::' in host:
                    host = host.replace(':::', '::')
                
                if host.count('::') > 1:
                    first_double_colon = host.find('::')
                    host = host[:first_double_colon+2] + host[first_double_colon+2:].replace('::', ':')
            
            target_address = f"[{host}]:{port}" if is_ipv6 else f"{host}:{port}"
            logger.info(f"CONNECT ch={channel_id} -> {target_address} (host: {host}, is_ipv6: {is_ipv6})")
            
            # 获取IPv4地址列表
            def get_ipv4_addresses(hostname):
                ipv4_addresses = []
                try:
                    addr_info = socket.getaddrinfo(hostname, port, socket.AF_INET, socket.SOCK_STREAM)
                    for info in addr_info:
                        ipv4_address = info[4][0]
                        if ipv4_address not in ipv4_addresses:
                            ipv4_addresses.append(ipv4_address)
                except Exception as e:
                    logger.debug(f"获取IPv4地址失败: {e}")
                    return ipv4_addresses
            
            # 检查服务器是否支持IPv6连接
            def is_ipv6_supported():
                try:
                    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                    sock.close()
                    return True
                except OSError as e:
                    logger.debug(f"IPv6支持测试失败: {e}")
                    return False
            
            ipv6_supported = is_ipv6_supported()
            ipv4_addresses = get_ipv4_addresses(original_host)
            
            # 构建连接策略列表
            connection_strategies = []
            
            if is_ipv6 and ipv6_supported:
                connection_strategies.append(("IPv6", socket.AF_INET6, host))
            
            if not is_ipv6:
                connection_strategies.append(("自动选择", None, host))
            
            for ipv4_addr in ipv4_addresses:
                connection_strategies.append((f"IPv4 ({ipv4_addr})", socket.AF_INET, ipv4_addr))
            
            if is_ipv6 and not ipv4_addresses:
                for service_name, ipv4_list in IPv4_FALLBACK_POOL.items():
                    for ipv4_addr in ipv4_list:
                        connection_strategies.append((f"IPv4地址池 ({service_name})", socket.AF_INET, ipv4_addr))
            
            if not is_ipv6:
                connection_strategies.append(("Google DNS解析", None, host))
            
            # 执行连接策略
            for strategy in connection_strategies:
                strategy_name = strategy[0]
                family = strategy[1]
                target_host = strategy[2]
                
                try:
                    connect_kwargs = {}
                    if family is not None:
                        connect_kwargs['family'] = family
                    
                    logger.debug(f"尝试连接策略: {strategy_name}, target={target_host}")
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target_host, port, **connect_kwargs),
                        timeout=10.0
                    )
                    
                    # 创建通道对象
                    channel = Channel(
                        channel_id=channel_id,
                        host=original_host,
                        port=port,
                        reader=reader,
                        writer=writer,
                        connected=True
                    )
                    self.channels[channel_id] = channel
                    
                    # 开始从目标读取数据
                    channel.reader_task = asyncio.create_task(self._channel_reader(channel))
                    
                    # 发送连接成功帧
                    await self.send_frame(FRAME_CONNECT_OK, channel_id)
                    logger.info(f"CONNECTED ch={channel_id} (策略: {strategy_name})")
                    
                    # 更新连接统计
                    self.connect_stats['total'] += 1
                    self.connect_stats['success'] += 1
                    if strategy_name not in self.connect_stats['by_strategy']:
                        self.connect_stats['by_strategy'][strategy_name] = {'success': 0, 'failed': 0}
                    self.connect_stats['by_strategy'][strategy_name]['success'] += 1
                    
                    return
                    
                except Exception as e:
                    logger.debug(f"连接策略失败: {strategy_name}, host: {target_host}, 错误: {e}")
                    continue
            
            # 所有策略都失败
            await self.send_frame(FRAME_CONNECT_FAIL, channel_id)
            logger.info(f"CONNECT_FAILED ch={channel_id}")
            
            self.connect_stats['total'] += 1
            self.connect_stats['failed'] += 1
            
        except Exception as e:
            logger.error(f"处理CONNECT请求错误: {e}")
            await self.send_frame(FRAME_CONNECT_FAIL, channel_id)
    
    async def _handle_data(self, channel_id: int, payload: bytes):
        """
        处理 DATA 帧 - 转发数据到目标主机
        
        此方法处理客户端发送的 DATA 帧，将数据转发到目标主机。
        
        Args:
            channel_id: 通道ID，标识目标通道
            payload: 要转发的数据
        """
        channel = self.channels.get(channel_id)
        if not channel or not channel.connected:
            logger.debug(f"通道 {channel_id} 不存在或未连接，跳过数据转发")
            return
        
        try:
            logger.debug(f"转发数据到通道 {channel_id}: {len(payload)} 字节")
            channel.writer.write(payload)
            await channel.writer.drain()
            logger.debug(f"数据转发成功: channel_id={channel_id}, bytes={len(payload)}")
        except Exception as e:
            logger.error(f"转发数据错误: channel_id={channel_id}, error={e}")
            await self._handle_close(channel_id)
    
    async def _handle_close(self, channel_id: int):
        """
        处理 CLOSE 帧 - 关闭指定的通道
        
        此方法处理客户端发送的 CLOSE 帧，关闭指定的通道。
        
        Args:
            channel_id: 通道ID，标识要关闭的通道
        """
        logger.debug(f"处理 CLOSE 帧: channel_id={channel_id}")
        channel = self.channels.get(channel_id)
        if channel:
            await self.close_channel(channel)
    
    async def _channel_reader(self, channel: Channel):
        """
        通道读取器 - 从目标主机读取数据并发送给客户端
        
        此方法在后台运行，持续从目标主机读取数据，并通过隧道发送给客户端。
        
        Args:
            channel: Channel 对象，要读取的通道
        """
        logger.debug(f"启动通道读取器: channel_id={channel.channel_id}")
        
        try:
            while channel.connected:
                data = await asyncio.wait_for(
                    channel.reader.read(32768),
                    timeout=300.0
                )
                if not data:
                    logger.debug(f"通道 {channel.channel_id} 连接已关闭（读取到空数据）")
                    break
                
                await self.send_frame(FRAME_DATA, channel.channel_id, data)
                logger.debug(f"从通道 {channel.channel_id} 转发数据: {len(data)} 字节")
                
        except asyncio.TimeoutError:
            logger.debug(f"通道 {channel.channel_id} 读取超时（300秒）")
        except Exception as e:
            logger.debug(f"通道读取器错误: channel_id={channel.channel_id}, error={e}")
        finally:
            if channel.connected:
                await self.send_frame(FRAME_CLOSE, channel.channel_id)
                await self.close_channel(channel)
                logger.debug(f"通道 {channel.channel_id} 读取器已停止")
    
    async def close_channel(self, channel: Channel):
        """
        关闭通道并清理资源
        
        此方法关闭指定的通道，清理所有相关资源。
        
        Args:
            channel: Channel 对象，要关闭的通道
        """
        if not channel.connected:
            return
        channel.connected = False
        
        # 取消读取任务
        if hasattr(channel, 'reader_task') and channel.reader_task:
            channel.reader_task.cancel()
            try:
                await channel.reader_task
            except asyncio.CancelledError:
                pass
        
        if channel.writer:
            try:
                channel.writer.close()
                await channel.writer.wait_closed()
            except:
                pass
        
        self.channels.pop(channel.channel_id, None)
    
    async def cleanup(self):
        """
        清理会话资源
        
        此方法清理会话的所有资源，包括关闭所有通道、关闭客户端连接、输出统计信息。
        """
        for channel in list(self.channels.values()):
            await self.close_channel(channel)
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except:
            pass
        
        # 输出连接统计信息
        if self.connect_stats['total'] > 0:
            success_rate = (self.connect_stats['success'] / self.connect_stats['total']) * 100
            logger.info(f"连接统计: 总数={self.connect_stats['total']}, 成功={self.connect_stats['success']}, 失败={self.connect_stats['failed']}, 成功率={success_rate:.2f}%")
            
            for strategy_name, stats in self.connect_stats['by_strategy'].items():
                strategy_total = stats['success'] + stats['failed']
                if strategy_total > 0:
                    strategy_success_rate = (stats['success'] / strategy_total) * 100
                    logger.info(f"策略 {strategy_name}: 成功={stats['success']}, 失败={stats['failed']}, 成功率={strategy_success_rate:.2f}%")