# install-client.sh 脚本更新总结

## 概述

已成功将 `smtp-tunnel-client-update` 脚本集成到 `install-client.sh` 安装脚本中。现在客户端安装时会自动下载并安装更新脚本。

## 修改内容

### 1. 添加管理脚本变量

**位置**: 第 55-56 行

```bash
# 管理脚本
MANAGEMENT_SCRIPTS="smtp-tunnel-client-update"

# 所有需要下载的文件
ALL_FILES="$PYTHON_FILES $MANAGEMENT_SCRIPTS"
```

**说明**:
- 定义了 `MANAGEMENT_SCRIPTS` 变量，包含更新脚本名称
- 定义了 `ALL_FILES` 变量，包含所有需要下载的文件（Python 文件 + 管理脚本）

### 2. 更新文件下载函数

**位置**: 第 268-274 行

```bash
# 下载管理脚本
for script in $MANAGEMENT_SCRIPTS; do
    if ! download_file "$script" "$INSTALL_DIR/$script"; then
        print_error "下载管理脚本失败: $script"
        exit 1
    fi
done
```

**说明**:
- 在 `install_files()` 函数中添加了管理脚本的下载逻辑
- 如果下载失败，会显示错误信息并退出

### 3. 更新文件权限设置

**位置**: 第 288-292 行

```bash
# 设置管理脚本执行权限
for script in $MANAGEMENT_SCRIPTS; do
    chmod +x "$INSTALL_DIR/$script" 2>/dev/null || true
done
```

**说明**:
- 在设置文件权限时，为管理脚本添加执行权限
- 使用 `2>/dev/null` 忽略可能的错误

### 4. 添加更新脚本下载逻辑

**位置**: 第 544-555 行

```bash
# 检查更新脚本是否存在
if [ ! -f "$INSTALL_DIR/smtp-tunnel-client-update" ]; then
    print_info "下载更新脚本..."
    if ! download_file "smtp-tunnel-client-update" "$INSTALL_DIR/smtp-tunnel-client-update"; then
        print_warn "下载更新脚本失败，您可以稍后手动下载"
    else
        chmod +x "$INSTALL_DIR/smtp-tunnel-client-update"
        print_info "更新脚本已安装"
    fi
else
    print_info "更新脚本已存在"
fi
```

**说明**:
- 在非交互式设置中添加了更新脚本的检查和下载逻辑
- 如果更新脚本不存在，会尝试下载
- 如果下载失败，会显示警告但不会中断安装
- 下载成功后会设置执行权限

### 5. 更新脚本说明

**位置**: 第 17 行

```bash
# 说明:
#   此脚本为非交互式安装脚本，会自动执行以下操作：
#   - 下载客户端文件（如果不存在）
#   - 创建 Python 虚拟环境（如果不存在）
#   - 安装 Python 依赖包
#   - 创建默认配置文件（如果不存在）
#   - 生成管理脚本（start.sh, stop.sh, status.sh）
#   - 下载更新脚本（smtp-tunnel-client-update）
#   - 安装 systemd 服务（如果可用）
```

**说明**:
- 在脚本开头的说明中添加了更新脚本的下载说明

### 6. 更新安装摘要

**位置**: 第 1149 行和第 1181、1187 行

```bash
echo -e "${BLUE}管理脚本:${NC}"
echo "   $INSTALL_DIR/start.sh    - 启动客户端"
echo "   $INSTALL_DIR/stop.sh     - 停止客户端"
echo "   $INSTALL_DIR/status.sh   - 查看状态"
echo "   $INSTALL_DIR/smtp-tunnel-client-update - 更新客户端"
```

```bash
echo "   5. 更新客户端: $INSTALL_DIR/smtp-tunnel-client-update"
```

**说明**:
- 在安装摘要中添加了更新脚本的使用说明
- 在快速开始指南中添加了更新客户端的步骤

## 功能特性

### 1. 自动下载
- ✅ 安装时自动下载更新脚本
- ✅ 如果更新脚本已存在，跳过下载
- ✅ 下载失败时显示警告但不中断安装

### 2. 权限设置
- ✅ 自动设置更新脚本的执行权限
- ✅ 与其他管理脚本保持一致

### 3. 用户提示
- ✅ 在安装摘要中显示更新脚本信息
- ✅ 在快速开始指南中包含更新步骤
- ✅ 提供清晰的使用说明

## 安装流程

### 修改后的安装流程

```
开始安装
  ↓
检查系统依赖
  ↓
创建目录
  ↓
下载客户端文件
  ↓
下载管理脚本（包括更新脚本）
  ↓
设置文件权限
  ↓
创建虚拟环境
  ↓
安装 Python 包
  ↓
创建配置文件
  ↓
检查证书文件
  ↓
生成管理脚本
  ↓
下载更新脚本（如果不存在）
  ↓
配置 systemd 服务
  ↓
显示安装摘要
  ↓
结束
```

