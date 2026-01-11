"""
SMTP 隧道 - 流量整形模块
通过流量整形实现 DPI 规避。

版本: 1.3.0

功能概述:
本模块提供了流量整形功能，用于规避深度包检测（DPI）。
通过添加随机延迟、填充数据和发送虚拟消息，使隧道流量
看起来更像正常的电子邮件通信。

主要功能:
1. 消息之间的随机延迟
2. 填充数据到标准大小
3. 偶尔发送虚拟消息

流量整形策略:
- 随机延迟模拟人类行为
- 填充到常见的电子邮件附件大小
- 虚拟消息增加流量随机性
"""

import struct
import asyncio
import random
import os


class TrafficShaper:
    """
    通过流量整形实现 DPI 规避:
    - 消息之间的随机延迟
    - 填充到标准大小
    - 偶尔发送虚拟消息
    
    标准填充大小（常见的电子邮件附件大小）:
    - 4096 字节 (4KB)
    - 8192 字节 (8KB)
    - 16384 字节 (16KB)
    - 32768 字节 (32KB)
    """

    PAD_SIZES = [4096, 8192, 16384, 32768]

    def __init__(
        self,
        min_delay_ms: int = 50,
        max_delay_ms: int = 500,
        dummy_probability: float = 0.1
    ):
        """
        初始化流量整形器。

        参数:
            min_delay_ms: 消息之间的最小延迟（毫秒）
            max_delay_ms: 消息之间的最大延迟（毫秒）
            dummy_probability: 发送虚拟消息的概率（0.0-1.0）
        """
        self.min_delay_ms = min_delay_ms
        self.max_delay_ms = max_delay_ms
        self.dummy_probability = dummy_probability

    async def delay(self):
        """
        添加随机延迟以模拟人类行为
        
        在 min_delay_ms 和 max_delay_ms 之间随机选择延迟时间。
        """
        delay_ms = random.randint(self.min_delay_ms, self.max_delay_ms)
        await asyncio.sleep(delay_ms / 1000.0)

    def pad_data(self, data: bytes) -> bytes:
        """
        将数据填充到下一个标准大小
        
        填充格式: data_length (2 字节) + data + random_padding
        
        Args:
            data: 要填充的原始数据
            
        Returns:
            bytes: 填充后的数据
        """
        data_len = len(data)

        total_needed = data_len + 2
        target_size = self.PAD_SIZES[-1]
        for size in self.PAD_SIZES:
            if total_needed <= size:
                target_size = size
                break

        padding_len = target_size - total_needed
        padding = os.urandom(padding_len) if padding_len > 0 else b''

        return struct.pack('>H', data_len) + data + padding

    @staticmethod
    def unpad_data(padded_data: bytes) -> bytes:
        """
        从数据中移除填充
        
        Args:
            padded_data: 填充后的数据
            
        Returns:
            bytes: 原始数据
        """
        if len(padded_data) < 2:
            return padded_data

        data_len = struct.unpack('>H', padded_data[:2])[0]
        return padded_data[2:2 + data_len]

    def should_send_dummy(self) -> bool:
        """
        确定是否应该发送虚拟消息
        
        Returns:
            bool: 如果应该发送虚拟消息则返回 True
        """
        return random.random() < self.dummy_probability

    def generate_dummy_data(self, min_size: int = 100, max_size: int = 1000) -> bytes:
        """
        生成随机虚拟数据
        
        Args:
            min_size: 最小数据大小（字节）
            max_size: 最大数据大小（字节）
            
        Returns:
            bytes: 随机生成的虚拟数据
        """
        size = random.randint(min_size, max_size)
        return os.urandom(size)
