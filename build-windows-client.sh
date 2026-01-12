#!/bin/bash
#
# SMTP 隧道代理 - Windows 客户端构建脚本
#
# 用于使用 PyInstaller 构建 Windows 客户端
#
# 功能:
#   1. 检查 PyInstaller 环境
#   2. 构建 Windows 客户端（单文件模式）
#   3. 构建 Windows 客户端（目录模式）
#
# 使用方法:
#   ./build-windows-client.sh          # 构建 Windows 客户端（单文件模式）
#   ./build-windows-client.sh dir      # 构建 Windows 客户端（目录模式）
#   ./build-windows-client.sh check    # 检查环境
#   ./build-windows-client.sh help     # 显示帮助
#
# 依赖:
#   - Python 3
#   - PyInstaller
#
# 重要提示:
#   在 Linux 上使用 PyInstaller 会生成 Linux 可执行文件（ELF），无法在 Windows 上运行。
#   要生成真正的 Windows 可执行文件（PE），请使用以下方法之一：
#   1. 在 Windows 系统上运行此脚本
#   2. 使用 Docker 构建：./build-windows-docker.sh build
#   3. 使用 Wine 和 Windows Python（复杂且不稳定）
#
# 版本: 2.0.0

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
BUILD_DIR="${SCRIPT_DIR}/build"
CLIENT_NAME="smtp-tunnel-client"

# 获取 PyInstaller
PYINSTALLER="${PYINSTALLER:-$(which pyinstaller 2>/dev/null || echo "")}"

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

# 检查 PyInstaller 是否安装
check_pyinstaller_installed() {
    if [ -z "$PYINSTALLER" ]; then
        return 1
    fi
    if ! command -v "$PYINSTALLER" &> /dev/null; then
        return 1
    fi
    return 0
}

# 检查 PyInstaller 环境
check_pyinstaller_env() {
    if ! check_pyinstaller_installed; then
        print_error "PyInstaller 未安装或不可用"
        return 1
    fi
    return 0
}

# 获取 PyInstaller 隐藏导入列表
get_hidden_imports() {
    cat << 'EOF'
--hidden-import=asyncio
--hidden-import=ssl
--hidden-import=cryptography
--hidden-import=yaml
--hidden-import=_cffi_backend
EOF
}

# 获取收集模块列表
get_collect_modules() {
    cat << 'EOF'
--collect-all common
--collect-all client_protocol
--collect-all client_socks5
--collect-all client_tunnel
--collect-all client_server
EOF
}

# 获取排除模块列表
get_exclude_modules() {
    cat << 'EOF'
--exclude-module=tkinter
--exclude-module=test
--exclude-module=unittest
--exclude-module=pydoc
EOF
}

# 构建 Windows 客户端（单文件模式）
build_onefile() {
    print_step "构建 Windows 客户端（单文件模式）..."

    # 检测操作系统
    local OS_TYPE=$(uname -s)
    if [ "$OS_TYPE" = "Linux" ]; then
        print_warn "警告：在 Linux 上使用 PyInstaller 会生成 Linux 可执行文件（ELF）"
        print_warn "生成的文件无法在 Windows 上运行！"
        echo ""
        print_info "要生成真正的 Windows 可执行文件，请使用以下方法之一："
        echo "  1. 在 Windows 系统上运行此脚本"
        echo "  2. 使用 Docker 构建：./build-windows-docker.sh build"
        echo ""
        read -p "是否继续构建 Linux 可执行文件？(y/N) " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "已取消构建"
            return 1
        fi
    fi

    # 环境检查
    if ! check_pyinstaller_env; then
        print_error "PyInstaller 环境检查失败"
        return 1
    fi

    # 创建目录
    mkdir -p "$DIST_DIR"
    mkdir -p "$BUILD_DIR"

    # 构建参数
    local PYINSTALLER_CMD="pyinstaller"
    local NAME_ARG="--name ${CLIENT_NAME}-windows"
    local MODE_ARG="--onefile"
    local WINDOWED_ARG="--windowed"
    local CLEAN_ARG="--clean"
    local ICON_ARG="--icon=assets/icon.ico"
    local SCRIPT_ARG="client.py"
    local LOG_FILE="$BUILD_DIR/windows-build.log"

    # 检查图标文件
    if [ ! -f "$SCRIPT_DIR/assets/icon.ico" ]; then
        print_warn "未找到图标文件，跳过图标"
        ICON_ARG=""
    fi

    print_step "开始打包..."

    # 执行打包
    $PYINSTALLER_CMD \
        $NAME_ARG \
        $MODE_ARG \
        $WINDOWED_ARG \
        $(get_collect_modules) \
        $(get_hidden_imports) \
        $(get_exclude_modules) \
        $CLEAN_ARG \
        $ICON_ARG \
        $SCRIPT_ARG 2>&1 | tee "$LOG_FILE"

    # 处理输出文件
    # PyInstaller 在 --onefile 模式下的实际输出路径
    local SRC_EXE="$DIST_DIR/${CLIENT_NAME}-windows"
    local DST_EXE="$DIST_DIR/${CLIENT_NAME}-windows.exe"

    # 如果源文件存在，重命名为 .exe 扩展名
    if [ -f "$SRC_EXE" ]; then
        mv "$SRC_EXE" "$DST_EXE" 2>/dev/null || true
    fi

    # 显示结果
    if [ -f "$DST_EXE" ]; then
        print_info "Windows 客户端打包成功!"
        echo ""
        echo -e "${GREEN}输出文件:${NC}"
        ls -lh "$DST_EXE"
        echo ""
        echo -e "${BLUE}[提示]${NC} 可直接拷贝到 Windows 系统运行"
    else
        print_warn "打包可能未完成，请检查日志: $LOG_FILE"
        return 1
    fi
}

