# SMTP 隧道客户端更新脚本使用说明

## 概述

`smtp-tunnel-client-update` 是一个用于更新 SMTP 隧道客户端的自动化脚本。它提供了完整的更新流程，包括版本检查、文件下载、校验、备份、更新和回滚等功能。

## 功能特性

### 1. 版本管理
- **当前版本检查**：从本地 `client.py` 文件读取当前版本
- **最新版本检查**：通过 GitHub API 获取最新版本信息
- **版本比较**：自动比较当前版本和最新版本

### 2. 下载和更新
- **文件下载**：从 GitHub 下载最新的程序文件
- **重试机制**：下载失败时自动重试（最多 3 次）
- **进度显示**：实时显示下载进度

### 3. 文件校验
- **文件完整性检查**：验证下载的文件是否完整
- **语法检查**：对 Python 文件进行语法验证
- **文件大小检查**：确保下载的文件不为空

### 4. 备份和回滚
- **自动备份**：更新前自动备份当前版本
- **回滚机制**：更新失败时自动回滚到备份版本
- **备份清理**：自动清理超过 7 天的旧备份

### 5. 依赖管理
- **虚拟环境检查**：检查 Python 虚拟环境是否存在
- **pip 升级**：自动升级 pip 到最新版本
- **依赖包更新**：根据 `requirements.txt` 更新依赖包

### 6. 服务管理
- **停止客户端**：更新前安全停止客户端
- **启动客户端**：更新后自动启动客户端
- **状态检查**：检查客户端运行状态

### 7. 日志记录
- **详细日志**：记录所有操作和错误信息
- **日志文件**：保存到 `logs/client-update.log`
- **调试模式**：支持调试模式输出详细信息

## 使用方法

### 基本用法

```bash
# 正常更新（检查版本、下载、更新、重启）
./smtp-tunnel-client-update

# 或使用 bash 执行
bash smtp-tunnel-client-update
```

### 命令行选项

| 选项 | 说明 |
|------|------|
| `--check-only` | 仅检查版本，不执行更新 |
| `--no-restart` | 更新后不重启客户端 |
| `--no-backup` | 不创建备份（不推荐） |
| `--force` | 强制更新，即使版本相同 |
| `--debug` | 启用调试模式 |
| `-h, --help` | 显示帮助信息 |

### 使用示例

```bash
# 仅检查版本
./smtp-tunnel-client-update --check-only

# 更新但不重启客户端
./smtp-tunnel-client-update --no-restart

# 强制更新（即使版本相同）
./smtp-tunnel-client-update --force

# 调试模式（显示详细信息）
./smtp-tunnel-client-update --debug

# 使用环境变量启用调试模式
DEBUG_MODE=true ./smtp-tunnel-client-update

# 组合使用多个选项
./smtp-tunnel-client-update --no-restart --debug
```

## 工作流程

### 完整更新流程

1. **前置检查**
   - 检查客户端是否已安装
   - 检查日志目录
   - 检查备份目录
   - 检查网络连接

2. **版本检查**
   - 读取当前版本
   - 获取最新版本
   - 比较版本差异

3. **创建备份**
   - 备份所有程序文件
   - 备份管理脚本
   - 保存备份路径

4. **停止服务**
   - 停止客户端进程
   - 等待进程完全停止

5. **下载更新**
   - 下载程序文件
   - 下载管理脚本
   - 校验文件完整性

6. **安装更新**
   - 替换程序文件
   - 设置文件权限
   - 更新 Python 依赖

7. **清理备份**
   - 删除超过保留期的旧备份

8. **启动服务**
   - 启动客户端
   - 检查运行状态

9. **显示摘要**
   - 显示更新结果
   - 显示管理命令

### 错误处理流程

如果更新过程中出现错误：

1. **下载失败**
   - 自动重试（最多 3 次）
   - 记录错误日志
   - 回滚到备份版本

2. **文件校验失败**
   - 记录错误日志
   - 回滚到备份版本

3. **更新失败**
   - 自动回滚到备份版本
   - 显示错误信息
   - 记录详细日志

## 目录结构

```
smtp-tunnel/
├── client.py                 # 客户端主程序
├── socks5_server.py          # SOCKS5 代理服务器
├── config.py                 # 配置管理模块
├── logger.py                # 日志管理模块
├── connection.py            # 连接管理模块
├── protocol/                # 协议模块目录
│   ├── __init__.py
│   ├── core.py
│   └── client.py
├── tunnel/                  # 隧道模块目录
│   ├── __init__.py
│   ├── crypto.py
│   ├── base.py
│   └── client.py
├── start.sh                 # 启动脚本
├── stop.sh                  # 停止脚本
├── status.sh                # 状态脚本
├── smtp-tunnel-client-update # 更新脚本（本脚本）
├── config/                  # 配置文件目录
│   ├── config.yaml
│   ├── ca.crt
│   ├── client.crt
│   └── client.key
├── logs/                    # 日志目录
│   ├── client.log
│   └── client-update.log    # 更新日志
└── backups/                 # 备份目录
    └── backup_YYYYMMDD_HHMMSS/
```

