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
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 安装目录（使用脚本执行时当前路径下的 smtp-tunnel 文件夹）
INSTALL_DIR="$SCRIPT_DIR/smtp-tunnel"           # 程序安装目录
CONFIG_DIR="$SCRIPT_DIR/smtp-tunnel/config"            # 配置文件目录
VENV_DIR="$SCRIPT_DIR/smtp-tunnel/venv"        # Python 虚拟环境目录
LOG_DIR="$SCRIPT_DIR/smtp-tunnel/logs"           # 日志目录

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

# 设置日志目录
setup_log_directory() {
    print_step "设置日志目录..."
    
    # 创建日志目录
    mkdir -p "$LOG_DIR"
    chmod 755 "$LOG_DIR"
    
    # 创建日志文件
    touch "$LOG_FILE"
    chmod 644 "$LOG_FILE"
    
    print_info "已创建: $LOG_DIR"
    print_info "已创建: $LOG_FILE"
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
    
    # 设置文件权限
    print_info "设置文件权限..."
    
    # 设置 Python 文件权限
    find "$INSTALL_DIR" -name "*.py" -exec chmod 644 {} \;
    
    # 设置目录权限
    find "$INSTALL_DIR" -type d -exec chmod 755 {} \;
    
    # 设置子目录权限
    if [ -d "$INSTALL_DIR/protocol" ]; then
        chmod 755 "$INSTALL_DIR/protocol"
    fi
    if [ -d "$INSTALL_DIR/tunnel" ]; then
        chmod 755 "$INSTALL_DIR/tunnel"
    fi
    
    print_info "文件权限设置完成"
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
    
    # 检查客户端文件是否已存在
    if [ -f "$INSTALL_DIR/client.py" ] && [ -f "$INSTALL_DIR/socks5_server.py" ]; then
        print_info "客户端文件已存在，跳过下载"
        echo ""
        print_ask "是否重新下载客户端文件？[y/N]: "
        read -p "    " REDOWNLOAD_CLIENT < /dev/tty
        
        if [ "$REDOWNLOAD_CLIENT" = "y" ] || [ "$REDOWNLOAD_CLIENT" = "Y" ]; then
            # 下载客户端文件
            if ! install_files; then
                print_error "下载客户端文件失败"
                exit 1
            fi
        fi
    else
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
    fi
    
    # 询问是否创建虚拟环境
    echo ""
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
    
    # 配置文件处理
    echo ""
    print_step "配置文件设置"
    
    if [ -f "$CONFIG_DIR/config.yaml" ]; then
        print_info "配置文件已存在: $CONFIG_DIR/config.yaml"
        print_ask "是否重新创建配置文件？[y/N]: "
        read -p "    " RECREATE_CONFIG < /dev/tty
        
        if [ "$RECREATE_CONFIG" = "y" ] || [ "$RECREATE_CONFIG" = "Y" ]; then
            create_config_file
        fi
    else
        print_info "创建默认配置文件..."
        create_config_file
    fi
    
    # 检查证书文件
    check_certificates_simple
    
    # 生成管理脚本
    echo ""
    print_step "生成管理脚本"
    generate_start_script
    generate_stop_script
    generate_status_script
    
    # systemd 服务配置
    echo ""
    print_step "systemd 服务配置"
    
    # 检查是否为 root 用户
    if [ "$EUID" -ne 0 ]; then
        print_warn "需要 root 权限才能安装 systemd 服务"
        print_info "跳过 systemd 服务安装"
        print_info "您可以使用管理脚本手动启动客户端："
        print_info "  $INSTALL_DIR/start.sh"
    else
        # 检查 systemd 是否可用
        if command -v systemctl &> /dev/null; then
            print_ask "是否安装 systemd 服务？[Y/n]: "
            read -p "    " INSTALL_SYSTEMD < /dev/tty
            
            if [ -z "$INSTALL_SYSTEMD" ] || [ "$INSTALL_SYSTEMD" = "y" ] || [ "$INSTALL_SYSTEMD" = "Y" ]; then
                # 生成 systemd 服务文件
                if generate_systemd_service; then
                    # 启用服务
                    enable_systemd_service
                    
                    # 询问是否立即启动服务
                    echo ""
                    print_ask "是否立即启动服务？[Y/n]: "
                    read -p "    " START_NOW < /dev/tty
                    
                    if [ -z "$START_NOW" ] || [ "$START_NOW" = "y" ] || [ "$START_NOW" = "Y" ]; then
                        start_systemd_service
                    else
                        print_info "跳过启动服务"
                        echo ""
                        print_info "您可以稍后使用以下命令启动服务："
                        print_info "  sudo systemctl start smtp-tunnel-client"
                    fi
                fi
            else
                print_info "跳过 systemd 服务安装"
                print_info "您可以使用管理脚本手动启动客户端："
                print_info "  $INSTALL_DIR/start.sh"
            fi
        else
            print_warn "systemd 不可用，跳过 systemd 服务安装"
            print_info "您可以使用管理脚本手动启动客户端："
            print_info "  $INSTALL_DIR/start.sh"
        fi
    fi
}

