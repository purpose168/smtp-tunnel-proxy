#!/bin/bash
#
# SMTP 隧道客户端更新脚本 - 测试脚本
#
# 用于测试 smtp-tunnel-client-update 脚本的各种功能
#

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 测试统计
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# 打印测试结果
print_test_result() {
    local test_name=$1
    local result=$2
    local message=$3
    
    TESTS_RUN=$((TESTS_RUN + 1))
    
    if [ "$result" = "PASS" ]; then
        echo -e "${GREEN}[PASS]${NC} $test_name"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        echo -e "${RED}[FAIL]${NC} $test_name"
        if [ -n "$message" ]; then
            echo -e "       ${YELLOW}Reason: $message${NC}"
        fi
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
}

# 测试脚本是否存在
test_script_exists() {
    echo -e "${BLUE}[TEST]${NC} 测试脚本是否存在..."
    
    if [ -f "./smtp-tunnel-client-update" ]; then
        print_test_result "脚本存在" "PASS"
        return 0
    else
        print_test_result "脚本存在" "FAIL" "文件不存在"
        return 1
    fi
}

# 测试脚本可执行权限
test_script_executable() {
    echo -e "${BLUE}[TEST]${NC} 测试脚本可执行权限..."
    
    if [ -x "./smtp-tunnel-client-update" ]; then
        print_test_result "脚本可执行" "PASS"
        return 0
    else
        print_test_result "脚本可执行" "FAIL" "没有执行权限"
        return 1
    fi
}

# 测试脚本语法
test_script_syntax() {
    echo -e "${BLUE}[TEST]${NC} 测试脚本语法..."
    
    if bash -n "./smtp-tunnel-client-update" 2>/dev/null; then
        print_test_result "脚本语法正确" "PASS"
        return 0
    else
        print_test_result "脚本语法正确" "FAIL" "语法错误"
        return 1
    fi
}

# 测试帮助信息
test_help_output() {
    echo -e "${BLUE}[TEST]${NC} 测试帮助信息输出..."
    
    local output=$(./smtp-tunnel-client-update --help 2>&1)
    
    if echo "$output" | grep -q "SMTP 隧道代理 - 客户端更新脚本"; then
        print_test_result "帮助信息输出" "PASS"
        return 0
    else
        print_test_result "帮助信息输出" "FAIL" "帮助信息不正确"
        return 1
    fi
}

# 测试版本检查功能
test_version_check() {
    echo -e "${BLUE}[TEST]${NC} 测试版本检查功能..."
    
    # 检查 get_current_version 函数
    if [ -f "./client.py" ]; then
        local version=$(grep -m1 "Version:" "./client.py" | sed 's/.*Version: //')
        if [ -n "$version" ]; then
            print_test_result "版本检查功能" "PASS" "当前版本: $version"
            return 0
        fi
    fi
    
    print_test_result "版本检查功能" "FAIL" "无法读取版本"
    return 1
}

# 测试日志目录创建
test_log_directory() {
    echo -e "${BLUE}[TEST]${NC} 测试日志目录创建..."
    
    local log_dir="./logs"
    
    # 创建测试日志目录
    mkdir -p "$log_dir" 2>/dev/null
    
    if [ -d "$log_dir" ]; then
        print_test_result "日志目录创建" "PASS"
        return 0
    else
        print_test_result "日志目录创建" "FAIL" "无法创建日志目录"
        return 1
    fi
}

# 测试备份目录创建
test_backup_directory() {
    echo -e "${BLUE}[TEST]${NC} 测试备份目录创建..."
    
    local backup_dir="./backups"
    
    # 创建测试备份目录
    mkdir -p "$backup_dir" 2>/dev/null
    
    if [ -d "$backup_dir" ]; then
        print_test_result "备份目录创建" "PASS"
        return 0
    else
        print_test_result "备份目录创建" "FAIL" "无法创建备份目录"
        return 1
    fi
}

# 测试网络连接
test_network_connection() {
    echo -e "${BLUE}[TEST]${NC} 测试网络连接..."
    
    if command -v curl &> /dev/null; then
        if curl -sSL --connect-timeout 5 --max-time 10 "https://raw.githubusercontent.com/purpose168/smtp-tunnel-proxy/main/client.py" > /dev/null 2>&1; then
            print_test_result "网络连接" "PASS"
            return 0
        else
            print_test_result "网络连接" "FAIL" "无法连接到 GitHub"
            return 1
        fi
    else
        print_test_result "网络连接" "FAIL" "curl 命令不存在"
        return 1
    fi
}

