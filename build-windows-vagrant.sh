#!/bin/bash
#
# SMTP 隧道代理 - Vagrant Windows 构建脚本
#
# 使用 Vagrant 在 Ubuntu 宿主机上构建 Windows 客户端
#
# 功能:
#   1. 检查 Vagrant 环境
#   2. 启动 Windows 虚拟机
#   3. 在 Windows 虚拟机中构建 Windows 客户端
#   4. 从虚拟机复制生成的文件
#
# 使用方法:
#   ./build-windows-vagrant.sh          # 构建 Windows 客户端
#   ./build-windows-vagrant.sh setup      # 设置 Vagrant 环境
#   ./build-windows-vagrant.sh start      # 启动虚拟机
#   ./build-windows-vagrant.sh stop       # 停止虚拟机
#   ./build-windows-vagrant.sh destroy    # 销毁虚拟机
#   ./build-windows-vagrant.sh help       # 显示帮助
#
# 依赖:
#   - Vagrant
#   - VirtualBox
#   - 足够的内存（建议 8GB+）
#
# 版本: 1.0.0

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 变量定义
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}"
DIST_DIR="${SCRIPT_DIR}/dist"
CLIENT_NAME="smtp-tunnel-client"

# 打印函数
print_info() {
    echo -e "${GREEN}[信息]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[警告]${NC} $1"
}

print_error() {
    echo -e "${RED}[错误]${NC} $1"
}

print_step() {
    echo -e "${BLUE}[步骤]${NC} $1"
}

# 检查 Vagrant 是否安装
check_vagrant() {
    if ! command -v vagrant &> /dev/null; then
        print_error "Vagrant 未安装"
        echo ""
        echo "请先安装 Vagrant:"
        echo "  Ubuntu/Debian: sudo apt install vagrant"
        echo "  Fedora: sudo dnf install vagrant"
        echo "  Arch: sudo pacman -S vagrant"
        echo ""
        echo "或者从官网下载: https://www.vagrantup.com/downloads"
        return 1
    fi

    if ! command -v VBoxManage &> /dev/null; then
        print_error "VirtualBox 未安装"
        echo ""
        echo "请先安装 VirtualBox:"
        echo "  Ubuntu/Debian: sudo apt install virtualbox"
        echo "  Fedora: sudo dnf install virtualbox"
        echo "  Arch: sudo pacman -S virtualbox"
        echo ""
        echo "或者从官网下载: https://www.virtualbox.org/wiki/Downloads"
        return 1
    fi

    return 0
}

# 检查系统资源
check_resources() {
    local total_mem=$(free -g | awk '/^Mem:/{print $2}')
    
    if [ "$total_mem" -lt 8 ]; then
        print_warn "系统内存不足 8GB，建议至少 8GB"
        print_warn "当前内存: ${total_mem}GB"
        echo ""
        read -p "是否继续？(y/N) " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "已取消"
            exit 1
        fi
    fi
}

# 设置 Vagrant 环境
setup_vagrant() {
    print_step "设置 Vagrant 环境..."

    # 检查依赖
    check_vagrant || return 1

    # 检查资源
    check_resources

    # 检查 Vagrantfile
    if [ ! -f "$PROJECT_DIR/Vagrantfile" ]; then
        print_error "未找到 Vagrantfile"
        return 1
    fi

    print_info "Vagrantfile 已就绪"
    echo ""
    print_info "下一步: 运行 ./build-windows-vagrant.sh start 启动虚拟机"
}

# 启动虚拟机
start_vm() {
    print_step "启动 Windows 虚拟机..."

    # 检查依赖
    check_vagrant || return 1

    # 检查虚拟机是否已运行
    if vagrant status | grep -q "running"; then
        print_info "虚拟机已在运行"
        return 0
    fi

    # 启动虚拟机
    vagrant up

    print_info "虚拟机启动成功!"
    echo ""
    print_info "下一步: 运行 ./build-windows-vagrant.sh build 构建客户端"
}

# 停止虚拟机
stop_vm() {
    print_step "停止 Windows 虚拟机..."

    # 检查虚拟机是否运行
    if ! vagrant status | grep -q "running"; then
        print_info "虚拟机未运行"
        return 0
    fi

    # 停止虚拟机
    vagrant halt

    print_info "虚拟机已停止"
}

# 销毁虚拟机
destroy_vm() {
    print_step "销毁 Windows 虚拟机..."

    # 检查虚拟机是否存在
    if ! vagrant status | grep -q "default"; then
        print_info "虚拟机不存在"
        return 0
    fi

    echo ""
    print_warn "这将删除虚拟机和所有数据!"
    read -p "确认删除？(y/N) " -n 1 -r
    echo ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        vagrant destroy -f
        print_info "虚拟机已销毁"
    else
        print_info "已取消"
    fi
}

