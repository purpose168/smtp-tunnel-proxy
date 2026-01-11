#!/usr/bin/env python3
"""
SMTP 隧道服务器 - 快速二进制模式

版本: 1.3.0

协议:
1. SMTP 握手 (EHLO, STARTTLS, AUTH) - 看起来像真实的 SMTP
2. AUTH 成功后，切换到二进制流模式
3. 全双工二进制协议 - 不再有 SMTP 开销

特性:
- 支持多用户，每个用户有独立的密钥
- 每用户 IP 白名单
- 每用户日志记录（可选）
"""

import asyncio
import ssl
import logging
import argparse
import struct
import os
import socket
from typing import Dict, Optional
from dataclasses import dataclass

from common import (
    TunnelCrypto, load_config, load_users, ServerConfig, UserConfig, IPWhitelist
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('smtp-tunnel-server')


# ============================================================================
# 二进制协议（SMTP 握手后使用）
# ============================================================================

# 帧类型
FRAME_DATA = 0x01
FRAME_CONNECT = 0x02
FRAME_CONNECT_OK = 0x03
FRAME_CONNECT_FAIL = 0x04
FRAME_CLOSE = 0x05

def make_frame(frame_type: int, channel_id: int, payload: bytes = b'') -> bytes:
    """创建二进制帧: 类型(1) + 通道(2) + 长度(2) + 负载"""
    return struct.pack('>BHH', frame_type, channel_id, len(payload)) + payload

def parse_frame_header(data: bytes):
    """解析帧头，返回 (类型, 通道ID, 负载长度) 或 None"""
    if len(data) < 5:
        return None
    frame_type, channel_id, payload_len = struct.unpack('>BHH', data[:5])
    return frame_type, channel_id, payload_len

FRAME_HEADER_SIZE = 5


# ============================================================================
# 通道 - 隧道化的 TCP 连接
# ============================================================================

# IPv4 地址池 - 用于纯 IPv6 地址的回退
# 这些是常用服务的 IPv4 地址，当 IPv6 连接失败时使用
IPv4_FALLBACK_POOL = {
    # Google 服务
    'google.com': ['142.250.72.174', '142.250.72.175', '142.250.72.176'],
    'www.google.com': ['142.250.72.174', '142.250.72.175'],
    # Cloudflare 服务
    'cloudflare.com': ['104.16.132.229', '104.16.133.229'],
    'www.cloudflare.com': ['104.16.132.229', '104.16.133.229'],
    # Facebook 服务
    'facebook.com': ['157.240.22.35', '157.240.22.19'],
    'www.facebook.com': ['157.240.22.35', '157.240.22.19'],
    # Apple 服务
    'apple.com': ['17.253.144.10', '17.253.144.11'],
    'www.apple.com': ['17.253.144.10', '17.253.144.11'],
}

@dataclass
class Channel:
    channel_id: int
    host: str
    port: int
    reader: Optional[asyncio.StreamReader] = None
    writer: Optional[asyncio.StreamWriter] = None
    connected: bool = False
    reader_task: Optional[asyncio.Task] = None  # 添加任务引用


# ============================================================================
# 隧道会话
# ============================================================================

class TunnelSession:
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        config: ServerConfig,
        ssl_context: ssl.SSLContext,
        users: Dict[str, UserConfig]
    ):
        self.reader = reader
        self.writer = writer
        self.config = config
        self.ssl_context = ssl_context
        self.users = users
        self.authenticated = False
        self.binary_mode = False
        self.channels: Dict[int, Channel] = {}
        self.write_lock = asyncio.Lock()

        # 用户信息（认证后设置）
        self.username: Optional[str] = None
        self.user_config: Optional[UserConfig] = None

        peer = writer.get_extra_info('peername')
        self.client_ip = peer[0] if peer else "unknown"
        self.peer_str = f"{peer[0]}:{peer[1]}" if peer else "unknown"

        # 连接统计
        self.connect_stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'by_strategy': {}
        }

    def _log(self, level: int, msg: str):
        """记录日志消息，可选包含用户信息。"""
        if self.user_config and not self.user_config.logging:
            return  # 此用户已禁用日志记录

        if self.username:
            logger.log(level, f"[{self.username}] {msg}")
        else:
            logger.log(level, msg)

    async def run(self):
        """主会话处理器。"""
        logger.info(f"来自 {self.peer_str} 的连接")

        try:
            # 阶段 1: SMTP 握手
            if not await self._smtp_handshake():
                return

            self._log(logging.INFO, f"已认证，进入二进制模式: {self.peer_str}")

            # 阶段 2: 二进制流模式
            await self._binary_mode()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._log(logging.ERROR, f"会话错误: {e}")
        finally:
            await self._cleanup()
            self._log(logging.INFO, f"会话结束: {self.peer_str}")

    async def _smtp_handshake(self) -> bool:
        """执行 SMTP 握手 - 这是 DPI 看到的内容。"""
        try:
            # 发送问候
            await self._send_line(f"220 {self.config.hostname} ESMTP Postfix (Ubuntu)")

            # 等待 EHLO
            line = await self._read_line()
            if not line or not line.upper().startswith(('EHLO', 'HELO')):
                return False

            # 发送能力
            await self._send_line(f"250-{self.config.hostname}")
            await self._send_line("250-STARTTLS")
            await self._send_line("250-AUTH PLAIN LOGIN")
            await self._send_line("250 8BITMIME")

            # 等待 STARTTLS
            line = await self._read_line()
            if not line or line.upper() != 'STARTTLS':
                return False

            await self._send_line("220 2.0.0 Ready to start TLS")

            # 升级到 TLS
            await self._upgrade_tls()

            # 再次等待 EHLO
            line = await self._read_line()
            if not line or not line.upper().startswith(('EHLO', 'HELO')):
                return False

            await self._send_line(f"250-{self.config.hostname}")
            await self._send_line("250-AUTH PLAIN LOGIN")
            await self._send_line("250 8BITMIME")

            # 等待 AUTH
            line = await self._read_line()
            if not line or not line.upper().startswith('AUTH'):
                return False

            parts = line.split(' ', 2)
            if len(parts) < 3:
                await self._send_line("535 5.7.8 Authentication failed")
                return False

            token = parts[2]

            # 多用户认证
            valid, username = TunnelCrypto.verify_auth_token_multi_user(token, self.users)

            if not valid or not username:
                logger.warning(f"来自 {self.peer_str} 的认证失败")
                await self._send_line("535 5.7.8 Authentication failed")
                return False

            # 获取用户配置
            self.username = username
            self.user_config = self.users.get(username)

            # 检查每用户 IP 白名单
            if self.user_config and self.user_config.whitelist:
                user_whitelist = IPWhitelist(self.user_config.whitelist)
                if not user_whitelist.is_allowed(self.client_ip):
                    logger.warning(f"用户 {username} 不允许从 IP {self.client_ip} 连接")
                    await self._send_line("535 5.7.8 Authentication failed")
                    return False

            await self._send_line("235 2.7.0 Authentication successful")
            self.authenticated = True

            # 信号二进制模式 - 客户端发送特殊标记
            line = await self._read_line()
            if line == "BINARY":
                await self._send_line("299 Binary mode activated")
                self.binary_mode = True
                return True

            return False

        except Exception as e:
            logger.error(f"握手错误: {e}")
            return False

    async def _upgrade_tls(self):
        """升级连接到 TLS。"""
        transport = self.writer.transport
        protocol = self.writer._protocol
        loop = asyncio.get_event_loop()

        new_transport = await loop.start_tls(
            transport, protocol, self.ssl_context, server_side=True
        )

        self.writer._transport = new_transport
        self.reader._transport = new_transport
        logger.debug(f"TLS 已建立: {self.peer_str}")

    async def _send_line(self, line: str):
        """发送 SMTP 行。"""
        self.writer.write(f"{line}\r\n".encode())
        await self.writer.drain()

    async def _read_line(self) -> Optional[str]:
        """读取 SMTP 行。"""
        try:
            data = await asyncio.wait_for(self.reader.readline(), timeout=60.0)
            if not data:
                return None
            return data.decode('utf-8', errors='replace').strip()
        except:
            return None

    async def _binary_mode(self):
        """处理二进制流模式 - 这是快速模式。"""
        buffer = b''

        while True:
            # 读取数据
            try:
                chunk = await asyncio.wait_for(self.reader.read(65536), timeout=60.0)
                if not chunk:
                    self._log(logging.DEBUG, "客户端关闭连接")
                    break
                buffer += chunk
            except asyncio.TimeoutError:
                # 检查连接是否仍然存活
                if self.writer.is_closing():
                    break
                continue
            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                self._log(logging.DEBUG, f"连接错误: {e}")
                break

            # 处理完整的帧
            while len(buffer) >= FRAME_HEADER_SIZE:
                header = parse_frame_header(buffer)
                if not header:
                    break

                frame_type, channel_id, payload_len = header
                total_len = FRAME_HEADER_SIZE + payload_len

                if len(buffer) < total_len:
                    break

                payload = buffer[FRAME_HEADER_SIZE:total_len]
                buffer = buffer[total_len:]

                await self._handle_frame(frame_type, channel_id, payload)

    async def _handle_frame(self, frame_type: int, channel_id: int, payload: bytes):
        """处理二进制帧。"""
        if frame_type == FRAME_CONNECT:
            await self._handle_connect(channel_id, payload)
        elif frame_type == FRAME_DATA:
            await self._handle_data(channel_id, payload)
        elif frame_type == FRAME_CLOSE:
            await self._handle_close(channel_id)

    async def _handle_connect(self, channel_id: int, payload: bytes):
        """处理 CONNECT 请求。"""
        try:
            # 解析: host_len(1) + host + port(2)
            host_len = payload[0]
            host = payload[1:1+host_len].decode('utf-8')
            port = struct.unpack('>H', payload[1+host_len:3+host_len])[0]

            # 处理IPv6地址格式
            is_ipv6 = ':' in host and '.' not in host
            original_host = host  # 保存原始主机名/地址
            
            # 修复IPv6地址格式错误
            if is_ipv6:
                logger.debug(f"原始IPv6地址: {host}")
                
                # 1. 确保正确的IPv6格式，将多个连续冒号替换为双冒号
                while ':::' in host:
                    host = host.replace(':::', '::')
                
                # 2. 确保双冒号只出现一次
                if host.count('::') > 1:
                    # 对于多个双冒号的情况，只保留第一个双冒号
                    # 查找第一个双冒号的位置
                    first_double_colon = host.find('::')
                    # 移除第一个双冒号之后的所有双冒号
                    host = host[:first_double_colon+2] + host[first_double_colon+2:].replace('::', ':')
                
                logger.debug(f"处理后IPv6地址: {host}")
                
                target_address = f"[{host}]:{port}"
            else:
                target_address = f"{host}:{port}"
            
            logger.info(f"CONNECT ch={channel_id} -> {target_address} (host: {host}, is_ipv6: {is_ipv6})")

            # 尝试解析主机的IPv4地址
            def get_ipv4_addresses(hostname):
                """获取主机的IPv4地址列表"""
                import socket
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
            
            # 首先检查服务器是否支持IPv6连接
            def is_ipv6_supported():
                """检查服务器是否支持IPv6连接"""
                try:
                    import socket
                    # 尝试创建IPv6套接字，这是测试IPv6支持的最基本方法
                    # 不需要绑定到特定地址，创建套接字本身就可以测试IPv6堆栈是否可用
                    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                    sock.close()
                    return True
                except OSError as e:
                    logger.debug(f"IPv6支持测试失败: {e}")
                    return False
            
            ipv6_supported = is_ipv6_supported()
            logger.debug(f"服务器IPv6支持状态: {ipv6_supported}")
            
            # 获取原始主机的IPv4地址列表
            ipv4_addresses = get_ipv4_addresses(original_host)
            logger.debug(f"原始主机的IPv4地址列表: {ipv4_addresses}")
            
            # 构建连接策略
            connection_strategies = []
            
            # 策略1: 如果是IPv6地址且服务器支持IPv6，尝试IPv6连接
            if is_ipv6 and ipv6_supported:
                connection_strategies.append(("IPv6", socket.AF_INET6, host))
            
            # 策略2: 如果是域名，尝试自动地址族选择
            if not is_ipv6:
                connection_strategies.append(("自动选择", None, host))
            
            # 策略3: 对于所有情况，尝试使用解析到的IPv4地址连接
            for ipv4_addr in ipv4_addresses:
                connection_strategies.append((f"IPv4 ({ipv4_addr})", socket.AF_INET, ipv4_addr))
            
            # 策略4: 对于纯IPv6地址，尝试使用IPv4地址池回退
            if is_ipv6 and not ipv4_addresses:
                # 尝试从IPv6地址推断可能的服务
                for service_name, ipv4_list in IPv4_FALLBACK_POOL.items():
                    for ipv4_addr in ipv4_list:
                        connection_strategies.append((f"IPv4地址池 ({service_name})", socket.AF_INET, ipv4_addr))
            
            # 策略5: 如果是域名，尝试使用Google公共DNS服务器解析
            if not is_ipv6:
                connection_strategies.append(("Google DNS解析", None, host))
            
            # 执行连接策略
            for strategy in connection_strategies:
                strategy_name = strategy[0]
                family = strategy[1]
                target_host = strategy[2]
                
                logger.debug(f"尝试连接策略: {strategy_name}, host: {target_host}, family: {family}")
                
                try:
                    connect_kwargs = {}
                    if family is not None:
                        connect_kwargs['family'] = family
                    
                    # 如果是Google DNS解析策略，我们不需要设置local_addr，让系统自动选择
                    # 注意：local_addr应该是本地地址，而不是外部DNS服务器地址
                    
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target_host, port, **connect_kwargs),
                        timeout=10.0
                    )
                    
                    logger.debug(f"连接策略成功: {strategy_name}, host: {target_host}")
                    
                    channel = Channel(
                        channel_id=channel_id,
                        host=original_host,
                        port=port,
                        reader=reader,
                        writer=writer,
                        connected=True
                    )
                    self.channels[channel_id] = channel
                    
                    # 开始从目标读取
                    channel.reader_task = asyncio.create_task(self._channel_reader(channel))
                    
                    # 发送成功
                    await self._send_frame(FRAME_CONNECT_OK, channel_id)
                    logger.info(f"CONNECTED ch={channel_id} (策略: {strategy_name})")
                    
                    # 更新连接统计
                    self.connect_stats['total'] += 1
                    self.connect_stats['success'] += 1
                    if strategy_name not in self.connect_stats['by_strategy']:
                        self.connect_stats['by_strategy'][strategy_name] = {'success': 0, 'failed': 0}
                    self.connect_stats['by_strategy'][strategy_name]['success'] += 1
                    
                    return
                    
                except ConnectionRefusedError as e:
                    logger.error(f"连接被拒绝: {strategy_name}, host: {target_host}, 错误: {e}")
                    continue
                except TimeoutError as e:
                    logger.error(f"连接超时: {strategy_name}, host: {target_host}, 错误: {e}")
                    continue
                except OSError as e:
                    if e.errno == 101:  # Network is unreachable
                        logger.error(f"网络不可达: {strategy_name}, host: {target_host}, 错误: {e}")
                        continue
                    elif e.errno == -9:  # Address family not supported
                        logger.error(f"地址族不支持: {strategy_name}, host: {target_host}, 错误: {e}")
                        continue
                    else:
                        logger.error(f"连接错误: {strategy_name}, host: {target_host}, 错误: {e}")
                        continue
                except Exception as e:
                    logger.error(f"未知错误: {strategy_name}, host: {target_host}, 错误: {e}")
                    import traceback
                    logger.debug(f"错误详情: {traceback.format_exc()}")
                    continue
            
            # 如果所有策略都失败，发送连接失败
            logger.error(f"所有连接策略均失败: {original_host}:{port}")
            await self._send_frame(FRAME_CONNECT_FAIL, channel_id, b"Network is unreachable")
            
            # 更新连接统计
            self.connect_stats['total'] += 1
            self.connect_stats['failed'] += 1
            for strategy_name in [s[0] for s in connection_strategies]:
                if strategy_name not in self.connect_stats['by_strategy']:
                    self.connect_stats['by_strategy'][strategy_name] = {'success': 0, 'failed': 0}
                self.connect_stats['by_strategy'][strategy_name]['failed'] += 1

        except Exception as e:
            logger.error(f"处理连接错误: {e}")
            await self._send_frame(FRAME_CONNECT_FAIL, channel_id)

    async def _handle_data(self, channel_id: int, payload: bytes):
        """转发数据到目标。"""
        channel = self.channels.get(channel_id)
        if channel and channel.connected and channel.writer:
            try:
                channel.writer.write(payload)
                await channel.writer.drain()
            except:
                await self._close_channel(channel)

    async def _handle_close(self, channel_id: int):
        """关闭通道。"""
        channel = self.channels.get(channel_id)
        if channel:
            await self._close_channel(channel)

    async def _channel_reader(self, channel: Channel):
        """从目标读取并发送到客户端。"""
        try:
            while channel.connected:
                data = await asyncio.wait_for(
                    channel.reader.read(32768),
                    timeout=300.0
                )
                if not data:
                    break

                await self._send_frame(FRAME_DATA, channel.channel_id, data)

        except asyncio.TimeoutError:
            pass
        except Exception as e:
            logger.debug(f"通道读取器错误: {e}")
        finally:
            if channel.connected:
                await self._send_frame(FRAME_CLOSE, channel.channel_id)
                await self._close_channel(channel)

    async def _send_frame(self, frame_type: int, channel_id: int, payload: bytes = b''):
        """发送二进制帧到客户端。"""
        if self.writer.is_closing():
            return
        try:
            async with self.write_lock:
                frame = make_frame(frame_type, channel_id, payload)
                self.writer.write(frame)
                await self.writer.drain()
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass

    async def _close_channel(self, channel: Channel):
        """关闭通道。"""
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

    async def _cleanup(self):
        """清理会话。"""
        for channel in list(self.channels.values()):
            await self._close_channel(channel)
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except:
            pass
        
        # 输出连接统计信息
        if self.connect_stats['total'] > 0:
            success_rate = (self.connect_stats['success'] / self.connect_stats['total']) * 100
            logger.info(f"连接统计: 总数={self.connect_stats['total']}, 成功={self.connect_stats['success']}, 失败={self.connect_stats['failed']}, 成功率={success_rate:.2f}%")
            
            # 输出各策略的连接统计
            for strategy_name, stats in self.connect_stats['by_strategy'].items():
                strategy_total = stats['success'] + stats['failed']
                if strategy_total > 0:
                    strategy_success_rate = (stats['success'] / strategy_total) * 100
                    logger.info(f"策略 {strategy_name}: 成功={stats['success']}, 失败={stats['failed']}, 成功率={strategy_success_rate:.2f}%")


