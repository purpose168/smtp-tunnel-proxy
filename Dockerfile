# SMTP 隧道代理 - 服务器 Dockerfile
# 多阶段构建以减小最终镜像体积
# 版本: 1.3.0

# ============================================================================
# 阶段 1: 构建阶段 - 安装依赖和准备环境
# ============================================================================
FROM python:3.11-slim AS builder

# 设置构建参数
ARG PYTHON_VERSION=3.11
ARG APP_VERSION=1.3.0

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# 创建虚拟环境
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 复制依赖文件
COPY requirements.txt /tmp/

# 安装 Python 依赖到虚拟环境
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# ============================================================================
# 阶段 2: 运行阶段 - 最小化镜像
# ============================================================================
FROM python:3.11-slim

# 设置标签
LABEL maintainer="SMTP Tunnel Proxy" \
      version="${APP_VERSION}" \
      description="SMTP Tunnel Proxy Server - Docker image"

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    SMTP_TUNNEL_HOME="/app" \
    SMTP_TUNNEL_CONFIG="/app/config" \
    SMTP_TUNNEL_DATA="/app/data" \
    SMTP_TUNNEL_LOGS="/app/logs"

# 安装运行时依赖（最小化）
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates

# 从构建阶段复制虚拟环境
COPY --from=builder /opt/venv /opt/venv

# 创建非 root 用户
RUN groupadd -r smtptunnel && \
    useradd -r -g smtptunnel -d ${SMTP_TUNNEL_HOME} -s /sbin/nologin -c "SMTP Tunnel User" smtptunnel

# 创建必要的目录结构
RUN mkdir -p ${SMTP_TUNNEL_HOME} \
    ${SMTP_TUNNEL_CONFIG} \
    ${SMTP_TUNNEL_DATA} \
    ${SMTP_TUNNEL_LOGS} \
    && chown -R smtptunnel:smtptunnel ${SMTP_TUNNEL_HOME}

# 复制应用程序文件
COPY server.py ${SMTP_TUNNEL_HOME}/
COPY common.py ${SMTP_TUNNEL_HOME}/
COPY generate_certs.py ${SMTP_TUNNEL_HOME}/
COPY smtp-tunnel-adduser ${SMTP_TUNNEL_HOME}/
COPY smtp-tunnel-deluser ${SMTP_TUNNEL_HOME}/
COPY smtp-tunnel-listusers ${SMTP_TUNNEL_HOME}/
COPY smtp-tunnel-update ${SMTP_TUNNEL_HOME}/

# 复制默认配置文件并重命名为实际文件名
COPY config.yaml ${SMTP_TUNNEL_CONFIG}/config.yaml

# 创建一个初始的用户配置文件（包含默认用户）
RUN echo 'users:\n  admin:\n    secret: "admin-secret-key-change-in-production"\n    whitelist: []\n    logging: true' > ${SMTP_TUNNEL_CONFIG}/users.yaml && \
    chmod 644 ${SMTP_TUNNEL_CONFIG}/users.yaml

# 复制启动脚本
COPY entrypoint.sh ${SMTP_TUNNEL_HOME}/entrypoint.sh
COPY healthcheck.sh ${SMTP_TUNNEL_HOME}/healthcheck.sh

# 设置脚本执行权限
RUN chmod +x ${SMTP_TUNNEL_HOME}/entrypoint.sh && \
    chmod +x ${SMTP_TUNNEL_HOME}/healthcheck.sh

# 切换到非 root 用户
USER smtptunnel

# 设置工作目录
WORKDIR ${SMTP_TUNNEL_HOME}

# 暴露端口
EXPOSE 587

# 设置卷
VOLUME ["${SMTP_TUNNEL_CONFIG}", "${SMTP_TUNNEL_DATA}", "${SMTP_TUNNEL_LOGS}"]

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD ${SMTP_TUNNEL_HOME}/healthcheck.sh

# 设置入口点
ENTRYPOINT ["/app/entrypoint.sh"]

# 默认命令
CMD []

# ============================================================================
# 使用说明
# ============================================================================
# 构建镜像:
#   docker build -t smtp-tunnel-server:latest .
#
# 运行容器:
#   docker run -d \
#     --name smtp-tunnel \
#     -p 587:587 \
#     -v smtp-tunnel-config:/app/config \
#     -v smtp-tunnel-data:/app/data \
#     -v smtp-tunnel-logs:/app/logs \
#     smtp-tunnel-server:latest
#
# 添加用户:
#   docker exec -it smtp-tunnel python3 /app/smtp-tunnel-adduser alice
#
# 查看日志:
#   docker logs -f smtp-tunnel
#
# 查看用户:
#   docker exec -it smtp-tunnel python3 /app/smtp-tunnel-listusers -v
# ============================================================================
