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
        print_error "Please run as root (use sudo)"
        echo ""
        echo "Usage: curl -sSL $GITHUB_RAW/install.sh | sudo bash"
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
        print_error "Cannot detect OS"
        exit 1
    fi
    print_info "Detected OS: $OS $OS_VERSION"
}

# 安装 Python 和依赖项
install_dependencies() {
    print_step "Installing system dependencies..."

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
            print_warn "Unknown OS '$OS', assuming Python 3 and curl are installed"
            ;;
    esac

    # 检查 Python 版本
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        print_info "Python version: $PYTHON_VERSION"
    else
        print_error "Python 3 not found. Please install Python 3.8+"
        exit 1
    fi
}

# 创建目录
create_directories() {
    print_step "Creating directories..."

    mkdir -p "$INSTALL_DIR"
    mkdir -p "$CONFIG_DIR"

    chmod 755 "$INSTALL_DIR"
    chmod 700 "$CONFIG_DIR"

    print_info "Created: $INSTALL_DIR"
    print_info "Created: $CONFIG_DIR"
}

# 从 GitHub 下载文件
download_file() {
    local filename=$1
    local destination=$2
    local url="$GITHUB_RAW/$filename"

    if curl -sSL -f "$url" -o "$destination" 2>/dev/null; then
        print_info "  Downloaded: $filename"
        return 0
    else
        print_error "  Failed to download: $filename"
        return 1
    fi
}

# 下载并安装文件
install_files() {
    print_step "Downloading files from GitHub..."

    # 下载 Python 文件到安装目录
    for file in $PYTHON_FILES; do
        if ! download_file "$file" "$INSTALL_DIR/$file"; then
            print_error "Failed to download required file: $file"
            exit 1
        fi
    done

    # 下载并安装管理脚本
    for script in $SCRIPTS; do
        if ! download_file "$script" "$INSTALL_DIR/$script"; then
            print_error "Failed to download required script: $script"
            exit 1
        fi
        chmod +x "$INSTALL_DIR/$script"
        # 在 bin 目录中创建符号链接
        ln -sf "$INSTALL_DIR/$script" "$BIN_DIR/$script"
        print_info "  Linked: $script -> $BIN_DIR/$script"
    done

    # 下载配置模板
    download_file "config.yaml" "$INSTALL_DIR/config.yaml.template" || true

    # 下载用户模板
    download_file "users.yaml" "$INSTALL_DIR/users.yaml.template" || true

    # 下载 requirements.txt
    if ! download_file "requirements.txt" "$INSTALL_DIR/requirements.txt"; then
        print_error "Failed to download requirements.txt"
        exit 1
    fi
}

# 安装 Python 包
install_python_packages() {
    print_step "Installing Python packages..."

    pip3 install --root-user-action=ignore -q -r "$INSTALL_DIR/requirements.txt" 2>/dev/null || \
    pip3 install -q -r "$INSTALL_DIR/requirements.txt"

    print_info "Python packages installed"
}

# 创建 systemd 服务
install_systemd_service() {
    print_step "Installing systemd service..."

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
    print_info "Service installed: smtp-tunnel.service"
}

# 创建卸载脚本
create_uninstall_script() {
    cat > "$INSTALL_DIR/uninstall.sh" << 'EOF'
#!/bin/bash
# SMTP 隧道代理 - 卸载脚本

echo "Stopping service..."
systemctl stop smtp-tunnel 2>/dev/null || true
systemctl disable smtp-tunnel 2>/dev/null || true

echo "Removing files..."
rm -f /etc/systemd/system/smtp-tunnel.service
rm -f /usr/local/bin/smtp-tunnel-adduser
rm -f /usr/local/bin/smtp-tunnel-deluser
rm -f /usr/local/bin/smtp-tunnel-listusers
rm -rf /opt/smtp-tunnel

echo ""
echo "Note: Configuration in /etc/smtp-tunnel was NOT removed"
echo "Remove manually if needed: rm -rf /etc/smtp-tunnel"

systemctl daemon-reload

echo ""
echo "SMTP Tunnel Proxy uninstalled successfully"
EOF

    chmod +x "$INSTALL_DIR/uninstall.sh"
    print_info "Created: $INSTALL_DIR/uninstall.sh"
}

