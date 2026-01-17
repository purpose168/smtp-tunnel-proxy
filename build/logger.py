"""
SMTP 隧道 - 日志管理模块

版本: 1.0.0

功能概述:
本模块提供了完整的日志管理功能，包括：
1. 多级别日志记录（DEBUG, INFO, WARNING, ERROR, CRITICAL）
2. 日志轮转（按日期/大小）
3. 结构化日志格式（时间戳、级别、上下文）
4. 配置文件和环境变量支持
5. 异常捕获和错误追踪
6. 日志文件管理（存储路径、命名规范）

主要功能:
1. 初始化日志系统
2. 配置日志处理器（文件、控制台、系统日志）
3. 日志轮转管理
4. 上下文信息记录
5. 异常捕获和记录
"""

import logging
import logging.handlers
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from systemd.journal import JournalHandler
    HAS_JOURNAL = True
except ImportError:
    HAS_JOURNAL = False


@dataclass
class LogConfig:
    """
    日志配置数据类

    Attributes:
        level: 日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）
        log_dir: 日志存储目录
        log_file: 日志文件名（支持日期占位符）
        max_bytes: 单个日志文件最大大小（字节）
        backup_count: 保留的备份文件数量
        rotation_type: 轮转类型（size, date, both）
        date_format: 日期格式（用于文件名）
        format_string: 日志格式字符串
        enable_console: 是否输出到控制台
        enable_file: 是否输出到文件
        enable_journal: 是否输出到系统日志
        context_fields: 上下文字段列表
    """
    level: str = "INFO"
    log_dir: str = "/opt/smtp-tunnel/logs"
    log_file: str = "smtp-tunnel.log"
    max_bytes: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 10
    rotation_type: str = "both"  # size, date, both
    date_format: str = "%Y-%m-%d"
    format_string: str = "%(asctime)s - %(name)s - %(levelname)s - [%(context)s] - %(message)s"
    enable_console: bool = True
    enable_file: bool = True
    enable_journal: bool = True
    context_fields: list = None

    def __post_init__(self):
        if self.context_fields is None:
            self.context_fields = ["username", "ip", "session_id"]


class ContextFilter(logging.Filter):
    """
    上下文过滤器

    为日志记录添加上下文信息
    """

    def __init__(self, context_fields: list = None):
        super().__init__()
        self.context_fields = context_fields or []
        self.context_data = {}

    def add_context(self, **kwargs):
        """
        添加上下文信息

        Args:
            **kwargs: 上下文键值对
        """
        self.context_data.update(kwargs)

    def clear_context(self):
        """
        清除上下文信息
        """
        self.context_data.clear()

    def filter(self, record):
        """
        过滤日志记录，添加上下文信息

        Args:
            record: 日志记录对象

        Returns:
            bool: 总是返回 True
        """
        context_parts = []
        for field in self.context_fields:
            value = self.context_data.get(field, "-")
            context_parts.append(f"{field}={value}")

        record.context = " | ".join(context_parts)
        return True


class LogFormatter(logging.Formatter):
    """
    自定义日志格式化器

    支持彩色输出和结构化格式
    """

    COLORS = {
        'DEBUG': '\033[36m',      # 青色
        'INFO': '\033[32m',       # 绿色
        'WARNING': '\033[33m',    # 黄色
        'ERROR': '\033[31m',      # 红色
        'CRITICAL': '\033[35m',   # 紫色
    }
    RESET = '\033[0m'

    def __init__(self, fmt=None, datefmt=None, style='%', use_color=False):
        super().__init__(fmt, datefmt, style)
        self.use_color = use_color

    def format(self, record):
        """
        格式化日志记录

        Args:
            record: 日志记录对象

        Returns:
            str: 格式化后的日志字符串
        """
        # 确保context字段存在
        if not hasattr(record, 'context'):
            record.context = "-"

        if self.use_color and hasattr(record, 'levelname'):
            levelname = record.levelname
            if levelname in self.COLORS:
                record.levelname = f"{self.COLORS[levelname]}{levelname}{self.RESET}"

        result = super().format(record)

        if self.use_color and hasattr(record, 'levelname'):
            record.levelname = levelname

        return result