# 构建 Windows 客户端
build_client() {
    print_step "构建 Windows 客户端..."

    # 检查依赖
    check_vagrant || return 1

    # 检查虚拟机是否运行
    if ! vagrant status | grep -q "running"; then
        print_warn "虚拟机未运行，正在启动..."
        vagrant up
    fi

    # 运行构建脚本
    print_step "在 Windows 虚拟机中运行 PyInstaller..."
    vagrant provision --provision-with build

    # 检查构建结果
    if [ -f "$DIST_DIR/${CLIENT_NAME}-windows.exe" ]; then
        print_info "Windows 客户端构建成功!"
        echo ""
        echo -e "${GREEN}输出文件:${NC}"
        ls -lh "$DIST_DIR/${CLIENT_NAME}-windows.exe"
        echo ""
        echo -e "${BLUE}[提示]${NC} 可直接拷贝到 Windows 系统运行"
    else
        print_warn "构建可能未完成"
        print_warn "请检查虚拟机日志"
        return 1
    fi
}

# 显示虚拟机状态
show_status() {
    print_step "虚拟机状态:"
    echo ""
    vagrant status
}

# 连接到虚拟机
connect_vm() {
    print_step "连接到 Windows 虚拟机..."
    print_warn "注意：Windows 虚拟机需要配置 SSH 才能使用 vagrant ssh"
    print_warn "请使用 VirtualBox GUI 直接访问虚拟机"
    echo ""
    print_info "或者使用以下方法："
    echo "  1. 打开 VirtualBox GUI"
    echo "  2. 选择虚拟机: smtp-tunnel-windows-builder"
    echo "  3. 点击 '显示' 按钮"
}

# 显示帮助信息
show_help() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  SMTP 隧道代理 - Vagrant Windows 构建脚本${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    echo "用法: $0 <命令>"
    echo ""
    echo "命令:"
    echo "          构建 Windows 客户端（默认）"
    echo "  setup      设置 Vagrant 环境"
    echo "  start      启动 Windows 虚拟机"
    echo "  stop       停止 Windows 虚拟机"
    echo "  destroy    销毁 Windows 虚拟机"
    echo "  status     显示虚拟机状态"
    echo "  connect    连接到虚拟机（需要配置 SSH）"
    echo "  help       显示此帮助信息"
    echo ""
    echo "前提条件:"
    echo "  1. 安装 Vagrant: sudo apt install vagrant"
    echo "  2. 安装 VirtualBox: sudo apt install virtualbox"
    echo "  3. 足够的内存（建议 8GB+）"
    echo ""
    echo "使用流程:"
    echo "  1. $0 setup          # 设置环境"
    echo "  2. $0 start          # 启动虚拟机"
    echo "  3. $0 build          # 构建客户端"
    echo "  4. $0 stop           # 停止虚拟机"
    echo ""
    echo "输出位置:"
    echo "  dist/${CLIENT_NAME}-windows.exe"
    echo ""
    echo "优势:"
    echo "  - 完整的 Windows 环境"
    echo "  - 可以使用 Windows GUI"
    echo "  - 可以安装任何 Windows 软件"
    echo "  - 适合复杂的 Windows 依赖"
    echo ""
    echo "注意事项:"
    echo "  - 首次使用需要下载 Windows 镜像（约 5GB）"
    echo "  - 虚拟机需要 4GB 内存"
    echo "  - 启动和停止需要较长时间"
    echo "  - 建议在构建完成后停止虚拟机以节省资源"
}

# 主函数
main() {
    local command="${1:-help}"
    shift 2>/dev/null || true

    # 解析选项
    while [ $# -gt 0 ]; do
        case "$1" in
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                ;;
        esac
        shift
    done

    # 检查脚本是否在正确的目录运行
    if [ ! -f "$SCRIPT_DIR/client.py" ]; then
        print_error "未找到 client.py，请确保在项目根目录运行此脚本"
        exit 1
    fi

    case "$command" in
        build|"")
            build_client
            ;;
        setup)
            setup_vagrant
            ;;
        start)
            start_vm
            ;;
        stop)
            stop_vm
            ;;
        destroy)
            destroy_vm
            ;;
        status)
            show_status
            ;;
        connect)
            connect_vm
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            print_error "未知命令: $command"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# 运行主函数
main "$@"
