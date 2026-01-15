"""
SMTP 隧道 - 核心协议模块
定义隧道协议的常量、消息类型和消息格式。

版本: 1.3.0

功能概述:
本模块提供了 SMTP 隧道代理系统的核心协议定义，包括协议常量、
消息类型枚举和隧道消息类。这些组件被客户端和服务器共享，确保
两端使用相同的协议格式。

主要功能:
1. 协议常量定义 - 版本号、载荷大小、加密参数
2. 消息类型枚举 - 定义所有隧道消息类型
3. 隧道消息类 - 消息序列化和反序列化
4. 兼容旧接口的函数式方法

协议架构:
- 使用 SMTP 协议作为传输层，伪装成正常的邮件通信
- 在 SMTP 连接建立后切换到二进制协议模式
- 使用多路复用技术支持多个并发通道
- 每个通道对应一个独立的 TCP 连接

消息格式:
┌─────────┬────────────┬────────────┬──────────────┬─────────────┐
│ 版本    │ 消息类型   │ 通道 ID    │ 负载长度     │   负载      │
│ 1 字节  │  1 字节    │  2 字节    │  2 字节      │  可变长度   │
└─────────┴────────────┴────────────┴──────────────┴─────────────┘

所有多字节字段使用大端序（网络字节序）。
"""

import struct
import logging
from enum import IntEnum
from typing import Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger('smtp-tunnel-protocol')


# ============================================================================
# 协议常量
# ============================================================================

PROTOCOL_VERSION = 1
MAX_PAYLOAD_SIZE = 65535
NONCE_SIZE = 12
TAG_SIZE = 16
FRAME_HEADER_SIZE = 6  # 包括版本字段


# ============================================================================
# 消息类型枚举
# ============================================================================

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
    DATA = 0x01
    CONNECT = 0x02
    CONNECT_OK = 0x03
    CONNECT_FAIL = 0x04
    CLOSE = 0x05
    KEEPALIVE = 0x06
    KEEPALIVE_ACK = 0x07


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
    """
    msg_type: MsgType
    channel_id: int
    payload: bytes

    HEADER_SIZE = FRAME_HEADER_SIZE

    def serialize(self) -> bytes:
        """
        将消息序列化为字节
        
        按照协议格式将消息转换为字节数组，准备发送。
        
        Returns:
            bytes: 序列化后的消息字节
            
        Raises:
            struct.error: 如果载荷长度超过 65535
        """
        logger.debug(f"序列化消息: type={self.msg_type.name}, channel_id={self.channel_id}, payload_len={len(self.payload)}")
        
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
        logger.debug(f"开始反序列化消息: data_len={len(data)}")
        
        if len(data) < cls.HEADER_SIZE:
            logger.error(f"数据不足以解析头部: {len(data)} 字节，需要 {cls.HEADER_SIZE} 字节")
            raise ValueError("数据不足以解析头部")
        
        version, msg_type, channel_id, payload_len = struct.unpack(
            '>BBHH', data[:cls.HEADER_SIZE]
        )
        
        logger.debug(f"解析帧头: version={version}, msg_type={msg_type}, channel_id={channel_id}, payload_len={payload_len}")
        
        if version != PROTOCOL_VERSION:
            logger.error(f"未知的协议版本: {version}, 预期: {PROTOCOL_VERSION}")
            raise ValueError(f"未知的协议版本: {version}")
        
        total_len = cls.HEADER_SIZE + payload_len
        if len(data) < total_len:
            logger.error(f"数据不足以解析负载: {len(data)} 字节，需要 {total_len} 字节")
            raise ValueError("数据不足以解析负载")
        
        payload = data[cls.HEADER_SIZE:total_len]
        remaining = data[total_len:]
        
        logger.debug(f"解析完成: payload_len={len(payload)}, remaining_len={len(remaining)}")
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
        logger.debug(f"创建 DATA 消息: channel_id={channel_id}, data_len={len(data)}")
        return cls(MsgType.DATA, channel_id, data)

    @classmethod
    def connect(cls, channel_id: int, host: str, port: int) -> 'TunnelMessage':
        """
        创建 CONNECT 消息
        
        用于请求建立到目标主机的连接。
        
        潽荷格式:
        ┌──────────┬────────────┬────────────┐
        │ 主机长度 │   主机名    │ 端口号   │
        │  1 字节  │  可变长度  │  2 字节   │
        └──────────┴────────────┴────────────┘
        
        Args:
            channel_id: 通道 ID
            host: 目标主机名或 IP 地址
            port: 目标端口号
            
        Returns:
            TunnelMessage: CONNECT 类型的消息对象
        """
        logger.debug(f"创建 CONNECT 消息: channel_id={channel_id}, host={host}, port={port}")
        host_bytes = host.encode('utf-8')
        payload = struct.pack('>B', len(host_bytes)) + host_bytes + struct.pack('>H', port)
        return cls(MsgType.CONNECT, channel_id, payload)

    @classmethod
    def connect_ok(cls, channel_id: int) -> 'TunnelMessage':
        """
        创建 CONNECT_OK 消息
        
        用于响应连接请求成功。
        
        Args:
            channel_id: 通道 ID
            
        Returns:
            TunnelMessage: CONNECT_OK 类型的消息对象
        """
        logger.debug(f"创建 CONNECT_OK 消息: channel_id={channel_id}")
        return cls(MsgType.CONNECT_OK, channel_id, b'')

    @classmethod
    def connect_fail(cls, channel_id: int, reason: str = None) -> 'TunnelMessage':
        """
        创建 CONNECT_FAIL 消息
        
        用于响应连接请求失败。
        
        Args:
            channel_id: 通道 ID
            reason: 失败原因（可选）
            
        Returns:
            TunnelMessage: CONNECT_FAIL 类型的消息对象
        """
        logger.debug(f"创建 CONNECT_FAIL 消息: channel_id={channel_id}, reason={reason}")
        payload = reason.encode('utf-8') if reason else b''
        return cls(MsgType.CONNECT_FAIL, channel_id, payload)

    @classmethod
    def keepalive(cls) -> 'TunnelMessage':
        """
        创建 KEEPALIVE 消息
        
        用于检测连接状态，防止连接因超时而断开。
        
        Returns:
            TunnelMessage: KEEPALIVE 类型的消息对象
        """
        logger.debug("创建 KEEPALIVE 消息")
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
            logger.error(f"解析 CONNECT 消息失败: 消息类型为 {self.msg_type.name}")
            raise ValueError("不是 CONNECT 消息")
        
        host_len = self.payload[0]
        host = self.payload[1:1+host_len].decode('utf-8')
        port = struct.unpack('>H', self.payload[1+host_len:3+host_len])[0]
        
        logger.debug(f"解析 CONNECT 消息: host={host}, port={port}")
        return host, port


# ============================================================================
# 兼容接口（为了向后兼容原有的函数式接口）
# ============================================================================

# 常量别名，保持向后兼容
FRAME_DATA = MsgType.DATA.value
FRAME_CONNECT = MsgType.CONNECT.value
FRAME_CONNECT_OK = MsgType.CONNECT_OK.value
FRAME_CONNECT_FAIL = MsgType.CONNECT_FAIL.value
FRAME_CLOSE = MsgType.CLOSE.value


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
    """
    msg = TunnelMessage(MsgType(frame_type), channel_id, payload)
    return msg.serialize()


