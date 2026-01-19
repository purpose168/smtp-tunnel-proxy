#!/bin/bash
#
# SMTP 隧道代理 - 服务器安装脚本
#
# 一行命令安装:
#   curl -sSL https://raw.githubusercontent.com/purpose168/smtp-tunnel-proxy/main/install.sh | sudo bash
#
# 版本: 1.3.0

# 输出颜色定义
RED='\033[0;31m'      # 红色
GREEN='\033[0;32m'    # 绿色
YELLOW='\033[1;33m'   # 黄色
BLUE='\033[0;34m'     # 蓝色
CYAN='\033[0;36m'     # 青色
NC='\033[0m'          # 无颜色

# GitHub 原始 URL 基础地址
GITHUB_RAW="https://raw.githubusercontent.com/purpose168/smtp-tunnel-proxy/main"

# 安装目录
INSTALL_DIR="/opt/smtp-tunnel"
CONFIG_DIR="/etc/smtp-tunnel"
BIN_DIR="/usr/local/bin"

# Conda 环境配置
CONDA_ENV_NAME="smtp-tunnel-py312"  # Conda 虚拟环境名称
CONDA_INSTALL_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"
CONDA_INSTALL_DIR="/opt/miniconda3"

# 需要下载的文件
PYTHON_FILES="server.py client.py common.py generate_certs.py"
SCRIPTS="smtp-tunnel-adduser smtp-tunnel-deluser smtp-tunnel-listusers smtp-tunnel-update"

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

# 检查是否以 root 身份运行
check_root() {
    if [ "$EUID" -ne 0 ]; then
        print_error "请以 root 身份运行 (使用 sudo)"
        echo ""
        echo "使用方法: curl -sSL $GITHUB_RAW/install.sh | sudo bash"
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
    print_info "检测到的操作系统: $OS $OS_VERSION"
}

# 安装 Python 和依赖项
install_dependencies() {
    print_step "正在安装系统依赖项..."

    case $OS in
        ubuntu|debian)
            apt-get update -qq
            apt-get install -y -qq python3 python3-pip python3-venv curl
            ;;
        centos|rhel|rocky|alma)
            if command -v dnf &> /dev/null; then
                dnf install -y python3 python3-pip curl
            else
                yum install -y python3 python3-pip curl
            fi
            ;;
        fedora)
            dnf install -y python3 python3-pip curl
            ;;
        arch|manjaro)
            pacman -Sy --noconfirm python python-pip curl
            ;;
        *)
            print_warn "未知的操作系统 '$OS', 假定已安装 Python 3 和 curl"
            ;;
    esac

    # 检查 Python 版本
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        print_info "Python 版本: $PYTHON_VERSION"
    else
        print_error "未找到 Python 3。请安装 Python 3.8+"
        exit 1
    fi
}

# 检查 Conda 是否已正确安装,并设置 CONDA_INSTALL_DIR
check_conda() {
    print_step "正在检查 Conda 安装状态..."

    # 方法 1: 检查 conda 是否为已初始化的 shell 函数
    if declare -f conda > /dev/null 2>&1; then
        # conda 是已初始化的函数,尝试获取安装目录
        local conda_path=$(type -P conda 2>/dev/null || echo "")
        if [ -n "$conda_path" ]; then
            CONDA_INSTALL_DIR=$(dirname "$conda_path")
            CONDA_INSTALL_DIR=$(dirname "$CONDA_INSTALL_DIR")
            print_info "Conda 已安装 (shell 函数): $(conda --version 2>/dev/null || echo 'unknown')"
            print_info "Conda 安装目录: $CONDA_INSTALL_DIR"
            return 0
        fi
    fi

    # 方法 2: 直接查找 conda 可执行文件
    local conda_path=""
    for path in "/home/pps/anaconda3/bin/conda" \
                "$HOME/anaconda3/bin/conda" \
                "$HOME/miniconda3/bin/conda" \
                "/opt/anaconda3/bin/conda" \
                "/opt/miniconda3/bin/conda" \
                "/usr/local/anaconda3/bin/conda" \
                "/usr/local/miniconda3/bin/conda"; do
        if [ -f "$path" ]; then
            conda_path="$path"
            break
        fi
    done

    # 如果没找到,尝试 which 命令
    if [ -z "$conda_path" ] && command -v conda > /dev/null 2>&1; then
        conda_path=$(which conda 2>/dev/null)
    fi

    if [ -n "$conda_path" ] && [ -f "$conda_path" ]; then
        CONDA_INSTALL_DIR=$(dirname "$conda_path")
        CONDA_INSTALL_DIR=$(dirname "$CONDA_INSTALL_DIR")
        export PATH="$CONDA_INSTALL_DIR/bin:$PATH"
        source "$CONDA_INSTALL_DIR/etc/profile.d/conda.sh" 2>/dev/null || true
        print_info "Conda 已安装: $(conda --version 2>/dev/null || echo 'unknown')"
        print_info "Conda 安装目录: $CONDA_INSTALL_DIR"
        return 0
    fi

    print_warn "未检测到 Conda 安装"
    return 1
}

