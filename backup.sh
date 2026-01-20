#!/bin/bash

# ============================================================================
# 自动备份脚本
# ============================================================================
# 功能说明：
# 1. 增量备份 - 仅备份修改过的文件
# 2. 错误处理 - 完善的异常处理机制
# 3. 日志记录 - 详细的备份日志
# 4. 自定义路径 - 支持自定义备份目标路径
# 5. 周期设置 - 支持定时备份配置
# 6. 压缩加密 - 支持备份文件压缩和加密
# ============================================================================

set -euo pipefail

# ============================================================================
# 配置区域 - 可根据需要修改
# ============================================================================

# 工作区路径（自动检测）
WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 默认备份路径
DEFAULT_BACKUP_DIR="${WORKSPACE_DIR}/backups"

# 备份配置文件
BACKUP_CONFIG="${WORKSPACE_DIR}/.backup_config"

# 日志文件
LOG_FILE="${DEFAULT_BACKUP_DIR}/backup.log"

# 备份文件前缀
BACKUP_PREFIX="smtp-tunnel-backup"

# 备份保留天数
RETENTION_DAYS=30

# 压缩级别（1-9，9为最高压缩率）
COMPRESSION_LEVEL=6

# 是否加密备份文件（true/false）
ENCRYPT_BACKUP=false

# 加密密码文件路径（如果启用加密）
ENCRYPT_PASSWORD_FILE="${WORKSPACE_DIR}/.backup_password"

# rsync 选项
RSYNC_OPTIONS="-avz --progress --delete --exclude-from=${WORKSPACE_DIR}/.backup_exclude"

# ============================================================================
# 颜色定义
# ============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# 检查命令是否存在
check_command() {
    local cmd="$1"
    if ! command -v "${cmd}" &> /dev/null; then
        log_error "命令 '${cmd}' 未找到，请先安装"
        return 1
    fi
    return 0
}

# 创建备份目录
create_backup_dirs() {
    local backup_dir="$1"
    
    if [ ! -d "${backup_dir}" ]; then
        mkdir -p "${backup_dir}"
        log_info "创建备份目录: ${backup_dir}"
    fi
    
    if [ ! -d "${backup_dir}/full" ]; then
        mkdir -p "${backup_dir}/full"
        log_info "创建全量备份目录: ${backup_dir}/full"
    fi
    
    if [ ! -d "${backup_dir}/incremental" ]; then
        mkdir -p "${backup_dir}/incremental"
        log_info "创建增量备份目录: ${backup_dir}/incremental"
    fi
    
    if [ ! -d "${backup_dir}/temp" ]; then
        mkdir -p "${backup_dir}/temp"
        log_info "创建临时目录: ${backup_dir}/temp"
    fi
}

# 创建排除文件
create_exclude_file() {
    local exclude_file="${WORKSPACE_DIR}/.backup_exclude"
    
    cat > "${exclude_file}" << 'EOF'
# Python 缓存文件
__pycache__/
*.py[cod]
*$py.class
*.so

# Git 相关
.git/
.gitignore

# 虚拟环境
.venv/
venv/
env/
ENV/

# IDE 配置
.vscode/
.idea/
*.swp
*.swo
*~

# 日志文件
*.log
logs/
log/

# 临时文件
*.tmp
*.temp
temp/
tmp/
data/

# 客户端包
*.zip
pps/

# 系统文件
.DS_Store
Thumbs.db

# 备份相关
backups/
backup/
*.backup

# Ruby 相关
.ruby-lsp/
.ruby-version

# 构建产物
dist/
build/
*.egg-info/

# 测试覆盖率
.coverage
htmlcov/
.pytest_cache/

# 其他
*.pid
*.lock
EOF
    
    log_info "创建排除文件: ${exclude_file}"
}

