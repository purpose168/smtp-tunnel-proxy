"""
SMTP 隧道协议包

本包提供了 SMTP 隧道代理系统的协议定义和实现，包括：
- 核心协议常量和消息类型
- 隧道消息类及序列化/反序列化
- 帧处理函数

使用示例：
    from protocol import TunnelMessage, MsgType, make_frame
    
    # 创建消息
    msg = TunnelMessage.data(channel_id=1, data=b'hello world')
    
    # 序列化消息
    data = msg.serialize()
    
    # 反序列化消息
    msg2, remaining = TunnelMessage.deserialize(data)
"""

from .core import (
    # 协议常量
    PROTOCOL_VERSION,
    MAX_PAYLOAD_SIZE,
    NONCE_SIZE,
    TAG_SIZE,
    FRAME_HEADER_SIZE,
    
    # 消息类型枚举
    MsgType,
    
    # 隧道消息类
    TunnelMessage,
    
    # 兼容函数式接口
    FRAME_DATA,
    FRAME_CONNECT,
    FRAME_CONNECT_OK,
    FRAME_CONNECT_FAIL,
    FRAME_CLOSE,
    make_frame,
    parse_frame_header,
    make_connect_payload,
)