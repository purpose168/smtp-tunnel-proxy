"""
SMTP 隧道 - 通用协议和工具
客户端和服务器共享的组件。

版本: 1.3.0

功能概述:
本模块提供了 SMTP 隧道代理系统的核心协议定义和工具函数。
这些组件被客户端和服务器共享，确保两端使用相同的协议和加密机制。

主要功能:
1. 隧道协议定义 - 定义消息格式和类型
2. 加密/解密 - 使用 ChaCha20-Poly1305 进行认证加密
3. 流量整形 - 通过随机延迟和填充规避深度包检测（DPI）
4. SMTP 消息生成 - 生成逼真的 MIME 邮件消息包装隧道数据
5. 配置管理 - 加载和保存配置文件
6. 用户管理 - 管理用户认证和权限

协议架构:
- 使用 SMTP 协议作为传输层，伪装成正常的邮件通信
- 在 SMTP 连接建立后切换到二进制协议模式
- 使用多路复用技术支持多个并发通道
- 每个通道对应一个独立的 TCP 连接

安全特性:
- TLS 加密通信（使用 STARTTLS）
- ChaCha20-Poly1305 认证加密（AEAD）
- HMAC-SHA256 令牌认证
- 时间戳防重放攻击
- 用户白名单和访问控制

依赖项:
- cryptography: 用于加密操作
- yaml: 用于配置文件解析
- asyncio: 用于异步 I/O
"""

# 标准库导入
import struct  # 用于二进制数据的打包和解包
import asyncio  # 用于异步 I/O 操作
import random  # 用于生成随机数
import logging  # 用于日志记录

# 设置日志记录器
logger = logging.getLogger(__name__)

import hashlib  # 用于哈希计算
import hmac  # 用于 HMAC 认证
import os  # 用于操作系统接口
import base64  # 用于 Base64 编码/解码
import time  # 用于时间相关操作
from enum import IntEnum  # 用于枚举类型
from dataclasses import dataclass  # 用于数据类
from typing import Optional, List, Tuple, Dict  # 用于类型注解
from datetime import datetime, timezone  # 用于日期时间处理

# 加密库导入
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305  # ChaCha20-Poly1305 认证加密
from cryptography.hazmat.primitives import hashes  # 哈希算法
from cryptography.hazmat.primitives.kdf.hkdf import HKDF  # HKDF 密钥派生
from cryptography.hazmat.backends import default_backend  # 加密后端


# ============================================================================
# 协议常量
# ============================================================================

PROTOCOL_VERSION = 1  # 当前协议版本号
MAX_PAYLOAD_SIZE = 65535  # 最大载荷大小（64KB - 1）
NONCE_SIZE = 12  # ChaCha20-Poly1305 nonce 大小（12 字节）
TAG_SIZE = 16  # ChaCha20-Poly1305 认证标签大小（16 字节）

# 消息类型枚举
class MsgType(IntEnum):
    """
    隧道协议消息类型枚举
    
    定义了隧道中传输的所有消息类型，用于多路复用多个 TCP 连接。
    
    消息类型说明:
    - DATA: 传输实际的应用层数据
    - CONNECT: 请求建立新的连接通道
    - CONNECT_OK: 连接建立成功的响应
    - CONNECT_FAIL: 连接建立失败的响应
    - CLOSE: 关闭已建立的通道
    - KEEPALIVE: 保持连接活跃的心跳消息
    - KEEPALIVE_ACK: 心跳消息的确认响应
    """
    DATA = 0x01           # 隧道数据 - 在通道上传输实际数据
    CONNECT = 0x02        # 打开新通道（SOCKS CONNECT）- 请求建立到目标主机的连接
    CONNECT_OK = 0x03     # 连接已建立 - 服务器成功连接到目标主机
    CONNECT_FAIL = 0x04   # 连接失败 - 服务器无法连接到目标主机
    CLOSE = 0x05          # 关闭通道 - 关闭指定的通道并释放资源
    KEEPALIVE = 0x06      # 保持连接活跃 - 定期发送以检测连接状态
    KEEPALIVE_ACK = 0x07  # 保活响应 - 对 KEEPALIVE 消息的确认


# ============================================================================
# 隧道协议消息
# ============================================================================

