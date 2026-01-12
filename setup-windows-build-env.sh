#!/bin/bash
#
# SMTP 隧道代理 - MinGW-w64 和 PyInstaller 环境安装脚本
#
# 用于在 Linux 上配置 MinGW-w64 和 PyInstaller 以进行 Windows 程序打包
#
# 功能:
#   1. 检查并安装 MinGW-w64
#   2. 检查交叉编译工具链
#   3. 安装 PyInstaller
#   4. 使用 PyInstaller 打包 Windows 客户端
#
# 使用方法:
#   ./setup-windows-build-env.sh check        # 检查 MinGW-w64 和 PyInstaller 环境
#   ./setup-windows-build-env.sh install      # 安装 MinGW-w64 和 PyInstaller
#   ./setup-windows-build-env.sh build        # 构建 Windows 客户端
#   ./setup-windows-build-env.sh build-dir    # 构建 Windows 客户端（目录模式）
#   ./setup-windows-build-env.sh all          # 执行完整安装和构建流程
#
# 版本: 2.1.0

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 变量定义
MINGW_PREFIX="${MINGW_PREFIX:-x86_64-w64-mingw32}"
MINGW_GCC="${MINGW_PREFIX}-gcc"
MINGW_GPP="${MINGW_PREFIX}-g++"
MINGW_WINDRES="${MINGW_PREFIX}-windres"
MINGW_STRIP="${MINGW_PREFIX}-strip"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}"
DIST_DIR="${SCRIPT_DIR}/dist"
BUILD_DIR="${SCRIPT_DIR}/build"
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

print_debug() {
    if [ "$DEBUG" = "true" ]; then
        echo -e "${CYAN}[调试]${NC} $1"
    fi
}

# 检查是否以 root 身份运行
check_root() {
    if [ "$EUID" -eq 0 ]; then
        print_warn "建议不要以 root 身份运行此脚本"
    fi
}

# 检查 MinGW-w64 是否安装
check_mingw_installed() {
    if command -v "$MINGW_GCC" &> /dev/null; then
        return 0
    fi
    return 1
}

# 检查 MinGW-w64 工具链是否完整
check_mingw_toolchain() {
    if command -v "$MINGW_GCC" &> /dev/null && \
       command -v "$MINGW_GPP" &> /dev/null && \
       command -v "$MINGW_WINDRES" &> /dev/null && \
       command -v "$MINGW_STRIP" &> /dev/null; then
        return 0
    fi
    return 1
}

# 检查交叉编译 Python 是否已安装
check_cross_python() {
    if command -v pyinstaller &> /dev/null || pip3 show pyinstaller &> /dev/null; then
        return 0
    fi
    return 1
}

# 安装 MinGW-w64（Ubuntu/Debian）
install_mingw_ubuntu() {
    print_step "正在安装 MinGW-w64（Ubuntu/Debian）..."

    # 检查是否已安装 MinGW-w64
    if check_mingw_installed; then
        print_info "MinGW-w64 已安装: $MINGW_GCC"
        return 0
    fi

    # 更新软件包列表
    print_step "更新软件包列表..."
    sudo apt update

    # 安装 MinGW-w64
    print_step "安装 MinGW-w64 工具链..."
    sudo apt install -y mingw-w64 mingw-w64-tools

    # 验证安装
    if check_mingw_installed; then
        print_info "MinGW-w64 安装成功: $MINGW_GCC"
    else
        print_error "MinGW-w64 安装失败"
        return 1
    fi

    # 检查工具链完整性
    if ! check_mingw_toolchain; then
        print_warn "MinGW-w64 工具链可能不完整"
    fi
}

# 安装 MinGW-w64（Fedora/RHEL）
install_mingw_fedora() {
    print_step "正在安装 MinGW-w64（Fedora/RHEL）..."
    sudo dnf install -y mingw64-gcc mingw64-gcc-c++ mingw64-winpthreads mingw64-tools
}

