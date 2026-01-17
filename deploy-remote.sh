#!/bin/bash
#
# SMTP Tunnel Proxy - 远程部署脚本
# ============================================================================
# 功能说明：
# 1. 远程部署 - 部署发布包到远程服务器
# 2. 部署前备份 - 自动备份现有部署
# 3. 部署后健康检查 - 验证部署成功
# 4. 回滚部署 - 回滚到上一个版本
# ============================================================================

set -euo pipefail

# ============================================================================
# 配置区域 - 可根据需要修改
# ============================================================================

# 工作区路径（自动检测）
WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 版本配置
VERSION_FILE="${WORKSPACE_DIR}/.version"
RELEASE_DIR="${WORKSPACE_DIR}/release"

# 远程服务器配置
REMOTE_SERVER=""
REMOTE_USER="root"
REMOTE_PORT="22"
REMOTE_DEPLOY_DIR="/opt/smtp-tunnel"
REMOTE_CONFIG_DIR="/opt/smtp-tunnel/config"
REMOTE_LOG_DIR="/var/log/smtp-tunnel"

# 日志配置
LOG_DIR="${WORKSPACE_DIR}/logs"
LOG_FILE="${LOG_DIR}/deploy-remote.log"

# ============================================================================
# 颜色定义
# ============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ============================================================================
# 函数定义
# ============================================================================

# 打印信息消息
log_info() {
    local message="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${BLUE}[INFO]${NC} ${timestamp} - ${message}" | tee -a "${LOG_FILE}"
}

# 打印成功消息
log_success() {
    local message="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${GREEN}[SUCCESS]${NC} ${timestamp} - ${message}" | tee -a "${LOG_FILE}"
}

# 打印警告消息
log_warning() {
    local message="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${YELLOW}[WARNING]${NC} ${timestamp} - ${message}" | tee -a "${LOG_FILE}"
}

# 打印错误消息
log_error() {
    local message="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${RED}[ERROR]${NC} ${timestamp} - ${message}" | tee -a "${LOG_FILE}"
}

# 打印步骤消息
log_step() {
    local message="$1"
    echo -e "${CYAN}[STEP]${NC} ${message}"
}

# 检查命令是否存在
check_command() {
    local cmd="$1"
    if ! command -v "${cmd}" &> /dev/null; then
        log_error "命令 '${cmd}' 未找到，请先安装"
        return 1
    fi
    return 0
}

# 检查文件是否存在
check_file() {
    local file="$1"
    if [ ! -f "${file}" ]; then
        log_error "文件不存在: ${file}"
        return 1
    fi
    return 0
}

# 获取当前版本
get_version() {
    if [ -f "${VERSION_FILE}" ]; then
        cat "${VERSION_FILE}"
    else
        echo "1.0.0"
    fi
}

# 创建必要的目录
create_directories() {
    log_step "创建必要的目录..."
    
    mkdir -p "${LOG_DIR}"
    mkdir -p "$(dirname "${LOG_FILE}")"
    
    log_info "目录创建完成"
}

# 测试 SSH 连接
test_ssh_connection() {
    log_step "测试 SSH 连接..."
    
    if [ -z "${REMOTE_SERVER}" ]; then
        log_error "远程服务器地址未配置"
        log_info "请设置 REMOTE_SERVER 环境变量"
        return 1
    fi
    
    if ! ssh -p "${REMOTE_PORT}" -o ConnectTimeout=10 "${REMOTE_USER}@${REMOTE_SERVER}" "echo 'Connection successful'" 2>&1 | tee -a "${LOG_FILE}"; then
        log_error "SSH 连接失败"
        return 1
    fi
    
    log_success "SSH 连接成功"
    return 0
}