@dataclass
class TunnelMessage:
    """
    隧道协议消息类
    
    用于多路复用隧道流量的二进制协议消息。每个消息包含类型、通道 ID 和载荷。
    
    线路格式（加密前）:
    ┌─────────┬────────────┬────────────┬──────────────┬─────────────┐
    │ 版本    │ 消息类型   │ 通道 ID    │ 负载长度     │   负载      │
    │ 1 字节  │  1 字节    │  2 字节    │  2 字节      │  可变长度   │
    └─────────┴────────────┴────────────┴──────────────┴─────────────┘
    
    所有多字节字段使用大端序（网络字节序）。
    
    Attributes:
        msg_type: 消息类型（MsgType 枚举）
        channel_id: 通道 ID（0-65535），用于标识不同的连接
        payload: 消息载荷（字节数据）
        HEADER_SIZE: 消息头部大小（6 字节）
    
    使用示例:
        # 创建数据消息
        msg = TunnelMessage.data(channel_id=1, data=b'Hello')
        
        # 创建连接请求消息
        msg = TunnelMessage.connect(channel_id=2, host='example.com', port=80)
        
        # 序列化消息
        data = msg.serialize()
        
        # 反序列化消息
        msg, remaining = TunnelMessage.deserialize(data)
    """
    msg_type: MsgType
    channel_id: int
    payload: bytes

    HEADER_SIZE = 6  # 头部大小: 版本(1) + 类型(1) + 通道ID(2) + 载荷长度(2)

    def serialize(self) -> bytes:
        """
        将消息序列化为字节
        
        按照协议格式将消息转换为字节数组，准备发送。
        
        Returns:
            bytes: 序列化后的消息字节
            
        Raises:
            struct.error: 如果载荷长度超过 65535
        """
        header = struct.pack(
            '>BBHH',
            PROTOCOL_VERSION,
            self.msg_type,
            self.channel_id,
            len(self.payload)
        )
        return header + self.payload

    @classmethod
    def deserialize(cls, data: bytes) -> Tuple['TunnelMessage', bytes]:
        """
        从字节反序列化消息
        
        从字节数组中解析消息，返回消息对象和剩余的字节数据。
        支持从流中连续解析多个消息。
        
        Args:
            data: 包含消息的字节数组
            
        Returns:
            Tuple[TunnelMessage, bytes]: (解析出的消息, 剩余的字节数据)
            
        Raises:
            ValueError: 如果数据不足以解析头部或载荷，或协议版本不匹配
        """
        if len(data) < cls.HEADER_SIZE:
            raise ValueError("数据不足以解析头部")

        version, msg_type, channel_id, payload_len = struct.unpack(
            '>BBHH', data[:cls.HEADER_SIZE]
        )

        if version != PROTOCOL_VERSION:
            raise ValueError(f"未知的协议版本: {version}")

        total_len = cls.HEADER_SIZE + payload_len
        if len(data) < total_len:
            raise ValueError("数据不足以解析负载")

        payload = data[cls.HEADER_SIZE:total_len]
        remaining = data[total_len:]

        return cls(MsgType(msg_type), channel_id, payload), remaining

    @classmethod
    def data(cls, channel_id: int, data: bytes) -> 'TunnelMessage':
        """
        创建 DATA 消息
        
        用于在已建立的通道上传输实际数据。
        
        Args:
            channel_id: 通道 ID
            data: 要传输的数据
            
        Returns:
            TunnelMessage: DATA 类型的消息对象
        """
        return cls(MsgType.DATA, channel_id, data)

    @classmethod
    def connect(cls, channel_id: int, host: str, port: int) -> 'TunnelMessage':
        """
        创建 CONNECT 消息
        
        用于请求建立到目标主机的连接。
        
        载荷格式:
        ┌──────────┬─────────────┬────────┐
        │ 主机长度 │   主机名    │ 端口号  │
        │  1 字节  │  可变长度   │ 2 字节 │
        └──────────┴─────────────┴────────┘
        
        Args:
            channel_id: 通道 ID
            host: 目标主机名或 IP 地址
            port: 目标端口号
            
        Returns:
            TunnelMessage: CONNECT 类型的消息对象
        """
        # 载荷格式: host_len (1) + host + port (2)
        host_bytes = host.encode('utf-8')
        payload = struct.pack('>B', len(host_bytes)) + host_bytes + struct.pack('>H', port)
        return cls(MsgType.CONNECT, channel_id, payload)

    @classmethod
    def connect_ok(cls, channel_id: int) -> 'TunnelMessage':
        """
        创建 CONNECT_OK 消息
        
        表示服务器成功连接到目标主机，通道已准备好传输数据。
        
        Args:
            channel_id: 通道 ID
            
        Returns:
            TunnelMessage: CONNECT_OK 类型的消息对象
        """
        return cls(MsgType.CONNECT_OK, channel_id, b'')

    @classmethod
    def connect_fail(cls, channel_id: int, reason: str = '') -> 'TunnelMessage':
        """
        创建 CONNECT_FAIL 消息
        
        表示服务器无法连接到目标主机。
        
        Args:
            channel_id: 通道 ID
            reason: 失败原因（可选）
            
        Returns:
            TunnelMessage: CONNECT_FAIL 类型的消息对象
        """
        return cls(MsgType.CONNECT_FAIL, channel_id, reason.encode('utf-8'))

    @classmethod
    def close(cls, channel_id: int) -> 'TunnelMessage':
        """
        创建 CLOSE 消息
        
        用于关闭指定的通道并释放相关资源。
        
        Args:
            channel_id: 要关闭的通道 ID
            
        Returns:
            TunnelMessage: CLOSE 类型的消息对象
        """
        return cls(MsgType.CLOSE, channel_id, b'')

    @classmethod
    def keepalive(cls) -> 'TunnelMessage':
        """
        创建 KEEPALIVE 消息
        
        用于检测连接状态，防止连接因超时而断开。
        
        Returns:
            TunnelMessage: KEEPALIVE 类型的消息对象
        """
        return cls(MsgType.KEEPALIVE, 0, b'')

    @classmethod
    def keepalive_ack(cls) -> 'TunnelMessage':
        """
        创建 KEEPALIVE_ACK 消息
        
        对 KEEPALIVE 消息的确认响应。
        
        Returns:
            TunnelMessage: KEEPALIVE_ACK 类型的消息对象
        """
        return cls(MsgType.KEEPALIVE_ACK, 0, b'')

    def parse_connect(self) -> Tuple[str, int]:
        """
        解析 CONNECT 消息的载荷
        
        从 CONNECT 消息中提取目标主机和端口信息。
        
        Returns:
            Tuple[str, int]: (主机名, 端口号)
            
        Raises:
            ValueError: 如果消息不是 CONNECT 类型
        """
        if self.msg_type != MsgType.CONNECT:
            raise ValueError("不是 CONNECT 消息")
        host_len = self.payload[0]
        host = self.payload[1:1+host_len].decode('utf-8')
        port = struct.unpack('>H', self.payload[1+host_len:3+host_len])[0]
        return host, port


