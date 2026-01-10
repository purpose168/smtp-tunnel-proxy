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

@dataclass
class Channel:
    channel_id: int
    host: str
    port: int
    reader: Optional[asyncio.StreamReader] = None
    writer: Optional[asyncio.StreamWriter] = None
    connected: bool = False


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

            logger.info(f"CONNECT ch={channel_id} -> {host}:{port}")

            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=30.0
                )

                channel = Channel(
                    channel_id=channel_id,
                    host=host,
                    port=port,
                    reader=reader,
                    writer=writer,
                    connected=True
                )
                self.channels[channel_id] = channel

                # 开始从目标读取
                asyncio.create_task(self._channel_reader(channel))

                # 发送成功
                await self._send_frame(FRAME_CONNECT_OK, channel_id)
                logger.info(f"CONNECTED ch={channel_id}")

            except Exception as e:
                logger.error(f"连接失败: {e}")
                await self._send_frame(FRAME_CONNECT_FAIL, channel_id, str(e).encode()[:100])

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
