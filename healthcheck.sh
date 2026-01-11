#!/bin/bash
# SMTP 隧道代理服务器 - 健康检查脚本
# 版本: 1.3.0

# 检查进程是否运行
if ! pgrep -f "server.py" > /dev/null; then
    echo "服务器进程未运行"
    exit 1
fi

# 检查端口是否监听
if ! nc -z localhost 587 2>/dev/null; then
    echo "端口 587 未监听"
    exit 1
fi

# 检查配置文件
if [ ! -f "${SMTP_TUNNEL_CONFIG}/config.yaml" ]; then
    echo "配置文件不存在"
    exit 1
fi

# 检查证书文件
if [ ! -f "${SMTP_TUNNEL_DATA}/server.crt" ] || [ ! -f "${SMTP_TUNNEL_DATA}/server.key" ]; then
    echo "证书文件不存在"
    exit 1
fi

echo "健康检查通过"
exit 0
