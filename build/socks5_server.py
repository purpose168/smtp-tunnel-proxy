#!/usr/bin/env python3
"""
客户端 SOCKS5 服务器模块

本模块定义了 SOCKS5 代理服务器，监听本地端口，接受 SOCKS5 客户端连接，
将请求通过隧道转发到远程服务器。
"""

import asyncio
import socket
import struct
import logging

from connection import SOCKS5, Channel
from tunnel.client import TunnelClient
from tunnel.crypto import TunnelCrypto

logger = logging.getLogger('smtp-tunnel-socks5-server')


class SOCKS5Server:
    """
    SOCKS5 代理服务器
    
    监听本地端口，接受 SOCKS5 客户端连接，将请求通过隧道转发到远程服务器。
    实现了 SOCKS5 协议的基本功能，支持 IPv4、IPv6 和域名地址类型。
    
    工作流程:
    1. 接受 SOCKS5 客户端连接
    2. 执行 SOCKS5 握手（版本协商、认证协商）
    3. 解析 CONNECT 请求，提取目标地址和端口
    4. 通过隧道打开到目标主机的通道
    5. 在 SOCKS 客户端和隧道之间双向转发数据
    
    Attributes:
        tunnel: 隧道客户端实例，用于与远程服务器通信
        host: SOCKS5 服务器监听地址
        port: SOCKS5 服务器监听端口
    """

    def __init__(self, tunnel: TunnelClient, host: str = '127.0.0.1', port: int = 1080):
        logger.info(f"初始化 SOCKS5 服务器: host={host}, port={port}")
        self.tunnel = tunnel
        self.host = host
        self.port = port

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """
        处理 SOCKS5 客户端连接
        
        完整的 SOCKS5 代理处理流程:
        1. 检查隧道连接状态
        2. 执行 SOCKS5 握手（版本协商）
        3. 解析 CONNECT 请求
        4. 根据地址类型解析目标地址（IPv4/IPv6/域名）
        5. 通过隧道建立到目标主机的连接
        6. 启动数据转发循环
        
        Args:
            reader: 从 SOCKS 客户端读取数据的异步流读取器
            writer: 向 SOCKS 客户端写入数据的异步流写入器
        """
        channel = None
        try:
            if not self.tunnel.connected:
                writer.close()
                return

            data = await reader.read(2)
            if len(data) < 2 or data[0] != SOCKS5.VERSION:
                return

            nmethods = data[1]
            await reader.read(nmethods)

            writer.write(bytes([SOCKS5.VERSION, SOCKS5.AUTH_NONE]))
            await writer.drain()

            data = await reader.read(4)
            if len(data) < 4:
                return

            version, cmd, _, atyp = data

            if cmd != SOCKS5.CMD_CONNECT:
                writer.write(bytes([SOCKS5.VERSION, 0x07, 0, 1, 0, 0, 0, 0, 0, 0]))
                await writer.drain()
                return

            if atyp == SOCKS5.ATYP_IPV4:
                addr_data = await reader.read(4)
                host = socket.inet_ntoa(addr_data)
            elif atyp == SOCKS5.ATYP_DOMAIN:
                length = (await reader.read(1))[0]
                host = (await reader.read(length)).decode()
            elif atyp == SOCKS5.ATYP_IPV6:
                addr_data = await reader.read(16)
                host = socket.inet_ntop(socket.AF_INET6, addr_data)
            else:
                return

            port_data = await reader.read(2)
            port = struct.unpack('>H', port_data)[0]

            logger.info(f"CONNECT {host}:{port}")

            channel_id, success = await self.tunnel.open_channel(host, port)

            if success:
                writer.write(bytes([SOCKS5.VERSION, SOCKS5.REP_SUCCESS, 0, 1, 0, 0, 0, 0, 0, 0]))
                await writer.drain()

                channel = Channel.create_client_channel(
                    channel_id=channel_id,
                    reader=reader,
                    writer=writer,
                    host=host,
                    port=port
                )
                self.tunnel.channels[channel_id] = channel

                await self._forward_loop(channel)
            else:
                writer.write(bytes([SOCKS5.VERSION, SOCKS5.REP_FAILURE, 0, 1, 0, 0, 0, 0, 0, 0]))
                await writer.drain()

        except Exception as e:
            logger.debug(f"SOCKS 错误: {e}")
        finally:
            if channel:
                await self.tunnel.close_channel_remote(channel.channel_id)
                await self.tunnel.close_channel(channel)
            try:
                writer.close()
                await writer.wait_closed()
            except:
                pass

    async def _forward_loop(self, channel: Channel):
        """
        从 SOCKS 客户端转发数据到隧道
        
        持续从 SOCKS 客户端读取数据，并通过隧道发送到服务器。
        使用短超时（0.1秒）实现非阻塞读取，允许及时检测连接断开。
        
        Args:
            channel: 通道对象，包含 SOCKS 客户端的读写流
        """
        logger.debug(f"启动数据转发循环: channel_id={channel.channel_id}")
        
        try:
            while channel.connected and self.tunnel.connected:
                try:
                    data = await asyncio.wait_for(channel.reader.read(32768), timeout=0.1)
                    if data:
                        logger.debug(f"从 SOCKS5 客户端读取数据: channel_id={channel.channel_id}, len={len(data)}")
                        await self.tunnel.send_data(channel.channel_id, data)
                    elif data == b'':
                        logger.debug(f"SOCKS5 客户端关闭连接: channel_id={channel.channel_id}")
                        break
                except asyncio.TimeoutError:
                    continue
        except Exception as e:
            logger.error(f"数据转发循环错误: channel_id={channel.channel_id}, error={e}")
        finally:
            logger.debug(f"数据转发循环结束: channel_id={channel.channel_id}")

    async def start(self):
        """
        启动 SOCKS5 服务器
        
        创建异步 TCP 服务器，监听指定地址和端口。
        服务器将持续运行，接受客户端连接。
        """
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        addr = server.sockets[0].getsockname()
        logger.info(f"SOCKS5 代理在 {addr[0]}:{addr[1]}")

        async with server:
            await server.serve_forever()
