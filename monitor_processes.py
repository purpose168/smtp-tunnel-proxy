#!/usr/bin/env python3
"""
进程监控脚本 - 监控 SMTP 隧道客户端的进程数量变化

功能:
1. 监控指定进程的 PID 数量变化
2. 记录进程数量随时间变化的趋势
3. 输出 CSV 格式的数据,可用于图表生成
"""

import psutil
import time
import argparse
import csv
from datetime import datetime
from typing import List, Dict

def get_process_count(process_name: str) -> int:
    """
    获取指定名称的进程数量

    参数:
        process_name: 进程名称 (如: python3)

    返回:
        int: 进程数量
    """
    count = 0
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            if proc.info['name'] == process_name:
                # 检查命令行参数,确保是目标进程
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if 'client.py' in cmdline:
                    count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return count

def get_process_details(process_name: str) -> List[Dict]:
    """
    获取指定进程的详细信息

    参数:
        process_name: 进程名称

    返回:
        List[Dict]: 进程详细信息列表
    """
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time', 'memory_info', 'cpu_percent']):
        try:
            if proc.info['name'] == process_name:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if 'client.py' in cmdline:
                    processes.append({
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'cmdline': cmdline,
                        'create_time': datetime.fromtimestamp(proc.info['create_time']),
                        'memory_mb': proc.info['memory_info'].rss / 1024 / 1024,
                        'cpu_percent': proc.info['cpu_percent']
                    })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return processes

def monitor_processes(process_name: str, interval: int = 5, duration: int = 300, output_file: str = None):
    """
    监控进程数量变化

    参数:
        process_name: 要监控的进程名称
        interval: 监控间隔 (秒)
        duration: 监控总时长 (秒)
        output_file: 输出 CSV 文件路径
    """
    print(f"开始监控进程: {process_name}")
    print(f"监控间隔: {interval} 秒")
    print(f"监控时长: {duration} 秒")
    print("-" * 80)

    data = []
    start_time = time.time()

    try:
        while time.time() - start_time < duration:
            current_time = datetime.now()
            count = get_process_count(process_name)
            details = get_process_details(process_name)

            total_memory = sum(p['memory_mb'] for p in details)
            avg_cpu = sum(p['cpu_percent'] for p in details) / len(details) if details else 0

            record = {
                'timestamp': current_time.strftime('%Y-%m-%d %H:%M:%S'),
                'elapsed_seconds': int(time.time() - start_time),
                'process_count': count,
                'total_memory_mb': round(total_memory, 2),
                'avg_cpu_percent': round(avg_cpu, 2)
            }

            data.append(record)

            # 实时输出
            print(f"[{record['timestamp']}] 进程数: {count:3d} | "
                  f"总内存: {record['total_memory_mb']:8.2f} MB | "
                  f"平均CPU: {record['avg_cpu_percent']:5.2f}%")

            # 如果进程数量超过阈值,输出详细信息
            if count > 10:
                print(f"  警告: 进程数量过多! 详细信息:")
                for p in details:
                    print(f"    PID: {p['pid']:6d} | 内存: {p['memory_mb']:8.2f} MB | "
                          f"CPU: {p['cpu_percent']:5.2f}% | 创建时间: {p['create_time']}")
                    print(f"      命令行: {p['cmdline'][:80]}...")

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n监控已中断")

    # 输出 CSV 文件
    if output_file and data:
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        print(f"\n数据已保存到: {output_file}")

    # 输出统计信息
    if data:
        print("\n" + "=" * 80)
        print("统计信息:")
        print(f"  监控时长: {data[-1]['elapsed_seconds']} 秒")
        print(f"  最大进程数: {max(d['process_count'] for d in data)}")
        print(f"  最小进程数: {min(d['process_count'] for d in data)}")
        print(f"  平均进程数: {sum(d['process_count'] for d in data) / len(data):.2f}")
        print(f"  最大内存使用: {max(d['total_memory_mb'] for d in data):.2f} MB")
        print("=" * 80)

def main():
    parser = argparse.ArgumentParser(description='监控 SMTP 隧道客户端进程')
    parser.add_argument('--process-name', default='python3', help='要监控的进程名称')
    parser.add_argument('--interval', type=int, default=5, help='监控间隔 (秒)')
    parser.add_argument('--duration', type=int, default=300, help='监控时长 (秒)')
    parser.add_argument('--output', default='process_monitor.csv', help='输出 CSV 文件路径')
    args = parser.parse_args()

    monitor_processes(args.process_name, args.interval, args.duration, args.output)

if __name__ == '__main__':
    main()
