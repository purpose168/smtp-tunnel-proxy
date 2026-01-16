#!/bin/bash
#
# SMTP 隧道代理 - 客户端安装脚本
#
# 一行命令安装:
#   curl -sSL https://raw.githubusercontent.com/purpose168/smtp-tunnel-proxy/main/install-client.sh | sudo bash
#
# 版本: 1.3.0
#

# 输出颜色定义
RED='\033[0;31m'      # 红色 - 错误
GREEN='\033[0;32m'    # 绿色 - 信息
YELLOW='\033[1;33m'   # 黄色 - 警告
BLUE='\033[0;34m'     # 蓝色 - 步骤
CYAN='\033[0;36m'     # 青色 - 提问
NC='\033[0m'          # 无颜色

# GitHub 原始文件 URL 基础地址
GITHUB_RAW="https://raw.githubusercontent.com/purpose168/smtp-tunnel-proxy/main"

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/smtp-tunnel-proxy"

# 安装目录（使用脚本执行时的当前路径）
INSTALL_DIR="$SCRIPT_DIR"           # 程序安装目录
CONFIG_DIR="$SCRIPT_DIR"            # 配置文件目录
VENV_DIR="$SCRIPT_DIR/venv"        # Python 虚拟环境目录
LOG_DIR="$SCRIPT_DIR/logs"           # 日志目录

# BIN_DIR 保持系统级目录不变
BIN_DIR="/usr/local/bin"            # 可执行文件目录

# 日志文件
LOG_FILE="$LOG_DIR/install-client.log"

# 需要下载的客户端 Python 文件
# 主入口文件
CLIENT_FILES="client.py socks5_server.py"

# 从 common.py 拆分出的模块（客户端需要的）
COMMON_MODULES="protocol/__init__.py protocol/core.py protocol/client.py tunnel/__init__.py tunnel/crypto.py tunnel/base.py tunnel/client.py connection.py config.py logger.py"

# 所有 Python 文件
PYTHON_FILES="$CLIENT_FILES $COMMON_MODULES"

# 日志记录函数
log_info() {
    local message=$1
    print_info "$message"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] $message" >> "$LOG_FILE"
}

log_warn() {
    local message=$1
    print_warn "$message"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [WARN] $message" >> "$LOG_FILE"
}

log_error() {
    local message=$1
    print_error "$message"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $message" >> "$LOG_FILE"
}

log_step() {
    local message=$1
    print_step "$message"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [STEP] $message" >> "$LOG_FILE"
}

# 打印函数
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

print_ask() {
    echo -e "${CYAN}[?]${NC} $1"
}

# 检查是否以 root 权限运行
check_root() {
    if [ "$EUID" -ne 0 ]; then
        print_error "请以 root 权限运行（使用 sudo）"
        echo ""
        echo "使用方法: curl -sSL $GITHUB_RAW/install-client.sh | sudo bash"
        exit 1
    fi
}

# 检测操作系统
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        OS_VERSION=$VERSION_ID
    else
        print_error "无法检测操作系统"
        exit 1
    fi
    print_info "检测到操作系统: $OS $OS_VERSION"
}

# 安装 Python 和依赖
install_dependencies() {
    print_step "安装系统依赖..."
    
    case $OS in
        ubuntu|debian)
            apt-get update -qq
            apt-get install -y -qq python3 python3-pip python3-venv curl
            ;;
        centos|rhel|rocky|alma)
            if command -v dnf &> /dev/null; then
                dnf install -y python3 python3-pip python3-devel curl
            else
                yum install -y python3 python3-pip python3-devel curl
            fi
            ;;
        fedora)
            dnf install -y python3 python3-pip python3-devel curl
            ;;
        arch|manjaro)
            pacman -Sy --noconfirm python python-pip curl
            ;;
        *)
            print_warn "未知操作系统 '$OS'，假设已安装 Python 3 和 curl"
            ;;
    esac

    # 检查 Python 版本
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        print_info "Python 版本: $PYTHON_VERSION"
        
        # 验证 Python 版本是否满足要求
        PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
        PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')
        
        if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]); then
            print_error "Python 3.8+ 是必需的，当前版本: $PYTHON_VERSION"
            exit 1
        fi
        
        print_info "Python 版本检查通过: $PYTHON_VERSION"
    else
        print_error "未找到 Python 3。请安装 Python 3.8+"
        exit 1
    fi
}