# 交互式设置
interactive_setup() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Interactive Setup${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""

    # 询问主机名
    print_ask "Enter your domain name (e.g., myserver.duckdns.org):"
    echo -e "    ${YELLOW}Tip: Get a free domain at duckdns.org, noip.com, or freedns.afraid.org${NC}"
    echo ""
    read -p "    Domain: " DOMAIN_NAME < /dev/tty

    if [ -z "$DOMAIN_NAME" ]; then
        print_error "Domain name is required!"
        exit 1
    fi

    print_info "Using domain: $DOMAIN_NAME"
    echo ""

    # 使用域名创建 config.yaml
    print_step "Creating configuration..."

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
    print_info "Created: $CONFIG_DIR/config.yaml"

    # 创建空的 users.yaml
    cat > "$CONFIG_DIR/users.yaml" << 'EOF'
# SMTP Tunnel Users
# Managed by smtp-tunnel-adduser

users: {}
EOF

    chmod 600 "$CONFIG_DIR/users.yaml"
    print_info "Created: $CONFIG_DIR/users.yaml"

    # 生成证书
    echo ""
    print_step "Generating TLS certificates for $DOMAIN_NAME..."

    cd "$INSTALL_DIR"
    if python3 generate_certs.py --hostname "$DOMAIN_NAME" --output-dir "$CONFIG_DIR"; then
        print_info "Certificates generated successfully"
        # 创建符号链接以便 adduser 脚本可以找到 ca.crt
        ln -sf "$CONFIG_DIR/ca.crt" "$INSTALL_DIR/ca.crt"
    else
        print_error "Failed to generate certificates. You can try manually:"
        echo "    cd $INSTALL_DIR"
        echo "    python3 generate_certs.py --hostname $DOMAIN_NAME --output-dir $CONFIG_DIR"
    fi

    # 询问是否创建第一个用户
    echo ""
    print_ask "Would you like to create your first user now? [Y/n]: "
    read -p "    " CREATE_USER < /dev/tty

    if [ -z "$CREATE_USER" ] || [ "$CREATE_USER" = "y" ] || [ "$CREATE_USER" = "Y" ]; then
        echo ""
        print_ask "Enter username for the first user:"
        read -p "    Username: " FIRST_USER < /dev/tty

        if [ -n "$FIRST_USER" ]; then
            echo ""
            print_step "Creating user '$FIRST_USER'..."

            cd "$INSTALL_DIR"
            if python3 smtp-tunnel-adduser "$FIRST_USER"; then
                echo ""
                print_info "User '$FIRST_USER' created successfully!"
                print_info "Client package: $INSTALL_DIR/${FIRST_USER}.zip"
                echo ""
                echo -e "    ${YELLOW}Send this ZIP file to the user - it contains everything needed to connect!${NC}"
            else
                print_warn "Failed to create user. You can create users later with:"
                echo "    smtp-tunnel-adduser <username>"
            fi
        else
            print_warn "No username provided. You can create users later with:"
            echo "    smtp-tunnel-adduser <username>"
        fi
    else
        echo ""
        print_info "Skipping user creation."
        echo "    You can create users later with: smtp-tunnel-adduser <username>"
    fi

    # 打开防火墙
    echo ""
    print_step "Configuring firewall..."

    if command -v ufw &> /dev/null; then
        if ufw allow 587/tcp >/dev/null 2>&1; then
            print_info "Opened port 587/tcp (ufw)"
        else
            print_warn "Could not configure ufw. Make sure port 587/tcp is open!"
        fi
    elif command -v firewall-cmd &> /dev/null; then
        if firewall-cmd --permanent --add-port=587/tcp >/dev/null 2>&1 && firewall-cmd --reload >/dev/null 2>&1; then
            print_info "Opened port 587/tcp (firewalld)"
        else
            print_warn "Could not configure firewalld. Make sure port 587/tcp is open!"
        fi
    else
        print_warn "No firewall detected. Make sure port 587/tcp is open!"
    fi

    # 启用并启动服务
    echo ""
    print_step "Starting SMTP Tunnel service..."

    systemctl enable smtp-tunnel >/dev/null 2>&1 || true
    systemctl start smtp-tunnel 2>&1 || true

    sleep 2

    if systemctl is-active --quiet smtp-tunnel; then
        print_info "Service started successfully!"
    else
        print_warn "Service may not have started. Check with:"
        echo "    systemctl status smtp-tunnel"
        echo "    journalctl -u smtp-tunnel -n 50"
    fi
}

# 打印最终摘要
print_summary() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Installation Complete!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "Your SMTP Tunnel Proxy is now running!"
    echo ""
    echo -e "${BLUE}Service Status:${NC}"
    echo "   systemctl status smtp-tunnel"
    echo ""
    echo -e "${BLUE}View Logs:${NC}"
    echo "   journalctl -u smtp-tunnel -f"
    echo ""
    echo -e "${BLUE}User Management:${NC}"
    echo "   smtp-tunnel-adduser <username>    Add user + generate client ZIP"
    echo "   smtp-tunnel-deluser <username>    Remove user"
    echo "   smtp-tunnel-listusers             List all users"
    echo ""
    echo -e "${BLUE}Configuration Files:${NC}"
    echo "   $CONFIG_DIR/config.yaml"
    echo "   $CONFIG_DIR/users.yaml"
    echo ""
    echo -e "${BLUE}To Uninstall:${NC}"
    echo "   $INSTALL_DIR/uninstall.sh"
    echo ""
}

# 主安装流程
main() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  SMTP Tunnel Proxy Installer${NC}"
    echo -e "${GREEN}  Version 1.2.0${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""

    check_root
    detect_os
    install_dependencies
    create_directories
    install_files
    install_python_packages
    install_systemd_service
    create_uninstall_script
    interactive_setup
    print_summary
}

# 运行主函数
main "$@"
