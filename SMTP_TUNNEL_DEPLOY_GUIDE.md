# SMTP Tunnel Proxy - 服务端部署指南

## 概述

`smtp-tunnel-release.sh` 是一个完整的服务端打包发布脚本，提供了从代码构建到生产部署的全流程自动化支持。

## 功能特性

### 1. 代码构建与编译
- 验证代码完整性
- 检查 Python 语法
- 生成构建信息
- 创建版本信息文件

### 2. 打包压缩
- 创建 tar.gz 压缩包
- 生成包信息文件
- 计算包大小和哈希值

### 3. 版本号管理
- 版本号设置和读取
- 自动版本号递增（major/minor/patch）
- Git 标签创建和推送

### 4. GitHub Release
- 创建 GitHub Release 并上传发布包
- 支持 GitHub CLI (gh) 和 GitHub API 两种方式
- 自动从 git remote 获取仓库信息
- 自动读取 CHANGELOG 作为 release notes

### 5. 服务器部署
- 远程 SSH 部署
- 自动服务管理
- 文件权限设置

### 6. 部署前备份
- 自动备份现有部署
- 配置文件备份
- 日志文件备份

### 7. 部署后健康检查
- 服务状态检查
- 端口监听检查
- 配置文件验证
- 日志目录验证

## 快速开始

### 基本使用

```bash
# 赋予执行权限
chmod +x smtp-tunnel-release.sh

# 查看帮助
./smtp-tunnel-release.sh --help
```

## 详细使用说明

### 代码构建

```bash
# 构建代码
./smtp-tunnel-release.sh --build

**功能**：
- 验证代码完整性
- 检查 Python 语法
- 复制文件到构建目录
- 生成构建信息

**输出**：
- 构建目录：`build/`
- 构建信息文件：`build/BUILD_INFO`
```

### 创建发布包

```bash
# 创建发布包
./smtp-tunnel-release.sh --package

**功能**：
- 创建 tar.gz 压缩包
- 生成包信息文件
- 计算包大小和哈希值

**输出**：
- 发布目录：`release/`
- 发布包：`release/smtp-tunnel-proxy-{version}.tar.gz`
- 包信息：`release/smtp-tunnel-proxy-{version}.info`
```

### 完整发布流程

```bash
# 执行完整发布流程（构建+打包）
./smtp-tunnel-release.sh --release

**功能**：
- 代码构建
- 创建发布包
- 显示发布信息

**输出**：
- 构建目录：`build/`
- 发布目录：`release/`
- 发布包：`release/smtp-tunnel-proxy-{version}.tar.gz`
- 包信息：`release/smtp-tunnel-proxy-{version}.info`
```

### 版本号管理

```bash
# 设置版本号
./smtp-tunnel-release.sh --version 1.2.3

# 增加主版本号
./smtp-tunnel-release.sh --increment major

# 增加次版本号
./smtp-tunnel-release.sh --increment minor

# 增加补丁版本号
./smtp-tunnel-release.sh --increment patch

**版本格式**：`major.minor.patch`（例如：1.2.3）
```

### Git 标签管理

```bash
# 创建 Git 标签
./smtp-tunnel-release.sh --tag

# 推送 Git 标签
./smtp-tunnel-release.sh --push-tag

**标签格式**：`v{version}`（例如：v1.2.3）
```

### GitHub Release 创建

```bash
# 创建 GitHub Release
./smtp-tunnel-release.sh --create-release

**功能**：
- 从 git remote 自动获取 GitHub 仓库信息
- 创建 GitHub Release
- 上传发布包
- 自动读取 CHANGELOG 作为 release notes

**支持方式**：
1. GitHub CLI (gh) - 推荐，更简单
2. GitHub API - 需要 GITHUB_TOKEN

**输出**：
- Release URL：`https://github.com/{owner}/{repo}/releases/tag/v{version}`
```

### 清理操作

```bash
# 清理构建目录
./smtp-tunnel-release.sh --clean

# 清理旧发布包（保留最新的 5 个）
./smtp-tunnel-release.sh --cleanup-releases

**功能**：
- 删除构建目录
- 删除旧的发布包
- 释放磁盘空间
```

### 显示发布信息

```bash
# 显示发布信息
./smtp-tunnel-release.sh --info

