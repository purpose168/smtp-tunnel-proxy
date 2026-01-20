"""
SMTP 隧道 - 通用协议和工具
客户端和服务端共享的组件

版本: 1.3.0
"""

import struct
import asyncio
import random
import hashlib
import hmac
import os
import base64
import time
from enum import IntEnum
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict
from datetime import datetime, timezone

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.backends import default_backend


# ============================================================================
# 协议常量
# ============================================================================

PROTOCOL_VERSION = 1  # 协议版本号
MAX_PAYLOAD_SIZE = 65535  # 最大负载大小
NONCE_SIZE = 12  # 随机数（nonce）大小
TAG_SIZE = 16  # 认证标签大小

# 消息类型枚举
class MsgType(IntEnum):
    DATA = 0x01           # 隧道数据
    CONNECT = 0x02        # 打开新通道（SOCKS CONNECT）
    CONNECT_OK = 0x03     # 连接已建立
    CONNECT_FAIL = 0x04   # 连接失败
    CLOSE = 0x05          # 关闭通道
    KEEPALIVE = 0x06      # 保持连接活跃
    KEEPALIVE_ACK = 0x07  # 保活响应


# ============================================================================
# 隧道协议消息
# ============================================================================

@dataclass
class TunnelMessage:
    """
    用于多路复用隧道流量的二进制协议

    线路格式（加密前）:
    ┌─────────┬────────────┬────────────┬──────────────┬─────────────┐
    │ 版本号  │ 消息类型   │ 通道ID     │ 负载长度     │    负载     │
    │ 1 字节  │  1 字节    │  2 字节    │  2 字节      │   可变长度   │
    └─────────┴────────────┴────────────┴──────────────┴─────────────┘
    """
    msg_type: MsgType  # 消息类型
    channel_id: int  # 通道ID
    payload: bytes  # 负载数据

    HEADER_SIZE = 6  # 头部大小：1(版本) + 1(类型) + 2(通道ID) + 2(负载长度)

    def serialize(self) -> bytes:
        """将消息序列化为字节"""
        # 使用大端序打包头部：版本、类型、通道ID、负载长度
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
        返回: (消息对象, 剩余字节)
        """
        if len(data) < cls.HEADER_SIZE:
            raise ValueError("数据不足，无法解析头部")

        # 解包头部信息
        version, msg_type, channel_id, payload_len = struct.unpack(
            '>BBHH', data[:cls.HEADER_SIZE]
        )

        # 验证协议版本
        if version != PROTOCOL_VERSION:
            raise ValueError(f"未知的协议版本: {version}")

        # 检查数据是否完整
        total_len = cls.HEADER_SIZE + payload_len
        if len(data) < total_len:
            raise ValueError("数据不足，无法解析负载")

        # 提取负载数据和剩余字节
        payload = data[cls.HEADER_SIZE:total_len]
        remaining = data[total_len:]

        return cls(MsgType(msg_type), channel_id, payload), remaining

    @classmethod
    def data(cls, channel_id: int, data: bytes) -> 'TunnelMessage':
        """创建数据消息"""
        return cls(MsgType.DATA, channel_id, data)

    @classmethod
    def connect(cls, channel_id: int, host: str, port: int) -> 'TunnelMessage':
        """创建连接消息"""
        # 负载格式: 主机长度(1字节) + 主机名 + 端口(2字节)
        host_bytes = host.encode('utf-8')
        payload = struct.pack('>B', len(host_bytes)) + host_bytes + struct.pack('>H', port)
        return cls(MsgType.CONNECT, channel_id, payload)

    @classmethod
    def connect_ok(cls, channel_id: int) -> 'TunnelMessage':
        """创建连接成功消息"""
        return cls(MsgType.CONNECT_OK, channel_id, b'')

    @classmethod
    def connect_fail(cls, channel_id: int, reason: str = '') -> 'TunnelMessage':
        """创建连接失败消息"""
        return cls(MsgType.CONNECT_FAIL, channel_id, reason.encode('utf-8'))

    @classmethod
    def close(cls, channel_id: int) -> 'TunnelMessage':
        """创建关闭通道消息"""
        return cls(MsgType.CLOSE, channel_id, b'')

    @classmethod
    def keepalive(cls) -> 'TunnelMessage':
        """创建保活消息"""
        return cls(MsgType.KEEPALIVE, 0, b'')

    @classmethod
    def keepalive_ack(cls) -> 'TunnelMessage':
        """创建保活响应消息"""
        return cls(MsgType.KEEPALIVE_ACK, 0, b'')

    def parse_connect(self) -> Tuple[str, int]:
        """解析连接消息负载，获取主机和端口"""
        if self.msg_type != MsgType.CONNECT:
            raise ValueError("不是连接消息")
        host_len = self.payload[0]
        host = self.payload[1:1+host_len].decode('utf-8')
        port = struct.unpack('>H', self.payload[1+host_len:3+host_len])[0]
        return host, port


# ============================================================================
# 加密模块
# ============================================================================

class TunnelCrypto:
    """
    处理隧道消息的加密/解密
    使用 ChaCha20-Poly1305 进行认证加密
    使用 HKDF 从预共享密钥派生密钥
    """

    def __init__(self, secret: str, is_server: bool = False):
        """
        使用预共享密钥初始化加密模块

        参数:
            secret: 预共享密钥字符串
            is_server: True 表示服务端，False 表示客户端
        """
        self.secret = secret.encode('utf-8')  # 将密钥转换为字节
        self.is_server = is_server

        # 为客户端->服务端和服务端->客户端派生独立的密钥
        self._derive_keys()

        # 用于生成随机数的序列号（防止重放攻击）
        self.send_seq = 0  # 发送序列号
        self.recv_seq = 0  # 接收序列号

    def _derive_keys(self):
        """使用 HKDF 从密钥派生加密密钥"""
        # 派生主密钥
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=64,  # 每个方向 32 字节
            salt=b'smtp-tunnel-v1',
            info=b'tunnel-keys',
            backend=default_backend(),
        )
        key_material = hkdf.derive(self.secret)

        # 分割为客户端->服务端和服务端->客户端密钥
        c2s_key = key_material[:32]  # 客户端到服务端密钥
        s2c_key = key_material[32:]  # 服务端到客户端密钥

        # 根据角色分配发送和接收密钥
        if self.is_server:
            # 服务端使用 s2c_key 发送，c2s_key 接收
            self.send_key = ChaCha20Poly1305(s2c_key)
            self.recv_key = ChaCha20Poly1305(c2s_key)
        else:
            # 客户端使用 c2s_key 发送，s2c_key 接收
            self.send_key = ChaCha20Poly1305(c2s_key)
            self.recv_key = ChaCha20Poly1305(s2c_key)

    def encrypt(self, plaintext: bytes) -> bytes:
        """
        使用认证加密加密数据
        返回: 随机数(12字节) + 密文 + 认证标签(16字节)
        """
        # 从序列号和随机数生成 nonce
        nonce = struct.pack('>Q', self.send_seq) + os.urandom(4)
        self.send_seq += 1

        # 加密数据（ChaCha20-Poly1305 自动附加认证标签）
        ciphertext = self.send_key.encrypt(nonce, plaintext, None)
        return nonce + ciphertext

    def decrypt(self, data: bytes) -> bytes:
        """
        解密并验证数据
        输入: 随机数(12字节) + 密文 + 认证标签(16字节)
        返回: 明文
        """
        if len(data) < NONCE_SIZE + TAG_SIZE:
            raise ValueError("数据太短")

        nonce = data[:NONCE_SIZE]
        ciphertext = data[NONCE_SIZE:]

        # 解密并验证（如果验证失败会抛出异常）
        plaintext = self.recv_key.decrypt(nonce, ciphertext, None)
        self.recv_seq += 1

        return plaintext

    def generate_auth_token(self, timestamp: int, username: str = None) -> str:
        """
        生成用于 SMTP AUTH 的认证令牌
        使用 HMAC-SHA256 和时间戳防止重放攻击

        参数:
            timestamp: Unix 时间戳
            username: 可选的用户名（用于多用户模式）

        返回:
            Base64 编码的令牌
        """
        if username:
            # 新格式：包含用户名
            message = f"smtp-tunnel-auth:{username}:{timestamp}".encode()
            mac = hmac.new(self.secret, message, hashlib.sha256).digest()
            # 格式: base64(用户名:时间戳:MAC)
            token = f"{username}:{timestamp}:{base64.b64encode(mac).decode()}"
        else:
            # 旧格式：向后兼容
            message = f"smtp-tunnel-auth:{timestamp}".encode()
            mac = hmac.new(self.secret, message, hashlib.sha256).digest()
            # 格式: base64(时间戳:MAC)
            token = f"{timestamp}:{base64.b64encode(mac).decode()}"
        return base64.b64encode(token.encode()).decode()

    def verify_auth_token(self, token: str, max_age: int = 300) -> Tuple[bool, Optional[str]]:
        """
        验证认证令牌

        参数:
            token: Base64 编码的认证令牌
            max_age: 最大有效期（秒，默认 5 分钟）

        返回:
            (是否有效, 用户名) 元组 - 旧格式令牌的用户名为 None
        """
        try:
            # 解码令牌
            decoded = base64.b64decode(token).decode()
            parts = decoded.split(':')

            if len(parts) == 3:
                # 新格式: 用户名:时间戳:MAC
                username, timestamp_str, mac_b64 = parts
                timestamp = int(timestamp_str)
            elif len(parts) == 2:
                # 旧格式: 时间戳:MAC
                username = None
                timestamp_str, mac_b64 = parts
                timestamp = int(timestamp_str)
            else:
                return False, None

            # 检查时间戳是否在有效期内
            now = int(time.time())
            if abs(now - timestamp) > max_age:
                return False, None

            # 验证 HMAC
            expected_token = self.generate_auth_token(timestamp, username)
            if hmac.compare_digest(token, expected_token):
                return True, username
            return False, None
        except Exception:
            return False, None

    @staticmethod
    def verify_auth_token_multi_user(token: str, users: dict, max_age: int = 300) -> Tuple[bool, Optional[str]]:
        """
        验证多用户模式的认证令牌

        参数:
            token: Base64 编码的认证令牌
            users: {用户名: UserConfig} 或 {用户名: 密钥字符串} 字典
            max_age: 最大有效期（秒，默认 5 分钟）

        返回:
            (是否有效, 用户名) 元组
        """
        import logging
        logger = logging.getLogger('smtp-tunnel')
        try:
            # 解码令牌
            decoded = base64.b64decode(token).decode()
            parts = decoded.split(':')

            if len(parts) != 3:
                logger.debug(f"认证: 令牌格式无效，获得 {len(parts)} 个部分")
                return False, None

            username, timestamp_str, mac_b64 = parts
            timestamp = int(timestamp_str)

            # 检查时间戳是否在有效期内
            now = int(time.time())
            if abs(now - timestamp) > max_age:
                logger.debug(f"认证: 时间戳已过期。差值: {abs(now-timestamp)}秒")
                return False, None

            # 查找用户
            if username not in users:
                logger.debug(f"认证: 用户 '{username}' 未找到")
                return False, None

            # 获取用户密钥
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
    - 偶尔发送虚假消息
    """

    # 标准填充大小（常见的邮件附件大小）
    PAD_SIZES = [4096, 8192, 16384, 32768]

    def __init__(
        self,
        min_delay_ms: int = 50,
        max_delay_ms: int = 500,
        dummy_probability: float = 0.1
    ):
        """
        初始化流量整形器

        参数:
            min_delay_ms: 消息之间的最小延迟（毫秒）
            max_delay_ms: 消息之间的最大延迟（毫秒）
            dummy_probability: 发送虚假消息的概率
        """
        self.min_delay_ms = min_delay_ms
        self.max_delay_ms = max_delay_ms
        self.dummy_probability = dummy_probability

    async def delay(self):
        """添加随机延迟以模拟人类行为"""
        delay_ms = random.randint(self.min_delay_ms, self.max_delay_ms)
        await asyncio.sleep(delay_ms / 1000.0)

    def pad_data(self, data: bytes) -> bytes:
        """
        将数据填充到下一个标准大小
        填充格式: 数据长度(2字节) + 数据 + 随机填充
        """
        data_len = len(data)

        # 找到下一个标准大小（需要为 2 字节长度前缀留出空间）
        total_needed = data_len + 2
        target_size = self.PAD_SIZES[-1]  # 默认使用最大值
        for size in self.PAD_SIZES:
            if total_needed <= size:
                target_size = size
                break

        # 计算填充长度并生成随机填充
        padding_len = target_size - total_needed
        padding = os.urandom(padding_len) if padding_len > 0 else b''

        # 格式: 长度前缀 + 数据 + 填充
        return struct.pack('>H', data_len) + data + padding

    @staticmethod
    def unpad_data(padded_data: bytes) -> bytes:
        """从数据中移除填充"""
        if len(padded_data) < 2:
            return padded_data

        # 从前 2 字节读取数据长度
        data_len = struct.unpack('>H', padded_data[:2])[0]

        # 提取数据（跳过 2 字节长度前缀）
        return padded_data[2:2 + data_len]

    def should_send_dummy(self) -> bool:
        """判断是否应该发送虚假消息"""
        return random.random() < self.dummy_probability

    def generate_dummy_data(self, min_size: int = 100, max_size: int = 1000) -> bytes:
        """生成随机虚假数据"""
        size = random.randint(min_size, max_size)
        return os.urandom(size)


