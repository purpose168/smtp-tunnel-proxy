#!/usr/bin/env python3
"""
负载测试脚本 - 测试 SMTP 隧道客户端在不同负载下的表现

功能:
1. 模拟多个并发 SOCKS5 连接
2. 测试连接建立和断开的稳定性
3. 监控客户端的进程和资源使用情况
4. 验证资源是否正确释放
"""

import asyncio
import socket
import struct
import time
import argparse
import subprocess
import sys
from typing import List, Tuple

class SOCKS5TestClient:
    """SOCKS5 测试客户端"""

    def __init__(self, socks_host: str = '127.0.0.1', socks_port: int = 1080):
        self.socks_host = socks_host
        self.socks_port = socks_port

    async def connect(self, target_host: str, target_port: int, duration: int = 10) -> bool:
        """
        通过 SOCKS5 代理连接到目标主机

        参数:
            target_host: 目标主机
            target_port: 目标端口
            duration: 连接持续时间 (秒)

        返回:
            bool: 连接是否成功
        """
        try:
            # 连接到 SOCKS5 代理
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.socks_host, self.socks_port),
                timeout=5.0
            )

            # SOCKS5 握手
            writer.write(bytes([0x05, 0x01, 0x00]))  # 版本5, 1个方法, 无需认证
            await writer.drain()

            response = await reader.read(2)
            if len(response) != 2 or response[0] != 0x05 or response[1] != 0x00:
                writer.close()
                await writer.wait_closed()
                return False

            # 发送连接请求
            if '.' in target_host:
                # 域名
                host_bytes = target_host.encode('utf-8')
                request = bytes([0x05, 0x01, 0x00, 0x03, len(host_bytes)]) + host_bytes + struct.pack('>H', target_port)
            else:
                # IPv4
                addr_bytes = socket.inet_aton(target_host)
                request = bytes([0x05, 0x01, 0x00, 0x01]) + addr_bytes + struct.pack('>H', target_port)

            writer.write(request)
            await writer.drain()

            # 读取响应
            response = await reader.read(10)
            if len(response) < 4 or response[0] != 0x05 or response[1] != 0x00:
                writer.close()
                await writer.wait_closed()
                return False

            # 保持连接一段时间
            start_time = time.time()
            while time.time() - start_time < duration:
                try:
                    data = await asyncio.wait_for(reader.read(1024), timeout=1.0)
                    if not data:
                        break
                except asyncio.TimeoutError:
                    continue

            # 关闭连接
            writer.close()
            await writer.wait_closed()
            return True

        except Exception as e:
            return False

async def test_single_connection(socks_host: str, socks_port: int, target_host: str, target_port: int) -> Tuple[bool, float]:
    """
    测试单个连接

    返回:
        Tuple[bool, float]: (是否成功, 耗时秒数)
    """
    client = SOCKS5TestClient(socks_host, socks_port)
    start_time = time.time()

    success = await client.connect(target_host, target_port, duration=5)

    elapsed = time.time() - start_time
    return success, elapsed

async def test_concurrent_connections(socks_host: str, socks_port: int, num_connections: int, target_host: str, target_port: int):
    """
    测试并发连接

    参数:
        socks_host: SOCKS5 代理地址
        socks_port: SOCKS5 代理端口
        num_connections: 并发连接数
        target_host: 目标主机
        target_port: 目标端口
    """
    print(f"\n{'='*80}")
    print(f"测试场景: 并发连接")
    print(f"连接数量: {num_connections}")
    print(f"目标: {target_host}:{target_port}")
    print(f"{'='*80}\n")

    start_time = time.time()

    # 创建所有连接任务
    tasks = [
        test_single_connection(socks_host, socks_port, target_host, target_port)
        for _ in range(num_connections)
    ]

    # 等待所有任务完成
    results = await asyncio.gather(*tasks, return_exceptions=True)

    elapsed = time.time() - start_time

    # 统计结果
    success_count = sum(1 for r in results if isinstance(r, tuple) and r[0])
    failure_count = num_connections - success_count
    avg_time = sum(r[1] for r in results if isinstance(r, tuple)) / len(results) if results else 0

    print(f"测试完成!")
    print(f"  总耗时: {elapsed:.2f} 秒")
    print(f"  成功连接: {success_count}")
    print(f"  失败连接: {failure_count}")
    print(f"  平均耗时: {avg_time:.2f} 秒")
    print(f"  吞吐量: {num_connections/elapsed:.2f} 连接/秒")

    return success_count, failure_count, elapsed

async def test_repeated_connections(socks_host: str, socks_port: int, num_connections: int, target_host: str, target_port: int):
    """
    测试重复连接 (串行)

    参数:
        socks_host: SOCKS5 代理地址
        socks_port: SOCKS5 代理端口
        num_connections: 连接总数
        target_host: 目标主机
        target_port: 目标端口
    """
    print(f"\n{'='*80}")
    print(f"测试场景: 重复连接 (串行)")
    print(f"连接数量: {num_connections}")
    print(f"目标: {target_host}:{target_port}")
    print(f"{'='*80}\n")

    start_time = time.time()
    success_count = 0
    failure_count = 0

    for i in range(num_connections):
        success, elapsed = await test_single_connection(socks_host, socks_port, target_host, target_port)
        if success:
            success_count += 1
        else:
            failure_count += 1

        # 显示进度
        if (i + 1) % 10 == 0:
            print(f"进度: {i+1}/{num_connections} (成功: {success_count}, 失败: {failure_count})")

    total_elapsed = time.time() - start_time

    print(f"\n测试完成!")
    print(f"  总耗时: {total_elapsed:.2f} 秒")
    print(f"  成功连接: {success_count}")
    print(f"  失败连接: {failure_count}")
    print(f"  平均耗时: {total_elapsed/num_connections:.2f} 秒/连接")
    print(f"  吞吐量: {num_connections/total_elapsed:.2f} 连接/秒")

    return success_count, failure_count, total_elapsed