class LoggerManager:
    """
    日志管理器

    管理日志系统的初始化、配置和运行
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        """
        单例模式
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """
        初始化日志管理器
        """
        if not self._initialized:
            self.config = None
            self.context_filter = None
            self.loggers = {}
            self._initialized = True

    def load_config_from_file(self, config_file: str) -> LogConfig:
        """
        从配置文件加载日志配置

        Args:
            config_file: 配置文件路径

        Returns:
            LogConfig: 日志配置对象
        """
        try:
            import yaml
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)

            log_config = config_data.get('logging', {})

            return LogConfig(
                level=os.getenv('LOG_LEVEL', log_config.get('level', 'INFO')),
                log_dir=os.getenv('LOG_DIR', log_config.get('log_dir', '/opt/smtp-tunnel/logs')),
                log_file=os.getenv('LOG_FILE', log_config.get('log_file', 'smtp-tunnel.log')),
                max_bytes=int(os.getenv('LOG_MAX_BYTES', log_config.get('max_bytes', 10 * 1024 * 1024))),
                backup_count=int(os.getenv('LOG_BACKUP_COUNT', log_config.get('backup_count', 10))),
                rotation_type=os.getenv('LOG_ROTATION_TYPE', log_config.get('rotation_type', 'both')),
                date_format=os.getenv('LOG_DATE_FORMAT', log_config.get('date_format', '%Y-%m-%d')),
                format_string=os.getenv('LOG_FORMAT', log_config.get('format_string',
                    '%(asctime)s - %(name)s - %(levelname)s - [%(context)s] - %(message)s')),
                enable_console=os.getenv('LOG_ENABLE_CONSOLE', str(log_config.get('enable_console', True))).lower() == 'true',
                enable_file=os.getenv('LOG_ENABLE_FILE', str(log_config.get('enable_file', True))).lower() == 'true',
                enable_journal=os.getenv('LOG_ENABLE_JOURNAL', str(log_config.get('enable_journal', True))).lower() == 'true',
                context_fields=log_config.get('context_fields', ['username', 'ip', 'session_id'])
            )
        except FileNotFoundError:
            return self._load_config_from_env()
        except Exception as e:
            print(f"加载日志配置文件失败: {e}，使用环境变量配置", file=sys.stderr)
            return self._load_config_from_env()

    def _load_config_from_env(self) -> LogConfig:
        """
        从环境变量加载日志配置

        Returns:
            LogConfig: 日志配置对象
        """
        return LogConfig(
            level=os.getenv('LOG_LEVEL', 'INFO'),
            log_dir=os.getenv('LOG_DIR', '/opt/smtp-tunnel/logs'),
            log_file=os.getenv('LOG_FILE', 'smtp-tunnel.log'),
            max_bytes=int(os.getenv('LOG_MAX_BYTES', 10 * 1024 * 1024)),
            backup_count=int(os.getenv('LOG_BACKUP_COUNT', 10)),
            rotation_type=os.getenv('LOG_ROTATION_TYPE', 'both'),
            date_format=os.getenv('LOG_DATE_FORMAT', '%Y-%m-%d'),
            format_string=os.getenv('LOG_FORMAT',
                '%(asctime)s - %(name)s - %(levelname)s - [%(context)s] - %(message)s'),
            enable_console=os.getenv('LOG_ENABLE_CONSOLE', 'true').lower() == 'true',
            enable_file=os.getenv('LOG_ENABLE_FILE', 'true').lower() == 'true',
            enable_journal=os.getenv('LOG_ENABLE_JOURNAL', 'true').lower() == 'true',
            context_fields=['username', 'ip', 'session_id']
        )

    def initialize(self, config: Optional[LogConfig] = None, config_file: Optional[str] = None):
        """
        初始化日志系统

        Args:
            config: 日志配置对象（可选）
            config_file: 配置文件路径（可选）
        """
        if config:
            self.config = config
        elif config_file:
            self.config = self.load_config_from_file(config_file)
        else:
            self.config = self._load_config_from_env()

        self._setup_log_directory()
        self._setup_root_logger()
        self._setup_context_filter()

    def _setup_log_directory(self):
        """
        设置日志目录
        """
        log_dir = Path(self.config.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

    def _setup_root_logger(self):
        """
        设置根日志记录器
        """
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, self.config.level.upper(), logging.INFO))

        root_logger.handlers.clear()

        if self.config.enable_console:
            self._add_console_handler(root_logger)

        if self.config.enable_file:
            self._add_file_handler(root_logger)

        if self.config.enable_journal and HAS_JOURNAL:
            self._add_journal_handler(root_logger)

    def _setup_context_filter(self):
        """
        设置上下文过滤器
        """
        self.context_filter = ContextFilter(self.config.context_fields)
        logging.getLogger().addFilter(self.context_filter)

    def _add_console_handler(self, logger: logging.Logger):
        """
        添加控制台处理器

        Args:
            logger: 日志记录器
        """
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, self.config.level.upper(), logging.INFO))

        formatter = LogFormatter(
            fmt=self.config.format_string,
            datefmt='%Y-%m-%d %H:%M:%S',
            use_color=sys.stdout.isatty()
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    def _add_file_handler(self, logger: logging.Logger):
        """
        添加文件处理器（支持轮转）

        Args:
            logger: 日志记录器
        """
        log_file_path = Path(self.config.log_dir) / self.config.log_file

        if self.config.rotation_type in ['size', 'both']:
            file_handler = logging.handlers.RotatingFileHandler(
                filename=log_file_path,
                maxBytes=self.config.max_bytes,
                backupCount=self.config.backup_count,
                encoding='utf-8'
            )
        elif self.config.rotation_type == 'date':
            file_handler = logging.handlers.TimedRotatingFileHandler(
                filename=log_file_path,
                when='midnight',
                interval=1,
                backupCount=self.config.backup_count,
                encoding='utf-8'
            )
        else:
            file_handler = logging.FileHandler(
                filename=log_file_path,
                encoding='utf-8'
            )

        file_handler.setLevel(getattr(logging, self.config.level.upper(), logging.INFO))

        formatter = LogFormatter(
            fmt=self.config.format_string,
            datefmt='%Y-%m-%d %H:%M:%S',
            use_color=False
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    def _add_journal_handler(self, logger: logging.Logger):
        """
        添加系统日志处理器

        Args:
            logger: 日志记录器
        """
        journal_handler = JournalHandler()
        journal_handler.setLevel(getattr(logging, self.config.level.upper(), logging.INFO))
        logger.addHandler(journal_handler)

    def get_logger(self, name: str) -> logging.Logger:
        """
        获取日志记录器

        Args:
            name: 日志记录器名称

        Returns:
            logging.Logger: 日志记录器对象
        """
        if name not in self.loggers:
            self.loggers[name] = logging.getLogger(name)
        return self.loggers[name]

    def add_context(self, **kwargs):
        """
        添加上下文信息

        Args:
            **kwargs: 上下文键值对
        """
        if self.context_filter:
            self.context_filter.add_context(**kwargs)

    def clear_context(self):
        """
        清除上下文信息
        """
        if self.context_filter:
            self.context_filter.clear_context()

    def log_exception(self, logger: logging.Logger, exc_info: bool = True):
        """
        记录异常信息

        Args:
            logger: 日志记录器
            exc_info: 是否包含异常信息
        """
        logger.error("发生异常", exc_info=exc_info)


def get_logger(name: str) -> logging.Logger:
    """
    获取日志记录器（便捷函数）

    Args:
        name: 日志记录器名称

    Returns:
        logging.Logger: 日志记录器对象
    """
    manager = LoggerManager()
    return manager.get_logger(name)


def add_context(**kwargs):
    """
    添加上下文信息（便捷函数）

    Args:
        **kwargs: 上下文键值对
    """
    manager = LoggerManager()
    manager.add_context(**kwargs)


def clear_context():
    """
    清除上下文信息（便捷函数）
    """
    manager = LoggerManager()
    manager.clear_context()


def log_exception(logger: logging.Logger, exc_info: bool = True):
    """
    记录异常信息（便捷函数）

    Args:
        logger: 日志记录器
        exc_info: 是否包含异常信息
    """
    manager = LoggerManager()
    manager.log_exception(logger, exc_info)