# ============================================================================
# 加密
# ============================================================================

class TunnelCrypto:
    """
    隧道加密类
    
    处理隧道消息的加密/解密操作。
    
    加密方案:
    - 使用 ChaCha20-Poly1305 进行认证加密（AEAD）
    - 使用 HKDF-SHA256 从预共享密钥派生加密密钥
    - 为客户端->服务器和服务器->客户端使用不同的密钥
    - 使用序列号生成 nonce，防止重放攻击
    
    密钥派生流程:
    1. 从预共享密钥（secret）派生 64 字节密钥材料
    2. 前 32 字节用于客户端->服务器方向
    3. 后 32 字节用于服务器->客户端方向
    
    加密格式:
    ┌────────────────┬────────────┬─────────────┐
    │     nonce      │   密文     │  认证标签   │
    │    12 字节     │  可变长度  │   16 字节   │
    └────────────────┴────────────┴─────────────┘
    
    Attributes:
        secret: 预共享密钥（字节串）
        is_server: 是否为服务器端
        send_key: 发送方向使用的 ChaCha20-Poly1305 密钥
        recv_key: 接收方向使用的 ChaCha20-Poly1305 密钥
        send_seq: 发送序列号（用于 nonce 生成）
        recv_seq: 接收序列号（用于验证）
    
    使用示例:
        # 创建加密实例
        crypto = TunnelCrypto("my-secret-key", is_server=False)
        
        # 加密数据
        encrypted = crypto.encrypt(b"Hello, World!")
        
        # 解密数据
        decrypted = crypto.decrypt(encrypted)
    """

    def __init__(self, secret: str, is_server: bool = False):
        """
        使用预共享密钥初始化加密实例
        
        Args:
            secret: 预共享密钥字符串
            is_server: True 表示服务器，False 表示客户端
        """
        self.secret = secret.encode('utf-8')
        self.is_server = is_server

        # 为客户端->服务器和服务器->客户端派生单独的密钥
        self._derive_keys()

        # 用于 nonce 生成的序列号（防止重放）
        self.send_seq = 0
        self.recv_seq = 0

    def _derive_keys(self):
        """
        使用 HKDF 从预共享密钥派生加密密钥
        
        使用 HKDF-SHA256 算法从预共享密钥派生两个独立的密钥：
        - 客户端->服务器密钥（前 32 字节）
        - 服务器->客户端密钥（后 32 字节）
        
        HKDF 参数:
        - 算法: SHA256
        - 输出长度: 64 字节（每个方向 32 字节）
        - 盐值: b'smtp-tunnel-v1'（固定值）
        - 信息: b'tunnel-keys'（固定值）
        """
        # 派生主密钥
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=64,  # 每个方向 32 字节
            salt=b'smtp-tunnel-v1',
            info=b'tunnel-keys',
            backend=default_backend(),
        )
        key_material = hkdf.derive(self.secret)

        # 分割为客户端->服务器和服务器->客户端密钥
        c2s_key = key_material[:32]
        s2c_key = key_material[32:]

        if self.is_server:
            # 服务器使用 s2c_key 发送，c2s_key 接收
            self.send_key = ChaCha20Poly1305(s2c_key)
            self.recv_key = ChaCha20Poly1305(c2s_key)
        else:
            # 客户端使用 c2s_key 发送，s2c_key 接收
            self.send_key = ChaCha20Poly1305(c2s_key)
            self.recv_key = ChaCha20Poly1305(s2c_key)

    def encrypt(self, plaintext: bytes) -> bytes:
        """
        使用认证加密加密数据
        
        使用 ChaCha20-Poly1305 加密数据，并附加认证标签。
        Nonce 由序列号和随机数组成，确保唯一性。
        
        Nonce 格式:
        ┌────────────────┬────────────┐
        │  序列号 (8B)   │ 随机数(4B) │
        │   大端序       │            │
        └────────────────┴────────────┘
        
        Args:
            plaintext: 要加密的明文数据
            
        Returns:
            bytes: nonce (12 字节) + 密文 + tag (16 字节)
            
        Raises:
            OverflowError: 如果序列号超过 2^64-1
        """
        # 从序列号 + 随机数生成 nonce
        nonce = struct.pack('>Q', self.send_seq) + os.urandom(4)
        self.send_seq += 1

        ciphertext = self.send_key.encrypt(nonce, plaintext, None)
        return nonce + ciphertext

    def decrypt(self, data: bytes) -> bytes:
        """
        解密并验证数据
        
        从加密数据中提取 nonce，使用 ChaCha20-Poly1305 解密并验证认证标签。
        如果认证失败，会抛出异常。
        
        Args:
            data: 加密数据，格式为 nonce (12 字节) + 密文 + tag (16 字节)
            
        Returns:
            bytes: 解密后的明文数据
            
        Raises:
            ValueError: 如果数据太短或认证失败
        """
        if len(data) < NONCE_SIZE + TAG_SIZE:
            raise ValueError("数据太短")

        nonce = data[:NONCE_SIZE]
        ciphertext = data[NONCE_SIZE:]

        plaintext = self.recv_key.decrypt(nonce, ciphertext, None)
        self.recv_seq += 1

        return plaintext

    def generate_auth_token(self, timestamp: int, username: str = None) -> str:
        """
        为 SMTP AUTH 生成认证令牌
        
        使用 HMAC-SHA256 生成认证令牌，包含时间戳以防止重放攻击。
        支持单用户和多用户两种格式。
        
        令牌格式（编码前）:
        - 多用户格式: username:timestamp:mac
        - 单用户格式: timestamp:mac（向后兼容）
        
        最终输出为 Base64 编码的令牌。
        
        Args:
            timestamp: Unix 时间戳
            username: 可选用户名（用于多用户模式）
            
        Returns:
            str: Base64 编码的认证令牌
        """
        if username:
            # 多用户格式
            message = f"smtp-tunnel-auth:{username}:{timestamp}".encode()
            mac = hmac.new(self.secret, message, hashlib.sha256).digest()
            # 格式: base64(username:timestamp:mac)
            token = f"{username}:{timestamp}:{base64.b64encode(mac).decode()}"
        else:
            # 用于向后兼容的旧格式（单用户）
            message = f"smtp-tunnel-auth:{timestamp}".encode()
            mac = hmac.new(self.secret, message, hashlib.sha256).digest()
            # 格式: base64(timestamp:mac)
            token = f"{timestamp}:{base64.b64encode(mac).decode()}"
        return base64.b64encode(token.encode()).decode()

    def verify_auth_token(self, token: str, max_age: int = 300) -> Tuple[bool, Optional[str]]:
        """
        验证认证令牌
        
        验证令牌的有效性，包括：
        1. 解码 Base64 令牌
        2. 解析令牌格式（支持新旧两种格式）
        3. 检查时间戳新鲜度（防止重放）
        4. 验证 HMAC 签名
        
        Args:
            token: Base64 编码的认证令牌
            max_age: 最大年龄（秒），默认 5 分钟
            
        Returns:
            Tuple[bool, Optional[str]]: (是否有效, 用户名)
                                         - 旧格式令牌的 username 为 None
        """
        try:
            decoded = base64.b64decode(token).decode()
            parts = decoded.split(':')

            if len(parts) == 3:
                # 新格式: username:timestamp:mac
                username, timestamp_str, mac_b64 = parts
                timestamp = int(timestamp_str)
            elif len(parts) == 2:
                # 旧格式: timestamp:mac（向后兼容）
                username = None
                timestamp_str, mac_b64 = parts
                timestamp = int(timestamp_str)
            else:
                return False, None

            # 检查时间戳新鲜度
            now = int(time.time())
            if abs(now - timestamp) > max_age:
                return False, None

            # 验证 HMAC（使用恒定时间比较防止时序攻击）
            expected_token = self.generate_auth_token(timestamp, username)
            if hmac.compare_digest(token, expected_token):
                return True, username
            return False, None
        except Exception:
            return False, None

    @staticmethod
    def verify_auth_token_multi_user(token: str, users: dict, max_age: int = 300) -> Tuple[bool, Optional[str]]:
        """
        针对多个用户验证认证令牌
        
        在多用户环境中验证令牌，支持两种用户数据格式：
        1. UserConfig 对象（包含 secret、whitelist、logging）
        2. 字符串（仅包含 secret）
        
        验证流程:
        1. 解码并解析令牌
        2. 检查时间戳新鲜度
        3. 查找用户
        4. 使用用户的密钥验证 HMAC
        
        Args:
            token: Base64 编码的认证令牌
            users: {username: UserConfig} 或 {username: secret_string} 字典
            max_age: 最大年龄（秒），默认 5 分钟
            
        Returns:
            Tuple[bool, Optional[str]]: (是否有效, 用户名)
        """
        try:
            decoded = base64.b64decode(token).decode()
            parts = decoded.split(':')

            if len(parts) != 3:
                logger.debug(f"认证: 令牌格式无效，得到 {len(parts)} 部分")
                return False, None

            username, timestamp_str, mac_b64 = parts
            timestamp = int(timestamp_str)

            # 检查时间戳新鲜度
            now = int(time.time())
            if abs(now - timestamp) > max_age:
                logger.debug(f"认证: 时间戳已过期。差值: {abs(now-timestamp)}s")
                return False, None

            # 查找用户
            if username not in users:
                logger.debug(f"认证: 未找到用户 '{username}'")
                return False, None

            user_data = users[username]
            if isinstance(user_data, UserConfig):
                secret = user_data.secret
            elif isinstance(user_data, dict):
                secret = user_data.get('secret', '')
            else:
                secret = str(user_data)

            # 使用用户的密钥验证 HMAC
            crypto = TunnelCrypto(secret)
            expected_token = crypto.generate_auth_token(timestamp, username)
            if hmac.compare_digest(token, expected_token):
                return True, username
            logger.debug(f"认证: 用户 '{username}' 的 HMAC 不匹配")
            return False, None
        except Exception as e:
            logger.warning(f"认证: 异常 - {e}")
            return False, None