# 创建目录
create_directories() {
    print_step "创建目录..."
    
    # 创建安装目录
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$CONFIG_DIR"
    
    chmod 755 "$INSTALL_DIR"
    chmod 700 "$CONFIG_DIR"
    
    print_info "已创建: $INSTALL_DIR"
    print_info "已创建: $CONFIG_DIR"
}

# 从 GitHub 下载文件
download_file() {
    local filename=$1
    local destination=$2
    local url="$GITHUB_RAW/$filename"
    
    log_step "正在下载: $filename"
    log_info "URL: $url"
    log_info "目标: $destination"
    
    # 先删除目标文件（如果存在）
    if [ -f "$destination" ]; then
        log_warn "目标文件已存在，正在删除: $destination"
        rm -f "$destination"
    fi
    
    # 创建目标目录（如果不存在）
    local dest_dir=$(dirname "$destination")
    if [ ! -d "$dest_dir" ]; then
        log_info "创建目标目录: $dest_dir"
        mkdir -p "$dest_dir"
    fi
    
    # 尝试下载文件
    local retry_count=0
    local max_retries=3
    
    while [ $retry_count -lt $max_retries ]; do
        if curl -sSL -f "$url" -o "$destination" 2>/dev/null; then
            log_info "  已下载: $filename"
            return 0
        else
            retry_count=$((retry_count + 1))
            log_warn "  下载失败，重试 $retry_count/$max_retries..."
            sleep 2
        fi
    done
    
    log_error "  下载失败: $filename（已重试 $max_retries 次）"
    log_error "  URL: $url"
    log_error "  请检查网络连接或文件是否存在"
    return 1
}

# 下载并安装文件
install_files() {
    print_step "从 GitHub 下载文件..."
    
    # 下载 Python 文件到安装目录
    for file in $PYTHON_FILES; do
        if ! download_file "$file" "$INSTALL_DIR/$file"; then
            print_error "下载必需文件失败: $file"
            exit 1
        fi
    done
    
    # 下载 requirements.txt
    if ! download_file "requirements.txt" "$INSTALL_DIR/requirements.txt"; then
        print_error "下载 requirements.txt 失败"
        exit 1
    fi
}

# 检查 Python 虚拟环境
check_venv() {
    print_step "检查 Python 虚拟环境..."
    
    if [ -n "$VIRTUAL_ENV" ]; then
        print_info "当前已在虚拟环境中: $VIRTUAL_ENV"
        return 0
    else
        print_info "当前未在虚拟环境中"
        return 1
    fi
}

# 创建 Python 虚拟环境
create_venv() {
    print_step "创建 Python 虚拟环境..."
    
    # 检查虚拟环境是否已存在
    if [ -d "$VENV_DIR" ]; then
        print_warn "虚拟环境已存在: $VENV_DIR"
        
        # 询问是否重新创建
        print_ask "是否重新创建虚拟环境？[y/N]: "
        read -p "    " RECREATE_VENV < /dev/tty
        
        if [ "$RECREATE_VENV" = "y" ] || [ "$RECREATE_VENV" = "Y" ]; then
            print_info "正在删除现有虚拟环境..."
            rm -rf "$VENV_DIR"
        else
            print_info "保留现有虚拟环境"
            return 0
        fi
    fi
    
    # 创建虚拟环境
    print_info "正在创建虚拟环境: $VENV_DIR"
    
    if python3 -m venv "$VENV_DIR"; then
        print_info "虚拟环境创建成功"
        return 0
    else
        print_error "虚拟环境创建失败"
        return 1
    fi
}

# 激活虚拟环境
activate_venv() {
    if [ -f "$VENV_DIR/bin/activate" ]; then
        print_info "激活虚拟环境: $VENV_DIR"
        source "$VENV_DIR/bin/activate"
        print_info "虚拟环境已激活"
        return 0
    else
        print_error "虚拟环境激活脚本不存在: $VENV_DIR/bin/activate"
        return 1
    fi
}

