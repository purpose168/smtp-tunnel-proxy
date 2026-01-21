#!/usr/bin/env python3
"""
资源耗尽诊断工具 - 快速定位资源泄漏问题

功能:
1. 监控进程的内存、CPU、文件描述符和协程数量
2. 检测资源泄漏和异常增长
3. 提供实时告警
4. 生成诊断报告
"""

import psutil
import asyncio
import time
import argparse
import sys
import os
from typing import Dict, List
from datetime import datetime

class ResourceExhaustionDiagnostics:
    """资源耗尽诊断工具"""

    def __init__(self, process_name: str = 'python3', check_interval: int = 5):
        """
        初始化诊断工具

        参数:
            process_name: 要诊断的进程名称
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
            'file_descriptors': 1000,  # 文件描述符阈值: 1000
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

    def get_coroutine_count(self, proc: psutil.Process) -> int:
        """
        获取协程数量

        参数:
            proc: 进程对象

        返回:
            int: 协程数量
        """
        try:
            # 使用 /proc/<pid>/task 获取线程数
            task_dir = f"/proc/{proc.pid}/task"
            if os.path.exists(task_dir):
                return len(os.listdir(task_dir))
            return proc.num_threads()
        except (psutil.NoSuchProcess, psutil.AccessDenied, FileNotFoundError):
            return 0

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

        if stats['num_fds'] > self.thresholds['file_descriptors']:
            warnings.append(f"文件描述符过多: {stats['num_fds']} > {self.thresholds['file_descriptors']}")

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
                'total_fds': 0,
                'total_coroutines': 0,
                'warnings': ['未找到目标进程']
            }

        total_memory = 0
        total_cpu = 0
        total_connections = 0
        total_fds = 0
        total_coroutines = 0
        all_warnings = []

        for proc in processes:
            stats = self.get_process_stats(proc)
            if stats:
                total_memory += stats['memory_mb']
                total_cpu += stats['cpu_percent']
                total_connections += stats['connections']
                total_fds += stats['num_fds']
                total_coroutines += self.get_coroutine_count(proc)

                warnings = self.check_thresholds(stats)
                all_warnings.extend(warnings)

        result = {
            'timestamp': datetime.now(),
            'process_count': len(processes),
            'total_memory_mb': total_memory,
            'total_cpu_percent': total_cpu,
            'total_connections': total_connections,
            'total_fds': total_fds,
            'total_coroutines': total_coroutines,
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
        print(f"  总文件描述符: {result['total_fds']}")
        print(f"  总协程数: {result['total_coroutines']}")

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
        print(f"开始诊断进程: {self.process_name}")
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
        report.append("资源耗尽诊断报告")
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
        fd_values = [h['total_fds'] for h in self.history]
        coroutine_values = [h['total_coroutines'] for h in self.history]

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

        report.append(f"文件描述符:")
        report.append(f"  最大: {max(fd_values)}")
        report.append(f"  最小: {min(fd_values)}")
        report.append(f"  平均: {sum(fd_values)/len(fd_values):.2f}")
        report.append(f"  增长: {fd_values[-1] - fd_values[0]}")
        report.append("")

        report.append(f"协程数:")
        report.append(f"  最大: {max(coroutine_values)}")
        report.append(f"  最小: {min(coroutine_values)}")
        report.append(f"  平均: {sum(coroutine_values)/len(coroutine_values):.2f}")
        report.append(f"  增长: {coroutine_values[-1] - coroutine_values[0]}")
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

            # 计算文件描述符增长趋势
            first_half_fds = fd_values[:len(fd_values)//2]
            second_half_fds = fd_values[len(fd_values)//2:]
            avg_first_fds = sum(first_half_fds) / len(first_half_fds)
            avg_second_fds = sum(second_half_fds) / len(second_half_fds)
            fd_growth_rate = (avg_second_fds - avg_first_fds) / avg_first_fds * 100

            if fd_growth_rate > 10:
                report.append(f"  ⚠️  文件描述符持续增长: {fd_growth_rate:.2f}%")
                report.append("  可能存在句柄泄漏")
            elif fd_growth_rate < -10:
                report.append(f"  ✓ 文件描述符持续下降: {fd_growth_rate:.2f}%")
            else:
                report.append(f"  ✓ 文件描述符使用稳定: {fd_growth_rate:.2f}%")
            report.append("")

        # 诊断建议
        report.append("诊断建议:")
        report.append("-" * 80)

        if memory_values[-1] > self.thresholds['memory_mb']:
            report.append("  ⚠️  内存使用过高,建议:")
            report.append("    1. 检查是否有内存泄漏")
            report.append("    2. 检查事件对象是否累积")
            report.append("    3. 检查协程是否泄漏")
            report.append("    4. 使用内存分析工具定位泄漏点")
            report.append("")

        if fd_values[-1] > self.thresholds['file_descriptors']:
            report.append("  ⚠️  文件描述符过多,建议:")
            report.append("    1. 检查是否有 Socket 句柄泄漏")
            report.append("    2. 检查连接是否正确关闭")
            report.append("    3. 使用 lsof 检查打开的文件")
            report.append("")

        if connection_values[-1] > self.thresholds['connections']:
            report.append("  ⚠️  连接数过多,建议:")
            report.append("    1. 检查是否有僵尸连接")
            report.append("    2. 检查连接超时时间是否合理")
            report.append("    3. 实施连接速率限制")
            report.append("")

        if growth_rate > 10:
            report.append("  ⚠️  检测到内存增长,建议:")
            report.append("    1. 检查缓冲区是否无限增长")
            report.append("    2. 检查是否有未释放的资源")
            report.append("    3. 使用内存分析工具定位泄漏点")
            report.append("")

        if fd_growth_rate > 10:
            report.append("  ⚠️  检测到文件描述符增长,建议:")
            report.append("    1. 检查 Socket 句柄是否正确关闭")
            report.append("    2. 检查是否有连接泄漏")
            report.append("    3. 使用 lsof 检查打开的文件描述符")
            report.append("")

        if not all_warnings:
            report.append("  ✓ 未检测到异常,系统运行正常")
            report.append("")

        report.append("=" * 80)

        return "\n".join(report)

def main():
    parser = argparse.ArgumentParser(description='资源耗尽诊断工具')
    parser.add_argument('--process-name', default='python3', help='要诊断的进程名称')
    parser.add_argument('--interval', type=int, default=5, help='检查间隔 (秒)')
    parser.add_argument('--duration', type=int, default=None, help='监控时长 (秒)')
    parser.add_argument('--report', action='store_true', help='生成诊断报告')
    args = parser.parse_args()

    diagnostics = ResourceExhaustionDiagnostics(args.process_name, args.check_interval)

    try:
        if args.report:
            # 监控一段时间后生成报告
            asyncio.run(diagnostics.monitor_loop(duration=300))
            print("\n" + diagnostics.generate_report())
        else:
            # 持续监控
            asyncio.run(diagnostics.monitor_loop(duration=args.duration))
    except KeyboardInterrupt:
        print("\n监控已中断")
        print("\n" + diagnostics.generate_report())
        sys.exit(0)

if __name__ == '__main__':
    main()
