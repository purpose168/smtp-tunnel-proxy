#!/bin/bash
#
# SMTP 隧道代理 - 证书下载脚本
#
# 用于从服务器下载客户端所需的证书文件
#
# 版本: 1.0.0
#

# 输出颜色定义
RED='\033[0;31m'      # 红色 - 错误
GREEN='\033[0;32m'    # 绿色 - 信息
YELLOW='\033[1;33m'   # 黄色 - 警告
BLUE='\033[0;34m'     # 蓝色 - 步骤
CYAN='\033[0;36m'     # 青色 - 提问
NC='\033[0m'          # 无颜色

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 配置文件目录
CONFIG_DIR="$SCRIPT_DIR/config"

# 服务器证书路径（默认）
SERVER_CERT_DIR="/opt/smtp-tunnel/config"

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

# 显示帮助信息
show_help() {
    cat << EOF
SMTP 隧道代理 - 证书下载脚本

用法: $(basename "$0") [选项]

选项:
  -s, --server <地址>      服务器地址（必需）
  -u, --username <用户名>   客户端用户名（必需）
  -d, --cert-dir <路径>     服务器证书目录（默认: /opt/smtp-tunnel/config）
  -c, --config-dir <路径>    本地配置目录（默认: ./config）
  -h, --help               显示此帮助信息

示例:
  $(basename "$0") --server 192.168.1.100 --username testuser
  $(basename "$0") -s 192.168.1.100 -u testuser -d /opt/smtp-tunnel/config

说明:
  此脚本用于从 SMTP 隧道代理服务器下载客户端所需的证书文件。
  下载的证书文件包括：
    - CA 证书 (ca.crt)
    - 客户端证书 (client.crt)
    - 客户端私钥 (client.key)

  前提条件:
    1. 服务器上已创建用户（使用 smtp-tunnel-adduser 命令）
    2. 可以通过 SSH 访问服务器
    3. 有权限读取服务器上的证书文件

EOF
}

# 检查命令是否存在
check_command() {
    local cmd="$1"
    if ! command -v "${cmd}" &> /dev/null; then
        print_error "命令 '${cmd}' 未找到，请先安装"
        return 1
    fi
    return 0
}

# 检查证书文件
check_certificates() {
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
        return 1
    else
        return 0
    fi
}

# 验证证书文件
verify_certificates() {
    print_step "验证证书文件..."
    
    local cert_valid=true
    
    # 检查 CA 证书
    if [ -f "$CONFIG_DIR/ca.crt" ]; then
        if openssl x509 -in "$CONFIG_DIR/ca.crt" -noout -checkend 0 2>/dev/null; then
            print_info "✓ CA 证书有效: $CONFIG_DIR/ca.crt"
        else
            print_warn "✗ CA 证书无效或已过期: $CONFIG_DIR/ca.crt"
            cert_valid=false
        fi
    fi
    
    # 检查客户端证书
    if [ -f "$CONFIG_DIR/client.crt" ]; then
        if openssl x509 -in "$CONFIG_DIR/client.crt" -noout -checkend 0 2>/dev/null; then
            print_info "✓ 客户端证书有效: $CONFIG_DIR/client.crt"
        else
            print_warn "✗ 客户端证书无效或已过期: $CONFIG_DIR/client.crt"
            cert_valid=false
        fi
    fi
    
    # 检查私钥和证书是否匹配
    if [ -f "$CONFIG_DIR/client.crt" ] && [ -f "$CONFIG_DIR/client.key" ]; then
        local cert_modulus=$(openssl x509 -noout -modulus -in "$CONFIG_DIR/client.crt" 2>/dev/null | openssl md5)
        local key_modulus=$(openssl rsa -noout -modulus -in "$CONFIG_DIR/client.key" 2>/dev/null | openssl md5)
        
        if [ "$cert_modulus" = "$key_modulus" ]; then
            print_info "✓ 客户端证书和私钥匹配"
        else
            print_warn "✗ 客户端证书和私钥不匹配"
            cert_valid=false
        fi
    fi
    
    if [ "$cert_valid" = true ]; then
        echo ""
        print_info "所有证书文件验证通过"
        echo ""
        return 0
    else
        echo ""
        print_warn "证书文件验证失败，请检查证书文件"
        echo ""
        return 1
    fi
}

# 下载证书文件
download_certificates() {
    local server_addr="$1"
    local username="$2"
    local server_cert_dir="$3"
    
    print_step "从服务器下载证书文件..."
    echo ""
    
    # 下载 CA 证书
    print_info "正在下载 CA 证书..."
    if ! scp "root@${server_addr}:${server_cert_dir}/ca.crt" "$CONFIG_DIR/ca.crt"; then
        print_error "下载 CA 证书失败"
        return 1
    fi
    print_info "✓ 已下载: ca.crt"
    
    # 下载客户端证书
    print_info "正在下载客户端证书..."
    if ! scp "root@${server_addr}:${server_cert_dir}/client-${username}.crt" "$CONFIG_DIR/client.crt"; then
        print_error "下载客户端证书失败"
        return 1
    fi
    print_info "✓ 已下载: client.crt"
    
    # 下载客户端私钥
    print_info "正在下载客户端私钥..."
    if ! scp "root@${server_addr}:${server_cert_dir}/client-${username}.key" "$CONFIG_DIR/client.key"; then
        print_error "下载客户端私钥失败"
        return 1
    fi
    print_info "✓ 已下载: client.key"
    
    # 设置证书文件权限
    chmod 600 "$CONFIG_DIR/ca.crt"
    chmod 600 "$CONFIG_DIR/client.crt"
    chmod 600 "$CONFIG_DIR/client.key"
    
    echo ""
    print_info "证书文件下载完成！"
    print_info "证书文件权限已设置为 600"
    echo ""
    
    return 0
}

