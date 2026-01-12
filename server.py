#!/usr/bin/env python3
"""
SMTP 隧道服务器 - 快速二进制模式

版本: 1.3.0

协议:
1. SMTP 握手 (EHLO, STARTTLS, AUTH) - 看起来像真实的 SMTP
2. AUTH 成功后，切换到二进制流模式
3. 全双工二进制协议 - 不再有 SMTP 开销

特性:
- 支持多用户，每个用户有独立的密钥
- 每用户 IP 白名单
- 每用户日志记录（可选）
"""

# 标准库导入
import asyncio  # 异步 I/O 框架，用于处理高并发网络连接
import argparse  # 命令行参数解析
import os  # 操作系统接口
import sys  # 系统功能

# 本地模块导入
from logger import LoggerManager, get_logger, add_context, clear_context
from common import (
    load_config,  # 加载服务器配置
    load_users,  # 加载用户配置
    ServerConfig,  # 服务器配置数据类
    UserConfig,  # 用户配置数据类
)
from server_server import TunnelServer  # 隧道服务器类

logger = get_logger('smtp-tunnel-server')


def main():
    """
    SMTP 隧道服务器主函数 - 程序入口点
    
    此函数是 SMTP 隧道服务器的入口点，负责:
    1. 解析命令行参数
    2. 加载配置文件
    3. 加载用户配置
    4. 验证证书文件
    5. 启动服务器
    
    命令行参数:
        --config, -c: 配置文件路径（默认: config.yaml）
        --users, -u: 用户文件路径（默认: 从配置或 users.yaml）
        --debug, -d: 启用调试模式
    
    工作流程:
        1. 解析命令行参数
        2. 设置日志级别（如果启用调试模式）
        3. 加载配置文件
        4. 创建 ServerConfig 对象
        5. 加载用户配置
        6. 验证用户配置和证书文件
        7. 创建并启动 TunnelServer
    
    错误处理:
        - 配置文件不存在: 使用默认配置
        - 用户配置为空: 输出错误信息并退出
        - 证书文件不存在: 输出错误信息并退出
        - KeyboardInterrupt: 优雅地停止服务器
    
    返回值:
        - 0: 成功
        - 1: 失败（用户配置为空或证书文件不存在）
    
    Note:
        - 使用 argparse 解析命令行参数
        - 配置文件使用 YAML 格式
        - 用户文件使用 YAML 格式
        - 服务器在 KeyboardInterrupt 时优雅退出
    
    Example:
        # 使用默认配置启动服务器
        $ python server.py
        
        # 指定配置文件
        $ python server.py --config my-config.yaml
        
        # 指定用户文件
        $ python server.py --users my-users.yaml
        
        # 启用调试模式
        $ python server.py --debug
    """
    parser = argparse.ArgumentParser(description='SMTP 隧道服务器')
    parser.add_argument('--config', '-c', default='config.yaml')
    parser.add_argument('--users', '-u', default=None, help='用户文件（默认: 从配置或 users.yaml）')
    parser.add_argument('--debug', '-d', action='store_true')
    args = parser.parse_args()

    # 初始化日志系统
    log_manager = LoggerManager()
    log_manager.initialize(config_file=args.config)

    # 如果启用调试模式，覆盖日志级别
    if args.debug:
        log_manager.config.level = 'DEBUG'
        logger.setLevel('DEBUG')
        logger.info("调试模式已启用")

    # 加载配置文件 - 如果文件不存在，使用空字典
    try:
        config_data = load_config(args.config)
    except FileNotFoundError:
        config_data = {}

    # 从配置中提取服务器配置
    server_conf = config_data.get('server', {})

    # 创建 ServerConfig 对象 - 使用配置文件中的值或默认值
    config = ServerConfig(
        host=server_conf.get('host', '0.0.0.0'),
        port=server_conf.get('port', 587),
        hostname=server_conf.get('hostname', 'mail.example.com'),
        cert_file=server_conf.get('cert_file', 'server.crt'),
        key_file=server_conf.get('key_file', 'server.key'),
        users_file=server_conf.get('users_file', 'users.yaml'),
        log_users=server_conf.get('log_users', True),
    )

    # 加载用户文件 - 命令行参数优先于配置文件
    users_file = args.users or config.users_file
    users = load_users(users_file)

    # 验证用户配置 - 如果没有用户，输出错误信息并退出
    if not users:
        logger.error(f"未配置用户！请创建 {users_file}")
        logger.error("使用 smtp-tunnel-adduser 添加用户")
        return 1

    # 验证证书文件 - 如果证书文件不存在，输出错误信息并退出
    if not os.path.exists(config.cert_file):
        logger.error(f"未找到证书: {config.cert_file}")
        return 1

    # 创建服务器对象
    server = TunnelServer(config, users)

    # 启动服务器 - 使用 asyncio.run 运行异步服务器
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("服务器已停止")

    return 0


if __name__ == '__main__':
    sys.exit(main())
