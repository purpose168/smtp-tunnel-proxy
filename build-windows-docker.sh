#!/bin/bash
#
# SMTP 隧道代理 - Docker Windows 编译脚本
#
# 使用 Docker + QEMU + Windows 环境进行 Python 程序编译
# 基于 dockur/windows 项目实现方式
#
# 功能:
#   1. 使用 Docker 运行完整 Windows 系统
#   2. 在 Windows 环境中安装 Python 和依赖
#   3. 使用 PyInstaller 构建独立的 Windows 可执行文件
#   4. 自动处理依赖项和打包配置
#   5. 生成独立的可执行文件（不依赖外部 Python 环境）
#
# 使用方法:
#   ./build-windows-docker.sh              # 构建单文件模式
#   ./build-windows-docker.sh dir        # 构建目录模式
#   ./build-windows-docker.sh clean       # 清理 Docker 镜像
#
# 依赖:
#   - Docker (已安装并运行）
#   - 支持虚拟化的 CPU
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
PYTHON_VERSION="3.12"
# 使用 dockur/windows 作为基础镜像
DOCKER_IMAGE="dockurr/windows:latest"
DOCKER_CONTAINER="smtp-tunnel-builder"
# Windows 相关配置
WINDOWS_USER="Administrator"
WINDOWS_PASS="Password123!"
# 构建配置
BUILD_TIMEOUT=3600  # 构建超时时间（秒）

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

# 检查 Docker 是否安装
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker 未安装"
        echo ""
        echo "请先安装 Docker:"
        echo "  Ubuntu/Debian: sudo apt install docker.io"
        echo "  Fedora: sudo dnf install docker"
        echo "  Arch: sudo pacman -S docker"
        echo ""
        echo "安装后请确保 Docker 服务已启动:"
        echo "  sudo systemctl start docker"
        echo "  sudo usermod -aG docker \$USER"
        echo ""
        echo "然后重新登录或重启以应用组权限"
        return 1
    fi

    if ! docker info &> /dev/null; then
        print_error "Docker 服务未运行"
        echo ""
        echo "请启动 Docker 服务:"
        echo "  sudo systemctl start docker"
        return 1
    fi

    return 0
}