# 创建配置文件
create_config_file() {
    cat > "$CONFIG_DIR/config.yaml" << 'EOF'
# SMTP 隧道代理客户端配置文件

# 服务器配置
server:
  # 服务器地址
  host: "your-server-ip"
  # 服务器端口
  port: 8443
  # CA 证书路径（从服务器获取）
  ca_cert: "config/ca.crt"
  # 客户端证书路径（从服务器获取）
  client_cert: "config/client.crt"
  # 客户端私钥路径（从服务器获取）
  client_key: "config/client.key"

# SOCKS5 代理配置
socks5:
  # 监听地址
  host: "127.0.0.1"
  # 监听端口
  port: 1080
  # 允许的客户端地址（空表示允许所有）
  allowed_clients: []

# 日志配置
logging:
  # 日志级别: DEBUG, INFO, WARNING, ERROR, CRITICAL
  level: "INFO"
  # 日志文件路径
  file: "logs/client.log"
  # 是否启用控制台日志
  console: true
  # 是否启用文件日志
  file_enabled: true
  # 日志文件最大大小（MB）
  max_size: 10
  # 保留的日志文件数量
  backup_count: 5

# 连接配置
connection:
  # 连接超时（秒）
  timeout: 30
  # 心跳间隔（秒）
  heartbeat_interval: 60
  # 最大重试次数
  max_retries: 3
  # 重试间隔（秒）
  retry_interval: 5

# 加密配置
crypto:
  # 加密算法: AES, ChaCha20
  algorithm: "AES"
  # 密钥长度（位）
  key_length: 256
EOF
    
    chmod 600 "$CONFIG_DIR/config.yaml"
    print_info "已创建配置文件: $CONFIG_DIR/config.yaml"
    print_warn "请编辑配置文件，设置服务器地址和证书路径"
}

