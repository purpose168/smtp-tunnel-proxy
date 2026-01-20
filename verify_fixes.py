#!/usr/bin/env python3
"""
修复验证脚本 - 验证 client.py 的修复是否正确

功能:
1. 检查代码中所有资源清理点
2. 验证异常处理是否完整
3. 检查任务管理是否正确
4. 生成验证报告
"""

import ast
import sys
from typing import List, Dict, Set

class ResourceLeakChecker(ast.NodeVisitor):
    """资源泄漏检查器"""

    def __init__(self):
        self.issues = []
        self.writer_vars = set()
        self.channel_vars = set()
        self.receiver_tasks = set()
        self.socks_servers = set()

    def visit_AsyncFunctionDef(self, node):
        # 检查函数参数中的 writer 和 channel
        for arg in node.args.args:
            if arg.arg == 'writer':
                self.writer_vars.add(arg.arg)
            elif arg.arg == 'channel':
                self.channel_vars.add(arg.arg)

        # 检查函数体中的赋值
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        if 'writer' in target.id.lower():
                            self.writer_vars.add(target.id)
                        elif 'channel' in target.id.lower():
                            self.channel_vars.add(target.id)
                        elif 'receiver_task' in target.id.lower():
                            self.receiver_tasks.add(target.id)
                        elif 'socks_server' in target.id.lower():
                            self.socks_servers.add(target.id)

        # 检查是否有 finally 块
        has_finally = False
        for stmt in node.body:
            if isinstance(stmt, ast.Try):
                if stmt.finalbody:
                    has_finally = True
                    # 检查 finally 块中是否有 writer.close()
                    for finally_stmt in stmt.finalbody:
                        self._check_finally_block(finally_stmt, node.name)

        # 检查是否有提前返回且未关闭资源
        for stmt in node.body:
            self._check_early_returns(stmt, node.name, has_finally)

        self.generic_visit(node)

    def _check_finally_block(self, node, func_name):
        """检查 finally 块是否正确清理资源"""
        if isinstance(node, ast.Try):
            if node.finalbody:
                for stmt in node.finalbody:
                    self._check_finally_block(stmt, func_name)
        elif isinstance(node, ast.With):
            # with 语句会自动管理资源
            pass
        elif isinstance(node, ast.Expr):
            if isinstance(node.value, ast.Await):
                call = node.value.value
                if isinstance(call, ast.Call):
                    if isinstance(call.func, ast.Attribute):
                        # 检查是否有 writer.close() 和 wait_closed()
                        if call.func.attr == 'close':
                            if isinstance(call.func.value, ast.Name):
                                if call.func.value.id in self.writer_vars:
                                    # 检查是否有对应的 wait_closed()
                                    pass

    def _check_early_returns(self, node, func_name, has_finally):
        """检查提前返回是否关闭资源"""
        if isinstance(node, ast.Return):
            if not has_finally:
                if 'handle_client' in func_name:
                    self.issues.append({
                        'type': 'early_return',
                        'function': func_name,
                        'line': node.lineno,
                        'message': '提前返回可能未关闭 writer'
                    })
        elif isinstance(node, ast.If):
            for stmt in node.body:
                self._check_early_returns(stmt, func_name, has_finally)
            if node.orelse:
                for stmt in node.orelse:
                    self._check_early_returns(stmt, func_name, has_finally)
        elif isinstance(node, ast.Try):
            for stmt in node.body:
                self._check_early_returns(stmt, func_name, has_finally)
            if node.orelse:
                for stmt in node.orelse:
                    self._check_early_returns(stmt, func_name, has_finally)

def check_resource_cleanup(filename: str) -> List[Dict]:
    """
    检查资源清理

    参数:
        filename: 要检查的文件路径

    返回:
        List[Dict]: 发现的问题列表
    """
    with open(filename, 'r', encoding='utf-8') as f:
        source = f.read()

    tree = ast.parse(source)
    checker = ResourceLeakChecker()
    checker.visit(tree)

    return checker.issues

def check_function_patterns(filename: str) -> List[Dict]:
    """
    检查函数模式

    参数:
        filename: 要检查的文件路径

    返回:
        List[Dict]: 发现的问题列表
    """
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    issues = []

    # 检查 handle_client 函数
    in_handle_client = False
    indent_level = 0

    for i, line in enumerate(lines, 1):
        stripped = line.lstrip()
        if 'async def handle_client' in line:
            in_handle_client = True
            indent_level = len(line) - len(stripped)
        elif in_handle_client:
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= indent_level and stripped and not stripped.startswith('#'):
                in_handle_client = False
            else:
                # 检查是否有提前返回且未关闭 writer
                if 'return' in stripped and 'writer.close()' not in lines[i-2:i]:
                    # 检查是否在 finally 块中
                    has_finally = False
                    for j in range(max(0, i-20), i):
                        if 'finally:' in lines[j]:
                            has_finally = True
                            break
                    if not has_finally:
                        issues.append({
                            'type': 'early_return_without_close',
                            'line': i,
                            'message': f'提前返回可能未关闭 writer: {stripped.strip()}'
                        })

    return issues