# ============================================================================
# 流量整形
# ============================================================================

class TrafficShaper:
    """
    通过流量整形实现 DPI 规避:
    - 消息之间的随机延迟
    - 填充到标准大小
    - 偶尔发送虚拟消息
    """

    # 标准填充大小（常见的电子邮件附件大小）
    PAD_SIZES = [4096, 8192, 16384, 32768]

    def __init__(
        self,
        min_delay_ms: int = 50,
        max_delay_ms: int = 500,
        dummy_probability: float = 0.1
    ):
        """
        初始化流量整形器。

        参数:
            min_delay_ms: 消息之间的最小延迟
            max_delay_ms: 消息之间的最大延迟
            dummy_probability: 发送虚拟消息的概率
        """
        self.min_delay_ms = min_delay_ms
        self.max_delay_ms = max_delay_ms
        self.dummy_probability = dummy_probability

    async def delay(self):
        """添加随机延迟以模拟人类行为。"""
        delay_ms = random.randint(self.min_delay_ms, self.max_delay_ms)
        await asyncio.sleep(delay_ms / 1000.0)

    def pad_data(self, data: bytes) -> bytes:
        """
        将数据填充到下一个标准大小。
        填充格式: data_length (2 字节) + data + random_padding
        """
        data_len = len(data)

        # 查找下一个标准大小（需要 2 字节长度前缀的空间）
        total_needed = data_len + 2
        target_size = self.PAD_SIZES[-1]  # 默认为最大值
        for size in self.PAD_SIZES:
            if total_needed <= size:
                target_size = size
                break

        padding_len = target_size - total_needed
        padding = os.urandom(padding_len) if padding_len > 0 else b''

        # 格式: 长度前缀 + 数据 + 填充
        return struct.pack('>H', data_len) + data + padding

    @staticmethod
    def unpad_data(padded_data: bytes) -> bytes:
        """从数据中移除填充。"""
        if len(padded_data) < 2:
            return padded_data

        # 从前 2 字节读取数据长度
        data_len = struct.unpack('>H', padded_data[:2])[0]

        # 提取数据（跳过 2 字节长度前缀）
        return padded_data[2:2 + data_len]

    def should_send_dummy(self) -> bool:
        """确定是否应该发送虚拟消息。"""
        return random.random() < self.dummy_probability

    def generate_dummy_data(self, min_size: int = 100, max_size: int = 1000) -> bytes:
        """生成随机虚拟数据。"""
        size = random.randint(min_size, max_size)
        return os.urandom(size)


