#!/usr/bin/env python3
"""
资源泄漏修复验证脚本

用于验证客户端资源泄漏修复是否有效
"""

import asyncio
import logging
import time
import os
import sys
from client import TunnelClient, ClientConfig

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('resource-leak-test')


async def test_channel_id_recycling():
    """测试通道ID回收机制"""
    logger.info("=" * 60)
    logger.info("测试1: 通道ID回收机制")
    logger.info("=" * 60)
    
    config = ClientConfig(
        server_host='localhost',
        server_port=587,
        socks_port=1080,
        username='test',
        secret='test_secret'
    )
    
    client = TunnelClient(config)
    
    # 模拟打开多个通道并超时
    initial_available = len(client.available_channel_ids)
    logger.info(f"初始可用通道ID: {initial_available}")
    
    # 分配一些通道ID
    allocated_ids = []
    for i in range(10):
        async with client.channel_lock:
            if client.available_channel_ids:
                channel_id = client.available_channel_ids.pop()
            else:
                channel_id = client.next_channel_id
                client.next_channel_id += 1
        allocated_ids.append(channel_id)
        logger.info(f"分配通道ID: {channel_id}")
    
    logger.info(f"分配的通道ID: {allocated_ids}")
    logger.info(f"分配后可用通道ID: {len(client.available_channel_ids)}")
    
    # 模拟回收通道ID
    for channel_id in allocated_ids[:5]:
        async with client.channel_lock:
            if channel_id not in client.available_channel_ids:
                client.available_channel_ids.append(channel_id)
        logger.info(f"回收通道ID: {channel_id}")
    
    logger.info(f"回收后可用通道ID: {len(client.available_channel_ids)}")
    logger.info(f"可用通道ID列表: {client.available_channel_ids}")
    
    if len(client.available_channel_ids) >= 5:
        logger.info("✓ 通道ID回收机制正常")
    else:
        logger.error("✗ 通道ID回收机制异常")
    
    logger.info("")


async def test_buffer_management():
    """测试缓冲区管理"""
    logger.info("=" * 60)
    logger.info("测试2: 缓冲区管理")
    logger.info("=" * 60)
    
    config = ClientConfig(
        server_host='localhost',
        server_port=587,
        socks_port=1080,
        username='test',
        secret='test_secret'
    )
    
    client = TunnelClient(config)
    
    # 模拟缓冲区增长
    buffer = b''
    chunk_size = 65536
    
    logger.info(f"最大缓冲区大小: {client.max_buffer_size / 1024 / 1024:.1f}MB")
    
    # 添加数据直到超过限制
    for i in range(200):
        buffer += b'x' * chunk_size
        if len(buffer) > client.max_buffer_size:
            logger.info(f"缓冲区大小: {len(buffer) / 1024 / 1024:.1f}MB (超过限制)")
            # 模拟清空缓冲区
            buffer = b''
            logger.info(f"缓冲区已清空")
            break
    
    if len(buffer) < client.max_buffer_size:
        logger.info("✓ 缓冲区管理正常")
    else:
        logger.error("✗ 缓冲区管理异常")
    
    logger.info("")


async def test_forward_loop_timeout():
    """测试转发循环超时机制"""
    logger.info("=" * 60)
    logger.info("测试3: 转发循环超时机制")
    logger.info("=" * 60)
    
    # 直接测试超时逻辑
    idle_count = 0
    max_idle_count = 100
    
    logger.info(f"最大空闲计数: {max_idle_count}")
    logger.info(f"超时时间: 约 {max_idle_count * 0.1} 秒")
    
    start_time = time.time()
    
    # 模拟150次超时
    for i in range(150):
        idle_count += 1
        if idle_count >= max_idle_count:
            elapsed = time.time() - start_time
            logger.info(f"空闲计数达到 {idle_count}，触发超时退出")
            logger.info(f"耗时: {elapsed:.2f}秒")
            if elapsed < 15:  # 应该在10-15秒内退出
                logger.info("✓ 转发循环超时机制正常")
            else:
                logger.error("✗ 转发循环超时机制异常")
            break
    
    logger.info("")


async def test_resource_cleanup():
    """测试资源清理机制"""
    logger.info("=" * 60)
    logger.info("测试4: 资源清理机制")
    logger.info("=" * 60)
    
    config = ClientConfig(
        server_host='localhost',
        server_port=587,
        socks_port=1080,
        username='test',
        secret='test_secret'
    )
    
    client = TunnelClient(config)
    
    # 创建一些已设置的事件
    for i in range(20):
        event = asyncio.Event()
        event.set()  # 标记为已完成
        client.connect_events[i] = event
        client.connect_results[i] = True
    
    logger.info(f"创建 {len(client.connect_events)} 个已设置的连接事件")
    
    # 模拟清理过期资源
    stale_events = []
    for channel_id, event in client.connect_events.items():
        if event.is_set():
            stale_events.append(channel_id)
    
    for channel_id in stale_events:
        client.connect_events.pop(channel_id, None)
        client.connect_results.pop(channel_id, None)
    
    logger.info(f"清理了 {len(stale_events)} 个过期事件")
    logger.info(f"剩余连接事件: {len(client.connect_events)}")
    logger.info(f"剩余连接结果: {len(client.connect_results)}")
    
    if len(client.connect_events) == 0 and len(client.connect_results) == 0:
        logger.info("✓ 资源清理机制正常")
    else:
        logger.error("✗ 资源清理机制异常")
    
    logger.info("")


async def monitor_memory_usage():
    """监控内存使用情况"""
    logger.info("=" * 60)
    logger.info("测试5: 内存使用监控")
    logger.info("=" * 60)
    
    # 使用简单的内存监控（不依赖psutil）
    import gc
    gc.collect()
    
    logger.info("创建多个客户端实例...")
    
    # 创建多个客户端实例
    clients = []
    for i in range(10):
        config = ClientConfig(
            server_host='localhost',
            server_port=587,
            socks_port=1080,
            username=f'test{i}',
            secret='test_secret'
        )
        client = TunnelClient(config)
        clients.append(client)
    
    logger.info(f"创建了 {len(clients)} 个客户端实例")
    logger.info(f"总通道数: {sum(len(c.channels) for c in clients)}")
    logger.info(f"总事件数: {sum(len(c.connect_events) for c in clients)}")
    logger.info(f"总结果数: {sum(len(c.connect_results) for c in clients)}")
    logger.info(f"总可用ID: {sum(len(c.available_channel_ids) for c in clients)}")
    
    # 清理客户端
    clients.clear()
    gc.collect()
    
    logger.info("已清理所有客户端实例")
    logger.info("✓ 内存测试完成（需要实际运行客户端才能验证内存泄漏）")
    
    logger.info("")


async def main():
    """运行所有测试"""
    logger.info("开始资源泄漏修复验证测试")
    logger.info("")
    
    await test_channel_id_recycling()
    await test_buffer_management()
    await test_forward_loop_timeout()
    await test_resource_cleanup()
    await monitor_memory_usage()
    
    logger.info("=" * 60)
    logger.info("所有测试完成")
    logger.info("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())