# ============================================================================
# SMTP 消息生成
# ============================================================================

class SMTPMessageGenerator:
    """
    生成逼真的 SMTP 消息来包装隧道数据
    """

    # 逼真的邮件主题
    SUBJECTS = [
        "回复: 您的订单 #{order_id} 已发货",
        "发票附件 - 账户 #{account_id}",
        "会议纪要 - {date}",
        "转发: 您请求的文档",
        "周报 - 第 {week} 周",
        "回复: 关于项目的快速问题",
        "更新后的文件已附上",
        "确认: 您在 {date} 的预约",
        "您的购买收据",
        "需要采取行动: 请审阅",
        "转发: 重要更新",
        "回复: 跟进我们的对话",
    ]

    # 发件人域名（常见服务提供商）
    DOMAINS = [
        # 国际主流邮箱
        "gmail.com", "outlook.com", "yahoo.com", "protonmail.com",
        "icloud.com", "mail.com", "hotmail.com", "aol.com",
        "zoho.com", "yandex.com", "mail.ru", "gmx.com",
        "fastmail.com", "tutanota.com", "hushmail.com",
        
        # 中国主流邮箱
        "qq.com", "163.com", "126.com", "sina.com",
        "sohu.com", "aliyun.com", "foxmail.com",
       
        # 其他常见邮箱
        "163.net", "yeah.net", "vip.qq.com", "vip.163.com",
        "vip.sina.com", "live.com", "msn.com", "passport.com"
    ]

    # 用于逼真发件人字段的名字
    FIRST_NAMES = [
        # 翻译后的英文名字
        "约翰", "简", "迈克尔", "莎拉", "大卫", "艾米丽",
        "詹姆斯", "艾玛", "罗伯特", "奥利维亚", "威廉", "索菲亚",
        
        # 中文名字
        "张伟", "王芳", "李娜", "刘洋", "陈静",
        "杨强", "赵敏", "黄磊", "周婷", "吴刚",
        "徐明", "孙丽", "马超", "朱燕", "胡勇",
        "郭华", "林涛", "何娟", "高峰", "罗杰",
        "梁敏", "宋强", "郑芳", "谢明", "韩磊",
        "唐静", "冯涛", "于强", "董芳", "萧然",
        "程明", "曹丽", "袁强", "邓芳", "许杰",
        "傅静", "沈涛", "曾强", "彭芳", "吕明",
        "苏静", "卢强", "蒋芳", "蔡杰", "贾明",
        "丁静", "魏涛", "薛芳", "叶强", "阎明",
        "余静", "潘强", "杜芳", "戴杰", "夏明",
        "钟华", "田敏", "任强", "姜芳", "范杰",
        "方静", "石涛", "姚强", "谭芳", "廖明",
        "邹静", "熊强", "金芳", "陆杰", "郝明",
        "孔静", "白涛", "崔强", "康芳", "毛杰",
        "邱静", "秦涛", "江强", "史芳", "顾明",
        "侯静", "邵涛", "孟强", "龙芳", "万杰",
        "段静", "雷涛", "钱强", "汤芳", "尹明",
        "黎静", "易强", "常芳", "武杰", "乔明",
        "贺静", "赖涛", "龚强", "文芳", "庞明"
    ]

    # 纯文本部分的邮件正文模板
    BODY_TEMPLATES = [
        "请查收附件文档。\n\n致以诚挚的问候",
        "如讨论所述，这里是相关文件。\n\n谢谢",
        "附件是您请求的信息。\n\n此致",
        "请审阅附件。\n\n谢谢",
        "这里是文档。\n\n祝好",
    ]

    def __init__(self, from_domain: str = "example.com", to_domain: str = "example.org"):
        """
        初始化消息生成器

        参数:
            from_domain: 发件人地址的域名
            to_domain: 收件人地址的域名
        """
        self.from_domain = from_domain
        self.to_domain = to_domain
        self._message_counter = 0

    def generate_message_id(self) -> str:
        """生成逼真的消息 ID"""
        random_part = os.urandom(8).hex()
        timestamp = int(time.time() * 1000) % 1000000
        return f"<{random_part}.{timestamp}@{self.from_domain}>"

    def generate_subject(self) -> str:
        """生成逼真的邮件主题"""
        template = random.choice(self.SUBJECTS)
        now = datetime.now()
        return template.format(
            order_id=random.randint(10000, 99999),
            account_id=random.randint(1000, 9999),
            date=now.strftime("%B %d"),
            week=now.isocalendar()[1]
        )

    def generate_sender(self) -> Tuple[str, str]:
        """生成逼真的发件人姓名和地址"""
        first = random.choice(self.FIRST_NAMES)
        last = random.choice(self.LAST_NAMES)
        name = f"{first} {last}"

        # 生成邮件地址变体
        email_styles = [
            f"{first.lower()}.{last.lower()}",
            f"{first.lower()}{last.lower()}",
            f"{first[0].lower()}{last.lower()}",
            f"{first.lower()}{random.randint(1, 99)}",
        ]
        email = f"{random.choice(email_styles)}@{random.choice(self.DOMAINS)}"

        return name, email

    def generate_recipient(self) -> Tuple[str, str]:
        """生成逼真的收件人地址"""
        first = random.choice(self.FIRST_NAMES)
        last = random.choice(self.LAST_NAMES)
        name = f"{first} {last}"
        email = f"{first.lower()}.{last.lower()}@{self.to_domain}"
        return name, email

    def generate_boundary(self) -> str:
        """生成 MIME 边界"""
        return f"----=_Part_{os.urandom(6).hex()}"

    def wrap_tunnel_data(self, tunnel_data: bytes, filename: str = "document.dat") -> Tuple[str, str, str, str]:
        """
        将隧道数据包装在逼真的 MIME 邮件消息中

        返回:
            (发件人地址, 收件人地址, 主题, 消息正文) 元组
        """
        from_name, from_addr = self.generate_sender()
        to_name, to_addr = self.generate_recipient()
        subject = self.generate_subject()
        message_id = self.generate_message_id()
        boundary = self.generate_boundary()

        # 当前日期（RFC 2822 格式）
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%a, %d %b %Y %H:%M:%S %z")

        # Base64 编码隧道数据（根据 RFC 2045 使用 76 字符行宽）
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

        # 转换为 CRLF 行结束符
        message = message.replace('\n', '\r\n')

        return from_addr, to_addr, subject, message

    def extract_tunnel_data(self, message: str) -> Optional[bytes]:
        """
        从 MIME 邮件消息中提取隧道数据

        参数:
            message: 邮件消息内容

        返回:
            隧道数据，如果提取失败则返回 None
        """
        try:
            import re
            from email import message_from_string
            from email.policy import default

            # 解析邮件消息
            email_msg = message_from_string(message, policy=default)

            # 查找附件
            for part in email_msg.walk():
                # 检查是否为附件
                if part.get_content_disposition() == 'attachment':
                    # 获取附件内容
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload

            return None
        except Exception:
            return None


