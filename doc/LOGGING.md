# SMTP 隧道代理日志系统文档

## 目录

1. [概述](#概述)
2. [功能特性](#功能特性)
3. [配置说明](#配置说明)
4. [使用方法](#使用方法)
5. [日志轮转](#日志轮转)
6. [环境变量](#环境变量)
7. [测试验证](#测试验证)
8. [故障排查](#故障排查)
9. [最佳实践](#最佳实践)

---

## 概述

SMTP 隧道代理日志系统是一个功能完善的日志管理解决方案，提供多级别日志记录、自动轮转、上下文追踪和灵活配置等功能。

### 核心组件

- **logger.py**: 日志管理核心模块
- **config.yaml**: 日志配置文件
- **logrotate.conf**: 日志轮转配置
- **test_logger.py**: 日志系统测试脚本

### 设计目标

- ✅ 捕获系统运行过程中的关键事件
- ✅ 记录错误信息和警告提示
- ✅ 支持调试信息输出
- ✅ 自动日志轮转，避免单个文件过大
- ✅ 结构化日志格式，便于分析和查询
- ✅ 上下文信息追踪，支持问题定位
- ✅ 灵活配置，支持配置文件和环境变量

---

## 功能特性

### 1. 多级别日志记录

支持标准的 Python 日志级别：

| 级别 | 数值 | 用途 | 示例 |
|--------|--------|--------|--------|
| DEBUG | 10 | 详细的调试信息 | 函数调用参数、中间变量值 |
| INFO | 20 | 一般信息 | 服务启动、用户登录 |
| WARNING | 30 | 警告信息 | 连接超时、资源使用高 |
| ERROR | 40 | 错误信息 | 连接失败、认证错误 |
| CRITICAL | 50 | 严重错误 | 服务崩溃、数据丢失 |

### 2. 日志轮转机制

支持三种轮转策略：

- **按大小轮转**: 当日志文件达到指定大小时自动轮转
- **按日期轮转**: 每天自动创建新的日志文件
- **混合轮转**: 同时按大小和日期轮转（推荐）

### 3. 上下文信息追踪

支持在日志中添加上下文信息，便于追踪请求、用户、会话等：

```python
from logger import add_context

# 添加上下文信息
add_context(username="testuser", ip="192.168.1.100", session_id="abc123")
logger.info("用户登录成功")
```

日志输出：
```
2025-01-11 10:30:45 - smtp-tunnel - INFO - [username=testuser | ip=192.168.1.100 | session_id=abc123] - 用户登录成功
```

### 4. 多输出目标

支持同时输出到多个目标：

- **控制台**: 彩色输出，便于开发调试
- **文件**: 持久化存储，支持轮转
- **系统日志**: 集成到 systemd journal

### 5. 异常捕获

完整的异常信息记录，包括堆栈跟踪：

```python
try:
    result = 10 / 0
except ZeroDivisionError as e:
    logger.error("发生除零错误", exc_info=True)
```

---

## 配置说明

### 配置文件 (config.yaml)

在 `config.yaml` 中添加日志配置：

```yaml
# 日志配置
logging:
  # 日志级别: DEBUG, INFO, WARNING, ERROR, CRITICAL
  level: "INFO"

  # 日志存储目录
  log_dir: "/var/log/smtp-tunnel"

  # 日志文件名（支持日期占位符）
  log_file: "smtp-tunnel.log"

  # 单个日志文件最大大小（字节）- 默认 10MB
  max_bytes: 10485760

  # 保留的备份文件数量
  backup_count: 10

  # 日志轮转类型: size（按大小）, date（按日期）, both（同时按大小和日期）
  rotation_type: "both"

  # 日期格式（用于文件名）
  date_format: "%Y-%m-%d"

  # 日志格式字符串
  format_string: "%(asctime)s - %(name)s - %(levelname)s - [%(context)s] - %(message)s"

  # 是否输出到控制台
  enable_console: true

  # 是否输出到文件
  enable_file: true

  # 是否输出到系统日志（systemd journal）
  enable_journal: true

  # 上下文字段列表
  context_fields:
    - "username"
    - "ip"
    - "session_id"
    - "connection_id"
```

### 配置参数详解

#### level
日志级别，控制输出的详细程度：

- `DEBUG`: 输出所有级别的日志
- `INFO`: 输出 INFO 及以上级别的日志（推荐用于生产环境）
- `WARNING`: 输出 WARNING 及以上级别的日志
- `ERROR`: 只输出 ERROR 和 CRITICAL 日志
- `CRITICAL`: 只输出 CRITICAL 日志

#### log_dir
日志文件存储目录：

- 生产环境: `/var/log/smtp-tunnel`
- 开发环境: `./logs` 或 `/tmp/smtp-tunnel-logs`
- Docker 容器: `/app/logs`

#### log_file
日志文件名，支持日期占位符：

- 固定文件名: `smtp-tunnel.log`
- 按日期命名: `smtp-tunnel-%Y-%m-%d.log`
- 按小时命名: `smtp-tunnel-%Y-%m-%d-%H.log`

支持的占位符：
- `%Y`: 四位年份 (2025)
- `%m`: 两位月份 (01-12)
- `%d`: 两位日期 (01-31)
- `%H`: 两位小时 (00-23)
- `%M`: 两位分钟 (00-59)

#### max_bytes
单个日志文件的最大大小（字节）：

- 10MB: `10485760` (默认)
- 100MB: `104857600`
- 1GB: `1073741824`

#### backup_count
保留的备份文件数量：

- 默认: 10
- 推荐: 30（保留30天的日志）
- 最小: 1

#### rotation_type
日志轮转类型：

- `size`: 按文件大小轮转
- `date`: 按日期轮转
- `both`: 同时按大小和日期轮转（推荐）

#### format_string
日志格式字符串，支持标准 Python logging 格式化占位符：

- `%(asctime)s`: 时间戳
- `%(name)s`: 日志记录器名称
- `%(levelname)s`: 日志级别
- `%(message)s`: 日志消息
- `%(context)s`: 上下文信息（自定义）

#### context_fields
上下文字段列表，用于追踪：

```yaml
context_fields:
  - "username"      # 用户名
  - "ip"           # IP地址
  - "session_id"    # 会话ID
  - "connection_id" # 连接ID
  - "request_id"    # 请求ID
```

---

## 使用方法

### 基本使用

在代码中使用日志：

```python
from logger import get_logger

# 获取日志记录器
logger = get_logger('my-module')

# 记录不同级别的日志
logger.debug("调试信息")
logger.info("一般信息")
logger.warning("警告信息")
logger.error("错误信息")
logger.critical("严重错误")
```

### 上下文追踪

添加上下文信息以追踪请求：

```python
from logger import get_logger, add_context, clear_context

logger = get_logger('my-module')

# 添加上下文信息
add_context(username="testuser", ip="192.168.1.100", session_id="abc123")
logger.info("用户登录成功")

# 更新上下文信息
add_context(username="testuser", ip="192.168.1.100", session_id="abc123", action="send_email")
logger.info("发送邮件")

# 清除上下文信息
clear_context()
logger.info("上下文已清除")
```

### 异常记录

记录异常信息：

```python
from logger import get_logger, log_exception

logger = get_logger('my-module')

try:
    # 可能出错的代码
    result = 10 / 0
except Exception as e:
    # 记录异常（包含堆栈跟踪）
    logger.error(f"操作失败: {e}", exc_info=True)
```

或者使用便捷函数：

```python
from logger import get_logger, log_exception

logger = get_logger('my-module')

try:
    result = 10 / 0
except Exception:
    log_exception(logger)
```

### 初始化日志系统

在程序启动时初始化日志系统：

```python
from logger import LoggerManager

# 创建日志管理器实例
log_manager = LoggerManager()

# 从配置文件初始化
log_manager.initialize(config_file='config.yaml')

# 或者使用自定义配置
from logger import LogConfig
config = LogConfig(
    level='DEBUG',
    log_dir='./logs',
    log_file='app.log',
    enable_console=True,
    enable_file=True
)
log_manager.initialize(config=config)
```

### 在 server.py 中使用

server.py 已集成日志系统：

```python
from logger import LoggerManager, get_logger, add_context, clear_context

# 初始化日志系统
log_manager = LoggerManager()
log_manager.initialize(config_file=args.config)

# 获取日志记录器
logger = get_logger('smtp-tunnel-server')

# 使用日志
logger.info("服务器启动")
add_context(username="testuser", ip="192.168.1.100")
logger.info("用户连接")
```

---

## 日志轮转

### Python 内置轮转

使用 Python logging 模块的轮转处理器：

```python
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler

# 按大小轮转
handler = RotatingFileHandler(
    filename='app.log',
    maxBytes=10*1024*1024,  # 10MB
    backupCount=10
)

# 按日期轮转
handler = TimedRotatingFileHandler(
    filename='app.log',
    when='midnight',  # 每天午夜轮转
    interval=1,
    backupCount=30
)
```

### logrotate 配置

使用系统 logrotate 进行日志轮转（推荐用于生产环境）：

1. 安装 logrotate 配置：

```bash
sudo cp logrotate.conf /etc/logrotate.d/smtp-tunnel
```

2. 验证配置：

```bash
sudo logrotate -d /etc/logrotate.d/smtp-tunnel
```

3. 手动测试轮转：

```bash
sudo logrotate -f /etc/logrotate.d/smtp-tunnel
```

### logrotate 配置详解

```conf
/var/log/smtp-tunnel/*.log {
    # 每天轮转一次
    daily

    # 保留最近30天的日志
    rotate 30

    # 如果日志文件为空则不轮转
    notifempty

    # 轮转后创建新日志文件
    create 0644 root root

    # 压缩旧日志文件
    compress

    # 延迟压缩（下次轮转时才压缩）
    delaycompress

    # 日志文件大小超过100MB时立即轮转
    size 100M

    # 缺失日志文件时不报错
    missingok

    # 轮转后通知应用程序重新打开日志文件
    # postrotate
    #     systemctl reload smtp-tunnel > /dev/null 2>&1 || true
    # endscript
}
```

### 轮转文件命名

轮转后的日志文件命名规则：

- 按大小轮转: `smtp-tunnel.log.1`, `smtp-tunnel.log.2`, ...
- 按日期轮转: `smtp-tunnel.log.2025-01-10`, `smtp-tunnel.log.2025-01-11`, ...
- 混合轮转: `smtp-tunnel.log.2025-01-10.1`, `smtp-tunnel.log.2025-01-10.2`, ...

压缩后的文件：
- `smtp-tunnel.log.1.gz`
- `smtp-tunnel.log.2025-01-10.gz`

---

## 环境变量

支持通过环境变量配置日志系统：

| 环境变量 | 说明 | 默认值 | 示例 |
|-----------|--------|---------|--------|
| `LOG_LEVEL` | 日志级别 | INFO | `LOG_LEVEL=DEBUG` |
| `LOG_DIR` | 日志目录 | /var/log/smtp-tunnel | `LOG_DIR=/tmp/logs` |
| `LOG_FILE` | 日志文件名 | smtp-tunnel.log | `LOG_FILE=app.log` |
| `LOG_MAX_BYTES` | 最大文件大小（字节） | 10485760 | `LOG_MAX_BYTES=52428800` |
| `LOG_BACKUP_COUNT` | 备份文件数量 | 10 | `LOG_BACKUP_COUNT=30` |
| `LOG_ROTATION_TYPE` | 轮转类型 | both | `LOG_ROTATION_TYPE=size` |
| `LOG_DATE_FORMAT` | 日期格式 | %Y-%m-%d | `LOG_DATE_FORMAT=%Y%m%d` |
| `LOG_FORMAT` | 日志格式字符串 | - | `LOG_FORMAT=%(message)s` |
| `LOG_ENABLE_CONSOLE` | 是否输出到控制台 | true | `LOG_ENABLE_CONSOLE=false` |
| `LOG_ENABLE_FILE` | 是否输出到文件 | true | `LOG_ENABLE_FILE=false` |
| `LOG_ENABLE_JOURNAL` | 是否输出到系统日志 | true | `LOG_ENABLE_JOURNAL=false` |

### 使用环境变量

#### 方法1: 在命令行中设置

```bash
LOG_LEVEL=DEBUG LOG_DIR=/tmp/logs python server.py
```

#### 方法2: 在 systemd 服务中设置

```ini
[Service]
Environment=LOG_LEVEL=DEBUG
Environment=LOG_DIR=/var/log/smtp-tunnel
Environment=LOG_ENABLE_CONSOLE=true
```

#### 方法3: 在 Docker 容器中设置

```yaml
version: '3'
services:
  smtp-tunnel:
    image: smtp-tunnel:latest
    environment:
      - LOG_LEVEL=INFO
      - LOG_DIR=/app/logs
      - LOG_ENABLE_CONSOLE=false
```

---

## 测试验证

### 运行测试脚本

```bash
python test_logger.py
```

### 测试内容

测试脚本包含以下测试：

1. **基本日志记录功能**
   - 测试不同级别的日志输出
   - 验证日志格式正确性
   - 检查时间戳准确性

2. **上下文信息记录功能**
   - 测试上下文信息的添加
   - 验证上下文在日志中的显示
   - 测试上下文信息的清除

3. **异常捕获和记录功能**
   - 测试异常信息的完整记录
   - 验证堆栈跟踪的显示
   - 测试异常上下文的保留

4. **日志轮转功能**
   - 测试按大小轮转
   - 验证备份文件的生成
   - 检查文件数量限制

5. **配置加载功能**
   - 测试从配置文件加载
   - 测试从环境变量加载
   - 验证配置优先级

6. **日志系统性能**
   - 测试大量日志写入性能
   - 测试上下文切换性能
   - 测试异常记录性能

7. **日志级别过滤功能**
   - 测试不同级别下的日志输出
   - 验证级别切换功能
   - 测试级别继承机制

### 测试输出示例

```
============================================================
SMTP 隧道日志系统测试
============================================================
使用临时日志目录: /tmp/smtp-tunnel-log-test-xxxx

============================================================
测试1: 基本日志记录功能
============================================================
2025-01-11 10:30:45 - test-basic - INFO - [-] - 这是一条INFO级别的日志
2025-01-11 10:30:45 - test-basic - WARNING - [-] - 这是一条WARNING级别的日志
2025-01-11 10:30:45 - test-basic - ERROR - [-] - 这是一条ERROR级别的日志
2025-01-11 10:30:45 - test-basic - CRITICAL - [-] - 这是一条CRITICAL级别的日志
✅ 基本日志记录测试完成

============================================================
测试2: 上下文信息记录功能
============================================================
2025-01-11 10:30:45 - test-context - INFO - [username=testuser | ip=192.168.1.100 | session_id=abc123] - 用户登录成功
✅ 上下文信息记录测试完成

============================================================
✅ 所有测试完成
============================================================
```

---

## 故障排查

### 常见问题

#### 1. 日志文件未创建

**症状**: 日志目录为空，没有日志文件

**可能原因**:
- 日志目录权限不足
- 日志目录不存在
- 磁盘空间不足

**解决方案**:
```bash
# 检查日志目录权限
ls -la /var/log/smtp-tunnel

# 创建日志目录并设置权限
sudo mkdir -p /var/log/smtp-tunnel
sudo chown root:root /var/log/smtp-tunnel
sudo chmod 755 /var/log/smtp-tunnel

# 检查磁盘空间
df -h /var/log
```

#### 2. 日志轮转不工作

**症状**: 日志文件持续增长，没有轮转

**可能原因**:
- 轮转配置错误
- logrotate 未安装
- logrotate 配置文件路径错误

**解决方案**:
```bash
# 检查 logrotate 是否安装
which logrotate

# 验证 logrotate 配置
sudo logrotate -d /etc/logrotate.d/smtp-tunnel

# 手动触发轮转
sudo logrotate -f /etc/logrotate.d/smtp-tunnel

# 检查 logrotate 日志
sudo cat /var/log/logrotate.log
```

#### 3. 上下文信息不显示

**症状**: 日志中的 context 字段为 "-"

**可能原因**:
- 未调用 `add_context()`
- 上下文字段名称不匹配
- 上下文被清除

**解决方案**:
```python
# 确保在记录日志前添加上下文
add_context(username="testuser", ip="192.168.1.100")
logger.info("用户登录")

# 确保上下文字段名称与配置一致
# config.yaml 中定义的字段
context_fields:
  - "username"
  - "ip"

# 代码中使用的字段
add_context(username="testuser", ip="192.168.1.100")
```

#### 4. 日志级别不生效

**症状**: 设置了日志级别，但仍然输出其他级别的日志

**可能原因**:
- 配置文件未正确加载
- 环境变量优先级问题
- 日志记录器级别未设置

**解决方案**:
```python
# 确保正确初始化日志系统
log_manager = LoggerManager()
log_manager.initialize(config_file='config.yaml')

# 检查配置是否正确加载
print(f"日志级别: {log_manager.config.level}")

# 设置日志记录器级别
logger = get_logger('my-module')
logger.setLevel('DEBUG')
```

#### 5. systemd journal 中没有日志

**症状**: 使用 `journalctl` 查看不到日志

**可能原因**:
- `enable_journal` 设置为 false
- systemd journal 未启用
- 权限不足

**解决方案**:
```bash
# 检查 systemd 服务配置
sudo systemctl cat smtp-tunnel

# 查看日志
sudo journalctl -u smtp-tunnel -n 100

# 检查 journal 状态
sudo journalctl --disk-usage
```

### 调试技巧

#### 启用调试模式

```bash
# 方法1: 使用命令行参数
python server.py --debug

# 方法2: 设置环境变量
LOG_LEVEL=DEBUG python server.py

# 方法3: 修改配置文件
# config.yaml
logging:
  level: "DEBUG"
```

#### 查看实时日志

```bash
# 查看日志文件
tail -f /var/log/smtp-tunnel/smtp-tunnel.log

# 查看 systemd 日志
sudo journalctl -u smtp-tunnel -f

# 查看所有日志（包括轮转的）
tail -f /var/log/smtp-tunnel/smtp-tunnel.log*
```

#### 搜索日志

```bash
# 搜索错误日志
grep ERROR /var/log/smtp-tunnel/smtp-tunnel.log

# 搜索特定用户的日志
grep "username=testuser" /var/log/smtp-tunnel/smtp-tunnel.log

# 搜索特定时间段的日志
grep "2025-01-11 10:" /var/log/smtp-tunnel/smtp-tunnel.log

# 使用 journalctl 搜索
sudo journalctl -u smtp-tunnel --since "2025-01-11 10:00" --until "2025-01-11 11:00"
```

---

## 最佳实践

### 1. 日志级别选择

- **开发环境**: 使用 `DEBUG` 级别，获取详细信息
- **测试环境**: 使用 `INFO` 级别，平衡详细程度和性能
- **生产环境**: 使用 `WARNING` 或 `ERROR` 级别，减少日志量

### 2. 日志轮转策略

- **小型应用**: 按日期轮转，保留 7-30 天
- **中型应用**: 按大小轮转（100MB），保留 30 个备份
- **大型应用**: 混合轮转，保留 30-90 天

### 3. 上下文信息使用

- 在请求开始时添加上下文
- 在请求结束时清除上下文
- 使用有意义的字段名称
- 避免在上下文中存储敏感信息

### 4. 异常处理

- 始终记录异常的完整信息
- 使用 `exc_info=True` 包含堆栈跟踪
- 在异常消息中提供有用的上下文
- 避免捕获并忽略异常

### 5. 性能优化

- 避免在热路径中使用 DEBUG 日志
- 使用字符串格式化而不是字符串连接
- 考虑使用异步日志处理器
- 定期清理旧日志文件

### 6. 安全考虑

- 不要在日志中记录敏感信息（密码、密钥）
- 对日志文件设置适当的权限（644 或 600）
- 定期审计日志内容
- 考虑日志加密

### 7. 监控和告警

- 监控日志文件大小
- 监控 ERROR 和 CRITICAL 日志数量
- 设置日志告警阈值
- 集成到监控系统（Prometheus、Grafana）

### 8. 日志分析

- 使用日志分析工具（ELK、Splunk）
- 建立日志查询和报表
- 定期分析日志趋势
- 识别和解决常见问题

---

## 附录

### A. 日志格式示例

#### 标准格式

```
2025-01-11 10:30:45 - smtp-tunnel - INFO - [username=testuser | ip=192.168.1.100] - 用户登录成功
```

#### 异常格式

```
2025-01-11 10:30:45 - smtp-tunnel - ERROR - [-] - 发生除零错误
Traceback (most recent call last):
  File "/app/server.py", line 123, in process_request
    result = 10 / 0
ZeroDivisionError: division by zero
```

#### 上下文格式

```
2025-01-11 10:30:45 - smtp-tunnel - INFO - [username=testuser | ip=192.168.1.100 | session_id=abc123 | connection_id=conn456] - 建立连接
```

### B. 配置文件完整示例

```yaml
# SMTP 隧道配置
server:
  host: "0.0.0.0"
  port: 587
  hostname: "mail.example.com"
  cert_file: "server.crt"
  key_file: "server.key"
  users_file: "users.yaml"
  log_users: true

# 日志配置
logging:
  level: "INFO"
  log_dir: "/var/log/smtp-tunnel"
  log_file: "smtp-tunnel.log"
  max_bytes: 10485760
  backup_count: 10
  rotation_type: "both"
  date_format: "%Y-%m-%d"
  format_string: "%(asctime)s - %(name)s - %(levelname)s - [%(context)s] - %(message)s"
  enable_console: true
  enable_file: true
  enable_journal: true
  context_fields:
    - "username"
    - "ip"
    - "session_id"
    - "connection_id"

client:
  server_host: "mail.example.com"
  server_port: 587
  socks_port: 1080
  socks_host: "127.0.0.1"
  ca_cert: "ca.crt"
```

### C. systemd 服务配置

```ini
[Unit]
Description=SMTP 隧道代理服务器
Documentation=https://github.com/purpose168/smtp-tunnel-proxy
After=network.target
RequiresMountsFor=/opt/smtp-tunnel
RequiresMountsFor=/etc/smtp-tunnel

[Service]
Type=simple
User=root
WorkingDirectory=/opt/smtp-tunnel

ExecStart=/opt/smtp-tunnel/venv/bin/python /opt/smtp-tunnel/server.py -c /etc/smtp-tunnel/config.yaml

Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

# Python 环境变量
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=VIRTUAL_ENV=/opt/smtp-tunnel/venv
Environment=PATH=/opt/smtp-tunnel/venv/bin:/usr/local/bin:/usr/bin:/bin

# 日志环境变量（可选）
Environment=LOG_LEVEL=INFO
Environment=LOG_DIR=/var/log/smtp-tunnel

# 资源限制
LimitNOFILE=65536
LimitNPROC=4096

# 安全加固配置
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictRealtime=true
RestrictSUIDSGID=true
RemoveIPC=true
SystemCallFilter=@system-service
SystemCallErrorNumber=EPERM

# 允许写入的路径
ReadWritePaths=/etc/smtp-tunnel
ReadWritePaths=/opt/smtp-tunnel
ReadWritePaths=/var/log/smtp-tunnel

# 日志轮转配置
# 日志文件将在达到大小时自动轮转
# 使用logrotate进行日志管理
# 配置文件位于: /etc/logrotate.d/smtp-tunnel

# 私有临时目录
PrivateTmp=true

# 网络绑定能力
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
```

### D. 相关命令

```bash
# 查看日志
tail -f /var/log/smtp-tunnel/smtp-tunnel.log

# 查看系统日志
sudo journalctl -u smtp-tunnel -n 100

# 测试日志轮转
sudo logrotate -f /etc/logrotate.d/smtp-tunnel

# 搜索错误
grep ERROR /var/log/smtp-tunnel/smtp-tunnel.log

# 查看日志文件大小
du -sh /var/log/smtp-tunnel/

# 清理旧日志
find /var/log/smtp-tunnel -name "*.gz" -mtime +30 -delete
```

---

**文档版本**: 1.0.0
**最后更新**: 2025-01-11
**维护者**: SMTP 隧道代理团队