async def test_long_running_connection(socks_host: str, socks_port: int, target_host: str, target_port: int, duration: int):
    """
    测试长时间运行的连接

    参数:
        socks_host: SOCKS5 代理地址
        socks_port: SOCKS5 代理端口
        target_host: 目标主机
        target_port: 目标端口
        duration: 连接持续时间 (秒)
    """
    print(f"\n{'='*80}")
    print(f"测试场景: 长时间运行连接")
    print(f"持续时间: {duration} 秒")
    print(f"目标: {target_host}:{target_port}")
    print(f"{'='*80}\n")

    client = SOCKS5TestClient(socks_host, socks_port)
    start_time = time.time()

    success = await client.connect(target_host, target_port, duration=duration)

    elapsed = time.time() - start_time

    print(f"测试完成!")
    print(f"  总耗时: {elapsed:.2f} 秒")
    print(f"  连接状态: {'成功' if success else '失败'}")

    return success, elapsed

async def test_connection_leak(socks_host: str, socks_port: int, num_connections: int, target_host: str, target_port: int):
    """
    测试连接泄漏

    参数:
        socks_host: SOCKS5 代理地址
        socks_port: SOCKS5 代理端口
        num_connections: 连接总数
        target_host: 目标主机
        target_port: 目标端口
    """
    print(f"\n{'='*80}")
    print(f"测试场景: 连接泄漏检测")
    print(f"连接数量: {num_connections}")
    print(f"目标: {target_host}:{target_port}")
    print(f"{'='*80}\n")

    # 获取初始进程数量
    def get_process_count():
        try:
            result = subprocess.run(
                ['ps', 'aux'],
                capture_output=True,
                text=True
            )
            return result.stdout.count('client.py')
        except:
            return 0

    initial_count = get_process_count()
    print(f"初始进程数量: {initial_count}")

    # 执行连接测试
    for i in range(num_connections):
        success, _ = await test_single_connection(socks_host, socks_port, target_host, target_port)

        # 每10个连接检查一次进程数量
        if (i + 1) % 10 == 0:
            current_count = get_process_count()
            print(f"进度: {i+1}/{num_connections}, 当前进程数量: {current_count}")

            # 如果进程数量持续增长,可能存在泄漏
            if current_count > initial_count + 5:
                print(f"  警告: 进程数量显著增加! 可能存在泄漏")

    # 最终检查
    final_count = get_process_count()
    print(f"\n最终进程数量: {final_count}")
    print(f"进程数量变化: {final_count - initial_count}")

    if final_count > initial_count + 5:
        print("  警告: 检测到可能的进程泄漏!")
        return False
    else:
        print("  正常: 进程数量稳定")
        return True

async def run_all_tests(socks_host: str, socks_port: int, target_host: str, target_port: int):
    """
    运行所有测试

    参数:
        socks_host: SOCKS5 代理地址
        socks_port: SOCKS5 代理端口
        target_host: 目标主机
        target_port: 目标端口
    """
    print("\n" + "="*80)
    print("SMTP 隧道客户端负载测试")
    print("="*80)

    # 测试 1: 小规模并发连接
    await test_concurrent_connections(socks_host, socks_port, 10, target_host, target_port)
    await asyncio.sleep(2)

    # 测试 2: 中等规模并发连接
    await test_concurrent_connections(socks_host, socks_port, 50, target_host, target_port)
    await asyncio.sleep(2)

    # 测试 3: 重复连接
    await test_repeated_connections(socks_host, socks_port, 100, target_host, target_port)
    await asyncio.sleep(2)

    # 测试 4: 长时间运行连接
    await test_long_running_connection(socks_host, socks_port, target_host, target_port, 30)
    await asyncio.sleep(2)

    # 测试 5: 连接泄漏检测
    await test_connection_leak(socks_host, socks_port, 200, target_host, target_port)

    print("\n" + "="*80)
    print("所有测试完成!")
    print("="*80)

def main():
    parser = argparse.ArgumentParser(description='SMTP 隧道客户端负载测试')
    parser.add_argument('--socks-host', default='127.0.0.1', help='SOCKS5 代理地址')
    parser.add_argument('--socks-port', type=int, default=1080, help='SOCKS5 代理端口')
    parser.add_argument('--target-host', default='www.google.com', help='目标主机')
    parser.add_argument('--target-port', type=int, default=80, help='目标端口')
    args = parser.parse_args()

    try:
        asyncio.run(run_all_tests(args.socks_host, args.socks_port, args.target_host, args.target_port))
    except KeyboardInterrupt:
        print("\n测试已中断")
        sys.exit(1)

if __name__ == '__main__':
    main()