# 验证虚拟环境
verify_venv() {
    print_step "验证虚拟环境..."
    
    # 检查虚拟环境目录
    if [ ! -d "$VENV_DIR" ]; then
        print_error "虚拟环境目录不存在: $VENV_DIR"
        return 1
    fi
    
    # 检查 Python 解释器
    if [ ! -f "$VENV_DIR/bin/python" ]; then
        print_error "虚拟环境 Python 解释器不存在"
        return 1
    fi
    
    # 检查 pip
    if [ ! -f "$VENV_DIR/bin/pip" ]; then
        print_error "虚拟环境 pip 不存在"
        return 1
    fi
    
    # 获取虚拟环境信息
    VENV_PYTHON_VERSION=$($VENV_DIR/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)
    VENV_PIP_VERSION=$($VENV_DIR/bin/pip --version 2>/dev/null | cut -d' ' -f2)
    
    print_info "虚拟环境 Python 版本: $VENV_PYTHON_VERSION"
    print_info "虚拟环境 pip 版本: $VENV_PIP_VERSION"
    
    # 检查是否在虚拟环境中
    if [ "$VIRTUAL_ENV" = "$VENV_DIR" ]; then
        print_info "当前已在虚拟环境中"
    else
        print_info "虚拟环境路径: $VENV_DIR"
    fi
    
    print_info "虚拟环境验证通过"
    return 0
}

# 停用虚拟环境
deactivate_venv() {
    if [ -n "$VIRTUAL_ENV" ]; then
        print_info "停用当前虚拟环境: $VIRTUAL_ENV"
        deactivate 2>/dev/null || true
    fi
}

# 列出虚拟环境信息
list_venv_info() {
    echo ""
    echo -e "${BLUE}Python 虚拟环境信息:${NC}"
    echo -e "  路径: $VENV_DIR"
    echo -e "  Python: $VENV_DIR/bin/python"
    echo -e "  pip: $VENV_DIR/bin/pip"
    echo -e "  激活脚本: $VENV_DIR/bin/activate"
    echo ""
    
    if [ -f "$VENV_DIR/bin/python" ]; then
        echo -e "${BLUE}Python 版本信息:${NC}"
        $VENV_DIR/bin/python --version
        echo ""
    fi
    
    if [ -f "$VENV_DIR/bin/pip" ]; then
        echo -e "${BLUE}已安装的包:${NC}"
        $VENV_DIR/bin/pip list --format=columns | head -20
        echo ""
    fi
}

# 安装 Python 包
install_python_packages() {
    print_step "在虚拟环境中安装 Python 包..."
    
    # 检查虚拟环境是否存在
    if [ ! -d "$VENV_DIR" ]; then
        print_error "虚拟环境不存在，请先创建虚拟环境"
        return 1
    fi
    
    # 激活虚拟环境
    source "$VENV_DIR/bin/activate"
    
    # 升级 pip
    print_info "升级 pip 到最新版本..."
    pip install --upgrade pip
    
    # 安装 Python 包
    print_info "安装依赖包..."
    if pip install -r "$INSTALL_DIR/requirements.txt"; then
        print_info "Python 包安装成功"
        
        # 显示已安装的包
        print_info "已安装的包:"
        pip list --format=columns | grep -E "(cryptography|pyyaml)" || true
        return 0
    else
        print_error "Python 包安装失败"
        return 1
    fi
}

# 清理虚拟环境
clean_venv() {
    print_step "清理虚拟环境..."
    
    if [ -d "$VENV_DIR" ]; then
        print_info "删除虚拟环境: $VENV_DIR"
        rm -rf "$VENV_DIR"
        print_info "虚拟环境已删除"
    else
        print_info "虚拟环境不存在，无需清理"
    fi
}

# 重新安装虚拟环境
reinstall_venv() {
    print_step "重新安装虚拟环境..."
    
    # 清理现有虚拟环境
    clean_venv
    
    # 创建新的虚拟环境
    if create_venv; then
        # 激活虚拟环境
        activate_venv
        
        # 安装 Python 包
        install_python_packages
        
        # 验证安装
        if verify_venv; then
            print_info "虚拟环境重新安装成功"
            return 0
        else
            print_error "虚拟环境重新安装失败"
            return 1
        fi
    else
        print_error "虚拟环境创建失败"
        return 1
    fi
}

# 创建卸载脚本
create_uninstall_script() {
    cat > "$INSTALL_DIR/uninstall-client.sh" << 'EOF'
#!/bin/bash
# SMTP 隧道代理 - 客户端卸载脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "正在清理虚拟环境..."
deactivate 2>/dev/null || true

echo "正在删除文件..."
rm -rf "$SCRIPT_DIR/venv"
rm -rf "$SCRIPT_DIR"

echo ""
echo "SMTP 隧道代理客户端已成功卸载"
EOF
    
    chmod +x "$INSTALL_DIR/uninstall-client.sh"
    print_info "已创建: $INSTALL_DIR/uninstall-client.sh"
}