# ============================================================================
# SMTP 状态管理
# ============================================================================

class SMTPState:
    """
    SMTP 协议状态机
    跟踪 SMTP 会话的当前状态
    """

    def __init__(self):
        self.state = 'INIT'  # 初始状态
        self.buffer = []  # 消息缓冲区
        self.current_message = None  # 当前正在处理的消息

    def transition(self, new_state: str):
        """转换到新状态"""
        self.state = new_state

    def is_state(self, state: str) -> bool:
        """检查是否处于指定状态"""
        return self.state == state


# ============================================================================
# 配置类
# ============================================================================

@dataclass
class UserConfig:
    """用户配置"""
    username: str  # 用户名
    secret: str  # 密钥
    whitelist: List[str] = None  # IP 白名单
    logging: bool = True  # 是否记录日志

    def __post_init__(self):
        if self.whitelist is None:
            self.whitelist = []


@dataclass
class StealthConfig:
    """隐蔽/流量整形配置"""
    min_delay_ms: int = 50  # 最小延迟（毫秒）
    max_delay_ms: int = 500  # 最大延迟（毫秒）
    pad_to_sizes: List[int] = None  # 填充大小列表
    dummy_message_probability: float = 0.1  # 虚假消息概率

    def __post_init__(self):
        if self.pad_to_sizes is None:
            self.pad_to_sizes = [4096, 8192, 16384]