**功能**：
- 显示当前版本号
- 显示发布包信息
- 显示包大小和哈希值
```

## 环境变量配置

### 远程服务器配置

```bash
# 设置远程服务器
export REMOTE_SERVER="192.168.1.100"
export REMOTE_USER="root"
export REMOTE_PORT="22"
export REMOTE_DEPLOY_DIR="/opt/smtp-tunnel"
```

### GitHub 配置

```bash
# 方式 1：使用 GitHub CLI（推荐）
# 无需额外配置，只需登录
gh auth login

# 方式 2：使用 GitHub API
export GITHUB_TOKEN="your_github_token_here"

# 手动设置 GitHub 仓库信息（可选）
export GITHUB_REPO_OWNER="your-username"
export GITHUB_REPO_NAME="smtp-tunnel-proxy"
```

## 目录结构

```
smtp-tunnel-proxy/
├── smtp-tunnel-release.sh    # 发布脚本
├── build/                       # 构建目录（自动生成）
├── release/                     # 发布目录（自动生成）
│   ├── smtp-tunnel-proxy-{version}.tar.gz
│   └── smtp-tunnel-proxy-{version}.info
├── logs/                        # 日志目录（自动生成）
└── deploy.log                  # 部署日志
```

## 工作流程

### 开发流程

1. 开发新功能
2. 本地测试
3. 增加版本号
4. 创建 Git 标签
5. 创建发布包
6. 创建 GitHub Release

### 测试流程

1. 切换到测试环境
2. 部署到测试服务器
3. 运行健康检查
4. 验证功能
5. 修复问题

### 生产流程

1. 切换到生产环境
2. 备份现有部署
3. 部署新版本
4. 运行健康检查
5. 验证功能

### 回滚流程

1. 停止服务
2. 查找最近的备份
3. 恢复备份
4. 重启服务
5. 验证功能

## 错误处理

### 常见错误

1. **代码验证失败**
   - 检查必需文件是否存在
   - 检查 Python 语法错误
   - 解决：确保所有必需文件存在，修复语法错误

2. **构建失败**
   - 检查构建目录权限
   - 解决：确保有足够的磁盘空间和权限

3. **发布包创建失败**
   - 检查磁盘空间
   - 检查文件权限
   - 解决：清理磁盘空间，修复权限问题

4. **GitHub Release 创建失败**
   - 检查 GitHub CLI 是否安装
   - 检查 GitHub Token 是否有效
   - 检查网络连接
   - 解决：安装 GitHub CLI，更新 Token，检查网络连接

5. **部署失败**
   - 检查 SSH 连接
   - 检查服务器状态
   - 解决：检查网络连接，检查服务器状态

### 回滚机制

脚本支持自动回滚到上一个版本：

1. 保留最近的备份
2. 自动恢复备份
3. 验证回滚结果

## 最佳实践

### 版本管理

1. **使用语义化版本号**
   - 遵循 `major.minor.patch` 格式
   - 主版本：不兼容的 API 变更
   - 次版本：向后兼容的功能添加
   - 补丁版本：向后兼容的错误修复

2. **版本号递增**
   - 每次发布前增加版本号
   - 根据变更类型选择递增类型

3. **Git 标签管理**
   - 每个版本创建对应的 Git 标签
   - 推送标签到远程仓库
   - 标签格式：`v{version}`

### 部署策略

1. **部署前备份**
   - 每次部署前备份现有部署
   - 保留最近 5 个备份
   - 备份包含配置文件和日志文件

2. **分阶段部署**
   - 先部署到测试环境
   - 验证功能
   - 再部署到生产环境

3. **部署后验证**
   - 部署后立即运行健康检查
   - 验证所有功能正常
   - 检查服务状态和日志

### 安全实践

1. **使用 SSH 密钥认证**
   - 不要使用密码认证
   - 使用 SSH 密钥对进行认证
   - 限制 SSH 用户权限

2. **保护敏感信息**
   - 不要将密码和密钥提交到代码仓库
   - 使用环境变量存储敏感信息
   - 定期更新密钥

3. **最小权限原则**
   - 只授予必要的权限
   - 使用 sudo 时谨慎操作
   - 定期审计权限设置

### 监控和日志

1. **日志记录**
   - 所有操作都记录到日志文件
   - 日志文件位置：`logs/deploy.log`
   - 日志包含时间戳和详细信息

2. **健康检查**
   - 部署后自动运行健康检查
   - 检查服务状态
   - 检查端口监听
   - 验证配置文件

3. **监控指标**
   - 监控服务状态
   - 监控日志错误
   - 监控性能指标

## 完整示例

### 完整发布流程

```bash
# 1. 增加版本号
./smtp-tunnel-release.sh --increment minor