# 交互式设置
interactive_setup() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  交互式设置${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    
    # 询问是否创建虚拟环境
    print_ask "是否创建 Python 虚拟环境？[Y/n]: "
    read -p "    " CREATE_VENV < /dev/tty
    
    if [ -z "$CREATE_VENV" ] || [ "$CREATE_VENV" = "y" ] || [ "$CREATE_VENV" = "Y" ]; then
        # 创建虚拟环境
        if ! create_venv; then
            print_error "虚拟环境创建失败"
            exit 1
        fi
        
        # 激活虚拟环境
        if ! activate_venv; then
            print_error "虚拟环境激活失败"
            exit 1
        fi
        
        # 安装 Python 包
        if ! install_python_packages; then
            print_error "Python 包安装失败"
            exit 1
        fi
    else
        print_info "跳过虚拟环境创建"
        echo ""
        print_info "您可以使用现有的虚拟环境或系统 Python"
    fi
    
    # 询问是否下载客户端文件
    print_ask "是否下载客户端文件？[Y/n]: "
    read -p "    " DOWNLOAD_CLIENT < /dev/tty
    
    if [ -z "$DOWNLOAD_CLIENT" ] || [ "$DOWNLOAD_CLIENT" = "y" ] || [ "$DOWNLOAD_CLIENT" = "Y" ]; then
        # 下载客户端文件
        if ! install_files; then
            print_error "下载客户端文件失败"
            exit 1
        fi
    else
        print_info "跳过客户端文件下载"
        echo ""
        print_info "您可以使用现有的客户端文件"
    fi
}

# 打印最终摘要
print_summary() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  安装完成！${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "您的 SMTP 隧道代理客户端已安装！"
    echo ""
    echo -e "${BLUE}虚拟环境:${NC}"
    echo "   $VENV_DIR"
    echo ""
    echo -e "${BLUE}已安装的包:${NC}"
    echo "   $(pip list --format=columns 2>/dev/null | head -10)"
    echo ""
    echo -e "${BLUE}客户端文件:${NC}"
    echo "   $INSTALL_DIR/client.py"
    echo "   $INSTALL_DIR/socks5_server.py"
    echo ""
    echo -e "${BLUE}卸载:${NC}"
    echo "   $INSTALL_DIR/uninstall-client.sh"
    echo ""
    echo -e "${BLUE}下一步:${NC}"
    echo "   1. 编辑配置文件: $INSTALL_DIR/config.yaml"
    echo "   2. 运行客户端: python $INSTALL_DIR/client.py"
    echo ""
    echo -e "${YELLOW}提示:${NC}"
    echo "   如果您使用虚拟环境，请先激活虚拟环境："
    echo "     source $VENV_DIR/bin/activate"
    echo ""
}

# 验证安装
verify_installation() {
    print_step "验证安装..."
    
    # 检查安装目录
    if [ ! -d "$INSTALL_DIR" ]; then
        log_error "安装目录不存在: $INSTALL_DIR"
        return 1
    fi
    
    # 检查虚拟环境
    if [ ! -d "$VENV_DIR" ]; then
        log_warn "虚拟环境未创建（将在交互式设置中创建）"
    fi
    
    # 检查客户端文件
    if [ ! -f "$INSTALL_DIR/client.py" ]; then
        log_warn "客户端文件未安装（将在交互式设置中下载）"
    fi
    
    log_info "安装验证通过"
    return 0
}

# 回滚安装
rollback_installation() {
    print_step "回滚安装..."
    
    log_warn "正在删除安装的文件..."
    
    # 清理虚拟环境
    rm -rf "$VENV_DIR"
    
    # 删除安装的文件
    rm -rf "$INSTALL_DIR"
    
    log_info "回滚完成"
    log_warn "请重新运行安装脚本"
}

# 主安装流程
main() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  SMTP 隧道代理客户端安装程序${NC}"
    echo -e "${GREEN}  版本 1.3.0${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    
    check_root
    detect_os
    install_dependencies
    create_directories
    install_files
    
    # 交互式设置
    interactive_setup
    
    print_summary
}

# 运行主函数
main
