#!/usr/bin/env python3
"""
SMTP 隧道服务端 - 快速二进制模式

版本: 1.3.0

协议:
1. SMTP 握手（EHLO, STARTTLS, AUTH）- 看起来像真实的 SMTP
2. AUTH 成功后，切换到二进制流模式
3. 全双工二进制协议 - 不再有 SMTP 开销

功能:
- 支持多用户，每个用户有独立密钥
- 每用户 IP 白名单
- 每用户日志记录（可选）
"""

import asyncio
import ssl
import logging
import argparse
import struct
import os
import re
import ipaddress
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
# 二进制协议（在 SMTP 握手后使用）
# ============================================================================

# 帧类型
FRAME_DATA = 0x01  # 数据帧
FRAME_CONNECT = 0x02  # 连接帧
FRAME_CONNECT_OK = 0x03  # 连接成功帧
FRAME_CONNECT_FAIL = 0x04  # 连接失败帧
FRAME_CLOSE = 0x05  # 关闭帧

def make_frame(frame_type: int, channel_id: int, payload: bytes = b'') -> bytes:
    """创建二进制帧: 类型(1) + 通道(2) + 长度(2) + 负载"""
    return struct.pack('>BHH', frame_type, channel_id, len(payload)) + payload

def parse_frame_header(data: bytes):
    """解析帧头部，返回 (类型, 通道ID, 负载长度) 或 None"""
    if len(data) < 5:
        return None
    frame_type, channel_id, payload_len = struct.unpack('>BHH', data[:5])
    return frame_type, channel_id, payload_len

FRAME_HEADER_SIZE = 5  # 帧头部大小


# ============================================================================
# 通道 - 隧道 TCP 连接
# ============================================================================

@dataclass
class Channel:
    """表示一个隧道 TCP 连接的通道"""
    channel_id: int  # 通道 ID
    host: str  # 目标主机
    port: int  # 目标端口
    reader: Optional[asyncio.StreamReader] = None  # 读取器
    writer: Optional[asyncio.StreamWriter] = None  # 写入器
    connected: bool = False  # 连接状态


# ============================================================================
# 隧道会话
# ============================================================================