# 生成启动脚本
generate_start_script() {
    print_step "生成启动脚本..."
    
    local start_script="$INSTALL_DIR/start.sh"
    
    cat > "$start_script" << 'EOF'
#!/bin/bash
# SMTP 隧道代理客户端启动脚本

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 配置文件路径
CONFIG_FILE="${SCRIPT_DIR}/config/config.yaml"

# 虚拟环境路径
VENV_DIR="${SCRIPT_DIR}/venv"

# 日志文件
LOG_FILE="${SCRIPT_DIR}/logs/client.log"

# 检查配置文件是否存在
if [ ! -f "$CONFIG_FILE" ]; then
    echo "错误: 配置文件不存在: $CONFIG_FILE"
    echo "请先运行安装脚本创建配置文件"
    exit 1
fi

# 检查虚拟环境是否存在
if [ -d "$VENV_DIR" ]; then
    # 使用虚拟环境中的 Python
    PYTHON_CMD="${VENV_DIR}/bin/python"
    
    if [ ! -f "$PYTHON_CMD" ]; then
        echo "错误: 虚拟环境中的 Python 不存在: $PYTHON_CMD"
        exit 1
    fi
else
    # 使用系统 Python
    PYTHON_CMD="python3"
    
    if ! command -v python3 &> /dev/null; then
        echo "错误: 找不到 python3 命令"
        echo "请先安装 Python 3"
        exit 1
    fi
fi

# 检查客户端文件是否存在
CLIENT_FILE="${SCRIPT_DIR}/client.py"
if [ ! -f "$CLIENT_FILE" ]; then
    echo "错误: 客户端文件不存在: $CLIENT_FILE"
    exit 1
fi

# 创建日志目录
mkdir -p "$(dirname "$LOG_FILE")"

# 启动客户端
echo "启动 SMTP 隧道代理客户端..."
echo "配置文件: $CONFIG_FILE"
echo "Python: $PYTHON_CMD"
echo "日志文件: $LOG_FILE"
echo ""

# 启动客户端（后台运行）
nohup "$PYTHON_CMD" "$CLIENT_FILE" -c "$CONFIG_FILE" >> "$LOG_FILE" 2>&1 &
CLIENT_PID=$!

# 保存 PID
echo "$CLIENT_PID" > "${SCRIPT_DIR}/client.pid"

echo "客户端已启动，PID: $CLIENT_PID"
echo ""
echo "查看日志: tail -f $LOG_FILE"
echo "停止客户端: ${SCRIPT_DIR}/stop.sh"
echo "查看状态: ${SCRIPT_DIR}/status.sh"
EOF
    
    chmod +x "$start_script"
    print_info "已生成启动脚本: $start_script"
}

# 生成停止脚本
generate_stop_script() {
    print_step "生成停止脚本..."
    
    local stop_script="$INSTALL_DIR/stop.sh"
    
    cat > "$stop_script" << 'EOF'
#!/bin/bash
# SMTP 隧道代理客户端停止脚本

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# PID 文件
PID_FILE="${SCRIPT_DIR}/client.pid"

# 检查 PID 文件是否存在
if [ ! -f "$PID_FILE" ]; then
    echo "错误: PID 文件不存在: $PID_FILE"
    echo "客户端可能未运行"
    exit 1
fi

# 读取 PID
PID=$(cat "$PID_FILE")

# 检查进程是否存在
if ! kill -0 "$PID" 2>/dev/null; then
    echo "警告: 进程 $PID 不存在"
    rm -f "$PID_FILE"
    exit 1
fi

# 停止进程
echo "正在停止客户端 (PID: $PID)..."
kill "$PID"

# 等待进程结束
for i in {1..10}; do
    if ! kill -0 "$PID" 2>/dev/null; then
        echo "客户端已停止"
        rm -f "$PID_FILE"
        exit 0
    fi
    sleep 1
done

# 如果进程仍在运行，强制停止
echo "警告: 进程未正常停止，强制终止..."
kill -9 "$PID"
rm -f "$PID_FILE"
echo "客户端已强制停止"
EOF
    
    chmod +x "$stop_script"
    print_info "已生成停止脚本: $stop_script"
}

# 生成状态脚本
generate_status_script() {
    print_step "生成状态脚本..."
    
    local status_script="$INSTALL_DIR/status.sh"
    
    cat > "$status_script" << 'EOF'
#!/bin/bash
# SMTP 隧道代理客户端状态脚本

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# PID 文件
PID_FILE="${SCRIPT_DIR}/client.pid"

# 日志文件
LOG_FILE="${SCRIPT_DIR}/logs/client.log"

# 检查 PID 文件是否存在
if [ ! -f "$PID_FILE" ]; then
    echo "状态: 未运行"
    echo "PID 文件不存在"
    exit 0
fi

# 读取 PID
PID=$(cat "$PID_FILE")

# 检查进程是否存在
if ! kill -0 "$PID" 2>/dev/null; then
    echo "状态: 未运行"
    echo "PID: $PID (进程已终止)"
    rm -f "$PID_FILE"
    exit 0
fi

# 进程正在运行
echo "状态: 运行中"
echo "PID: $PID"
echo ""
echo "进程信息:"
ps -p "$PID" -o pid,ppid,cmd,etime,pcpu,pmem
echo ""
echo "最近的日志 (最后 20 行):"
if [ -f "$LOG_FILE" ]; then
    tail -n 20 "$LOG_FILE"
else
    echo "日志文件不存在: $LOG_FILE"
fi
EOF
    
    chmod +x "$status_script"
    print_info "已生成状态脚本: $status_script"
}

