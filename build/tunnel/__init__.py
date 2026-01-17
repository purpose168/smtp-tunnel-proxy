"""
SMTP 隧道统一模块

本模块整合了 SMTP 隧道客户端和服务器的核心功能，提供了统一的隧道接口。

主要功能包括：
- SMTP 握手协议
- TLS 连接升级
- 二进制帧处理
- 多通道管理
- 数据转发

使用示例：
    # 客户端使用
    from tunnel import TunnelClient
    client = TunnelClient(config, ca_cert)
    await client.connect()
    
    # 服务器使用
    from tunnel import TunnelSession, TunnelServer
    session = TunnelSession(reader, writer, config, ssl_context, users)
    await session.run()
    
    # 服务器类使用
    server = TunnelServer(config, users)
    await server.start()
"""

from .base import BaseTunnel

# 延迟导入所有模块以避免循环导入和模块缺失错误
def __getattr__(name):
    if name == 'TunnelClient':
        try:
            from .client import TunnelClient
            return TunnelClient
        except ImportError as e:
            raise ImportError(f"无法导入 tunnel.client 模块: {e}")
    elif name == 'TunnelCrypto':
        try:
            from .crypto import TunnelCrypto
            return TunnelCrypto
        except ImportError as e:
            raise ImportError(f"无法导入 tunnel.crypto 模块: {e}")
    elif name == 'TunnelSession':
        try:
            from .session import TunnelSession
            return TunnelSession
        except ImportError as e:
            raise ImportError(f"无法导入 tunnel.session 模块: {e}")
    elif name == 'TunnelServer':
        try:
            from .server import TunnelServer
            return TunnelServer
        except ImportError as e:
            raise ImportError(f"无法导入 tunnel.server 模块: {e}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    'BaseTunnel',
    'TunnelClient',
    'TunnelCrypto',
    'TunnelSession',
    'TunnelServer',
]