# 备份远程部署
backup_remote_deployment() {
    log_step "备份远程部署..."
    
    ssh -p "${REMOTE_PORT}" "${REMOTE_USER}@${REMOTE_SERVER}" << EOF 2>&1 | tee -a "${LOG_FILE}"
# 创建备份目录
mkdir -p ${REMOTE_DEPLOY_DIR}/backups

# 备份时间戳
TIMESTAMP=\$(date +%Y%m%d_%H%M%S)

# 备份配置文件
if [ -f "${REMOTE_CONFIG_DIR}/config.yaml" ]; then
    cp "${REMOTE_CONFIG_DIR}/config.yaml" "${REMOTE_DEPLOY_DIR}/backups/config.yaml.\${TIMESTAMP}"
    echo "配置文件已备份"
fi

if [ -f "${REMOTE_CONFIG_DIR}/users.yaml" ]; then
    cp "${REMOTE_CONFIG_DIR}/users.yaml" "${REMOTE_DEPLOY_DIR}/backups/users.yaml.\${TIMESTAMP}"
    echo "用户文件已备份"
fi

# 备份日志
if [ -d "${REMOTE_LOG_DIR}" ]; then
    mkdir -p ${REMOTE_DEPLOY_DIR}/backups/logs.\${TIMESTAMP}
    cp -r ${REMOTE_LOG_DIR}/* ${REMOTE_DEPLOY_DIR}/backups/logs.\${TIMESTAMP}/ 2>/dev/null || true
    echo "日志已备份"
fi

# 清理旧备份（保留最近 7 天）
find ${REMOTE_DEPLOY_DIR}/backups -type f -mtime +7 -delete 2>/dev/null || true
find ${REMOTE_DEPLOY_DIR}/backups -type d -mtime +7 -delete 2>/dev/null || true

echo "远程备份完成"
EOF
    
    if [ $? -eq 0 ]; then
        log_success "远程备份成功"
        return 0
    else
        log_error "远程备份失败"
        return 1
    fi
}

# 部署到远程服务器
deploy_to_remote() {
    local package_file="$1"
    
    log_step "部署到远程服务器..."
    
    # 检查远程服务器配置
    if [ -z "${REMOTE_SERVER}" ]; then
        log_error "远程服务器地址未配置"
        log_info "请设置 REMOTE_SERVER 环境变量"
        return 1
    fi
    
    # 检查发布包文件
    if [ ! -f "${package_file}" ]; then
        log_error "发布包不存在: ${package_file}"
        log_info "请先运行 deploy-server.sh --package 创建发布包"
        return 1
    fi
    
    # 测试 SSH 连接
    if ! test_ssh_connection; then
        return 1
    fi
    
    # 部署前备份
    if ! backup_remote_deployment; then
        log_error "远程备份失败，取消部署"
        return 1
    fi
    
    # 上传发布包
    log_info "上传发布包..."
    if ! scp -P "${REMOTE_PORT}" "${package_file}" "${REMOTE_USER}@${REMOTE_SERVER}:/tmp/" 2>&1 | tee -a "${LOG_FILE}"; then
        log_error "上传失败"
        return 1
    fi
    
    log_success "上传成功"
    
    # 执行远程部署
    log_info "执行远程部署..."
    local package_name=$(basename "${package_file}")
    
    ssh -p "${REMOTE_PORT}" "${REMOTE_USER}@${REMOTE_SERVER}" << EOF 2>&1 | tee -a "${LOG_FILE}"
# 创建临时目录
mkdir -p /tmp/smtp-tunnel-deploy

# 解压发布包
cd /tmp/smtp-tunnel-deploy
tar -xzf /tmp/${package_name}

# 停止服务
systemctl stop smtp-tunnel 2>/dev/null || true

# 备份现有部署
if [ -d "${REMOTE_DEPLOY_DIR}" ]; then
    mv "${REMOTE_DEPLOY_DIR}" "${REMOTE_DEPLOY_DIR}.backup.\$(date +%Y%m%d_%H%M%S)"
fi

# 创建部署目录
mkdir -p "${REMOTE_DEPLOY_DIR}"

# 复制文件
cp -r /tmp/smtp-tunnel-deploy/* "${REMOTE_DEPLOY_DIR}/"

# 设置权限
chmod +x ${REMOTE_DEPLOY_DIR}/*.sh
chmod 600 ${REMOTE_DEPLOY_DIR}/config.yaml
chmod 600 ${REMOTE_DEPLOY_DIR}/users.yaml

# 清理临时目录
rm -rf /tmp/smtp-tunnel-deploy
rm -f /tmp/${package_name}

# 启动服务
systemctl start smtp-tunnel

# 检查服务状态
sleep 5
if systemctl is-active --quiet smtp-tunnel; then
    echo "服务启动成功"
else
    echo "服务启动失败"
    exit 1
fi
EOF
    
    if [ $? -eq 0 ]; then
        log_success "远程部署成功"
        return 0
    else
        log_error "远程部署失败"
        return 1
    fi
}

# 部署后健康检查
health_check() {
    log_step "执行健康检查..."
    
    if [ -z "${REMOTE_SERVER}" ]; then
        log_warning "未配置远程服务器，跳过远程健康检查"
        return 0
    fi
    
    # 检查服务状态
    log_info "检查服务状态..."
    local service_status=$(ssh -p "${REMOTE_PORT}" "${REMOTE_USER}@${REMOTE_SERVER}" "systemctl is-active smtp-tunnel" 2>&1)
    
    if [ "${service_status}" = "active" ]; then
        log_success "服务状态: active"
    else
        log_error "服务状态: ${service_status}"
        return 1
    fi
    
    # 检查端口监听
    log_info "检查端口监听..."
    local port_status=$(ssh -p "${REMOTE_PORT}" "${REMOTE_USER}@${REMOTE_SERVER}" "nc -z localhost 587 2>&1 && echo 'listening' || echo 'not listening'" 2>&1)
    
    if [ "${port_status}" = "listening" ]; then
        log_success "端口 587: listening"
    else
        log_error "端口 587: ${port_status}"
        return 1
    fi
    
    # 检查配置文件
    log_info "检查配置文件..."
    local config_status=$(ssh -p "${REMOTE_PORT}" "${REMOTE_USER}@${REMOTE_SERVER}" "[ -f ${REMOTE_CONFIG_DIR}/config.yaml ] && echo 'exists' || echo 'missing'" 2>&1)
    
    if [ "${config_status}" = "exists" ]; then
        log_success "配置文件: exists"
    else
        log_error "配置文件: missing"
        return 1
    fi
    
    # 检查日志
    log_info "检查日志..."
    local log_status=$(ssh -p "${REMOTE_PORT}" "${REMOTE_USER}@${REMOTE_SERVER}" "[ -d ${REMOTE_LOG_DIR} ] && echo 'exists' || echo 'missing'" 2>&1)
    
    if [ "${log_status}" = "exists" ]; then
        log_success "日志目录: exists"
    else
        log_warning "日志目录: missing"
    fi
    
    log_success "健康检查通过"
    return 0
}

# 回滚部署
rollback_deployment() {
    log_step "回滚部署..."
    
    if [ -z "${REMOTE_SERVER}" ]; then
        log_error "未配置远程服务器"
        return 1
    fi
    
    ssh -p "${REMOTE_PORT}" "${REMOTE_USER}@${REMOTE_SERVER}" << EOF 2>&1 | tee -a "${LOG_FILE}"
# 停止服务
systemctl stop smtp-tunnel 2>/dev/null || true

# 查找最近的备份
LATEST_BACKUP=\$(find ${REMOTE_DEPLOY_DIR}/backups -type d -name "backup.*" -printf '%T@ %p\n' 2>/dev/null | sort -n | head -1 | cut -d' ' -f2-)

if [ -z "\${LATEST_BACKUP}" ]; then
    echo "未找到备份"
    exit 1
fi

echo "回滚到: \${LATEST_BACKUP}"

# 删除当前部署
rm -rf ${REMOTE_DEPLOY_DIR}

# 恢复备份
mv "\${LATEST_BACKUP}" ${REMOTE_DEPLOY_DIR}

# 启动服务
systemctl start smtp-tunnel

# 检查服务状态
sleep 5
if systemctl is-active --quiet smtp-tunnel; then
    echo "服务启动成功"
else
    echo "服务启动失败"
    exit 1
fi

echo "回滚完成"
EOF
    
    if [ $? -eq 0 ]; then
        log_success "回滚成功"
        return 0
    else
        log_error "回滚失败"
        return 1
    fi
}

# 显示帮助信息
show_help() {
    cat << EOF
SMTP Tunnel Proxy - 远程部署脚本

用法: $(basename "$0") [选项]

选项:
  --deploy <package_file>    部署发布包到远程服务器
  --backup                  备份远程部署
  --health-check            执行健康检查
  --rollback               回滚到上一个版本
  -h, --help               显示此帮助信息

环境变量:
  REMOTE_SERVER            远程服务器地址（必需）
  REMOTE_USER              远程用户名（默认: root）
  REMOTE_PORT              远程端口（默认: 22）
  REMOTE_DEPLOY_DIR        远程部署目录（默认: /opt/smtp-tunnel）
  REMOTE_CONFIG_DIR        远程配置目录（默认: /opt/smtp-tunnel/config）
  REMOTE_LOG_DIR           远程日志目录（默认: /var/log/smtp-tunnel）

示例:
  $(basename "$0") --deploy release/smtp-tunnel-proxy-1.0.0.tar.gz
  $(basename "$0") --deploy release/smtp-tunnel-proxy-1.0.0.tar.gz --health-check
  $(basename "$0") --backup
  $(basename "$0") --health-check
  $(basename "$0") --rollback
  REMOTE_SERVER=192.168.1.100 $(basename "$0") --deploy release/smtp-tunnel-proxy-1.0.0.tar.gz

注意:
  - 首次部署必须先设置 REMOTE_SERVER 环境变量
  - 部署流程会自动备份现有部署
  - 部署失败时可以使用 --rollback 回滚
  - 所有操作都会记录到日志文件

EOF
}

# ============================================================================
# 主程序
# ============================================================================

main() {
    local action=""
    local package_file=""
    
    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --deploy)
                action="deploy"
                if [ -z "$2" ]; then
                    log_error "请指定发布包文件"
                    show_help
                    exit 1
                fi
                package_file="$2"
                shift 2
                ;;
            --backup)
                action="backup"
                shift
                ;;
            --health-check)
                action="health-check"
                shift
                ;;
            --rollback)
                action="rollback"
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log_error "未知选项: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # 如果没有指定操作，显示帮助
    if [ -z "${action}" ]; then
        show_help
        exit 0
    fi
    
    # 创建必要的目录
    create_directories
    
    # 记录开始时间
    log_info "=========================================="
    log_info "远程部署脚本启动"
    log_info "工作区: ${WORKSPACE_DIR}"
    log_info "远程服务器: ${REMOTE_SERVER}"
    log_info "操作: ${action}"
    log_info "=========================================="
    
    # 执行相应的操作
    case ${action} in
        deploy)
            deploy_to_remote "${package_file}"
            ;;
        backup)
            backup_remote_deployment
            ;;
        health-check)
            health_check
            ;;
        rollback)
            rollback_deployment
            ;;
        *)
            log_error "未知操作: ${action}"
            exit 1
            ;;
    esac
    
    # 记录结束时间
    log_info "=========================================="
    log_info "远程部署脚本完成"
    log_info "=========================================="
    
    exit 0
}

# 执行主程序
main "$@"
