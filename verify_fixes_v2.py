#!/usr/bin/env python3
"""
修复验证脚本 (改进版) - 验证 client.py 的修复是否正确

功能:
1. 检查所有提前返回点是否正确关闭 writer
2. 验证异常处理是否完整
3. 检查任务管理是否正确
4. 生成详细的验证报告
"""

import re
import sys
from typing import List, Dict, Tuple

def check_handle_client_function(filename: str) -> Tuple[List[Dict], List[Dict]]:
    """
    检查 handle_client 函数

    参数:
        filename: 要检查的文件路径

    返回:
        Tuple[List[Dict], List[Dict]]: (问题列表, 通过列表)
    """
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    issues = []
    passed = []

    # 找到 handle_client 函数
    in_handle_client = False
    func_start = 0
    indent_level = 0

    for i, line in enumerate(lines):
        if 'async def handle_client' in line:
            in_handle_client = True
            func_start = i
            indent_level = len(line) - len(line.lstrip())
            break

    if not in_handle_client:
        issues.append({
            'type': 'function_not_found',
            'message': '未找到 handle_client 函数'
        })
        return issues, passed

    # 分析函数体
    in_function = False
    for i in range(func_start, len(lines)):
        line = lines[i]
        stripped = line.lstrip()

        # 检查是否进入函数体
        if not in_function:
            if stripped.startswith('"""') or stripped.startswith("'''"):
                # 跳过文档字符串
                continue
            if stripped and not stripped.startswith('#'):
                current_indent = len(line) - len(stripped)
                if current_indent > indent_level:
                    in_function = True
                elif current_indent <= indent_level and stripped:
                    # 函数结束
                    break
        else:
            # 在函数体内
            current_indent = len(line) - len(stripped)
            if current_indent <= indent_level and stripped and not stripped.startswith('#'):
                # 函数结束
                break

            # 检查提前返回
            if 'return' in stripped and not stripped.startswith('#'):
                # 检查前面几行是否有 writer.close()
                has_close = False
                has_wait_closed = False

                # 检查 return 语句之前的几行
                for j in range(max(func_start, i-5), i):
                    prev_line = lines[j].strip()
                    if 'writer.close()' in prev_line:
                        has_close = True
                    if 'await writer.wait_closed()' in prev_line:
                        has_wait_closed = True

                # 检查是否在 finally 块中
                in_finally = False
                for j in range(max(func_start, i-20), i):
                    if 'finally:' in lines[j]:
                        in_finally = True
                        break

                if in_finally:
                    # 在 finally 块中,不需要检查
                    passed.append({
                        'line': i + 1,
                        'message': 'return 语句在 finally 块中,资源会自动清理'
                    })
                elif has_close and has_wait_closed:
                    # 正确关闭
                    passed.append({
                        'line': i + 1,
                        'message': 'return 语句前正确关闭了 writer'
                    })
                elif has_close:
                    # 只有 close,没有 wait_closed
                    issues.append({
                        'type': 'missing_wait_closed',
                        'line': i + 1,
                        'message': f'return 语句前调用了 writer.close() 但未调用 await writer.wait_closed()'
                    })
                else:
                    # 没有 close
                    issues.append({
                        'type': 'missing_writer_close',
                        'line': i + 1,
                        'message': f'return 语句前未关闭 writer: {stripped.strip()}'
                    })

    return issues, passed