class TunnelSession:
    """处理单个客户端的隧道会话"""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        config: ServerConfig,
        ssl_context: ssl.SSLContext,
        users: Dict[str, UserConfig]
    ):
        """初始化隧道会话"""
        self.reader = reader
        self.writer = writer
        self.config = config
        self.ssl_context = ssl_context
        self.users = users
        self.authenticated = False  # 认证状态
        self.binary_mode = False  # 二进制模式标志
        self.channels: Dict[int, Channel] = {}  # 通道字典
        self.write_lock = asyncio.Lock()  # 写入锁

        # 用户信息（认证后设置）
        self.username: Optional[str] = None
        self.user_config: Optional[UserConfig] = None

        # 获取客户端信息
        peer = writer.get_extra_info('peername')
        self.client_ip = peer[0] if peer else "unknown"
        self.peer_str = f"{peer[0]}:{peer[1]}" if peer else "unknown"

    def _log(self, level: int, msg: str):
        """记录日志（可选包含用户信息）"""
        # 如果用户禁用了日志记录，则跳过
        if self.user_config and not self.user_config.logging:
            return

        # 根据是否已认证记录不同的日志格式
        if self.username:
            logger.log(level, f"[{self.username}] {msg}")
        else:
            logger.log(level, msg)

    async def run(self):
        """主会话处理器"""
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
        """
        执行 SMTP 握手 - 这是 DPI 看到的内容
        返回: True 表示握手成功，False 表示失败
        """
        try:
            # 发送问候消息
            await self._send_line(f"220 {self.config.hostname} ESMTP Postfix (Ubuntu)")

            # 等待 EHLO
            line = await self._read_line()
            if not line or not line.upper().startswith(('EHLO', 'HELO')):
                return False

            # 发送服务器功能列表
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

            # 解析认证令牌
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
                    logger.warning(f"用户 {username} 不允许从 IP {self.client_ip} 访问")
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
        """升级连接到 TLS"""
        transport = self.writer.transport
        protocol = self.writer._protocol
        loop = asyncio.get_event_loop()

        # 启动 TLS 升级
        new_transport = await loop.start_tls(
            transport, protocol, self.ssl_context, server_side=True
        )

        # 更新读写器的传输层
        self.writer._transport = new_transport
        self.reader._transport = new_transport
        logger.debug(f"TLS 已建立: {self.peer_str}")

    async def _send_line(self, line: str):
        """发送 SMTP 行"""
        self.writer.write(f"{line}\r\n".encode())
        await self.writer.drain()

    async def _read_line(self) -> Optional[str]:
        """读取 SMTP 行"""
        try:
            data = await asyncio.wait_for(self.reader.readline(), timeout=60.0)
            if not data:
                return None
            return data.decode('utf-8', errors='replace').strip()
        except asyncio.TimeoutError:
            logger.debug(f"读取行超时: {self.peer_str}")
            return None
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            logger.debug(f"连接错误: {e}")
            return None
        except UnicodeDecodeError as e:
            logger.warning(f"解码错误: {e}")
            return None

    async def _binary_mode(self):
        """处理二进制流模式 - 这是快速模式"""
        buffer = b''  # 数据缓冲区

        while True:
            # 读取数据
            try:
                chunk = await asyncio.wait_for(self.reader.read(65536), timeout=60.0)
                if not chunk:
                    self._log(logging.DEBUG, "客户端关闭连接")
                    break
                buffer += chunk
            except asyncio.TimeoutError:
                # 检查连接是否仍然活跃
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

                # 如果数据不足，等待更多数据
                if len(buffer) < total_len:
                    break

                # 提取负载并更新缓冲区
                payload = buffer[FRAME_HEADER_SIZE:total_len]
                buffer = buffer[total_len:]

                # 处理帧
                await self._handle_frame(frame_type, channel_id, payload)

    async def _handle_frame(self, frame_type: int, channel_id: int, payload: bytes):
        """处理二进制帧"""
        if frame_type == FRAME_CONNECT:
            await self._handle_connect(channel_id, payload)
        elif frame_type == FRAME_DATA:
            await self._handle_data(channel_id, payload)
        elif frame_type == FRAME_CLOSE:
            await self._handle_close(channel_id)

    async def _handle_connect(self, channel_id: int, payload: bytes):
        """处理 CONNECT 请求"""
        # 输入验证：检查payload最小长度
        MIN_PAYLOAD_SIZE = 4  # 主机长度(1) + 最短主机名(1) + 端口(2)
        if len(payload) < MIN_PAYLOAD_SIZE:
            logger.warning(f"无效的连接请求: payload太短 ({len(payload)} 字节)")
            await self._send_frame(FRAME_CONNECT_FAIL, channel_id, b'Invalid payload')
            return
        
        # 检查通道数量限制
        MAX_CHANNELS = 1000
        if len(self.channels) >= MAX_CHANNELS:
            logger.warning(f"通道数量超过限制: {len(self.channels)} >= {MAX_CHANNELS}")
            await self._send_frame(FRAME_CONNECT_FAIL, channel_id, b'Too many channels')
            return
        
        try:
            # 解析: 主机长度(1) + 主机名 + 端口(2)
            host_len = payload[0]
            
            # 验证主机名长度
            MAX_HOST_LEN = 253  # DNS最大主机名长度
            if host_len == 0 or host_len > MAX_HOST_LEN:
                logger.warning(f"无效的主机名长度: {host_len}")
                await self._send_frame(FRAME_CONNECT_FAIL, channel_id, b'Invalid hostname length')
                return
            
            # 验证payload是否包含完整的主机名和端口
            if len(payload) < 1 + host_len + 2:
                logger.warning(f"payload不完整: 需要 {1 + host_len + 2} 字节，实际 {len(payload)} 字节")
                await self._send_frame(FRAME_CONNECT_FAIL, channel_id, b'Incomplete payload')
                return
            
            host = payload[1:1+host_len].decode('utf-8')
            port = struct.unpack('>H', payload[1+host_len:3+host_len])[0]
            
            # 验证端口号范围
            if port == 0 or port > 65535:
                logger.warning(f"无效的端口号: {port}")
                await self._send_frame(FRAME_CONNECT_FAIL, channel_id, b'Invalid port')
                return
            
            # 验证主机名格式（防止注入攻击）
            if not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*$', host):
                # 也允许IP地址格式
                try:
                    ipaddress.ip_address(host)
                except ValueError:
                    logger.warning(f"无效的主机名格式: {host}")
                    await self._send_frame(FRAME_CONNECT_FAIL, channel_id, b'Invalid hostname format')
                    return

            logger.info(f"连接 ch={channel_id} -> {host}:{port}")

            try:
                # 连接到目标主机
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=30.0
                )

                # 创建通道对象
                channel = Channel(
                    channel_id=channel_id,
                    host=host,
                    port=port,
                    reader=reader,
                    writer=writer,
                    connected=True
                )
                self.channels[channel_id] = channel

                # 启动从目标读取数据的任务
                asyncio.create_task(self._channel_reader(channel))

                # 发送成功响应
                await self._send_frame(FRAME_CONNECT_OK, channel_id)
                logger.info(f"已连接 ch={channel_id}")

            except Exception as e:
                logger.error(f"连接失败: {e}")
                # 发送失败响应（限制错误消息长度）
                await self._send_frame(FRAME_CONNECT_FAIL, channel_id, str(e).encode()[:100])

        except UnicodeDecodeError as e:
            logger.error(f"主机名解码错误: {e}")
            await self._send_frame(FRAME_CONNECT_FAIL, channel_id, b'Invalid hostname encoding')
        except struct.error as e:
            logger.error(f"端口解析错误: {e}")
            await self._send_frame(FRAME_CONNECT_FAIL, channel_id, b'Invalid port format')
        except Exception as e:
            logger.error(f"处理连接错误: {e}")
            await self._send_frame(FRAME_CONNECT_FAIL, channel_id)

    async def _handle_data(self, channel_id: int, payload: bytes):
        """将数据转发到目标"""
        channel = self.channels.get(channel_id)
        if channel and channel.connected and channel.writer:
            try:
                channel.writer.write(payload)
                await channel.writer.drain()
            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                self._log(logging.DEBUG, f"通道 {channel_id} 写入失败: {e}")
                await self._close_channel(channel)
            except Exception as e:
                self._log(logging.ERROR, f"通道 {channel_id} 意外错误: {e}")
                await self._close_channel(channel)

    async def _handle_close(self, channel_id: int):
        """关闭通道"""
        channel = self.channels.get(channel_id)
        if channel:
            await self._close_channel(channel)

    async def _channel_reader(self, channel: Channel):
        """从目标读取数据并发送到客户端"""
        try:
            while channel.connected:
                # 从目标读取数据
                data = await asyncio.wait_for(
                    channel.reader.read(32768),
                    timeout=300.0
                )
                if not data:
                    break

                # 将数据发送到客户端
                await self._send_frame(FRAME_DATA, channel.channel_id, data)

        except asyncio.TimeoutError:
            pass
        except Exception as e:
            logger.debug(f"通道读取器错误: {e}")
        finally:
            # 清理通道
            if channel.connected:
                await self._send_frame(FRAME_CLOSE, channel.channel_id)
                await self._close_channel(channel)

    async def _send_frame(self, frame_type: int, channel_id: int, payload: bytes = b''):
        """向客户端发送二进制帧"""
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
        """关闭通道"""
        if not channel.connected:
            return
        channel.connected = False

        # 关闭写入器
        if channel.writer:
            try:
                channel.writer.close()
                await channel.writer.wait_closed()
            except (ConnectionResetError, BrokenPipeError, OSError):
                pass  # 连接已断开，忽略错误
            except Exception as e:
                logger.debug(f"关闭通道写入器时出错: {e}")

        # 从通道字典中移除
        self.channels.pop(channel.channel_id, None)

    async def _cleanup(self):
        """清理会话"""
        # 关闭所有通道
        for channel in list(self.channels.values()):
            await self._close_channel(channel)
        # 关闭客户端连接
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass  # 连接已断开，忽略错误
        except Exception as e:
            logger.debug(f"清理会话时出错: {e}")


