# SMTP 隧道客户端更新脚本

## 快速开始

### 基本使用

```bash
# 正常更新
./smtp-tunnel-client-update

# 仅检查版本
./smtp-tunnel-client-update --check-only

# 更新但不重启
./smtp-tunnel-client-update --no-restart

# 强制更新
./smtp-tunnel-client-update --force

# 调试模式
./smtp-tunnel-client-update --debug
```

### 查看帮助

```bash
./smtp-tunnel-client-update --help
```

## 功能特性

- ✅ 自动版本检查
- ✅ 从 GitHub 下载最新版本
- ✅ 文件完整性校验
- ✅ 自动备份和回滚
- ✅ 更新 Python 依赖
- ✅ 自动重启客户端
- ✅ 详细的日志记录
- ✅ 错误处理和重试机制

## 文档

- [详细使用说明](CLIENT_UPDATE_GUIDE.md) - 完整的使用文档
- [开发总结](CLIENT_UPDATE_SUMMARY.md) - 开发过程和技术细节

## 测试

```bash
# 运行测试脚本
./test-client-update.sh
```

## 日志

```bash
# 查看更新日志
cat logs/client-update.log

# 实时查看日志
tail -f logs/client-update.log
```

## 备份

备份自动保存在 `backups/` 目录，格式为 `backup_YYYYMMDD_HHMMSS/`。

```bash
# 查看备份
ls -la backups/

# 手动回滚（如果需要）
cp -r backups/backup_20260117_100000/* .
./stop.sh
./start.sh
```

## 故障排除

### 更新失败

1. 查看日志：`cat logs/client-update.log`
2. 检查网络连接
3. 脚本会自动回滚到备份版本

### 客户端启动失败

1. 查看客户端日志：`cat logs/client.log`
2. 检查配置文件：`cat config/config.yaml`
3. 检查证书文件是否存在

## 支持

如有问题，请访问：
- GitHub: https://github.com/purpose168/smtp-tunnel-proxy
- Issues: https://github.com/purpose168/smtp-tunnel-proxy/issues

## 许可证

GPL-3.0
