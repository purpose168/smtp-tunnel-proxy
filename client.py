#!/usr/bin/env python3
"""
SMTP 隧道客户端 - 快速二进制模式

版本: 1.3.0

功能概述:
本程序是一个 SMTP 隧道客户端，通过伪装成 SMTP 协议与服务器通信，
然后切换到高效二进制模式进行数据传输。它提供了一个本地 SOCKS5 代理，
允许任何支持 SOCKS5 的应用程序通过隧道连接到远程服务器。

工作原理:
1. 连接到 SMTP 隧道服务器
2. 执行标准 SMTP 握手（EHLO, STARTTLS, AUTH）
3. 发送 "BINARY" 命令切换到二进制协议模式
4. 启动本地 SOCKS5 代理服务器
5. 将 SOCKS5 客户端的连接请求通过隧道转发到服务器
6. 在 SOCKS 客户端和隧道服务器之间双向转发数据

协议说明:
- SMTP 握手阶段: 使用标准 SMTP 协议，看起来像正常的 SMTP 客户端
- 二进制模式阶段: 使用自定义二进制协议，支持多通道并发传输

二进制协议帧格式:
[类型(1B)] [通道ID(2B, 大端序)] [载荷长度(2B, 大端序)] [载荷数据]

帧类型:
- FRAME_DATA (0x01): 数据帧，用于传输实际数据
- FRAME_CONNECT (0x02): 连接请求帧
- FRAME_CONNECT_OK (0x03): 连接成功响应帧
- FRAME_CONNECT_FAIL (0x04): 连接失败响应帧
- FRAME_CLOSE (0x05): 关闭通道帧

特性:
- 多用户支持（用户名 + 密钥认证）
- TLS 加密通信
- 自动重连机制（指数退避）
- 支持 IPv4、IPv6 和域名地址
- 多通道并发传输
- 完整的错误处理和日志记录

使用方法:
1. 配置 config.yaml 文件或使用命令行参数
2. 运行: python client.py --config config.yaml
3. 配置应用程序使用 SOCKS5 代理（默认 127.0.0.1:1080）

命令行参数:
--config, -c: 配置文件路径（默认: config.yaml）
--server: 服务器域名
--server-port: 服务器端口（默认: 587）
--socks-port, -p: SOCKS5 代理端口（默认: 1080）
--username, -u: 认证用户名
--secret, -s: 认证密钥
--ca-cert: CA 证书路径
--debug, -d: 启用调试日志

依赖:
- Python 3.7+
- asyncio
- ssl
- struct
- socket
- dataclasses
"""

import asyncio
import logging
import argparse
import sys

from common import load_config, ClientConfig
from tunnel.client import TunnelClient
from socks5_server import SOCKS5Server

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('smtp-tunnel-client')


async def run_client(config: ClientConfig, ca_cert: str):
    """
    运行客户端并实现自动重连机制
    
    主循环逻辑:
    1. 尝试连接到隧道服务器
    2. 如果连接失败，等待后重试（使用指数退避）
    3. 如果连接成功，启动 SOCKS5 代理服务器
    4. 等待连接断开或用户中断
    5. 清理资源并重新开始循环
    
    重连策略:
    - 初始延迟: 2 秒
    - 最大延迟: 30 秒
    - 连接失败时延迟翻倍（指数退避）
    - 连接成功后重置延迟
    
    Args:
        config: 客户端配置对象
        ca_cert: CA 证书路径
    """
    reconnect_delay = 2
    max_reconnect_delay = 30
    current_delay = reconnect_delay

    while True:
        tunnel = TunnelClient(config, ca_cert)

        if not await tunnel.connect():
            logger.warning(f"连接失败，{current_delay}秒后重试...")
            await asyncio.sleep(current_delay)
            current_delay = min(current_delay * 2, max_reconnect_delay)
            continue

        current_delay = reconnect_delay
        
        receiver_task = asyncio.create_task(tunnel._receiver_loop())
        tunnel.receiver_task = receiver_task

        socks = SOCKS5Server(tunnel, config.socks_host, config.socks_port)

        try:
            socks_server = await asyncio.start_server(
                socks.handle_client,
                socks.host,
                socks.port,
                reuse_address=True
            )
            addr = socks_server.sockets[0].getsockname()
            logger.info(f"SOCKS5 代理在 {addr[0]}:{addr[1]}")

            async with socks_server:
                try:
                    await receiver_task
                except asyncio.CancelledError:
                    pass

            if tunnel.connected:
                tunnel.connected = False

            logger.warning("连接丢失，正在重连...")
            current_delay = reconnect_delay

        except KeyboardInterrupt:
            logger.info("正在关闭...")
            await tunnel.disconnect()
            return 0
        except OSError as e:
            if "Address already in use" in str(e):
                logger.error(f"端口 {socks.port} 已被占用，等待中...")
                await asyncio.sleep(2)
            else:
                logger.error(f"SOCKS 服务器错误: {e}")
        finally:
            await tunnel.disconnect()
            if tunnel.receiver_task:
                tunnel.receiver_task.cancel()
                try:
                    await tunnel.receiver_task
                except asyncio.CancelledError:
                    pass
                tunnel.receiver_task = None


def main():
    """
    主函数 - 程序入口点
    
    解析命令行参数，加载配置文件，启动客户端。
    
    命令行参数:
    --config, -c: 配置文件路径（默认: config.yaml）
    --server: 服务器域名（TLS 需要 FQDN）
    --server-port: 服务器端口
    --socks-port, -p: SOCKS5 代理端口
    --username, -u: 认证用户名
    --secret, -s: 认证密钥
    --ca-cert: CA 证书路径
    --debug, -d: 启用调试日志
    
    配置优先级（从高到低）:
    1. 命令行参数
    2. 配置文件中的设置
    3. 默认值
    """
    parser = argparse.ArgumentParser(description='SMTP 隧道客户端（快速模式）')
    parser.add_argument('--config', '-c', default='config.yaml')
    parser.add_argument('--server', default=None, help='服务器域名（TLS 需要 FQDN）')
    parser.add_argument('--server-port', type=int, default=None)
    parser.add_argument('--socks-port', '-p', type=int, default=None)
    parser.add_argument('--username', '-u', default=None, help='认证用户名')
    parser.add_argument('--secret', '-s', default=None)
    parser.add_argument('--ca-cert', default=None)
    parser.add_argument('--debug', '-d', action='store_true')
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        config_data = load_config(args.config)
    except FileNotFoundError:
        config_data = {}

    client_conf = config_data.get('client', {})

    config = ClientConfig(
        server_host=args.server or client_conf.get('server_host', 'localhost'),
        server_port=args.server_port or client_conf.get('server_port', 587),
        socks_port=args.socks_port or client_conf.get('socks_port', 1080),
        socks_host=client_conf.get('socks_host', '127.0.0.1'),
        username=args.username or client_conf.get('username', ''),
        secret=args.secret or client_conf.get('secret', ''),
    )

    ca_cert = args.ca_cert or client_conf.get('ca_cert')

    if not config.username:
        logger.error("错误: 未配置用户名。请使用 --username 参数或在配置文件中设置 'username' 字段。")
        return 1

    if not config.secret:
        logger.error("错误: 未配置密钥。请使用 --secret 参数或在配置文件中设置 'secret' 字段。")
        return 1

    try:
        return asyncio.run(run_client(config, ca_cert))
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    sys.exit(main())