# 2. 创建 Git 标签
./smtp-tunnel-release.sh --tag

# 3. 推送 Git 标签
./smtp-tunnel-release.sh --push-tag

# 4. 创建发布包
./smtp-tunnel-release.sh --package

# 5. 创建 GitHub Release
./smtp-tunnel-release.sh --create-release
```

### 一键发布

```bash
# 完整发布流程
./smtp-tunnel-release.sh --release

# 创建 GitHub Release
./smtp-tunnel-release.sh --create-release
```

### 与 CI/CD 集成

```yaml
name: Deploy to Production

on:
  push:
    tags:
      - 'v*'
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v2
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Run deployment script
        run: |
          chmod +x smtp-tunnel-release.sh
          ./smtp-tunnel-release.sh --release
          ./smtp-tunnel-release.sh --create-release
```

### 与 Docker 集成

```bash
# 构建 Docker 镜像
docker build -t smtp-tunnel-proxy:latest .

# 推送到镜像仓库
docker push smtp-tunnel-proxy:latest

# 部署到服务器
docker run --rm \
  -v $(pwd)/smtp-tunnel-release.sh:/app/smtp-tunnel-release.sh \
  smtp-tunnel-proxy:latest \
  bash -c "cd /app && ./smtp-tunnel-release.sh --release"
```

## 注意事项

1. **权限要求**
   - 脚本需要执行权限：`chmod +x smtp-tunnel-release.sh`
   - 部署需要 SSH 访问权限
   - GitHub Release 需要 `repo` 权限

2. **依赖工具**
   - Bash 4.0+
   - Python 3.8+
   - Git
   - GitHub CLI (gh) 或 curl + jq
   - SSH 客户端

3. **网络要求**
   - 能够访问 GitHub
   - 能够访问远程服务器
   - 稳定的网络连接

4. **磁盘空间**
   - 确保有足够的磁盘空间
   - 定期清理旧发布包
   - 清理构建目录

5. **安全性**
   - 不要将敏感信息提交到代码仓库
   - 使用环境变量存储敏感信息
   - 定期更新密钥和密码
   - 使用 SSH 密钥认证

6. **备份策略**
   - 每次部署前备份
   - 保留最近 5 个备份
   - 定期清理旧备份
   - 验证备份完整性

7. **日志管理**
   - 定期检查日志文件大小
   - 清理旧日志文件
   - 保留重要日志信息

## 故障排除

### 问题：脚本无法执行

**检查项**：
- 检查执行权限：`ls -l smtp-tunnel-release.sh`
- 检查 Bash 版本：`bash --version`
- 检查语法错误：`bash -n smtp-tunnel-release.sh`

**解决方法**：
- 赋予执行权限：`chmod +x smtp-tunnel-release.sh`
- 更新 Bash 版本
- 修复语法错误

### 问题：GitHub Release 创建失败

**检查项**：
- 检查 GitHub CLI 是否安装：`gh --version`
- 检查 GitHub CLI 登录状态：`gh auth status`
- 检查网络连接：`ping github.com`

**解决方法**：
- 安装 GitHub CLI
- 登录 GitHub：`gh auth login`
- 检查网络连接
- 验证 GitHub Token

### 问题：部署失败

**检查项**：
- 检查 SSH 连接：`ssh user@host`
- 检查服务器状态：`ssh user@host "systemctl status smtp-tunnel"`
- 检查服务日志：`ssh user@host "journalctl -u smtp-tunnel -n 50"`

**解决方法**：
- 检查网络连接
- 检查服务器状态
- 检查服务日志
- 修复配置问题

## 总结

`smtp-tunnel-release.sh` 脚本提供了完整的服务端打包发布流程，包括：

1. ✅ **代码构建与编译** - 验证代码完整性，生成构建信息
2. ✅ **打包压缩** - 创建发布包，计算包大小和哈希值
3. ✅ **版本号管理** - 自动版本管理和标记
4. ✅ **GitHub Release** - 创建 GitHub Release 并上传发布包
5. ✅ **服务器部署** - 远程 SSH 部署，自动服务管理
6. ✅ **部署前备份** - 自动备份现有部署
7. ✅ **部署后健康检查** - 服务状态检查，端口监听检查
8. ✅ **错误处理与回滚** - 完善的错误处理和自动回滚机制

该脚本符合项目现有的技术栈和架构规范，可以安全、高效地完成从开发到生产的完整流程。

---

**版本**: 1.0.0  
**最后更新**: 2026-01-17  
**维护者**: SMTP Tunnel Proxy Team