# 执行全量备份
perform_full_backup() {
    local backup_dir="$1"
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local backup_name="${BACKUP_PREFIX}_full_${timestamp}"
    local backup_path="${backup_dir}/full/${backup_name}"
    
    log_info "开始全量备份..."
    log_info "备份名称: ${backup_name}"
    
    # 创建临时目录
    local temp_dir="${backup_dir}/temp/${backup_name}"
    mkdir -p "${temp_dir}"
    
    # 使用 rsync 进行备份
    if rsync ${RSYNC_OPTIONS} "${WORKSPACE_DIR}/" "${temp_dir}/" 2>&1 | tee -a "${LOG_FILE}"; then
        log_success "rsync 备份完成"
    else
        log_error "rsync 备份失败"
        rm -rf "${temp_dir}"
        return 1
    fi
    
    # 压缩备份
    log_info "开始压缩备份..."
    if tar -czf "${backup_path}.tar.gz" -C "${backup_dir}/temp" "${backup_name}" 2>&1 | tee -a "${LOG_FILE}"; then
        log_success "压缩完成: ${backup_path}.tar.gz"
    else
        log_error "压缩失败"
        rm -rf "${temp_dir}"
        return 1
    fi
    
    # 清理临时目录
    rm -rf "${temp_dir}"
    
    # 计算备份大小
    local backup_size=$(du -h "${backup_path}.tar.gz" | cut -f1)
    log_success "全量备份完成，大小: ${backup_size}"
    
    # 保存备份元数据
    save_backup_metadata "${backup_path}.tar.gz" "full"
    
    # 如果启用加密，则加密备份文件
    if [ "${ENCRYPT_BACKUP}" = true ]; then
        encrypt_backup_file "${backup_path}.tar.gz"
    fi
    
    # 清理旧备份
    cleanup_old_backups "${backup_dir}/full" "full"
    
    return 0
}

# 执行增量备份
perform_incremental_backup() {
    local backup_dir="$1"
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local backup_name="${BACKUP_PREFIX}_incremental_${timestamp}"
    local backup_path="${backup_dir}/incremental/${backup_name}"
    
    log_info "开始增量备份..."
    log_info "备份名称: ${backup_name}"
    
    # 查找最近的全量备份
    local last_full_backup=$(find "${backup_dir}/full" -name "${BACKUP_PREFIX}_full_*.tar.gz" -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)
    
    if [ -z "${last_full_backup}" ]; then
        log_warning "未找到全量备份，执行全量备份"
        perform_full_backup "${backup_dir}"
        return $?
    fi
    
    log_info "基于全量备份: $(basename ${last_full_backup})"
    
    # 创建临时目录
    local temp_dir="${backup_dir}/temp/${backup_name}"
    mkdir -p "${temp_dir}"
    
    # 解压全量备份到临时目录
    log_info "解压全量备份..."
    local full_backup_name=$(basename "${last_full_backup}" .tar.gz)
    if tar -xzf "${last_full_backup}" -C "${backup_dir}/temp" 2>&1 | tee -a "${LOG_FILE}"; then
        log_success "解压完成"
    else
        log_error "解压失败"
        rm -rf "${temp_dir}"
        return 1
    fi
    
    # 使用 rsync 进行增量备份
    log_info "执行增量同步..."
    if rsync -avz --delete --exclude-from="${WORKSPACE_DIR}/.backup_exclude" \
           --link-dest="${backup_dir}/temp/${full_backup_name}" \
           "${WORKSPACE_DIR}/" "${temp_dir}/" 2>&1 | tee -a "${LOG_FILE}"; then
        log_success "增量同步完成"
    else
        log_error "增量同步失败"
        rm -rf "${temp_dir}"
        return 1
    fi
    
    # 压缩备份
    log_info "开始压缩备份..."
    if tar -czf "${backup_path}.tar.gz" -C "${backup_dir}/temp" "${backup_name}" 2>&1 | tee -a "${LOG_FILE}"; then
        log_success "压缩完成: ${backup_path}.tar.gz"
    else
        log_error "压缩失败"
        rm -rf "${temp_dir}"
        return 1
    fi
    
    # 清理临时目录
    rm -rf "${temp_dir}"
    
    # 计算备份大小
    local backup_size=$(du -h "${backup_path}.tar.gz" | cut -f1)
    log_success "增量备份完成，大小: ${backup_size}"
    
    # 保存备份元数据
    save_backup_metadata "${backup_path}.tar.gz" "incremental"
    
    # 如果启用加密，则加密备份文件
    if [ "${ENCRYPT_BACKUP}" = true ]; then
        encrypt_backup_file "${backup_path}.tar.gz"
    fi
    
    # 清理旧备份
    cleanup_old_backups "${backup_dir}/incremental" "incremental"
    
    return 0
}

