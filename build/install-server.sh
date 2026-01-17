#!/bin/bash
#
# SMTP 隧道代理 - 服务器安装脚本
#
# 一行命令安装:
#   curl -sSL https://raw.githubusercontent.com/purpose168/smtp-tunnel-proxy/main/install-server.sh | sudo bash
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

# 安装目录（使用系统级 /opt 目录）
INSTALL_DIR="/opt/smtp-tunnel"           # 程序安装目录
CONFIG_DIR="/opt/smtp-tunnel/config"      # 配置文件目录
VENV_DIR="/opt/smtp-tunnel/venv"         # Python 虚拟环境目录
LOG_DIR="/opt/smtp-tunnel/logs"           # 日志目录

# BIN_DIR 保持系统级目录不变
BIN_DIR="/usr/local/bin"            # 可执行文件目录

# 日志文件
LOG_FILE="$LOG_DIR/install.log"

# logrotate 配置文件
LOGROTATE_CONF="$CONFIG_DIR/logrotate.conf"

# 需要下载的 Python 文件
# 主入口文件
MAIN_FILES="server.py common.py generate_certs.py connection.py"

# 从 common.py 拆分出的模块（服务器需要的）
COMMON_MODULES="protocol/__init__.py protocol/core.py protocol/server.py tunnel/__init__.py tunnel/crypto.py tunnel/base.py tunnel/session.py tunnel/server.py connection.py config.py logger.py"

# 从 server.py 拆分出的模块
SERVER_MODULES="tunnel/server.py"   

# 所有 Python 文件
PYTHON_FILES="$MAIN_FILES $COMMON_MODULES $SERVER_MODULES"

# 需要下载的管理脚本
# 包括用户管理和系统更新脚本
SCRIPTS="smtp-tunnel-adduser smtp-tunnel-deluser smtp-tunnel-listusers smtp-tunnel-update"

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
        echo "使用方法: curl -sSL $GITHUB_RAW/install-server.sh | sudo bash"
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
            apt-get install -y -qq python3 python3-pip python3-venv python3-dev curl
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
    
    # 先创建日志目录（确保日志文件可以写入）
    mkdir -p "$LOG_DIR"
    chmod 755 "$LOG_DIR"
    
    # 创建日志文件（确保存在）
    touch "$LOG_FILE"
    chmod 644 "$LOG_FILE"
    
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$CONFIG_DIR"
    
    chmod 755 "$INSTALL_DIR"
    chmod 700 "$CONFIG_DIR"
    chmod 755 "$LOG_DIR"
    
    print_info "已创建: $INSTALL_DIR"
    print_info "已创建: $CONFIG_DIR"
    print_info "已创建: $LOG_DIR"
    print_info "已创建: $LOG_FILE"
}

# 设置日志目录权限
setup_log_directory() {
    print_step "设置日志目录权限..."
    
    if [ -d "$LOG_DIR" ]; then
        chmod 755 "$LOG_DIR"
        chown root:root "$LOG_DIR"
        print_info "日志目录权限已设置: $LOG_DIR"
    else
        print_error "日志目录不存在: $LOG_DIR"
        return 1
    fi
}

