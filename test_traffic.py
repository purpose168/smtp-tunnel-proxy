#!/usr/bin/env python3
"""
Traffic 功能验证测试脚本

此脚本用于验证 traffic.py 功能是否正确集成到项目中，
并测试所有流量整形功能是否正常工作。

测试内容:
1. TrafficShaper 类导入测试
2. 配置集成测试
3. 数据填充功能测试
4. 延迟功能测试
5. 虚拟数据生成测试
6. 数据解填充功能测试
7. 性能影响测试

使用方法:
    python3 test_traffic.py

输出:
    - 控制台输出测试结果
    - 生成 traffic_test_report.txt 测试报告
"""

import sys
import os
import time
import asyncio
from typing import List, Dict, Any

# 测试结果存储
test_results = {
    'total': 0,
    'passed': 0,
    'failed': 0,
    'tests': []
}

def log_test(test_name: str, passed: bool, message: str, duration: float = 0.0):
    """
    记录测试结果
    
    Args:
        test_name: 测试名称
        passed: 是否通过
        message: 测试消息
        duration: 测试耗时（秒）
    """
    test_results['total'] += 1
    if passed:
        test_results['passed'] += 1
        status = "✓ PASS"
    else:
        test_results['failed'] += 1
        status = "✗ FAIL"
    
    result = {
        'name': test_name,
        'passed': passed,
        'message': message,
        'duration': duration
    }
    test_results['tests'].append(result)
    
    print(f"{status} | {test_name} | {duration:.3f}s | {message}")

def test_1_import_traffic_shaper() -> bool:
    """
    测试 1: TrafficShaper 类导入测试
    
    验证 traffic.py 模块可以正确导入 TrafficShaper 类。
    """
    test_name = "TrafficShaper 类导入"
    start_time = time.time()
    
    try:
        from traffic import TrafficShaper
        
        # 验证类属性
        assert hasattr(TrafficShaper, 'PAD_SIZES'), "缺少 PAD_SIZES 属性"
        assert hasattr(TrafficShaper, '__init__'), "缺少 __init__ 方法"
        assert hasattr(TrafficShaper, 'delay'), "缺少 delay 方法"
        assert hasattr(TrafficShaper, 'pad_data'), "缺少 pad_data 方法"
        assert hasattr(TrafficShaper, 'unpad_data'), "缺少 unpad_data 方法"
        assert hasattr(TrafficShaper, 'should_send_dummy'), "缺少 should_send_dummy 方法"
        assert hasattr(TrafficShaper, 'generate_dummy_data'), "缺少 generate_dummy_data 方法"
        
        duration = time.time() - start_time
        log_test(test_name, True, "TrafficShaper 类导入成功，所有方法可用", duration)
        return True
    except Exception as e:
        duration = time.time() - start_time
        log_test(test_name, False, f"导入失败: {e}", duration)
        return False

def test_2_config_integration() -> bool:
    """
    测试 2: 配置集成测试
    
    验证 ServerConfig 和 ClientConfig 包含 traffic 相关配置项。
    """
    test_name = "配置集成"
    start_time = time.time()
    
    try:
        from config import ServerConfig, ClientConfig
        
        # 验证 ServerConfig
        server_config = ServerConfig()
        assert hasattr(server_config, 'traffic_enabled'), "ServerConfig 缺少 traffic_enabled"
        assert hasattr(server_config, 'traffic_min_delay'), "ServerConfig 缺少 traffic_min_delay"
        assert hasattr(server_config, 'traffic_max_delay'), "ServerConfig 缺少 traffic_max_delay"
        assert hasattr(server_config, 'traffic_dummy_probability'), "ServerConfig 缺少 traffic_dummy_probability"
        
        # 验证 ClientConfig
        client_config = ClientConfig(server_host="test")
        assert hasattr(client_config, 'traffic_enabled'), "ClientConfig 缺少 traffic_enabled"
        assert hasattr(client_config, 'traffic_min_delay'), "ClientConfig 缺少 traffic_min_delay"
        assert hasattr(client_config, 'traffic_max_delay'), "ClientConfig 缺少 traffic_max_delay"
        assert hasattr(client_config, 'traffic_dummy_probability'), "ClientConfig 缺少 traffic_dummy_probability"
        
        # 验证默认值
        assert server_config.traffic_enabled == False, "traffic_enabled 默认值错误"
        assert server_config.traffic_min_delay == 50, "traffic_min_delay 默认值错误"
        assert server_config.traffic_max_delay == 500, "traffic_max_delay 默认值错误"
        assert server_config.traffic_dummy_probability == 0.1, "traffic_dummy_probability 默认值错误"
        
        duration = time.time() - start_time
        log_test(test_name, True, "配置集成成功，所有配置项可用", duration)
        return True
    except Exception as e:
        duration = time.time() - start_time
        log_test(test_name, False, f"配置集成失败: {e}", duration)
        return False