# 加密备份文件
encrypt_backup_file() {
    local backup_file="$1"
    
    log_info "开始加密备份文件..."
    
    # 检查密码文件
    if [ ! -f "${ENCRYPT_PASSWORD_FILE}" ]; then
        log_error "加密密码文件不存在: ${ENCRYPT_PASSWORD_FILE}"
        log_info "请创建密码文件: echo 'your-password' > ${ENCRYPT_PASSWORD_FILE}"
        log_info "并设置权限: chmod 600 ${ENCRYPT_PASSWORD_FILE}"
        return 1
    fi
    
    # 检查 openssl 命令
    if ! check_command "openssl"; then
        log_error "openssl 命令未找到，无法加密"
        return 1
    fi
    
    # 使用 AES-256-CBC 加密
    local encrypted_file="${backup_file}.enc"
    if openssl enc -aes-256-cbc -salt -in "${backup_file}" -out "${encrypted_file}" -pass file:"${ENCRYPT_PASSWORD_FILE}" 2>&1 | tee -a "${LOG_FILE}"; then
        log_success "加密完成: ${encrypted_file}"
        
        # 删除原始文件
        rm -f "${backup_file}"
        log_info "已删除未加密的备份文件"
        
        return 0
    else
        log_error "加密失败"
        return 1
    fi
}

# 解密备份文件
decrypt_backup_file() {
    local encrypted_file="$1"
    local output_file="$2"
    
    log_info "开始解密备份文件..."
    
    # 检查密码文件
    if [ ! -f "${ENCRYPT_PASSWORD_FILE}" ]; then
        log_error "加密密码文件不存在: ${ENCRYPT_PASSWORD_FILE}"
        return 1
    fi
    
    # 检查 openssl 命令
    if ! check_command "openssl"; then
        log_error "openssl 命令未找到，无法解密"
        return 1
    fi
    
    # 解密文件
    if openssl enc -aes-256-cbc -d -in "${encrypted_file}" -out "${output_file}" -pass file:"${ENCRYPT_PASSWORD_FILE}" 2>&1 | tee -a "${LOG_FILE}"; then
        log_success "解密完成: ${output_file}"
        return 0
    else
        log_error "解密失败"
        return 1
    fi
}

# 保存备份元数据
save_backup_metadata() {
    local backup_file="$1"
    local backup_type="$2"
    
    local metadata_file="${backup_file}.meta"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local file_size=$(du -b "${backup_file}" | cut -f1)
    local file_hash=$(sha256sum "${backup_file}" | cut -d' ' -f1)
    
    cat > "${metadata_file}" << EOF
backup_name=$(basename "${backup_file}")
backup_type=${backup_type}
backup_path=${backup_file}
backup_timestamp=${timestamp}
backup_size=${file_size}
backup_hash=${file_hash}
workspace_dir=${WORKSPACE_DIR}
EOF
    
    log_info "保存备份元数据: ${metadata_file}"
}