# 安装 MinGW-w64（Arch Linux）
install_mingw_arch() {
    print_step "正在安装 MinGW-w64（Arch Linux）..."
    sudo pacman -S --noconfirm mingw-w64-gcc
}

# 自动检测系统并安装 MinGW-w64
install_mingw_auto() {
    print_step "检测系统类型..."

    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS_ID="$ID"
    else
        print_error "无法检测系统类型"
        return 1
    fi

    case "$OS_ID" in
        ubuntu|debian|linuxmint|pop)
            install_mingw_ubuntu
            ;;
        fedora|rhel|centos)
            install_mingw_fedora
            ;;
        arch|manjaro)
            install_mingw_arch
            ;;
        *)
            print_error "不支持的系统: $OS_ID"
            print_info "请手动安装 MinGW-w64"
            return 1
            ;;
    esac
}

# 安装 MinGW-w64 和 PyInstaller
install_cross_python() {
    print_step "安装 MinGW-w64 和 PyInstaller..."

    # 检查 MinGW-w64 是否安装
    if ! check_mingw_installed; then
        print_info "MinGW-w64 未安装，开始安装..."
        install_mingw_auto || return 1
    fi

    # 检查工具链完整性
    if ! check_mingw_toolchain; then
        print_warn "MinGW-w64 工具链不完整"
        print_warn "可能需要安装额外的工具"
    fi

    # 安装 Python 和 PyInstaller
    print_step "安装 Python 和 PyInstaller..."
    sudo apt install -y python3 python3-pip python3-venv || true

    # 安装 PyInstaller 和其他依赖
    print_step "安装 PyInstaller 和依赖包..."
    pip3 install --user pyinstaller cryptography pyyaml || {
        print_warn "pip3 安装失败，尝试使用系统包管理器..."
        sudo apt install -y python3-pyinstaller || true
    }

    # 验证安装
    if command -v pyinstaller &> /dev/null || pip3 show pyinstaller &> /dev/null; then
        print_info "PyInstaller 安装成功"
    else
        print_warn "PyInstaller 安装可能遇到问题"
    fi

    print_info "MinGW-w64 和 PyInstaller 安装完成"
    echo ""
    print_info "提示: 现在可以使用 ./setup-windows-build-env.sh build 构建 Windows 客户端"
    print_info "      PyInstaller 会自动处理 Windows 可执行文件的打包"
}

