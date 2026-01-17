# GitHub Release 创建指南

## 概述

`smtp-tunnel-release.sh` 脚本支持两种方式创建 GitHub Release：

1. **使用 GitHub CLI (gh)** - 推荐，更简单
2. **使用 GitHub API** - 需要 GITHUB_TOKEN

## 方式 1：使用 GitHub CLI (gh)

### 安装 GitHub CLI

**macOS**:
```bash
brew install gh
```

**Linux (Ubuntu/Debian)**:
```bash
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update
sudo apt install gh
```

**登录 GitHub**:
```bash
gh auth login
```

### 创建 Release

```bash
# 创建发布包
./smtp-tunnel-release.sh --release

# 创建 GitHub Release
./smtp-tunnel-release.sh --create-release
```

## 方式 2：使用 GitHub API

### 获取 GitHub Token

1. 访问 https://github.com/settings/tokens
2. 点击 "Generate new token (classic)"
3. 选择权限：`repo` (完整仓库访问权限)
4. 生成并复制 token

### 设置 GITHUB_TOKEN

**方式 1：通过环境变量传入**
```bash
export GITHUB_TOKEN="your_github_token_here"
./smtp-tunnel-release.sh --create-release
```

**方式 2：在脚本中设置**
编辑 `smtp-tunnel-release.sh`，找到以下行：
```bash
# GitHub API Token（用于创建 release，可选）
GITHUB_TOKEN=""
```

将 `GITHUB_TOKEN` 设置为您的 token：
```bash
GITHUB_TOKEN="your_github_token_here"
```

### 创建 Release

```bash
# 创建发布包
./smtp-tunnel-release.sh --release

# 创建 GitHub Release
./smtp-tunnel-release.sh --create-release
```

## 自动获取 GitHub 仓库信息

脚本会自动从 git remote URL 中获取 GitHub 仓库信息，无需手动配置。

### 支持的 URL 格式

- `https://github.com/owner/repo.git`
- `https://github.com/owner/repo`
- `git@github.com:owner/repo.git`
- `git@github.com:owner/repo`

### 手动覆盖

如果需要手动设置，可以通过环境变量设置：
```bash
export GITHUB_REPO_OWNER="your-username"
export GITHUB_REPO_NAME="smtp-tunnel-proxy"
./smtp-tunnel-release.sh --create-release
```

## 完整发布流程

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

## 一键发布

```bash
# 完整发布流程
./smtp-tunnel-release.sh --release

# 创建 GitHub Release
./smtp-tunnel-release.sh --create-release
```

## 环境变量配置

### GitHub 配置