# 清理旧备份
cleanup_old_backups() {
    local backup_dir="$1"
    local backup_type="$2"
    
    log_info "清理超过 ${RETENTION_DAYS} 天的旧备份..."
    
    # 查找并删除超过保留期的备份
    local old_backups=$(find "${backup_dir}" -name "${BACKUP_PREFIX}_${backup_type}_*.tar.gz*" -type f -mtime +${RETENTION_DAYS} 2>/dev/null)
    
    if [ -n "${old_backups}" ]; then
        echo "${old_backups}" | while read -r old_backup; do
            log_info "删除旧备份: $(basename ${old_backup})"
            rm -f "${old_backup}"
            # 同时删除元数据文件
            rm -f "${old_backup}.meta"
        done
        log_success "清理完成"
    else
        log_info "没有需要清理的旧备份"
    fi
}

# 列出所有备份
list_backups() {
    local backup_dir="$1"
    
    log_info "备份列表:"
    echo ""
    
    # 全量备份
    echo "=== 全量备份 ==="
    find "${backup_dir}/full" -name "${BACKUP_PREFIX}_full_*.tar.gz*" -type f -printf '%T+ %s %p\n' 2>/dev/null | sort -r | while read -r line; do
        local timestamp=$(echo "${line}" | awk '{print $1}')
        local size=$(echo "${line}" | awk '{print $2}')
        local path=$(echo "${line}" | awk '{print $3}')
        local name=$(basename "${path}")
        local size_human=$(numfmt --to=iec-i --suffix=B ${size} 2>/dev/null || echo "${size}")
        
        echo "  ${name}"
        echo "    时间: ${timestamp}"
        echo "    大小: ${size_human}"
        echo "    路径: ${path}"
        echo ""
    done
    
    # 增量备份
    echo "=== 增量备份 ==="
    find "${backup_dir}/incremental" -name "${BACKUP_PREFIX}_incremental_*.tar.gz*" -type f -printf '%T+ %s %p\n' 2>/dev/null | sort -r | while read -r line; do
        local timestamp=$(echo "${line}" | awk '{print $1}')
        local size=$(echo "${line}" | awk '{print $2}')
        local path=$(echo "${line}" | awk '{print $3}')
        local name=$(basename "${path}")
        local size_human=$(numfmt --to=iec-i --suffix=B ${size} 2>/dev/null || echo "${size}")
        
        echo "  ${name}"
        echo "    时间: ${timestamp}"
        echo "    大小: ${size_human}"
        echo "    路径: ${path}"
        echo ""
    done
}

# 恢复备份
restore_backup() {
    local backup_file="$1"
    local restore_dir="$2"
    
    log_info "开始恢复备份..."
    log_info "备份文件: ${backup_file}"
    log_info "恢复目录: ${restore_dir}"
    
    # 检查备份文件是否存在
    if [ ! -f "${backup_file}" ]; then
        log_error "备份文件不存在: ${backup_file}"
        return 1
    fi
    
    # 创建恢复目录
    mkdir -p "${restore_dir}"
    
    # 如果是加密文件，先解密
    if [[ "${backup_file}" == *.enc ]]; then
        local decrypted_file="${backup_file%.enc}"
        log_info "检测到加密备份，正在解密..."
        
        if ! decrypt_backup_file "${backup_file}" "${decrypted_file}"; then
            log_error "解密失败"
            return 1
        fi
        
        backup_file="${decrypted_file}"
    fi
    
    # 解压备份
    log_info "解压备份文件..."
    if tar -xzf "${backup_file}" -C "${restore_dir}" 2>&1 | tee -a "${LOG_FILE}"; then
        log_success "解压完成"
    else
        log_error "解压失败"
        return 1
    fi
    
    log_success "备份恢复完成"
    log_info "恢复位置: ${restore_dir}"
    
    return 0
}