# ============================================================================
# SMTP 消息生成
# ============================================================================

class SMTPMessageGenerator:
    """
    生成逼真的 SMTP 消息以包装隧道数据。
    """

    # 逼真的主题行
    SUBJECTS = [
        "回复: 您的订单 #{order_id} 已发货",
        "发票附件 - 账户 #{account_id}",
        "会议纪要 - {date}",
        "转发: 您请求的文档",
        "周报 - 第 {week} 周",
        "回复: 关于项目的快速问题",
        "更新后的文件附件",
        "确认: 您在 {date} 的预约",
        "您的购买收据",
        "需要操作: 请审核",
        "转发: 重要更新",
        "回复: 跟进我们的对话",
    ]

    # 发件人域名（常见提供商）
    DOMAINS = [
        "gmail.com", "outlook.com", "yahoo.com", "protonmail.com",
        "icloud.com", "mail.com", "hotmail.com"
    ]

    # 用于逼真的 From 头部的名字
    FIRST_NAMES = [
        "张", "李", "王", "刘", "陈", "杨",
        "赵", "黄", "周", "吴", "徐", "孙"
    ]

    LAST_NAMES = [
        "伟", "芳", "娜", "敏", "静", "强",
        "磊", "洋", "艳", "杰", "勇", "军"
    ]

    # 纯文本部分的文本正文
    BODY_TEMPLATES = [
        "请查收附件中的文档。\n\n致以问候",
        "如讨论所述，这里是文件。\n\n谢谢",
        "附件是您请求的信息。\n\n致敬",
        "请审核附件。\n\n感谢",
        "这是文档。\n\n祝好",
    ]

    def __init__(self, from_domain: str = "example.com", to_domain: str = "example.org"):
        """
        初始化消息生成器。

        参数:
            from_domain: 发件人地址的域名
            to_domain: 收件人地址的域名
        """
        self.from_domain = from_domain
        self.to_domain = to_domain
        self._message_counter = 0

    def generate_message_id(self) -> str:
        """生成逼真的 Message-ID。"""
        random_part = os.urandom(8).hex()
        timestamp = int(time.time() * 1000) % 1000000
        return f"<{random_part}.{timestamp}@{self.from_domain}>"

    def generate_subject(self) -> str:
        """生成逼真的主题行。"""
        template = random.choice(self.SUBJECTS)
        now = datetime.now()
        return template.format(
            order_id=random.randint(10000, 99999),
            account_id=random.randint(1000, 9999),
            date=now.strftime("%m月%d日"),
            week=now.isocalendar()[1]
        )

    def generate_sender(self) -> Tuple[str, str]:
        """生成逼真的 From 名称和地址。"""
        first = random.choice(self.FIRST_NAMES)
        last = random.choice(self.LAST_NAMES)
        name = f"{first}{last}"

        # 生成电子邮件变体
        email_styles = [
            f"{first.lower()}.{last.lower()}",
            f"{first.lower()}{last.lower()}",
            f"{first[0].lower()}{last.lower()}",
            f"{first.lower()}{random.randint(1, 99)}",
        ]
        email = f"{random.choice(email_styles)}@{random.choice(self.DOMAINS)}"

        return name, email

    def generate_recipient(self) -> Tuple[str, str]:
        """生成逼真的 To 地址。"""
        first = random.choice(self.FIRST_NAMES)
        last = random.choice(self.LAST_NAMES)
        name = f"{first}{last}"
        email = f"{first.lower()}.{last.lower()}@{self.to_domain}"
        return name, email

    def generate_boundary(self) -> str:
        """生成 MIME 边界。"""
        return f"----=_Part_{os.urandom(6).hex()}"

    def wrap_tunnel_data(self, tunnel_data: bytes, filename: str = "document.dat") -> Tuple[str, str, str, str]:
        """
        将隧道数据包装在逼真的 MIME 电子邮件消息中。

        返回:
            (from_addr, to_addr, subject, message_body) 元组
        """
        from_name, from_addr = self.generate_sender()
        to_name, to_addr = self.generate_recipient()
        subject = self.generate_subject()
        message_id = self.generate_message_id()
        boundary = self.generate_boundary()

        # RFC 2822 格式的当前日期
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%a, %d %b %Y %H:%M:%S %z")

        # Base64 编码隧道数据（根据 RFC 2045，每行 76 个字符）
        b64_data = base64.b64encode(tunnel_data).decode('ascii')
        b64_lines = [b64_data[i:i+76] for i in range(0, len(b64_data), 76)]
        b64_formatted = '\r\n'.join(b64_lines)

        # 构建 MIME 消息
        body_text = random.choice(self.BODY_TEMPLATES)

        message = f"""From: {from_name} <{from_addr}>
To: {to_name} <{to_addr}>
Subject: {subject}
Date: {date_str}
Message-ID: {message_id}
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="{boundary}"

--{boundary}
Content-Type: text/plain; charset=utf-8
Content-Transfer-Encoding: 7bit

{body_text}

--{boundary}
Content-Type: application/octet-stream
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="{filename}"

{b64_formatted}
--{boundary}--"""

        # 转换为 CRLF 行尾
        message = message.replace('\n', '\r\n')


