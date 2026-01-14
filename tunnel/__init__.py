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
from .client import TunnelClient

# 延迟导入 TunnelSession 和 TunnelServer 以避免循环导入
def __getattr__(name):
    if name == 'TunnelSession':
        from .session import TunnelSession
        return TunnelSession
    elif name == 'TunnelServer':
        from .server import TunnelServer
        return TunnelServer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    'BaseTunnel',
    'TunnelClient',
    'TunnelSession',
    'TunnelServer',
]