# 安装 Conda (Miniconda)
install_conda() {
    print_step "正在安装 Miniconda..."

    # 检查是否以 root 身份运行,决定安装位置
    if [ "$EUID" -eq 0 ]; then
        # root 用户安装到系统目录
        local install_script="/tmp/miniconda_install.sh"
        CONDA_INSTALL_DIR="/opt/miniconda3"
    else
        # 普通用户安装到用户主目录
        local install_script="$HOME/miniconda_install.sh"
        CONDA_INSTALL_DIR="$HOME/miniconda3"
    fi

    local conda_bin="$CONDA_INSTALL_DIR/bin/conda"

    # 下载 Miniconda 安装脚本
    print_info "正在下载 Miniconda 安装脚本..."
    if ! curl -sSL -f "$CONDA_INSTALL_URL" -o "$install_script" 2>/dev/null; then
        print_error "下载 Miniconda 安装脚本失败"
        return 1
    fi

    # 运行安装脚本 (静默模式)
    print_info "正在运行安装程序..."
    bash "$install_script" -b -p "$CONDA_INSTALL_DIR" 2>/dev/null

    # 检查安装结果
    if [ -f "$conda_bin" ]; then
        print_info "Conda 安装成功: $CONDA_INSTALL_DIR"
        # 配置环境变量
        export PATH="$CONDA_INSTALL_DIR/bin:$PATH"
        source "$CONDA_INSTALL_DIR/etc/profile.d/conda.sh" 2>/dev/null || true
        return 0
    else
        print_error "Conda 安装失败"
        rm -f "$install_script"
        return 1
    fi
}

# 创建 Python 3.12 Conda 虚拟环境
create_conda_env() {
    print_step "正在创建 Conda 虚拟环境: $CONDA_ENV_NAME (Python 3.12)..."

    # 重新检查并设置 CONDA_INSTALL_DIR (确保使用正确的值)
    check_conda 2>/dev/null

    # 确保 Conda 命令可用
    if ! command -v conda > /dev/null 2>&1 && ! declare -f conda > /dev/null 2>&1; then
        print_error "Conda 命令不可用,请先安装 Conda"
        return 1
    fi

    # 初始化 conda shell 集成 (如果需要)
    if [ -f "$CONDA_INSTALL_DIR/etc/profile.d/conda.sh" ]; then
        source "$CONDA_INSTALL_DIR/etc/profile.d/conda.sh" 2>/dev/null || true
    fi

    # 验证环境目录 (使用 conda env list 命令的输出)
    local env_exists=false
    if conda env list 2>/dev/null | grep -q "^$CONDA_ENV_NAME "; then
        env_exists=true
    elif [ -d "$CONDA_INSTALL_DIR/envs/$CONDA_ENV_NAME" ]; then
        env_exists=true
    fi

    if [ "$env_exists" = true ]; then
        print_info "环境 '$CONDA_ENV_NAME' 已存在"
        return 0
    fi

    # 创建新环境
    print_info "正在创建环境,这可能需要几分钟..."
    local create_output
    
    # 首先尝试默认通道
    if create_output=$(conda create -n "$CONDA_ENV_NAME" python=3.12 -y 2>&1); then
        print_info "环境 '$CONDA_ENV_NAME' 创建成功"
        if [ -d "$CONDA_INSTALL_DIR/envs/$CONDA_ENV_NAME" ]; then
            print_info "环境目录: $CONDA_INSTALL_DIR/envs/$CONDA_ENV_NAME"
            return 0
        else
            print_warn "环境创建命令成功,但目录未找到"
            return 1
        fi
    fi
    
    # 检查是否是服务条款问题
    if echo "$create_output" | grep -qi "Terms of Service"; then
        print_warn "检测到 Anaconda 服务条款限制,正在自动接受服务条款..."
        
        # 自动接受 Anaconda 服务条款
        print_info "正在接受 Anaconda 服务条款..."
        conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main 2>/dev/null || true
        conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r 2>/dev/null || true
        
        # 再次尝试创建环境
        print_info "正在重新创建环境..."
        if create_output=$(conda create -n "$CONDA_ENV_NAME" python=3.12 -y 2>&1); then
            print_info "环境 '$CONDA_ENV_NAME' 创建成功"
            if [ -d "$CONDA_INSTALL_DIR/envs/$CONDA_ENV_NAME" ]; then
                print_info "环境目录: $CONDA_INSTALL_DIR/envs/$CONDA_ENV_NAME"
                return 0
            else
                print_warn "环境创建命令成功,但目录未找到"
                return 1
            fi
        fi
    fi
    
    # 所有尝试都失败
    print_error "环境 '$CONDA_ENV_NAME' 创建失败"
    echo "$create_output" | head -n 10
    return 1
}

