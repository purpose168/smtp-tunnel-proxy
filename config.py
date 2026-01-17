"""
SMTP 隧道 - 配置管理模块
加载和保存配置文件，管理用户配置。

版本: 1.3.0

功能概述:
本模块提供了配置管理功能，包括：
1. 服务器配置管理
2. 客户端配置管理
3. 用户配置管理
4. IP 白名单管理
5. 配置文件的加载和保存

主要功能:
1. 加载和保存 YAML 格式的配置文件
2. 管理用户配置（支持简化和完整两种格式）
3. IP 白名单验证
4. 配置数据类定义

配置文件格式:
- 服务器配置: config.yaml
- 用户配置: users.yaml
- 使用 YAML 格式，支持 Unicode
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

import yaml

logger = logging.getLogger(__name__)


# ============================================================================
# 配置数据类
# ============================================================================

@dataclass
class ServerConfig:
    """
    服务器配置数据类
    
    Attributes:
        host: 服务器监听地址（默认: "0.0.0.0"）
        port: 服务器监听端口（默认: 587）
        hostname: 服务器主机名（默认: "mail.example.com"）
        cert_file: TLS 证书文件路径（默认: "server.crt"）
        key_file: TLS 私钥文件路径（默认: "server.key"）
        users_file: 用户配置文件路径（默认: "users.yaml"）
        log_users: 是否记录用户日志（默认: True）
        traffic_enabled: 是否启用流量整形（默认: False）
        traffic_min_delay: 流量整形最小延迟（毫秒，默认: 50）
        traffic_max_delay: 流量整形最大延迟（毫秒，默认: 500）
        traffic_dummy_probability: 发送虚拟消息的概率（默认: 0.1）
    """
    host: str = "0.0.0.0"
    port: int = 587
    hostname: str = "mail.example.com"
    cert_file: str = "server.crt"
    key_file: str = "server.key"
    users_file: str = "users.yaml"
    log_users: bool = True
    traffic_enabled: bool = False
    traffic_min_delay: int = 50
    traffic_max_delay: int = 500
    traffic_dummy_probability: float = 0.1


@dataclass
class UserConfig:
    """
    用户配置数据类
    
    Attributes:
        username: 用户名
        secret: 用户密钥
        whitelist: IP 白名单列表（可选）
        logging: 是否记录该用户的日志（默认: True）
    """
    username: str
    secret: str
    whitelist: List[str] = None
    logging: bool = True

    def __post_init__(self):
        if self.whitelist is None:
            self.whitelist = []


@dataclass
class ClientConfig:
    """
    客户端配置数据类
    
    Attributes:
        server_host: 服务器地址
        server_port: 服务器端口（默认: 587）
        socks_port: SOCKS 代理端口（默认: 1080）
        socks_host: SOCKS 代理地址（默认: "127.0.0.1"）
        username: 用户名（可选）
        secret: 用户密钥（可选）
        ca_cert: CA 证书路径（可选）
        traffic_enabled: 是否启用流量整形（默认: False）
        traffic_min_delay: 流量整形最小延迟（毫秒，默认: 50）
        traffic_max_delay: 流量整形最大延迟（毫秒，默认: 500）
        traffic_dummy_probability: 发送虚拟消息的概率（默认: 0.1）
    """
    server_host: str
    server_port: int = 587
    socks_port: int = 1080
    socks_host: str = "127.0.0.1"
    username: str = None
    secret: str = None
    ca_cert: str = None
    traffic_enabled: bool = False
    traffic_min_delay: int = 50
    traffic_max_delay: int = 500
    traffic_dummy_probability: float = 0.1


# ============================================================================
# IP 白名单管理
# ============================================================================

class IPWhitelist:
    """
    IP 白名单管理类
    
    支持以下 IP 格式:
    - 单个 IP 地址（如 "192.168.1.1"）
    - CIDR 表示法（如 "192.168.1.0/24"）
    
    如果白名单为空，则允许所有 IP 访问。
    """
    
    def __init__(self, whitelist: List[str] = None):
        """
        初始化 IP 白名单
        
        Args:
            whitelist: IP 地址列表，支持以下格式：
                - 单个 IP 地址（如 "192.168.1.1"）
                - CIDR 表示法（如 "192.168.1.0/24"）
                如果为 None 或空列表，则允许所有 IP 访问
        """
        self.whitelist = whitelist or []
    
    def is_allowed(self, ip: str) -> bool:
        """
        检查 IP 是否在白名单中
        
        Args:
            ip: 要检查的 IP 地址字符串
            
        Returns:
            bool: 如果 IP 在白名单中或白名单为空则返回 True，否则返回 False
        """
        if not self.whitelist:
            return True
        
        for allowed_ip in self.whitelist:
            if self._match_ip(ip, allowed_ip):
                return True
        return False
    
    def _match_ip(self, ip: str, pattern: str) -> bool:
        """
        检查 IP 是否匹配模式
        
        支持两种匹配方式：
        1. 精确匹配：IP 地址完全相同
        2. CIDR 匹配：使用网络掩码进行子网匹配
        
        Args:
            ip: 要检查的 IP 地址字符串
            pattern: 匹配模式，可以是 IP 地址或 CIDR 表示法
            
        Returns:
            bool: 如果 IP 匹配模式则返回 True，否则返回 False
        """
        if ip == pattern:
            return True
        
        if '/' in pattern:
            try:
                from ipaddress import ip_network, ip_address
                network = ip_network(pattern, strict=False)
                return ip_address(ip) in network
            except ImportError:
                pass
        
        return False


# ============================================================================
# 配置文件管理函数
# ============================================================================

def load_config(config_file: str) -> Dict[str, Any]:
    """
    加载配置文件
    
    从 YAML 格式的配置文件中加载配置数据
    
    Args:
        config_file: 配置文件路径
        
    Returns:
        Dict[str, Any]: 配置数据字典，如果文件不存在或格式错误则返回空字典
    """
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as e:
        logger.warning(f"配置文件格式错误: {e}")
        return {}


def save_config(config_file: str, config_data: Dict[str, Any]) -> bool:
    """
    保存配置文件
    
    将配置数据保存到 YAML 格式的配置文件中
    
    Args:
        config_file: 配置文件路径
        config_data: 要保存的配置数据字典
        
    Returns:
        bool: 保存成功返回 True，失败返回 False
    """
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
        return True
    except Exception as e:
        logger.error(f"保存配置文件失败: {e}")
        return False


def load_users(users_file: str) -> Dict[str, Union[UserConfig, str]]:
    """
    加载用户配置
    
    从 YAML 格式的用户配置文件中加载用户数据
    支持两种用户配置格式：
    1. 简化格式：username: secret_string
    2. 完整格式：username: {secret: xxx, whitelist: [...], logging: true/false}
    
    Args:
        users_file: 用户配置文件路径
        
    Returns:
        Dict[str, Union[UserConfig, str]]: 用户配置字典
            - 简化格式：值为字符串（密钥）
            - 完整格式：值为 UserConfig 对象
            如果文件不存在或格式错误则返回空字典
    """
    try:
        with open(users_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        if not data or 'users' not in data or data['users'] is None:
            return {}
        
        users = {}
        for username, user_data in data['users'].items():
            if isinstance(user_data, str):
                users[username] = user_data
            elif isinstance(user_data, dict):
                whitelist = user_data.get('whitelist', [])
                logging = user_data.get('logging', True)
                secret = user_data.get('secret', '')
                users[username] = UserConfig(
                    username=username,
                    secret=secret,
                    whitelist=whitelist,
                    logging=logging
                )
        
        return users
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as e:
        logger.warning(f"用户配置文件格式错误: {e}")
        return {}
    except Exception as e:
        logger.warning(f"加载用户配置失败: {e}")
        return {}


def save_users(users_file: str, users: Dict[str, Union[UserConfig, str]]) -> bool:
    """
    保存用户配置
    
    将用户配置数据保存到 YAML 格式的配置文件中
    支持两种用户配置格式：
    1. 简化格式：username: secret_string
    2. 完整格式：username: {secret: xxx, whitelist: [...], logging: true/false}
    
    Args:
        users_file: 用户配置文件路径
        users: 用户配置字典
            - 简化格式：值为字符串（密钥）
            - 完整格式：值为 UserConfig 对象
            
    Returns:
        bool: 保存成功返回 True，失败返回 False
    """
    try:
        data = {'users': {}}
        
        for username, user_data in users.items():
            if isinstance(user_data, str):
                data['users'][username] = user_data
            elif isinstance(user_data, UserConfig):
                data['users'][username] = {
                    'secret': user_data.secret,
                    'whitelist': user_data.whitelist,
                    'logging': user_data.logging
                }
        
        with open(users_file, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        return True
    except Exception as e:
        logger.error(f"保存用户配置失败: {e}")
        return False
