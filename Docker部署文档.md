# SMTP 隧道代理 - Docker 部署文档

## 目录

- [项目概述](#项目概述)
- [Docker 架构分析](#docker-架构分析)
- [快速开始](#快速开始)
- [构建镜像](#构建镜像)
- [部署方式](#部署方式)
- [配置管理](#配置管理)
- [用户管理](#用户管理)
- [监控与日志](#监控与日志)
- [故障排除](#故障排除)
- [生产环境优化](#生产环境优化)
- [安全建议](#安全建议)

---

## 项目概述

SMTP 隧道代理是一个基于 Python 的高性能 SMTP 隧道服务，使用 Docker 容器化部署可以提供更好的可移植性、隔离性和可扩展性。

### 技术栈

- **语言**: Python 3.11
- **核心依赖**:
  - `cryptography>=41.0.0` - 加密库（ChaCha20-Poly1305, HKDF, TLS）
  - `pyyaml>=6.0` - YAML 配置解析
- **运行时**: 异步 I/O（asyncio）
- **协议**: SMTP + 自定义二进制协议

### Docker 特性

- ✅ 多阶段构建，减小镜像体积
- ✅ 非 root 用户运行，提升安全性
- ✅ 健康检查，自动监控服务状态
- ✅ 资源限制，防止资源耗尽
- ✅ 日志管理，支持日志轮转
- ✅ 数据持久化，配置和数据分离

---

## Docker 架构分析

### 镜像结构

```
┌─────────────────────────────────────────────────────────────┐
│                    最终镜像 (运行时)                         │
│  基础: python:3.11-slim (~120MB)                            │
│                                                             │
│  包含内容:                                                  │
│  - Python 虚拟环境 (/opt/venv)                              │
│  - 应用程序文件 (/app)                                      │
│  - 配置文件 (/app/config)                                  │
│  - 数据文件 (/app/data)                                    │
│  - 日志文件 (/app/logs)                                    │
│                                                             │
│  用户: smtptunnel (非 root)                               │
│  端口: 587 (SMTP)                                         │
└─────────────────────────────────────────────────────────────┘
                              ↑
                              │ 从构建阶段复制
                              │
┌─────────────────────────────────────────────────────────────┐
│                    构建阶段 (builder)                      │
│  基础: python:3.11-slim                                   │
│                                                             │
│  操作:                                                      │
│  1. 安装构建依赖 (gcc, libc-dev, libssl-dev)               │
│  2. 创建虚拟环境                                           │
│  3. 安装 Python 依赖                                       │
│  4. 优化和清理                                             │
│                                                             │
│  最终只复制虚拟环境到运行时镜像                             │
└─────────────────────────────────────────────────────────────┘
```

### 多阶段构建优势

1. **减小镜像体积**: 最终镜像只包含运行时必需的文件
2. **提升安全性**: 构建依赖不包含在最终镜像中
3. **加快部署**: 镜像体积小，拉取和启动更快
4. **优化层缓存**: 依赖变化不影响应用代码层

### 文件系统布局
```
/opt/smtp-tunnel/              # 应用根目录
├── server.py                  # 服务器主程序
├── client.py                  # 客户端程序
├── common.py                  # 共享库（兼容层）
├── generate_certs.py          # 证书生成工具
├── smtp-tunnel-adduser        # 用户管理脚本
├── smtp-tunnel-deluser        # 用户删除脚本
├── smtp-tunnel-listusers      # 用户列表脚本
├── smtp-tunnel-update         # 更新脚本
├── entrypoint.sh              # 容器入口脚本
├── healthcheck.sh             # 健康检查脚本
│
├── protocol.py                # 二进制协议定义
├── crypto.py                  # 加密和认证功能
├── traffic.py                 # 流量伪装（DPI 规避）
├── smtp_message.py            # MIME 邮件生成
├── config.py                  # 配置管理
│
├── client_protocol.py         # 客户端协议定义
├── client_socks5.py           # SOCKS5 代理实现
├── client_tunnel.py           # 隧道客户端
└── client_server.py           # SOCKS5 服务器
│
├── server_protocol.py         # 服务器协议定义
├── server_connection.py       # 连接管理
├── server_tunnel.py           # 隧道会话
└── server_server.py           # 服务器类
│
└── venv/                     # Python 虚拟环境

/etc/smtp-tunnel/config/                   # 配置目录（卷）
├── config.yaml                # 服务器配置
└── users.yaml                 # 用户配置

/etc/smtp-tunnel/data/                     # 数据目录（卷）
├── server.crt                 # TLS 证书
├── server.key                 # TLS 私钥
└── ca.crt                     # CA 证书

/var/log/smtp-tunnel/                     # 日志目录（卷）
└── smtp-tunnel.log            # 应用日志
```

---

## 快速开始

### 前置条件

- Docker 20.10+
- Docker Compose 2.0+
- 至少 512MB 可用内存
- 端口 587 可用

### 一键启动
```bash
# 克隆项目
git clone https://github.com/purpose168/smtp-tunnel-proxy.git
cd smtp-tunnel-proxy

# 使用 Docker Compose 启动
docker compose up -d

# 查看日志
docker compose logs -f

# 添加第一个用户
docker compose exec smtp-tunnel python3 /opt/smtp-tunnel/smtp-tunnel-adduser alice
```

### 验证部署
```bash
# 检查容器状态
docker compose ps

# 检查健康状态
docker inspect smtp-tunnel-server | grep -A 10 Health

# 测试端口
telnet localhost 587
```

---

## 构建镜像

### 基础构建

```bash
# 构建镜像
docker build -t smtp-tunnel-server:latest .

# 查看镜像
docker images | grep smtp-tunnel

# 查看镜像大小
docker images smtp-tunnel-server:latest --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
```

### 自定义构建

```bash
# 指定 Python 版本
docker build \
  --build-arg PYTHON_VERSION=3.11 \
  -t smtp-tunnel-server:python3.11 .

# 指定应用版本
docker build \
  --build-arg APP_VERSION=1.3.0 \
  -t smtp-tunnel-server:v1.3.0 .

# 无缓存构建
docker build --no-cache -t smtp-tunnel-server:latest .
```

### 多平台构建

```bash
# 构建多架构镜像（需要 buildx）
docker buildx create --use
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t smtp-tunnel-server:latest \
  --push .
```

### 优化构建

```bash
# 使用 BuildKit 加速构建
DOCKER_BUILDKIT=1 docker build -t smtp-tunnel-server:latest .

# 查看构建历史
docker history smtp-tunnel-server:latest

# 分析镜像层
docker dive smtp-tunnel-server:latest
```

---

## 部署方式

### 方式一：Docker Compose（推荐）

#### 开发环境

```bash
# 启动服务
docker compose up -d

# 查看日志
docker compose logs -f

# 停止服务
docker compose down

# 停止并删除数据卷
docker compose down -v
```

#### 生产环境

```bash
# 使用生产配置启动
docker compose -f docker compose.prod.yml up -d

# 查看服务状态
docker compose -f docker compose.prod.yml ps

# 查看资源使用
docker stats smtp-tunnel-server-prod
```

### 方式二：Docker 命令行

#### 基础运行

```bash
docker run -d \
  --name smtp-tunnel \
  -p 587:587 \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  smtp-tunnel-server:latest
```

#### 完整配置运行

```bash
docker run -d \
  --name smtp-tunnel \
  --hostname smtp-tunnel \
  --network bridge \
  -p 587:587 \
  -e TZ=Asia/Shanghai \
  -e PYTHONUNBUFFERED=1 \
  -v $(pwd)/config:/app/config:ro \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  --restart unless-stopped \
  --health-cmd="/app/healthcheck.sh" \
  --health-interval=30s \
  --health-timeout=10s \
  --health-retries=3 \
  --memory=512m \
  --cpus=1.0 \
  --security-opt no-new-privileges:true \
  --read-only \
  --tmpfs /tmp \
  smtp-tunnel-server:latest
```

### 方式三：Kubernetes 部署

#### Deployment 配置

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: smtp-tunnel
  labels:
    app: smtp-tunnel
spec:
  replicas: 1
  selector:
    matchLabels:
      app: smtp-tunnel
  template:
    metadata:
      labels:
        app: smtp-tunnel
    spec:
      containers:
      - name: smtp-tunnel
        image: smtp-tunnel-server:latest
        ports:
        - containerPort: 587
          name: smtp
        env:
        - name: PYTHONUNBUFFERED
          value: "1"
        - name: TZ
          value: "Asia/Shanghai"
        volumeMounts:
        - name: config
          mountPath: /app/config
        - name: data
          mountPath: /app/data
        - name: logs
          mountPath: /app/logs
        resources:
          requests:
            memory: "128Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "1000m"
        livenessProbe:
          exec:
            command:
            - /app/healthcheck.sh
          initialDelaySeconds: 10
          periodSeconds: 30
          timeoutSeconds: 10
          failureThreshold: 3
        readinessProbe:
          exec:
            command:
            - /app/healthcheck.sh
          initialDelaySeconds: 5
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
      volumes:
      - name: config
        persistentVolumeClaim:
          claimName: smtp-tunnel-config
      - name: data
        persistentVolumeClaim:
          claimName: smtp-tunnel-data
      - name: logs
        persistentVolumeClaim:
          claimName: smtp-tunnel-logs
---
apiVersion: v1
kind: Service
metadata:
  name: smtp-tunnel
spec:
  selector:
    app: smtp-tunnel
  ports:
  - port: 587
    targetPort: 587
    name: smtp
  type: LoadBalancer
```

---

## 配置管理

### 初始配置
首次启动时，容器会自动创建默认配置文件：
```bash
# 查看生成的配置
docker exec smtp-tunnel cat /etc/smtp-tunnel/config/config.yaml

# 查看用户文件
docker exec smtp-tunnel cat /etc/smtp-tunnel/users.yaml
```

### 修改配置

#### 方式一：直接编辑
```bash
# 编辑配置文件
docker exec -it smtp-tunnel nano /etc/smtp-tunnel/config.yaml

# 重启容器应用配置
docker compose restart smtp-tunnel
```

#### 方式二：挂载配置文件
```bash
# 创建本地配置目录
mkdir -p config data logs

# 复制默认配置
docker cp smtp-tunnel:/etc/smtp-tunnel/config.yaml config/
docker cp smtp-tunnel:/etc/smtp-tunnel/users.yaml config/

# 编辑配置
nano config/config.yaml

# 重启容器
docker compose up -d
```

#### 方式三：环境变量覆盖

```yaml
# docker compose.yml
services:
  smtp-tunnel:
    environment:
      - SMTP_TUNNEL_HOSTNAME=mail.example.com
      - SMTP_TUNNEL_PORT=587
      - SMTP_TUNNEL_LOG_USERS=true
```

### 配置文件示例
```yaml
server:
  host: "0.0.0.0"
  port: 587
  hostname: "mail.example.com"
  cert_file: "/etc/smtp-tunnel/data/server.crt"
  key_file: "/etc/smtp-tunnel/data/server.key"
  users_file: "/etc/smtp-tunnel/config/users.yaml"
  log_users: true

client:
  server_host: "mail.example.com"
  server_port: 587
  socks_port: 1080
  socks_host: "127.0.0.1"
  ca_cert: "ca.crt"
```

### 证书管理

#### 自动生成证书
容器首次启动时会自动生成证书：
```bash
# 查看生成的证书
docker exec smtp-tunnel ls -la /etc/smtp-tunnel/data/

# 查看证书详情
docker exec smtp-tunnel openssl x509 -in /etc/smtp-tunnel/data/server.crt -noout -text
```

#### 手动生成证书
```bash
# 进入容器
docker exec -it smtp-tunnel bash

# 生成证书
cd /opt/smtp-tunnel
python3 generate_certs.py --hostname mail.example.com --output-dir /etc/smtp-tunnel/data

# 重启服务
exit
docker compose restart smtp-tunnel
```

#### 使用自定义证书

```bash
# 复制证书到数据目录
cp your-server.crt data/
cp your-server.key data/
cp your-ca.crt data/

# 设置权限
chmod 644 data/server.crt
chmod 600 data/server.key

# 重启容器
docker compose restart smtp-tunnel
```

---

## 用户管理

### 添加用户
```bash
# 添加用户（自动生成密钥）
docker compose exec smtp-tunnel python3 /opt/smtp-tunnel/smtp-tunnel-adduser alice

# 添加用户（指定密钥）
docker compose exec smtp-tunnel python3 /opt/smtp-tunnel/smtp-tunnel-adduser bob --secret mysecret

# 添加用户（IP 白名单）
docker compose exec smtp-tunnel python3 /opt/smtp-tunnel/smtp-tunnel-adduser carol \
  --whitelist 192.168.1.100 \
  --whitelist 10.0.0.0/8

# 添加用户（禁用日志）
docker compose exec smtp-tunnel python3 /opt/smtp-tunnel/smtp-tunnel-adduser dave --no-logging
```

### 删除用户
```bash
# 删除用户
docker compose exec smtp-tunnel python3 /opt/smtp-tunnel/smtp-tunnel-deluser alice

# 强制删除（不确认）
docker compose exec smtp-tunnel python3 /opt/smtp-tunnel/smtp-tunnel-deluser bob -f
```

### 列出用户
```bash
# 简单列表
docker compose exec smtp-tunnel python3 /opt/smtp-tunnel/smtp-tunnel-listusers

# 详细列表（显示密钥和白名单）
docker compose exec smtp-tunnel python3 /opt/smtp-tunnel/smtp-tunnel-listusers -v
```

### 获取客户端包
```bash
# 添加用户时自动生成 ZIP 包
docker compose exec smtp-tunnel python3 /opt/smtp-tunnel/smtp-tunnel-adduser alice

# 从容器复制 ZIP 包
docker cp smtp-tunnel:/opt/smtp-tunnel/alice.zip .

# 发送给用户
```

### 批量管理

```bash
# 批量添加用户
for user in user1 user2 user3; do
  docker compose exec smtp-tunnel python3 /app/smtp-tunnel-adduser $user
done

# 批量删除用户
for user in user1 user2 user3; do
  docker compose exec smtp-tunnel python3 /app/smtp-tunnel-deluser $user -f
done
```

---

## 监控与日志

### 查看日志
```bash
# 实时查看日志
docker compose logs -f

# 查看最近 100 行
docker compose logs --tail=100

# 查看特定时间的日志
docker compose logs --since 2024-01-10T00:00:00

# 查看容器日志
docker logs -f smtp-tunnel-server

# 查看应用日志文件
docker exec smtp-tunnel tail -f /var/log/smtp-tunnel/smtp-tunnel.log
```

### 日志配置

```yaml
# docker compose.yml
services:
  smtp-tunnel:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"      # 单个日志文件最大大小
        max-file: "3"        # 保留的日志文件数量
        compress: "true"     # 压缩旧日志
```

### 监控指标

```bash
# 查看容器资源使用
docker stats smtp-tunnel-server

# 查看容器详细信息
docker inspect smtp-tunnel-server

# 查看健康状态
docker inspect smtp-tunnel-server | grep -A 10 Health

# 查看进程
docker exec smtp-tunnel ps aux

# 查看网络连接
docker exec smtp-tunnel netstat -tlnp
```

### 集成监控工具

#### Prometheus + Grafana

```yaml
# docker compose.yml
services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
```

#### cAdvisor

```bash
docker run -d \
  --name=cadvisor \
  --volume=/:/rootfs:ro \
  --volume=/var/run:/var/run:ro \
  --volume=/sys:/sys:ro \
  --volume=/var/lib/docker/:/var/lib/docker:ro \
  --publish=8080:8080 \
  google/cadvisor:latest
```

---

## 故障排除

### 容器无法启动
```bash
# 查看容器日志
docker logs smtp-tunnel-server

# 查看容器状态
docker ps -a | grep smtp-tunnel

# 检查配置文件
docker exec smtp-tunnel cat /etc/smtp-tunnel/config.yaml

# 检查文件权限
docker exec smtp-tunnel ls -la /etc/smtp-tunnel/data/
```

### 端口被占用

```bash
# 检查端口占用
netstat -tlnp | grep 587
# 或
ss -tlnp | grep 587

# 停止占用端口的容器
docker stop <container_name>

# 使用不同端口
docker run -p 2587:587 smtp-tunnel-server:latest
```

### 健康检查失败

```bash
# 手动运行健康检查
docker exec smtp-tunnel /app/healthcheck.sh

# 检查进程
docker exec smtp-tunnel ps aux | grep server.py

# 检查端口监听
docker exec smtp-tunnel netstat -tlnp | grep 587

# 检查配置文件
docker exec smtp-tunnel cat /app/config/config.yaml
```

### 证书问题

```bash
# 检查证书文件
docker exec smtp-tunnel ls -la /app/data/

# 重新生成证书
docker exec -it smtp-tunnel bash
cd /app
python3 generate_certs.py --hostname mail.example.com --output-dir /app/data
exit
docker compose restart smtp-tunnel

# 验证证书
docker exec smtp-tunnel openssl x509 -in /app/data/server.crt -noout -text
```

### 权限问题

```bash
# 检查文件权限
docker exec smtp-tunnel ls -la /app/data/

# 修复权限
docker exec -u root smtp-tunnel chown -R smtptunnel:smtptunnel /app/data/
docker exec -u root smtp-tunnel chmod 600 /app/data/server.key
docker exec -u root smtp-tunnel chmod 644 /app/data/server.crt
```

### 网络问题

```bash
# 检查网络连接
docker exec smtp-tunnel ping -c 3 google.com

# 检查 DNS 解析
docker exec smtp-tunnel nslookup google.com

# 检查防火墙规则
docker exec smtp-tunnel iptables -L -n

# 重启网络
docker network prune
docker compose down
docker compose up -d
```

### 性能问题

```bash
# 查看资源使用
docker stats smtp-tunnel-server --no-stream

# 查看容器限制
docker inspect smtp-tunnel-server | grep -A 10 Memory
docker inspect smtp-tunnel-server | grep -A 10 Cpu

# 调整资源限制
docker update --memory=1g --cpus=2 smtp-tunnel-server

# 查看进程资源
docker exec smtp-tunnel top
```

---

## 生产环境优化

### 资源限制

```yaml
# docker compose.prod.yml
services:
  smtp-tunnel:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 256M
```

### 安全加固

```yaml
services:
  smtp-tunnel:
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
      - CHOWN
      - SETGID
      - SETUID
    read_only: true
    tmpfs:
      - /tmp
```

### 日志管理

```yaml
services:
  smtp-tunnel:
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "5"
        compress: "true"
```

### 数据持久化

```yaml
volumes:
  smtp-tunnel-config:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /var/lib/smtp-tunnel/config

  smtp-tunnel-data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /var/lib/smtp-tunnel/data

  smtp-tunnel-logs:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /var/lib/smtp-tunnel/logs
```

### 高可用部署

```yaml
# 使用负载均衡
version: '3.8'

services:
  smtp-tunnel-1:
    image: smtp-tunnel-server:latest
    ports:
      - "5871:587"
    volumes:
      - ./config:/app/config
      - ./data1:/app/data
    restart: always

  smtp-tunnel-2:
    image: smtp-tunnel-server:latest
    ports:
      - "5872:587"
    volumes:
      - ./config:/app/config
      - ./data2:/app/data
    restart: always

  loadbalancer:
    image: haproxy:2.8
    ports:
      - "587:587"
    volumes:
      - ./haproxy.cfg:/usr/local/etc/haproxy/haproxy.cfg:ro
    depends_on:
      - smtp-tunnel-1
      - smtp-tunnel-2
```

---

## 安全建议

### 1. 使用非 root 用户

镜像已配置为使用 `smtptunnel` 用户运行，不要修改为 root 用户。

### 2. 限制容器能力

```yaml
cap_drop:
  - ALL
cap_add:
  - NET_BIND_SERVICE
```

### 3. 只读文件系统

```yaml
read_only: true
tmpfs:
  - /tmp
  - /app/logs
```

### 4. 网络隔离

```yaml
networks:
  smtp-tunnel-network:
    driver: bridge
    internal: false  # 设为 true 可完全隔离网络
```

### 5. 资源限制

```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 1G
```

### 6. 定期更新

```bash
# 更新镜像
docker pull smtp-tunnel-server:latest

# 重新部署
docker compose up -d
```

### 7. 备份配置和数据

```bash
# 备份配置
docker cp smtp-tunnel:/app/config ./backup/config-$(date +%Y%m%d)

# 备份数据
docker cp smtp-tunnel:/app/data ./backup/data-$(date +%Y%m%d)

# 备份日志
docker cp smtp-tunnel:/app/logs ./backup/logs-$(date +%Y%m%d)
```

### 8. 监控和告警

设置监控和告警系统，及时发现异常情况。

### 9. 使用强密钥

使用 `smtp-tunnel-adduser` 自动生成强密钥，不要使用弱密钥。

### 10. 启用 IP 白名单

为每个用户配置 IP 白名单，限制访问来源。

---

## 附录

### A. 常用命令速查

```bash
# 构建镜像
docker build -t smtp-tunnel-server:latest .

# 启动服务
docker compose up -d

# 停止服务
docker compose down

# 查看日志
docker compose logs -f

# 添加用户
docker compose exec smtp-tunnel python3 /app/smtp-tunnel-adduser <username>

# 删除用户
docker compose exec smtp-tunnel python3 /app/smtp-tunnel-deluser <username>

# 列出用户
docker compose exec smtp-tunnel python3 /app/smtp-tunnel-listusers -v

# 进入容器
docker exec -it smtp-tunnel bash

# 查看资源使用
docker stats smtp-tunnel-server

# 查看健康状态
docker inspect smtp-tunnel-server | grep -A 10 Health
```

### B. 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `PYTHONUNBUFFERED` | 1 | 禁用 Python 输出缓冲 |
| `PYTHONDONTWRITEBYTECODE` | 1 | 禁止生成 .pyc 文件 |
| `SMTP_TUNNEL_HOME` | /app | 应用根目录 |
| `SMTP_TUNNEL_CONFIG` | /app/config | 配置目录 |
| `SMTP_TUNNEL_DATA` | /app/data | 数据目录 |
| `SMTP_TUNNEL_LOGS` | /app/logs | 日志目录 |
| `TZ` | UTC | 时区设置 |

### C. 端口说明

| 端口 | 协议 | 用途 |
|------|------|------|
| 587 | TCP | SMTP 提交端口（容器内部） |
| 587 | TCP | SMTP 提交端口（宿主机映射） |

### D. 卷说明

| 卷 | 路径 | 说明 |
|------|------|------|
| config | /app/config | 配置文件 |
| data | /app/data | 证书和数据 |
| logs | /app/logs | 日志文件 |

### E. 健康检查

健康检查脚本会验证：
- 服务器进程是否运行
- 端口 587 是否监听
- 配置文件是否存在
- 证书文件是否存在

---

## 更新日志

**版本 1.3.0**
- 添加 Docker 支持
- 实现多阶段构建
- 添加健康检查
- 优化镜像体积
- 添加生产环境配置

---

## 许可证

本项目仅供教育和授权使用。请负责任地使用，并遵守适用法律。

---

## 免责声明

本工具旨在用于合法的隐私和审查规避目的。用户有责任确保其使用符合适用的法律法规。

---

*文档生成时间: 2026-01-10*
