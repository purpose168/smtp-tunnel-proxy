#!/usr/bin/env python3
"""
客户端 SOCKS5 协议模块

本模块定义了 SOCKS5 协议的常量和通道数据结构。

SOCKS5 是一种网络协议，客户端通过代理服务器与任意服务器进行通信。
本实现支持 CONNECT 命令，用于建立 TCP 隧道。
"""

from dataclasses import dataclass
import asyncio


# ============================================================================
# SOCKS5 协议常量
# ============================================================================

class SOCKS5:
    """
    SOCKS5 协议常量定义
    
    SOCKS5 是一种网络协议，客户端通过代理服务器与任意服务器进行通信。
    本实现支持 CONNECT 命令，用于建立 TCP 隧道。
    """
    VERSION = 0x05
    AUTH_NONE = 0x00
    CMD_CONNECT = 0x01
    ATYP_IPV4 = 0x01
    ATYP_DOMAIN = 0x03
    ATYP_IPV6 = 0x04
    REP_SUCCESS = 0x00
    REP_FAILURE = 0x01


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class Channel:
    """
    隧道通道数据类
    
    表示一个通过隧道建立的连接通道，包含通道的所有状态信息。
    每个通道对应一个通过 SOCKS5 代理的 TCP 连接。
    
    Attributes:
        channel_id: 通道唯一标识符
        reader: 异步流读取器，用于从 SOCKS 客户端读取数据
        writer: 异步流写入器，用于向 SOCKS 客户端写入数据
        host: 目标主机地址
        port: 目标端口
        connected: 通道连接状态，True 表示连接活跃
    """
    channel_id: int
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    host: str
    port: int
    connected: bool = False
