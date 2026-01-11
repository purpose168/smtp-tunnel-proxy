"""
连接管理模块 - 管理隧道通道和连接策略

此模块定义了隧道通道数据类和 IPv4 回退地址池，
用于管理从客户端到目标主机的 TCP 连接。
"""

import asyncio
import socket
from dataclasses import dataclass, field
from typing import Optional, Dict, List

# ============================================================================
# IPv4 地址池 - 用于纯 IPv6 地址的回退
# ============================================================================

IPv4_FALLBACK_POOL = {
    'google.com': ['142.250.72.174', '142.250.72.175', '142.250.72.176'],
    'www.google.com': ['142.250.72.174', '142.250.72.175'],
    'cloudflare.com': ['104.16.132.229', '104.16.133.229'],
    'www.cloudflare.com': ['104.16.132.229', '104.16.133.229'],
    'facebook.com': ['157.240.22.35', '157.240.22.19'],
    'www.facebook.com': ['157.240.22.35', '157.240.22.19'],
    'apple.com': ['17.253.144.10', '17.253.144.11'],
    'www.apple.com': ['17.253.144.10', '17.253.144.11'],
}

# ============================================================================
# 通道 - 隧道化的 TCP 连接
# ============================================================================

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
    channel_id: int
    host: str
    port: int
    reader: Optional[asyncio.StreamReader] = None
    writer: Optional[asyncio.StreamWriter] = None
    connected: bool = False
    reader_task: Optional[asyncio.Task] = None

# ============================================================================
# 连接策略和辅助函数
# ============================================================================

async def connect_to_target(host: str, port: int, ipv6_supported: bool = True) -> tuple[Optional[asyncio.StreamReader], Optional[asyncio.StreamWriter]]:
    """
    建立到目标主机的 TCP 连接，支持多种连接策略
    
    此方法尝试使用多种策略建立到目标主机的连接，包括 IPv6、IPv4、
    自动地址族选择和回退机制。连接策略按优先级依次尝试，直到成功
    或所有策略都失败。
    
    Args:
        host: 目标主机名或 IP 地址
        port: 目标端口号
        ipv6_supported: 是否支持 IPv6 连接，默认为 True
    
    Returns:
        tuple: (reader, writer) 如果连接成功
        tuple: (None, None) 如果所有连接策略都失败
    
    连接策略（按优先级）:
        1. IPv6 连接（如果是 IPv6 地址且服务器支持 IPv6）
        2. 自动地址族选择（如果是域名）
        3. IPv4 连接（使用解析到的 IPv4 地址）
        4. IPv4 地址池回退（对于纯 IPv6 地址）
        5. Google DNS 解析（如果是域名）
    
    Example:
        >>> reader, writer = await connect_to_target('example.com', 80)
        >>> if reader and writer:
        ...     print("连接成功")
    """
    reader, writer = None, None
    
    # 策略 1: IPv6 连接（如果是 IPv6 地址）
    if ':' in host and ipv6_supported:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, family=socket.AF_INET6),
                timeout=10.0
            )
            return reader, writer
        except Exception as e:
            pass
    
    # 策略 2: 自动地址族选择（如果是域名）
    if '.' in host or ':' in host:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=10.0
            )
            return reader, writer
        except Exception as e:
            pass
    
    # 策略 3: IPv4 连接
    if '.' in host:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, family=socket.AF_INET),
                timeout=10.0
            )
            return reader, writer
        except Exception as e:
            pass
    
    # 策略 4: IPv4 地址池回退（对于纯 IPv6 地址）
    if host in IPv4_FALLBACK_POOL:
        for ipv4_addr in IPv4_FALLBACK_POOL[host]:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(ipv4_addr, port, family=socket.AF_INET),
                    timeout=10.0
                )
                return reader, writer
            except Exception as e:
                continue
    
    # 策略 5: Google DNS 解析（如果是域名）
    if '.' in host:
        try:
            loop = asyncio.get_event_loop()
            infos = await loop.getaddrinfo(host, port, family=socket.AF_INET)
            for info in infos:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(info[4][0], port),
                        timeout=10.0
                    )
                    return reader, writer
                except Exception as e:
                    continue
        except Exception as e:
            pass
    
    return None, None

def close_channel(channel: Channel):
    """
    关闭通道并清理资源
    
    此方法关闭通道的读写器，取消读取任务，并清理所有相关资源。
    
    Args:
        channel: 要关闭的通道对象
    
    Example:
        >>> close_channel(channel)
    """
    if channel.reader_task and not channel.reader_task.done():
        channel.reader_task.cancel()
        try:
            channel.reader_task.result()
        except:
            pass
    
    if channel.writer:
        try:
            channel.writer.close()
        except:
            pass
    
    if channel.reader:
        channel.reader = None
    
    channel.writer = None
    channel.connected = False
