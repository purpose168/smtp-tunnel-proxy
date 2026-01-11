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

# 标准库导入
import asyncio  # 异步 I/O 框架，用于处理高并发网络连接
import ssl  # SSL/TLS 加密支持
import logging  # 日志记录模块
import argparse  # 命令行参数解析
import struct  # 二进制数据打包和解包
import os  # 操作系统接口
import socket  # 网络套接字操作
from typing import Dict, Optional  # 类型提示支持
from dataclasses import dataclass  # 数据类装饰器

# 本地模块导入
from common import (
    TunnelCrypto,  # 隧道加密工具类
    load_config,  # 加载服务器配置
    load_users,  # 加载用户配置
    ServerConfig,  # 服务器配置数据类
    UserConfig,  # 用户配置数据类
    IPWhitelist  # IP 白名单管理类
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('smtp-tunnel-server')


# ============================================================================
# 二进制协议（SMTP 握手后使用）
# ============================================================================

# 帧类型常量 - 定义二进制协议中使用的帧类型
FRAME_DATA = 0x01  # 数据帧 - 用于传输实际数据
FRAME_CONNECT = 0x02  # 连接请求帧 - 客户端请求建立到目标主机的连接
FRAME_CONNECT_OK = 0x03  # 连接成功帧 - 服务器确认连接已建立
FRAME_CONNECT_FAIL = 0x04  # 连接失败帧 - 服务器通知连接失败
FRAME_CLOSE = 0x05  # 关闭帧 - 用于关闭已建立的连接

def make_frame(frame_type: int, channel_id: int, payload: bytes = b'') -> bytes:
    """
    创建二进制帧
    
    帧格式: 类型(1字节) + 通道ID(2字节) + 负载长度(2字节) + 负载
    所有多字节字段使用网络字节序（大端序）
    
    Args:
        frame_type: 帧类型，取值为 FRAME_DATA、FRAME_CONNECT、FRAME_CONNECT_OK、FRAME_CONNECT_FAIL 或 FRAME_CLOSE
        channel_id: 通道ID，用于标识不同的隧道连接（0-65535）
        payload: 负载数据，默认为空字节
    
    Returns:
        bytes: 完整的二进制帧，包括帧头和负载
    
    Example:
        >>> frame = make_frame(FRAME_CONNECT, 1, b'example.com\x00\x1F\x90')
        >>> len(frame)
        20
    """
    return struct.pack('>BHH', frame_type, channel_id, len(payload)) + payload

def parse_frame_header(data: bytes):
    """
    解析帧头，返回帧类型、通道ID和负载长度
    
    帧头格式: 类型(1字节) + 通道ID(2字节) + 负载长度(2字节) = 5字节
    
    Args:
        data: 原始字节数据，至少包含5字节的帧头
    
    Returns:
        tuple: (frame_type, channel_id, payload_len) 如果数据足够
        None: 如果数据不足5字节
    
    Example:
        >>> header = parse_frame_header(b'\x02\x00\x01\x00\x0a')
        >>> header
        (2, 1, 10)
    """
    if len(data) < 5:
        return None
    frame_type, channel_id, payload_len = struct.unpack('>BHH', data[:5])
    return frame_type, channel_id, payload_len

# 帧头大小常量 - 帧头固定为5字节
FRAME_HEADER_SIZE = 5


# ============================================================================
# 通道 - 隧道化的 TCP 连接
# ============================================================================

# IPv4 地址池 - 用于纯 IPv6 地址的回退
# 当服务器不支持 IPv6 或 IPv6 连接失败时，使用这些 IPv4 地址作为回退选项
# 这些是常用服务的 IPv4 地址，可以用于推断或替代纯 IPv6 地址
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
    """
    隧道通道数据类 - 表示一个隧道化的 TCP 连接
    
    每个通道对应一个从客户端到目标主机的 TCP 连接，
    通过 SMTP 隧道进行数据传输。通道支持全双工通信，
    即可以同时进行双向数据传输。
    
    Attributes:
        channel_id: 通道唯一标识符（0-65535），用于在二进制协议中标识不同的连接
        host: 目标主机名或 IP 地址
        port: 目标端口号
        reader: asyncio.StreamReader，用于从目标主机读取数据
        writer: asyncio.StreamWriter，用于向目标主机写入数据
        connected: 连接状态标志，True 表示已成功连接到目标主机
        reader_task: 异步任务对象，用于从目标主机读取数据并转发给客户端
    
    Lifecycle:
        1. 创建 Channel 对象（未连接状态）
        2. 建立到目标主机的 TCP 连接
        3. 创建 reader_task 开始读取数据
        4. 传输数据（双向）
        5. 关闭连接并清理资源
    
    Example:
        >>> channel = Channel(channel_id=1, host='example.com', port=80)
        >>> reader, writer = await asyncio.open_connection('example.com', 80)
        >>> channel.reader = reader
        >>> channel.writer = writer
        >>> channel.connected = True
    """
    channel_id: int  # 通道唯一标识符
    host: str  # 目标主机名或 IP 地址
    port: int  # 目标端口号
    reader: Optional[asyncio.StreamReader] = None  # 读取器（从目标主机读取数据）
    writer: Optional[asyncio.StreamWriter] = None  # 写入器（向目标主机写入数据）
    connected: bool = False  # 连接状态标志
    reader_task: Optional[asyncio.Task] = None  # 读取任务引用


# ============================================================================
# 隧道会话
# ============================================================================

class TunnelSession:
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
        reader: asyncio.StreamReader，用于从客户端读取数据
        writer: asyncio.StreamWriter，用于向客户端写入数据
        config: ServerConfig，服务器配置对象
        ssl_context: ssl.SSLContext，SSL/TLS 上下文
        users: Dict[str, UserConfig]，用户配置字典
        authenticated: bool，认证状态标志
        binary_mode: bool，二进制模式标志
        channels: Dict[int, Channel]，活动通道字典
        write_lock: asyncio.Lock，写入锁，防止并发写入冲突
        username: Optional[str]，已认证的用户名
        user_config: Optional[UserConfig]，已认证用户的配置
        client_ip: str，客户端 IP 地址
        peer_str: str，客户端地址字符串（IP:端口）
        connect_stats: dict，连接统计信息
    """
    
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        config: ServerConfig,
        ssl_context: ssl.SSLContext,
        users: Dict[str, UserConfig]
    ):
        """
        初始化隧道会话
        
        Args:
            reader: asyncio.StreamReader，用于从客户端读取数据
            writer: asyncio.StreamWriter，用于向客户端写入数据
            config: ServerConfig，服务器配置对象，包含主机名等配置
            ssl_context: ssl.SSLContext，SSL/TLS 上下文，用于升级连接到 TLS
            users: Dict[str, UserConfig]，用户配置字典，键为用户名，值为用户配置
        
        初始化步骤:
            1. 保存传入的参数
            2. 初始化认证和模式标志为 False
            3. 创建空的通道字典和写入锁
            4. 从 writer 中提取客户端地址信息
            5. 初始化连接统计信息
        
        Note:
            - username 和 user_config 在认证成功后才会被设置
            - channels 字典在二进制模式下用于管理多个隧道连接
            - write_lock 用于防止多个协程同时向客户端写入数据
        """
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

        # 从连接中提取客户端地址信息
        peer = writer.get_extra_info('peername')
        self.client_ip = peer[0] if peer else "unknown"
        self.peer_str = f"{peer[0]}:{peer[1]}" if peer else "unknown"

        # 连接统计信息
        self.connect_stats = {
            'total': 0,  # 总连接尝试次数
            'success': 0,  # 成功连接次数
            'failed': 0,  # 失败连接次数
            'by_strategy': {}  # 按连接策略分类的统计
        }

    def _log(self, level: int, msg: str):
        """
        记录日志消息，可选包含用户信息
        
        此方法根据用户配置决定是否记录日志。如果用户配置中禁用了日志记录，
        则此方法会直接返回而不记录任何内容。否则，会根据是否已认证用户
        来决定日志消息的格式。
        
        Args:
            level: 日志级别，使用 logging 模块常量（如 logging.INFO、logging.ERROR）
            msg: 日志消息内容
        
        日志格式:
            - 已认证用户: "[{username}] {msg}"
            - 未认证用户: "{msg}"
        
        Note:
            - 如果 user_config 存在且 logging 为 False，则不记录日志
            - 此方法用于保护用户隐私，允许用户选择是否记录其活动
            - 日志级别和消息由调用者决定
        
        Example:
            >>> self._log(logging.INFO, "连接已建立")
            # 如果用户名为 "alice"，则输出: [alice] 连接已建立
        """
        if self.user_config and not self.user_config.logging:
            return  # 此用户已禁用日志记录

        if self.username:
            logger.log(level, f"[{self.username}] {msg}")
        else:
            logger.log(level, msg)

    async def run(self):
        """
        主会话处理器 - 处理完整的客户端连接生命周期
        
        此方法是隧道会话的入口点，负责协调整个连接处理流程。
        它按顺序执行以下阶段:
        1. SMTP 握手阶段 - 模拟真实 SMTP 服务器行为
        2. TLS 升级阶段 - 建立加密连接
        3. 用户认证阶段 - 验证客户端身份
        4. 二进制模式阶段 - 处理多通道数据转发
        
        异常处理:
        - asyncio.CancelledError: 正常取消，静默处理
        - Exception: 捕获所有其他异常，记录错误日志
        - finally: 确保资源被清理
        
        Note:
            - 此方法是异步的，使用 asyncio 协程
            - 任何阶段的失败都会导致会话结束
            - 资源清理在 finally 块中保证执行
        
        Example:
            >>> session = TunnelSession(reader, writer, config, ssl_context, users)
            >>> await session.run()
        """
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
        执行 SMTP 握手 - 模拟真实 SMTP 服务器行为以欺骗 DPI
        
        此方法执行完整的 SMTP 握手流程，包括 EHLO、STARTTLS、AUTH 等步骤。
        这个过程是为了让深度包检测（DPI）系统认为这是一个正常的 SMTP 连接，
        从而避免被识别为隧道流量。
        
        握手流程:
        1. 服务器发送 220 问候消息
        2. 客户端发送 EHLO/HELO
        3. 服务器发送 250 能力列表（包括 STARTTLS）
        4. 客户端发送 STARTTLS
        5. 服务器发送 220 准备 TLS
        6. 升级到 TLS 加密连接
        7. 客户端再次发送 EHLO/HELO
        8. 服务器发送 250 能力列表（包括 AUTH）
        9. 客户端发送 AUTH PLAIN <token>
        10. 服务器验证令牌并返回 235 认证成功
        11. 客户端发送 BINARY 切换到二进制模式
        12. 服务器发送 299 二进制模式已激活
        
        Returns:
            bool: True 表示握手成功，False 表示握手失败
        
        安全特性:
        - TLS 加密保护认证令牌
        - 多用户支持，每个用户独立密钥
        - IP 白名单验证（可选，每用户配置）
        - 认证令牌包含时间戳防止重放攻击
        
        Note:
            - 此方法模拟 Postfix SMTP 服务器行为
            - 认证令牌使用 TunnelCrypto.verify_auth_token_multi_user 验证
            - 用户配置中的 IP 白名单在认证后检查
            - 认证成功后设置 username 和 user_config 属性
        
        Example:
            >>> success = await session._smtp_handshake()
            >>> if success:
            ...     print("SMTP 握手成功，可以进入二进制模式")
        """
        try:
            # 发送问候 - 模拟 Postfix SMTP 服务器
            await self._send_line(f"220 {self.config.hostname} ESMTP Postfix (Ubuntu)")

            # 等待 EHLO - 客户端发送扩展 Hello
            line = await self._read_line()
            if not line or not line.upper().startswith(('EHLO', 'HELO')):
                return False

            # 发送能力列表 - 声明支持 STARTTLS 和 AUTH
            await self._send_line(f"250-{self.config.hostname}")
            await self._send_line("250-STARTTLS")  # 支持 TLS 升级
            await self._send_line("250-AUTH PLAIN LOGIN")  # 支持 PLAIN 和 LOGIN 认证
            await self._send_line("250 8BITMIME")  # 支持 8 位 MIME

            # 等待 STARTTLS - 客户端请求 TLS 升级
            line = await self._read_line()
            if not line or line.upper() != 'STARTTLS':
                return False

            await self._send_line("220 2.0.0 Ready to start TLS")

            # 升级到 TLS - 建立加密连接
            await self._upgrade_tls()

            # 再次等待 EHLO - TLS 加密后的第二个 Hello
            line = await self._read_line()
            if not line or not line.upper().startswith(('EHLO', 'HELO')):
                return False

            # 发送能力列表 - 加密后的能力声明
            await self._send_line(f"250-{self.config.hostname}")
            await self._send_line("250-AUTH PLAIN LOGIN")  # 支持 PLAIN 和 LOGIN 认证
            await self._send_line("250 8BITMIME")  # 支持 8 位 MIME

            # 等待 AUTH - 客户端发送认证令牌
            line = await self._read_line()
            if not line or not line.upper().startswith('AUTH'):
                return False

            # 解析认证令牌 - 格式: AUTH PLAIN <base64_token>
            parts = line.split(' ', 2)
            if len(parts) < 3:
                await self._send_line("535 5.7.8 Authentication failed")
                return False

            token = parts[2]

            # 多用户认证 - 验证令牌并获取用户名
            valid, username = TunnelCrypto.verify_auth_token_multi_user(token, self.users)

            if not valid or not username:
                logger.warning(f"来自 {self.peer_str} 的认证失败")
                await self._send_line("535 5.7.8 Authentication failed")
                return False

            # 获取用户配置
            self.username = username
            self.user_config = self.users.get(username)

            # 检查每用户 IP 白名单 - 如果配置了白名单，验证客户端 IP
            if self.user_config and self.user_config.whitelist:
                user_whitelist = IPWhitelist(self.user_config.whitelist)
                if not user_whitelist.is_allowed(self.client_ip):
                    logger.warning(f"用户 {username} 不允许从 IP {self.client_ip} 连接")
                    await self._send_line("535 5.7.8 Authentication failed")
                    return False

            # 认证成功
            await self._send_line("235 2.7.0 Authentication successful")
            self.authenticated = True

            # 信号二进制模式 - 客户端发送特殊标记切换到二进制模式
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
        """
        升级连接到 TLS 加密
        
        此方法将现有的明文 TCP 连接升级到 TLS 加密连接。
        TLS 升级是在 SMTP STARTTLS 命令后执行的，用于保护
        后续的认证令牌和二进制数据传输。
        
        工作原理:
        1. 获取当前传输层（transport）和协议对象
        2. 使用 loop.start_tls() 创建新的 TLS 传输层
        3. 将新的传输层设置到 reader 和 writer
        
        Note:
            - 此方法在 STARTTLS 命令后调用
            - TLS 上下文在服务器初始化时创建
            - 升级后，所有后续通信都经过 TLS 加密
            - 使用服务器端 TLS 模式（server_side=True）
        
        Example:
            >>> await session._upgrade_tls()
            # 连接现在使用 TLS 加密
        """
        transport = self.writer.transport
        protocol = self.writer._protocol
        loop = asyncio.get_event_loop()

        # 创建新的 TLS 传输层
        new_transport = await loop.start_tls(
            transport, protocol, self.ssl_context, server_side=True
        )

        # 更新 reader 和 writer 的传输层
        self.writer._transport = new_transport
        self.reader._transport = new_transport
        logger.debug(f"TLS 已建立: {self.peer_str}")

    async def _send_line(self, line: str):
        """
        发送 SMTP 行消息
        
        此方法发送一行 SMTP 协议消息，自动添加 CRLF 行结束符。
        SMTP 协议要求每行以 \\r\\n 结尾。
        
        Args:
            line: 要发送的 SMTP 行消息（不包含 CRLF）
        
        Note:
            - 自动添加 \\r\\n 行结束符
            - 使用 UTF-8 编码
            - await writer.drain() 确保数据已发送
            - 此方法用于 SMTP 握手阶段
        
        Example:
            >>> await self._send_line("220 mail.example.com ESMTP Postfix")
            # 发送: "220 mail.example.com ESMTP Postfix\\r\\n"
        """
        self.writer.write(f"{line}\r\n".encode())
        await self.writer.drain()

    async def _read_line(self) -> Optional[str]:
        """
        读取 SMTP 行消息
        
        此方法从客户端读取一行 SMTP 协议消息，自动处理 CRLF 行结束符。
        使用 60 秒超时，超时后返回 None。
        
        Returns:
            Optional[str]: 读取到的行消息（已去除 CRLF 和首尾空白），如果读取失败或超时则返回 None
        
        Note:
            - 使用 UTF-8 解码，错误时使用替换字符
            - 使用 strip() 去除首尾空白
            - 60 秒超时防止客户端无响应
            - 此方法用于 SMTP 握手阶段
        
        Example:
            >>> line = await self._read_line()
            >>> if line:
            ...     print(f"收到: {line}")
        """
        try:
            data = await asyncio.wait_for(self.reader.readline(), timeout=60.0)
            if not data:
                return None
            return data.decode('utf-8', errors='replace').strip()
        except:
            return None

    async def _binary_mode(self):
        """
        处理二进制流模式 - 这是快速模式
        
        此方法在 SMTP 握手成功后进入，处理客户端发送的二进制帧。
        二进制模式使用自定义协议，支持多通道数据转发，性能远高于 SMTP 模式。
        
        工作流程:
        1. 从客户端读取数据块（最大 65536 字节）
        2. 将数据块累积到缓冲区
        3. 从缓冲区解析完整的帧
        4. 根据帧类型调用相应的处理方法
        5. 重复直到连接关闭
        
        帧格式:
        - 帧头: 类型(1字节) + 通道ID(2字节) + 负载长度(2字节) = 5字节
        - 负载: 实际数据，长度由帧头指定
        
        异常处理:
        - 超时: 60秒无数据，检查连接是否仍然存活
        - 连接错误: ConnectionResetError, BrokenPipeError, OSError
        - 客户端关闭: 空数据块表示客户端关闭连接
        
        Note:
            - 使用缓冲区处理不完整的帧
            - 60秒超时防止客户端无响应
            - 所有帧处理都是异步的
            - 此方法在 run() 方法中调用
        
        Example:
            >>> await session._binary_mode()
            # 进入二进制模式，开始处理帧
        """
        buffer = b''

        while True:
            # 读取数据 - 最大块大小 65536 字节，超时 60 秒
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

            # 处理完整的帧 - 循环处理缓冲区中的所有完整帧
            while len(buffer) >= FRAME_HEADER_SIZE:
                header = parse_frame_header(buffer)
                if not header:
                    break

                frame_type, channel_id, payload_len = header
                total_len = FRAME_HEADER_SIZE + payload_len

                # 检查缓冲区是否包含完整的帧
                if len(buffer) < total_len:
                    break

                # 提取帧负载并从缓冲区移除
                payload = buffer[FRAME_HEADER_SIZE:total_len]
                buffer = buffer[total_len:]

                # 处理帧
                await self._handle_frame(frame_type, channel_id, payload)

    async def _handle_frame(self, frame_type: int, channel_id: int, payload: bytes):
        """
        处理二进制帧 - 根据帧类型分发到相应的处理方法
        
        此方法根据帧类型将帧分发到相应的处理方法。
        支持的帧类型包括:
        - FRAME_CONNECT: 连接请求，建立到目标主机的连接
        - FRAME_DATA: 数据帧，转发数据到目标主机
        - FRAME_CLOSE: 关闭帧，关闭指定的通道
        
        Args:
            frame_type: 帧类型，取值为 FRAME_CONNECT、FRAME_DATA 或 FRAME_CLOSE
            channel_id: 通道ID，用于标识不同的隧道连接
            payload: 帧负载数据，内容取决于帧类型
        
        帧类型说明:
        - FRAME_CONNECT: 负载格式为 host_len(1) + host + port(2)
        - FRAME_DATA: 负载为要转发的实际数据
        - FRAME_CLOSE: 负载为空
        
        Note:
            - 此方法是帧分发器，不处理具体的帧逻辑
            - 每种帧类型都有对应的处理方法
            - 未知帧类型会被忽略
        
        Example:
            >>> await session._handle_frame(FRAME_CONNECT, 1, b'\x0bexample.com\x00P')
            # 处理连接请求，连接到 example.com:80
        """
        if frame_type == FRAME_CONNECT:
            await self._handle_connect(channel_id, payload)
        elif frame_type == FRAME_DATA:
            await self._handle_data(channel_id, payload)
        elif frame_type == FRAME_CLOSE:
            await self._handle_close(channel_id)

    async def _handle_connect(self, channel_id: int, payload: bytes):
        """
        处理 CONNECT 请求 - 建立到目标主机的连接
        
        此方法处理客户端发送的 CONNECT 帧，建立到目标主机的 TCP 连接。
        支持多种连接策略，包括 IPv6、IPv4、自动地址族选择和回退机制。
        
        负载格式:
        - host_len(1字节): 主机名长度
        - host(host_len字节): 主机名或 IP 地址
        - port(2字节): 端口号（大端序）
        
        连接策略（按优先级）:
        1. IPv6 连接（如果是 IPv6 地址且服务器支持 IPv6）
        2. 自动地址族选择（如果是域名）
        3. IPv4 连接（使用解析到的 IPv4 地址）
        4. IPv4 地址池回退（对于纯 IPv6 地址）
        5. Google DNS 解析（如果是域名）
        
        Args:
            channel_id: 通道ID，用于标识这个连接
            payload: 连接请求数据，包含主机名和端口
        
        返回:
        - 成功: 发送 FRAME_CONNECT_OK 帧到客户端
        - 失败: 发送 FRAME_CONNECT_FAIL 帧到客户端
        
        IPv6 处理:
        - 修复 IPv6 地址格式错误（多个连续冒号替换为双冒号）
        - 确保双冒号只出现一次
        - 使用正确的 IPv6 地址格式 [host]:port
        
        统计信息:
        - 记录总连接尝试次数
        - 记录成功和失败次数
        - 按策略分类记录连接统计
        
        Note:
            - 使用 asyncio.wait_for 设置 10 秒连接超时
            - 每个连接策略失败后会尝试下一个策略
            - 连接成功后创建 Channel 对象并启动读取任务
            - 所有策略都失败后发送连接失败帧
        
        Example:
            >>> payload = b'\x0bexample.com\x00P'  # host_len=11, host='example.com', port=80
            >>> await session._handle_connect(1, payload)
            # 建立到 example.com:80 的连接
        """
        try:
            # 解析负载: host_len(1) + host + port(2)
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

            # 尝试解析主机的IPv4地址列表
            def get_ipv4_addresses(hostname):
                """
                获取主机的IPv4地址列表
                
                Args:
                    hostname: 主机名或域名
                
                Returns:
                    list: IPv4 地址列表
                """
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
                """
                检查服务器是否支持IPv6连接
                
                Returns:
                    bool: True 表示支持 IPv6，False 表示不支持
                """
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
            
            # 构建连接策略列表
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
            
            # 执行连接策略 - 按顺序尝试每个策略
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
            
            # 如果所有策略都失败，发送连接失败帧
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
        """
        转发数据到目标主机
        
        此方法处理客户端发送的 DATA 帧，将数据转发到目标主机。
        数据通过已建立的通道发送到目标服务器。
        
        Args:
            channel_id: 通道ID，标识要发送数据的目标通道
            payload: 要转发的数据内容
        
        工作流程:
        1. 从 channels 字典中获取指定的通道
        2. 检查通道是否存在且已连接
        3. 将数据写入目标主机的 writer
        4. 等待数据发送完成（drain）
        
        异常处理:
        - 任何写入错误都会导致通道被关闭
        - 使用 _close_channel 方法清理资源
        
        Note:
            - 此方法是单向数据转发（客户端 -> 目标主机）
            - 目标主机 -> 客户端的数据由 _channel_reader 处理
            - 使用 asyncio.StreamWriter 的 write 和 drain 方法
            - drain() 确保数据已发送到系统缓冲区
        
        Example:
            >>> await session._handle_data(1, b'GET / HTTP/1.1\r\nHost: example.com\r\n\r\n')
            # 将 HTTP 请求转发到通道 1 的目标主机
        """
        channel = self.channels.get(channel_id)
        if channel and channel.connected and channel.writer:
            try:
                channel.writer.write(payload)
                await channel.writer.drain()
            except:
                await self._close_channel(channel)

    async def _handle_close(self, channel_id: int):
        """
        关闭通道
        
        此方法处理客户端发送的 CLOSE 帧，关闭指定的通道。
        关闭操作包括:
        1. 取消通道的读取任务
        2. 关闭到目标主机的连接
        3. 从 channels 字典中移除通道
        
        Args:
            channel_id: 要关闭的通道ID
        
        工作流程:
        1. 从 channels 字典中获取指定的通道
        2. 如果通道存在，调用 _close_channel 方法关闭它
        
        Note:
            - 如果通道不存在，此方法静默返回
            - _close_channel 方法会处理所有清理工作
            - 客户端发送 CLOSE 帧后，服务器也会发送 CLOSE 帧确认
            - 通道关闭后，通道ID可以被重用
        
        Example:
            >>> await session._handle_close(1)
            # 关闭通道 1
        """
        channel = self.channels.get(channel_id)
        if channel:
            await self._close_channel(channel)

    async def _channel_reader(self, channel: Channel):
        """
        从目标主机读取数据并发送到客户端
        
        此方法是一个后台任务，持续从目标主机读取数据并通过隧道转发给客户端。
        它在通道建立连接后启动，在通道关闭时结束。
        
        Args:
            channel: Channel 对象，包含目标主机的 reader 和 writer
        
        工作流程:
        1. 循环读取目标主机的数据（最大 32768 字节）
        2. 如果读取到数据，将其封装为 DATA 帧发送给客户端
        3. 如果目标主机关闭连接，发送 CLOSE 帧并关闭通道
        4. 处理超时和异常情况
        
        超时设置:
        - 300 秒（5分钟）读取超时
        - 超时后静默退出（不关闭通道）
        
        异常处理:
        - asyncio.TimeoutError: 静默退出
        - 其他异常: 记录日志，发送 CLOSE 帧，关闭通道
        
        Note:
            - 此方法在独立的 asyncio 任务中运行
            - 使用 asyncio.wait_for 设置读取超时
            - 通道关闭时，会发送 CLOSE 帧通知客户端
            - finally 块确保资源被正确清理
        
        Example:
            >>> channel = Channel(1, "example.com", 80, reader, writer, True)
            >>> channel.reader_task = asyncio.create_task(self._channel_reader(channel))
            # 启动后台读取任务
        """
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
        """
        发送二进制帧到客户端
        
        此方法将二进制帧发送给客户端，使用 write_lock 防止并发写入冲突。
        帧格式由 make_frame 函数生成，包含帧头和负载数据。
        
        Args:
            frame_type: 帧类型，取值为 FRAME_CONNECT、FRAME_CONNECT_OK、FRAME_CONNECT_FAIL、FRAME_DATA 或 FRAME_CLOSE
            channel_id: 通道ID，标识帧所属的通道
            payload: 帧负载数据，默认为空字节
        
        工作流程:
        1. 检查连接是否已关闭
        2. 使用 write_lock 获取写入锁
        3. 调用 make_frame 生成帧数据
        4. 将帧数据写入客户端 writer
        5. 等待数据发送完成（drain）
        
        异常处理:
        - ConnectionResetError: 连接被重置，静默忽略
        - BrokenPipeError: 管道破裂，静默忽略
        - OSError: 其他操作系统错误，静默忽略
        
        Note:
            - 使用 async with 确保锁的正确释放
            - write_lock 防止多个协程同时写入导致数据交错
            - drain() 确保数据已发送到系统缓冲区
            - 所有异常都被静默处理，避免影响主循环
        
        Example:
            >>> await session._send_frame(FRAME_DATA, 1, b'Hello, World!')
            # 发送 DATA 帧到客户端，通道 ID 为 1
        """
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
        """
        关闭通道并清理资源
        
        此方法关闭指定的通道，清理所有相关资源。
        关闭操作包括取消读取任务、关闭连接、从字典中移除通道。
        
        Args:
            channel: Channel 对象，要关闭的通道
        
        工作流程:
        1. 检查通道是否已关闭，避免重复关闭
        2. 设置通道的 connected 标志为 False
        3. 取消通道的读取任务（如果存在）
        4. 关闭到目标主机的 writer
        5. 从 channels 字典中移除通道
        
        资源清理:
        - 读取任务: 使用 cancel() 取消，并等待任务完成
        - 网络连接: 使用 close() 和 wait_closed() 关闭
        - 通道字典: 使用 pop() 移除通道
        
        Note:
            - 此方法可以被多次调用，第二次调用会直接返回
            - 使用 hasattr 检查 reader_task 是否存在
            - 等待已取消的任务完成，避免 CancelledError 传播
            - 所有异常都被静默处理
        
        Example:
            >>> channel = Channel(1, "example.com", 80, reader, writer, True)
            >>> await session._close_channel(channel)
            # 关闭通道并清理所有资源
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

    async def _cleanup(self):
        """
        清理会话资源
        
        此方法清理会话的所有资源，包括关闭所有通道、关闭客户端连接、输出统计信息。
        在会话结束时调用，确保所有资源被正确释放。
        
        工作流程:
        1. 关闭所有活动通道
        2. 关闭与客户端的连接
        3. 输出连接统计信息（如果有连接记录）
        
        资源清理:
        - 通道: 遍历 channels 字典，调用 _close_channel 关闭每个通道
        - 客户端连接: 使用 close() 和 wait_closed() 关闭 writer
        - 统计信息: 输出总连接数、成功数、失败数和成功率
        
        统计信息内容:
        - 总连接尝试次数
        - 成功连接次数
        - 失败连接次数
        - 成功率（百分比）
        - 按策略分类的连接统计
        
        Note:
            - 使用 list() 创建副本，避免在遍历时修改字典
            - 所有异常都被静默处理
            - 统计信息只在有连接记录时输出
            - 成功率保留两位小数
        
        Example:
            >>> await session._cleanup()
            # 清理会话资源并输出统计信息
            # 输出示例:
            # 连接统计: 总数=10, 成功=8, 失败=2, 成功率=80.00%
            # 策略 IPv6: 成功=5, 失败=0, 成功率=100.00%
            # 策略 自动选择: 成功=3, 失败=2, 成功率=60.00%
        """
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
    """
    SMTP 隧道服务器类 - 管理服务器生命周期和客户端连接
    
    TunnelServer 负责启动和管理 SMTP 隧道服务器，处理客户端连接的接受和会话创建。
    它是服务器的主入口点，负责:
    1. 创建 SSL/TLS 上下文
    2. 启动 TCP 服务器
    3. 接受客户端连接
    4. 为每个连接创建 TunnelSession
    
    工作流程:
    1. 初始化服务器配置和 SSL 上下文
    2. 启动异步 TCP 服务器
    3. 监听指定端口
    4. 为每个客户端连接创建独立的会话
    
    Attributes:
        config: ServerConfig，服务器配置对象
        users: Dict[str, UserConfig]，用户配置字典
        ssl_context: ssl.SSLContext，SSL/TLS 上下文，用于加密连接
    
    安全特性:
        - TLS 1.2 及以上版本加密
        - 服务器证书验证
        - 多用户认证支持
    
    Note:
        - 使用 asyncio.start_server 创建异步服务器
        - 每个客户端连接在独立的协程中处理
        - 服务器运行在 serve_forever 循环中
        - 支持 IPv4 和 IPv6 双栈
    
    Example:
        >>> config = ServerConfig(host='0.0.0.0', port=587, hostname='mail.example.com')
        >>> users = {'user1': UserConfig(...)}
        >>> server = TunnelServer(config, users)
        >>> asyncio.run(server.start())
    """
    
    def __init__(self, config: ServerConfig, users: Dict[str, UserConfig]):
        """
        初始化隧道服务器
        
        Args:
            config: ServerConfig，服务器配置对象，包含主机、端口、主机名等配置
            users: Dict[str, UserConfig]，用户配置字典，键为用户名，值为用户配置
        
        初始化步骤:
            1. 保存服务器配置
            2. 保存用户配置
            3. 创建 SSL/TLS 上下文
        
        Note:
            - SSL 上下文在初始化时创建，避免重复创建
            - 用户配置用于客户端认证
            - 服务器配置用于绑定监听地址
        """
        self.config = config
        self.users = users
        self.ssl_context = self._create_ssl_context()

    def _create_ssl_context(self) -> ssl.SSLContext:
        """
        创建 SSL/TLS 上下文
        
        此方法创建用于加密客户端连接的 SSL/TLS 上下文。
        配置 TLS 协议版本和加载服务器证书。
        
        Returns:
            ssl.SSLContext: 配置好的 SSL/TLS 上下文
        
        TLS 配置:
        - 协议: TLS_SERVER（服务器模式）
        - 最低版本: TLSv1.2（禁用不安全的旧版本）
        - 证书: 从配置文件加载服务器证书和私钥
        
        安全特性:
        - 禁用 SSLv2、SSLv3、TLSv1.0、TLSv1.1（已知漏洞）
        - 使用现代加密套件
        - 服务器证书验证
        
        Note:
            - 证书文件路径从 config.cert_file 获取
            - 私钥文件路径从 config.key_file 获取
            - 如果证书或私钥不存在，会抛出异常
        
        Example:
            >>> ctx = server._create_ssl_context()
            >>> # ctx 可用于创建 SSL 套接字
        """
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(self.config.cert_file, self.config.key_file)
        return ctx

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """
        处理客户端连接
        
        此方法是每个客户端连接的入口点，为每个连接创建独立的 TunnelSession。
        在独立的协程中运行，不会阻塞其他连接。
        
        Args:
            reader: asyncio.StreamReader，用于从客户端读取数据
            writer: asyncio.StreamWriter，用于向客户端写入数据
        
        工作流程:
        1. 创建 TunnelSession 对象
        2. 启动会话处理循环
        3. 会话结束后自动清理资源
        
        Note:
            - 此方法由 asyncio.start_server 自动调用
            - 每个客户端连接在独立的协程中运行
            - 异常会被自动捕获，不会影响服务器运行
        
        Example:
            >>> # 此方法由 asyncio.start_server 自动调用
            >>> # 不需要手动调用
        """
        session = TunnelSession(reader, writer, self.config, self.ssl_context, self.users)
        await session.run()

    async def start(self):
        """
        启动 SMTP 隧道服务器
        
        此方法启动异步 TCP 服务器，开始监听客户端连接。
        服务器运行在 serve_forever 循环中，直到被中断。
        
        工作流程:
        1. 创建异步 TCP 服务器
        2. 绑定到配置的主机和端口
        3. 输出服务器启动信息
        4. 进入 serve_forever 循环
        
        服务器信息:
        - 监听地址和端口
        - 服务器主机名
        - 已加载的用户数量
        
        Note:
            - 使用 asyncio.start_server 创建异步服务器
            - serve_forever 会阻塞直到服务器停止
            - 可以通过 KeyboardInterrupt 停止服务器
            - 支持多个并发连接
        
        Example:
            >>> server = TunnelServer(config, users)
            >>> asyncio.run(server.start())
            # 服务器开始运行，监听配置的端口
        """
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
    """
    SMTP 隧道服务器主函数 - 程序入口点
    
    此函数是 SMTP 隧道服务器的入口点，负责:
    1. 解析命令行参数
    2. 加载配置文件
    3. 加载用户配置
    4. 验证证书文件
    5. 启动服务器
    
    命令行参数:
        --config, -c: 配置文件路径（默认: config.yaml）
        --users, -u: 用户文件路径（默认: 从配置或 users.yaml）
        --debug, -d: 启用调试模式
    
    工作流程:
        1. 解析命令行参数
        2. 设置日志级别（如果启用调试模式）
        3. 加载配置文件
        4. 创建 ServerConfig 对象
        5. 加载用户配置
        6. 验证用户配置和证书文件
        7. 创建并启动 TunnelServer
    
    错误处理:
        - 配置文件不存在: 使用默认配置
        - 用户配置为空: 输出错误信息并退出
        - 证书文件不存在: 输出错误信息并退出
        - KeyboardInterrupt: 优雅地停止服务器
    
    返回值:
        - 0: 成功
        - 1: 失败（用户配置为空或证书文件不存在）
    
    Note:
        - 使用 argparse 解析命令行参数
        - 配置文件使用 YAML 格式
        - 用户文件使用 YAML 格式
        - 服务器在 KeyboardInterrupt 时优雅退出
    
    Example:
        # 使用默认配置启动服务器
        $ python server.py
        
        # 指定配置文件
        $ python server.py --config my-config.yaml
        
        # 指定用户文件
        $ python server.py --users my-users.yaml
        
        # 启用调试模式
        $ python server.py --debug
    """
    parser = argparse.ArgumentParser(description='SMTP 隧道服务器')
    parser.add_argument('--config', '-c', default='config.yaml')
    parser.add_argument('--users', '-u', default=None, help='用户文件（默认: 从配置或 users.yaml）')
    parser.add_argument('--debug', '-d', action='store_true')
    args = parser.parse_args()

    # 设置日志级别 - 如果启用调试模式，设置为 DEBUG 级别
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # 加载配置文件 - 如果文件不存在，使用空字典
    try:
        config_data = load_config(args.config)
    except FileNotFoundError:
        config_data = {}

    # 从配置中提取服务器配置
    server_conf = config_data.get('server', {})

    # 创建 ServerConfig 对象 - 使用配置文件中的值或默认值
    config = ServerConfig(
        host=server_conf.get('host', '0.0.0.0'),
        port=server_conf.get('port', 587),
        hostname=server_conf.get('hostname', 'mail.example.com'),
        cert_file=server_conf.get('cert_file', 'server.crt'),
        key_file=server_conf.get('key_file', 'server.key'),
        users_file=server_conf.get('users_file', 'users.yaml'),
        log_users=server_conf.get('log_users', True),
    )

    # 加载用户文件 - 命令行参数优先于配置文件
    users_file = args.users or config.users_file
    users = load_users(users_file)

    # 验证用户配置 - 如果没有用户，输出错误信息并退出
    if not users:
        logger.error(f"未配置用户！请创建 {users_file}")
        logger.error("使用 smtp-tunnel-adduser 添加用户")
        return 1

    # 验证证书文件 - 如果证书文件不存在，输出错误信息并退出
    if not os.path.exists(config.cert_file):
        logger.error(f"未找到证书: {config.cert_file}")
        return 1

    # 创建服务器对象
    server = TunnelServer(config, users)

    # 启动服务器 - 使用 asyncio.run 运行异步服务器
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("服务器已停止")

    return 0


if __name__ == '__main__':
    exit(main())
