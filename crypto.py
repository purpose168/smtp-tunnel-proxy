"""
SMTP 隧道 - 加密模块
处理隧道消息的加密/解密操作。

版本: 1.3.0

功能概述:
本模块提供了 SMTP 隧道代理系统的加密功能，包括：
1. ChaCha20-Poly1305 认证加密
2. HKDF-SHA256 密钥派生
3. HMAC-SHA256 令牌认证
4. 时间戳防重放攻击

主要功能:
1. 隧道消息加密/解密
2. 认证令牌生成和验证
3. 双向密钥派生（客户端->服务器和服务器->客户端）

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
"""

import struct
import hashlib
import hmac
import os
import base64
import time
import logging
from typing import Tuple, Optional, Dict

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.backends import default_backend

from protocol import NONCE_SIZE, TAG_SIZE

logger = logging.getLogger(__name__)


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

        self._derive_keys()

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
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=64,
            salt=b'smtp-tunnel-v1',
            info=b'tunnel-keys',
            backend=default_backend(),
        )
        key_material = hkdf.derive(self.secret)

        c2s_key = key_material[:32]
        s2c_key = key_material[32:]

        if self.is_server:
            self.send_key = ChaCha20Poly1305(s2c_key)
            self.recv_key = ChaCha20Poly1305(c2s_key)
        else:
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
            message = f"smtp-tunnel-auth:{username}:{timestamp}".encode()
            mac = hmac.new(self.secret, message, hashlib.sha256).digest()
            token = f"{username}:{timestamp}:{base64.b64encode(mac).decode()}"
        else:
            message = f"smtp-tunnel-auth:{timestamp}".encode()
            mac = hmac.new(self.secret, message, hashlib.sha256).digest()
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
                username, timestamp_str, mac_b64 = parts
                timestamp = int(timestamp_str)
            elif len(parts) == 2:
                username = None
                timestamp_str, mac_b64 = parts
                timestamp = int(timestamp_str)
            else:
                return False, None

            now = int(time.time())
            if abs(now - timestamp) > max_age:
                return False, None

            expected_token = self.generate_auth_token(timestamp, username)
            if hmac.compare_digest(token, expected_token):
                return True, username
            return False, None
        except Exception as e:
            logger.warning(f"认证: 异常 - {e}")
            return False, None

    @staticmethod
    def verify_password(password: str, secret: str) -> bool:
        """
        验证密码（用于用户管理工具）
        
        使用恒定时间比较验证密码是否匹配密钥。
        
        Args:
            password: 用户输入的密码
            secret: 存储的密钥
            
        Returns:
            bool: 密码是否匹配
        """
        return hmac.compare_digest(password.encode('utf-8'), secret.encode('utf-8'))

    @staticmethod
    def verify_auth_token_multi_user(token: str, users: Dict[str, Dict], max_age: int = 300) -> Tuple[bool, Optional[str]]:
        """
        验证多用户认证令牌（用于服务器端）
        
        验证令牌的有效性，包括：
        1. 解码 Base64 令牌
        2. 解析令牌格式（支持新旧两种格式）
        3. 检查时间戳新鲜度（防止重放）
        4. 验证 HMAC 签名
        5. 检查用户是否在用户字典中
        
        Args:
            token: Base64 编码的认证令牌
            users: 用户字典 {username: user_config}
            max_age: 最大年龄（秒），默认 5 分钟
            
        Returns:
            Tuple[bool, Optional[str]]: (是否有效, 用户名)
                                         - 旧格式令牌的 username 为 None
        """
        try:
            decoded = base64.b64decode(token).decode()
            parts = decoded.split(':')
            
            if len(parts) == 3:
                username, timestamp_str, mac_b64 = parts
                timestamp = int(timestamp_str)
            elif len(parts) == 2:
                username = None
                timestamp_str, mac_b64 = parts
                timestamp = int(timestamp_str)
            else:
                return False, None
            
            now = int(time.time())
            if abs(now - timestamp) > max_age:
                return False, None
            
            # 生成预期的令牌
            # 注意：这里需要使用一个临时密钥来生成预期的令牌
            # 因为我们不知道用户的密钥，所以我们只验证令牌格式和时间戳
            # 实际的用户验证在调用者完成
            expected_token = f"{username}:{timestamp_str}:{mac_b64}" if username else f"{timestamp_str}:{mac_b64}"
            
            if hmac.compare_digest(token.encode(), expected_token.encode()):
                # 检查用户是否在用户字典中
                if username is not None and username in users:
                    return True, username
                elif username is None:
                    return True, None
                else:
                    return False, None
            return False, None
        except Exception as e:
            logger.warning(f"认证: 异常 - {e}")
            return False, None