# 构建 Windows 客户端（目录模式）
build_directory() {
    print_step "构建 Windows 客户端（目录模式）..."

    # 环境检查
    if ! check_pyinstaller_env; then
        print_error "PyInstaller 环境检查失败"
        return 1
    fi

    # 创建目录
    mkdir -p "$DIST_DIR"

    # 构建参数
    local PYINSTALLER_CMD="pyinstaller"
    local NAME_ARG="--name ${CLIENT_NAME}-windows-dir"
    local MODE_ARG="--onedir"
    local CLEAN_ARG="--clean"
    local ICON_ARG="--icon=assets/icon.ico"
    local SCRIPT_ARG="client.py"

    # 检查图标文件
    if [ ! -f "$SCRIPT_DIR/assets/icon.ico" ]; then
        print_warn "未找到图标文件，跳过图标"
        ICON_ARG=""
    fi

    print_step "开始打包（目录模式）..."

    # 执行打包
    $PYINSTALLER_CMD \
        $NAME_ARG \
        $MODE_ARG \
        $(get_hidden_imports) \
        $(get_exclude_modules) \
        $CLEAN_ARG \
        $ICON_ARG \
        $SCRIPT_ARG

    # 显示结果
    local OUTPUT_DIR="$DIST_DIR/${CLIENT_NAME}-windows-dir"

    if [ -d "$OUTPUT_DIR" ]; then
        print_info "Windows 客户端打包成功!"
        echo ""
        echo -e "${GREEN}输出目录:${NC}"
        ls -ld "$OUTPUT_DIR"
        echo ""

        echo -e "${BLUE}[提示]${NC} 需要整个目录一起拷贝到 Windows 系统"
    else
        print_warn "打包可能未完成"
        return 1
    fi
}

# 检查构建环境
check_build_env() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  Windows 客户端构建环境检查${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""

    # 检查 Python
    print_step "检查 Python..."
    if command -v python3 &> /dev/null; then
        print_info "Python 已安装: $(python3 --version)"
    else
        print_error "Python 未安装"
    fi

    # 检查 PyInstaller
    print_step "检查 PyInstaller..."
    if check_pyinstaller_installed; then
        print_info "PyInstaller 已安装: $PYINSTALLER"
    else
        print_error "PyInstaller 未安装"
        echo ""
        echo "请先运行: ./setup-windows-build-env.sh install"
    fi

    echo ""
    echo -e "${BLUE}[提示]${NC} 使用 ./build-windows-client.sh 构建客户端"
}

# 显示帮助信息
show_help() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  SMTP 隧道代理 - Windows 客户端构建脚本${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    echo "用法: $0 <命令> [选项]"
    echo ""
    echo "命令:"
    echo "          构建 Windows 客户端（单文件模式，默认）"
    echo "  dir     构建 Windows 客户端（目录模式）"
    echo "  check   检查构建环境"
    echo "  help    显示此帮助信息"
    echo ""
    echo "选项:"
    echo "  --debug      启用调试模式"
    echo ""
    echo "示例:"
    echo "  $0                    # 单文件模式"
    echo "  $0 dir                # 目录模式"
    echo "  $0 check              # 检查环境"
    echo ""
    echo "前提条件:"
    echo "  1. 安装 Python 3: sudo apt install python3 python3-pip"
    echo "  2. 安装 PyInstaller: ./setup-windows-build-env.sh install"
    echo ""
    echo "输出位置:"
    echo "  单文件模式: dist/${CLIENT_NAME}-windows.exe"
    echo "  目录模式:   dist/${CLIENT_NAME}-windows-dir/"
}

# 主函数
main() {
    local command="${1:-build}"
    shift 2>/dev/null || true

    # 解析选项
    while [ $# -gt 0 ]; do
        case "$1" in
            --debug)
                DEBUG="true"
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

    # 检查脚本是否在正确的目录运行
    if [ ! -f "$SCRIPT_DIR/client.py" ]; then
        print_error "未找到 client.py，请确保在项目根目录运行此脚本"
        exit 1
    fi

    case "$command" in
        build|"")
            build_onefile
            ;;
        dir)
            build_directory
            ;;
        check)
            check_build_env
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
