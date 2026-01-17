# SMTP Tunnel Proxy - 服务端打包发布脚本使用文档

## 概述

`deploy-server.sh` 是一个完整的服务端打包发布脚本，提供了从代码构建到生产部署的全流程自动化支持。

## 功能特性

### 1. 代码构建与编译
- 验证代码完整性
- 检查 Python 语法
- 生成构建信息
- 创建版本信息文件

### 2. 依赖项安装
- 自动安装 Python 依赖
- 验证 Python 版本（要求 3.8+）
- 检查 pip 命令可用性

### 3. 环境配置处理
- 支持多环境切换（development/testing/production）
- 独立的环境配置文件
- 环境变量管理

### 4. 打包压缩
- 创建 tar.gz 压缩包
- 生成包信息文件
- 计算包大小和哈希值

### 5. 版本号管理
- 版本号设置和读取
- 自动版本号递增（major/minor/patch）
- Git 标签创建和推送

### 6. 服务器部署
- 远程 SSH 部署
- 自动服务管理
- 文件权限设置

### 7. 部署前备份
- 自动备份现有部署
- 配置文件备份
- 日志文件备份

### 8. 部署后健康检查
- 服务状态检查
- 端口监听检查
- 配置文件验证
- 日志目录验证

### 9. 错误处理与回滚机制
- 完善的错误处理
- 自动回滚到上一个版本
- 详细的日志记录

### 10. 多环境切换
- 开发环境（development）
- 测试环境（testing）
- 生产环境（production）

## 快速开始

### 1. 基本使用

```bash
# 赋予执行权限
chmod +x deploy-server.sh

# 查看帮助
./deploy-server.sh --help
```

### 2. 完整发布流程

```bash
# 执行完整发布流程（构建+测试+打包）
./deploy-server.sh --release
```

### 3. 部署到远程服务器

```bash
# 设置远程服务器
export REMOTE_SERVER="your-server-ip"

# 部署到远程服务器
```

## 详细使用说明

### 代码构建

```bash
# 构建代码
./deploy-server.sh --build
```

**功能**：
- 验证代码完整性
- 检查 Python 语法
- 复制文件到构建目录
- 生成构建信息

**输出**：
- 构建目录：`build/`
- 构建信息文件：`build/BUILD_INFO`

### 创建发布包

```bash
# 创建发布包
./deploy-server.sh --package
```

**功能**：
- 创建 tar.gz 压缩包
- 生成包信息文件
- 计算包大小和哈希值

**输出**：
- 发布目录：`release/`
- 包文件：`release/smtp-tunnel-proxy-{version}.tar.gz`
- 包信息：`release/smtp-tunnel-proxy-{version}.info`

### 完整发布流程

```bash
# 执行完整发布流程（构建+打包）
./deploy-server.sh --release
```

**功能**：
- 代码构建
- 创建发布包
- 显示发布信息

**流程**：
1. 验证代码完整性
2. 构建代码
3. 创建发布包
4. 显示发布信息

### 版本号管理

```bash
# 设置版本号
./deploy-server.sh --version 1.2.3

# 增加主版本号
./deploy-server.sh --increment major

# 增加次版本号
./deploy-server.sh --increment minor

# 增加补丁版本号
./deploy-server.sh --increment patch
```

**功能**：
- 版本号设置
- 自动版本号递增
- 版本号验证

**版本格式**：`major.minor.patch`（例如：1.2.3）

### Git 标签管理

```bash
# 创建 Git 标签
./deploy-server.sh --tag

# 推送 Git 标签
./deploy-server.sh --push-tag
```

**功能**：
- 创建 Git 标签
- 推送标签到远程仓库
- 版本号关联

**标签格式**：`v{version}`（例如：v1.2.3）

### 远程部署

```bash
# 设置远程服务器
export REMOTE_SERVER="192.168.1.100"
export REMOTE_USER="root"
export REMOTE_PORT="22"

# 部署到远程服务器
```

**功能**：
- 上传发布包
- 自动备份现有部署
- 部署新版本
- 重启服务
- 健康检查

**部署流程**：
1. 测试 SSH 连接
2. 备份远程部署
3. 上传发布包
4. 解压发布包
5. 停止服务
6. 备份现有文件
7. 复制新文件
8. 设置文件权限
9. 启动服务
10. 健康检查