## 日志文件

### 更新日志位置

```
logs/client-update.log
```

### 日志格式

```
[2026-01-17 10:30:00] [INFO] 开始客户端更新
[2026-01-17 10:30:01] [INFO] 脚本目录: /root/smtp-tunnel
[2026-01-17 10:30:01] [INFO] 安装目录: /root/smtp-tunnel
[2026-01-17 10:30:02] [INFO] 当前版本: 1.3.0
[2026-01-17 10:30:03] [INFO] 最新版本: 1.4.0
[2026-01-17 10:30:05] [INFO] 备份创建完成: /root/smtp-tunnel/backups/backup_20260117_103005
[2026-01-17 10:30:10] [INFO] 更新成功: client.py
[2026-01-17 10:30:11] [SUCCESS] 客户端更新成功
```

### 查看日志

```bash
# 查看完整日志
cat logs/client-update.log

# 实时查看日志
tail -f logs/client-update.log

# 查看最近 50 行
tail -n 50 logs/client-update.log

# 搜索错误信息
grep ERROR logs/client-update.log
```

## 备份管理

### 备份位置

```
backups/backup_YYYYMMDD_HHMMSS/
```

### 备份内容

- 所有程序文件（`client.py`, `socks5_server.py` 等）
- 协议模块（`protocol/` 目录）
- 隧道模块（`tunnel/` 目录）
- 管理脚本（`start.sh`, `stop.sh`, `status.sh`）

### 手动回滚

如果需要手动回滚到之前的版本：

```bash
# 查看可用备份
ls -la backups/

# 手动回滚到指定备份
cp -r backups/backup_20260117_100000/* .
chmod +x start.sh stop.sh status.sh

# 重启客户端
./stop.sh
./start.sh
```

### 清理旧备份

脚本会自动清理超过 7 天的备份。如果需要手动清理：

```bash
# 删除所有备份
rm -rf backups/backup_*

# 删除指定备份
rm -rf backups/backup_20260117_100000
```

## 故障排除

### 问题 1：无法连接到 GitHub

**错误信息：**
```
[ERROR] 无法连接到 GitHub，请检查网络连接
```

**解决方案：**
1. 检查网络连接
2. 检查防火墙设置
3. 尝试使用代理

### 问题 2：虚拟环境不存在

**错误信息：**
```
[WARN] 虚拟环境不存在: /root/smtp-tunnel/venv
```

**解决方案：**
```bash
# 重新创建虚拟环境
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 问题 3：更新失败

**错误信息：**
```
[ERROR] 文件更新失败
[STEP] 正在回滚到备份...
```

**解决方案：**
1. 查看更新日志：`cat logs/client-update.log`
2. 检查网络连接
3. 手动回滚到备份版本
4. 重新运行更新脚本

### 问题 4：客户端启动失败

**错误信息：**
```
[WARN] 客户端可能未正常启动，请检查日志
```

**解决方案：**
1. 查看客户端日志：`cat logs/client.log`
2. 检查配置文件：`cat config/config.yaml`
3. 检查证书文件是否存在
4. 手动启动客户端：`./start.sh`

## 高级用法

### 自定义配置

可以通过修改脚本中的配置变量来自定义行为：

```bash
# 最大重试次数
MAX_RETRIES=3

# 重试延迟（秒）
RETRY_DELAY=2

# 备份保留天数
BACKUP_RETENTION_DAYS=7
```

### 集成到 CI/CD

可以将更新脚本集成到 CI/CD 流程中：

```yaml
# 示例 GitHub Actions 工作流
- name: Update Client
  run: |
    cd /path/to/smtp-tunnel
    ./smtp-tunnel-client-update --no-restart
```

### 定时更新

使用 cron 定时更新：

```bash
# 编辑 crontab
crontab -e

# 添加定时任务（每天凌晨 2 点更新）
0 2 * * * cd /root/smtp-tunnel && ./smtp-tunnel-client-update --no-restart >> /var/log/smtp-tunnel-update.log 2>&1
```

## 安全建议

1. **备份重要数据**
   - 定期备份配置文件
   - 保留多个版本的备份

2. **测试更新**
   - 在测试环境中先测试更新
   - 验证更新后再在生产环境执行

3. **监控日志**
   - 定期检查更新日志
   - 及时发现和解决问题

4. **权限管理**
   - 确保脚本有正确的执行权限
   - 限制对备份目录的访问权限

## 版本历史

- **1.0.0** (2026-01-17)
  - 初始版本
  - 支持基本更新功能
  - 支持备份和回滚
  - 支持日志记录

## 支持

如有问题或建议，请访问：
- GitHub: https://github.com/purpose168/smtp-tunnel-proxy
- Issues: https://github.com/purpose168/smtp-tunnel-proxy/issues

## 许可证

GPL-3.0
