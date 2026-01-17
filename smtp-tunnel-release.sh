#!/bin/bash
#
# SMTP Tunnel Proxy - 服务端打包发布脚本
# ============================================================================
# 功能说明：
# 1. 代码构建与编译 - 验证代码完整性，生成版本信息
# 2. 打包压缩 - 创建发布包
# 3. 版本号管理 - 自动版本管理和标记
# 4. GitHub Release - 创建 GitHub Release 并上传发布包
# ============================================================================
set -euo pipefail
# ============================================================================
# 配置区域 - 可根据需要修改
# ============================================================================
# 工作区路径（自动检测）
WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 版本配置
VERSION_FILE="${WORKSPACE_DIR}/.version"
CHANGELOG_FILE="${WORKSPACE_DIR}/CHANGELOG.md"
RELEASE_DIR="${WORKSPACE_DIR}/release"
BUILD_DIR="${WORKSPACE_DIR}/build"
BACKUP_DIR="${WORKSPACE_DIR}/deploy_backup"
# 日志配置
LOG_DIR="${WORKSPACE_DIR}/logs"
LOG_FILE="${LOG_DIR}/deploy.log"
# 打包配置
PACKAGE_NAME="smtp-tunnel-proxy"
PACKAGE_FORMAT="tar.gz"
# Git 配置
GIT_BRANCH="main"
GIT_TAG_PREFIX="v"
# GitHub 配置（从 git remote 自动获取）
GITHUB_REPO_OWNER=""
GITHUB_REPO_NAME=""
# ============================================================================
# 颜色定义
# ============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
# ============================================================================
# 函数定义
# ============================================================================
# 打印信息消息
log_info() {
    local message="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${BLUE}[INFO]${NC} ${timestamp} - ${message}" | tee -a "${LOG_FILE}"
}
# 打印成功消息
log_success() {
    local message="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${GREEN}[SUCCESS]${NC} ${timestamp} - ${message}" | tee -a "${LOG_FILE}"
}
# 打印警告消息
log_warning() {
    local message="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${YELLOW}[WARNING]${NC} ${timestamp} - ${message}" | tee -a "${LOG_FILE}"
}
# 打印错误消息
log_error() {
    local message="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${RED}[ERROR]${NC} ${timestamp} - ${message}" | tee -a "${LOG_FILE}"
}
# 打印步骤消息
log_step() {
    local message="$1"
    echo -e "${CYAN}[STEP]${NC} ${message}"
}
# 检查命令是否存在
check_command() {
    local cmd="$1"
    if ! command -v "${cmd}" &> /dev/null; then
        log_error "命令 '${cmd}' 未找到，请先安装"
        return 1
    fi
    return 0
}
# 检查文件是否存在
check_file() {
    local file="$1"
    if [ ! -f "${file}" ]; then
        log_error "文件不存在: ${file}"
        return 1
    fi
    return 0
}
# 检查目录是否存在
check_dir() {
    local dir="$1"
    if [ ! -d "${dir}" ]; then
        log_error "目录不存在: ${dir}"
        return 1
    fi
    return 0
}
# 创建必要的目录
create_directories() {
    #log_step "创建必要的目录..."
    
    mkdir -p "${RELEASE_DIR}"
    mkdir -p "${BUILD_DIR}"
    mkdir -p "${BACKUP_DIR}"
    mkdir -p "${LOG_DIR}"
    mkdir -p "$(dirname "${LOG_FILE}")"
    
    #log_info "目录创建完成"
}
# 清理构建目录
clean_build() {
    log_step "清理构建目录..."
    
    if [ -d "${BUILD_DIR}" ]; then
        rm -rf "${BUILD_DIR}"
        log_info "构建目录已清理: ${BUILD_DIR}"
    fi
    
    mkdir -p "${BUILD_DIR}"
}
# 清理旧发布包
cleanup_old_releases() {
    log_step "清理旧发布包..."
    
    # 检查发布目录是否存在
    if [ ! -d "${RELEASE_DIR}" ]; then
        log_info "发布目录不存在: ${RELEASE_DIR}"
        return 0
    fi
    
    # 获取所有发布包
    local packages=($(ls -t "${RELEASE_DIR}"/*.${PACKAGE_FORMAT} 2>/dev/null || true))
    
    # 如果没有发布包，直接返回
    if [ ${#packages[@]} -eq 0 ]; then
        log_info "没有找到发布包"
        return 0
    fi
    
    log_info "找到 ${#packages[@]} 个发布包"
    
    # 保留最新的 5 个发布包
    local keep_count=5
    if [ ${#packages[@]} -le ${keep_count} ]; then
        log_info "发布包数量未超过保留数量 (${keep_count})"
        return 0
    fi
    
    # 计算需要删除的包数量
    local delete_count=$((${#packages[@]} - keep_count))
    log_info "将删除 ${delete_count} 个旧发布包"
    
    # 删除旧的发布包
    for ((i=${keep_count}; i<${#packages[@]}; i++)); do
        local package="${packages[$i]}"
        log_info "删除: $(basename "${package}")"
        rm -f "${package}"
    done
    
    log_success "已清理 ${delete_count} 个旧发布包，保留最新的 ${keep_count} 个"
    return 0
}
# 获取当前版本
get_version() {
    if [ -f "${VERSION_FILE}" ]; then
        cat "${VERSION_FILE}"
    else
        echo "1.0.0"
    fi
}
# 设置版本号
set_version() {
    local version="$1"
    echo "${version}" > "${VERSION_FILE}"
    log_info "版本号已设置为: ${version}"
}
# 增加版本号
increment_version() {
    local type="$1"
    local current_version=$(get_version)
    
    local major=$(echo "${current_version}" | cut -d'.' -f1)
    local minor=$(echo "${current_version}" | cut -d'.' -f2)
    local patch=$(echo "${current_version}" | cut -d'.' -f3)
    
    case "${type}" in
        major)
            major=$((major + 1))
            minor=0
            patch=0
            ;;
        minor)
            minor=$((minor + 1))
            patch=0
            ;;
        patch)
            patch=$((patch + 1))
            ;;
        *)
            log_error "无效的版本类型: ${type} (major/minor/patch)"
            return 1
            ;;
    esac
    
    local new_version="${major}.${minor}.${patch}"
    set_version "${new_version}"
    log_success "版本号已更新: ${current_version} -> ${new_version}"
    
    return 0
}
# 创建 Git 标签
create_git_tag() {
    local version="$1"
    
    log_step "创建 Git 标签..."
    
    if ! check_command "git"; then
        return 1
    fi
    
    local tag_name="${GIT_TAG_PREFIX}${version}"
    
    if git tag -a "${tag_name}" -m "Release version ${version}" 2>&1 | tee -a "${LOG_FILE}"; then
        log_success "Git 标签创建成功: ${tag_name}"
    else
        log_error "Git 标签创建失败"
        return 1
    fi
}
# 推送 Git 标签
push_git_tag() {
    log_step "推送 Git 标签..."
    
    if ! check_command "git"; then
        return 1
    fi
    
    if git push origin --tags 2>&1 | tee -a "${LOG_FILE}"; then
        log_success "Git 标签推送成功"
    else
        log_error "Git 标签推送失败"
        return 1
    fi
}
# 获取 GitHub 仓库信息
get_github_repo_info() {
    log_info "从 git remote 获取 GitHub 仓库信息..."
    
    # 检查 git 命令
    if ! command -v git &> /dev/null; then
        log_error "git 命令未安装"
        return 1
    fi
    
    # 检查是否在 git 仓库中
    if ! git rev-parse --git-dir &> /dev/null; then
        log_error "当前目录不是 git 仓库"
        return 1
    fi
    
    # 获取 remote URL
    local remote_url=$(git config --get remote.origin.url 2>/dev/null)
    
    if [ -z "${remote_url}" ]; then
        log_error "未找到 git remote origin"
        return 1
    fi
    
    log_info "Remote URL: ${remote_url}"
    
    # 解析 GitHub 仓库信息
    # 支持 HTTPS 和 SSH 格式
    # HTTPS: https://github.com/owner/repo.git 或 https://github.com/owner/repo
    # SSH: git@github.com:owner/repo.git 或 git@github.com:owner/repo
    
    if [[ "${remote_url}" =~ ^https://github\.com/([^/]+)/([^/]+?)(\.git)?$ ]]; then
        GITHUB_REPO_OWNER="${BASH_REMATCH[1]}"
        GITHUB_REPO_NAME="${BASH_REMATCH[2]}"
    elif [[ "${remote_url}" =~ ^git@github\.com:([^/]+)/([^/]+?)(\.git)?$ ]]; then
        GITHUB_REPO_OWNER="${BASH_REMATCH[1]}"
        GITHUB_REPO_NAME="${BASH_REMATCH[2]}"
    else
        log_error "无法解析 GitHub 仓库信息"
        log_info "Remote URL 格式应为: https://github.com/owner/repo.git 或 git@github.com:owner/repo.git"
        return 1
    fi
    
    log_success "GitHub 仓库信息: ${GITHUB_REPO_OWNER}/${GITHUB_REPO_NAME}"
    return 0
}
# 创建 GitHub Release
create_github_release() {
    log_step "创建 GitHub Release..."
    
    # 检查 gh CLI 工具
    if ! command -v gh &> /dev/null; then
        log_error "GitHub CLI (gh) 未安装"
        log_info "请访问 https://cli.github.com/ 安装 GitHub CLI"
        return 1
    fi
    
    # 从 git remote 自动获取 GitHub 仓库信息
    if [ -z "${GITHUB_REPO_OWNER}" ] || [ -z "${GITHUB_REPO_NAME}" ]; then
        if ! get_github_repo_info; then
            return 1
        fi
    fi
    
    # 获取版本号
    local version=$(get_version)
    local tag_name="${GIT_TAG_PREFIX}${version}"
    
    # 获取发布包文件
    local package_name="${PACKAGE_NAME}-${version}"
    local package_file="${RELEASE_DIR}/${package_name}.${PACKAGE_FORMAT}"
    
    if [ ! -f "${package_file}" ]; then
        log_error "发布包不存在: ${package_file}"
        log_info "请先运行 --package 或 --release"
        return 1
    fi
    
    # 检查是否已存在该 release
    if gh release view "${tag_name}" &> /dev/null; then
        log_warning "Release ${tag_name} 已存在"
        log_info "如需更新，请先删除现有 release"
        return 1
    fi
    
    # 读取 CHANGELOG 内容
    local release_notes=""
    if [ -f "${CHANGELOG_FILE}" ]; then
        # 提取当前版本的 CHANGELOG 内容
        release_notes=$(sed -n "/^## \[${version}\]/,/^## \[/p" "${CHANGELOG_FILE}" | head -n -1)
    fi
    
    # 如果没有 CHANGELOG，使用默认内容
    if [ -z "${release_notes}" ]; then
        release_notes="Release ${version}"
    fi
    
    # 创建 GitHub Release
    log_info "创建 GitHub Release: ${tag_name}"
    
    if gh release create "${tag_name}" \
        --title "${PACKAGE_NAME} ${version}" \
        --notes "${release_notes}" \
        "${package_file}" 2>&1 | tee -a "${LOG_FILE}"; then
        log_success "GitHub Release 创建成功"
        log_info "Release URL: https://github.com/${GITHUB_REPO_OWNER}/${GITHUB_REPO_NAME}/releases/tag/${tag_name}"
        return 0
    else
        log_error "GitHub Release 创建失败"
        return 1
    fi
}
# 更新 CHANGELOG
update_changelog() {
    local version="$1"
    
    log_step "更新 CHANGELOG..."
    
    if [ ! -f "${CHANGELOG_FILE}" ]; then
        cat > "${CHANGELOG_FILE}" << EOF
# 更新日志
## [${version}] - $(date '+%Y-%m-%d')
### 新增
- 初始化项目
### 修复
- 无
### 改进
- 无
### 已知问题
- 无
EOF
        log_info "CHANGELOG 文件已创建: ${CHANGELOG_FILE}"
    else
        local changelog_content=$(cat "${CHANGELOG_FILE}")
        
        cat > "${CHANGELOG_FILE}" << EOF
## [${version}] - $(date '+%Y-%m-%d')
### 新增
- 待更新
### 修复
- 待更新
### 改进
- 待更新
### 已知问题
- 待更新
${changelog_content}
EOF
        log_info "CHANGELOG 文件已更新"
    fi
}
# 验证代码完整性
validate_code() {
    log_step "验证代码完整性..."
    
    local errors=0
    
    # 检查必需的文件
    local required_files=(
        "server.py"
        "client.py"
        "common.py"
        "config.py"
        "logger.py"
        "requirements.txt"
    )
    
    for file in "${required_files[@]}"; do
        if [ ! -f "${WORKSPACE_DIR}/${file}" ]; then
            log_error "必需文件不存在: ${file}"
            errors=$((errors + 1))
        fi
    done
    
    # 检查必需的目录
    local required_dirs=(
        "tunnel"
        "protocol"
    )
    
    for dir in "${required_dirs[@]}"; do
        if [ ! -d "${WORKSPACE_DIR}/${dir}" ]; then
            log_error "必需目录不存在: ${dir}"
            errors=$((errors + 1))
        fi
    done
    
    # 检查 Python 语法
    log_info "检查 Python 语法..."
    for py_file in server.py client.py common.py config.py logger.py; do
        if [ -f "${WORKSPACE_DIR}/${py_file}" ]; then
            if ! python3 -m py_compile "${WORKSPACE_DIR}/${py_file}" 2>&1 | tee -a "${LOG_FILE}"; then
                log_error "Python 语法错误: ${py_file}"
                errors=$((errors + 1))
            fi
        fi
    done
    
    if [ ${errors} -eq 0 ]; then
        log_success "代码完整性验证通过"
        return 0
    else
        log_error "代码完整性验证失败，发现 ${errors} 个错误"
        return 1
    fi
}
# 构建代码
build_code() {
    log_step "构建代码..."
    
    # 清理构建目录
    clean_build
    
    # 复制文件到构建目录
    log_info "复制文件到构建目录..."
    
    # 复制 Python 文件
    cp -r "${WORKSPACE_DIR}"/*.py "${BUILD_DIR}/"
    
    # 复制模块目录（排除 __pycache__）
    for dir in tunnel protocol; do
        if [ -d "${WORKSPACE_DIR}/${dir}" ]; then
            # 使用 rsync 排除 __pycache__ 目录
            if command -v rsync &> /dev/null; then
                rsync -av --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' "${WORKSPACE_DIR}/${dir}/" "${BUILD_DIR}/${dir}/"
            else
                # 如果 rsync 不可用，使用 cp 并手动删除 __pycache__
                cp -r "${WORKSPACE_DIR}/${dir}" "${BUILD_DIR}/"
                find "${BUILD_DIR}/${dir}" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
                find "${BUILD_DIR}/${dir}" -type f -name '*.pyc' -delete 2>/dev/null || true
                find "${BUILD_DIR}/${dir}" -type f -name '*.pyo' -delete 2>/dev/null || true
            fi
        fi
    done
    
    # 复制配置文件
    if [ -f "${WORKSPACE_DIR}/config.yaml" ]; then
        cp "${WORKSPACE_DIR}/config.yaml" "${BUILD_DIR}/"
    fi
    
    if [ -f "${WORKSPACE_DIR}/users.yaml" ]; then
        cp "${WORKSPACE_DIR}/users.yaml" "${BUILD_DIR}/"
    fi
    
    # 复制依赖文件
    if [ -f "${WORKSPACE_DIR}/requirements.txt" ]; then
        cp "${WORKSPACE_DIR}/requirements.txt" "${BUILD_DIR}/"
    fi
    
    # 复制脚本文件
    for script in install.sh install-server.sh install-client.sh backup.sh healthcheck.sh; do
        if [ -f "${WORKSPACE_DIR}/${script}" ]; then
            cp "${WORKSPACE_DIR}/${script}" "${BUILD_DIR}/"
        fi
    done
    
    # 复制文档文件
    if [ -f "${WORKSPACE_DIR}/README.md" ]; then
        cp "${WORKSPACE_DIR}/README.md" "${BUILD_DIR}/"
    fi
    
    if [ -f "${WORKSPACE_DIR}/LICENSE" ]; then
        cp "${WORKSPACE_DIR}/LICENSE" "${BUILD_DIR}/"
    fi
    
    # 创建版本信息文件
    local version=$(get_version)
    cat > "${BUILD_DIR}/VERSION" << EOF
${version}
EOF
    
    # 创建构建信息文件
    cat > "${BUILD_DIR}/BUILD_INFO" << EOF
Package: ${PACKAGE_NAME}
Version: ${version}
Build Date: $(date '+%Y-%m-%d %H:%M:%S')
Git Branch: ${GIT_BRANCH}
Git Commit: $(git rev-parse HEAD 2>/dev/null || echo "unknown")
EOF
    
    log_success "代码构建完成"
    return 0
}
# 创建发布包
create_package() {
    log_step "创建发布包..."
    
    local version=$(get_version)
    local package_name="${PACKAGE_NAME}-${version}"
    local package_file="${RELEASE_DIR}/${package_name}.${PACKAGE_FORMAT}"
    
    # 进入构建目录
    cd "${BUILD_DIR}"
    
    # 创建压缩包
    log_info "创建压缩包: ${package_file}"
    if tar -czf "${package_file}" -C "${BUILD_DIR}" . 2>&1 | tee -a "${LOG_FILE}"; then
        log_success "发布包创建成功: ${package_file}"
    else
        log_error "发布包创建失败"
        return 1
    fi
    
    # 计算包大小
    local package_size=$(du -h "${package_file}" | cut -f1)
    log_info "包大小: ${package_size}"
    
    # 计算包哈希
    local package_hash=$(sha256sum "${package_file}" | cut -d' ' -f1)
    log_info "包哈希 (SHA256): ${package_hash}"
    
    # 保存包信息
    cat > "${RELEASE_DIR}/${package_name}.info" << EOF
Package: ${PACKAGE_NAME}
Version: ${version}
File: ${package_file}
Size: ${package_size}
Hash (SHA256): ${package_hash}
Created: $(date '+%Y-%m-%d %H:%M:%S')
EOF
    
    return 0
}
# 显示发布信息
show_release_info() {
    log_step "显示发布信息..."
    
    local version=$(get_version)
    local package_name="${PACKAGE_NAME}-${version}"
    local package_file="${RELEASE_DIR}/${package_name}.${PACKAGE_FORMAT}"
    
    if [ ! -f "${package_file}" ]; then
        log_error "发布包不存在: ${package_file}"
        return 1
    fi
    
    echo ""
    echo "=========================================="
    echo "发布信息"
    echo "=========================================="
    echo "包名称: ${PACKAGE_NAME}"
    echo "版本: ${version}"
    echo "文件: ${package_file}"
    echo ""
    
    if [ -f "${RELEASE_DIR}/${package_name}.info" ]; then
        cat "${RELEASE_DIR}/${package_name}.info"
    fi
    
    echo "=========================================="
}
# 显示帮助信息
show_help() {
    cat << EOF
SMTP Tunnel Proxy - 服务端打包发布脚本
用法: $(basename "$0") [选项]
选项:
  --build                  构建代码
  --package                创建发布包
  --release                完整发布流程（构建+打包）
  --version <version>      设置版本号
  --increment <type>       增加版本号 (major/minor/patch)
  --tag                    创建 Git 标签
  --push-tag               推送 Git 标签
  --create-release         创建 GitHub Release
  --clean                  清理构建目录
  --cleanup-releases       清理旧发布
  --info                   显示发布信息
  -h, --help               显示此帮助信息
环境变量:
示例:
  $(basename "$0") --release                            # 完整发布流程
  $(basename "$0") --increment minor --tag --push-tag   # 增加次版本、创建和推送标签
  $(basename "$0") --create-release                    # 创建 GitHub Release
注意:
  - 所有操作都会记录到日志文件
EOF
}
# ============================================================================
# 主程序
# ============================================================================
main() {
    local action=""
    local version=""
    local increment_type=""
    
    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --build)
                action="build"
                shift
                ;;
            --package)
                action="package"
                shift
                ;;
            --release)
                action="release"
                shift
                ;;
            --version)
                if [[ $# -lt 2 ]]; then
                    log_error "请指定版本号"
                    show_help
                    exit 1
                fi
                version="$2"
                set_version "${version}"
                shift 2
                action="version"
                ;;
            --increment)
                if [[ $# -lt 2 ]]; then
                    log_error "请指定版本类型 (major/minor/patch)"
                    show_help
                    exit 1
                fi
                increment_type="$2"
                shift 2
                action="increment"
                ;;
            --tag)
                action="tag"
                shift
                ;;
            --push-tag)
                action="push-tag"
                shift
                ;;
            --create-release)
                action="create-release"
                shift
                ;;
            --clean)
                action="clean"
                shift
                ;;
            --cleanup-releases)
                action="cleanup-releases"
                shift
                ;;
            --info)
                action="info"
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log_error "未知选项: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # 如果没有指定操作，显示帮助
    if [ -z "${action}" ]; then
        show_help
        exit 0
    fi
    
    # 执行相应的操作
    case ${action} in
        build)
            # 创建必要的目录
            create_directories
            if ! validate_code; then
                exit 1
            fi
            build_code
            ;;
        package)
            # 创建必要的目录
            create_directories
            if [ ! -d "${BUILD_DIR}" ] || [ -z "$(ls -A ${BUILD_DIR})" ]; then
                log_error "构建目录为空，请先运行 --build"
                exit 1
            fi
            create_package
            ;;
        release)
            # 创建必要的目录
            create_directories
            if ! validate_code; then
                exit 1
            fi
            build_code
            create_package
            show_release_info
            ;;
        deploy)
            # 创建必要的目录
            create_directories
            local version=$(get_version)
            local package_name="${PACKAGE_NAME}-${version}"
            local package_file="${RELEASE_DIR}/${package_name}.${PACKAGE_FORMAT}"
            
            if [ ! -f "${package_file}" ]; then
                log_error "发布包不存在，请先运行 --package"
                exit 1
            fi
            
            deploy_to_remote "${package_file}"
            health_check
            ;;
        rollback)
            # 创建必要的目录
            create_directories
            rollback_deployment
            ;;
        health-check)
            # 创建必要的目录
            create_directories
            health_check
            ;;
        tag)
            local version=$(get_version)
            create_git_tag "${version}"
            ;;
        push-tag)
            push_git_tag
            ;;
        create-release)
            create_github_release
            ;;
        version)
            # 版本号已在参数解析时设置
            ;;
        increment)
            # 版本号增加会在后面统一处理
            ;;
        clean)
            clean_build
            ;;
        cleanup-releases)
            # 创建必要的目录
            create_directories
            cleanup_old_releases
            ;;
        info)
            show_release_info
            ;;
        *)
            log_error "未知操作: ${action}"
            exit 1
            ;;
    esac
    
    # 处理版本增加
    if [ -n "${increment_type}" ]; then
        increment_version "${increment_type}"
    fi
    
    # 记录结束时间
    log_info "=========================================="
    log_info "发布脚本完成"
    log_info "=========================================="
    
    exit 0
}
# 执行主程序
main "$@"