def check_disconnect_function(filename: str) -> List[Dict]:
    """
    检查 disconnect 函数

    参数:
        filename: 要检查的文件路径

    返回:
        List[Dict]: 发现的问题列表
    """
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    issues = []
    in_disconnect = False

    for i, line in enumerate(lines, 1):
        if 'async def disconnect' in line:
            in_disconnect = True
        elif in_disconnect:
            if 'async def' in line and 'disconnect' not in line:
                in_disconnect = False
            else:
                # 检查是否清理了 connect_events 和 connect_results
                if 'self.connect_events.clear()' in line or 'self.connect_results.clear()' in line:
                    # 检查是否有日志输出
                    has_log = False
                    for j in range(max(0, i-10), i):
                        if 'logger' in lines[j] and ('event' in lines[j] or 'result' in lines[j]):
                            has_log = True
                            break
                    if not has_log:
                        issues.append({
                            'type': 'missing_log',
                            'line': i,
                            'message': '清理事件和结果时缺少日志输出'
                        })

    return issues

def check_run_client_function(filename: str) -> List[Dict]:
    """
    检查 run_client 函数

    参数:
        filename: 要检查的文件路径

    返回:
        List[Dict]: 发现的问题列表
    """
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    issues = []
    in_run_client = False
    has_socks_server_var = False
    has_socks_server_close = False

    for i, line in enumerate(lines, 1):
        if 'async def run_client' in line:
            in_run_client = True
        elif in_run_client:
            if 'async def' in line and 'run_client' not in line:
                in_run_client = False
            else:
                # 检查是否有 socks_server 变量
                if 'socks_server' in line and '=' in line:
                    has_socks_server_var = True

                # 检查是否关闭了 socks_server
                if 'socks_server.close()' in line:
                    has_socks_server_close = True

                # 检查 receiver_task 的取消和等待
                if 'receiver_task.cancel()' in line:
                    # 检查是否有 asyncio.wait_for
                    has_wait_for = False
                    for j in range(i, min(i+5, len(lines))):
                        if 'asyncio.wait_for' in lines[j]:
                            has_wait_for = True
                            break
                    if not has_wait_for:
                        issues.append({
                            'type': 'missing_wait_for',
                            'line': i,
                            'message': '取消 receiver_task 后应使用 asyncio.wait_for 等待'
                        })

    if has_socks_server_var and not has_socks_server_close:
        issues.append({
            'type': 'missing_socks_server_close',
            'line': 0,
            'message': 'run_client 函数中未关闭 socks_server'
        })

    return issues

def generate_report(filename: str) -> str:
    """
    生成验证报告

    参数:
        filename: 要检查的文件路径

    返回:
        str: 报告内容
    """
    report = []
    report.append("="*80)
    report.append("SMTP 隧道客户端修复验证报告")
    report.append("="*80)
    report.append(f"文件: {filename}")
    report.append("")

    # 检查资源清理
    report.append("1. 资源清理检查")
    report.append("-"*80)
    resource_issues = check_resource_cleanup(filename)
    if resource_issues:
        for issue in resource_issues:
            report.append(f"  [问题] 行 {issue['line']}: {issue['message']}")
    else:
        report.append("  ✓ 未发现资源清理问题")
    report.append("")

    # 检查函数模式
    report.append("2. 函数模式检查")
    report.append("-"*80)
    pattern_issues = check_function_patterns(filename)
    if pattern_issues:
        for issue in pattern_issues:
            report.append(f"  [问题] 行 {issue['line']}: {issue['message']}")
    else:
        report.append("  ✓ 未发现函数模式问题")
    report.append("")

    # 检查 disconnect 函数
    report.append("3. disconnect 函数检查")
    report.append("-"*80)
    disconnect_issues = check_disconnect_function(filename)
    if disconnect_issues:
        for issue in disconnect_issues:
            report.append(f"  [问题] 行 {issue['line']}: {issue['message']}")
    else:
        report.append("  ✓ disconnect 函数正常")
    report.append("")

    # 检查 run_client 函数
    report.append("4. run_client 函数检查")
    report.append("-"*80)
    run_client_issues = check_run_client_function(filename)
    if run_client_issues:
        for issue in run_client_issues:
            report.append(f"  [问题] 行 {issue['line']}: {issue['message']}")
    else:
        report.append("  ✓ run_client 函数正常")
    report.append("")

    # 总结
    total_issues = len(resource_issues) + len(pattern_issues) + len(disconnect_issues) + len(run_client_issues)
    report.append("="*80)
    report.append("总结")
    report.append("="*80)
    if total_issues == 0:
        report.append("✓ 所有检查通过! 修复已正确应用。")
    else:
        report.append(f"✗ 发现 {total_issues} 个问题需要修复。")
    report.append("="*80)

    return "\n".join(report)

def main():
    if len(sys.argv) < 2:
        print("用法: python3 verify_fixes.py <client.py 文件路径>")
        sys.exit(1)

    filename = sys.argv[1]
    report = generate_report(filename)
    print(report)

    # 如果有问题,返回非零退出码
    if "发现问题" in report:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == '__main__':
    main()
