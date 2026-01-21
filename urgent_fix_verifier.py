#!/usr/bin/env python3
"""
紧急修复验证脚本

用于验证资源耗尽问题的修复效果
"""

import asyncio
import time
import subprocess
import sys
from typing import List, Dict, Any


class FixVerifier:
    """修复验证器"""
    
    def __init__(self):
        self.client_process = None
        self.log_file = "client.log"
    
    async def start_client(self) -> bool:
        """启动客户端"""
        print("启动客户端...")
        try:
            # 启动客户端
            self.client_process = subprocess.Popen(
                [sys.executable, "client.py", "--server", "localhost", "--port", "2525", "--username", "test", "--secret", "test"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # 等待客户端启动
            await asyncio.sleep(5)
            
            if self.client_process.poll() is not None:
                print("❌ 客户端启动失败")
                return False
            
            print("✅ 客户端启动成功")
            return True
        except Exception as e:
            print(f"❌ 启动客户端时出错: {e}")
            return False
    
    async def stop_client(self):
        """停止客户端"""
        if self.client_process:
            print("停止客户端...")
            self.client_process.terminate()
            await asyncio.sleep(2)
            
            if self.client_process.poll() is None:
                self.client_process.kill()
                await asyncio.sleep(1)
            
            print("✅ 客户端已停止")
    
    async def monitor_channel_ids(self, duration: int = 60) -> Dict[str, Any]:
        """监控通道ID"""
        print(f"监控通道ID ({duration}秒)...")
        channel_ids = []
        
        start_time = time.time()
        while time.time() - start_time < duration:
            try:
                # 读取日志文件
                with open(self.log_file, 'r') as f:
                    lines = f.readlines()
                
                # 提取通道ID
                for line in lines:
                    if "打开通道" in line and "通道" in line:
                        try:
                            # 提取通道ID
                            parts = line.split()
                            for part in parts:
                                if part.isdigit():
                                    channel_id = int(part)
                                    channel_ids.append(channel_id)
                                    break
                        except:
                            pass
                
                await asyncio.sleep(1)
            except FileNotFoundError:
                await asyncio.sleep(1)
        
        # 分析通道ID
        unique_ids = list(set(channel_ids))
        max_id = max(unique_ids) if unique_ids else 0
        min_id = min(unique_ids) if unique_ids else 0
        
        result = {
            "total": len(channel_ids),
            "unique": len(unique_ids),
            "max": max_id,
            "min": min_id,
            "ids": unique_ids[:10]  # 只保留前10个
        }
        
        print(f"通道ID统计:")
        print(f"  总计: {result['total']}")
        print(f"  唯一: {result['unique']}")
        print(f"  最大: {result['max']}")
        print(f"  最小: {result['min']}")
        print(f"  示例: {result['ids']}")
        
        return result
    
    async def monitor_connection_stats(self, duration: int = 60) -> Dict[str, Any]:
        """监控连接统计"""
        print(f"监控连接统计 ({duration}秒)...")
        stats = []
        
        start_time = time.time()
        while time.time() - start_time < duration:
            try:
                # 读取日志文件
                with open(self.log_file, 'r') as f:
                    lines = f.readlines()
                
                # 提取连接统计
                for line in lines:
                    if "连接统计" in line:
                        try:
                            # 提取连接数
                            parts = line.split()
                            stat = {}
                            for part in parts:
                                if "=" in part:
                                    key, value = part.split("=")
                                    stat[key] = value
                            stats.append(stat)
                        except:
                            pass
                
                await asyncio.sleep(1)
            except FileNotFoundError:
                await asyncio.sleep(1)
        
        # 分析连接统计
        if stats:
            latest = stats[-1]
            print(f"最新连接统计:")
            for key, value in latest.items():
                print(f"  {key}: {value}")
        
        return {
            "count": len(stats),
            "latest": stats[-1] if stats else {}
        }
    
    async def monitor_resource_usage(self, duration: int = 60) -> Dict[str, Any]:
        """监控资源使用"""
        print(f"监控资源使用 ({duration}秒)...")
        
        try:
            import psutil
            import os
            
            proc = psutil.Process(os.getpid())
            
            memory_samples = []
            cpu_samples = []
            fd_samples = []
            
            start_time = time.time()
            while time.time() - start_time < duration:
                try:
                    memory_mb = proc.memory_info().rss / 1024 / 1024
                    cpu_percent = proc.cpu_percent(interval=0.1)
                    num_fds = proc.num_fds() if hasattr(proc, 'num_fds') else 0
                    
                    memory_samples.append(memory_mb)
                    cpu_samples.append(cpu_percent)
                    fd_samples.append(num_fds)
                    
                    await asyncio.sleep(1)
                except:
                    await asyncio.sleep(1)
            
            # 分析资源使用
            result = {
                "memory": {
                    "min": min(memory_samples) if memory_samples else 0,
                    "max": max(memory_samples) if memory_samples else 0,
                    "avg": sum(memory_samples) / len(memory_samples) if memory_samples else 0
                },
                "cpu": {
                    "min": min(cpu_samples) if cpu_samples else 0,
                    "max": max(cpu_samples) if cpu_samples else 0,
                    "avg": sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0
                },
                "fds": {
                    "min": min(fd_samples) if fd_samples else 0,
                    "max": max(fd_samples) if fd_samples else 0,
                    "avg": sum(fd_samples) / len(fd_samples) if fd_samples else 0
                }
            }
            
            print(f"资源使用统计:")
            print(f"  内存: 最小={result['memory']['min']:.1f}MB, 最大={result['memory']['max']:.1f}MB, 平均={result['memory']['avg']:.1f}MB")
            print(f"  CPU: 最小={result['cpu']['min']:.1f}%, 最大={result['cpu']['max']:.1f}%, 平均={result['cpu']['avg']:.1f}%")
            print(f"  文件描述符: 最小={result['fds']['min']}, 最大={result['fds']['max']}, 平均={result['fds']['avg']:.1f}")
            
            return result
        except ImportError:
            print("⚠️  psutil 未安装，跳过资源监控")
            return {}
    
    def analyze_results(self, channel_ids: Dict[str, Any], 
                       connection_stats: Dict[str, Any],
                       resource_usage: Dict[str, Any]) -> Dict[str, Any]:
        """分析结果"""
        print("\n分析结果...")
        
        issues = []
        warnings = []
        
        # 检查通道ID
        if channel_ids.get("max", 0) > 1000:
            issues.append(f"通道ID超过1000: {channel_ids.get('max', 0)}")
        elif channel_ids.get("max", 0) > 100:
            warnings.append(f"通道ID较大: {channel_ids.get('max', 0)}")
        
        # 检查连接统计
        if connection_stats.get("latest", {}).get("事件", "0") != "0":
            issues.append(f"存在泄漏的事件对象: {connection_stats.get('latest', {}).get('事件', '0')}")
        
        if connection_stats.get("latest", {}).get("结果", "0") != "0":
            issues.append(f"存在泄漏的结果对象: {connection_stats.get('latest', {}).get('结果', '0')}")
        
        # 检查资源使用
        if resource_usage.get("memory", {}).get("max", 0) > 500:
            issues.append(f"内存使用过高: {resource_usage.get('memory', {}).get('max', 0):.1f}MB")
        elif resource_usage.get("memory", {}).get("max", 0) > 200:
            warnings.append(f"内存使用较高: {resource_usage.get('memory', {}).get('max', 0):.1f}MB")
        
        if resource_usage.get("cpu", {}).get("max", 0) > 80:
            issues.append(f"CPU使用过高: {resource_usage.get('cpu', {}).get('max', 0):.1f}%")
        
        if resource_usage.get("fds", {}).get("max", 0) > 100:
            issues.append(f"文件描述符过多: {resource_usage.get('fds', {}).get('max', 0)}")
        elif resource_usage.get("fds", {}).get("max", 0) > 50:
            warnings.append(f"文件描述符较多: {resource_usage.get('fds', {}).get('max', 0)}")
        
        # 输出结果
        if issues:
            print("\n❌ 发现问题:")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print("\n✅ 未发现严重问题")
        
        if warnings:
            print("\n⚠️  发现警告:")
            for warning in warnings:
                print(f"  - {warning}")
        else:
            print("\n✅ 未发现警告")
        
        return {
            "issues": issues,
            "warnings": warnings
        }
    
    async def run_verification(self) -> bool:
        """运行验证"""
        print("=" * 60)
        print("开始验证修复效果")
        print("=" * 60)
        
        # 启动客户端
        if not await self.start_client():
            return False
        
        try:
            # 监控通道ID
            channel_ids = await self.monitor_channel_ids(duration=60)
            
            # 监控连接统计
            connection_stats = await self.monitor_connection_stats(duration=60)
            
            # 监控资源使用
            resource_usage = await self.monitor_resource_usage(duration=60)
            
            # 分析结果
            results = self.analyze_results(channel_ids, connection_stats, resource_usage)
            
            # 判断是否成功
            success = len(results.get("issues", [])) == 0
            
            print("\n" + "=" * 60)
            if success:
                print("✅ 验证通过")
            else:
                print("❌ 验证失败")
            print("=" * 60)
            
            return success
        finally:
            # 停止客户端
            await self.stop_client()


async def main():
    """主函数"""
    verifier = FixVerifier()
    success = await verifier.run_verification()
    
    if success:
        print("\n✅ 修复验证成功")
        sys.exit(0)
    else:
        print("\n❌ 修复验证失败")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