# 生成 systemd 服务文件
generate_systemd_service() {
    print_step "生成 systemd 服务文件..."
    
    # 检查是否为 root 用户
    if [ "$EUID" -ne 0 ]; then
        print_warn "需要 root 权限才能安装 systemd 服务"
        print_info "请使用 sudo 运行安装脚本"
        return 1
    fi
    
    # 检查 systemd 是否可用
    if ! command -v systemctl &> /dev/null; then
        print_warn "systemd 不可用，跳过 systemd 服务安装"
        return 1
    fi
    
    local service_name="smtp-tunnel-client"
    local service_file="/etc/systemd/system/${service_name}.service"
    
    cat > "$service_file" << EOF
[Unit]
Description=SMTP 隧道代理客户端
Documentation=https://github.com/purpose168/smtp-tunnel-proxy
After=network-online.target
Wants=network-online.target
RequiresMountsFor=$INSTALL_DIR
RequiresMountsFor=$CONFIG_DIR

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR

# 优先使用虚拟环境中的 Python，备用使用系统 Python
ExecStart=$VENV_DIR/bin/python $INSTALL_DIR/client.py -c $CONFIG_DIR/config.yaml

# 重启策略
Restart=on-failure
RestartSec=5
StartLimitInterval=60
StartLimitBurst=3

# 标准输出和错误
StandardOutput=journal
StandardError=journal
SyslogIdentifier=smtp-tunnel-client

# Python 环境变量
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=VIRTUAL_ENV=$VENV_DIR
Environment=PATH=$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin

# 日志环境变量
Environment=LOG_LEVEL=INFO
Environment=LOG_DIR=$LOG_DIR
Environment=LOG_ENABLE_CONSOLE=false
Environment=LOG_ENABLE_FILE=true
Environment=LOG_ENABLE_JOURNAL=true

# 资源限制
LimitNOFILE=65536
LimitNPROC=4096
MemoryMax=512M

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
ReadWritePaths=$CONFIG_DIR
ReadWritePaths=$INSTALL_DIR
ReadWritePaths=$LOG_DIR

# 私有临时目录
PrivateTmp=true

# 网络访问能力
CapabilityBoundingSet=CAP_NET_BIND_SERVICE CAP_NET_RAW
AmbientCapabilities=CAP_NET_BIND_SERVICE CAP_NET_RAW

[Install]
WantedBy=multi-user.target
EOF
    
    chmod 644 "$service_file"
    
    # 重新加载 systemd 配置
    systemctl daemon-reload
    
    print_info "已生成 systemd 服务文件: $service_file"
    return 0
}

# 启用 systemd 服务
enable_systemd_service() {
    print_step "启用 systemd 服务..."
    
    local service_name="smtp-tunnel-client"
    
    if ! systemctl is-enabled "$service_name" &> /dev/null; then
        systemctl enable "$service_name"
        print_info "服务已设置为开机自启: $service_name"
    else
        print_info "服务已启用: $service_name"
    fi
}

# 启动 systemd 服务
start_systemd_service() {
    print_step "启动 systemd 服务..."
    
    local service_name="smtp-tunnel-client"
    
    if systemctl is-active --quiet "$service_name"; then
        print_info "服务已在运行: $service_name"
    else
        systemctl start "$service_name"
        print_info "服务已启动: $service_name"
    fi
    
    # 显示服务状态
    echo ""
    systemctl status "$service_name" --no-pager -l
}