# 验证备份完整性
verify_backup() {
    local backup_file="$1"
    
    log_info "验证备份完整性..."
    log_info "备份文件: ${backup_file}"
    
    # 检查备份文件是否存在
    if [ ! -f "${backup_file}" ]; then
        log_error "备份文件不存在: ${backup_file}"
        return 1
    fi
    
    # 如果是加密文件，先解密到临时位置
    local temp_backup_file="${backup_file}"
    if [[ "${backup_file}" == *.enc ]]; then
        local decrypted_file="${backup_file%.enc}"
        log_info "检测到加密备份，正在解密..."
        
        if ! decrypt_backup_file "${backup_file}" "${decrypted_file}"; then
            log_error "解密失败"
            return 1
        fi
        
        temp_backup_file="${decrypted_file}"
    fi
    
    # 检查 tar 文件完整性
    log_info "检查 tar 文件完整性..."
    if tar -tzf "${temp_backup_file}" > /dev/null 2>&1; then
        log_success "tar 文件完整性检查通过"
    else
        log_error "tar 文件已损坏"
        return 1
    fi
    
    # 检查元数据文件
    local metadata_file="${temp_backup_file}.meta"
    if [ -f "${metadata_file}" ]; then
        log_info "检查备份元数据..."
        
        # 读取元数据
        source "${metadata_file}"
        
        # 验证文件大小
        local current_size=$(du -b "${temp_backup_file}" | cut -f1)
        if [ "${current_size}" = "${backup_size}" ]; then
            log_success "文件大小验证通过: ${backup_size} 字节"
        else
            log_warning "文件大小不匹配: 期望 ${backup_size}, 实际 ${current_size}"
        fi
        
        # 验证文件哈希
        local current_hash=$(sha256sum "${temp_backup_file}" | cut -d' ' -f1)
        if [ "${current_hash}" = "${backup_hash}" ]; then
            log_success "文件哈希验证通过: ${backup_hash}"
        else
            log_error "文件哈希不匹配: 期望 ${backup_hash}, 实际 ${current_hash}"
            return 1
        fi
    else
        log_warning "元数据文件不存在: ${metadata_file}"
    fi
    
    # 清理临时解密的文件
    if [[ "${backup_file}" == *.enc ]]; then
        rm -f "${temp_backup_file}"
    fi
    
    log_success "备份验证完成"
    return 0
}

# 设置定时备份
setup_cron_backup() {
    local backup_type="$1"
    local schedule="$2"
    
    log_info "设置定时备份..."
    log_info "备份类型: ${backup_type}"
    log_info "执行计划: ${schedule}"
    
    # 获取脚本路径
    local script_path="${WORKSPACE_DIR}/$(basename "${BASH_SOURCE[0]}")"
    
    # 创建 cron 任务
    local cron_job="${schedule} ${script_path} --${backup_type} >> ${LOG_FILE} 2>&1"
    
    # 检查是否已存在相同的 cron 任务
    if crontab -l 2>/dev/null | grep -q "${script_path}"; then
        log_warning "定时备份任务已存在，正在更新..."
        crontab -l 2>/dev/null | grep -v "${script_path}" | crontab -
    fi
    
    # 添加新的 cron 任务
    (crontab -l 2>/dev/null; echo "${cron_job}") | crontab -
    
    log_success "定时备份设置完成"
    log_info "当前 crontab 内容:"
    crontab -l | grep "${script_path}"
}

# 显示帮助信息
show_help() {
    cat << EOF
自动备份脚本

用法: $(basename "$0") [选项]

选项:
  --full                    执行全量备份
  --incremental             执行增量备份
  --restore <backup_file>   恢复指定的备份文件
  --verify <backup_file>    验证指定的备份文件
  --list                    列出所有备份
  --setup-cron <type> <schedule>  设置定时备份
                            type: full 或 incremental
                            schedule: cron 表达式 (例如: "0 2 * * *" 表示每天凌晨2点)
  --clean                   清理旧备份
  --config <file>           指定配置文件
  --backup-dir <dir>        指定备份目录
  --encrypt                 启用加密
  --no-encrypt              禁用加密
  --retention <days>        设置备份保留天数
  -h, --help                显示此帮助信息

示例:
  $(basename "$0") --full                              # 执行全量备份
  $(basename "$0") --incremental                       # 执行增量备份
  $(basename "$0") --list                              # 列出所有备份
  $(basename "$0") --restore backups/full/backup.tar.gz  # 恢复备份
  $(basename "$0") --verify backups/full/backup.tar.gz   # 验证备份
  $(basename "$0") --setup-cron incremental "0 2 * * *"  # 设置每天凌晨2点执行增量备份
  $(basename "$0") --clean                             # 清理旧备份

配置文件格式:
  BACKUP_DIR=/path/to/backup
  ENCRYPT_BACKUP=true
  ENCRYPT_PASSWORD_FILE=/path/to/password
  RETENTION_DAYS=30

注意:
  - 首次备份必须执行全量备份
  - 增量备份基于最近的全量备份
  - 加密需要 openssl 命令
  - 定时备份需要 cron 服务

EOF
}