```bash
# GitHub Token（用于 GitHub API 方式）
export GITHUB_TOKEN="your_github_token_here"

# GitHub 仓库信息（可选，脚本会自动从 git remote 获取）
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
2. 创建测试发布包
3. 创建测试 Release
4. 验证功能
5. 修复问题

### 生产流程

1. 切换到生产环境
2. 增加版本号
3. 创建 Git 标签
4. 创建发布包
5. 创建 GitHub Release
6. 验证 Release

## 错误处理

### 常见错误

1. **GitHub CLI 未安装**
   - 错误信息：`gh: command not found`
   - 解决方法：安装 GitHub CLI

2. **GitHub CLI 未登录**
   - 错误信息：`You are not logged in`
   - 解决方法：运行 `gh auth login`

3. **GitHub Token 无效**
   - 错误信息：`Bad credentials`
   - 解决方法：检查 Token 是否正确，重新生成 Token

4. **发布包不存在**
   - 错误信息：`发布包不存在: release/smtp-tunnel-proxy-{version}.tar.gz`
   - 解决方法：先运行 `--package` 或 `--release` 创建发布包

5. **Git 标签已存在**
   - 错误信息：`tag 'v{version}' already exists`
   - 解决方法：删除现有标签或增加版本号

6. **Release 已存在**
   - 错误信息：`Release already exists`
   - 解决方法：删除现有 Release 或使用新的标签

### 回滚机制

1. 删除 GitHub Release
2. 删除 Git 标签
3. 重新创建 Release

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

### Release 管理

1. **Release Notes**
   - 自动从 CHANGELOG 读取
   - 确保 CHANGELOG 更新到最新版本
   - 包含重要的变更和修复

2. **发布包**
   - 确保发布包完整
   - 验证包大小和哈希值
   - 测试发布包的完整性

3. **发布验证**
   - 验证 Release 创建成功
   - 验证发布包上传成功
   - 验证 Release Notes 正确

### 安全实践

1. **Token 管理**
   - 不要将 GITHUB_TOKEN 提交到代码仓库
   - 使用环境变量存储 Token
   - 定期更新 Token

2. **权限控制**
   - 使用最小权限原则
   - 只授予必要的权限
   - 定期审计权限设置

3. **访问控制**
   - 限制 Release 创建权限
   - 使用受保护的分支
   - 启用分支保护规则

## 注意事项

1. **权限要求**：
   - GitHub Token 需要 `repo` 权限
   - GitHub CLI 需要登录并授权

2. **依赖工具**：
   - GitHub CLI 方式：需要 `gh` 命令
   - GitHub API 方式：需要 `curl` 和 `jq` 命令

3. **Release 限制**：
   - 同一个 tag 只能创建一次 release
   - 如需更新，需要先删除现有 release

4. **安全性**：
   - 不要将 GITHUB_TOKEN 提交到代码仓库
   - 使用环境变量传入 token 更安全
   - 定期更新 token

5. **网络要求**：
   - 能够访问 GitHub
   - 稳定的网络连接

6. **磁盘空间**：
   - 确保有足够的磁盘空间
   - 定期清理旧发布包
   - 清理构建目录

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
name: Create Release

on:
  push:
    tags:
      - 'v*'
    branches:
      - main

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v2
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install GitHub CLI
        run: |
          curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
          echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
          sudo apt update
          sudo apt install gh
      
      - name: Login to GitHub
        run: |
          echo "${{ secrets.GITHUB_TOKEN }}" | gh auth login --with-token
      
      - name: Create release package
        run: |
          chmod +x smtp-tunnel-release.sh
          ./smtp-tunnel-release.sh --release
      
      - name: Create GitHub Release
        run: |
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
  bash -c "cd /app && ./smtp-tunnel-release.sh --release && ./smtp-tunnel-release.sh --create-release"
```

## 故障排除

### 问题：GitHub CLI 未安装

**检查项**：
- 检查 GitHub CLI 是否安装：`gh --version`

**解决方法**：
- 安装 GitHub CLI
- 参考 [安装指南](#方式-1使用-github-cli-gh)

### 问题：GitHub CLI 未登录

**检查项**：
- 检查 GitHub CLI 登录状态：`gh auth status`

**解决方法**：
- 登录 GitHub：`gh auth login`
- 参考 [登录指南](#方式-1使用-github-cli-gh)

### 问题：GitHub Token 无效

**检查项**：
- 检查 Token 是否正确
- 检查 Token 是否过期
- 检查 Token 权限

**解决方法**：
- 重新生成 Token
- 确保 Token 有 `repo` 权限
- 更新环境变量

### 问题：发布包不存在

**检查项**：
- 检查发布包是否存在：`ls -l release/`
- 检查发布包名称是否正确

**解决方法**：
- 运行 `--package` 或 `--release` 创建发布包
- 检查版本号是否正确

### 问题：Git 标签已存在

**检查项**：
- 检查 Git 标签是否存在：`git tag -l`

**解决方法**：
- 删除现有标签：`git tag -d v{version}`
- 增加版本号：`./smtp-tunnel-release.sh --increment patch`

### 问题：Release 已存在

**检查项**：
- 检查 Release 是否存在：访问 GitHub Release 页面

**解决方法**：
- 删除现有 Release（通过 GitHub 网页界面）
- 使用新的标签创建 Release

## 总结

`smtp-tunnel-release.sh` 脚本提供了完整的 GitHub Release 创建流程，包括：

1. ✅ **支持两种方式** - GitHub CLI 和 GitHub API
2. ✅ **自动获取仓库信息** - 从 git remote 自动解析
3. ✅ **自动读取 CHANGELOG** - 作为 release notes
4. ✅ **版本号管理** - 自动版本号递增和 Git 标签管理
5. ✅ **完整的发布流程** - 从构建到 GitHub Release 一键完成
6. ✅ **错误处理** - 完善的错误处理和回滚机制
7. ✅ **CI/CD 集成** - 支持与 GitHub Actions 集成
8. ✅ **Docker 集成** - 支持与 Docker 集成

该脚本符合项目现有的技术栈和架构规范，可以安全、高效地完成从开发到 GitHub Release 的完整流程。

---

**版本**: 1.0.0  
**最后更新**: 2026-01-17  
**维护者**: SMTP Tunnel Proxy Team