# 显示证书信息
show_certificate_info() {
    print_step "证书文件信息..."
    echo ""
    
    # 显示 CA 证书信息
    if [ -f "$CONFIG_DIR/ca.crt" ]; then
        echo -e "${BLUE}CA 证书 (ca.crt):${NC}"
        openssl x509 -in "$CONFIG_DIR/ca.crt" -noout -subject -issuer -dates 2>/dev/null | sed 's/^/  /'
        echo ""
    fi
    
    # 显示客户端证书信息
    if [ -f "$CONFIG_DIR/client.crt" ]; then
        echo -e "${BLUE}客户端证书 (client.crt):${NC}"
        openssl x509 -in "$CONFIG_DIR/client.crt" -noout -subject -issuer -dates 2>/dev/null | sed 's/^/  /'
        echo ""
    fi
    
    # 显示私钥信息
    if [ -f "$CONFIG_DIR/client.key" ]; then
        echo -e "${BLUE}客户端私钥 (client.key):${NC}"
        local key_type=$(openssl rsa -in "$CONFIG_DIR/client.key" -noout -text 2>/dev/null | grep "Private-Key:" | awk '{print $2}')
        echo "  密钥类型: $key_type"
        local key_bits=$(openssl rsa -in "$CONFIG_DIR/client.key" -noout -text 2>/dev/null | grep "Private-Key:" | awk '{print $3}')
        echo "  密钥长度: $key_bits"
        echo ""
    fi
}

# 主函数
main() {
    local server_addr=""
    local username=""
    local server_cert_dir="$SERVER_CERT_DIR"
    
    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            -s|--server)
                server_addr="$2"
                shift 2
                ;;
            -u|--username)
                username="$2"
                shift 2
                ;;
            -d|--cert-dir)
                server_cert_dir="$2"
                shift 2
                ;;
            -c|--config-dir)
                CONFIG_DIR="$2"
                shift 2
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                print_error "未知选项: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # 检查必要的命令
    if ! check_command "scp"; then
        print_error "scp 命令未找到，请安装 openssh-client"
        exit 1
    fi
    
    if ! check_command "openssl"; then
        print_error "openssl 命令未找到，请安装 openssl"
        exit 1
    fi
    
    # 创建配置目录
    if [ ! -d "$CONFIG_DIR" ]; then
        print_info "创建配置目录: $CONFIG_DIR"
        mkdir -p "$CONFIG_DIR"
        chmod 700 "$CONFIG_DIR"
    fi
    
    # 检查证书文件
    if check_certificates; then
        echo ""
        print_info "所有证书文件已存在"
        echo ""
        
        # 询问是否重新下载
        print_ask "是否重新下载证书文件？[y/N]: "
        read -p "    " REDOWNLOAD < /dev/tty
        
        if [ "$REDOWNLOAD" != "y" ] && [ "$REDOWNLOAD" != "Y" ]; then
            echo ""
            print_info "跳过证书下载"
            echo ""
            
            # 验证现有证书
            verify_certificates
            
            # 显示证书信息
            show_certificate_info
            
            exit 0
        fi
    fi
    
    # 获取服务器地址
    if [ -z "$server_addr" ]; then
        echo ""
        print_ask "请输入服务器地址: "
        read -p "    " server_addr < /dev/tty
        
        if [ -z "$server_addr" ]; then
            print_error "服务器地址不能为空"
            exit 1
        fi
    fi
    
    # 获取用户名
    if [ -z "$username" ]; then
        echo ""
        print_ask "请输入客户端用户名: "
        read -p "    " username < /dev/tty
        
        if [ -z "$username" ]; then
            print_error "用户名不能为空"
            exit 1
        fi
    fi
    
    # 显示下载信息
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  证书下载信息${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${BLUE}服务器地址:${NC} $server_addr"
    echo -e "${BLUE}用户名:${NC} $username"
    echo -e "${BLUE}服务器证书目录:${NC} $server_cert_dir"
    echo -e "${BLUE}本地配置目录:${NC} $CONFIG_DIR"
    echo ""
    
    # 确认下载
    print_ask "确认下载证书文件？[Y/n]: "
    read -p "    " CONFIRM < /dev/tty
    
    if [ "$CONFIRM" = "n" ] || [ "$CONFIRM" = "N" ]; then
        print_info "取消下载"
        exit 0
    fi
    
    # 下载证书文件
    if ! download_certificates "$server_addr" "$username" "$server_cert_dir"; then
        print_error "证书下载失败"
        exit 1
    fi
    
    # 验证证书文件
    if ! verify_certificates; then
        print_error "证书验证失败"
        exit 1
    fi
    
    # 显示证书信息
    show_certificate_info
    
    # 显示完成信息
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  证书下载完成！${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${BLUE}证书文件位置:${NC}"
    echo "   CA 证书: $CONFIG_DIR/ca.crt"
    echo "   客户端证书: $CONFIG_DIR/client.crt"
    echo "   客户端私钥: $CONFIG_DIR/client.key"
    echo ""
    echo -e "${BLUE}下一步:${NC}"
    echo "   1. 编辑配置文件: $CONFIG_DIR/config.yaml"
    echo "   2. 启动客户端: ./start.sh"
    echo ""
}

# 运行主函数
main "$@"
