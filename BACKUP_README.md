# 备份脚本使用说明

## 概述

本备份脚本为 SMTP Tunnel Proxy 项目提供完整的备份解决方案，支持全量备份、增量备份、压缩加密、定时备份等功能。

## 功能特性

- ✅ **增量备份** - 仅备份修改过的文件，提高备份效率
- ✅ **全量备份** - 完整备份工作区所有文件
- ✅ **错误处理** - 完善的异常处理机制，确保备份过程稳定
- ✅ **日志记录** - 详细的备份日志，便于审计和问题排查
- ✅ **自定义路径** - 支持自定义备份目标路径
- ✅ **周期设置** - 支持定时备份配置
- ✅ **压缩加密** - 支持备份文件压缩和 AES-256 加密
- ✅ **备份验证** - 自动验证备份完整性
- ✅ **自动清理** - 自动清理超过保留期的旧备份
- ✅ **备份恢复** - 支持从备份文件恢复数据

## 快速开始

### 1. 首次使用 - 执行全量备份

```bash
./backup.sh --full
```

### 2. 日常备份 - 执行增量备份

```bash
./backup.sh --incremental
```

### 3. 查看备份列表

```bash
./backup.sh --list
```

## 详细使用说明

### 基本命令

#### 执行全量备份

```bash
./backup.sh --full
```

首次使用必须执行全量备份，后续的增量备份将基于最近的全量备份。

#### 执行增量备份

```bash
./backup.sh --incremental
```

增量备份仅备份自上次备份以来修改过的文件，节省时间和空间。

#### 列出所有备份

```bash
./backup.sh --list
```

显示所有可用的备份文件，包括全量备份和增量备份。

#### 恢复备份

```bash
./backup.sh --restore <备份文件路径>
```

从指定的备份文件恢复数据到备份目录下的 restore 文件夹。

示例：
```bash
./backup.sh --restore backups/full/smtp-tunnel-backup_full_20240117_120000.tar.gz
```

#### 验证备份

```bash
./backup.sh --verify <备份文件路径>
```

验证备份文件的完整性，包括 tar 文件完整性、文件大小和 SHA256 哈希值。

示例：
```bash
./backup.sh --verify backups/full/smtp-tunnel-backup_full_20240117_120000.tar.gz
```

#### 清理旧备份

```bash
./backup.sh --clean
```

删除超过保留天数（默认 30 天）的旧备份文件。

### 高级配置

#### 指定备份目录

```bash
./backup.sh --backup-dir /path/to/backup --full
```

#### 启用加密

```bash
# 创建密码文件
echo 'your-secure-password' > .backup_password
chmod 600 .backup_password

# 执行加密备份
./backup.sh --encrypt --full
```

#### 使用配置文件

```bash
# 复制示例配置文件
cp .backup_config.example .backup_config

# 编辑配置文件
vim .backup_config

# 使用配置文件执行备份
./backup.sh --config .backup_config --full
```

#### 设置定时备份

```bash
# 设置每天凌晨 2 点执行增量备份
./backup.sh --setup-cron incremental "0 2 * * *"

# 设置每周日凌晨 3 点执行全量备份
./backup.sh --setup-cron full "0 3 * * 0"
```

#### 设置备份保留天数

```bash
./backup.sh --retention 60 --full
```

### 配置文件说明

配置文件 `.backup_config` 支持以下选项：

```bash
# 备份目录
BACKUP_DIR="/path/to/backup"

# 备份保留天数
RETENTION_DAYS=30

# 压缩级别 (1-9)
COMPRESSION_LEVEL=6

# 启用加密
ENCRYPT_BACKUP=true

# 加密密码文件
ENCRYPT_PASSWORD_FILE="/path/to/.backup_password"

# rsync 选项
RSYNC_OPTIONS="-avz --progress --delete"
```

## 备份策略建议

### 推荐的备份策略

1. **每周执行一次全量备份**（例如：每周日凌晨 3 点）
2. **每天执行一次增量备份**（例如：每天凌晨 2 点）
3. **保留 30 天的备份**

### 实施步骤

```bash
# 1. 设置每周全量备份
./backup.sh --setup-cron full "0 3 * * 0"

# 2. 设置每天增量备份
./backup.sh --setup-cron incremental "0 2 * * *"

# 3. 设置保留 60 天的备份
./backup.sh --retention 60 --clean
```

## 备份文件结构

```
backups/
├── full/                    # 全量备份目录
│   ├── smtp-tunnel-backup_full_20240117_120000.tar.gz
│   ├── smtp-tunnel-backup_full_20240117_120000.tar.gz.meta
│   └── ...
├── incremental/              # 增量备份目录
│   ├── smtp-tunnel-backup_incremental_20240118_020000.tar.gz
│   ├── smtp-tunnel-backup_incremental_20240118_020000.tar.gz.meta
│   └── ...
├── restore/                  # 恢复目录
│   └── 20240117_130000/
│       └── smtp-tunnel-backup_full_20240117_120000/
├── temp/                     # 临时目录
└── backup.log                # 备份日志
```

