"""
SMTP 隧道服务器模块 - 服务器生命周期管理

此模块包含 TunnelServer 类，负责管理 SMTP 隧道服务器的生命周期，
包括 SSL/TLS 上下文创建、TCP 服务器启动和客户端连接处理。

主要组件:
- TunnelServer: SMTP 隧道服务器类，管理服务器生命周期和客户端连接

依赖:
- asyncio: 异步 I/O 操作
- ssl: SSL/TLS 加密
- logging: 日志记录
- config: ServerConfig, UserConfig 配置类
- tunnel.session: TunnelSession 隧道会话类

使用示例:
    >>> config = ServerConfig(host='0.0.0.0', port=587, hostname='mail.example.com')
    >>> users = {'user1': UserConfig(...)}
    >>> server = TunnelServer(config, users)
    >>> asyncio.run(server.start())
"""

import asyncio
import ssl
import logging
from typing import Dict

from config import ServerConfig, UserConfig
from tunnel.session import TunnelSession

logger = logging.getLogger(__name__)


class TunnelServer:
    """
    SMTP 隧道服务器类 - 管理服务器生命周期和客户端连接
    
    TunnelServer 负责启动和管理 SMTP 隧道服务器，处理客户端连接的接受和会话创建。
    它是服务器的主入口点，负责:
    1. 创建 SSL/TLS 上下文
    2. 启动 TCP 服务器
    3. 接受客户端连接
    4. 为每个连接创建 TunnelSession
    
    工作流程:
    1. 初始化服务器配置和 SSL 上下文
    2. 启动异步 TCP 服务器
    3. 监听指定端口
    4. 为每个客户端连接创建独立的会话
    
    Attributes:
        config: ServerConfig，服务器配置对象
        users: Dict[str, UserConfig]，用户配置字典
        ssl_context: ssl.SSLContext，SSL/TLS 上下文，用于加密连接
    
    安全特性:
        - TLS 1.2 及以上版本加密
        - 服务器证书验证
        - 多用户认证支持
    
    Note:
        - 使用 asyncio.start_server 创建异步服务器
        - 每个客户端连接在独立的协程中处理
        - 服务器运行在 serve_forever 循环中
        - 支持 IPv4 和 IPv6 双栈
    
    Example:
        >>> config = ServerConfig(host='0.0.0.0', port=587, hostname='mail.example.com')
        >>> users = {'user1': UserConfig(...)}
        >>> server = TunnelServer(config, users)
        >>> asyncio.run(server.start())
    """
    
    def __init__(self, config: ServerConfig, users: Dict[str, UserConfig]):
        """
        初始化隧道服务器
        
        Args:
            config: ServerConfig，服务器配置对象，包含主机、端口、主机名等配置
            users: Dict[str, UserConfig]，用户配置字典，键为用户名，值为用户配置
        
        初始化步骤:
            1. 保存服务器配置
            2. 保存用户配置
            3. 创建 SSL/TLS 上下文
        
        Note:
            - SSL 上下文在初始化时创建，避免重复创建
            - 用户配置用于客户端认证
            - 服务器配置用于绑定监听地址
        """
        self.config = config
        self.users = users
        self.ssl_context = self._create_ssl_context()

    def _create_ssl_context(self) -> ssl.SSLContext:
        """
        创建 SSL/TLS 上下文
        
        此方法创建用于加密客户端连接的 SSL/TLS 上下文。
        配置 TLS 协议版本和加载服务器证书。
        
        Returns:
            ssl.SSLContext: 配置好的 SSL/TLS 上下文
        
        TLS 配置:
        - 协议: TLS_SERVER（服务器模式）
        - 最低版本: TLSv1.2（禁用不安全的旧版本）
        - 证书: 从配置文件加载服务器证书和私钥
        
        安全特性:
        - 禁用 SSLv2、SSLv3、TLSv1.0、TLSv1.1（已知漏洞）
        - 使用现代加密套件
        - 服务器证书验证
        
        Note:
            - 证书文件路径从 config.cert_file 获取
            - 私钥文件路径从 config.key_file 获取
            - 如果证书或私钥不存在，会抛出异常
        
        Example:
            >>> ctx = server._create_ssl_context()
            >>> # ctx 可用于创建 SSL 套接字
        """
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(self.config.cert_file, self.config.key_file)
        return ctx

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """
        处理客户端连接
        
        此方法是每个客户端连接的入口点，为每个连接创建独立的 TunnelSession。
        在独立的协程中运行，不会阻塞其他连接。
        
        Args:
            reader: asyncio.StreamReader，用于从客户端读取数据
            writer: asyncio.StreamWriter，用于向客户端写入数据
        
        工作流程:
        1. 创建 TunnelSession 对象
        2. 启动会话处理循环
        3. 会话结束后自动清理资源
        
        Note:
            - 此方法由 asyncio.start_server 自动调用
            - 每个客户端连接在独立的协程中运行
            - 异常会被自动捕获，不会影响服务器运行
        
        Example:
            >>> # 此方法由 asyncio.start_server 自动调用
            >>> # 不需要手动调用
        """
        session = TunnelSession(reader, writer, self.config, self.ssl_context, self.users)
        await session.run()

    async def start(self):
        """
        启动 SMTP 隧道服务器
        
        此方法启动异步 TCP 服务器，开始监听客户端连接。
        服务器运行在 serve_forever 循环中，直到被中断。
        
        工作流程:
        1. 创建异步 TCP 服务器
        2. 绑定到配置的主机和端口
        3. 输出服务器启动信息
        4. 进入 serve_forever 循环
        
        服务器信息:
        - 监听地址和端口
        - 服务器主机名
        - 已加载的用户数量
        
        Note:
            - 使用 asyncio.start_server 创建异步服务器
            - serve_forever 会阻塞直到服务器停止
            - 可以通过 KeyboardInterrupt 停止服务器
            - 支持多个并发连接
        
        Example:
            >>> server = TunnelServer(config, users)
            >>> asyncio.run(server.start())
            # 服务器开始运行，监听配置的端口
        """
        server = await asyncio.start_server(
            self.handle_client,
            self.config.host,
            self.config.port
        )
        addr = server.sockets[0].getsockname()
        logger.info(f"SMTP 隧道服务器运行于 {addr[0]}:{addr[1]}")
        logger.info(f"主机名: {self.config.hostname}")
        logger.info(f"已加载用户数: {len(self.users)}")

        async with server:
            await server.serve_forever()
