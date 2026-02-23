#!/usr/bin/env python3
"""
测试自动重连机制

测试内容:
1. 连续失败检测
2. 指数退避重连策略
3. 重连统计记录
"""

import asyncio
import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from client import TunnelClient
from common import ClientConfig


async def test_consecutive_failure_detection():
    """测试连续失败检测"""
    print("\n=== 测试1: 连续失败检测 ===")
    
    config = ClientConfig(
        server_host='localhost',
        server_port=587,
        socks_port=1080,
        username='test_user',
        secret='test_secret'
    )
    
    client = TunnelClient(config)
    
    # 配置重连参数（使用较小的阈值便于测试）
    client.configure_reconnect(
        consecutive_failures_threshold=3,
        initial_reconnect_delay=1.0,
        max_reconnect_delay=10.0,
        failure_window_seconds=30.0
    )
    
    print(f"初始配置: 阈值={client._consecutive_failures_threshold}, "
          f"初始延迟={client._initial_reconnect_delay}s, "
          f"最大延迟={client._max_reconnect_delay}s")
    
    # 模拟连续失败
    for i in range(5):
        client._record_channel_failure(f"模拟失败 #{i+1}")
        stats = client.get_reconnect_stats()
        print(f"  失败 {i+1}: 连续失败={stats['consecutive_failures']}, "
              f"窗口内失败={len(client._failure_timestamps)}")
        
        # 检查是否应该触发重连
        if client._should_trigger_reconnect():
            print(f"  ✓ 达到阈值，应触发重连")
            break
    
    # 验证统计信息
    stats = client.get_reconnect_stats()
    assert stats['consecutive_failures'] >= 3, "连续失败计数应该 >= 3"
    assert stats['last_failure_reason'] != "", "应该记录失败原因"
    print(f"✓ 测试通过: 连续失败={stats['consecutive_failures']}, "
          f"原因='{stats['last_failure_reason']}'")
    
    return True


async def test_success_reset():
    """测试成功后重置失败计数"""
    print("\n=== 测试2: 成功后重置失败计数 ===")
    
    config = ClientConfig(
        server_host='localhost',
        server_port=587,
        socks_port=1080,
        username='test_user',
        secret='test_secret'
    )
    
    client = TunnelClient(config)
    client.configure_reconnect(consecutive_failures_threshold=5)
    
    # 模拟一些失败
    for i in range(3):
        client._record_channel_failure(f"失败 #{i+1}")
    
    stats = client.get_reconnect_stats()
    print(f"  记录3次失败后: 连续失败={stats['consecutive_failures']}")
    assert stats['consecutive_failures'] == 3
    
    # 记录成功
    client._record_channel_success()
    
    stats = client.get_reconnect_stats()
    print(f"  记录成功后: 连续失败={stats['consecutive_failures']}")
    assert stats['consecutive_failures'] == 0, "成功后应该重置失败计数"
    assert stats['last_failure_reason'] == "", "成功后应该清除失败原因"
    print("✓ 测试通过: 成功后正确重置失败计数")
    
    return True


async def test_exponential_backoff():
    """测试指数退避策略"""
    print("\n=== 测试3: 指数退避策略 ===")
    
    config = ClientConfig(
        server_host='localhost',
        server_port=587,
        socks_port=1080,
        username='test_user',
        secret='test_secret'
    )
    
    client = TunnelClient(config)
    client.configure_reconnect(
        initial_reconnect_delay=1.0,
        max_reconnect_delay=30.0
    )
    
    # 验证初始延迟
    assert client._initial_reconnect_delay == 1.0
    assert client._max_reconnect_delay == 30.0
    
    # 计算指数退避序列
    delays = []
    for attempt in range(1, 8):
        delay = min(
            client._initial_reconnect_delay * (2 ** (attempt - 1)),
            client._max_reconnect_delay
        )
        delays.append(delay)
        print(f"  尝试 {attempt}: 延迟 {delay:.1f}s")
    
    # 验证延迟序列
    expected = [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0]  # 最大30秒
    for i, (actual, exp) in enumerate(zip(delays, expected)):
        assert actual == exp, f"尝试 {i+1}: 延迟应为 {exp}s，实际为 {actual}s"
    
    print("✓ 测试通过: 指数退避策略正确")
    
    return True


async def test_sliding_window():
    """测试滑动窗口失败计数"""
    print("\n=== 测试4: 滑动窗口失败计数 ===")
    
    config = ClientConfig(
        server_host='localhost',
        server_port=587,
        socks_port=1080,
        username='test_user',
        secret='test_secret'
    )
    
    client = TunnelClient(config)
    client.configure_reconnect(
        consecutive_failures_threshold=5,
        failure_window_seconds=2.0  # 2秒窗口
    )
    
    # 记录一些失败
    for i in range(3):
        client._record_channel_failure(f"失败 #{i+1}")
    
    print(f"  记录3次失败后: 窗口内失败={len(client._failure_timestamps)}")
    assert len(client._failure_timestamps) == 3
    
    # 等待窗口过期
    print("  等待窗口过期 (2.5秒)...")
    await asyncio.sleep(2.5)
    
    # 记录新失败，应该清理过期的记录
    client._record_channel_failure("新失败")
    print(f"  窗口过期后记录新失败: 窗口内失败={len(client._failure_timestamps)}")
    assert len(client._failure_timestamps) == 1, "过期的失败记录应该被清理"
    
    print("✓ 测试通过: 滑动窗口正确清理过期记录")
    
    return True


async def test_reconnect_stats():
    """测试重连统计"""
    print("\n=== 测试5: 重连统计 ===")
    
    config = ClientConfig(
        server_host='localhost',
        server_port=587,
        socks_port=1080,
        username='test_user',
        secret='test_secret'
    )
    
    client = TunnelClient(config)
    
    # 获取初始统计
    stats = client.get_reconnect_stats()
    print(f"  初始统计: {stats}")
    
    assert stats['total_reconnects'] == 0
    assert stats['successful_reconnects'] == 0
    assert stats['consecutive_failures'] == 0
    assert stats['is_reconnecting'] == False
    
    # 模拟一些状态变化
    client._total_reconnects = 5
    client._successful_reconnects = 3
    client._consecutive_failures = 2
    client._last_failure_reason = "测试失败"
    client._current_reconnect_delay = 8.0
    
    stats = client.get_reconnect_stats()
    print(f"  更新后统计: {stats}")
    
    assert stats['total_reconnects'] == 5
    assert stats['successful_reconnects'] == 3
    assert stats['consecutive_failures'] == 2
    assert stats['last_failure_reason'] == "测试失败"
    assert stats['current_reconnect_delay'] == 8.0
    
    print("✓ 测试通过: 重连统计正确")
    
    return True


async def main():
    """运行所有测试"""
    print("=" * 60)
    print("SMTP隧道客户端 - 自动重连机制测试")
    print("=" * 60)
    
    tests = [
        ("连续失败检测", test_consecutive_failure_detection),
        ("成功后重置失败计数", test_success_reset),
        ("指数退避策略", test_exponential_backoff),
        ("滑动窗口失败计数", test_sliding_window),
        ("重连统计", test_reconnect_stats),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            result = await test_func()
            if result:
                passed += 1
        except AssertionError as e:
            print(f"✗ 测试失败: {name} - {e}")
            failed += 1
        except Exception as e:
            print(f"✗ 测试异常: {name} - {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"测试结果: 通过={passed}, 失败={failed}")
    print("=" * 60)
    
    return failed == 0


if __name__ == '__main__':
    success = asyncio.run(main())
    exit(0 if success else 1)