# 激活 Conda 虚拟环境并配置环境变量
activate_conda_env() {
    print_step "正在激活 Conda 虚拟环境: $CONDA_ENV_NAME..."

    # 重新检查并设置 CONDA_INSTALL_DIR (确保使用正确的值)
    check_conda 2>/dev/null

    # 确保 Conda 命令可用
    if ! command -v conda > /dev/null 2>&1 && ! declare -f conda > /dev/null 2>&1; then
        print_error "无法找到 Conda 安装"
        return 1
    fi

    # 初始化 conda shell 集成 (如果需要)
    if [ -f "$CONDA_INSTALL_DIR/etc/profile.d/conda.sh" ]; then
        source "$CONDA_INSTALL_DIR/etc/profile.d/conda.sh" 2>/dev/null || true
    fi

    # 检查环境是否存在 (使用 conda env list 命令验证)
    local env_exists=false
    if conda env list 2>/dev/null | grep -q "^$CONDA_ENV_NAME "; then
        env_exists=true
    elif [ -d "$CONDA_INSTALL_DIR/envs/$CONDA_ENV_NAME" ]; then
        env_exists=true
    fi

    if [ "$env_exists" = false ]; then
        print_error "环境 '$CONDA_ENV_NAME' 不存在,请先创建"
        print_info "可用环境: $(conda env list 2>/dev/null | grep -v '^#' | grep -v '^$' | awk '{print $1}' | tr '\n' ', ')"
        return 1
    fi

    # 激活环境 (使用 __conda_exe 直接调用,避免依赖 shell 函数)
    local conda_activate_cmd="$CONDA_INSTALL_DIR/bin/conda activate $CONDA_ENV_NAME 2>/dev/null"
    eval "$($CONDA_INSTALL_DIR/bin/conda shell.bash hook 2>/dev/null)"
    conda activate "$CONDA_ENV_NAME" 2>/dev/null || source "$CONDA_INSTALL_DIR/bin/activate" "$CONDA_ENV_NAME" 2>/dev/null || true

    # 验证 Python 版本 (使用 Conda 环境的 Python)
    local python_path="$CONDA_INSTALL_DIR/envs/$CONDA_ENV_NAME/bin/python"
    if [ -f "$python_path" ]; then
        local py_version=$("$python_path" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)
        if [ "$py_version" = "3.12" ]; then
            print_info "已激活 Python $py_version 环境"
            print_info "Python 路径: $python_path"
            return 0
        else
            print_warn "Python 版本不是 3.12: $py_version"
            return 1
        fi
    else
        print_error "无法找到 Python 解释器: $python_path"
        return 1
    fi
}

# 使用 Conda 环境中的 Python 安装包
conda_install_packages() {
    print_step "正在使用 Conda 环境安装 Python 包..."

    # 确保环境已激活
    if ! command -v python &> /dev/null || ! python -c 'import sys; sys.exit(0 if sys.version_info.major == 3 and sys.version_info.minor == 12 else 1)' 2>/dev/null; then
        print_error "Conda 环境未正确激活,请确保已激活 $CONDA_ENV_NAME"
        return 1
    fi

    # 使用 pip 安装依赖 (Conda 环境中的 pip)
    local pip_path=$(which pip 2>/dev/null || echo "$CONDA_INSTALL_DIR/envs/$CONDA_ENV_NAME/bin/pip")
    
    if [ -f "$pip_path" ]; then
        print_info "使用 pip: $pip_path"
        "$pip_path" install -q -r "$INSTALL_DIR/requirements.txt" 2>/dev/null || \
        "$pip_path" install -r "$INSTALL_DIR/requirements.txt"
        print_info "Python 包已安装"
        return 0
    else
        print_error "未找到 pip 路径"
        return 1
    fi
}

