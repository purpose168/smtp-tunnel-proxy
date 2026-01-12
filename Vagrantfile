# -*- mode: ruby -*-
# vi: set ft=ruby :
#
# SMTP 隧道代理 - Vagrant 配置文件
#
# 用于在 Ubuntu 宿主机上创建 Windows 虚拟机
# 在 Windows 虚拟机中使用 PyInstaller 构建 Windows 客户端
#
# 使用方法:
#   vagrant up              # 启动 Windows 虚拟机
#   vagrant ssh             # 连接到虚拟机（需要配置 SSH）
#   vagrant halt            # 停止虚拟机
#   vagrant destroy         # 销毁虚拟机
#   vagrant reload          # 重启虚拟机
#
# 版本: 1.0.0

Vagrant.configure("2") do |config|
  # 使用 Windows 10 虚拟机镜像
  # Stefan Scherer 维护的 Windows 10 镜像
  # GitHub: https://github.com/StefanScherer/packer-boxes
  # https://github.com/StefanScherer/packer-windows
  # https://portal.cloud.hashicorp.com/vagrant/discover?query=windows
  # 可用版本: 2017.12.14, 2018.01.22, ..., 2021.12.09
  config.vm.box = "stefanscherer/windows_10"
  config.vm.box_version = "2021.12.09"  # 使用兼容 VirtualBox 7.0 的稳定版本

  # 配置虚拟机名称
  config.vm.hostname = "windows-builder"

  # 配置虚拟机提供商（VirtualBox）
  config.vm.provider "virtualbox" do |vb|
    # 虚拟机名称
    vb.name = "smtp-tunnel-windows-builder"

    # 分配内存（建议 4GB 或更多）
    vb.memory = "4096"

    # 分配 CPU 核心数
    vb.cpus = 2

    # 启用 GUI（可选，设置为 false 可以无头模式运行）
    vb.gui = true

    # 配置虚拟机显示
    vb.customize ["modifyvm", :id, "--vram", "128"]

    # 启用 3D 加速
    vb.customize ["modifyvm", :id, "--accelerate3d", "on"]

    # 禁用音频
    vb.customize ["modifyvm", :id, "--audio", "none"]

    # 配置共享文件夹
    vb.customize ["sharedfolder", "add", :id, "--name", "vagrant", "--hostpath", File.expand_path(".."), "--automount"]
  end

  # 同步项目目录到虚拟机
  # 宿主机目录 -> 虚拟机目录
  config.vm.synced_folder ".", "/vagrant",
    type: "virtualbox",
    mount_options: ["dmode=0777", "fmode=0777"]

  # 配置网络
  config.vm.network "private_network", type: "dhcp"

  # 配置端口转发（可选）
  # config.vm.network "forwarded_port", guest: 80, host: 8080

  # 禁用默认的共享文件夹
  config.vm.synced_folder ".", "/vagrant", disabled: true

  # 启用自定义共享文件夹
  config.vm.synced_folder ".", "/project",
    type: "virtualbox",
    mount_options: ["dmode=0777", "fmode=0777"]

  # 配置 Provisioning（自动化脚本）
  # 注意：Windows 虚拟机需要使用 PowerShell 脚本
  config.vm.provision "shell", inline: <<-SHELL
    # 更新 PowerShell 执行策略
    Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine -Force

    # 检查 Python 是否已安装
    $pythonInstalled = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonInstalled) {
      Write-Host "Python 未安装，请手动安装 Python 3.x"
      Write-Host "下载地址: https://www.python.org/downloads/"
      Write-Host "安装后请运行: vagrant provision"
      exit 1
    }

    # 检查 Python 版本
    $pythonVersion = python --version 2>&1
    Write-Host "Python 版本: $pythonVersion"

    # 安装 PyInstaller
    Write-Host "安装 PyInstaller..."
    pip install pyinstaller cryptography pyyaml

    # 验证安装
    $pyinstallerInstalled = Get-Command pyinstaller -ErrorAction SilentlyContinue
    if ($pyinstallerInstalled) {
      Write-Host "PyInstaller 安装成功!"
      pyinstaller --version
    } else {
      Write-Host "PyInstaller 安装失败"
      exit 1
    }

    Write-Host "Provisioning 完成!"
  SHELL

  # 配置 Provisioning（构建脚本）
  config.vm.provision "build", type: "shell", run: "never" do |s|
    s.inline = <<-SHELL
      # 切换到项目目录
      cd /project

      # 构建 Windows 客户端（单文件模式）
      Write-Host "开始构建 Windows 客户端..."

      pyinstaller `
        --name smtp-tunnel-client-windows `
        --onefile `
        --windowed `
        --collect-all common `
        --collect-all client_protocol `
        --collect-all client_socks5 `
        --collect-all client_tunnel `
        --collect-all client_server `
        --hidden-import=asyncio `
        --hidden-import=ssl `
        --hidden-import=cryptography `
        --hidden-import=yaml `
        --hidden-import=_cffi_backend `
        --exclude-module=tkinter `
        --exclude-module=test `
        --exclude-module=unittest `
        --exclude-module=pydoc `
        --clean `
        client.py

      # 检查构建结果
      if (Test-Path "dist/smtp-tunnel-client-windows.exe") {
        Write-Host "构建成功!"
        Get-Item dist/smtp-tunnel-client-windows.exe | Select-Object Name, Length
      } else {
        Write-Host "构建失败!"
        exit 1
      }
    SHELL
  end
end