def test_3_pad_data() -> bool:
    """
    测试 3: 数据填充功能测试
    
    验证 TrafficShaper.pad_data() 方法能够正确填充数据到标准大小。
    """
    test_name = "数据填充功能"
    start_time = time.time()
    
    try:
        from traffic import TrafficShaper
        
        shaper = TrafficShaper()
        
        # 测试不同大小的数据
        test_cases = [
            (b'hello', 4096),         # 小数据，填充到 4KB
            (b'x' * 100, 4096),       # 中等数据，填充到 4KB
            (b'x' * 1000, 4096),     # 较大数据，填充到 4KB
            (b'x' * 4000, 4096),     # 接近填充边界，填充到 4KB
            (b'x' * 5000, 8192),     # 需要填充到 8KB
            (b'x' * 10000, 16384),   # 需要填充到 16KB
        ]
        
        for data, expected_size in test_cases:
            padded = shaper.pad_data(data)
            actual_size = len(padded)
            
            # 验证填充后的大小
            assert actual_size == expected_size, f"填充后大小错误: 期望 {expected_size}, 实际 {actual_size}"
            
            # 验证可以解填充
            unpadded = TrafficShaper.unpad_data(padded)
            assert unpadded == data, "解填充后数据不匹配"
        
        duration = time.time() - start_time
        log_test(test_name, True, f"数据填充功能正常，测试了 {len(test_cases)} 个用例", duration)
        return True
    except Exception as e:
        duration = time.time() - start_time
        log_test(test_name, False, f"数据填充测试失败: {e}", duration)
        return False

async def test_4_delay() -> bool:
    """
    测试 4: 延迟功能测试
    
    验证 TrafficShaper.delay() 方法能够正确添加随机延迟。
    """
    test_name = "延迟功能"
    start_time = time.time()
    
    try:
        from traffic import TrafficShaper
        
        shaper = TrafficShaper(min_delay_ms=10, max_delay_ms=50)
        
        # 测试多次延迟
        delays = []
        for i in range(10):
            delay_start = time.time()
            await shaper.delay()
            delay_time = (time.time() - delay_start) * 1000  # 转换为毫秒
            delays.append(delay_time)
        
        # 验证延迟范围
        min_delay = min(delays)
        max_delay = max(delays)
        avg_delay = sum(delays) / len(delays)
        
        assert min_delay >= 10, f"最小延迟 {min_delay}ms 小于配置的 10ms"
        assert max_delay <= 50, f"最大延迟 {max_delay}ms 大于配置的 50ms"
        
        duration = time.time() - start_time
        log_test(test_name, True, f"延迟功能正常，平均延迟 {avg_delay:.1f}ms", duration)
        return True
    except Exception as e:
        duration = time.time() - start_time
        log_test(test_name, False, f"延迟测试失败: {e}", duration)
        return False

def test_5_generate_dummy_data() -> bool:
    """
    测试 5: 虚拟数据生成测试
    
    验证 TrafficShaper.generate_dummy_data() 方法能够生成随机数据。
    """
    test_name = "虚拟数据生成"
    start_time = time.time()
    
    try:
        from traffic import TrafficShaper
        
        shaper = TrafficShaper()
        
        # 测试生成不同大小的虚拟数据
        test_cases = [
            (100, 1000),
            (500, 5000),
            (1000, 10000),
        ]
        
        for min_size, max_size in test_cases:
            dummy_data = shaper.generate_dummy_data(min_size, max_size)
            
            # 验证数据大小
            assert min_size <= len(dummy_data) <= max_size, \
                f"虚拟数据大小错误: 期望 {min_size}-{max_size}, 实际 {len(dummy_data)}"
            
            # 验证数据是随机的（至少有一些变化）
            dummy_data2 = shaper.generate_dummy_data(min_size, max_size)
            assert dummy_data != dummy_data2, "虚拟数据不是随机的"
        
        duration = time.time() - start_time
        log_test(test_name, True, f"虚拟数据生成功能正常，测试了 {len(test_cases)} 个用例", duration)
        return True
    except Exception as e:
        duration = time.time() - start_time
        log_test(test_name, False, f"虚拟数据生成测试失败: {e}", duration)
        return False