# 创建 Conda 环境卸载脚本
create_conda_uninstall_script() {
    # 确保目录存在
    if [ ! -d "$INSTALL_DIR" ]; then
        print_error "安装目录不存在: $INSTALL_DIR"
        return 1
    fi

    local uninstall_script="$INSTALL_DIR/uninstall_conda_env.sh"
    
    cat > "$uninstall_script" << EOF
#!/bin/bash
# Conda 虚拟环境卸载脚本

echo "正在卸载 Conda 虚拟环境: $CONDA_ENV_NAME..."

# 检查 Conda 是否可用
if command -v conda &> /dev/null; then
    conda env remove -n "$CONDA_ENV_NAME" -y
    echo "环境 '$CONDA_ENV_NAME' 已删除"
else
    echo "Conda 不可用,无法删除环境"
fi

echo ""
echo "如需完全卸载 Conda,请手动删除: $CONDA_INSTALL_DIR"
EOF

    chmod +x "$uninstall_script"
    print_info "已创建: $uninstall_script"
}

# 创建目录
create_directories() {
    print_step "正在创建目录..."

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

    if curl -sSL -f "$url" -o "$destination" 2>/dev/null; then
        print_info "  已下载: $filename"
        return 0
    else
        print_error "  下载失败: $filename"
        return 1
    fi
}

# 下载并安装文件
install_files() {
    print_step "正在从 GitHub 下载文件..."

    # 下载 Python 文件到安装目录
    for file in $PYTHON_FILES; do
        if ! download_file "$file" "$INSTALL_DIR/$file"; then
            print_error "下载所需文件失败: $file"
            exit 1
        fi
    done

    # 下载并安装管理脚本
    for script in $SCRIPTS; do
        if ! download_file "$script" "$INSTALL_DIR/$script"; then
            print_error "下载所需脚本失败: $script"
            exit 1
        fi
        chmod +x "$INSTALL_DIR/$script"
        # 在 bin 目录中创建符号链接
        ln -sf "$INSTALL_DIR/$script" "$BIN_DIR/$script"
        print_info "  已链接: $script -> $BIN_DIR/$script"
    done

    # 下载配置模板
    download_file "config.yaml" "$INSTALL_DIR/config.yaml.template" || true

    # 下载用户模板
    download_file "users.yaml" "$INSTALL_DIR/users.yaml.template" || true

    # 下载 requirements.txt
    if ! download_file "requirements.txt" "$INSTALL_DIR/requirements.txt"; then
        print_error "下载 requirements.txt 失败"
        exit 1
    fi
}

# 安装 Python 包
install_python_packages() {
    print_step "正在安装 Python 包..."

    pip3 install --root-user-action=ignore -q -r "$INSTALL_DIR/requirements.txt" 2>/dev/null || \
    pip3 install -q -r "$INSTALL_DIR/requirements.txt"

    print_info "Python 包已安装"
}

