#!/bin/bash
#
# SMTP Tunnel Proxy - Server Installation Script
#
# One-liner installation:
#   curl -sSL https://raw.githubusercontent.com/x011/smtp-tunnel-proxy/main/install.sh | sudo bash
#
# Version: 1.1.0

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# GitHub raw URL base
GITHUB_RAW="https://raw.githubusercontent.com/x011/smtp-tunnel-proxy/main"

# Installation directories
INSTALL_DIR="/opt/smtp-tunnel"
CONFIG_DIR="/etc/smtp-tunnel"
BIN_DIR="/usr/local/bin"

# Files to download
PYTHON_FILES="server.py client.py common.py generate_certs.py"
SCRIPTS="smtp-tunnel-adduser smtp-tunnel-deluser smtp-tunnel-listusers"
CONFIG_FILES="config.yaml users.yaml requirements.txt"

# Print with color
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

# Check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        print_error "Please run as root (use sudo)"
        echo ""
        echo "Usage: curl -sSL $GITHUB_RAW/install.sh | sudo bash"
        exit 1
    fi
}

# Detect OS
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

# Install Python and dependencies
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

    # Check Python version
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        print_info "Python version: $PYTHON_VERSION"
    else
        print_error "Python 3 not found. Please install Python 3.8+"
        exit 1
    fi
}

# Create directories
create_directories() {
    print_step "Creating directories..."

    mkdir -p "$INSTALL_DIR"
    mkdir -p "$CONFIG_DIR"

    chmod 755 "$INSTALL_DIR"
    chmod 700 "$CONFIG_DIR"

    print_info "Created: $INSTALL_DIR"
    print_info "Created: $CONFIG_DIR"
}

# Download file from GitHub
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

# Download and install files
install_files() {
    print_step "Downloading files from GitHub..."

    # Download Python files to install directory
    for file in $PYTHON_FILES; do
        download_file "$file" "$INSTALL_DIR/$file" || exit 1
    done

    # Download and install management scripts
    for script in $SCRIPTS; do
        download_file "$script" "$INSTALL_DIR/$script" || exit 1
        chmod +x "$INSTALL_DIR/$script"
        # Create symlink in bin directory
        ln -sf "$INSTALL_DIR/$script" "$BIN_DIR/$script"
        print_info "  Linked: $script -> $BIN_DIR/$script"
    done

    # Download config files if they don't exist
    if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
        download_file "config.yaml" "$CONFIG_DIR/config.yaml" || exit 1
        # Update paths in config to use /etc/smtp-tunnel
        sed -i 's|cert_file: "server.crt"|cert_file: "/etc/smtp-tunnel/server.crt"|g' "$CONFIG_DIR/config.yaml"
        sed -i 's|key_file: "server.key"|key_file: "/etc/smtp-tunnel/server.key"|g' "$CONFIG_DIR/config.yaml"
        sed -i 's|users_file: "users.yaml"|users_file: "/etc/smtp-tunnel/users.yaml"|g' "$CONFIG_DIR/config.yaml"
    else
        print_warn "  Config exists, skipping: $CONFIG_DIR/config.yaml"
    fi

    if [ ! -f "$CONFIG_DIR/users.yaml" ]; then
        download_file "users.yaml" "$CONFIG_DIR/users.yaml" || exit 1
    else
        print_warn "  Users file exists, skipping: $CONFIG_DIR/users.yaml"
    fi

    # Download requirements.txt
    download_file "requirements.txt" "$INSTALL_DIR/requirements.txt" || exit 1

    # Set permissions
    chmod 600 "$CONFIG_DIR/config.yaml"
    chmod 600 "$CONFIG_DIR/users.yaml"
}

# Install Python packages
install_python_packages() {
    print_step "Installing Python packages..."

    pip3 install -q -r "$INSTALL_DIR/requirements.txt"
    print_info "Python packages installed"
}

# Create systemd service
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

# Create uninstall script
create_uninstall_script() {
    cat > "$INSTALL_DIR/uninstall.sh" << 'EOF'
#!/bin/bash
# SMTP Tunnel Proxy - Uninstall Script

set -e

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

# Print final instructions
print_instructions() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  SMTP Tunnel Proxy Installed!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "Next steps:"
    echo ""
    echo -e "${BLUE}1.${NC} Edit configuration:"
    echo "   nano $CONFIG_DIR/config.yaml"
    echo "   → Set 'hostname' to your domain (e.g., myserver.duckdns.org)"
    echo ""
    echo -e "${BLUE}2.${NC} Generate TLS certificates:"
    echo "   cd $INSTALL_DIR"
    echo "   python3 generate_certs.py --hostname YOUR-DOMAIN --output-dir $CONFIG_DIR"
    echo ""
    echo -e "${BLUE}3.${NC} Add your first user:"
    echo "   smtp-tunnel-adduser alice"
    echo "   → This creates alice.zip with everything the client needs"
    echo ""
    echo -e "${BLUE}4.${NC} Open firewall port:"
    echo "   ufw allow 587/tcp"
    echo ""
    echo -e "${BLUE}5.${NC} Start the service:"
    echo "   systemctl enable smtp-tunnel"
    echo "   systemctl start smtp-tunnel"
    echo ""
    echo -e "${BLUE}6.${NC} Check status:"
    echo "   systemctl status smtp-tunnel"
    echo "   journalctl -u smtp-tunnel -f"
    echo ""
    echo "Management commands:"
    echo "   smtp-tunnel-adduser <username>    Add user + generate client ZIP"
    echo "   smtp-tunnel-deluser <username>    Remove user"
    echo "   smtp-tunnel-listusers             List all users"
    echo ""
    echo "To uninstall:"
    echo "   $INSTALL_DIR/uninstall.sh"
    echo ""
}

# Main installation
main() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  SMTP Tunnel Proxy Installer${NC}"
    echo -e "${GREEN}  Version 1.1.0${NC}"
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
    print_instructions
}

# Run main
main "$@"