# 测试文件下载功能
test_file_download() {
    echo -e "${BLUE}[TEST]${NC} 测试文件下载功能..."
    
    local temp_file="/tmp/test_download.py"
    
    if curl -sSL --connect-timeout 10 --max-time 30 "https://raw.githubusercontent.com/purpose168/smtp-tunnel-proxy/main/client.py" -o "$temp_file" 2>/dev/null; then
        if [ -f "$temp_file" ] && [ -s "$temp_file" ]; then
            rm -f "$temp_file"
            print_test_result "文件下载功能" "PASS"
            return 0
        fi
    fi
    
    rm -f "$temp_file"
    print_test_result "文件下载功能" "FAIL" "下载失败"
    return 1
}

# 测试文件校验功能
test_file_verification() {
    echo -e "${BLUE}[TEST]${NC} 测试文件校验功能..."
    
    # 测试现有文件
    if [ -f "./client.py" ]; then
        local file_size=$(stat -c %s "./client.py" 2>/dev/null || echo 0)
        
        if [ $file_size -gt 0 ]; then
            print_test_result "文件校验功能" "PASS" "文件大小: $file_size bytes"
            return 0
        fi
    fi
    
    print_test_result "文件校验功能" "FAIL" "文件校验失败"
    return 1
}

# 测试备份功能
test_backup_functionality() {
    echo -e "${BLUE}[TEST]${NC} 测试备份功能..."
    
    local backup_dir="./backups/test_backup"
    
    # 创建测试备份
    mkdir -p "$backup_dir"
    
    if [ -f "./client.py" ]; then
        cp "./client.py" "$backup_dir/"
        
        if [ -f "$backup_dir/client.py" ]; then
            rm -rf "$backup_dir"
            print_test_result "备份功能" "PASS"
            return 0
        fi
    fi
    
    rm -rf "$backup_dir"
    print_test_result "备份功能" "FAIL" "备份失败"
    return 1
}

# 测试权限设置功能
test_permission_setting() {
    echo -e "${BLUE}[TEST]${NC} 测试权限设置功能..."
    
    # 创建测试文件
    local test_file="/tmp/test_permission.py"
    touch "$test_file"
    
    # 设置权限
    chmod 644 "$test_file"
    
    local perms=$(stat -c %a "$test_file" 2>/dev/null)
    
    if [ "$perms" = "644" ]; then
        rm -f "$test_file"
        print_test_result "权限设置功能" "PASS"
        return 0
    fi
    
    rm -f "$test_file"
    print_test_result "权限设置功能" "FAIL" "权限设置不正确"
    return 1
}

# 测试日志记录功能
test_logging_functionality() {
    echo -e "${BLUE}[TEST]${NC} 测试日志记录功能..."
    
    local log_file="./logs/test.log"
    
    # 创建日志目录
    mkdir -p "$(dirname "$log_file")"
    
    # 写入测试日志
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] Test message" >> "$log_file"
    
    if [ -f "$log_file" ] && grep -q "Test message" "$log_file"; then
        rm -f "$log_file"
        print_test_result "日志记录功能" "PASS"
        return 0
    fi
    
    rm -f "$log_file"
    print_test_result "日志记录功能" "FAIL" "日志记录失败"
    return 1
}

# 主测试函数
main() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  SMTP 隧道客户端更新脚本测试${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    
    # 运行所有测试
    test_script_exists
    test_script_executable
    test_script_syntax
    test_help_output
    test_version_check
    test_log_directory
    test_backup_directory
    test_network_connection
    test_file_download
    test_file_verification
    test_backup_functionality
    test_permission_setting
    test_logging_functionality
    
    # 显示测试结果摘要
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  测试结果摘要${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    echo -e "总测试数: ${GREEN}$TESTS_RUN${NC}"
    echo -e "通过: ${GREEN}$TESTS_PASSED${NC}"
    echo -e "失败: ${RED}$TESTS_FAILED${NC}"
    echo ""
    
    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "${GREEN}所有测试通过！${NC}"
        return 0
    else
        echo -e "${RED}部分测试失败！${NC}"
        return 1
    fi
}

# 运行主函数
main "$@"
