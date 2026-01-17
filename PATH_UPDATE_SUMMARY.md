# 路径更新总结

## 更新日期
2026-01-17

## 更新目的
将所有服务器端脚本的安装路径从脚本所在目录或 `/etc/smtp-tunnel`、`/var/log/smtp-tunnel` 统一更新为系统级 `/opt/smtp-tunnel` 目录，符合 Linux 系统标准目录结构规范。

## 更新的文件列表

### 1. install-server.sh
**文件路径**: `/home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/install-server.sh`

**修改内容**:
- 移除 `SCRIPT_DIR` 变量定义
- 更新 `INSTALL_DIR` 从 `$SCRIPT_DIR/smtp-tunnel` 到 `/opt/smtp-tunnel`
- 更新 `CONFIG_DIR` 从 `$SCRIPT_DIR/smtp-tunnel` 到 `/opt/smtp-tunnel/config`
- 更新 `VENV_DIR` 从 `$SCRIPT_DIR/smtp-tunnel/venv` 到 `/opt/smtp-tunnel/venv`
- 更新 `LOG_DIR` 从 `$SCRIPT_DIR/smtp-tunnel/logs` 到 `/opt/smtp-tunnel/logs`
- 添加 `LOGROTATE_CONF` 变量定义为 `$LOG_DIR/logrotate.conf`

**修改行数**: 第 20-40 行

---

### 2. smtp-tunnel-update
**文件路径**: `/home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/smtp-tunnel-update`

**修改内容**:
- 移除 `SCRIPT_DIR` 变量定义
- 更新 `INSTALL_DIR` 从 `$SCRIPT_DIR` 到 `/opt/smtp-tunnel`
- 更新 `CONFIG_DIR` 从 `$SCRIPT_DIR` 到 `/opt/smtp-tunnel/config`
- 更新 `VENV_DIR` 从 `$SCRIPT_DIR/venv` 到 `/opt/smtp-tunnel/venv`
- 更新 `LOG_DIR` 从 `$SCRIPT_DIR/logs` 到 `/opt/smtp-tunnel/logs`

**修改行数**: 第 18-26 行

---

### 3. smtp-tunnel-adduser
**文件路径**: `/home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/smtp-tunnel-adduser`

**修改内容**:
- 更新 `--users-file` 参数默认值从 `/etc/smtp-tunnel/users.yaml` 到 `/opt/smtp-tunnel/config/users.yaml`
- 更新 `--config` 参数默认值从 `/etc/smtp-tunnel/config.yaml` 到 `/opt/smtp-tunnel/config/config.yaml`

**修改行数**: 第 487-488 行

**注意**: `find_project_root()` 函数保持不变，因为它返回脚本所在目录，用于查找客户端文件（客户端文件不在服务器上）。

---

### 4. smtp-tunnel-deluser
**文件路径**: `/home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/smtp-tunnel-deluser`

**修改内容**:
- 更新 `--users-file` 参数默认值从 `/etc/smtp-tunnel/users.yaml` 到 `/opt/smtp-tunnel/config/users.yaml`

**修改行数**: 第 32 行

---

### 5. smtp-tunnel-listusers
**文件路径**: `/home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/smtp-tunnel-listusers`

**修改内容**:
- 更新 `--users-file` 参数默认值从 `/etc/smtp-tunnel/users.yaml` 到 `/opt/smtp-tunnel/config/users.yaml`

**修改行数**: 第 25 行

---

### 6. smtp-tunnel.service
**文件路径**: `/home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/smtp-tunnel.service`

**修改内容**:
- 移除 `RequiresMountsFor=/etc/smtp-tunnel`
- 更新 `ExecStart` 中的配置文件路径从 `/etc/smtp-tunnel/config.yaml` 到 `/opt/smtp-tunnel/config/config.yaml`
- 移除 `ReadWritePaths=/etc/smtp-tunnel`
- 移除 `ReadWritePaths=/var/log/smtp-tunnel`
- 更新日志轮转配置注释从 `/etc/logrotate.d/smtp-tunnel` 到 `/opt/smtp-tunnel/logs/logrotate.conf`

**修改行数**: 第 7, 14, 45-47, 51 行

---