# ============================================================================
# 服务器
# ============================================================================

class TunnelServer:
    def __init__(self, config: ServerConfig, users: Dict[str, UserConfig]):
        self.config = config
        self.users = users
        self.ssl_context = self._create_ssl_context()

    def _create_ssl_context(self) -> ssl.SSLContext:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(self.config.cert_file, self.config.key_file)
        return ctx

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        session = TunnelSession(reader, writer, self.config, self.ssl_context, self.users)
        await session.run()

    async def start(self):
        server = await asyncio.start_server(
            self.handle_client,
            self.config.host,
            self.config.port
        )
        addr = server.sockets[0].getsockname()
        logger.info(f"SMTP 隧道服务器运行于 {addr[0]}:{addr[1]}")
        logger.info(f"主机名: {self.config.hostname}")
        logger.info(f"已加载用户数: {len(self.users)}")

        async with server:
            await server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description='SMTP 隧道服务器')
    parser.add_argument('--config', '-c', default='config.yaml')
    parser.add_argument('--users', '-u', default=None, help='用户文件（默认: 从配置或 users.yaml）')
    parser.add_argument('--debug', '-d', action='store_true')
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        config_data = load_config(args.config)
    except FileNotFoundError:
        config_data = {}

    server_conf = config_data.get('server', {})

    config = ServerConfig(
        host=server_conf.get('host', '0.0.0.0'),
        port=server_conf.get('port', 587),
        hostname=server_conf.get('hostname', 'mail.example.com'),
        cert_file=server_conf.get('cert_file', 'server.crt'),
        key_file=server_conf.get('key_file', 'server.key'),
        users_file=server_conf.get('users_file', 'users.yaml'),
        log_users=server_conf.get('log_users', True),
    )

    # 加载用户文件（命令行覆盖或从配置）
    users_file = args.users or config.users_file
    users = load_users(users_file)

    if not users:
        logger.error(f"未配置用户！请创建 {users_file}")
        logger.error("使用 smtp-tunnel-adduser 添加用户")
        return 1

    if not os.path.exists(config.cert_file):
        logger.error(f"未找到证书: {config.cert_file}")
        return 1

    server = TunnelServer(config, users)

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("服务器已停止")

    return 0


if __name__ == '__main__':
    exit(main())
