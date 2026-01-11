#!/usr/bin/env python3
"""
客户端二进制协议模块

本模块定义了客户端与服务器通信使用的二进制协议格式和辅助函数。

二进制协议帧格式:
[类型(1B)] [通道ID(2B, 大端序)] [载荷长度(2B, 大端序)] [载荷数据]

帧类型:
- FRAME_DATA (0x01): 数据帧，用于传输实际数据
- FRAME_CONNECT (0x02): 连接请求帧
- FRAME_CONNECT_OK (0x03): 连接成功响应帧
- FRAME_CONNECT_FAIL (0x04): 连接失败响应帧
- FRAME_CLOSE (0x05): 关闭通道帧
"""

import struct


# ============================================================================
# 协议常量
# ============================================================================

FRAME_DATA = 0x01
FRAME_CONNECT = 0x02
FRAME_CONNECT_OK = 0x03
FRAME_CONNECT_FAIL = 0x04
FRAME_CLOSE = 0x05
FRAME_HEADER_SIZE = 5


# ============================================================================
# 协议函数
# ============================================================================

def make_frame(frame_type: int, channel_id: int, payload: bytes = b'') -> bytes:
    """
    构造二进制协议帧
    
    帧格式: [类型(1B)] [通道ID(2B, 大端序)] [载荷长度(2B, 大端序)] [载荷数据]
    
    Args:
        frame_type: 帧类型（FRAME_DATA, FRAME_CONNECT 等）
        channel_id: 通道标识符，用于区分不同的连接
        payload: 帧载荷数据，默认为空
    
    Returns:
        完整的二进制帧字节数组
    """
    return struct.pack('>BHH', frame_type, channel_id, len(payload)) + payload


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
    host_bytes = host.encode('utf-8')
    return struct.pack('>B', len(host_bytes)) + host_bytes + struct.pack('>H', port)
