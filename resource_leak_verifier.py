#!/usr/bin/env python3
"""
资源泄漏验证脚本 - 验证修复后的资源使用情况

功能:
1. 模拟大量连接请求
2. 监控资源使用情况
3. 验证修复效果
"""

import asyncio
import socket
import struct
import time
import argparse
import sys
from typing import List

class ResourceLeakVerifier:
    """资源泄漏验证器"""

    def __init__(self, host: str = '127.0.0.1', port: int = 1080):
        """
        初始化验证器

        参数:
            host: SOCKS5 代理地址
            port: SOCKS5 代理端口
        """
        self.host = host
        self.port = port

    async def create_socks5_connection(self, target_host: str, target_port: int) -> bool:
        """
        创建 SOCKS5 连接

        参数:
            target_host: 目标主机
            target_port: 目标端口

        返回:
            bool: 是否成功
        """
        try:
            # 建立连接
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=5.0
            )

            # SOCKS5 握手
            writer.write(bytes([0x05, 0x01, 0x00]))
            await writer.drain()

            # 读取握手响应
            response = await asyncio.wait_for(reader.read(2), timeout=5.0)
            if len(response) < 2 or response[0] != 0x05:
                writer.close()
                await writer.wait_closed()
                return False

            # 发送连接请求
            request = bytes([0x05, 0x01, 0x00, 0x03])
            request += bytes([len(target_host)]) + target_host.encode()
            request += struct.pack('>H', target_port)
            writer.write(request)
            await writer.drain()

            # 读取连接响应
            response = await asyncio.wait_for(reader.read(10), timeout=10.0)
            if len(response) < 10 or response[1] != 0x00:
                writer.close()
                await writer.wait_closed()
                return False

            # 关闭连接
            writer.close()
            await writer.wait_closed()
            return True

        except Exception as e:
            return False

    async def test_connection_leak(self, num_connections: int = 100):
        """
        测试连接泄漏

        参数:
            num_connections: 连接数量
        """
        print(f"\n{'='*80}")
        print(f"测试场景: 连接泄漏测试")
        print(f"连接数量: {num_connections}")
        print(f"{'='*80}\n")

        success_count = 0
        fail_count = 0

        start_time = time.time()

        for i in range(num_connections):
            result = await self.create_socks5_connection('github.com', 443)
            if result:
                success_count += 1
            else:
                fail_count += 1

            if (i + 1) % 10 == 0:
                print(f"已测试 {i + 1}/{num_connections} 个连接, "
                      f"成功: {success_count}, 失败: {fail_count}")

            # 间隔 0.1 秒
            await asyncio.sleep(0.1)

        end_time = time.time()
        duration = end_time - start_time

        print(f"\n测试完成!")
        print(f"总连接数: {num_connections}")
        print(f"成功: {success_count}")
        print(f"失败: {fail_count}")
        print(f"耗时: {duration:.2f} 秒")
        print(f"平均每个连接: {duration/num_connections:.3f} 秒")

        # 等待一段时间，观察资源使用
        print(f"\n等待 30 秒，观察资源使用情况...")
        await asyncio.sleep(30)

        return {
            'total': num_connections,
            'success': success_count,
            'fail': fail_count,
            'duration': duration
        }

    async def test_concurrent_connections(self, num_connections: int = 50):
        """
        测试并发连接

        参数:
            num_connections: 并发连接数
        """
        print(f"\n{'='*80}")
        print(f"测试场景: 并发连接测试")
        print(f"并发连接数: {num_connections}")
        print(f"{'='*80}\n")

        start_time = time.time()

        # 创建所有连接
        tasks = []
        for i in range(num_connections):
            task = asyncio.create_task(self.create_socks5_connection('github.com', 443))
            tasks.append(task)

        # 等待所有连接完成
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for r in results if r is True)
        fail_count = sum(1 for r in results if r is False)

        end_time = time.time()
        duration = end_time - start_time

        print(f"\n测试完成!")
        print(f"总连接数: {num_connections}")
        print(f"成功: {success_count}")
        print(f"失败: {fail_count}")
        print(f"耗时: {duration:.2f} 秒")
        print(f"平均每个连接: {duration/num_connections:.3f} 秒")

        # 等待一段时间，观察资源使用
        print(f"\n等待 30 秒，观察资源使用情况...")
        await asyncio.sleep(30)

        return {
            'total': num_connections,
            'success': success_count,
            'fail': fail_count,
            'duration': duration
        }

    async def test_long_running_connections(self, num_connections: int = 10, duration: int = 60):
        """
        测试长时间运行的连接

        参数:
            num_connections: 连接数量
            duration: 持续时间 (秒)
        """
        print(f"\n{'='*80}")
        print(f"测试场景: 长时间运行连接测试")
        print(f"连接数量: {num_connections}")
        print(f"持续时间: {duration} 秒")
        print(f"{'='*80}\n")

        connections = []

        # 创建连接
        for i in range(num_connections):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port),
                    timeout=5.0
                )

                # SOCKS5 握手
                writer.write(bytes([0x05, 0x01, 0x00]))
                await writer.drain()

                # 读取握手响应
                response = await asyncio.wait_for(reader.read(2), timeout=5.0)
                if len(response) < 2 or response[0] != 0x05:
                    writer.close()
                    await writer.wait_closed()
                    continue

                # 发送连接请求
                request = bytes([0x05, 0x01, 0x00, 0x03])
                request += bytes([len('github.com')]) + b'github.com'
                request += struct.pack('>H', 443)
                writer.write(request)
                await writer.drain()

                # 读取连接响应
                response = await asyncio.wait_for(reader.read(10), timeout=10.0)
                if len(response) < 10 or response[1] != 0x00:
                    writer.close()
                    await writer.wait_closed()
                    continue

                connections.append((reader, writer))
                print(f"连接 {i + 1}/{num_connections} 建立成功")

            except Exception as e:
                print(f"连接 {i + 1}/{num_connections} 建立失败: {e}")

        print(f"\n成功建立 {len(connections)} 个连接")
        print(f"保持连接 {duration} 秒...")

        # 保持连接
        await asyncio.sleep(duration)

        # 关闭所有连接
        print(f"\n关闭所有连接...")
        for reader, writer in connections:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                pass

        print(f"所有连接已关闭")

        return {
            'total': num_connections,
            'success': len(connections),
            'fail': num_connections - len(connections),
            'duration': duration
        }

    async def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "="*80)
        print("资源泄漏验证测试")
        print("="*80)

        # 测试 1: 连接泄漏测试
        result1 = await self.test_connection_leak(100)
        await asyncio.sleep(10)

        # 测试 2: 并发连接测试
        result2 = await self.test_concurrent_connections(50)
        await asyncio.sleep(10)

        # 测试 3: 长时间运行连接测试
        result3 = await self.test_long_running_connections(10, 60)

        print("\n" + "="*80)
        print("所有测试完成!")
        print("="*80)

        print("\n测试结果汇总:")
        print(f"  连接泄漏测试: {result1['success']}/{result1['total']} 成功")
        print(f"  并发连接测试: {result2['success']}/{result2['total']} 成功")
        print(f"  长时间运行测试: {result3['success']}/{result3['total']} 成功")

        print("\n请检查资源使用情况:")
        print("  1. 使用 resource_exhaustion_diagnostics.py 监控资源")
        print("  2. 检查内存使用是否稳定")
        print("  3. 检查文件描述符是否泄漏")
        print("  4. 检查协程数量是否稳定")

def main():
    parser = argparse.ArgumentParser(description='资源泄漏验证脚本')
    parser.add_argument('--host', default='127.0.0.1', help='SOCKS5 代理地址')
    parser.add_argument('--port', type=int, default=1080, help='SOCKS5 代理端口')
    parser.add_argument('--test', choices=['leak', 'concurrent', 'long-running', 'all'], default='all', help='测试场景')
    parser.add_argument('--num-connections', type=int, default=100, help='连接数量')
    parser.add_argument('--duration', type=int, default=60, help='持续时间 (秒)')
    args = parser.parse_args()

    verifier = ResourceLeakVerifier(args.host, args.port)

    try:
        if args.test == 'leak':
            asyncio.run(verifier.test_connection_leak(args.num_connections))
        elif args.test == 'concurrent':
            asyncio.run(verifier.test_concurrent_connections(args.num_connections))
        elif args.test == 'long-running':
            asyncio.run(verifier.test_long_running_connections(args.num_connections, args.duration))
        elif args.test == 'all':
            asyncio.run(verifier.run_all_tests())
    except KeyboardInterrupt:
        print("\n测试已中断")
        sys.exit(1)

if __name__ == '__main__':
    main()