# 检查证书文件
check_certificates_simple() {
    print_step "检查证书文件..."
    
    local cert_missing=false
    
    # 检查 CA 证书
    if [ ! -f "$CONFIG_DIR/ca.crt" ]; then
        print_warn "CA 证书未找到: $CONFIG_DIR/ca.crt"
        cert_missing=true
    else
        print_info "CA 证书已存在: $CONFIG_DIR/ca.crt"
    fi
    
    # 检查客户端证书
    if [ ! -f "$CONFIG_DIR/client.crt" ]; then
        print_warn "客户端证书未找到: $CONFIG_DIR/client.crt"
        cert_missing=true
    else
        print_info "客户端证书已存在: $CONFIG_DIR/client.crt"
    fi
    
    # 检查客户端私钥
    if [ ! -f "$CONFIG_DIR/client.key" ]; then
        print_warn "客户端私钥未找到: $CONFIG_DIR/client.key"
        cert_missing=true
    else
        print_info "客户端私钥已存在: $CONFIG_DIR/client.key"
    fi
    
    if [ "$cert_missing" = true ]; then
        echo ""
        print_warn "缺少证书文件！"
        echo ""
        echo -e "${YELLOW}证书文件说明:${NC}"
        echo "   客户端需要以下证书文件才能与服务器建立安全连接："
        echo "   - CA 证书 (ca.crt)"
        echo "   - 客户端证书 (client.crt)"
        echo "   - 客户端私钥 (client.key)"
        echo ""
        echo -e "${YELLOW}获取证书的步骤:${NC}"
        echo "   1. 在服务器上运行以下命令创建用户："
        echo "      sudo smtp-tunnel-adduser <username>"
        echo ""
        echo "   2. 服务器会生成以下证书文件："
        echo "      - /opt/smtp-tunnel/config/ca.crt"
        echo "      - /opt/smtp-tunnel/config/client-<username>.crt"
        echo "      - /opt/smtp-tunnel/config/client-<username>.key"
        echo ""
        echo -e "${YELLOW}使用证书下载脚本:${NC}"
        echo "   运行以下命令下载证书："
        echo "      ./download-certs.sh --server <服务器地址> --username <用户名>"
        echo ""
        echo -e "${YELLOW}或使用 scp 手动下载:${NC}"
        echo "   scp root@server:/opt/smtp-tunnel/config/ca.crt $CONFIG_DIR/"
        echo "   scp root@server:/opt/smtp-tunnel/config/client-<username>.crt $CONFIG_DIR/client.crt"
        echo "   scp root@server:/opt/smtp-tunnel/config/client-<username>.key $CONFIG_DIR/client.key"
        echo ""
        echo -e "${YELLOW}示例:${NC}"
        echo "   假设用户名为 'testuser'，服务器地址为 '192.168.1.100'："
        echo "   ./download-certs.sh --server 192.168.1.100 --username testuser"
        echo ""
        echo "   或使用 scp："
        echo "   scp root@192.168.1.100:/opt/smtp-tunnel/config/client-testuser.* $CONFIG_DIR/"
        echo "   scp root@192.168.1.100:/opt/smtp-tunnel/config/ca.crt $CONFIG_DIR/"
        echo ""
        echo -e "${YELLOW}注意事项:${NC}"
        echo "   - 确保将客户端证书重命名为 client.crt"
        echo "   - 确保将客户端私钥重命名为 client.key"
        echo "   - CA 证书保持为 ca.crt"
        echo "   - 证书文件权限应设置为 600（仅所有者可读写）"
        echo ""
        
        # 询问是否现在下载证书
        print_ask "是否现在使用证书下载脚本下载证书？[y/N]: "
        read -p "    " DOWNLOAD_CERTS < /dev/tty
        
        if [ "$DOWNLOAD_CERTS" = "y" ] || [ "$DOWNLOAD_CERTS" = "Y" ]; then
            echo ""
            print_info "启动证书下载脚本..."
            echo ""
            
            # 调用证书下载脚本
            if [ -f "$SCRIPT_DIR/download-certs.sh" ]; then
                "$SCRIPT_DIR/download-certs.sh"
                
                # 重新检查证书文件
                if check_certificates_simple; then
                    echo ""
                    print_info "证书文件已成功下载"
                fi
            else
                print_error "证书下载脚本不存在: $SCRIPT_DIR/download-certs.sh"
                print_info "请手动下载证书文件"
            fi
        else
            echo ""
            print_info "跳过证书下载"
            echo ""
            print_warn "您可以在获取证书文件后重新运行客户端"
            echo ""
            print_info "获取证书后，使用以下命令启动客户端："
            echo "  $INSTALL_DIR/start.sh"
            echo ""
        fi
    else
        echo ""
        print_info "所有证书文件已存在"
        echo ""
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
    echo -e "${BLUE}管理脚本:${NC}"
    echo "   $INSTALL_DIR/start.sh    - 启动客户端"
    echo "   $INSTALL_DIR/stop.sh     - 停止客户端"
    echo "   $INSTALL_DIR/status.sh   - 查看状态"
    echo ""
    
    # 检查 systemd 服务是否已安装
    if [ -f "/etc/systemd/system/smtp-tunnel-client.service" ]; then
        echo -e "${BLUE}systemd 服务:${NC}"
        echo "   服务名称: smtp-tunnel-client"
        echo "   服务文件: /etc/systemd/system/smtp-tunnel-client.service"
        echo ""
        echo -e "${BLUE}systemd 命令:${NC}"
        echo "   sudo systemctl start smtp-tunnel-client    - 启动服务"
        echo "   sudo systemctl stop smtp-tunnel-client     - 停止服务"
        echo "   sudo systemctl restart smtp-tunnel-client  - 重启服务"
        echo "   sudo systemctl status smtp-tunnel-client   - 查看状态"
        echo "   sudo systemctl enable smtp-tunnel-client   - 开机自启"
        echo "   sudo systemctl disable smtp-tunnel-client  - 禁用开机自启"
        echo ""
        echo -e "${BLUE}查看日志:${NC}"
        echo "   sudo journalctl -u smtp-tunnel-client -f  - 实时日志"
        echo "   sudo journalctl -u smtp-tunnel-client -n 100 - 最近 100 条"
        echo ""
    fi
    
    echo -e "${BLUE}卸载:${NC}"
    echo "   $INSTALL_DIR/uninstall-client.sh"
    echo ""
    echo -e "${BLUE}快速开始:${NC}"
    if [ -f "/etc/systemd/system/smtp-tunnel-client.service" ]; then
        echo "   1. 编辑配置文件: $INSTALL_DIR/config.yaml"
        echo "   2. 启动服务: sudo systemctl start smtp-tunnel-client"
        echo "   3. 查看状态: sudo systemctl status smtp-tunnel-client"
        echo "   4. 查看日志: sudo journalctl -u smtp-tunnel-client -f"
    else
        echo "   1. 编辑配置文件: $INSTALL_DIR/config.yaml"
        echo "   2. 启动客户端: $INSTALL_DIR/start.sh"
        echo "   3. 查看状态: $INSTALL_DIR/status.sh"
        echo "   4. 查看日志: tail -f $INSTALL_DIR/logs/client.log"
    fi
    echo ""
    echo -e "${YELLOW}提示:${NC}"
    echo "   如果您使用虚拟环境，请先激活虚拟环境："
    echo "     source $VENV_DIR/bin/activate"
    echo ""
    echo -e "${YELLOW}防火墙配置:${NC}"
    echo "   如果需要从其他机器访问 SOCKS5 代理，请开放防火墙端口："
    echo ""
    echo "   Ubuntu/Debian:"
    echo "     sudo ufw allow 1080/tcp"
    echo ""
    echo "   CentOS/RHEL:"
    echo "     sudo firewall-cmd --permanent --add-port=1080/tcp"
    echo "     sudo firewall-cmd --reload"
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
    setup_log_directory
    
    # 交互式设置
    interactive_setup
    
    print_summary
}

# 运行主函数
main