# ============================================================================
# 配置管理
# ============================================================================

import yaml  # 用于 YAML 配置文件解析
from dataclasses import dataclass  # 用于数据类
from typing import Any, Dict, List, Optional, Union  # 用于类型注解


@dataclass
class ServerConfig:
    """服务器配置数据类。"""
    host: str = "0.0.0.0"
    port: int = 587
    hostname: str = "mail.example.com"
    cert_file: str = "server.crt"
    key_file: str = "server.key"
    users_file: str = "users.yaml"
    log_users: bool = True


@dataclass
class UserConfig:
    """用户配置数据类。"""
    username: str
    secret: str
    whitelist: List[str] = None
    logging: bool = True

    def __post_init__(self):
        if self.whitelist is None:
            self.whitelist = []


@dataclass
class ClientConfig:
    """客户端配置数据类。"""
    server_host: str
    server_port: int = 587
    socks_port: int = 1080
    socks_host: str = "127.0.0.1"
    username: str = None
    secret: str = None
    ca_cert: str = None


class IPWhitelist:
    """IP 白名单管理类。"""
    
    def __init__(self, whitelist: List[str] = None):
        """
        初始化 IP 白名单
        
        Args:
            whitelist: IP 地址列表，支持以下格式：
                - 单个 IP 地址（如 "192.168.1.1"）
                - CIDR 表示法（如 "192.168.1.0/24"）
                如果为 None 或空列表，则允许所有 IP 访问
        """
        self.whitelist = whitelist or []
    
    def is_allowed(self, ip: str) -> bool:
        """
        检查 IP 是否在白名单中
        
        Args:
            ip: 要检查的 IP 地址字符串
            
        Returns:
            bool: 如果 IP 在白名单中或白名单为空则返回 True，否则返回 False
        """
        if not self.whitelist:
            return True
        
        for allowed_ip in self.whitelist:
            if self._match_ip(ip, allowed_ip):
                return True
        return False
    
    def _match_ip(self, ip: str, pattern: str) -> bool:
        """
        检查 IP 是否匹配模式
        
        支持两种匹配方式：
        1. 精确匹配：IP 地址完全相同
        2. CIDR 匹配：使用网络掩码进行子网匹配
        
        Args:
            ip: 要检查的 IP 地址字符串
            pattern: 匹配模式，可以是 IP 地址或 CIDR 表示法
            
        Returns:
            bool: 如果 IP 匹配模式则返回 True，否则返回 False
        """
        # 精确匹配
        if ip == pattern:
            return True
        
        # CIDR 匹配
        if '/' in pattern:
            try:
                from ipaddress import ip_network, ip_address
                network = ip_network(pattern, strict=False)
                return ip_address(ip) in network
            except ImportError:
                # 如果没有 ipaddress 模块，只做简单匹配
                pass
        
        return False


