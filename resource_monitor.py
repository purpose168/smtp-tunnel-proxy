#!/usr/bin/env python3
"""
资源监控和诊断工具 - 实时监控 SMTP 隧道客户端的资源使用情况

功能:
1. 监控进程的内存、CPU 和协程数量
2. 检测资源泄漏和异常增长
3. 提供实时告警
4. 生成诊断报告
"""

import psutil
import asyncio
import time
import argparse
import sys
from typing import Dict, List
from datetime import datetime

class ResourceMonitor:
    """资源监控器"""

    def __init__(self, process_name: str = 'python3', check_interval: int = 5):
        """
        初始化资源监控器

        参数:
            process_name: 要监控的进程名称
            check_interval: 检查间隔 (秒)
        """
        self.process_name = process_name
        self.check_interval = check_interval
        self.processes = []
        self.history = []

        # 告警阈值
        self.thresholds = {
            'memory_mb': 500,        # 内存阈值: 500MB
            'cpu_percent': 80,        # CPU 阈值: 80%
            'coroutines': 1000,       # 协程数量阈值: 1000
            'connections': 100,        # 连接数阈值: 100
            'buffer_size_mb': 10,      # 缓冲区大小阈值: 10MB
        }

    def find_processes(self) -> List[psutil.Process]:
        """
        查找目标进程

        返回:
            List[psutil.Process]: 进程列表
        """
        processes = []
        for proc in psutil.process_iter(['name', 'cmdline', 'pid']):
            try:
                if proc.info['name'] == self.process_name:
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    if 'client.py' in cmdline:
                        processes.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return processes

    def get_process_stats(self, proc: psutil.Process) -> Dict:
        """
        获取进程统计信息

        参数:
            proc: 进程对象

        返回:
            Dict: 统计信息
        """
        try:
            memory_info = proc.memory_info()
            return {
                'pid': proc.pid,
                'memory_mb': memory_info.rss / 1024 / 1024,
                'cpu_percent': proc.cpu_percent(interval=0.1),
                'num_threads': proc.num_threads(),
                'num_fds': proc.num_fds() if hasattr(proc, 'num_fds') else 0,
                'connections': len(proc.connections()) if hasattr(proc, 'connections') else 0,
                'create_time': datetime.fromtimestamp(proc.create_time())
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None

    def check_thresholds(self, stats: Dict) -> List[str]:
        """
        检查是否超过阈值

        参数:
            stats: 统计信息

        返回:
            List[str]: 告警信息列表
        """
        warnings = []

        if stats['memory_mb'] > self.thresholds['memory_mb']:
            warnings.append(f"内存使用过高: {stats['memory_mb']:.2f} MB > {self.thresholds['memory_mb']} MB")

        if stats['cpu_percent'] > self.thresholds['cpu_percent']:
            warnings.append(f"CPU 使用过高: {stats['cpu_percent']:.2f}% > {self.thresholds['cpu_percent']}%")

        if stats['connections'] > self.thresholds['connections']:
            warnings.append(f"连接数过多: {stats['connections']} > {self.thresholds['connections']}")

        if stats['num_fds'] > 1000:
            warnings.append(f"文件描述符过多: {stats['num_fds']} > 1000")

        return warnings

    def monitor_once(self) -> Dict:
        """
        执行一次监控检查

        返回:
            Dict: 监控结果
        """
        processes = self.find_processes()
        self.processes = processes

        if not processes:
            return {
                'timestamp': datetime.now(),
                'process_count': 0,
                'total_memory_mb': 0,
                'total_cpu_percent': 0,
                'total_connections': 0,
                'warnings': ['未找到目标进程']
            }

        total_memory = 0
        total_cpu = 0
        total_connections = 0
        all_warnings = []

        for proc in processes:
            stats = self.get_process_stats(proc)
            if stats:
                total_memory += stats['memory_mb']
                total_cpu += stats['cpu_percent']
                total_connections += stats['connections']

                warnings = self.check_thresholds(stats)
                all_warnings.extend(warnings)

        result = {
            'timestamp': datetime.now(),
            'process_count': len(processes),
            'total_memory_mb': total_memory,
            'total_cpu_percent': total_cpu,
            'total_connections': total_connections,
            'warnings': all_warnings
        }

        self.history.append(result)
        return result

    def print_status(self, result: Dict):
        """
        打印监控状态

        参数:
            result: 监控结果
        """
        print(f"\n[{result['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}]")
        print(f"  进程数: {result['process_count']}")
        print(f"  总内存: {result['total_memory_mb']:.2f} MB")
        print(f"  总CPU: {result['total_cpu_percent']:.2f}%")
        print(f"  总连接数: {result['total_connections']}")

        if result['warnings']:
            print(f"  ⚠️  告警:")
            for warning in result['warnings']:
                print(f"    - {warning}")
        else:
            print(f"  ✓ 状态正常")

    async def monitor_loop(self, duration: int = None):
        """
        持续监控

        参数:
            duration: 监控时长 (秒), None 表示无限期
        """
        print(f"开始监控进程: {self.process_name}")
        print(f"检查间隔: {self.check_interval} 秒")
        print(f"监控时长: {duration if duration else '无限期'} 秒")
        print("-" * 80)

        start_time = time.time()

        while True:
            result = self.monitor_once()
            self.print_status(result)

            if duration and (time.time() - start_time) >= duration:
                break

            await asyncio.sleep(self.check_interval)

    def generate_report(self) -> str:
        """
        生成诊断报告

        返回:
            str: 报告内容
        """
        if not self.history:
            return "没有历史数据"

        report = []
        report.append("=" * 80)
        report.append("资源监控诊断报告")
        report.append("=" * 80)
        report.append(f"监控开始时间: {self.history[0]['timestamp']}")
        report.append(f"监控结束时间: {self.history[-1]['timestamp']}")
        report.append(f"监控时长: {(self.history[-1]['timestamp'] - self.history[0]['timestamp']).total_seconds():.2f} 秒")
        report.append(f"检查次数: {len(self.history)}")
        report.append("")

        # 统计信息
        memory_values = [h['total_memory_mb'] for h in self.history]
        cpu_values = [h['total_cpu_percent'] for h in self.history]
        connection_values = [h['total_connections'] for h in self.history]

        report.append("统计信息:")
        report.append("-" * 80)
        report.append(f"内存使用:")
        report.append(f"  最大: {max(memory_values):.2f} MB")
        report.append(f"  最小: {min(memory_values):.2f} MB")
        report.append(f"  平均: {sum(memory_values)/len(memory_values):.2f} MB")
        report.append(f"  增长: {memory_values[-1] - memory_values[0]:.2f} MB")
        report.append("")

        report.append(f"CPU 使用:")
        report.append(f"  最大: {max(cpu_values):.2f}%")
        report.append(f"  最小: {min(cpu_values):.2f}%")
        report.append(f"  平均: {sum(cpu_values)/len(cpu_values):.2f}%")
        report.append("")

        report.append(f"连接数:")
        report.append(f"  最大: {max(connection_values)}")
        report.append(f"  最小: {min(connection_values)}")
        report.append(f"  平均: {sum(connection_values)/len(connection_values):.2f}")
        report.append(f"  增长: {connection_values[-1] - connection_values[0]}")
        report.append("")

        # 告警统计
        all_warnings = []
        for h in self.history:
            all_warnings.extend(h['warnings'])

        if all_warnings:
            report.append("告警统计:")
            report.append("-" * 80)
            warning_counts = {}
            for warning in all_warnings:
                warning_type = warning.split(':')[0]
                warning_counts[warning_type] = warning_counts.get(warning_type, 0) + 1

            for warning_type, count in sorted(warning_counts.items(), key=lambda x: x[1], reverse=True):
                report.append(f"  {warning_type}: {count} 次")
            report.append("")

        # 趋势分析
        if len(memory_values) > 10:
            # 计算内存增长趋势
            first_half = memory_values[:len(memory_values)//2]
            second_half = memory_values[len(memory_values)//2:]
            avg_first = sum(first_half) / len(first_half)
            avg_second = sum(second_half) / len(second_half)
            growth_rate = (avg_second - avg_first) / avg_first * 100

            report.append("趋势分析:")
            report.append("-" * 80)
            if growth_rate > 10:
                report.append(f"  ⚠️  内存持续增长: {growth_rate:.2f}%")
                report.append("  可能存在内存泄漏")
            elif growth_rate < -10:
                report.append(f"  ✓ 内存持续下降: {growth_rate:.2f}%")
            else:
                report.append(f"  ✓ 内存使用稳定: {growth_rate:.2f}%")
            report.append("")

        # 诊断建议
        report.append("诊断建议:")
        report.append("-" * 80)

        if memory_values[-1] > self.thresholds['memory_mb']:
            report.append("  ⚠️  内存使用过高,建议:")
            report.append("    1. 检查是否有内存泄漏")
            report.append("    2. 减少并发连接数")
            report.append("    3. 增加系统内存")
            report.append("")

        if connection_values[-1] > self.thresholds['connections']:
            report.append("  ⚠️  连接数过多,建议:")
            report.append("    1. 检查是否有僵尸连接")
            report.append("    2. 减少连接超时时间")
            report.append("    3. 实施连接速率限制")
            report.append("")

        if growth_rate > 10:
            report.append("  ⚠️  检测到内存增长,建议:")
            report.append("    1. 检查缓冲区是否无限增长")
            report.append("    2. 检查是否有未释放的资源")
            report.append("    3. 使用内存分析工具定位泄漏点")
            report.append("")

        if not all_warnings:
            report.append("  ✓ 未检测到异常,系统运行正常")
            report.append("")

        report.append("=" * 80)

        return "\n".join(report)

def main():
    parser = argparse.ArgumentParser(description='资源监控和诊断工具')
    parser.add_argument('--process-name', default='python3', help='要监控的进程名称')
    parser.add_argument('--interval', type=int, default=5, help='检查间隔 (秒)')
    parser.add_argument('--duration', type=int, default=None, help='监控时长 (秒)')
    parser.add_argument('--report', action='store_true', help='生成诊断报告')
    args = parser.parse_args()

    monitor = ResourceMonitor(args.process_name, args.interval)

    try:
        if args.report:
            # 监控一段时间后生成报告
            asyncio.run(monitor.monitor_loop(duration=300))
            print("\n" + monitor.generate_report())
        else:
            # 持续监控
            asyncio.run(monitor.monitor_loop(duration=args.duration))
    except KeyboardInterrupt:
        print("\n监控已中断")
        print("\n" + monitor.generate_report())
        sys.exit(0)

if __name__ == '__main__':
    main()
