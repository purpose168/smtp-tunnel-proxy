"""
SMTP 隧道 - SMTP 消息生成模块
生成逼真的 SMTP 消息以包装隧道数据。

版本: 1.3.0

功能概述:
本模块提供了逼真的 SMTP 消息生成功能，用于将隧道数据
包装在看起来像正常电子邮件的消息中，以进一步规避检测。

主要功能:
1. 生成逼真的邮件主题
2. 生成逼真的发件人和收件人地址
3. 生成符合 RFC 标准的 MIME 消息
4. 将隧道数据作为附件包装

消息格式:
- 符合 RFC 2822 标准的邮件格式
- 使用 MIME multipart/mixed 格式
- 包含纯文本正文和 Base64 编码的附件
"""

import os
import time
import base64
import random
from datetime import datetime, timezone
from typing import Tuple


class SMTPMessageGenerator:
    """
    生成逼真的 SMTP 消息以包装隧道数据。
    
    生成的消息包含:
    - 逼真的发件人和收件人地址
    - 逼真的主题行
    - 符合 RFC 标准的邮件头部
    - MIME multipart/mixed 格式
    - 纯文本正文
    - Base64 编码的隧道数据附件
    
    逼真性特征:
    - 使用常见的邮件域名（gmail.com, outlook.com 等）
    - 使用逼真的中文姓名
    - 使用常见的邮件主题模板
    - 符合 RFC 2822 和 MIME 标准
    """

    SUBJECTS = [
        "回复: 您的订单 #{order_id} 已发货",
        "发票附件 - 账户 #{account_id}",
        "会议纪要 - {date}",
        "转发: 您请求的文档",
        "周报 - 第 {week} 周",
        "回复: 关于项目的快速问题",
        "更新后的文件附件",
        "确认: 您在 {date} 的预约",
        "您的购买收据",
        "需要操作: 请审核",
        "转发: 重要更新",
        "回复: 跟进我们的对话",
    ]

    DOMAINS = [
        "gmail.com", "outlook.com", "yahoo.com", "protonmail.com",
        "icloud.com", "mail.com", "hotmail.com"
    ]

    FIRST_NAMES = [
        "张", "李", "王", "刘", "陈", "杨",
        "赵", "黄", "周", "吴", "徐", "孙"
    ]

    LAST_NAMES = [
        "伟", "芳", "娜", "敏", "静", "强",
        "磊", "洋", "艳", "杰", "勇", "军"
    ]

    BODY_TEMPLATES = [
        "请查收附件中的文档。\n\n致以问候",
        "如讨论所述，这里是文件。\n\n谢谢",
        "附件是您请求的信息。\n\n致敬",
        "请审核附件。\n\n感谢",
        "这是文档。\n\n祝好",
    ]

    def __init__(self, from_domain: str = "example.com", to_domain: str = "example.org"):
        """
        初始化消息生成器。

        参数:
            from_domain: 发件人地址的域名
            to_domain: 收件人地址的域名
        """
        self.from_domain = from_domain
        self.to_domain = to_domain
        self._message_counter = 0

    def generate_message_id(self) -> str:
        """
        生成逼真的 Message-ID
        
        Returns:
            str: 符合 RFC 标准的 Message-ID
        """
        random_part = os.urandom(8).hex()
        timestamp = int(time.time() * 1000) % 1000000
        return f"<{random_part}.{timestamp}@{self.from_domain}>"

    def generate_subject(self) -> str:
        """
        生成逼真的主题行
        
        Returns:
            str: 随机选择的主题行
        """
        template = random.choice(self.SUBJECTS)
        now = datetime.now()
        return template.format(
            order_id=random.randint(10000, 99999),
            account_id=random.randint(1000, 9999),
            date=now.strftime("%m月%d日"),
            week=now.isocalendar()[1]
        )

    def generate_sender(self) -> Tuple[str, str]:
        """
        生成逼真的 From 名称和地址
        
        Returns:
            Tuple[str, str]: (显示名称, 邮件地址)
        """
        first = random.choice(self.FIRST_NAMES)
        last = random.choice(self.LAST_NAMES)
        name = f"{first}{last}"

        email_styles = [
            f"{first.lower()}.{last.lower()}",
            f"{first.lower()}{last.lower()}",
            f"{first[0].lower()}{last.lower()}",
            f"{first.lower()}{random.randint(1, 99)}",
        ]
        email = f"{random.choice(email_styles)}@{random.choice(self.DOMAINS)}"

        return name, email

    def generate_recipient(self) -> Tuple[str, str]:
        """
        生成逼真的 To 地址
        
        Returns:
            Tuple[str, str]: (显示名称, 邮件地址)
        """
        first = random.choice(self.FIRST_NAMES)
        last = random.choice(self.LAST_NAMES)
        name = f"{first}{last}"
        email = f"{first.lower()}.{last.lower()}@{self.to_domain}"
        return name, email

    def generate_boundary(self) -> str:
        """
        生成 MIME 边界
        
        Returns:
            str: MIME 边界字符串
        """
        return f"----=_Part_{os.urandom(6).hex()}"

    def wrap_tunnel_data(self, tunnel_data: bytes, filename: str = "document.dat") -> Tuple[str, str, str, str]:
        """
        将隧道数据包装在逼真的 MIME 电子邮件消息中。

        Args:
            tunnel_data: 要包装的隧道数据
            filename: 附件文件名
            
        Returns:
            Tuple[str, str, str, str]: (from_addr, to_addr, subject, message_body)
        """
        from_name, from_addr = self.generate_sender()
        to_name, to_addr = self.generate_recipient()
        subject = self.generate_subject()
        message_id = self.generate_message_id()
        boundary = self.generate_boundary()

        now = datetime.now(timezone.utc)
        date_str = now.strftime("%a, %d %b %Y %H:%M:%S %z")

        b64_data = base64.b64encode(tunnel_data).decode('ascii')
        b64_lines = [b64_data[i:i+76] for i in range(0, len(b64_data), 76)]
        b64_formatted = '\r\n'.join(b64_lines)

        body_text = random.choice(self.BODY_TEMPLATES)

        message = f"""From: {from_name} <{from_addr}>
To: {to_name} <{to_addr}>
Subject: {subject}
Date: {date_str}
Message-ID: {message_id}
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="{boundary}"

--{boundary}
Content-Type: text/plain; charset=utf-8
Content-Transfer-Encoding: 7bit

{body_text}

--{boundary}
Content-Type: application/octet-stream
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="{filename}"

{b64_formatted}
--{boundary}--"""

        message = message.replace('\n', '\r\n')

        return from_addr, to_addr, subject, message