### 部署后健康检查

```bash
# 执行健康检查
```

**功能**：
- 检查服务状态
- 检查端口监听
- 检查配置文件
- 检查日志目录

**检查项**：
- 服务状态：`systemctl is-active smtp-tunnel`
- 端口监听：`nc -z localhost 587`
- 配置文件：`/opt/smtp-tunnel/config/config.yaml`
- 日志目录：`/var/log/smtp-tunnel`

### 回滚部署

```bash
# 回滚到上一个版本
```

**功能**：
- 停止服务
- 查找最近的备份
- 恢复备份
- 启动服务
- 验证服务状态

**回滚流程**：
1. 停止服务
2. 查找最近的备份
3. 删除当前部署
4. 恢复备份
5. 启动服务
6. 验证服务状态

### 多环境切换

```bash
# 切换到开发环境
./deploy-server.sh --env development

# 切换到生产环境
./deploy-server.sh --env production
```

**功能**：
- 加载环境配置
- 切换环境变量
- 更新配置文件路径

**环境配置文件**：
- `.env.development` - 开发环境配置
- `.env.testing` - 测试环境配置
- `.env.production` - 生产环境配置

### 清理操作

```bash
# 清理构建目录
./deploy-server.sh --clean

# 清理旧发布
./deploy-server.sh --cleanup-releases
```

**功能**：
- 删除构建目录
- 清理旧发布包（保留 30 天）
- 释放磁盘空间

### 显示发布信息

```bash
# 显示发布信息
./deploy-server.sh --info
```

**功能**：
- 显示当前版本
- 显示发布包信息
- 显示包大小和哈希值

## 环境变量配置

### 远程服务器配置

```bash
# 远程服务器地址（必需）
export REMOTE_SERVER="your-server-ip"

# 远程用户名（默认：root）
export REMOTE_USER="root"

# 远程端口（默认：22）
export REMOTE_PORT="22"

# 远程部署目录（默认：/opt/smtp-tunnel）
export REMOTE_DEPLOY_DIR="/opt/smtp-tunnel"
```

### 环境配置文件

创建环境配置文件：

```bash
# 开发环境配置
cat > .env.development << EOF
REMOTE_SERVER="dev-server.local"
REMOTE_USER="root"
REMOTE_DEPLOY_DIR="/opt/smtp-tunnel-dev"
EOF

# 生产环境配置
cat > .env.production << EOF
REMOTE_SERVER="prod-server.example.com"
REMOTE_USER="root"
REMOTE_DEPLOY_DIR="/opt/smtp-tunnel"
EOF
```

## 目录结构

```
smtp-tunnel-proxy/
├── deploy-server.sh              # 发布脚本
├── build/                 # 构建目录（自动生成）
│   ├── BUILD_INFO        # 构建信息
│   ├── VERSION           # 版本信息
│   ├── *.py              # Python 文件
│   ├── tunnel/           # 隧道模块
│   ├── protocol/          # 协议模块
│   └── config.yaml       # 配置文件
├── release/               # 发布目录（自动生成）
│   ├── smtp-tunnel-proxy-{version}.tar.gz
│   └── smtp-tunnel-proxy-{version}.info
├── logs/                  # 日志目录（自动生成）
│   └── deploy.log       # 部署日志
└── .env.{environment}     # 环境配置文件
```

## 工作流程

### 开发流程

```bash
# 1. 开发新功能
# ... 编写代码 ...

# 2. 运行测试
./deploy-server.sh --test

# 3. 增加版本号
./deploy-server.sh --increment patch

# 4. 创建 Git 标签
./deploy-server.sh --tag

# 5. 推送标签
./deploy-server.sh --push-tag
```

### 测试流程

```bash
# 1. 切换到测试环境
./deploy-server.sh --env testing

# 2. 构建代码
./deploy-server.sh --build

# 3. 运行测试
./deploy-server.sh --test

# 4. 创建发布包
./deploy-server.sh --package

# 5. 部署到测试服务器
```

### 生产流程

```bash
# 1. 切换到生产环境
./deploy-server.sh --env production

# 2. 完整发布流程
./deploy-server.sh --release

# 3. 部署到生产服务器

# 4. 验证部署
```

### 回滚流程

```bash
# 1. 检查部署状态

# 2. 如果部署失败，执行回滚

# 3. 验证回滚
```