## 备份排除规则

默认排除以下文件和目录：

- Python 缓存文件 (`__pycache__/`, `*.pyc`)
- Git 相关文件 (`.git/`, `.gitignore`)
- 虚拟环境 (`.venv/`, `venv/`)
- IDE 配置 (`.vscode/`, `.idea/`)
- 日志文件 (`*.log`, `logs/`)
- 临时文件 (`*.tmp`, `temp/`)
- 客户端包 (`*.zip`, `pps/`)
- 系统文件 (`.DS_Store`, `Thumbs.db`)
- 备份目录 (`backups/`, `backup/`)

如需自定义排除规则，编辑 `.backup_exclude` 文件。

## 加密功能

### 启用加密

1. 创建密码文件：
```bash
echo 'your-secure-password' > .backup_password
chmod 600 .backup_password
```

2. 执行加密备份：
```bash
./backup.sh --encrypt --full
```

### 解密备份

如果备份文件已加密（`.tar.gz.enc`），恢复时会自动解密。

### 安全建议

- 使用强密码（至少 16 位，包含大小写字母、数字和特殊字符）
- 定期更换密码
- 妥善保管密码文件（设置权限为 600）
- 不要将密码文件提交到版本控制系统

## 日志说明

备份日志保存在 `backups/backup.log`，包含以下信息：

- 时间戳
- 操作类型
- 备份文件路径
- 备份大小
- 错误和警告信息
- 备份验证结果

查看日志：
```bash
tail -f backups/backup.log
```

## 故障排除

### 问题：备份失败，提示 "rsync 命令未找到"

**解决方案：**
```bash
# Ubuntu/Debian
sudo apt-get install rsync

# CentOS/RHEL
sudo yum install rsync

# macOS
brew install rsync
```

### 问题：加密失败，提示 "openssl 命令未找到"

**解决方案：**
```bash
# Ubuntu/Debian
sudo apt-get install openssl

# CentOS/RHEL
sudo yum install openssl

# macOS
brew install openssl
```

### 问题：增量备份失败，提示 "未找到全量备份"

**解决方案：**
首次使用必须先执行全量备份：
```bash
./backup.sh --full
```

### 问题：恢复备份时提示 "解密失败"

**解决方案：**
1. 检查密码文件是否存在
2. 确认密码文件权限为 600
3. 验证密码是否正确

### 问题：备份文件损坏

**解决方案：**
使用验证命令检查备份完整性：
```bash
./backup.sh --verify <备份文件路径>
```

## 最佳实践

1. **定期测试恢复** - 定期从备份恢复数据，确保备份可用
2. **监控备份日志** - 定期检查备份日志，及时发现异常
3. **异地备份** - 将备份文件复制到异地存储，防止本地灾难
4. **版本控制** - 保留多个版本的备份，便于回滚
5. **文档记录** - 记录备份策略和恢复流程
6. **权限管理** - 确保备份文件和目录的权限设置正确
7. **磁盘空间** - 定期检查磁盘空间，确保有足够空间存放备份

## 系统要求

- **操作系统**: Linux, macOS, 或 Windows (WSL)
- **必需工具**:
  - `bash` (版本 4.0+)
  - `tar`
  - `rsync`
  - `openssl` (如果使用加密功能)
- **可选工具**:
  - `cron` (用于定时备份)
  - `numfmt` (用于格式化文件大小)

## 性能优化

### 提高备份速度

1. 使用增量备份而非全量备份
2. 增加 `rsync` 并行传输数量
3. 使用 SSD 存储备份文件
4. 减少排除规则中的通配符

### 减少备份大小

1. 增加压缩级别（最高为 9）
2. 添加更多排除规则
3. 定期清理不必要的文件

### 节省磁盘空间

1. 减少备份保留天数
2. 定期清理旧备份
3. 使用压缩和加密功能

## 安全建议

1. **加密备份** - 启用加密功能保护敏感数据
2. **权限控制** - 设置严格的文件和目录权限
3. **密码管理** - 使用强密码并定期更换
4. **访问控制** - 限制备份文件的访问权限
5. **审计日志** - 定期审查备份日志
6. **安全存储** - 将备份存储在安全的位置

## 支持与反馈

如有问题或建议，请通过以下方式联系：

- 提交 Issue
- 发送邮件
- 查看文档

## 许可证

本备份脚本遵循 SMTP Tunnel Proxy 项目的许可证。

## 更新日志

### v1.0.0 (2024-01-17)

- 初始版本发布
- 支持全量备份和增量备份
- 支持压缩和加密
- 支持定时备份
- 支持备份验证和恢复
- 支持自动清理旧备份