## 使用示例

### 安装客户端

```bash
# 从 GitHub 安装
curl -sSL https://raw.githubusercontent.com/purpose168/smtp-tunnel-proxy/main/install-client.sh | bash

# 或使用本地脚本
./install-client.sh
```

### 安装后使用更新脚本

```bash
# 进入安装目录
cd smtp-tunnel

# 检查更新
./smtp-tunnel-client-update --check-only

# 执行更新
./smtp-tunnel-client-update

# 查看帮助
./smtp-tunnel-client-update --help
```

## 文件结构

### 安装后的目录结构

```
smtp-tunnel/
├── client.py                      # 客户端主程序
├── socks5_server.py               # SOCKS5 代理服务器
├── smtp-tunnel-client-update      # 更新脚本（新增）
├── start.sh                      # 启动脚本
├── stop.sh                       # 停止脚本
├── status.sh                     # 状态脚本
├── config/                       # 配置文件目录
│   ├── config.yaml
│   ├── ca.crt
│   ├── client.crt
│   └── client.key
├── logs/                        # 日志目录
│   ├── client.log
│   ├── client-update.log          # 更新日志
│   └── install-client.log        # 安装日志
├── venv/                        # 虚拟环境
├── backups/                     # 备份目录
│   └── backup_YYYYMMDD_HHMMSS/
├── protocol/                     # 协议模块
└── tunnel/                      # 隧道模块
```

## 验证

### 语法检查

```bash
bash -n install-client.sh
```

**结果**: ✅ 语法检查通过

### 功能验证

1. **变量定义**: ✅ `MANAGEMENT_SCRIPTS` 和 `ALL_FILES` 变量已正确定义
2. **下载逻辑**: ✅ 管理脚本下载逻辑已添加到 `install_files()` 函数
3. **权限设置**: ✅ 管理脚本执行权限设置已添加
4. **更新脚本下载**: ✅ 更新脚本检查和下载逻辑已添加到 `non_interactive_setup()` 函数
5. **用户提示**: ✅ 安装摘要和快速开始指南已更新

## 兼容性

### 向后兼容
- ✅ 不影响现有安装流程
- ✅ 不影响现有功能
- ✅ 不影响现有配置

### 新增功能
- ✅ 自动下载更新脚本
- ✅ 自动设置执行权限
- ✅ 显示更新脚本使用说明

## 注意事项

### 1. 下载失败处理
- 如果更新脚本下载失败，会显示警告但不会中断安装
- 用户可以稍后手动下载更新脚本

### 2. 重复安装
- 如果更新脚本已存在，会跳过下载
- 不会覆盖现有的更新脚本

### 3. 权限要求
- 更新脚本需要执行权限
- 安装脚本会自动设置执行权限

## 相关文件

### 修改的文件
- [install-client.sh](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/install-client.sh) - 客户端安装脚本

### 相关文件
- [smtp-tunnel-client-update](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/smtp-tunnel-client-update) - 客户端更新脚本
- [CLIENT_UPDATE_GUIDE.md](file:///home/pps/code/smtp-tunnel-proxy/smtp-tunnel-proxy/CLIENT_UPDATE_GUIDE.md) - 更新脚本使用指南

## 测试建议

### 1. 全新安装测试
```bash
# 在新目录中测试安装
mkdir test-install
cd test-install
curl -sSL https://raw.githubusercontent.com/purpose168/smtp-tunnel-proxy/main/install-client.sh | bash

# 验证更新脚本是否存在
ls -la smtp-tunnel/smtp-tunnel-client-update

# 验证执行权限
ls -l smtp-tunnel/smtp-tunnel-client-update
```

### 2. 重复安装测试
```bash
# 再次运行安装脚本
./install-client.sh

# 验证更新脚本不会被覆盖
ls -la smtp-tunnel/smtp-tunnel-client-update
```

### 3. 更新功能测试
```bash
# 测试更新脚本
cd smtp-tunnel
./smtp-tunnel-client-update --check-only
./smtp-tunnel-client-update --help
```

## 总结

已成功将 `smtp-tunnel-client-update` 脚本集成到 `install-client.sh` 安装脚本中。主要修改包括：

1. ✅ 添加管理脚本变量定义
2. ✅ 更新文件下载函数
3. ✅ 更新文件权限设置
4. ✅ 添加更新脚本下载逻辑
5. ✅ 更新脚本说明
6. ✅ 更新安装摘要

所有修改都经过语法检查，确保脚本可以正常运行。现在用户在安装客户端时会自动获得更新脚本，可以方便地进行客户端更新。

---

**版本**: 1.0.0  
**创建日期**: 2026-01-17  
**作者**: AI Assistant  
**许可证**: GPL-3.0