## 错误处理

### 常见错误

#### 1. 代码验证失败

```
[ERROR] 2024-01-17 10:00:00 - 必需文件不存在: server.py
```

**解决方法**：
- 检查工作区目录
- 确保所有必需文件存在

#### 2. Python 版本不满足

```
[ERROR] 2024-01-17 10:00:00 - Python 3.8+ 是必需的，当前版本: 3.7.0
```

**解决方法**：
- 升级 Python 到 3.8+
- 更新 requirements.txt

#### 3. SSH 连接失败

```
[ERROR] 2024-01-17 10:00:00 - SSH 连接失败
```

**解决方法**：
- 检查网络连接
- 验证 SSH 密钥
- 确认服务器地址正确

#### 4. 部署失败

```
[ERROR] 2024-01-17 10:00:00 - 远程部署失败
```

**解决方法**：
- 检查日志文件：`logs/deploy.log`
- 验证服务器状态

#### 5. 健康检查失败

```
[ERROR] 2024-01-17 10:00:00 - 服务状态: inactive
```

**解决方法**：
- 检查服务日志：`journalctl -u smtp-tunnel -n 50`
- 检查配置文件
- 重启服务：`systemctl restart smtp-tunnel`

## 最佳实践

### 1. 版本管理

- 使用语义化版本号（major.minor.patch）
- 每次发布前更新 CHANGELOG
- 创建 Git 标签关联版本号
- 定期清理旧发布包

### 2. 测试

- 每次发布前运行完整测试
- 在测试环境验证部署
- 使用自动化测试套件
- 记录测试结果

### 3. 部署

- 使用自动化部署脚本
- 部署前自动备份
- 部署后自动健康检查
- 保留部署日志
- 支持快速回滚

### 4. 安全

- 使用 SSH 密钥认证
- 限制远程用户权限
- 加密敏感配置
- 定期更新依赖

### 5. 监控

- 监控服务状态
- 监控日志文件
- 设置告警机制
- 定期健康检查

## 故障排除

### 问题：脚本无法执行

```bash
# 检查执行权限
ls -l deploy-server.sh

# 赋予执行权限
chmod +x deploy-server.sh

# 检查 Bash 版本
bash --version
```

### 问题：构建失败

```bash
# 检查构建目录
ls -la build/

# 清理构建目录
./deploy-server.sh --clean

# 重新构建
./deploy-server.sh --build
```

### 问题：部署失败

```bash
# 检查远程服务器连接
ssh root@your-server "echo 'Connection successful'"

# 检查远程目录
ssh root@your-server "ls -la /opt/smtp-tunnel"

# 检查服务状态
ssh root@your-server "systemctl status smtp-tunnel"

# 执行回滚
```

### 问题：健康检查失败

```bash
# 手动检查服务状态
ssh root@your-server "systemctl is-active smtp-tunnel"

# 手动检查端口监听
ssh root@your-server "nc -z localhost 587"

# 手动检查日志
ssh root@your-server "journalctl -u smtp-tunnel -n 50"

# 重启服务
ssh root@your-server "systemctl restart smtp-tunnel"
```

## 集成示例

### 与 CI/CD 集成

```yaml
# .github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    tags:
      - 'v*'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v2
      
      - name: Deploy to server
        env:
          REMOTE_SERVER: ${{ secrets.SERVER_IP }}
          REMOTE_USER: ${{ secrets.SERVER_USER }}
        run: |
          chmod +x deploy-server.sh
```

### 与 Docker 集成

```bash
# 构建 Docker 镜像
docker build -t smtp-tunnel-proxy:latest .

# 推送到镜像仓库
docker push smtp-tunnel-proxy:latest

# 部署到服务器
ssh root@your-server "docker pull smtp-tunnel-proxy:latest && docker-compose up -d"
```

## 总结

`deploy-server.sh` 脚本提供了完整的服务端打包发布流程，包括：

✅ 代码构建与编译
✅ 依赖项安装
✅ 环境配置处理
✅ 打包压缩
✅ 版本号管理
✅ 服务器部署
✅ 部署前备份
✅ 部署后健康检查
✅ 错误处理与回滚机制
✅ 多环境切换

该脚本符合项目现有的技术栈和架构规范，可以安全、高效地完成从开发到生产的完整流程。