# 创建 systemd 服务
install_systemd_service() {
    print_step "正在安装 systemd 服务..."

    cat > /etc/systemd/system/smtp-tunnel.service << EOF
[Unit]
Description=SMTP Tunnel Proxy Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/server.py -c $CONFIG_DIR/config.yaml
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

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

echo "正在停止服务..."
systemctl stop smtp-tunnel 2>/dev/null || true
systemctl disable smtp-tunnel 2>/dev/null || true

echo "正在删除文件..."
rm -f /etc/systemd/system/smtp-tunnel.service
rm -f /usr/local/bin/smtp-tunnel-adduser
rm -f /usr/local/bin/smtp-tunnel-deluser
rm -f /usr/local/bin/smtp-tunnel-listusers
rm -rf /opt/smtp-tunnel

echo ""
echo "注意: /etc/smtp-tunnel 中的配置未被删除"
echo "如需手动删除: rm -rf /etc/smtp-tunnel"

systemctl daemon-reload

echo ""
echo "SMTP Tunnel Proxy 卸载成功"
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

    # 询问主机名
    print_ask "请输入您的域名 (例如: myserver.duckdns.org):"
    echo -e "    ${YELLOW}提示: 在 duckdns.org, noip.com 或 freedns.afraid.org 获取免费域名${NC}"
    echo ""
    read -p "    域名: " DOMAIN_NAME < /dev/tty

    if [ -z "$DOMAIN_NAME" ]; then
        print_error "域名是必需的!"
        exit 1
    fi

    print_info "使用的域名: $DOMAIN_NAME"
    echo ""

    # 使用域名创建 config.yaml
    print_step "正在创建配置..."

    cat > "$CONFIG_DIR/config.yaml" << EOF
# SMTP Tunnel Proxy Configuration
# Generated by install.sh

server:
  host: "0.0.0.0"
  port: 587
  hostname: "$DOMAIN_NAME"
  cert_file: "$CONFIG_DIR/server.crt"
  key_file: "$CONFIG_DIR/server.key"
  users_file: "$CONFIG_DIR/users.yaml"
  log_users: true

client:
  server_host: "$DOMAIN_NAME"
  server_port: 587
  socks_port: 1080
  socks_host: "127.0.0.1"
  ca_cert: "ca.crt"
EOF

    chmod 600 "$CONFIG_DIR/config.yaml"
    print_info "已创建: $CONFIG_DIR/config.yaml"

    # 创建空的 users.yaml
    cat > "$CONFIG_DIR/users.yaml" << 'EOF'
# SMTP Tunnel Users
# Managed by smtp-tunnel-adduser

users: {}
EOF

    chmod 600 "$CONFIG_DIR/users.yaml"
    print_info "已创建: $CONFIG_DIR/users.yaml"

    # 生成证书
    echo ""
    print_step "正在为 $DOMAIN_NAME 生成 TLS 证书..."

    cd "$INSTALL_DIR"
    if python3 generate_certs.py --hostname "$DOMAIN_NAME" --output-dir "$CONFIG_DIR"; then
        print_info "证书生成成功"
        # 创建符号链接以便 adduser 脚本可以找到 ca.crt
        ln -sf "$CONFIG_DIR/ca.crt" "$INSTALL_DIR/ca.crt"
    else
        print_error "证书生成失败。您可以手动尝试:"
        echo "    cd $INSTALL_DIR"
        echo "    python3 generate_certs.py --hostname $DOMAIN_NAME --output-dir $CONFIG_DIR"
    fi

    # 询问是否创建第一个用户
    echo ""
    print_ask "您现在想创建第一个用户吗? [Y/n]: "
    read -p "    " CREATE_USER < /dev/tty

    if [ -z "$CREATE_USER" ] || [ "$CREATE_USER" = "y" ] || [ "$CREATE_USER" = "Y" ]; then
        echo ""
        print_ask "请输入第一个用户的用户名:"
        read -p "    用户名: " FIRST_USER < /dev/tty

        if [ -n "$FIRST_USER" ]; then
            echo ""
            print_step "正在创建用户 '$FIRST_USER'..."

            cd "$INSTALL_DIR"
            if python3 smtp-tunnel-adduser "$FIRST_USER"; then
                echo ""
                print_info "用户 '$FIRST_USER' 创建成功!"
                print_info "客户端包: $INSTALL_DIR/${FIRST_USER}.zip"
                echo ""
                echo -e "    ${YELLOW}将此 ZIP 文件发送给用户 - 它包含连接所需的一切!${NC}"
            else
                print_warn "创建用户失败。您可以稍后创建用户:"
                echo "    smtp-tunnel-adduser <username>"
            fi
        else
            print_warn "未提供用户名。您可以稍后创建用户:"
            echo "    smtp-tunnel-adduser <username>"
        fi
    else
        echo ""
        print_info "跳过用户创建。"
        echo "    您可以稍后创建用户: smtp-tunnel-adduser <username>"
    fi

    # 打开防火墙
    echo ""
    print_step "正在配置防火墙..."

    if command -v ufw &> /dev/null; then
        if ufw allow 587/tcp >/dev/null 2>&1; then
            print_info "已打开端口 587/tcp (ufw)"
        else
            print_warn "无法配置 ufw。请确保端口 587/tcp 已打开!"
        fi
    elif command -v firewall-cmd &> /dev/null; then
        if firewall-cmd --permanent --add-port=587/tcp >/dev/null 2>&1 && firewall-cmd --reload >/dev/null 2>&1; then
            print_info "已打开端口 587/tcp (firewalld)"
        else
            print_warn "无法配置 firewalld。请确保端口 587/tcp 已打开!"
        fi
    else
        print_warn "未检测到防火墙。请确保端口 587/tcp 已打开!"
    fi

    # 启用并启动服务
    echo ""
    print_step "正在启动 SMTP Tunnel 服务..."

    systemctl enable smtp-tunnel >/dev/null 2>&1 || true
    systemctl start smtp-tunnel 2>&1 || true

    sleep 2

    if systemctl is-active --quiet smtp-tunnel; then
        print_info "服务启动成功!"
    else
        print_warn "服务可能未启动。请检查:"
        echo "    systemctl status smtp-tunnel"
        echo "    journalctl -u smtp-tunnel -n 50"
    fi
}