# 诊断 MinGW-w64 环境
diagnose_mingw() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  MinGW-w64 环境诊断${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""

    # 检查 MinGW-w64 版本
    print_step "MinGW-w64 版本..."
    if command -v "$MINGW_GCC" &> /dev/null; then
        "$MINGW_GCC" --version | head -n 1
    else
        print_error "MinGW-w64 未安装"
    fi

    # 检查工具链
    print_step "检查 MinGW-w64 工具链..."
    if check_mingw_toolchain; then
        print_info "MinGW-w64 工具链: 完整"
        echo "  - GCC: $(command -v "$MINGW_GCC" 2>/dev/null || echo '未找到')"
        echo "  - G++: $(command -v "$MINGW_GPP" 2>/dev/null || echo '未找到')"
        echo "  - windres: $(command -v "$MINGW_WINDRES" 2>/dev/null || echo '未找到')"
        echo "  - strip: $(command -v "$MINGW_STRIP" 2>/dev/null || echo '未找到')"
    else
        print_warn "MinGW-w64 工具链: 不完整"
        echo "  - GCC: $(command -v "$MINGW_GCC" 2>/dev/null || echo '未找到')"
        echo "  - G++: $(command -v "$MINGW_GPP" 2>/dev/null || echo '未找到')"
        echo "  - windres: $(command -v "$MINGW_WINDRES" 2>/dev/null || echo '未找到')"
        echo "  - strip: $(command -v "$MINGW_STRIP" 2>/dev/null || echo '未找到')"
    fi

    # 检查 PyInstaller
    print_step "检查 PyInstaller..."
    if check_cross_python; then
        print_info "PyInstaller: 已安装"
        pyinstaller --version 2>/dev/null || pip3 show pyinstaller 2>/dev/null | grep Version || true
    else
        print_warn "PyInstaller: 未安装"
    fi

    # 测试 MinGW-w64
    print_step "测试 MinGW-w64..."
    if command -v "$MINGW_GCC" &> /dev/null; then
        cat > /tmp/test_mingw.c << 'EOF'
#include <stdio.h>
int main() {
    printf("MinGW-w64 测试成功\n");
    return 0;
}
EOF
        "$MINGW_GCC" -o /tmp/test_mingw.exe /tmp/test_mingw.c 2>&1 && {
            print_info "MinGW-w64 测试成功"
            rm -f /tmp/test_mingw.c /tmp/test_mingw.exe
        } || {
            print_warn "MinGW-w64 测试失败"
            rm -f /tmp/test_mingw.c /tmp/test_mingw.exe
        }
    fi

    echo ""
    echo -e "${YELLOW}[建议]${NC} 如果 MinGW-w64 无法正常工作，请尝试以下方案:"
    echo ""
    echo "1. 重新安装 MinGW-w64:"
    echo "   sudo apt remove --purge mingw-w64 mingw-w64-tools"
    echo "   sudo apt autoremove"
    echo "   sudo apt install mingw-w64 mingw-w64-tools"
    echo ""
    echo "2. 检查系统架构:"
    echo "   uname -m"
    echo ""
    echo "3. 使用 Docker（推荐用于交叉编译）"
    echo ""
}

# 重置 MinGW-w64 环境
reset_mingw() {
    print_step "重置 MinGW-w64 环境..."

    # 清理构建目录
    if [ -d "$BUILD_DIR" ]; then
        print_warn "删除构建目录..."
        rm -rf "$BUILD_DIR"
    fi

    # 清理发布目录
    if [ -d "$DIST_DIR" ]; then
        print_warn "删除发布目录..."
        rm -rf "$DIST_DIR"
    fi

    print_info "MinGW-w64 环境已重置"
    echo ""
    echo -e "${BLUE}[提示]${NC} 现在可以重新运行: ./setup-windows-build-env.sh install"
}

# 检查 MinGW-w64 环境
check_mingw_env() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  MinGW-w64 和 PyInstaller 环境检查${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""

    # 检查 MinGW-w64
    print_step "检查 MinGW-w64 安装..."
    if check_mingw_installed; then
        print_info "MinGW-w64 已安装: $MINGW_GCC"
    else
        print_error "MinGW-w64 未安装"
        echo ""
        echo "请安装 MinGW-w64:"
        echo "  Ubuntu/Debian: sudo apt install mingw-w64 mingw-w64-tools"
        echo "  Fedora: sudo dnf install mingw64-gcc mingw64-gcc-c++ mingw64-winpthreads mingw64-tools"
        echo "  Arch: sudo pacman -S mingw-w64-gcc"
    fi

    # 检查工具链
    print_step "检查 MinGW-w64 工具链..."
    if check_mingw_toolchain; then
        print_info "MinGW-w64 工具链完整"
    else
        print_warn "MinGW-w64 工具链不完整"
        echo ""
        echo "建议安装完整的工具链:"
        echo "  sudo apt install mingw-w64 mingw-w64-tools"
    fi

    # 检查 PyInstaller
    print_step "检查 PyInstaller..."
    if check_cross_python; then
        print_info "PyInstaller 已安装"
    else
        print_warn "PyInstaller 未安装"
        echo ""
        echo "安装方法:"
        echo "  ./setup-windows-build-env.sh install"
    fi

    echo ""
    echo -e "${BLUE}[提示]${NC} 使用 ./setup-windows-build-env.sh install 安装完整环境"
    echo -e "${BLUE}[提示]${NC} 使用 ./setup-windows-build-env.sh build 构建 Windows 客户端"
}