### 7. logrotate.conf
**文件路径**: `/home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/logrotate.conf`

**修改内容**:
- 更新安装位置注释从 `/etc/logrotate.d/smtp-tunnel` 到 `/opt/smtp-tunnel/logs/logrotate.conf`
- 更新日志文件路径从 `/var/log/smtp-tunnel/*.log` 到 `/opt/smtp-tunnel/logs/*.log`

**修改行数**: 第 3, 5 行

---

### 8. logger.py
**文件路径**: `/home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/logger.py`

**修改内容**:
- 更新 `LogConfig` 类的 `log_dir` 默认值从 `/var/log/smtp-tunnel` 到 `/opt/smtp-tunnel/logs`（第 60 行）
- 更新 `load_config_from_file()` 方法中的默认路径从 `/var/log/smtp-tunnel` 到 `/opt/smtp-tunnel/logs`（第 217 行）
- 更新 `_load_config_from_env()` 方法中的默认路径从 `/var/log/smtp-tunnel` 到 `/opt/smtp-tunnel/logs`（第 245 行）

**修改行数**: 第 60, 217, 245 行

---

### 9. install-client.sh
**文件路径**: `/home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/install-client.sh`

**修改内容**: 无修改

**说明**: 客户端安装脚本保持不变，因为客户端通常在用户机器上运行，不需要系统级安装。

---

### 10. install.sh
**文件路径**: `/home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/install.sh`

**修改内容**: 无修改

**说明**: 这是一个旧的安装脚本，已被 `install-server.sh` 替代，保持不变。

---

## 新的目录结构

```
/opt/smtp-tunnel/                    # 程序根目录
├── config/                         # 配置文件目录
│   ├── config.yaml                  # 服务器配置文件
│   ├── users.yaml                   # 用户配置文件
│   ├── ca.crt                      # CA 证书
│   ├── ca.key                      # CA 私钥
│   ├── server.crt                   # 服务器证书
│   └── server.key                  # 服务器私钥
├── venv/                           # Python 虚拟环境
│   ├── bin/
│   │   ├── python
│   │   ├── pip
│   │   └── activate
│   └── lib/
├── logs/                           # 日志目录
│   ├── install.log                  # 安装日志
│   ├── update.log                   # 更新日志
│   ├── smtp-tunnel.log             # 服务器日志
│   └── logrotate.conf             # 日志轮转配置
├── server.py                       # 服务器主程序
├── common.py                       # 通用模块
├── generate_certs.py               # 证书生成脚本
├── connection.py                   # 连接模块
├── config.py                       # 配置模块
├── logger.py                       # 日志模块
├── protocol/                       # 协议模块
│   ├── __init__.py
│   ├── core.py
│   ├── client.py
│   └── server.py
├── tunnel/                         # 隧道模块
│   ├── __init__.py
│   ├── crypto.py
│   ├── base.py
│   ├── client.py
│   ├── session.py
│   └── server.py
├── smtp-tunnel-adduser             # 用户管理脚本
├── smtp-tunnel-deluser             # 用户删除脚本
├── smtp-tunnel-listusers           # 用户列表脚本
├── smtp-tunnel-update              # 系统更新脚本
└── uninstall.sh                    # 卸载脚本

/usr/local/bin/                      # 可执行文件符号链接
├── smtp-tunnel-adduser -> /opt/smtp-tunnel/smtp-tunnel-adduser
├── smtp-tunnel-deluser -> /opt/smtp-tunnel/smtp-tunnel-deluser
├── smtp-tunnel-listusers -> /opt/smtp-tunnel/smtp-tunnel-listusers
└── smtp-tunnel-update -> /opt/smtp-tunnel/smtp-tunnel-update

/etc/systemd/system/                 # systemd 服务文件
└── smtp-tunnel.service            # 服务配置
```

## 路径对照表

