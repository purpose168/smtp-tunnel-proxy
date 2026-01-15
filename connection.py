"""
  连接管理模块 - 统一的通道和连接管理

  本模块整合了 SOCKS5 协议常量、通道数据类和连接管理功能，
  提供客户端和服务器端的统一接口。

  主要功能:
  - SOCKS5 协议常量定义
  - IPv4 回退地址池管理
  - 统一的隧道通道数据类
  - TCP 连接管理（支持多种连接策略）
  - 通道资源清理

  版本:1.3.0
"""

import asyncio
import socket
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger('smtp-tunnel-connection')


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
    
    统一的通道接口，支持客户端和服务器端的通道管理。
    每个通道对应一个 TCP 连接，通过 SMTP 隧道进行数据传输。
    通道支持全双工通信，即可以同时进行双向数据传输。
    
    Attributes:
        channel_id: 通道唯一标识符（0-65535），用于在二进制协议中标识不同的连接
        host: 目标主机名或 IP 地址
        port: 目标端口号
        reader: asyncio.StreamReader，用于读取数据（客户端为 SOCKS 客户端，服务器为目标主机）
        writer: asyncio.StreamWriter，用于写入数据（客户端为 SOCKS 客户端，服务器为目标主机）
        connected: 连接状态标志，True 表示已成功连接
        reader_task: 异步任务对象，仅服务器端使用，用于从目标主机读取数据并转发
    
    Lifecycle:
        1. 创建 Channel 对象（未连接状态）
        2. 建立连接（客户端：SOCKS 客户端；服务器：目标主机）
        3. 服务器端创建 reader_task 开始读取数据
        4. 传输数据（双向）
        5. 关闭连接并清理资源
    
    Example:
        # 客户端通道创建
        >>> channel = Channel.create_client_channel(
        ...     channel_id=1, reader=reader, writer=writer,
        ...     host='example.com', port=80
        ... )
        
        # 服务器通道创建
        >>> channel = Channel.create_server_channel(
        ...     channel_id=1, host='example.com', port=80
        ... )
    """
    channel_id: int
    host: str
    port: int
    reader: Optional[asyncio.StreamReader] = None
    writer: Optional[asyncio.StreamWriter] = None
    connected: bool = False
    reader_task: Optional[asyncio.Task] = None

    @classmethod
    def create_client_channel(cls, channel_id: int, reader: asyncio.StreamReader,
                           writer: asyncio.StreamWriter, host: str, port: int) -> 'Channel':
        """
        创建客户端通道
        
        客户端通道用于 SOCKS5 客户端连接，reader 和 writer 必须提供。
        
        Args:
            channel_id: 通道唯一标识符
            reader: 从 SOCKS 客户端读取数据的异步流读取器
            writer: 向 SOCKS 客户端写入数据的异步流写入器
            host: 目标主机地址
            port: 目标端口
        
        Returns:
            Channel: 已连接的客户端通道对象
        """
        logger.debug(f"创建客户端通道: channel_id={channel_id}, host={host}, port={port}")
        return cls(
            channel_id=channel_id,
            reader=reader,
            writer=writer,
            host=host,
            port=port,
            connected=True
        )

    @classmethod
    def create_server_channel(cls, channel_id: int, host: str, port: int) -> 'Channel':
        """
        创建服务器通道
        
        服务器通道用于目标主机连接，reader 和 writer 在连接建立后设置。
        
        Args:
            channel_id: 通道唯一标识符
            host: 目标主机地址
            port: 目标端口
        
        Returns:
            Channel: 未连接的服务器通道对象
        """
        logger.debug(f"创建服务器通道: channel_id={channel_id}, host={host}, port={port}")
        return cls(
            channel_id=channel_id,
            host=host,
            port=port,
            connected=False
        )

    def is_client_channel(self) -> bool:
        """
        判断是否为客户端通道
        
        Returns:
            bool: True 表示客户端通道，False 表示服务器通道
        """
        return self.reader_task is None and self.reader is not None

    def is_server_channel(self) -> bool:
        """
        判断是否为服务器通道
        
        Returns:
            bool: True 表示服务器通道，False 表示客户端通道
        """
        return self.reader_task is not None


# ============================================================================
# 连接策略和辅助函数
# ============================================================================

async def connect_to_target(host: str, port: int, ipv6_supported: bool = True) -> Tuple[Optional[asyncio.StreamReader], Optional[asyncio.StreamWriter]]:
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
    logger.info(f"尝试连接到目标: {host}:{port}, ipv6_supported={ipv6_supported}")
    reader, writer = None, None
    
    # 策略 1: IPv6 连接（如果是 IPv6 地址）
    if ':' in host and ipv6_supported:
        logger.debug(f"尝试策略 1: IPv6 连接")
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, family=socket.AF_INET6),
                timeout=10.0
            )
            logger.info(f"IPv6 连接成功: {host}:{port}")
            return reader, writer
        except Exception as e:
            logger.debug(f"IPv6 连接失败: {e}")
            pass
    
    # 策略 2: 自动地址族选择（如果是域名）
    if '.' in host or ':' in host:
        logger.debug(f"尝试策略 2: 自动地址族选择")
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=10.0
            )
            logger.info(f"自动地址族连接成功: {host}:{port}")
            return reader, writer
        except Exception as e:
            logger.debug(f"自动地址族连接失败: {e}")
            pass
    
    # 策略 3: IPv4 连接
    if '.' in host:
        logger.debug(f"尝试策略 3: IPv4 连接")
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, family=socket.AF_INET),
                timeout=10.0
            )
            logger.info(f"IPv4 连接成功: {host}:{port}")
            return reader, writer
        except Exception as e:
            logger.debug(f"IPv4 连接失败: {e}")
            pass
    
    # 策略 4: IPv4 地址池回退（对于纯 IPv6 地址）
    if host in IPv4_FALLBACK_POOL:
        logger.debug(f"尝试策略 4: IPv4 地址池回退")
        for ipv4_addr in IPv4_FALLBACK_POOL[host]:
            logger.debug(f"尝试 IPv4 地址: {ipv4_addr}")
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(ipv4_addr, port, family=socket.AF_INET),
                    timeout=10.0
                )
                logger.info(f"IPv4 地址池连接成功: {ipv4_addr}:{port}")
                return reader, writer
            except Exception as e:
                logger.debug(f"IPv4 地址池连接失败: {ipv4_addr}, 错误: {e}")
                continue
    
    # 策略 5: Google DNS 解析（如果是域名）
    if '.' in host:
        logger.debug(f"尝试策略 5: Google DNS 解析")
        try:
            loop = asyncio.get_event_loop()
            infos = await loop.getaddrinfo(host, port, family=socket.AF_INET)
            logger.debug(f"DNS 解析结果: {len(infos)} 个地址")
            for info in infos:
                logger.debug(f"尝试 DNS 解析地址: {info[4][0]}")
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(info[4][0], port),
                        timeout=10.0
                    )
                    logger.info(f"Google DNS 解析连接成功: {info[4][0]}:{port}")
                    return reader, writer
                except Exception as e:
                    logger.debug(f"Google DNS 解析连接失败: {info[4][0]}, 错误: {e}")
                    continue
        except Exception as e:
            logger.debug(f"Google DNS 解析失败: {e}")
            pass
    
    logger.warning(f"所有连接策略都失败: {host}:{port}")
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
    logger.debug(f"关闭通道: channel_id={channel.channel_id}, host={channel.host}, port={channel.port}")
    
    if channel.reader_task and not channel.reader_task.done():
        logger.debug(f"取消读取任务: channel_id={channel.channel_id}")
        channel.reader_task.cancel()
        try:
            channel.reader_task.result()
        except Exception as e:
            logger.debug(f"取消读取任务异常: channel_id={channel.channel_id}, error={e}")
            pass
    
    if channel.writer:
        logger.debug(f"关闭写入器: channel_id={channel.channel_id}")
        try:
            channel.writer.close()
            logger.debug(f"写入器已关闭: channel_id={channel.channel_id}")
        except Exception as e:
            logger.error(f"关闭写入器失败: channel_id={channel.channel_id}, error={e}")
            pass
    
    if channel.reader:
        logger.debug(f"清理读取器: channel_id={channel.channel_id}")
        channel.reader = None
    
    channel.writer = None
    channel.connected = False
    
    logger.info(f"通道已关闭: channel_id={channel.channel_id}")