# 安装 logrotate 配置
install_logrotate() {
    print_step "安装 logrotate 配置..."
    
    cat > "$LOGROTATE_CONF" << 'EOF'
$LOG_DIR/*.log {
    daily
    rotate 10
    compress
    delaycompress
    missingok
    notifempty
    create 0640 root root
    sharedscripts
    postrotate
        systemctl reload smtp-tunnel >/dev/null 2>&1 || true
    endscript
}
EOF
    
    chmod 644 "$LOGROTATE_CONF"
    print_info "已安装: $LOGROTATE_CONF"
}

# ============================================================================
# 从 GitHub 下载文件（增强版）
# ============================================================================
# 功能说明：
# 1. 安全可靠的文件下载机制
# 2. 自动重试机制（最多3次）
# 3. 下载进度显示
# 4. 文件完整性校验（检查文件大小）
# 5. 详细的日志记录
# 6. 错误处理和回滚机制
#
# 参数说明：
#   $1 - filename: 要下载的文件名（相对路径）
#   $2 - destination: 目标文件路径（绝对路径）
#
# 返回值：
#   0 - 下载成功
#   1 - 下载失败
#
# 使用示例：
#   download_file "server.py" "/opt/smtp-tunnel/server.py"
# ============================================================================
download_file() {
    local filename=$1
    local destination=$2
    local url="$GITHUB_RAW/$filename"
    
    # 记录下载开始信息
    log_step "正在下载: $filename"
    log_info "  源 URL: $url"
    log_info "  目标路径: $destination"
    
    # 安全检查：验证 URL 合法性
    if [[ ! "$url" =~ ^https://raw\.githubusercontent\.com/purpose168/smtp-tunnel-proxy/main/ ]]; then
        log_error "  URL 安全检查失败：不合法的源地址"
        return 1
    fi
    
    # 先删除目标文件（如果存在）
    if [ -f "$destination" ]; then
        log_info "  目标文件已存在，正在删除旧版本"
        rm -f "$destination"
    fi
    
    # 创建目标目录（如果不存在）
    local dest_dir=$(dirname "$destination")
    if [ ! -d "$dest_dir" ]; then
        log_info "  创建目标目录: $dest_dir"
        mkdir -p "$dest_dir"
        if [ $? -ne 0 ]; then
            log_error "  创建目录失败: $dest_dir"
            return 1
        fi
    fi
    
    # 检查目录写权限
    if [ ! -w "$dest_dir" ]; then
        log_error "  目标目录无写权限: $dest_dir"
        return 1
    fi
    
    # 下载配置参数
    local retry_count=0
    local max_retries=3
    local retry_delay=2
    local temp_file="${destination}.tmp"
    local download_success=false
    
    # 下载重试循环
    while [ $retry_count -lt $max_retries ]; do
        retry_count=$((retry_count + 1))
        
        # 显示下载进度信息
        if [ $retry_count -gt 1 ]; then
            log_info "  第 $retry_count 次尝试下载..."
        fi
        
        # 使用 curl 下载文件（显示进度条）
        # 参数说明：
        #   -s: 静默模式（不显示进度条）
        #   -S: 显示错误信息
        #   -L: 跟随重定向
        #   -f: HTTP 错误时失败（404, 500等）
        #   -#: 显示进度条
        #   --connect-timeout 30: 连接超时30秒
        #   --max-time 300: 最大下载时间300秒
        #   --retry 2: curl 内部重试2次
        #   --retry-delay 1: 重试延迟1秒
        if curl -sSL -f --connect-timeout 30 --max-time 300 --retry 2 --retry-delay 1 \
            "$url" -o "$temp_file" 2>&1 | while read line; do
                log_info "  $line"
            done; then
            
            # 下载成功，检查文件完整性
            if [ -f "$temp_file" ] && [ -s "$temp_file" ]; then
                local file_size=$(stat -c%s "$temp_file" 2>/dev/null || stat -f%z "$temp_file" 2>/dev/null)
                
                # 检查文件大小是否合理（至少10字节，避免空文件）
                if [ "$file_size" -lt 10 ]; then
                    log_warn "  文件大小异常: $file_size 字节，可能下载不完整"
                    rm -f "$temp_file"
                    continue
                fi
                
                # 文件完整性检查通过，重命名为正式文件名
                mv "$temp_file" "$destination"
                
                # 设置文件权限
                chmod 644 "$destination"
                
                # 对于脚本文件，添加执行权限
                if [[ "$filename" =~ ^(smtp-tunnel-.*|.*\.sh)$ ]]; then
                    chmod +x "$destination"
                fi
                
                log_info "  下载成功: $filename ($file_size 字节)"
                download_success=true
                break
            else
                log_warn "  下载的文件为空或不存在"
                rm -f "$temp_file"
            fi
        else
            # 下载失败
            local curl_exit_code=$?
            log_warn "  下载失败 (curl 退出码: $curl_exit_code)"
            rm -f "$temp_file"
        fi
        
        # 如果不是最后一次尝试，则等待后重试
        if [ $retry_count -lt $max_retries ]; then
            log_info "  等待 $retry_delay 秒后重试..."
            sleep $retry_delay
        fi
    done
    
    # 清理临时文件
    if [ -f "$temp_file" ]; then
        rm -f "$temp_file"
    fi
    
    # 检查最终结果
    if [ "$download_success" = true ]; then
        # 最终验证文件是否存在且可读
        if [ -f "$destination" ] && [ -r "$destination" ]; then
            return 0
        else
            log_error "  文件下载后验证失败: $destination"
            return 1
        fi
    else
        log_error "  下载失败: $filename（已重试 $max_retries 次）"
        log_error "  可能的原因："
        log_error "    1. 网络连接问题"
        log_error "    2. GitHub 服务暂时不可用"
        log_error "    3. 文件不存在或已被删除"
        log_error "    4. URL 地址错误: $url"
        log_error "  建议解决方案："
        log_error "    1. 检查网络连接"
        log_error "    2. 稍后重试"
        log_error "    3. 访问 $GITHUB_RAW 确认文件存在"
        return 1
    fi
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
    
    # 下载并安装管理脚本
    for script in $SCRIPTS; do
        if ! download_file "$script" "$INSTALL_DIR/$script"; then
            print_error "下载必需脚本失败: $script"
            exit 1
        fi
        chmod +x "$INSTALL_DIR/$script"
        # 在 bin 目录创建符号链接
        ln -sf "$INSTALL_DIR/$script" "$BIN_DIR/$script"
        print_info "  已链接: $script -> $BIN_DIR/$script"
    done
    
    # 下载配置模板
    download_file "config.yaml" "$INSTALL_DIR/config.yaml.template" || true
    download_file "users.yaml" "$INSTALL_DIR/users.yaml.template" || true
    
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
    $VENV_DIR/bin/pip install --upgrade pip
    
    # 安装 Python 包
    print_info "安装依赖包..."
    if $VENV_DIR/bin/pip install -r "$INSTALL_DIR/requirements.txt"; then
        print_info "Python 包安装成功"
        
        # 显示已安装的包
        print_info "已安装的包:"
        $VENV_DIR/bin/pip list --format=columns | grep -E "(cryptography|pyyaml)" || true
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

# 生成 TLS 证书
generate_certificates() {
    print_step "生成 TLS 证书..."
    
    cd "$INSTALL_DIR"
    
    # 检查配置文件是否存在
    if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
        print_error "配置文件不存在: $CONFIG_DIR/config.yaml"
        print_error "请先运行交互式配置或手动创建配置文件"
        return 1
    fi
    
    # 从配置文件读取主机名
    HOSTNAME=$(grep -E "^hostname:" "$CONFIG_DIR/config.yaml" | awk '{print $2}' | tr -d '"')
    
    if [ -z "$HOSTNAME" ]; then
        print_error "无法从配置文件读取主机名"
        return 1
    fi
    
    print_info "为主机名生成证书: $HOSTNAME"
    
    # 生成证书
    if python3 generate_certs.py --hostname "$HOSTNAME" --output-dir "$CONFIG_DIR"; then
        print_info "证书生成成功"
        
        # 创建符号链接以便 adduser 脚本可以找到 ca.crt
        # 只有当配置目录和安装目录不同时才创建符号链接
        if [ "$CONFIG_DIR" != "$INSTALL_DIR" ]; then
            ln -sf "$CONFIG_DIR/ca.crt" "$INSTALL_DIR/ca.crt"
        fi
        return 0
    else
        print_error "证书生成失败。您可以手动尝试:"
        echo "    cd $INSTALL_DIR"
        echo "    python3 generate_certs.py --hostname $HOSTNAME --output-dir $CONFIG_DIR"
        return 1
    fi
}

# 创建 systemd 服务
install_systemd_service() {
    print_step "安装 systemd 服务..."
    
    cat > /etc/systemd/system/smtp-tunnel.service << EOF
[Unit]
Description=SMTP 隧道代理服务器
Documentation=https://github.com/purpose168/smtp-tunnel-proxy
After=network.target
RequiresMountsFor=$INSTALL_DIR
RequiresMountsFor=$CONFIG_DIR

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$VENV_DIR/bin/python $INSTALL_DIR/server.py -c $CONFIG_DIR/config.yaml
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

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

# 日志轮转配置
# 日志文件将在达到大小时自动轮转
# 使用logrotate进行日志管理
# 配置文件位于: $CONFIG_DIR/logrotate.conf

# 私有临时目录
PrivateTmp=true

# 网络绑定能力
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
EOF
    
    systemctl daemon-reload
    print_info "服务已安装: smtp-tunnel.service"
}

# 创建卸载脚本
create_uninstall_script() {
    cat > "$INSTALL_DIR/uninstall.sh" << 'EOF'
#!/bin/bash
# SMTP 隧道代理 - 卸载脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "正在停止服务..."
systemctl stop smtp-tunnel 2>/dev/null || true
systemctl disable smtp-tunnel 2>/dev/null || true

echo "正在删除文件..."
rm -f /etc/systemd/system/smtp-tunnel.service
rm -f /usr/local/bin/smtp-tunnel-adduser
rm -f /usr/local/bin/smtp-tunnel-deluser
rm -f /usr/local/bin/smtp-tunnel-listusers
rm -rf "$SCRIPT_DIR"

echo ""
echo "SMTP 隧道代理已成功卸载"
EOF
    
    chmod +x "$INSTALL_DIR/uninstall.sh"
    print_info "已创建: $INSTALL_DIR/uninstall.sh"
}

# 交互式设置
interactive_setup() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  交互式设置${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    
    # 询问域名
    print_ask "输入您的域名（例如: myserver.duckdns.org）:"
    echo -e "    ${YELLOW}提示: 可以在 duckdns.org、noip.com 或 freedns.afraid.org 获取免费域名${NC}"
    echo ""
    read -p "    域名: " DOMAIN_NAME < /dev/tty
    
    if [ -z "$DOMAIN_NAME" ]; then
        print_error "域名是必需的！"
        exit 1
    fi
    
    print_info "使用域名: $DOMAIN_NAME"
    echo ""
    
    # 使用域名创建 config.yaml
    print_step "创建配置..."
    
    cat > "$CONFIG_DIR/config.yaml" << EOF
# SMTP 隧道代理配置
# 由 install-server.sh 生成

server:
  host: "0.0.0.0"
  port: 587
  hostname: "$DOMAIN_NAME"
  cert_file: "$CONFIG_DIR/server.crt"
  key_file: "$CONFIG_DIR/server.key"
  users_file: "$CONFIG_DIR/users.yaml"
  log_users: true

  # 流量整形配置（可选，用于增强 DPI 规避效果）
  traffic:
    # 是否启用流量整形（默认: false）
    enabled: false

    # 消息之间的随机延迟范围（毫秒）
    # 模拟人类行为（阅读、思考、输入）
    min_delay: 50
    max_delay: 500

    # 发送虚拟消息的概率（0.0-1.0）
    # 偶尔发送虚拟数据以增加流量随机性
    dummy_probability: 0.1

# 日志配置
logging:
  # 日志级别: DEBUG, INFO, WARNING, ERROR, CRITICAL
  level: "INFO"
  
  # 日志存储目录
  log_dir: "$LOG_DIR"
  
  # 日志文件名
  log_file: "smtp-tunnel.log"
  
  # 单个日志文件最大大小（字节）- 默认 10MB
  max_bytes: 10485760
  
  # 保留的备份文件数量
  backup_count: 10
  
  # 日志轮转类型: size（按大小）, date（按日期）, both（同时按大小和日期）
  rotation_type: "both"
  
  # 是否输出到控制台
  enable_console: false
  
  # 是否输出到文件
  enable_file: true
  
  # 是否输出到系统日志（systemd journal）
  enable_journal: true
  
  # 上下文字段列表
  context_fields:
    - "username"
    - "ip"
    - "session_id"
    - "connection_id"
EOF
    
    chmod 600 "$CONFIG_DIR/config.yaml"
    print_info "已创建: $CONFIG_DIR/config.yaml"
    
    # 创建空的 users.yaml
    cat > "$CONFIG_DIR/users.yaml" << 'EOF'
# SMTP 隧道用户
# 由 smtp-tunnel-adduser 管理

users: {}
EOF
    
    chmod 600 "$CONFIG_DIR/users.yaml"
    print_info "已创建: $CONFIG_DIR/users.yaml"
    
    # 生成证书
    echo ""
    print_step "为 $DOMAIN_NAME 生成 TLS 证书..."
    cd "$INSTALL_DIR"
    if python3 generate_certs.py --hostname "$DOMAIN_NAME" --output-dir "$CONFIG_DIR"; then
        print_info "证书生成成功"
        
        # 创建符号链接以便 adduser 脚本可以找到 ca.crt
        # 只有当配置目录和安装目录不同时才创建符号链接
        if [ "$CONFIG_DIR" != "$INSTALL_DIR" ]; then
            ln -sf "$CONFIG_DIR/ca.crt" "$INSTALL_DIR/ca.crt"
        fi
    else
        print_error "证书生成失败。您可以手动尝试:"
        echo "    cd $INSTALL_DIR"
        echo "    python3 generate_certs.py --hostname $DOMAIN_NAME --output-dir $CONFIG_DIR"
        exit 1
    fi
    
    # 询问是否创建第一个用户
    echo ""
    print_ask "您现在想创建第一个用户吗？[Y/n]: "
    read -p "    " CREATE_USER < /dev/tty
    
    if [ -z "$CREATE_USER" ] || [ "$CREATE_USER" = "y" ] || [ "$CREATE_USER" = "Y" ]; then
        echo ""
        print_ask "输入第一个用户的用户名:"
        read -p "    用户名: " FIRST_USER < /dev/tty
        
        if [ -n "$FIRST_USER" ]; then
            echo ""
            print_step "正在创建用户 '$FIRST_USER'..."
            
            cd "$INSTALL_DIR"
            source "$VENV_DIR/bin/activate"
            
            if python3 smtp-tunnel-adduser "$FIRST_USER"; then
                echo ""
                print_info "用户 '$FIRST_USER' 创建成功！"
                print_info "客户端包: $INSTALL_DIR/${FIRST_USER}.zip"
                echo ""
                echo -e "    ${YELLOW}将此 ZIP 文件发送给用户 - 它包含连接所需的一切！${NC}"
            else
                print_warn "创建用户失败。您可以稍后使用以下命令创建用户:"
                echo "    smtp-tunnel-adduser <username>"
            fi
        else
            print_warn "未提供用户名。您可以稍后使用以下命令创建用户:"
            echo "    smtp-tunnel-adduser <username>"
        fi
    else
        echo ""
        print_info "跳过用户创建。"
        echo "    您可以稍后使用以下命令创建用户: smtp-tunnel-adduser <username>"
    fi
    
    # 打开防火墙
    echo ""
    print_step "配置防火墙..."
    
    if command -v ufw &> /dev/null; then
        if ufw allow 587/tcp >/dev/null 2>&1; then
            print_info "已打开端口 587/tcp (ufw)"
        else
            print_warn "无法配置 ufw。请确保端口 587/tcp 已打开！"
        fi
    elif command -v firewall-cmd &> /dev/null; then
        if firewall-cmd --permanent --add-port=587/tcp >/dev/null 2>&1 && firewall-cmd --reload >/dev/null 2>&1; then
            print_info "已打开端口 587/tcp (firewalld)"
        else
            print_warn "无法配置 firewalld。请确保端口 587/tcp 已打开！"
        fi
    else
        print_warn "未检测到防火墙。请确保端口 587/tcp 已打开！"
    fi
    
    # 启用并启动服务
    echo ""
    print_step "启动 SMTP 隧道服务..."
    
    systemctl enable smtp-tunnel >/dev/null 2>&1 || true
    systemctl start smtp-tunnel 2>&1 || true
    
    sleep 2
    
    if systemctl is-active --quiet smtp-tunnel; then
        print_info "服务启动成功！"
    else
        print_warn "服务可能未启动。请使用以下命令检查:"
        echo "    systemctl status smtp-tunnel"
        echo "    journalctl -u smtp-tunnel -n 50"
    fi
}

# 打印最终摘要
print_summary() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  安装完成！${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "您的 SMTP 隧道代理服务器现在正在运行！"
    echo ""
    echo -e "${BLUE}服务状态:${NC}"
    echo "   systemctl status smtp-tunnel"
    echo ""
    echo -e "${BLUE}查看日志:${NC}"
    echo "   journalctl -u smtp-tunnel -n 50          # systemd 日志"
    echo "   tail -f $LOG_FILE                      # 安装日志"
    echo ""
    echo -e "${BLUE}日志配置:${NC}"
    echo "   日志目录: $LOG_DIR"
    echo "   安装日志: $LOG_FILE"
    echo "   logrotate: $LOGROTATE_CONF"
    echo ""
    echo -e "${BLUE}用户管理:${NC}"
    echo "   smtp-tunnel-adduser <username>    添加用户并生成客户端 ZIP"
    echo "   smtp-tunnel-deluser <username>    删除用户"
    echo "   smtp-tunnel-listusers             列出所有用户"
    echo ""
    echo -e "${BLUE}配置文件:${NC}"
    echo "   $CONFIG_DIR/config.yaml"
    echo "   $CONFIG_DIR/users.yaml"
    echo ""
    echo -e "${BLUE}虚拟环境:${NC}"
    echo "   $VENV_DIR"
    echo ""
    echo -e "${BLUE}卸载:${NC}"
    echo "   $INSTALL_DIR/uninstall.sh"
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
        log_error "虚拟环境不存在: $VENV_DIR"
        return 1
    fi
    
    # 检查服务文件
    if [ ! -f "/etc/systemd/system/smtp-tunnel.service" ]; then
        log_error "服务文件不存在: /etc/systemd/system/smtp-tunnel.service"
        return 1
    fi
    
    log_info "安装验证通过"
    return 0
}

# 回滚安装
rollback_installation() {
    print_step "回滚安装..."
    
    log_warn "正在删除安装的文件..."
    
    # 停止服务
    systemctl stop smtp-tunnel 2>/dev/null || true
    systemctl disable smtp-tunnel 2>/dev/null || true
    
    # 删除安装的文件
    rm -rf "$INSTALL_DIR"
    rm -rf "$CONFIG_DIR"
    rm -rf "$LOG_DIR"
    rm -f "/etc/systemd/system/smtp-tunnel.service"
    rm -f "/etc/logrotate.d/smtp-tunnel"
    rm -f "/usr/local/bin/smtp-tunnel-adduser"
    rm -f "/usr/local/bin/smtp-tunnel-deluser"
    rm -f "/usr/local/bin/smtp-tunnel-listusers"
    
    log_info "回滚完成"
    log_warn "请重新运行安装脚本"
}

# 主安装流程
main() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  SMTP 隧道代理服务器安装程序${NC}"
    echo -e "${GREEN}  版本 1.3.0${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    
    check_root
    detect_os
    install_dependencies
    create_directories
    setup_log_directory
    install_files
    
    # 创建和配置 Python 虚拟环境
    create_venv
    activate_venv
    install_python_packages
    verify_venv
    
    install_systemd_service
    install_logrotate
    create_uninstall_script
    
    # 验证安装
    if ! verify_installation; then
        print_error "安装验证失败，正在回滚..."
        rollback_installation
        exit 1
    fi
    
    interactive_setup
    print_summary
}

# 运行主函数
main
