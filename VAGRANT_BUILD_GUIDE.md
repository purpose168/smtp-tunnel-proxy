# Vagrant Windows 构建指南

使用 Vagrant 在 Ubuntu 系统上构建 Windows 客户端。

## 📋 目录

- [简介](#简介)
- [前提条件](#前提条件)
- [安装步骤](#安装步骤)
- [使用方法](#使用方法)
- [常见问题](#常见问题)
- [故障排除](#故障排除)

## 简介

本指南介绍如何使用 Vagrant 在 Ubuntu 宿主机上创建 Windows 虚拟机，然后在 Windows 虚拟机中使用 PyInstaller 构建 Windows 客户端。

### 为什么使用 Vagrant？

- ✅ **完整的 Windows 环境**：可以使用任何 Windows 软件
- ✅ **图形界面支持**：可以使用 Windows GUI
- ✅ **隔离的构建环境**：不影响宿主机
- ✅ **可复现的构建**：确保构建环境一致
- ✅ **跨平台支持**：在 Linux 上构建 Windows 程序

### 与其他方法对比

| 方法 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| **Vagrant** | 完整 Windows 环境、GUI 支持 | 资源占用高、启动慢 | 需要 Windows GUI 或复杂依赖 |
| **Docker** | 轻量级、启动快 | 无 GUI、Windows Server Core | 命令行程序、资源有限 |
| **直接在 Windows 上** | 最简单直接 | 需要 Windows 系统 | 有 Windows 系统、简单构建 |

## 前提条件

### 系统要求

- **操作系统**：Ubuntu 18.04+ 或其他 Linux 发行版
- **内存**：建议 8GB 或更多（虚拟机需要 4GB）
- **磁盘空间**：至少 20GB（Windows 镜像约 5GB）
- **CPU**：建议 4 核或更多（虚拟机使用 2 核）

### 软件要求

#### 1. 安装 VirtualBox

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install virtualbox virtualbox-ext-pack

# Fedora
sudo dnf install VirtualBox kernel-devel

# Arch
sudo pacman -S virtualbox virtualbox-host-modules-arch
```

#### 2. 安装 Vagrant

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install vagrant

# Fedora
sudo dnf install vagrant

# Arch
sudo pacman -S vagrant
```

#### 3. 验证安装

```bash
# 检查 VirtualBox
VBoxManage --version

# 检查 Vagrant
vagrant --version
```

## 安装步骤

### 步骤 1：克隆项目

```bash
cd /path/to/smtp-tunnel-proxy
```

### 步骤 2：设置 Vagrant 环境

```bash
# 检查环境
./build-windows-vagrant.sh setup
```

输出示例：
```
[步骤] 设置 Vagrant 环境...
[信息] Vagrantfile 已就绪
[信息] 下一步: 运行 ./build-windows-vagrant.sh start 启动虚拟机
```

### 步骤 3：启动 Windows 虚拟机

```bash
# 启动虚拟机
./build-windows-vagrant.sh start
```

**首次启动需要：**
- 下载 Windows 10 镜像（约 5GB）
- 安装 VirtualBox 扩展包
- 配置虚拟机设置

预计时间：10-30 分钟（取决于网络速度）

### 步骤 4：构建 Windows 客户端

```bash
# 构建客户端
./build-windows-vagrant.sh build
```

输出示例：
```
[步骤] 构建 Windows 客户端...
[步骤] 在 Windows 虚拟机中运行 PyInstaller...
[信息] Windows 客户端构建成功!

输出文件:
-rwxr-xr-x 1 pps pps 25M Jan 11 14:30 dist/smtp-tunnel-client-windows.exe

[提示] 可直接拷贝到 Windows 系统运行
```

### 步骤 5：停止虚拟机（可选）

```bash
# 停止虚拟机以节省资源
./build-windows-vagrant.sh stop
```

## 使用方法

### 基本命令

```bash
# 显示帮助
./build-windows-vagrant.sh help

# 设置环境
./build-windows-vagrant.sh setup

# 启动虚拟机
./build-windows-vagrant.sh start

# 构建客户端
./build-windows-vagrant.sh build

# 停止虚拟机
./build-windows-vagrant.sh stop

# 销毁虚拟机
./build-windows-vagrant.sh destroy

# 查看状态
./build-windows-vagrant.sh status
```

### 直接使用 Vagrant 命令

```bash
# 启动虚拟机
vagrant up

# 连接到虚拟机（需要配置 SSH）
vagrant ssh

# 运行 Provisioning
vagrant provision

# 停止虚拟机
vagrant halt

# 重启虚拟机
vagrant reload

# 销毁虚拟机
vagrant destroy

# 查看状态
vagrant status
```

### 访问 Windows 虚拟机

由于 Windows 虚拟机默认不启用 SSH，可以使用以下方法访问：

#### 方法 1：使用 VirtualBox GUI

```bash
# 打开 VirtualBox
virtualbox &

# 选择虚拟机
# smtp-tunnel-windows-builder

# 点击 '显示' 按钮
```

#### 方法 2：启用 SSH（高级）

在 Windows 虚拟机中：

```powershell
# 安装 OpenSSH Server
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0

# 启动 SSH 服务
Start-Service sshd

# 设置开机自启
Set-Service -Name sshd -StartupType 'Automatic'

# 配置防火墙
New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
```

然后可以使用 `vagrant ssh` 连接。

## 常见问题

### Q1: 首次启动需要多长时间？

**A:** 首次启动需要下载 Windows 10 镜像（约 5GB），预计 10-30 分钟，取决于网络速度。后续启动会快很多（约 1-2 分钟）。

### Q2: 虚拟机需要多少资源？

**A:** 虚拟机配置：
- 内存：4GB
- CPU：2 核
- 磁盘：动态分配（初始约 10GB）

建议宿主机至少有 8GB 内存和 4 核 CPU。

### Q3: 可以修改虚拟机配置吗？

**A:** 可以！编辑 `Vagrantfile` 中的配置：

```ruby
config.vm.provider "virtualbox" do |vb|
  vb.memory = "4096"  # 修改内存
  vb.cpus = 2          # 修改 CPU 核心数
  vb.gui = true         # 启用/禁用 GUI
end
```

修改后运行 `vagrant reload` 应用更改。

### Q4: 如何在虚拟机中安装额外的软件？

**A:** 使用 VirtualBox GUI 访问虚拟机，然后：

```powershell
# 使用 PowerShell
# 下载并安装软件
```

或者编辑 `Vagrantfile`，在 `config.vm.provision` 中添加安装命令。

### Q5: 生成的 Windows 可执行文件在哪里？

**A:** 生成的文件在项目目录的 `dist/` 文件夹中：

```
dist/smtp-tunnel-client-windows.exe
```

这个文件可以直接拷贝到 Windows 系统运行。

## 故障排除

### 问题 1：Vagrant 启动失败

**错误信息：**
```
Vagrant failed to initialize at a very early stage:
```

**解决方案：**

```bash
# 检查 VirtualBox 是否运行
sudo systemctl status vboxdrv

# 如果未运行，启动服务
sudo systemctl start vboxdrv

# 或者重新加载内核模块
sudo modprobe vboxdrv
```

### 问题 2：虚拟机启动后无法访问

**错误信息：**
```
default: SSH auth method: private key
default: SSH auth method: password
```

**解决方案：**

Windows 虚拟机默认不启用 SSH，使用 VirtualBox GUI 访问：

```bash
# 打开 VirtualBox GUI
virtualbox &

# 选择虚拟机并点击 '显示'
```

### 问题 3：构建失败

**错误信息：**
```
[错误] PyInstaller 环境检查失败
```

**解决方案：**

```bash
# 重新运行 Provisioning
vagrant provision

# 或手动在虚拟机中安装
# 使用 VirtualBox GUI 访问虚拟机
pip install pyinstaller cryptography pyyaml
```

### 问题 4：内存不足

**错误信息：**
```
[警告] 系统内存不足 8GB，建议至少 8GB
```

**解决方案：**

1. 关闭其他应用程序
2. 减少 Vagrantfile 中的虚拟机内存：
   ```ruby
   vb.memory = "2048"  # 改为 2GB
   ```
3. 或增加系统内存

### 问题 5：磁盘空间不足

**错误信息：**
```
[错误] 磁盘空间不足
```

**解决方案：**

```bash
# 检查磁盘空间
df -h

# 清理不必要的文件
# 或增加虚拟机磁盘大小（编辑 Vagrantfile）
```

### 问题 6：网络连接问题

**错误信息：**
```
[错误] 无法下载 Windows 镜像
```

**解决方案：**

1. 检查网络连接
2. 使用镜像源（如果在中国）：
   ```bash
   # 编辑 Vagrantfile，使用国内镜像
   config.vm.box = "https://mirrors.ustc.edu.cn/vagrant-boxes/gusztavvargadr/windows10"
   ```
3. 手动下载镜像并添加：
   ```bash
   vagrant box add windows10 /path/to/windows10.box
   ```

## 高级用法

### 自定义 Provisioning

编辑 `Vagrantfile`，添加自定义脚本：

```ruby
config.vm.provision "shell", inline: <<-SHELL
  # 安装额外的软件
  choco install git

  # 配置环境变量
  [System.Environment]::SetEnvironmentVariable('PATH', $env:PATH + ';C:\Program Files\Git\bin', 'Machine')
SHELL
```

### 多个虚拟机

创建多个虚拟机用于不同的构建环境：

```ruby
# Windows 10
config.vm.define "win10" do |win10|
  win10.vm.box = "gusztavvargadr/windows10"
  win10.vm.provider "virtualbox" do |vb|
    vb.name = "smtp-tunnel-win10"
  end
end

# Windows 11
config.vm.define "win11" do |win11|
  win11.vm.box = "gusztavvargadr/windows11"
  win11.vm.provider "virtualbox" do |vb|
    vb.name = "smtp-tunnel-win11"
  end
end
```

### 使用快照

在 VirtualBox 中创建快照，方便回滚：

```bash
# 在 VirtualBox GUI 中
# 机器 -> 快照 -> 拍摄快照
```

## 性能优化

### 减少启动时间

```ruby
# 禁用 GUI（无头模式）
vb.gui = false

# 启用 3D 加速
vb.customize ["modifyvm", :id, "--accelerate3d", "on"]

# 增加视频内存
vb.customize ["modifyvm", :id, "--vram", "256"]
```

### 减少资源占用

```ruby
# 减少内存
vb.memory = "2048"

# 减少 CPU
vb.cpus = 1

# 禁用音频
vb.customize ["modifyvm", :id, "--audio", "none"]

# 禁用 USB
vb.customize ["modifyvm", :id, "--usb", "off"]
```

## 清理

### 清理虚拟机

```bash
# 停止虚拟机
./build-windows-vagrant.sh stop

# 销毁虚拟机
./build-windows-vagrant.sh destroy
```

### 清理 Vagrant 缓存

```bash
# 清理下载的 boxes
vagrant box list
vagrant box remove <box-name>

# 清理临时文件
rm -rf .vagrant/
```

## 总结

使用 Vagrant 在 Ubuntu 系统上构建 Windows 客户端的优势：

- ✅ 完整的 Windows 环境
- ✅ 图形界面支持
- ✅ 隔离的构建环境
- ✅ 可复现的构建
- ✅ 跨平台支持

适用场景：

- 需要完整的 Windows 环境
- 需要图形界面进行调试
- 项目依赖 Windows 特定的 GUI 库
- 需要安装复杂的 Windows 软件

## 参考资料

- [Vagrant 官方文档](https://www.vagrantup.com/docs)
- [VirtualBox 官方文档](https://www.virtualbox.org/wiki/Documentation)
- [PyInstaller 官方文档](https://pyinstaller.org/en/stable/)
- [Windows Vagrant Boxes](https://app.vagrantup.com/boxes/search)

## 许可证

本脚本遵循项目的许可证。