def parse_frame_header(data: bytes) -> Optional[Tuple[int, int, int]]:
    """
    解析帧头，返回帧类型、通道ID和负载长度
    
    帧头格式: 类型(1字节) + 通道ID(2字节) + 负载长度(2字节) = 5字节
    
    Args:
        data: 原始字节数据，至少包含5字节的帧头
    
    Returns:
        tuple: (frame_type, channel_id, payload_len) 如果数据足够
        None: 如果数据不足5字节
    """
    logger.debug(f"解析帧头: data_len={len(data)}")
    
    if len(data) < TunnelMessage.HEADER_SIZE:
        logger.warning(f"数据不足以解析帧头: {len(data)} 字节，需要 {TunnelMessage.HEADER_SIZE} 字节")
        return None
    
    version, msg_type, channel_id, payload_len = struct.unpack(
        '>BBHH', data[:TunnelMessage.HEADER_SIZE]
    )
    
    logger.debug(f"解析帧头完成: version={version}, msg_type={msg_type}, channel_id={channel_id}, payload_len={payload_len}")
    return msg_type, channel_id, payload_len


def make_connect_payload(host: str, port: int) -> bytes:
    """
    构造连接请求的载荷
    
    载荷格式: [主机名长度(1B)] [主机名(UTF-8编码)] [端口(2B, 大端序)]
    
    Args:
        host: 目标主机名或IP地址
        port: 目标端口号
        
    Returns:
        连接请求载荷字节数组
    """
    logger.debug(f"构造连接载荷: host={host}, port={port}")
    host_bytes = host.encode('utf-8')
    payload = struct.pack('>B', len(host_bytes)) + host_bytes + struct.pack('>H', port)
    
    logger.debug(f"连接载荷构造完成: payload_len={len(payload)}")
    return payload