def test_6_should_send_dummy() -> bool:
    """
    测试 6: 虚拟消息概率测试
    
    验证 TrafficShaper.should_send_dummy() 方法能够根据概率正确判断。
    """
    test_name = "虚拟消息概率"
    start_time = time.time()
    
    try:
        from traffic import TrafficShaper
        
        # 测试不同的概率
        test_cases = [
            (0.0, 0),    # 概率 0，应该总是返回 False
            (1.0, 100),  # 概率 1.0，应该总是返回 True
            (0.5, 100),  # 概率 0.5，应该大约 50% 返回 True
        ]
        
        for probability, iterations in test_cases:
            shaper = TrafficShaper(dummy_probability=probability)
            true_count = 0
            
            for i in range(iterations):
                if shaper.should_send_dummy():
                    true_count += 1
            
            # 验证结果
            if probability == 0.0:
                assert true_count == 0, f"概率 {probability} 时应该总是返回 False"
            elif probability == 1.0:
                assert true_count == iterations, f"概率 {probability} 时应该总是返回 True"
            elif probability == 0.5:
                # 允许 20% 的误差范围
                expected = iterations * 0.5
                assert abs(true_count - expected) / expected < 0.2, \
                    f"概率 {probability} 时结果偏差过大: {true_count}/{iterations}"
        
        duration = time.time() - start_time
        log_test(test_name, True, f"虚拟消息概率功能正常，测试了 {len(test_cases)} 个用例", duration)
        return True
    except Exception as e:
        duration = time.time() - start_time
        log_test(test_name, False, f"虚拟消息概率测试失败: {e}", duration)
        return False

def test_7_performance_impact() -> bool:
    """
    测试 7: 性能影响测试
    
    验证流量整形功能对性能的影响在可接受范围内。
    """
    test_name = "性能影响"
    start_time = time.time()
    
    try:
        from traffic import TrafficShaper
        
        shaper = TrafficShaper(min_delay_ms=10, max_delay_ms=20)
        
        # 测试填充性能
        test_data = b'x' * 1000
        iterations = 1000
        
        pad_start = time.time()
        for i in range(iterations):
            padded = shaper.pad_data(test_data)
        pad_duration = time.time() - pad_start
        
        # 验证性能（每次填充应该小于 1ms）
        avg_pad_time = (pad_duration / iterations) * 1000  # 转换为毫秒
        assert avg_pad_time < 1.0, f"填充性能过慢: 平均 {avg_pad_time:.3f}ms"
        
        duration = time.time() - start_time
        log_test(test_name, True, f"性能影响可接受，平均填充时间 {avg_pad_time:.3f}ms", duration)
        return True
    except Exception as e:
        duration = time.time() - start_time
        log_test(test_name, False, f"性能影响测试失败: {e}", duration)
        return False

def generate_report() -> str:
    """
    生成测试报告
    
    Returns:
        str: 测试报告内容
    """
    report = []
    report.append("=" * 80)
    report.append("Traffic 功能验证测试报告")
    report.append("=" * 80)
    report.append("")
    
    # 测试摘要
    report.append("测试摘要:")
    report.append(f"  总测试数: {test_results['total']}")
    report.append(f"  通过: {test_results['passed']}")
    report.append(f"  失败: {test_results['failed']}")
    report.append(f"  通过率: {test_results['passed']/test_results['total']*100:.1f}%")
    report.append("")
    
    # 详细测试结果
    report.append("详细测试结果:")
    report.append("-" * 80)
    for test in test_results['tests']:
        status = "✓ PASS" if test['passed'] else "✗ FAIL"
        report.append(f"  {status} | {test['name']}")
        report.append(f"         耗时: {test['duration']:.3f}s")
        report.append(f"         消息: {test['message']}")
        report.append("")
    
    # 风险评估
    report.append("风险评估:")
    report.append("-" * 80)
    
    if test_results['failed'] == 0:
        report.append("  ✓ 所有测试通过，功能正常")
        report.append("  ✓ 无已知风险")
    else:
        report.append("  ✗ 部分测试失败，需要修复")
        report.append("  ⚠ 可能影响 DPI 规避效果")
    
    report.append("")
    report.append("=" * 80)
    
    return "\n".join(report)

async def run_all_tests():
    """
    运行所有测试
    """
    print("")
    print("=" * 80)
    print("Traffic 功能验证测试")
    print("=" * 80)
    print("")
    
    # 运行同步测试
    test_1_import_traffic_shaper()
    test_2_config_integration()
    test_3_pad_data()
    test_5_generate_dummy_data()
    test_6_should_send_dummy()
    test_7_performance_impact()
    
    # 运行异步测试
    await test_4_delay()
    
    # 生成报告
    print("")
    print(generate_report())
    
    # 保存报告到文件
    report_content = generate_report()
    report_file = "traffic_test_report.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report_content)
    
    print(f"\n测试报告已保存到: {report_file}")
    
    # 返回测试结果
    return test_results['failed'] == 0

def main():
    """
    主函数
    """
    try:
        # 运行异步测试
        success = asyncio.run(run_all_tests())
        
        # 根据测试结果返回退出码
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ 测试执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)

if __name__ == '__main__':
    main()