@dataclass
class ServerConfig:
    """服务端配置"""
    host: str = '0.0.0.0'  # 监听地址
    port: int = 25  # 监听端口
    hostname: str = 'mail.example.com'  # 服务器主机名
    cert_file: str = 'server.crt'  # 证书文件路径
    key_file: str = 'server.key'  # 私钥文件路径
    users_file: str = 'users.yaml'  # 用户文件路径
    log_users: bool = True  # 是否记录用户日志
    secret: str = ''  # 密钥
    users: Dict[str, UserConfig] = None  # 用户字典
    stealth_enabled: bool = False  # 是否启用隐蔽模式
    stealth: StealthConfig = None  # 隐蔽配置

    def __post_init__(self):
        if self.users is None:
            self.users = {}
        if self.stealth is None:
            self.stealth = StealthConfig()


class IPWhitelist:
    """
    IP 地址白名单管理
    支持单个 IP 和 CIDR 范围
    """

    def __init__(self, entries: List[str] = None):
        """
        初始化白名单

        参数:
            entries: IP 地址或 CIDR 范围列表
        """
        self.entries = entries or []
        self._parsed_entries = self._parse_entries()

    def _parse_entries(self):
        """解析白名单条目"""
        parsed = []
        for entry in self.entries:
            try:
                import ipaddress
                # 尝试解析为网络（CIDR）
                if '/' in entry:
                    parsed.append(ipaddress.ip_network(entry, strict=False))
                else:
                    # 单个 IP 地址
                    parsed.append(ipaddress.ip_address(entry))
            except ValueError:
                # 无效的 IP 地址，跳过
                continue
        return parsed

    def is_allowed(self, ip: str) -> bool:
        """
        检查 IP 地址是否在白名单中

        参数:
            ip: 要检查的 IP 地址

        返回:
            True 如果 IP 在白名单中或白名单为空
        """
        # 如果白名单为空，允许所有 IP
        if not self.entries:
            return True

        try:
            import ipaddress
            addr = ipaddress.ip_address(ip)

            # 检查是否匹配任何条目
            for entry in self._parsed_entries:
                if isinstance(entry, ipaddress.IPv4Network) or isinstance(entry, ipaddress.IPv6Network):
                    # 网络范围
                    if addr in entry:
                        return True
                else:
                    # 单个 IP 地址
                    if addr == entry:
                        return True

            return False
        except ValueError:
            # 无效的 IP 地址
            return False

    def __bool__(self):
        """如果白名单有条目（激活状态）则返回 True"""
        return bool(self.entries)


