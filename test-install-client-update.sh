#!/bin/bash
#
# 测试 install-client.sh 脚本的更新脚本集成
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

# 测试脚本语法
test_script_syntax() {
    echo -e "${BLUE}[TEST]${NC} 测试脚本语法..."
    
    if bash -n "./install-client.sh" 2>/dev/null; then
        print_test_result "脚本语法正确" "PASS"
        return 0
    else
        print_test_result "脚本语法正确" "FAIL" "语法错误"
        return 1
    fi
}

# 测试管理脚本变量定义
test_management_scripts_variable() {
    echo -e "${BLUE}[TEST]${NC} 测试管理脚本变量定义..."
    
    if grep -q 'MANAGEMENT_SCRIPTS="smtp-tunnel-client-update"' "./install-client.sh"; then
        print_test_result "管理脚本变量定义" "PASS"
        return 0
    else
        print_test_result "管理脚本变量定义" "FAIL" "变量未正确定义"
        return 1
    fi
}

# 测试所有文件变量定义
test_all_files_variable() {
    echo -e "${BLUE}[TEST]${NC} 测试所有文件变量定义..."
    
    if grep -q 'ALL_FILES="$PYTHON_FILES $MANAGEMENT_SCRIPTS"' "./install-client.sh"; then
        print_test_result "所有文件变量定义" "PASS"
        return 0
    else
        print_test_result "所有文件变量定义" "FAIL" "变量未正确定义"
        return 1
    fi
}

# 测试管理脚本下载逻辑
test_management_scripts_download() {
    echo -e "${BLUE}[TEST]${NC} 测试管理脚本下载逻辑..."
    
    if grep -q 'for script in \$MANAGEMENT_SCRIPTS; do' "./install-client.sh"; then
        print_test_result "管理脚本下载逻辑" "PASS"
        return 0
    else
        print_test_result "管理脚本下载逻辑" "FAIL" "下载逻辑未找到"
        return 1
    fi
}

# 测试管理脚本权限设置
test_management_scripts_permissions() {
    echo -e "${BLUE}[TEST]${NC} 测试管理脚本权限设置..."
    
    if grep -q 'chmod +x "\$INSTALL_DIR/\$script"' "./install-client.sh"; then
        print_test_result "管理脚本权限设置" "PASS"
        return 0
    else
        print_test_result "管理脚本权限设置" "FAIL" "权限设置未找到"
        return 1
    fi
}

# 测试更新脚本下载逻辑
test_update_script_download() {
    echo -e "${BLUE}[TEST]${NC} 测试更新脚本下载逻辑..."
    
    if grep -q 'if \[ ! -f "\$INSTALL_DIR/smtp-tunnel-client-update" \]; then' "./install-client.sh"; then
        print_test_result "更新脚本下载逻辑" "PASS"
        return 0
    else
        print_test_result "更新脚本下载逻辑" "FAIL" "下载逻辑未找到"
        return 1
    fi
}

# 测试更新脚本执行权限设置
test_update_script_permissions() {
    echo -e "${BLUE}[TEST]${NC} 测试更新脚本执行权限设置..."
    
    if grep -q 'chmod +x "\$INSTALL_DIR/smtp-tunnel-client-update"' "./install-client.sh"; then
        print_test_result "更新脚本执行权限设置" "PASS"
        return 0
    else
        print_test_result "更新脚本执行权限设置" "FAIL" "权限设置未找到"
        return 1
    fi
}

# 测试更新脚本在摘要中显示
test_update_script_in_summary() {
    echo -e "${BLUE}[TEST]${NC} 测试更新脚本在摘要中显示..."
    
    if grep -q 'smtp-tunnel-client-update - 更新客户端' "./install-client.sh"; then
        print_test_result "更新脚本在摘要中显示" "PASS"
        return 0
    else
        print_test_result "更新脚本在摘要中显示" "FAIL" "摘要中未找到"
        return 1
    fi
}

# 测试更新脚本在快速开始中显示
test_update_script_in_quick_start() {
    echo -e "${BLUE}[TEST]${NC} 测试更新脚本在快速开始中显示..."
    
    if grep -q '更新客户端: \$INSTALL_DIR/smtp-tunnel-client-update' "./install-client.sh"; then
        print_test_result "更新脚本在快速开始中显示" "PASS"
        return 0
    else
        print_test_result "更新脚本在快速开始中显示" "FAIL" "快速开始中未找到"
        return 1
    fi
}

# 测试脚本说明更新
test_script_description_updated() {
    echo -e "${BLUE}[TEST]${NC} 测试脚本说明更新..."
    
    if grep -q '下载更新脚本（smtp-tunnel-client-update）' "./install-client.sh"; then
        print_test_result "脚本说明更新" "PASS"
        return 0
    else
        print_test_result "脚本说明更新" "FAIL" "说明未更新"
        return 1
    fi
}

# 主测试函数
main() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  install-client.sh 更新脚本集成测试${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    
    # 运行所有测试
    test_script_syntax
    test_management_scripts_variable
    test_all_files_variable
    test_management_scripts_download
    test_management_scripts_permissions
    test_update_script_download
    test_update_script_permissions
    test_update_script_in_summary
    test_update_script_in_quick_start
    test_script_description_updated
    
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
        echo ""
        echo "install-client.sh 脚本已成功集成 smtp-tunnel-client-update"
        echo "现在安装客户端时会自动下载并安装更新脚本。"
        return 0
    else
        echo -e "${RED}部分测试失败！${NC}"
        return 1
    fi
}

# 运行主函数
main "$@"