def load_config(config_file: str) -> Dict[str, Any]:
    """
    加载配置文件
    
    从 YAML 格式的配置文件中加载配置数据
    
    Args:
        config_file: 配置文件路径
        
    Returns:
        Dict[str, Any]: 配置数据字典，如果文件不存在或格式错误则返回空字典
    """
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as e:
        logger.warning(f"配置文件格式错误: {e}")
        return {}


def save_config(config_file: str, config_data: Dict[str, Any]) -> bool:
    """
    保存配置文件
    
    将配置数据保存到 YAML 格式的配置文件中
    
    Args:
        config_file: 配置文件路径
        config_data: 要保存的配置数据字典
        
    Returns:
        bool: 保存成功返回 True，失败返回 False
    """
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
        return True
    except Exception as e:
        logger.error(f"保存配置文件失败: {e}")
        return False


def load_users(users_file: str) -> Dict[str, Union[UserConfig, str]]:
    """
    加载用户配置
    
    从 YAML 格式的用户配置文件中加载用户数据
    支持两种用户配置格式：
    1. 简化格式：username: secret_string
    2. 完整格式：username: {secret: xxx, whitelist: [...], logging: true/false}
    
    Args:
        users_file: 用户配置文件路径
        
    Returns:
        Dict[str, Union[UserConfig, str]]: 用户配置字典
            - 简化格式：值为字符串（密钥）
            - 完整格式：值为 UserConfig 对象
            如果文件不存在或格式错误则返回空字典
    """
    try:
        with open(users_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        if not data or 'users' not in data or data['users'] is None:
            return {}
        
        users = {}
        for username, user_data in data['users'].items():
            if isinstance(user_data, str):
                # 简化格式：只有密钥
                users[username] = user_data
            elif isinstance(user_data, dict):
                # 完整格式：包含配置
                whitelist = user_data.get('whitelist', [])
                logging = user_data.get('logging', True)
                secret = user_data.get('secret', '')
                users[username] = UserConfig(
                    username=username,
                    secret=secret,
                    whitelist=whitelist,
                    logging=logging
                )
        
        return users
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as e:
        logger.warning(f"用户配置文件格式错误: {e}")
        return {}
    except Exception as e:
        logger.warning(f"加载用户配置失败: {e}")
        return {}


def save_users(users_file: str, users: Dict[str, Union[UserConfig, str]]) -> bool:
    """
    保存用户配置
    
    将用户配置数据保存到 YAML 格式的配置文件中
    支持两种用户配置格式：
    1. 简化格式：username: secret_string
    2. 完整格式：username: {secret: xxx, whitelist: [...], logging: true/false}
    
    Args:
        users_file: 用户配置文件路径
        users: 用户配置字典
            - 简化格式：值为字符串（密钥）
            - 完整格式：值为 UserConfig 对象
            
    Returns:
        bool: 保存成功返回 True，失败返回 False
    """
    try:
        data = {'users': {}}
        
        for username, user_data in users.items():
            if isinstance(user_data, str):
                # 简化格式
                data['users'][username] = user_data
            elif isinstance(user_data, UserConfig):
                # 完整格式
                data['users'][username] = {
                    'secret': user_data.secret,
                    'whitelist': user_data.whitelist,
                    'logging': user_data.logging
                }
        
        with open(users_file, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        return True
    except Exception as e:
        logger.error(f"保存用户配置失败: {e}")
        return False
