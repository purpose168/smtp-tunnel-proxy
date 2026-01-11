#!/bin/bash
# SMTP 隧道代理服务器 - 容器入口脚本
# 版本: 1.3.0

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  SMTP 隧道代理服务器${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查配置目录是否存在，如果不存在则创建
if [ ! -d "${SMTP_TUNNEL_CONFIG}" ]; then
    echo -e "${YELLOW}[信息]${NC} 配置目录不存在，正在创建..."
    mkdir -p ${SMTP_TUNNEL_CONFIG}
    echo -e "${GREEN}[成功]${NC} 配置目录已创建"
fi

# 检查配置文件
if [ ! -f "${SMTP_TUNNEL_CONFIG}/config.yaml" ] || [ ! -s "${SMTP_TUNNEL_CONFIG}/config.yaml" ]; then
    echo -e "${YELLOW}[信息]${NC} 配置文件不存在或为空，从默认配置创建..."
    exit 1
fi

# 检查证书文件
if [ ! -f "${SMTP_TUNNEL_DATA}/server.crt" ] || [ ! -f "${SMTP_TUNNEL_DATA}/server.key" ]; then
    echo -e "${YELLOW}[信息]${NC} 证书文件不存在，正在生成..."

    # 从配置文件读取主机名
    HOSTNAME=$(grep -E "^  hostname:" ${SMTP_TUNNEL_CONFIG}/config.yaml | sed 's/.*"\(.*\)".*/\1/' || echo "mail.example.com")

    cd ${SMTP_TUNNEL_HOME}
    python3 generate_certs.py --hostname "${HOSTNAME}" --output-dir ${SMTP_TUNNEL_DATA}

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}[成功]${NC} 证书已生成"
    else
        echo -e "${RED}[错误]${NC} 证书生成失败"
        exit 1
    fi
fi

# 更新配置文件中的证书路径（如果需要）
if grep -q "cert_file: \"server.crt\"" ${SMTP_TUNNEL_CONFIG}/config.yaml; then
    sed -i 's|cert_file: "server.crt"|cert_file: "/app/data/server.crt"|g' ${SMTP_TUNNEL_CONFIG}/config.yaml
    sed -i 's|key_file: "server.key"|key_file: "/app/data/server.key"|g' ${SMTP_TUNNEL_CONFIG}/config.yaml
    sed -i 's|users_file: "users.yaml"|users_file: "/app/config/users.yaml"|g' ${SMTP_TUNNEL_CONFIG}/config.yaml
fi

# 设置正确的文件权限
chmod 600 ${SMTP_TUNNEL_DATA}/server.key 2>/dev/null || true
chmod 644 ${SMTP_TUNNEL_DATA}/server.crt 2>/dev/null || true
chmod 600 ${SMTP_TUNNEL_CONFIG}/users.yaml 2>/dev/null || true

echo -e "${GREEN}[信息]${NC} 启动 SMTP 隧道服务器..."
echo ""

# 启动服务器
exec python3 ${SMTP_TUNNEL_HOME}/server.py -c ${SMTP_TUNNEL_CONFIG}/config.yaml "$@"