# ============================================================================
# 服务端
# ============================================================================

class TunnelServer:
    """SMTP 隧道服务端"""

    def __init__(self, config: ServerConfig, users: Dict[str, UserConfig]):
        """初始化服务端"""
        self.config = config
        self.users = users
        self.ssl_context = self._create_ssl_context()

    def _create_ssl_context(self) -> ssl.SSLContext:
        """创建 SSL 上下文"""
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2  # 最低 TLS 1.2
        ctx.load_cert_chain(self.config.cert_file, self.config.key_file)
        return ctx

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """处理客户端连接"""
        session = TunnelSession(reader, writer, self.config, self.ssl_context, self.users)
        await session.run()

    async def start(self):
        """启动服务端"""
        server = await asyncio.start_server(
            self.handle_client,
            self.config.host,
            self.config.port
        )
        addr = server.sockets[0].getsockname()
        logger.info(f"SMTP 隧道服务端运行在 {addr[0]}:{addr[1]}")
        logger.info(f"主机名: {self.config.hostname}")
        logger.info(f"已加载用户数: {len(self.users)}")

        async with server:
            await server.serve_forever()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='SMTP 隧道服务端')
    parser.add_argument('--config', '-c', default='config.yaml', help='配置文件路径')
    parser.add_argument('--users', '-u', default=None, help='用户文件（默认：从配置或 users.yaml）')
    parser.add_argument('--debug', '-d', action='store_true', help='启用调试模式')
    args = parser.parse_args()

    # 设置调试级别
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # 加载配置文件
    try:
        config_data = load_config(args.config)
    except FileNotFoundError:
        config_data = {}

    server_conf = config_data.get('server', {})

    # 创建服务端配置
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

    # 检查是否有用户配置
    if not users:
        logger.error(f"未配置用户！请创建 {users_file}")
        logger.error("使用 smtp-tunnel-adduser 添加用户")
        return 1

    # 检查证书文件是否存在
    if not os.path.exists(config.cert_file):
        logger.error(f"未找到证书: {config.cert_file}")
        return 1

    # 创建并启动服务端
    server = TunnelServer(config, users)

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("服务端已停止")

    return 0


if __name__ == '__main__':
    exit(main())
