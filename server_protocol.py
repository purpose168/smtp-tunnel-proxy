"""
二进制协议模块 - 定义 SMTP 隧道服务器的二进制协议

此模块定义了 SMTP 握手后使用的二进制协议，包括帧类型常量、
帧构造函数和帧解析函数。二进制协议用于高效的多通道数据转发。
"""

import struct

# ============================================================================
# 二进制协议常量
# ============================================================================

FRAME_DATA = 0x01
FRAME_CONNECT = 0x02
FRAME_CONNECT_OK = 0x03
FRAME_CONNECT_FAIL = 0x04
FRAME_CLOSE = 0x05

FRAME_HEADER_SIZE = 5

# ============================================================================
# 帧构造和解析函数
# ============================================================================

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