# ============================================================================
# 主程序
# ============================================================================

main() {
    local backup_dir="${DEFAULT_BACKUP_DIR}"
    local action=""
    local backup_file=""
    local restore_dir=""
    
    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --full)
                action="full"
                shift
                ;;
            --incremental)
                action="incremental"
                shift
                ;;
            --restore)
                action="restore"
                backup_file="$2"
                shift 2
                ;;
            --verify)
                action="verify"
                backup_file="$2"
                shift 2
                ;;
            --list)
                action="list"
                shift
                ;;
            --setup-cron)
                action="setup-cron"
                local backup_type="$2"
                local schedule="$3"
                shift 3
                ;;
            --clean)
                action="clean"
                shift
                ;;
            --config)
                if [ -f "$2" ]; then
                    source "$2"
                    log_info "加载配置文件: $2"
                else
                    log_error "配置文件不存在: $2"
                    exit 1
                fi
                shift 2
                ;;
            --backup-dir)
                backup_dir="$2"
                shift 2
                ;;
            --encrypt)
                ENCRYPT_BACKUP=true
                shift
                ;;
            --no-encrypt)
                ENCRYPT_BACKUP=false
                shift
                ;;
            --retention)
                RETENTION_DAYS="$2"
                shift 2
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
    
    # 更新日志文件路径
    LOG_FILE="${backup_dir}/backup.log"
    
    # 创建日志目录
    mkdir -p "$(dirname "${LOG_FILE}")"
    
    # 记录开始时间
    log_info "=========================================="
    log_info "备份脚本启动"
    log_info "工作区: ${WORKSPACE_DIR}"
    log_info "备份目录: ${backup_dir}"
    log_info "操作: ${action}"
    log_info "=========================================="
    
    # 检查必要的命令
    log_info "检查必要的命令..."
    check_command "tar" || exit 1
    check_command "rsync" || exit 1
    
    # 创建备份目录
    create_backup_dirs "${backup_dir}"
    
    # 创建排除文件
    #create_exclude_file
    
    # 执行相应的操作
    case ${action} in
        full)
            perform_full_backup "${backup_dir}"
            ;;
        incremental)
            perform_incremental_backup "${backup_dir}"
            ;;
        restore)
            if [ -z "${backup_file}" ]; then
                log_error "请指定备份文件"
                exit 1
            fi
            restore_dir="${backup_dir}/restore/$(date '+%Y%m%d_%H%M%S')"
            restore_backup "${backup_file}" "${restore_dir}"
            ;;
        verify)
            if [ -z "${backup_file}" ]; then
                log_error "请指定备份文件"
                exit 1
            fi
            verify_backup "${backup_file}"
            ;;
        list)
            list_backups "${backup_dir}"
            ;;
        setup-cron)
            setup_cron_backup "${backup_type}" "${schedule}"
            ;;
        clean)
            cleanup_old_backups "${backup_dir}/full" "full"
            cleanup_old_backups "${backup_dir}/incremental" "incremental"
            ;;
        *)
            log_error "未知操作: ${action}"
            exit 1
            ;;
    esac
    
    # 记录结束时间
    log_info "=========================================="
    log_info "备份脚本完成"
    log_info "=========================================="
    
    exit 0
}

# 执行主程序
main "$@"