# 打印最终摘要
print_summary() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  安装完成!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "您的 SMTP Tunnel Proxy 现在正在运行!"
    echo ""
    echo -e "${BLUE}服务状态:${NC}"
    echo "   systemctl status smtp-tunnel"
    echo ""
    echo -e "${BLUE}查看日志:${NC}"
    echo "   journalctl -u smtp-tunnel -f"
    echo ""
    echo -e "${BLUE}用户管理:${NC}"
    echo "   smtp-tunnel-adduser <username>    添加用户 + 生成客户端 ZIP"
    echo "   smtp-tunnel-deluser <username>    删除用户"
    echo "   smtp-tunnel-listusers             列出所有用户"
    echo ""
    echo -e "${BLUE}配置文件:${NC}"
    echo "   $CONFIG_DIR/config.yaml"
    echo "   $CONFIG_DIR/users.yaml"
    echo ""
    echo -e "${BLUE}卸载方法:${NC}"
    echo "   $INSTALL_DIR/uninstall.sh"
    echo ""
}

# 主安装流程
main() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  SMTP Tunnel Proxy 安装程序${NC}"
    echo -e "${GREEN}  版本 1.2.0${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""

    check_root
    detect_os
    install_dependencies

    # Conda 虚拟环境设置 (可选功能)
    echo ""
    echo -e "${CYAN}[?]${NC} 是否使用 Conda 虚拟环境运行服务端? [Y/n]"
    echo "    提示: 使用 Conda 可以确保 Python 3.12 环境隔离,避免依赖冲突"
    read -p "    " USE_CONDA < /dev/tty

    if [ -z "$USE_CONDA" ] || [ "$USE_CONDA" = "y" ] || [ "$USE_CONDA" = "Y" ]; then
        print_info "将使用 Conda 管理 Python 环境"

        # 检查 Conda 是否已安装
        if ! check_conda; then
            echo ""
            print_ask "Conda 未安装,是否自动安装 Miniconda? [Y/n]: "
            read -p "    " INSTALL_CONDA < /dev/tty

            if [ -z "$INSTALL_CONDA" ] || [ "$INSTALL_CONDA" = "y" ] || [ "$INSTALL_CONDA" = "Y" ]; then
                if ! install_conda; then
                    print_warn "Conda 安装失败,将使用系统 Python 继续安装"
                fi
            else
                print_warn "跳过 Conda 安装,将使用系统 Python"
            fi
        fi

        # 创建 Conda 环境
        if check_conda 2>/dev/null; then
            if ! create_conda_env; then
                print_warn "Conda 环境创建失败,将使用系统 Python"
            else
                # 激活 Conda 环境
                if activate_conda_env; then
                    # 标记需要创建 Conda 环境卸载脚本
                    CREATE_CONDA_UNINSTALL_SCRIPT=true
                else
                    print_warn "无法激活 Conda 环境,将使用系统 Python"
                fi
            fi
        fi
    else
        print_info "将使用系统 Python 环境"
    fi

    create_directories
    install_files

    # 根据是否使用 Conda 环境选择不同的包安装方式
    if command -v python &> /dev/null && python -c 'import sys; sys.exit(0 if sys.version_info.major == 3 and sys.version_info.minor == 12 else 1)' 2>/dev/null; then
        print_info "检测到 Python 3.12 环境,使用 Conda 环境安装包"
        conda_install_packages
    else
        install_python_packages
    fi

    install_systemd_service
    create_uninstall_script
    
    # 在目录创建后创建 Conda 环境卸载脚本
    if [ "$CREATE_CONDA_UNINSTALL_SCRIPT" = true ]; then
        create_conda_uninstall_script
    fi
    interactive_setup
    print_summary
}

# 运行主函数
main "$@"
