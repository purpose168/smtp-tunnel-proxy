# GitHub Release 创建指南

## 概述

`deploy-server.sh` 脚本支持两种方式创建 GitHub Release：

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
./deploy-server.sh --release

# 创建 GitHub Release
./deploy-server.sh --create-release
```

## 方式 2：使用 GitHub API

### 获取 GitHub Token

1. 访问 https://github.com/settings/tokens
2. 点击 "Generate new token (classic)"
3. 选择权限：`repo` (完整仓库访问权限)
4. 生成并复制 token

### 设置 GITHUB_TOKEN

**方式 1：在脚本中设置**
编辑 `deploy-server.sh`，找到以下行：
```bash
# GitHub API Token（用于创建 release，可选）
GITHUB_TOKEN=""
```

将 `GITHUB_TOKEN` 设置为您的 token：
```bash
GITHUB_TOKEN="your_github_token_here"
```

**方式 2：通过环境变量传入**
```bash
export GITHUB_TOKEN="your_github_token_here"
./deploy-server.sh --create-release
```

### 创建 Release

```bash
# 创建发布包
./deploy-server.sh --release

# 创建 GitHub Release
./deploy-server.sh --create-release
```

## 自动获取 GitHub 仓库信息

脚本会自动从 git remote URL 中获取 GitHub 仓库信息，无需手动配置。

### 支持的 URL 格式

- `https://github.com/owner/repo.git`
- `https://github.com/owner/repo`
- `git@github.com:owner/repo.git`
- `git@github.com:owner/repo`

### 手动覆盖

如果需要手动设置，可以在脚本中设置：
```bash
GITHUB_REPO_OWNER="your-username"
GITHUB_REPO_NAME="smtp-tunnel-proxy"
```

## 完整发布流程

```bash
# 1. 增加版本号
./deploy-server.sh --increment minor

# 2. 创建 Git 标签
./deploy-server.sh --tag

# 3. 推送 Git 标签
./deploy-server.sh --push-tag

# 4. 创建发布包
./deploy-server.sh --package

# 5. 创建 GitHub Release
./deploy-server.sh --create-release
```

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