@dataclass
class ClientConfig:
    """客户端配置"""
    server_host: str = 'localhost'  # 服务器地址
    server_port: int = 587  # 服务器端口
    socks_port: int = 1080  # SOCKS 代理端口
    socks_host: str = '127.0.0.1'  # SOCKS 代理地址
    username: str = ''  # 多用户认证的用户名
    secret: str = ''  # 密钥


def load_config(path: str) -> dict:
    """
    从 YAML 文件加载配置

    参数:
        path: 配置文件路径

    返回:
        配置字典
    """
    import yaml
    with open(path, 'r') as f:
        return yaml.safe_load(f) or {}


def load_users(path: str) -> Dict[str, UserConfig]:
    """
    从 YAML 文件加载用户

    参数:
        path: users.yaml 文件路径

    返回:
        {用户名: UserConfig} 字典
    """
    import yaml

    try:
        with open(path, 'r') as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}

    users = {}
    users_data = data.get('users', {})

    for username, user_data in users_data.items():
        if isinstance(user_data, dict):
            # 完整格式
            users[username] = UserConfig(
                username=username,
                secret=user_data.get('secret', ''),
                whitelist=user_data.get('whitelist', []),
                logging=user_data.get('logging', True)
            )
        elif isinstance(user_data, str):
            # 简单格式: 用户名: 密钥
            users[username] = UserConfig(
                username=username,
                secret=user_data,
                whitelist=[],
                logging=True
            )

    return users


