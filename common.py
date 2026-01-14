"""
SMTP 隧道 - 通用协议和工具（兼容层）
客户端和服务器共享的组件。

版本: 1.3.0

注意:
此文件已重构为兼容层，所有功能已拆分到以下模块:
- protocol.py: 协议常量、消息类型和消息类
- tunnel/crypto.py: 加密/解密功能
- traffic.py: 流量整形
- smtp_message.py: SMTP 消息生成
- config.py: 配置管理和用户管理

为了保持向后兼容性，此文件从上述模块重新导出所有公共 API。
建议新代码直接从相应模块导入。
"""

# ============================================================================
# 从 protocol.py 导入
# ============================================================================
from protocol import (
    PROTOCOL_VERSION,
    MAX_PAYLOAD_SIZE,
    NONCE_SIZE,
    TAG_SIZE,
    MsgType,
    TunnelMessage,
)

# ============================================================================
# 从 crypto.py 导入
# ============================================================================
from tunnel.crypto import (
    TunnelCrypto,
)

# ============================================================================
# 从 traffic.py 导入
# ============================================================================
from traffic import (
    TrafficShaper,
)

# ============================================================================
# 从 smtp_message.py 导入
# ============================================================================
from smtp_message import (
    SMTPMessageGenerator,
)

# ============================================================================
# 从 config.py 导入
# ============================================================================
from config import (
    ServerConfig,
    UserConfig,
    ClientConfig,
    IPWhitelist,
    load_config,
    save_config,
    load_users,
    save_users,
)

# ============================================================================
# 公共 API
# ============================================================================
__all__ = [
    # 协议常量
    'PROTOCOL_VERSION',
    'MAX_PAYLOAD_SIZE',
    'NONCE_SIZE',
    'TAG_SIZE',
    # 消息类型
    'MsgType',
    'TunnelMessage',
    # 加密
    'TunnelCrypto',
    # 流量整形
    'TrafficShaper',
    # SMTP 消息生成
    'SMTPMessageGenerator',
    # 配置管理
    'ServerConfig',
    'UserConfig',
    'ClientConfig',
    'IPWhitelist',
    'load_config',
    'save_config',
    'load_users',
    'save_users',
]