def check_disconnect_function(filename: str) -> Tuple[List[Dict], List[Dict]]:
    """
    检查 disconnect 函数

    参数:
        filename: 要检查的文件路径

    返回:
        Tuple[List[Dict], List[Dict]]: (问题列表, 通过列表)
    """
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    issues = []
    passed = []

    # 找到 disconnect 函数
    in_disconnect = False
    func_start = 0

    for i, line in enumerate(lines):
        if 'async def disconnect' in line:
            in_disconnect = True
            func_start = i
            break

    if not in_disconnect:
        issues.append({
            'type': 'function_not_found',
            'message': '未找到 disconnect 函数'
        })
        return issues, passed

    # 检查函数体
    has_clear_events = False
    has_clear_results = False
    has_log = False

    for i in range(func_start, min(func_start + 50, len(lines))):
        line = lines[i]
        stripped = line.strip()

        if 'async def' in stripped and 'disconnect' not in stripped:
            break

        if 'self.connect_events.clear()' in line:
            has_clear_events = True
        if 'self.connect_results.clear()' in line:
            has_clear_results = True
        if 'logger' in line and ('event' in line or 'result' in line):
            has_log = True

    if has_clear_events and has_clear_results:
        passed.append({
            'line': func_start + 1,
            'message': 'disconnect 函数清理了 connect_events 和 connect_results'
        })
    else:
        if not has_clear_events:
            issues.append({
                'type': 'missing_clear_events',
                'line': func_start + 1,
                'message': 'disconnect 函数未清理 connect_events'
            })
        if not has_clear_results:
            issues.append({
                'type': 'missing_clear_results',
                'line': func_start + 1,
                'message': 'disconnect 函数未清理 connect_results'
            })

    if has_log:
        passed.append({
            'line': func_start + 1,
            'message': 'disconnect 函数清理事件和结果时有日志输出'
        })

    return issues, passed

def check_run_client_function(filename: str) -> Tuple[List[Dict], List[Dict]]:
    """
    检查 run_client 函数

    参数:
        filename: 要检查的文件路径

    返回:
        Tuple[List[Dict], List[Dict]]: (问题列表, 通过列表)
    """
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    issues = []
    passed = []

    # 找到 run_client 函数
    in_run_client = False
    func_start = 0

    for i, line in enumerate(lines):
        if 'async def run_client' in line:
            in_run_client = True
            func_start = i
            break

    if not in_run_client:
        issues.append({
            'type': 'function_not_found',
            'message': '未找到 run_client 函数'
        })
        return issues, passed

    # 检查函数体
    has_socks_server_var = False
    has_socks_server_close = False
    has_receiver_wait_for = False

    for i in range(func_start, min(func_start + 200, len(lines))):
        line = lines[i]
        stripped = line.strip()

        if 'async def' in stripped and 'run_client' not in stripped:
            break

        if 'socks_server = None' in line:
            has_socks_server_var = True
            passed.append({
                'line': i + 1,
                'message': 'run_client 函数声明了 socks_server 变量'
            })

        if 'socks_server.close()' in line:
            has_socks_server_close = True
            passed.append({
                'line': i + 1,
                'message': 'run_client 函数关闭了 socks_server'
            })

        if 'asyncio.wait_for(receiver_task' in line:
            has_receiver_wait_for = True
            passed.append({
                'line': i + 1,
                'message': 'run_client 函数使用 asyncio.wait_for 等待 receiver_task'
            })

    if has_socks_server_var and has_socks_server_close:
        passed.append({
            'line': func_start + 1,
            'message': 'run_client 函数正确管理了 socks_server 生命周期'
        })
    elif has_socks_server_var and not has_socks_server_close:
        issues.append({
            'type': 'missing_socks_server_close',
            'line': func_start + 1,
            'message': 'run_client 函数声明了 socks_server 但未关闭'
        })

    if has_receiver_wait_for:
        passed.append({
            'line': func_start + 1,
            'message': 'run_client 函数正确等待 receiver_task 完成'
        })

    return issues, passed

