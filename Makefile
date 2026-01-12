# SMTP 隧道代理 - Makefile
# 简化 Docker 构建和部署操作

.PHONY: help build push run stop restart logs clean test shell adduser deluser listusers build-client build-client-onefile build-client-debug build-client-windows build-client-windows-dir build-server build-server-onefile build-server-debug clean-dist install-pyinstaller list-client list-server list-all install-wine check-wine clean-docker

# 默认目标
.DEFAULT_GOAL := help

# 变量定义
IMAGE_NAME := smtp-tunnel-server
IMAGE_TAG := latest
VERSION := 1.3.0
CONTAINER_NAME := smtp-tunnel-server

# PyInstaller 打包变量
PYINSTALLER := pyinstaller
CLIENT_SCRIPT := client.py
CLIENT_NAME := smtp-tunnel-client
SERVER_SCRIPT := server.py
SERVER_NAME := smtp-tunnel-server
DIST_DIR := dist
BUILD_DIR := build
CLIENT_ICON := 

# Python 虚拟环境
VENV_DIR := venv
VENV_PYTHON := $(VENV_DIR)/bin/python
VENV_PIP := $(VENV_DIR)/bin/pip

# 颜色定义
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[1;33m
RED := \033[0;31m
NC := \033[0m

# 帮助信息
help: ## 显示帮助信息
	@echo "$(BLUE)========================================$(NC)"
	@echo "$(BLUE)  SMTP 隧道代理 - Docker 命令$(NC)"
	@echo "$(BLUE)========================================$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(YELLOW)示例:$(NC)"
	@echo "  make build              # 构建镜像"
	@echo "  make run                # 启动容器"
	@echo "  make adduser USER=alice # 添加用户"

# 构建镜像
build: ## 构建 Docker 镜像
	@echo "$(BLUE)[构建]$(NC) 构建 Docker 镜像..."
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .
	@echo "$(GREEN)[完成]$(NC) 镜像构建成功: $(IMAGE_NAME):$(IMAGE_TAG)"

# 构建镜像（无缓存）
build-no-cache: ## 构建 Docker 镜像（无缓存）
	@echo "$(BLUE)[构建]$(NC) 构建 Docker 镜像（无缓存）..."
	docker build --no-cache -t $(IMAGE_NAME):$(IMAGE_TAG) .
	@echo "$(GREEN)[完成]$(NC) 镜像构建成功: $(IMAGE_NAME):$(IMAGE_TAG)"

# 构建多架构镜像
build-multi: ## 构建多架构镜像（需要 buildx）
	@echo "$(BLUE)[构建]$(NC) 构建多架构镜像..."
	docker buildx create --use
	docker buildx build \
		--platform linux/amd64,linux/arm64 \
		-t $(IMAGE_NAME):$(IMAGE_TAG) \
		--push .
	@echo "$(GREEN)[完成]$(NC) 多架构镜像构建成功"

# 推送镜像
push: ## 推送镜像到仓库
	@echo "$(BLUE)[推送]$(NC) 推送镜像到仓库..."
	docker push $(IMAGE_NAME):$(IMAGE_TAG)
	@echo "$(GREEN)[完成]$(NC) 镜像推送成功"

# 启动容器
run: ## 启动容器
	@echo "$(BLUE)[启动]$(NC) 启动容器..."
	docker run -d \
		--name $(CONTAINER_NAME) \
		-p 587:587 \
		-v $(PWD)/config:/app/config \
		-v $(PWD)/data:/app/data \
		-v $(PWD)/logs:/app/logs \
		--restart unless-stopped \
		$(IMAGE_NAME):$(IMAGE_TAG)
	@echo "$(GREEN)[完成]$(NC) 容器启动成功: $(CONTAINER_NAME)"

# 停止容器
stop: ## 停止容器
	@echo "$(BLUE)[停止]$(NC) 停止容器..."
	docker stop $(CONTAINER_NAME)
	@echo "$(GREEN)[完成]$(NC) 容器已停止"

# 重启容器
restart: ## 重启容器
	@echo "$(BLUE)[重启]$(NC) 重启容器..."
	docker restart $(CONTAINER_NAME)
	@echo "$(GREEN)[完成]$(NC) 容器已重启"

# 删除容器
rm: ## 删除容器
	@echo "$(BLUE)[删除]$(NC) 删除容器..."
	docker rm -f $(CONTAINER_NAME)
	@echo "$(GREEN)[完成]$(NC) 容器已删除"

# 查看日志
logs: ## 查看容器日志
	docker logs -f $(CONTAINER_NAME)

# 查看日志（最近 100 行）
logs-tail: ## 查看容器日志（最近 100 行）
	docker logs --tail=100 $(CONTAINER_NAME)

# 查看状态
status: ## 查看容器状态
	docker ps -a | grep $(CONTAINER_NAME)

# 查看资源使用
stats: ## 查看容器资源使用
	docker stats $(CONTAINER_NAME)

# 进入容器
shell: ## 进入容器 shell
	docker exec -it $(CONTAINER_NAME) bash

# 清理
clean: ## 清理未使用的镜像和容器
	@echo "$(BLUE)[清理]$(NC) 清理未使用的镜像和容器..."
	docker system prune -f
	@echo "$(GREEN)[完成]$(NC) 清理完成"

# 清理所有
clean-all: ## 清理所有未使用的资源
	@echo "$(BLUE)[清理]$(NC) 清理所有未使用的资源..."
	docker system prune -a -f
	@echo "$(GREEN)[完成]$(NC) 清理完成"

# 添加用户
adduser: ## 添加用户 (用法: make adduser USER=alice)
	@if [ -z "$(USER)" ]; then \
		echo "$(RED)[错误]$(NC) 请指定用户名: make adduser USER=alice"; \
		exit 1; \
	fi
	@echo "$(BLUE)[用户]$(NC) 添加用户: $(USER)"
	docker exec $(CONTAINER_NAME) python3 /app/smtp-tunnel-adduser $(USER)

# 删除用户
deluser: ## 删除用户 (用法: make deluser USER=alice)
	@if [ -z "$(USER)" ]; then \
		echo "$(RED)[错误]$(NC) 请指定用户名: make deluser USER=alice"; \
		exit 1; \
	fi
	@echo "$(BLUE)[用户]$(NC) 删除用户: $(USER)"
	docker exec $(CONTAINER_NAME) python3 /app/smtp-tunnel-deluser $(USER)

# 列出用户
listusers: ## 列出所有用户
	@echo "$(BLUE)[用户]$(NC) 用户列表:"
	docker exec $(CONTAINER_NAME) python3 /app/smtp-tunnel-listusers -v

# 列出用户（简单）
listusers-simple: ## 列出所有用户（简单）
	@echo "$(BLUE)[用户]$(NC) 用户列表:"
	docker exec $(CONTAINER_NAME) python3 /app/smtp-tunnel-listusers

# 测试连接
test: ## 测试连接
	@echo "$(BLUE)[测试]$(NC) 测试 SMTP 隧道连接..."
	@echo "EHLO test.com" | nc -w 5 localhost 587 || echo "$(RED)[失败]$(NC) 连接失败"

# 健康检查
health: ## 健康检查
	@echo "$(BLUE)[健康]$(NC) 检查容器健康状态..."
	docker exec $(CONTAINER_NAME) /app/healthcheck.sh

# 查看配置
config: ## 查看配置文件
	docker exec $(CONTAINER_NAME) cat /app/config/config.yaml

# 查看用户配置
users-config: ## 查看用户配置文件
	docker exec $(CONTAINER_NAME) cat /app/config/users.yaml

# 备份
backup: ## 备份配置和数据
	@echo "$(BLUE)[备份]$(NC) 备份配置和数据..."
	@mkdir -p backup
	@docker cp $(CONTAINER_NAME):/app/config backup/config-$$(date +%Y%m%d-%H%M%S)
	@docker cp $(CONTAINER_NAME):/app/data backup/data-$$(date +%Y%m%d-%H%M%S)
	@docker cp $(CONTAINER_NAME):/app/logs backup/logs-$$(date +%Y%m%d-%H%M%S)
	@echo "$(GREEN)[完成]$(NC) 备份完成: backup/"

# 恢复
restore: ## 恢复配置和数据 (用法: make restore BACKUP=backup/config-20240110)
	@if [ -z "$(BACKUP)" ]; then \
		echo "$(RED)[错误]$(NC) 请指定备份路径: make restore BACKUP=backup/config-20240110"; \
		exit 1; \
	fi
	@echo "$(BLUE)[恢复]$(NC) 恢复配置和数据..."
	@docker cp $(BACKUP)/config.yaml $(CONTAINER_NAME):/app/config/config.yaml
	@docker cp $(BACKUP)/users.yaml $(CONTAINER_NAME):/app/config/users.yaml
	@docker cp $(BACKUP)/server.crt $(CONTAINER_NAME):/app/data/server.crt
	@docker cp $(BACKUP)/server.key $(CONTAINER_NAME):/app/data/server.key
	@docker cp $(BACKUP)/ca.crt $(CONTAINER_NAME):/app/data/ca.crt
	@echo "$(GREEN)[完成]$(NC) 恢复完成，请重启容器: make restart"

# 更新镜像
update: ## 更新镜像并重启容器
	@echo "$(BLUE)[更新]$(NC) 更新镜像..."
	@docker pull $(IMAGE_NAME):$(IMAGE_TAG) || make build
	@echo "$(BLUE)[更新]$(NC) 重启容器..."
	@docker stop $(CONTAINER_NAME)
	@docker rm $(CONTAINER_NAME)
	@make run
	@echo "$(GREEN)[完成]$(NC) 更新完成"

# 查看镜像
images: ## 查看镜像
	docker images | grep $(IMAGE_NAME)

# 查看容器
ps: ## 查看容器
	docker ps -a | grep $(CONTAINER_NAME)

# 查看网络
network: ## 查看网络
	docker network ls | grep smtp-tunnel

# 查看卷
volumes: ## 查看卷
	docker volume ls | grep smtp-tunnel

# Docker Compose 命令
compose-up: ## 使用 Docker Compose 启动
	docker-compose up -d

compose-down: ## 使用 Docker Compose 停止
	docker-compose down

compose-logs: ## 使用 Docker Compose 查看日志
	docker-compose logs -f

compose-restart: ## 使用 Docker Compose 重启
	docker-compose restart

compose-ps: ## 使用 Docker Compose 查看状态
	docker-compose ps

# 生产环境
prod-up: ## 使用生产配置启动
	docker-compose -f docker-compose.prod.yml up -d

prod-down: ## 使用生产配置停止
	docker-compose -f docker-compose.prod.yml down

prod-logs: ## 使用生产配置查看日志
	docker-compose -f docker-compose.prod.yml logs -f

# 安装
install: build run ## 构建并运行（首次安装）
	@echo "$(GREEN)[安装]$(NC) 安装完成！"
	@echo "$(BLUE)[下一步]$(NC) 添加用户: make adduser USER=alice"

# 卸载
uninstall: stop rm ## 停止并删除容器
	@echo "$(YELLOW)[警告]$(NC) 配置和数据卷未被删除"
	@echo "$(BLUE)[下一步]$(NC) 如需删除，请手动删除: rm -rf config data logs"

# 完整安装（包括目录创建）
install-full: ## 完整安装（创建目录并启动）
	@echo "$(BLUE)[安装]$(NC) 创建必要的目录..."
	@mkdir -p config data logs
	@make install

# 安装 PyInstaller
install-pyinstaller: ## 安装 PyInstaller
	@echo "$(BLUE)[打包]$(NC) 安装 PyInstaller..."
	@pip install pyinstaller
	@echo "$(GREEN)[完成]$(NC) PyInstaller 安装成功"

# 检查虚拟环境
check-venv:
	@if [ -d "$(VENV_DIR)" ]; then \
		echo "$(GREEN)[检查]$(NC) 虚拟环境存在"; \
		exit 0; \
	else \
		echo "$(YELLOW)[警告]$(NC) 虚拟环境不存在，尝试使用系统 Python"; \
		exit 1; \
	fi

# 使用虚拟环境中的 Python
venv-pip:
	@if [ -d "$(VENV_DIR)" ]; then \
		$(VENV_PIP) install pyinstaller; \
	else \
		pip install pyinstaller; \
	fi

# 构建客户端（目录模式 - 推荐）
build-client: ## 构建客户端（目录模式，推荐）
	@echo "$(BLUE)[打包]$(NC) 构建客户端（目录模式）..."
	@mkdir -p $(DIST_DIR)
	@if [ -d "$(VENV_DIR)" ]; then \
		$(VENV_PYTHON) -m PyInstaller \
			--name $(CLIENT_NAME) \
			--onedir \
			--collect-all common \
			--collect-all client_protocol \
			--collect-all client_socks5 \
			--collect-all client_tunnel \
			--collect-all client_server \
			--hidden-import=asyncio \
			--hidden-import=ssl \
			--hidden-import=cryptography \
			--hidden-import=yaml \
			--clean \
			$(CLIENT_SCRIPT); \
	else \
		python3 -m PyInstaller \
			--name $(CLIENT_NAME) \
			--onedir \
			--collect-all common \
			--collect-all client_protocol \
			--collect-all client_socks5 \
			--collect-all client_tunnel \
			--collect-all client_server \
			--hidden-import=asyncio \
			--hidden-import=ssl \
			--hidden-import=cryptography \
			--hidden-import=yaml \
			--clean \
			$(CLIENT_SCRIPT); \
	fi
	@echo "$(GREEN)[完成]$(NC) 客户端已打包到: $(DIST_DIR)/$(CLIENT_NAME)/"
	@echo "$(BLUE)[提示]$(NC) 运行: ./$(DIST_DIR)/$(CLIENT_NAME)/$(CLIENT_NAME)"

# 构建客户端（单文件模式 - 便携版）
build-client-onefile: ## 构建客户端（单文件模式，便携版）
	@echo "$(BLUE)[打包]$(NC) 构建客户端（单文件模式）..."
	@mkdir -p $(DIST_DIR)
	@if [ -d "$(VENV_DIR)" ]; then \
		$(VENV_PYTHON) -m PyInstaller \
			--name $(CLIENT_NAME) \
			--onefile \
			--collect-all common \
			--collect-all client_protocol \
			--collect-all client_socks5 \
			--collect-all client_tunnel \
			--collect-all client_server \
			--hidden-import=asyncio \
			--hidden-import=ssl \
			--hidden-import=cryptography \
			--hidden-import=yaml \
			--clean \
			$(CLIENT_SCRIPT); \
	else \
		python3 -m PyInstaller \
			--name $(CLIENT_NAME) \
			--onefile \
			--collect-all common \
			--collect-all client_protocol \
			--collect-all client_socks5 \
			--collect-all client_tunnel \
			--collect-all client_server \
			--hidden-import=asyncio \
			--hidden-import=ssl \
			--hidden-import=cryptography \
			--hidden-import=yaml \
			--clean \
			$(CLIENT_SCRIPT); \
	fi
	@echo "$(GREEN)[完成]$(NC) 客户端已打包到: $(DIST_DIR)/$(CLIENT_NAME)"
	@echo "$(BLUE)[提示]$(NC) 运行: ./$(DIST_DIR)/$(CLIENT_NAME)"

# 构建客户端（调试模式 - 带调试信息）
build-client-debug: ## 构建客户端（调试模式）
	@echo "$(BLUE)[打包]$(NC) 构建客户端（调试模式）..."
	@mkdir -p $(DIST_DIR)
	@if [ -d "$(VENV_DIR)" ]; then \
		$(VENV_PYTHON) -m PyInstaller \
			--name $(CLIENT_NAME)-debug \
			--onedir \
			--debug all \
			--collect-all common \
			--collect-all client_protocol \
			--collect-all client_socks5 \
			--collect-all client_tunnel \
			--collect-all client_server \
			--hidden-import=asyncio \
			--hidden-import=ssl \
			--hidden-import=cryptography \
			--hidden-import=yaml \
			$(CLIENT_SCRIPT); \
	else \
		python3 -m PyInstaller \
			--name $(CLIENT_NAME)-debug \
			--onedir \
			--debug all \
			--collect-all common \
			--collect-all client_protocol \
			--collect-all client_socks5 \
			--collect-all client_tunnel \
			--collect-all client_server \
			--hidden-import=asyncio \
			--hidden-import=ssl \
			--hidden-import=cryptography \
			--hidden-import=yaml \
			$(CLIENT_SCRIPT); \
	fi
	@echo "$(GREEN)[完成]$(NC) 调试版客户端已打包到: $(DIST_DIR)/$(CLIENT_NAME)-debug/"
	@echo "$(BLUE)[提示]$(NC) 运行: ./$(DIST_DIR)/$(CLIENT_NAME)-debug/$(CLIENT_NAME)-debug"



# 构建服务端（目录模式 - 推荐）
build-server: ## 构建服务端（目录模式，推荐）
	@echo "$(BLUE)[打包]$(NC) 构建服务端（目录模式）..."
	@mkdir -p $(DIST_DIR)
	@if [ -d "$(VENV_DIR)" ]; then \
		$(VENV_PYTHON) -m PyInstaller \
			--name $(SERVER_NAME) \
			--onedir \
			--collect-all common \
			--collect-all protocol \
			--collect-all crypto \
			--collect-all traffic \
			--collect-all smtp_message \
			--collect-all config \
			--collect-all logger \
			--collect-all server_protocol \
			--collect-all server_connection \
			--collect-all server_tunnel \
			--collect-all server_server \
			--hidden-import=asyncio \
			--hidden-import=ssl \
			--hidden-import=cryptography \
			--hidden-import=yaml \
			--hidden-import=systemd \
			--hidden-import=systemd.journal \
			--clean \
			$(SERVER_SCRIPT); \
	else \
		python3 -m PyInstaller \
			--name $(SERVER_NAME) \
			--onedir \
			--collect-all common \
			--collect-all protocol \
			--collect-all crypto \
			--collect-all traffic \
			--collect-all smtp_message \
			--collect-all config \
			--collect-all logger \
			--collect-all server_protocol \
			--collect-all server_connection \
			--collect-all server_tunnel \
			--collect-all server_server \
			--hidden-import=asyncio \
			--hidden-import=ssl \
			--hidden-import=cryptography \
			--hidden-import=yaml \
			--hidden-import=systemd \
			--hidden-import=systemd.journal \
			--clean \
			$(SERVER_SCRIPT); \
	fi
	@echo "$(GREEN)[完成]$(NC) 服务端已打包到: $(DIST_DIR)/$(SERVER_NAME)/"
	@echo "$(BLUE)[提示]$(NC) 运行: ./$(DIST_DIR)/$(SERVER_NAME)/$(SERVER_NAME) -c /path/to/config.yaml"

# 构建服务端（单文件模式 - 便携版）
build-server-onefile: ## 构建服务端（单文件模式，便携版）
	@echo "$(BLUE)[打包]$(NC) 构建服务端（单文件模式）..."
	@mkdir -p $(DIST_DIR)
	@if [ -d "$(VENV_DIR)" ]; then \
		$(VENV_PYTHON) -m PyInstaller \
			--name $(SERVER_NAME) \
			--onefile \
			--collect-all common \
			--collect-all protocol \
			--collect-all crypto \
			--collect-all traffic \
			--collect-all smtp_message \
			--collect-all config \
			--collect-all logger \
			--collect-all server_protocol \
			--collect-all server_connection \
			--collect-all server_tunnel \
			--collect-all server_server \
			--hidden-import=asyncio \
			--hidden-import=ssl \
			--hidden-import=cryptography \
			--hidden-import=yaml \
			--hidden-import=systemd \
			--hidden-import=systemd.journal \
			--clean \
			$(SERVER_SCRIPT); \
	else \
		python3 -m PyInstaller \
			--name $(SERVER_NAME) \
			--onefile \
			--collect-all common \
			--collect-all protocol \
			--collect-all crypto \
			--collect-all traffic \
			--collect-all smtp_message \
			--collect-all config \
			--collect-all logger \
			--collect-all server_protocol \
			--collect-all server_connection \
			--collect-all server_tunnel \
			--collect-all server_server \
			--hidden-import=asyncio \
			--hidden-import=ssl \
			--hidden-import=cryptography \
			--hidden-import=yaml \
			--hidden-import=systemd \
			--hidden-import=systemd.journal \
			--clean \
			$(SERVER_SCRIPT); \
	fi
	@echo "$(GREEN)[完成]$(NC) 服务端已打包到: $(DIST_DIR)/$(SERVER_NAME)"
	@echo "$(BLUE)[提示]$(NC) 运行: ./$(DIST_DIR)/$(SERVER_NAME) -c /path/to/config.yaml"

# 构建服务端（调试模式 - 带调试信息）
build-server-debug: ## 构建服务端（调试模式）
	@echo "$(BLUE)[打包]$(NC) 构建服务端（调试模式）..."
	@mkdir -p $(DIST_DIR)
	@if [ -d "$(VENV_DIR)" ]; then \
		$(VENV_PYTHON) -m PyInstaller \
			--name $(SERVER_NAME)-debug \
			--onedir \
			--debug all \
			--collect-all common \
			--collect-all protocol \
			--collect-all crypto \
			--collect-all traffic \
			--collect-all smtp_message \
			--collect-all config \
			--collect-all logger \
			--collect-all server_protocol \
			--collect-all server_connection \
			--collect-all server_tunnel \
			--collect-all server_server \
			--hidden-import=asyncio \
			--hidden-import=ssl \
			--hidden-import=cryptography \
			--hidden-import=yaml \
			--hidden-import=systemd \
			--hidden-import=systemd.journal \
			$(SERVER_SCRIPT); \
	else \
		python3 -m PyInstaller \
			--name $(SERVER_NAME)-debug \
			--onedir \
			--debug all \
			--collect-all common \
			--collect-all protocol \
			--collect-all crypto \
			--collect-all traffic \
			--collect-all smtp_message \
			--collect-all config \
			--collect-all logger \
			--collect-all server_protocol \
			--collect-all server_connection \
			--collect-all server_tunnel \
			--collect-all server_server \
			--hidden-import=asyncio \
			--hidden-import=ssl \
			--hidden-import=cryptography \
			--hidden-import=yaml \
			--hidden-import=systemd \
			--hidden-import=systemd.journal \
			$(SERVER_SCRIPT); \
	fi
	@echo "$(GREEN)[完成]$(NC) 调试版服务端已打包到: $(DIST_DIR)/$(SERVER_NAME)-debug/"
	@echo "$(BLUE)[提示]$(NC) 运行: ./$(DIST_DIR)/$(SERVER_NAME)-debug/$(SERVER_NAME)-debug -c /path/to/config.yaml"

# 查看服务端
list-server: ## 查看已打包的服务端
	@echo "$(BLUE)[服务端]$(NC) 已打包的服务端:"
	@ls -lh $(DIST_DIR)/$(SERVER_NAME)* 2>/dev/null || echo "尚无打包的服务端"

# 查看所有已打包的应用
list-all: ## 查看所有已打包的应用
	@echo "$(BLUE)[打包]$(NC) 所有已打包的应用:"
	@ls -lh $(DIST_DIR)/ 2>/dev/null || echo "尚无打包的应用"

# 清理打包文件
clean-dist: ## 清理打包文件
	@echo "$(BLUE)[清理]$(NC) 清理打包文件..."
	@rm -rf $(DIST_DIR) $(BUILD_DIR)
	@rm -f *.spec
	@echo "$(GREEN)[完成]$(NC) 清理完成"

# Windows 构建环境脚本路径
WINDOWS_BUILD_SCRIPT := $(shell [ -f ./setup-windows-build-env.sh ] && echo "./setup-windows-build-env.sh" || echo "")

# Docker 构建脚本路径
DOCKER_SCRIPT := $(shell [ -f ./build-windows-docker.sh ] && echo "./build-windows-docker.sh" || echo "")

# 检查 Wine 环境
check-wine: ## 检查 Wine 环境（使用独立脚本）
	@if [ -z "$(WINE_SCRIPT)" ]; then \
		echo "$(RED)[错误]$(NC) 未找到 install-wine-env.sh 脚本"; \
		exit 1; \
	fi
	@$(WINE_SCRIPT) check

# 安装 Windows Python 到 Wine
install-wine: ## 安装 Windows Python 到 Wine（使用独立脚本）
	@if [ -z "$(WINE_SCRIPT)" ]; then \
		echo "$(RED)[错误]$(NC) 未找到 install-wine-env.sh 脚本"; \
		exit 1; \
	fi
	@$(WINE_SCRIPT) install

# 检查 Windows 构建环境
check-windows-env: ## 检查 Windows 构建环境（使用独立脚本）
	@if [ -z "$(WINDOWS_BUILD_SCRIPT)" ]; then \
		echo "$(RED)[错误]$(NC) 未找到 setup-windows-build-env.sh 脚本"; \
		exit 1; \
	fi
	@$(WINDOWS_BUILD_SCRIPT) check

# 安装 Windows 构建环境
install-windows-env: ## 安装 Windows 构建环境（使用独立脚本）
	@if [ -z "$(WINDOWS_BUILD_SCRIPT)" ]; then \
		echo "$(RED)[错误]$(NC) 未找到 setup-windows-build-env.sh 脚本"; \
		exit 1; \
	fi
	@$(WINDOWS_BUILD_SCRIPT) install

# 构建 Windows 客户端（使用 Docker，推荐）
build-client-windows: ## 构建 Windows 客户端（使用 Docker，推荐）
	@if [ -n "$(DOCKER_SCRIPT)" ]; then \
		@echo "$(BLUE)[提示]$(NC) 使用 Docker 构建 Windows 客户端（推荐）"; \
		$(DOCKER_SCRIPT) build; \
	else \
		@echo "$(RED)[错误]$(NC) 未找到 build-windows-docker.sh 脚本"; \
		exit 1; \
	fi

# 构建 Windows 客户端（目录模式，使用 Docker）
build-client-windows-dir: ## 构建 Windows 客户端（目录模式，使用 Docker）
	@if [ -n "$(DOCKER_SCRIPT)" ]; then \
		$(DOCKER_SCRIPT) dir; \
	else \
		@echo "$(RED)[错误]$(NC) 未找到 build-windows-docker.sh 脚本"; \
		exit 1; \
	fi

# 清理 Docker 镜像
clean-docker: ## 清理 Docker 镜像
	@if [ -n "$(DOCKER_SCRIPT)" ]; then \
		$(DOCKER_SCRIPT) clean; \
	else \
		@echo "$(RED)[错误]$(NC) 未找到 build-windows-docker.sh 脚本"; \
		exit 1; \
	fi

# 查看客户端
list-client: ## 查看已打包的客户端
	@echo "$(BLUE)[客户端]$(NC) 已打包的客户端:"
	@ls -lh $(DIST_DIR)/ 2>/dev/null || echo "尚无打包的客户端"

# 信息
info: ## 显示项目信息
	@echo "$(BLUE)========================================$(NC)"
	@echo "$(BLUE)  SMTP 隧道代理 - 项目信息$(NC)"
	@echo "$(BLUE)========================================$(NC)"
	@echo ""
	@echo "$(GREEN)镜像名称:$(NC) $(IMAGE_NAME)"
	@echo "$(GREEN)镜像标签:$(NC) $(IMAGE_TAG)"
	@echo "$(GREEN)版本:$(NC) $(VERSION)"
	@echo "$(GREEN)容器名称:$(NC) $(CONTAINER_NAME)"
	@echo ""
	@echo "$(GREEN)端口:$(NC) 587 (SMTP)"
	@echo ""
	@echo "$(GREEN)配置目录:$(NC) config/"
	@echo "$(GREEN)数据目录:$(NC) data/"
	@echo "$(GREEN)日志目录:$(NC) logs/"
	@echo ""
	@echo "$(GREEN)客户端打包:$(NC) make build-client"
	@echo "$(GREEN)Windows 打包:$(NC) ./setup-windows-build-env.sh build"
	@echo "$(GREEN)更多命令:$(NC) make help"