# 准备构建环境
prepare_build_env() {
    print_step "准备构建环境..."
    
    # 创建必要的目录
    mkdir -p "$DIST_DIR"
    mkdir -p "$BUILD_DIR"
    
    # 复制项目文件到构建目录
    cp -r "$PROJECT_DIR"/* "$BUILD_DIR/" 2>/dev/null || true
    
    # 创建 Windows 构建脚本
    cat > "${BUILD_DIR}/build_win.bat" << 'EOF'
@echo off
setlocal enabledelayedexpansion

REM 设置工作目录
cd /d %~dp0

REM 下载并安装 Python
if not exist "python-installer.exe" (
    echo Downloading Python %PYTHON_VERSION%...
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-amd64.exe' -OutFile 'python-installer.exe'"
)

echo Installing Python %PYTHON_VERSION%...
python-installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0

REM 验证 Python 安装
echo Verifying Python installation...
python --version
pip --version

REM 升级 pip
echo Upgrading pip...
pip install --upgrade pip

REM 安装依赖
echo Installing dependencies...
pip install pyinstaller cryptography pyyaml

REM 构建可执行文件
if "%BUILD_MODE%" == "onefile" (
    echo Building onefile executable...
    pyinstaller --onefile --windowed --name "%CLIENT_NAME%-windows" --collect-all common --collect-all client_protocol --collect-all client_socks5 --collect-all client_tunnel --collect-all client_server --hidden-import=asyncio --hidden-import=ssl --hidden-import=cryptography --hidden-import=yaml --hidden-import=_cffi_backend --exclude-module=tkinter --exclude-module=test --exclude-module=unittest --exclude-module=pydoc --clean client.py
) else (
    echo Building directory executable...
    pyinstaller --onedir --windowed --name "%CLIENT_NAME%-windows-dir" --collect-all common --collect-all client_protocol --collect-all client_socks5 --collect-all client_tunnel --collect-all client_server --hidden-import=asyncio --hidden-import=ssl --hidden-import=cryptography --hidden-import=yaml --clean client.py
)

REM 检查构建结果
if exist "dist\*.exe" (
    echo Build successful!
    echo Executable files:
    dir dist\*.exe
    exit 0
) else if exist "dist\*\*.exe" (
    echo Build successful!
    echo Executable directory:
    dir dist
    exit 0
) else (
    echo Build failed!
    exit 1
)
EOF
    
    print_info "构建环境准备完成"
}

# 构建 Windows 客户端（单文件模式）
build_onefile() {
    print_step "构建 Windows 客户端（单文件模式）..."

    # 检查 Docker
    check_docker || return 1

    # 准备构建环境
    prepare_build_env || return 1

    # 运行 Docker 容器进行构建
    print_step "运行 Windows Docker 容器..."

    # 设置构建模式
    export BUILD_MODE="onefile"
    export CLIENT_NAME="$CLIENT_NAME"
    export PYTHON_VERSION="$PYTHON_VERSION"
    
    # 使用 dockur/windows 镜像运行构建
    # 注意：此方式需要较长时间初始化 Windows 系统
    print_warn "注意：首次运行需要下载并初始化 Windows 系统，可能需要较长时间（30分钟以上）"
    
    # 启动 Windows 容器并运行构建脚本
    # 由于 dockur/windows 主要用于交互式使用，我们采用文件挂载 + 远程执行的方式
    docker run --rm -d \
        --name "$DOCKER_CONTAINER" \
        --platform=linux/amd64 \
        --privileged \
        --device=/dev/kvm \
        -e RAM_SIZE=4G \
        -e CPU_CORES=2 \
        -e DISK_SIZE=20G \
        -e USER="$WINDOWS_USER" \
        -e PASSWORD="$WINDOWS_PASS" \
        -v "$BUILD_DIR:/app" \
        "$DOCKER_IMAGE" > /dev/null 2>&1
    
    if [ $? -ne 0 ]; then
        print_error "无法启动 Windows 容器"
        return 1
    fi
    
    print_info "Windows 容器启动成功，正在初始化..."
    
    # 等待容器初始化（30秒）
    sleep 30
    
    # 检查容器状态
    if ! docker ps | grep -q "$DOCKER_CONTAINER"; then
        print_error "Windows 容器启动失败"
        return 1
    fi
    
    print_info "Windows 容器正在运行，开始构建过程..."
    
    # 完整实现：在 Windows 容器中启用 SSH 服务并执行构建
    print_info "在 Windows 容器中启用 SSH 服务..."
    
    # 等待 Windows 系统完全启动（最多120秒）
    print_info "等待 Windows 系统完全启动..."
    local max_wait=120
    local wait_count=0
    local ssh_ready=false
    
    while [ $wait_count -lt $max_wait ]; do
        # 检查 SSH 服务是否可用
        if docker exec -i "$DOCKER_CONTAINER" powershell -Command "Get-Service -Name sshd" > /dev/null 2>&1; then
            ssh_ready=true
            break
        fi
        
        wait_count=$((wait_count + 5))
        sleep 5
        print_info "等待中... ($wait_count/$max_wait 秒)"
    done
    
    if [ "$ssh_ready" = false ]; then
        print_error "Windows 容器 SSH 服务未准备就绪，超时退出"
        docker stop "$DOCKER_CONTAINER" > /dev/null 2>&1 || true
        return 1
    fi
    
    print_info "Windows 系统已完全启动，配置 SSH 服务..."
    
    # 在 Windows 容器中配置 SSH 服务
    docker exec -i "$DOCKER_CONTAINER" powershell -Command " \
        # 检查 SSH 服务状态
        $sshdService = Get-Service -Name sshd -ErrorAction SilentlyContinue; \
        if (-not $sshdService) { \
            # 安装 SSH 服务器 \
            Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0; \
            # 启动 SSH 服务 \
            Start-Service -Name sshd; \
            # 设置为自动启动 \
            Set-Service -Name sshd -StartupType Automatic; \
            # 配置防火墙规则 \
            New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22; \
        } else { \
            # 确保 SSH 服务正在运行 \
            if ($sshdService.Status -ne 'Running') { \
                Start-Service -Name sshd; \
            } \
        } \
    " > /dev/null 2>&1
    
    if [ $? -ne 0 ]; then
        print_error "在 Windows 容器中配置 SSH 服务失败"
        docker stop "$DOCKER_CONTAINER" > /dev/null 2>&1 || true
        return 1
    fi
    
    print_info "SSH 服务已配置完成，执行构建脚本..."
    
    # 执行构建脚本
    print_info "在 Windows 容器中执行构建脚本..."
    
    # 复制构建脚本到 Windows 容器
    docker cp "${BUILD_DIR}/build_win.bat" "$DOCKER_CONTAINER:/app/build_win.bat" > /dev/null 2>&1
    
    if [ $? -ne 0 ]; then
        print_error "无法将构建脚本复制到 Windows 容器"
        docker stop "$DOCKER_CONTAINER" > /dev/null 2>&1 || true
        return 1
    fi
    
    # 在 Windows 容器中执行构建脚本
    docker exec -i "$DOCKER_CONTAINER" powershell -Command " \
        # 设置构建环境变量 \
        $env:BUILD_MODE = '$BUILD_MODE'; \
        $env:CLIENT_NAME = '$CLIENT_NAME'; \
        $env:PYTHON_VERSION = '$PYTHON_VERSION'; \
        # 切换到工作目录 \
        Set-Location -Path C:\app; \
        # 执行构建脚本 \
        .\build_win.bat > build.log 2>&1; \
        # 返回构建结果 \
        exit $LASTEXITCODE; \
    "
    
    local build_exit_code=$?
    
    # 获取构建日志
    docker cp "$DOCKER_CONTAINER:/app/build.log" "$BUILD_DIR/build.log" > /dev/null 2>&1
    
    if [ $build_exit_code -ne 0 ]; then
        print_error "Windows 容器中构建失败，查看日志: $BUILD_DIR/build.log"
        print_info "构建日志摘要:"
        tail -50 "$BUILD_DIR/build.log"
        docker stop "$DOCKER_CONTAINER" > /dev/null 2>&1 || true
        return 1
    fi
    
    print_info "Windows 容器中构建成功，获取构建结果..."
    
    # 复制构建结果到宿主系统
    if [ "$BUILD_MODE" = "onefile" ]; then
        docker cp "$DOCKER_CONTAINER:/app/dist/${CLIENT_NAME}-windows.exe" "$DIST_DIR/" > /dev/null 2>&1
    else
        docker cp -r "$DOCKER_CONTAINER:/app/dist/${CLIENT_NAME}-windows-dir" "$DIST_DIR/" > /dev/null 2>&1
    fi
    
    if [ $? -ne 0 ]; then
        print_error "无法获取构建结果"
        docker stop "$DOCKER_CONTAINER" > /dev/null 2>&1 || true
        return 1
    fi
    
    print_info "构建结果已成功获取到宿主系统"
    
    # 停止 Windows 容器
    docker stop "$DOCKER_CONTAINER" > /dev/null 2>&1 || true
    
    # 显示结果
    if [ "$BUILD_MODE" = "onefile" ]; then
        if [ -f "$DIST_DIR/${CLIENT_NAME}-windows.exe" ]; then
            print_info "Windows 客户端单文件打包成功!"
            echo ""
            echo -e "${GREEN}输出文件:${NC}"
            ls -lh "$DIST_DIR/${CLIENT_NAME}-windows.exe"
            echo ""
            echo -e "${BLUE}[提示]${NC} 可直接拷贝到 Windows 系统运行"
        else
            print_error "单文件构建结果未找到"
            return 1
        fi
    else
        if [ -d "$DIST_DIR/${CLIENT_NAME}-windows-dir" ]; then
            print_info "Windows 客户端目录打包成功!"
            echo ""
            echo -e "${GREEN}输出目录:${NC}"
            ls -ld "$DIST_DIR/${CLIENT_NAME}-windows-dir"
            echo ""
            echo -e "${BLUE}[提示]${NC} 需要整个目录一起拷贝到 Windows 系统"
        else
            print_error "目录构建结果未找到"
            return 1
        fi
    fi
}

# 构建 Windows 客户端（目录模式）
build_directory() {
    print_step "构建 Windows 客户端（目录模式）..."

    # 检查 Docker
    check_docker || return 1

    # 准备构建环境
    prepare_build_env || return 1

    # 运行 Docker 容器进行构建
    print_step "运行 Windows Docker 容器..."

    # 设置构建模式
    export BUILD_MODE="directory"
    export CLIENT_NAME="$CLIENT_NAME"
    export PYTHON_VERSION="$PYTHON_VERSION"
    
    print_warn "注意：首次运行需要下载并初始化 Windows 系统，可能需要较长时间（30分钟以上）"
    
    # 启动 Windows 容器并运行构建脚本
    docker run --rm -d \
        --name "$DOCKER_CONTAINER" \
        --platform=linux/amd64 \
        --privileged \
        --device=/dev/kvm \
        -e RAM_SIZE=4G \
        -e CPU_CORES=2 \
        -e DISK_SIZE=20G \
        -e USER="$WINDOWS_USER" \
        -e PASSWORD="$WINDOWS_PASS" \
        -v "$BUILD_DIR:/app" \
        "$DOCKER_IMAGE" > /dev/null 2>&1
    
    if [ $? -ne 0 ]; then
        print_error "无法启动 Windows 容器"
        return 1
    fi
    
    print_info "Windows 容器启动成功，正在初始化..."
    
    # 等待容器初始化（30秒）
    sleep 30
    
    # 检查容器状态
    if ! docker ps | grep -q "$DOCKER_CONTAINER"; then
        print_error "Windows 容器启动失败"
        return 1
    fi
    
    print_info "Windows 容器正在运行，开始构建过程..."
    
    # 完整实现：在 Windows 容器中启用 SSH 服务并执行构建
    print_info "在 Windows 容器中启用 SSH 服务..."
    
    # 等待 Windows 系统完全启动（最多120秒）
    print_info "等待 Windows 系统完全启动..."
    local max_wait=120
    local wait_count=0
    local ssh_ready=false
    
    while [ $wait_count -lt $max_wait ]; do
        # 检查 SSH 服务是否可用
        if docker exec -i "$DOCKER_CONTAINER" powershell -Command "Get-Service -Name sshd" > /dev/null 2>&1; then
            ssh_ready=true
            break
        fi
        
        wait_count=$((wait_count + 5))
        sleep 5
        print_info "等待中... ($wait_count/$max_wait 秒)"
    done
    
    if [ "$ssh_ready" = false ]; then
        print_error "Windows 容器 SSH 服务未准备就绪，超时退出"
        docker stop "$DOCKER_CONTAINER" > /dev/null 2>&1 || true
        return 1
    fi
    
    print_info "Windows 系统已完全启动，配置 SSH 服务..."
    
    # 在 Windows 容器中配置 SSH 服务
    docker exec -i "$DOCKER_CONTAINER" powershell -Command " \
        # 检查 SSH 服务状态
        $sshdService = Get-Service -Name sshd -ErrorAction SilentlyContinue; \
        if (-not $sshdService) { \
            # 安装 SSH 服务器 \
            Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0; \
            # 启动 SSH 服务 \
            Start-Service -Name sshd; \
            # 设置为自动启动 \
            Set-Service -Name sshd -StartupType Automatic; \
            # 配置防火墙规则 \
            New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22; \
        } else { \
            # 确保 SSH 服务正在运行 \
            if ($sshdService.Status -ne 'Running') { \
                Start-Service -Name sshd; \
            } \
        } \
    " > /dev/null 2>&1
    
    if [ $? -ne 0 ]; then
        print_error "在 Windows 容器中配置 SSH 服务失败"
        docker stop "$DOCKER_CONTAINER" > /dev/null 2>&1 || true
        return 1
    fi
    
    print_info "SSH 服务已配置完成，执行构建脚本..."
    
    # 执行构建脚本
    print_info "在 Windows 容器中执行构建脚本..."
    
    # 复制构建脚本到 Windows 容器
    docker cp "${BUILD_DIR}/build_win.bat" "$DOCKER_CONTAINER:/app/build_win.bat" > /dev/null 2>&1
    
    if [ $? -ne 0 ]; then
        print_error "无法将构建脚本复制到 Windows 容器"
        docker stop "$DOCKER_CONTAINER" > /dev/null 2>&1 || true
        return 1
    fi
    
    # 在 Windows 容器中执行构建脚本
    docker exec -i "$DOCKER_CONTAINER" powershell -Command " \
        # 设置构建环境变量 \
        $env:BUILD_MODE = '$BUILD_MODE'; \
        $env:CLIENT_NAME = '$CLIENT_NAME'; \
        $env:PYTHON_VERSION = '$PYTHON_VERSION'; \
        # 切换到工作目录 \
        Set-Location -Path C:\app; \
        # 执行构建脚本 \
        .\build_win.bat > build.log 2>&1; \
        # 返回构建结果 \
        exit $LASTEXITCODE; \
    "
    
    local build_exit_code=$?
    
    # 获取构建日志
    docker cp "$DOCKER_CONTAINER:/app/build.log" "$BUILD_DIR/build.log" > /dev/null 2>&1
    
    if [ $build_exit_code -ne 0 ]; then
        print_error "Windows 容器中构建失败，查看日志: $BUILD_DIR/build.log"
        print_info "构建日志摘要:"
        tail -50 "$BUILD_DIR/build.log"
        docker stop "$DOCKER_CONTAINER" > /dev/null 2>&1 || true
        return 1
    fi
    
    print_info "Windows 容器中构建成功，获取构建结果..."
    
    # 复制构建结果到宿主系统
    if [ "$BUILD_MODE" = "onefile" ]; then
        docker cp "$DOCKER_CONTAINER:/app/dist/${CLIENT_NAME}-windows.exe" "$DIST_DIR/" > /dev/null 2>&1
    else
        docker cp -r "$DOCKER_CONTAINER:/app/dist/${CLIENT_NAME}-windows-dir" "$DIST_DIR/" > /dev/null 2>&1
    fi
    
    if [ $? -ne 0 ]; then
        print_error "无法获取构建结果"
        docker stop "$DOCKER_CONTAINER" > /dev/null 2>&1 || true
        return 1
    fi
    
    print_info "构建结果已成功获取到宿主系统"
    
    # 停止 Windows 容器
    docker stop "$DOCKER_CONTAINER" > /dev/null 2>&1 || true
    
    # 显示结果
    if [ "$BUILD_MODE" = "onefile" ]; then
        if [ -f "$DIST_DIR/${CLIENT_NAME}-windows.exe" ]; then
            print_info "Windows 客户端单文件打包成功!"
            echo ""
            echo -e "${GREEN}输出文件:${NC}"
            ls -lh "$DIST_DIR/${CLIENT_NAME}-windows.exe"
            echo ""
            echo -e "${BLUE}[提示]${NC} 可直接拷贝到 Windows 系统运行"
        else
            print_error "单文件构建结果未找到"
            return 1
        fi
    else
        if [ -d "$DIST_DIR/${CLIENT_NAME}-windows-dir" ]; then
            print_info "Windows 客户端目录打包成功!"
            echo ""
            echo -e "${GREEN}输出目录:${NC}"
            ls -ld "$DIST_DIR/${CLIENT_NAME}-windows-dir"
            echo ""
            echo -e "${BLUE}[提示]${NC} 需要整个目录一起拷贝到 Windows 系统"
        else
            print_error "目录构建结果未找到"
            return 1
        fi
    fi
}

# 清理 Docker 资源
clean_docker() {
    print_step "清理 Docker 资源..."

    # 停止并删除构建容器
    if docker ps -a | grep -q "$DOCKER_CONTAINER"; then
        print_info "停止并删除构建容器: $DOCKER_CONTAINER"
        docker rm -f "$DOCKER_CONTAINER" > /dev/null 2>&1
    fi

    # 可选：删除 dockur/windows 镜像（如果需要）
    print_warn "注意：dockur/windows 镜像较大（约10GB），建议保留以加快后续构建速度"
    
    # 清理构建目录
    if [ -d "$BUILD_DIR" ]; then
        print_info "清理构建目录: $BUILD_DIR"
        rm -rf "$BUILD_DIR"/*
    fi
    
    print_info "Docker 资源清理完成"
}

# 显示帮助信息
show_help() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  SMTP 隧道代理 - Docker Windows 编译脚本${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    echo "用法: $0 <命令>"
    echo ""
    echo "命令:"
    echo "          构建 Windows 客户端（单文件模式，默认）"
    echo "  dir     构建 Windows 客户端（目录模式）"
    echo "  clean   清理 Docker 资源"
    echo "  help    显示此帮助信息"
    echo ""
    echo "前提条件:"
    echo "  1. 安装 Docker: sudo apt install docker.io"
    echo "  2. 启动 Docker 服务: sudo systemctl start docker"
    echo "  3. 添加用户到 docker 组: sudo usermod -aG docker \$USER"
    echo "  4. 支持虚拟化的 CPU（启用 KVM）"
    echo ""
    echo "输出位置:"
    echo "  单文件模式: dist/${CLIENT_NAME}-windows.exe"
    echo "  目录模式:   dist/${CLIENT_NAME}-windows-dir/"
    echo ""
    echo "核心实现:"
    echo "  - 基于 dockur/windows 项目（Docker + QEMU + Windows）"
    echo "  - 在 Windows 环境中安装 Python 和依赖"
    echo "  - 使用 PyInstaller 构建独立可执行文件"
    echo "  - 生成的可执行文件不依赖外部 Python 环境"
    echo ""
    echo "注意事项:"
    echo "  - 首次运行需要下载并初始化 Windows 系统，可能需要较长时间（30分钟以上）"
    echo "  - Windows 镜像较大（约10GB），建议保留以加快后续构建速度"
    echo "  - 构建过程中会自动处理所有依赖项"
}

# 主函数
main() {
    local command="${1:-build}"
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
            build_onefile
            ;;
        dir)
            build_directory
            ;;
        clean)
            clean_docker
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