def check_open_channel_function(filename: str) -> Tuple[List[Dict], List[Dict]]:
    """
    检查 open_channel 函数

    参数:
        filename: 要检查的文件路径

    返回:
        Tuple[List[Dict], List[Dict]]: (问题列表, 通过列表)
    """
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    issues = []
    passed = []

    # 找到 open_channel 函数
    in_open_channel = False
    func_start = 0

    for i, line in enumerate(lines):
        if 'async def open_channel' in line:
            in_open_channel = True
            func_start = i
            break

    if not in_open_channel:
        issues.append({
            'type': 'function_not_found',
            'message': '未找到 open_channel 函数'
        })
        return issues, passed

    # 检查函数体中的异常处理
    in_try_block = False
    in_except_block = False
    has_cleanup_in_except = False

    for i in range(func_start, min(func_start + 80, len(lines))):
        line = lines[i]
        stripped = line.strip()

        if 'async def' in stripped and 'open_channel' not in stripped:
            break

        if 'try:' in stripped:
            in_try_block = True
        elif 'except' in stripped:
            in_except_block = True
        elif in_except_block:
            # 检查是否清理了事件和结果
            if 'self.connect_events.pop' in line or 'self.connect_results.pop' in line:
                has_cleanup_in_except = True
                passed.append({
                    'line': i + 1,
                    'message': 'open_channel 函数在异常处理中清理了事件或结果'
                })

    if in_try_block and in_except_block and has_cleanup_in_except:
        passed.append({
            'line': func_start + 1,
            'message': 'open_channel 函数正确处理了异常情况下的资源清理'
        })
    elif in_try_block and in_except_block and not has_cleanup_in_except:
        issues.append({
            'type': 'missing_cleanup_in_except',
            'line': func_start + 1,
            'message': 'open_channel 函数在异常处理中未清理事件和结果'
        })

    return issues, passed

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
    report.append("SMTP 隧道客户端修复验证报告 (改进版)")
    report.append("="*80)
    report.append(f"文件: {filename}")
    report.append("")

    total_issues = 0
    total_passed = 0

    # 检查 handle_client 函数
    report.append("1. handle_client 函数检查")
    report.append("-"*80)
    issues, passed = check_handle_client_function(filename)
    total_issues += len(issues)
    total_passed += len(passed)

    if issues:
        for issue in issues:
            report.append(f"  [问题] 行 {issue['line']}: {issue['message']}")
    else:
        report.append("  ✓ 所有提前返回点都正确关闭了 writer")

    if passed and not issues:
        report.append(f"  ✓ 通过 {len(passed)} 项检查")
    report.append("")

    # 检查 disconnect 函数
    report.append("2. disconnect 函数检查")
    report.append("-"*80)
    issues, passed = check_disconnect_function(filename)
    total_issues += len(issues)
    total_passed += len(passed)

    if issues:
        for issue in issues:
            report.append(f"  [问题] 行 {issue['line']}: {issue['message']}")
    else:
        report.append("  ✓ disconnect 函数正确清理了所有资源")

    if passed:
        for p in passed:
            report.append(f"  ✓ {p['message']}")
    report.append("")

    # 检查 run_client 函数
    report.append("3. run_client 函数检查")
    report.append("-"*80)
    issues, passed = check_run_client_function(filename)
    total_issues += len(issues)
    total_passed += len(passed)

    if issues:
        for issue in issues:
            report.append(f"  [问题] 行 {issue['line']}: {issue['message']}")
    else:
        report.append("  ✓ run_client 函数正确管理了所有资源")

    if passed:
        for p in passed:
            report.append(f"  ✓ {p['message']}")
    report.append("")

    # 检查 open_channel 函数
    report.append("4. open_channel 函数检查")
    report.append("-"*80)
    issues, passed = check_open_channel_function(filename)
    total_issues += len(issues)
    total_passed += len(passed)

    if issues:
        for issue in issues:
            report.append(f"  [问题] 行 {issue['line']}: {issue['message']}")
    else:
        report.append("  ✓ open_channel 函数正确处理了异常情况")

    if passed:
        for p in passed:
            report.append(f"  ✓ {p['message']}")
    report.append("")

    # 总结
    report.append("="*80)
    report.append("总结")
    report.append("="*80)
    if total_issues == 0:
        report.append(f"✓ 所有检查通过! 通过 {total_passed} 项检查。")
        report.append("✓ 修复已正确应用,进程泄漏问题应该已解决。")
    else:
        report.append(f"✗ 发现 {total_issues} 个问题需要修复。")
        report.append(f"✓ 通过 {total_passed} 项检查。")
    report.append("="*80)

    return "\n".join(report)

def main():
    if len(sys.argv) < 2:
        print("用法: python3 verify_fixes_v2.py <client.py 文件路径>")
        sys.exit(1)

    filename = sys.argv[1]
    report = generate_report(filename)
    print(report)

    # 如果有问题,返回非零退出码
    if total_issues := report.count("[问题]"):
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == '__main__':
    main()