def save_users(path: str, users: Dict[str, UserConfig]):
    """
    将用户保存到 YAML 文件

    参数:
        path: users.yaml 文件路径
        users: {用户名: UserConfig} 字典
    """
    lines = ["# SMTP 隧道用户", "# 由 smtp-tunnel-adduser 管理", "", "users:"]

    for username, user in users.items():
        lines.append(f"  {username}:")
        lines.append(f"    secret: {user.secret}")
        lines.append(f"    logging: {str(user.logging).lower()}")

        if user.whitelist:
            lines.append("    whitelist:")
            for ip in user.whitelist:
                lines.append(f"      - {ip}")
        else:
            lines.append("    # whitelist:")
            lines.append("    #   - 192.168.1.100")
            lines.append("    #   - 10.0.0.0/8")

        lines.append("")

    with open(path, 'w') as f:
        f.write('\n'.join(lines))


# ============================================================================
# 工具类
# ============================================================================

class FrameBuffer:
    """
    用于累积和解析隧道消息的缓冲区
    处理部分读取和消息边界
    """

    def __init__(self):
        """初始化缓冲区"""
        self.buffer = b''  # 内部字节缓冲区

    def append(self, data: bytes):
        """将数据添加到缓冲区"""
        self.buffer += data

    def get_messages(self) -> List[TunnelMessage]:
        """
        从缓冲区提取完整的消息
        返回消息列表，更新缓冲区以包含剩余数据
        """
        messages = []

        # 只要缓冲区中有足够的数据来解析头部
        while len(self.buffer) >= TunnelMessage.HEADER_SIZE:
            try:
                # 预览负载长度
                _, _, _, payload_len = struct.unpack(
                    '>BBHH', self.buffer[:TunnelMessage.HEADER_SIZE]
                )
                total_len = TunnelMessage.HEADER_SIZE + payload_len

                # 如果数据不足，等待更多数据
                if len(self.buffer) < total_len:
                    break

                # 反序列化消息
                msg, remaining = TunnelMessage.deserialize(self.buffer)
                messages.append(msg)
                self.buffer = remaining

            except ValueError:
                break

        return messages

    def clear(self):
        """清空缓冲区"""
        self.buffer = b''


class AsyncQueue:
    """用于消息传递的简单异步队列包装器"""

    def __init__(self, maxsize: int = 0):
        """
        初始化队列

        参数:
            maxsize: 最大队列大小，0 表示无限制
        """
        self._queue = asyncio.Queue(maxsize=maxsize)

    async def put(self, item):
        """异步放入项目"""
        await self._queue.put(item)

    async def get(self):
        """异步获取项目"""
        return await self._queue.get()

    def put_nowait(self, item):
        """非阻塞放入项目"""
        self._queue.put_nowait(item)

    def get_nowait(self):
        """非阻塞获取项目"""
        return self._queue.get_nowait()

    def empty(self) -> bool:
        """检查队列是否为空"""
        return self._queue.empty()

    def qsize(self) -> int:
        """获取队列大小"""
        return self._queue.qsize()