| 用途 | 旧路径 | 新路径 |
|------|--------|--------|
| 程序安装目录 | `$SCRIPT_DIR/smtp-tunnel` 或 `/etc/smtp-tunnel` | `/opt/smtp-tunnel` |
| 配置文件目录 | `/etc/smtp-tunnel` | `/opt/smtp-tunnel/config` |
| 服务器配置 | `/etc/smtp-tunnel/config.yaml` | `/opt/smtp-tunnel/config/config.yaml` |
| 用户配置 | `/etc/smtp-tunnel/users.yaml` | `/opt/smtp-tunnel/config/users.yaml` |
| Python 虚拟环境 | `$SCRIPT_DIR/smtp-tunnel/venv` | `/opt/smtp-tunnel/venv` |
| 日志目录 | `/var/log/smtp-tunnel` | `/opt/smtp-tunnel/logs` |
| logrotate 配置 | `/etc/logrotate.d/smtp-tunnel` | `/opt/smtp-tunnel/logs/logrotate.conf` |

## 测试结果

所有更新后的脚本均通过语法检查：

✓ smtp-tunnel-update 语法正确
✓ smtp-tunnel-adduser 语法正确
✓ smtp-tunnel-deluser 语法正确
✓ smtp-tunnel-listusers 语法正确
✓ install-server.sh 语法正确
✓ logger.py 语法正确

## 使用方法

### 在远程服务器上安装

```bash
curl -sSL https://raw.githubusercontent.com/purpose168/smtp-tunnel-proxy/main/install-server.sh | sudo bash
```

### 更新现有安装

```bash
sudo smtp-tunnel-update
```

### 管理用户

```bash
# 添加用户
sudo smtp-tunnel-adduser username

# 删除用户
sudo smtp-tunnel-deluser username

# 列出用户
sudo smtp-tunnel-listusers
```

## 注意事项

1. **需要 root 权限**: 安装到 `/opt` 目录需要 root 权限
2. **符号链接**: 可执行文件仍然会创建符号链接到 `/usr/local/bin/`
3. **客户端脚本**: `install-client.sh` 保持不变，客户端在用户机器上运行
4. **配置文件**: 所有配置文件现在都在 `/opt/smtp-tunnel/config/` 目录下
5. **日志文件**: 所有日志文件现在都在 `/opt/smtp-tunnel/logs/` 目录下
6. **向后兼容**: 如果用户有旧的配置文件在 `/etc/smtp-tunnel`，需要手动迁移到新位置

## 迁移指南

如果用户有旧的安装（在 `/etc/smtp-tunnel` 或 `/var/log/smtp-tunnel`），可以按以下步骤迁移：

```bash
# 1. 停止服务
sudo systemctl stop smtp-tunnel

# 2. 备份旧配置
sudo cp -r /etc/smtp-tunnel /tmp/smtp-tunnel-backup

# 3. 迁移配置文件
sudo mkdir -p /opt/smtp-tunnel/config
sudo cp /etc/smtp-tunnel/config.yaml /opt/smtp-tunnel/config/
sudo cp /etc/smtp-tunnel/users.yaml /opt/smtp-tunnel/config/
sudo cp /etc/smtp-tunnel/ca.crt /opt/smtp-tunnel/config/
sudo cp /etc/smtp-tunnel/ca.key /opt/smtp-tunnel/config/
sudo cp /etc/smtp-tunnel/server.crt /opt/smtp-tunnel/config/
sudo cp /etc/smtp-tunnel/server.key /opt/smtp-tunnel/config/

# 4. 重新安装
curl -sSL https://raw.githubusercontent.com/purpose168/smtp-tunnel-proxy/main/install-server.sh | sudo bash

# 5. 启动服务
sudo systemctl start smtp-tunnel
```

## 版本信息

- **脚本版本**: 1.3.0
- **修改日期**: 2026-01-17
- **修改者**: AI Assistant

## 相关文件

- [install-server.sh](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/install-server.sh) - 服务器安装脚本
- [smtp-tunnel-update](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/smtp-tunnel-update) - 系统更新脚本
- [smtp-tunnel-adduser](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/smtp-tunnel-adduser) - 用户管理脚本
- [smtp-tunnel-deluser](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/smtp-tunnel-deluser) - 用户删除脚本
- [smtp-tunnel-listusers](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/smtp-tunnel-listusers) - 用户列表脚本
- [smtp-tunnel.service](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/smtp-tunnel.service) - systemd 服务文件
- [logrotate.conf](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/logrotate.conf) - 日志轮转配置
- [logger.py](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/logger.py) - 日志管理模块