# 构建 Windows 客户端（单文件模式）- 调用独立脚本
build_windows_client() {
    local BUILD_SCRIPT="${SCRIPT_DIR}/build-windows-client.sh"

    if [ ! -f "$BUILD_SCRIPT" ]; then
        print_error "未找到构建脚本: $BUILD_SCRIPT"
        return 1
    fi

    "$BUILD_SCRIPT" build
}

# 构建 Windows 客户端（目录模式）- 调用独立脚本
build_windows_client_dir() {
    local BUILD_SCRIPT="${SCRIPT_DIR}/build-windows-client.sh"

    if [ ! -f "$BUILD_SCRIPT" ]; then
        print_error "未找到构建脚本: $BUILD_SCRIPT"
        return 1
    fi

    "$BUILD_SCRIPT" dir
}

# 显示帮助信息
show_help() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  SMTP 隧道代理 - MinGW-w64 和 PyInstaller 环境安装脚本${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    echo "用法: $0 <命令> [选项]"
    echo ""
    echo "命令:"
    echo "  check        检查 MinGW-w64 和 PyInstaller 环境"
    echo "  diagnose      诊断 MinGW-w64 环境（详细）"
    echo "  reset        重置 MinGW-w64 环境（删除配置）"
    echo "  install      安装 MinGW-w64 和 PyInstaller"
    echo "  build        构建 Windows 客户端（单文件模式）"
    echo "  build-dir    构建 Windows 客户端（目录模式）"
    echo "  all          执行完整安装和构建流程"
    echo "  help         显示此帮助信息"
    echo ""
    echo "选项:"
    echo "  --debug      启用调试模式"
    echo "  --force      强制重新安装"
    echo ""
    echo "示例:"
    echo "  $0 check              # 检查环境"
    echo "  $0 diagnose            # 诊断 MinGW-w64 环境"
    echo "  $0 reset              # 重置 MinGW-w64 环境"
    echo "  $0 install            # 安装 MinGW-w64 和 PyInstaller"
    echo "  $0 build              # 构建客户端"
    echo "  $0 all                # 完整流程"
    echo ""
    echo "关于 MinGW-w64 和 PyInstaller:"
    echo "  MinGW-w64 是一个用于在 Linux 上编译 Windows 程序的交叉编译工具链"
    echo "  PyInstaller 可以将 Python 脚本打包为独立的 Windows 可执行文件"
    echo "  本脚本使用 Docker 和 Windows Python 镜像进行跨平台构建"
    echo ""
    echo "优势:"
    echo "  - 更可靠：使用官方 Windows Python 镜像"
    echo "  - 更简单：无需配置 Wine 或交叉编译环境"
    echo "  - 更快速：Docker 构建环境已预先配置"
    echo "  - 更稳定：生成真正的 Windows 可执行文件（PE 格式）"
    echo ""
    echo "故障排除:"
    echo "  如果遇到 Docker 错误，请确保 Docker 服务已启动"
    echo "  如果 PyInstaller 打包失败，请检查 Python 脚本依赖"
    echo "  如果 Docker 镜像构建失败，请检查网络连接"
}

# 主函数
main() {
    local command="${1:-help}"
    shift 2>/dev/null || true

    # 解析选项
    while [ $# -gt 0 ]; do
        case "$1" in
            --debug)
                DEBUG="true"
                ;;
            --force)
                FORCE="true"
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                ;;
        esac
        shift
    done

    case "$command" in
        check)
            check_mingw_env
            ;;
        diagnose)
            diagnose_mingw
            ;;
        reset)
            reset_mingw
            ;;
        install)
            install_cross_python
            ;;
        build)
            build_windows_client
            ;;
        build-dir)
            build_windows_client_dir
            ;;
        all)
            install_cross_python
            echo ""
            build_windows_client
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
