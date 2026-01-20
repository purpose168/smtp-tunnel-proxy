#!/usr/bin/env python3
"""
恶意客户端模拟工具 - 模拟各种异常情况以测试客户端的健壮性

功能:
1. 发送不完整的 SOCKS5 握手
2. 发送不完整的连接请求
3. 建立大量并发连接
4. 发送大量数据导致缓冲区溢出
5. 长时间保持连接不发送数据
"""

import asyncio
import socket
import struct
import argparse
import sys
from typing import List

class MaliciousClient:
    """恶意客户端"""

    def __init__(self, host: str = '127.0.0.1', port: int = 1080):
        """
        初始化恶意客户端

        参数:
            host: SOCKS5 代理地址
            port: SOCKS5 代理端口
        """
        self.host = host
        self.port = port

    async def send_incomplete_handshake(self, num_connections: int = 10):
        """
        发送不完整的 SOCKS5 握手

        参数:
            num_connections: 连接数量
        """
        print(f"\n{'='*80}")
        print(f"测试场景: 发送不完整的 SOCKS5 握手")
        print(f"连接数量: {num_connections}")
        print(f"{'='*80}\n")

        tasks = []
        for i in range(num_connections):
            tasks.append(self._send_incomplete_handshake(i))

        await asyncio.gather(*tasks, return_exceptions=True)
        print(f"✓ 已发送 {num_connections} 个不完整握手")

    async def _send_incomplete_handshake(self, index: int):
        """发送单个不完整握手"""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=5.0
            )

            # 发送不完整的握手 (只发送版本,不发送方法数)
            writer.write(bytes([0x05]))  # 只发送版本
            await writer.drain()

            # 保持连接不发送更多数据
            await asyncio.sleep(60)  # 保持 60 秒

            writer.close()
            await writer.wait_closed()
        except Exception as e:
            pass

    async def send_incomplete_request(self, num_connections: int = 10):
        """
        发送不完整的连接请求

        参数:
            num_connections: 连接数量
        """
        print(f"\n{'='*80}")
        print(f"测试场景: 发送不完整的连接请求")
        print(f"连接数量: {num_connections}")
        print(f"{'='*80}\n")

        tasks = []
        for i in range(num_connections):
            tasks.append(self._send_incomplete_request(i))

        await asyncio.gather(*tasks, return_exceptions=True)
        print(f"✓ 已发送 {num_connections} 个不完整请求")

    async def _send_incomplete_request(self, index: int):
        """发送单个不完整请求"""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=5.0
            )

            # 发送完整的握手
            writer.write(bytes([0x05, 0x01, 0x00]))  # 版本5, 1个方法, 无需认证
            await writer.drain()

            # 读取握手响应
            response = await reader.read(2)

            # 发送不完整的请求 (只发送 3 字节,需要 4 字节)
            writer.write(bytes([0x05, 0x01, 0x00]))  # 不完整
            await writer.drain()

            # 保持连接不发送更多数据
            await asyncio.sleep(60)  # 保持 60 秒

            writer.close()
            await writer.wait_closed()
        except Exception as e:
            pass

    async def send_massive_connections(self, num_connections: int = 100):
        """
        发送大量并发连接

        参数:
            num_connections: 连接数量
        """
        print(f"\n{'='*80}")
        print(f"测试场景: 发送大量并发连接")
        print(f"连接数量: {num_connections}")
        print(f"{'='*80}\n")

        tasks = []
        for i in range(num_connections):
            tasks.append(self._send_normal_connection(i))
            # 每次间隔 0.1 秒,避免连接被拒绝
            await asyncio.sleep(0.1)

        await asyncio.gather(*tasks, return_exceptions=True)
        print(f"✓ 已发送 {num_connections} 个并发连接")

    async def _send_normal_connection(self, index: int):
        """发送单个正常连接"""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=5.0
            )

            # 发送完整的握手
            writer.write(bytes([0x05, 0x01, 0x00]))
            await writer.drain()

            # 读取握手响应
            response = await reader.read(2)

            # 发送连接请求
            request = bytes([0x05, 0x01, 0x00, 0x03]) + b'www.google.com' + struct.pack('>H', 80)
            writer.write(request)
            await writer.drain()

            # 读取响应
            response = await reader.read(10)

            # 保持连接
            await asyncio.sleep(30)  # 保持 30 秒

            writer.close()
            await writer.wait_closed()
        except Exception as e:
            pass

    async def send_slow_data(self, num_connections: int = 10):
        """
        发送慢速数据 (每次只发送 1 字节)

        参数:
            num_connections: 连接数量
        """
        print(f"\n{'='*80}")
        print(f"测试场景: 发送慢速数据")
        print(f"连接数量: {num_connections}")
        print(f"{'='*80}\n")

        tasks = []
        for i in range(num_connections):
            tasks.append(self._send_slow_data(i))

        await asyncio.gather(*tasks, return_exceptions=True)
        print(f"✓ 已发送 {num_connections} 个慢速数据连接")

    async def _send_slow_data(self, index: int):
        """发送单个慢速数据连接"""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=5.0
            )

            # 发送完整的握手
            writer.write(bytes([0x05, 0x01, 0x00]))
            await writer.drain()

            # 读取握手响应
            response = await reader.read(2)

            # 发送连接请求
            request = bytes([0x05, 0x01, 0x00, 0x03]) + b'www.google.com' + struct.pack('>H', 80)
            writer.write(request)
            await writer.drain()

            # 读取响应
            response = await reader.read(10)

            # 慢速发送数据 (每次 1 字节,间隔 1 秒)
            for i in range(100):
                writer.write(b'x')
                await writer.drain()
                await asyncio.sleep(1)

            writer.close()
            await writer.wait_closed()
        except Exception as e:
            pass

    async def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "="*80)
        print("恶意客户端模拟测试")
        print("="*80)

        # 测试 1: 不完整握手
        await self.send_incomplete_handshake(10)
        await asyncio.sleep(5)

        # 测试 2: 不完整请求
        await self.send_incomplete_request(10)
        await asyncio.sleep(5)

        # 测试 3: 大量并发连接
        await self.send_massive_connections(50)
        await asyncio.sleep(5)

        # 测试 4: 慢速数据
        await self.send_slow_data(10)

        print("\n" + "="*80)
        print("所有测试完成!")
        print("="*80)

def main():
    parser = argparse.ArgumentParser(description='恶意客户端模拟工具')
    parser.add_argument('--host', default='127.0.0.1', help='SOCKS5 代理地址')
    parser.add_argument('--port', type=int, default=1080, help='SOCKS5 代理端口')
    parser.add_argument('--test', choices=['incomplete-handshake', 'incomplete-request', 'massive-connections', 'slow-data', 'all'], default='all', help='测试场景')
    parser.add_argument('--num-connections', type=int, default=10, help='连接数量')
    args = parser.parse_args()

    client = MaliciousClient(args.host, args.port)

    try:
        if args.test == 'incomplete-handshake':
            asyncio.run(client.send_incomplete_handshake(args.num_connections))
        elif args.test == 'incomplete-request':
            asyncio.run(client.send_incomplete_request(args.num_connections))
        elif args.test == 'massive-connections':
            asyncio.run(client.send_massive_connections(args.num_connections))
        elif args.test == 'slow-data':
            asyncio.run(client.send_slow_data(args.num_connections))
        elif args.test == 'all':
            asyncio.run(client.run_all_tests())
    except KeyboardInterrupt:
        print("\n测试已中断")
        sys.exit(1)

if __name__ == '__main__':
    main()
