@echo off
chcp 65001 >nul 2>&1
title SMTP 隧道代理 - 客户端安装程序

REM 颜色定义
set "RED=[91m"
set "GREEN=[92m"
set "YELLOW=[93m"
set "BLUE=[94m"
set "CYAN=[96m"
set "NC=[0m"

REM GitHub 原始文件 URL 基础地址
set "GITHUB_RAW=https://raw.githubusercontent.com/purpose168/smtp-tunnel-proxy/main"

REM 安装目录
set "INSTALL_DIR=C:\Program Files\SMTP-Tunnel"
set "CONFIG_DIR=C:\ProgramData\SMTP-Tunnel"
set "VENV_DIR=%INSTALL_DIR%\venv"

REM 日志文件
set "LOG_FILE=%CONFIG_DIR%\install-client.log"

REM 需要下载的客户端 Python 文件
set "CLIENT_FILES=client.py socks5_server.py"

REM 从 common.py 拆分出的模块
set "COMMON_MODULES=protocol\__init__.py protocol\core.py protocol\client.py protocol\server.py tunnel\__init__.py tunnel\crypto.py tunnel\base.py tunnel\client.py traffic.py smtp_message.py config.py logger.py connection.py"

REM 所有 Python 文件
set "PYTHON_FILES=%CLIENT_FILES% %COMMON_MODULES%"

REM ============================================================================
REM 日志记录函数
REM ============================================================================

:log_info
setlocal
set "message=%~1"
echo %GREEN%[INFO]%NC% %message%
echo [%DATE% %TIME%] [INFO] %message%>> "%LOG_FILE%"
endlocal

:log_warn
setlocal
set "message=%~1"
echo %YELLOW%[WARN]%NC% %message%
echo [%DATE% %TIME%] [WARN] %message%>> "%LOG_FILE%"
endlocal

:log_error
setlocal
set "message=%~1"
echo %RED%[ERROR]%NC% %message%
echo [%DATE% %TIME%] [ERROR] %message%>> "%LOG_FILE%"
endlocal

:log_step
setlocal
set "message=%~1"
echo %BLUE%[STEP]%NC% %message%
echo [%DATE% %TIME%] [STEP] %message%>> "%LOG_FILE%"
endlocal

REM ============================================================================
REM 打印函数
REM ============================================================================

:print_info
echo %GREEN%[INFO]%NC% %~1
goto :eof

:print_warn
echo %YELLOW%[WARN]%NC% %~1
goto :eof

:print_error
echo %RED%[ERROR]%NC% %~1
goto :eof

:print_step
echo %BLUE%[STEP]%NC% %~1
goto :eof

:print_ask
echo %CYAN%[?]%NC% %~1
goto :eof

REM ============================================================================
REM 检查是否以管理员权限运行
REM ============================================================================

:check_admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    call :log_error "请以管理员权限运行（右键点击以管理员身份运行）"
    echo.
    echo 使用方法: 右键点击 install-client.bat，选择"以管理员身份运行"
    echo.
    pause
    exit /b 1
)

REM ============================================================================
REM 检测 Python 是否安装
REM ============================================================================

:detect_python
call :log_step "检测 Python 安装..."

where python >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python"
    goto :python_found
)

where python3 >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python3"
    goto :python_found
)

call :log_error "未找到 Python！"
echo.
echo 请从以下地址安装 Python 3.8+:
echo   https://www.python.org/downloads/
echo.
echo 安装时请确保勾选"Add Python to PATH"选项。
echo.
pause
exit /b 1

:python_found
for /f "tokens=2 delims==" %%a in ('%PYTHON_CMD% --version') do (
    set "PYTHON_VERSION=%%a"
    goto :python_version_found
)

call :log_error "无法获取 Python 版本"
echo.
echo 请确保 Python 已正确安装。
echo.
pause
exit /b 1

:python_version_found
call :log_info "Python 版本: %PYTHON_VERSION%"

REM 验证 Python 版本是否满足要求
for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VERSION%") do (
    set "PYTHON_MAJOR=%%a"
    set "PYTHON_MINOR=%%b"
)

if %PYTHON_MAJOR% lss 3 (
    call :log_error "Python 3.8+ 是必需的，当前版本: %PYTHON_VERSION%"
    echo.
    pause
    exit /b 1
)

if %PYTHON_MAJOR% equ 3 (
    if %PYTHON_MINOR% lss 8 (
        call :log_error "Python 3.8+ 是必需的，当前版本: %PYTHON_VERSION%"
        echo.
        pause
        exit /b 1
    )
)

call :log_info "Python 版本检查通过: %PYTHON_VERSION%"

REM ============================================================================
REM 创建目录
REM ============================================================================

:create_directories
call :log_step "创建目录..."

if not exist "%INSTALL_DIR%" (
    mkdir "%INSTALL_DIR%"
    call :log_info "已创建: %INSTALL_DIR%"
) else (
    call :log_warn "目录已存在: %INSTALL_DIR%"
)

if not exist "%CONFIG_DIR%" (
    mkdir "%CONFIG_DIR%"
    call :log_info "已创建: %CONFIG_DIR%"
) else (
    call :log_warn "目录已存在: %CONFIG_DIR%"
)

REM 创建日志文件
if not exist "%LOG_FILE%" (
    type nul > "%LOG_FILE%"
    call :log_info "已创建: %LOG_FILE%"
)

call :log_info "目录创建完成"

REM ============================================================================
REM 从 GitHub 下载文件
REM ============================================================================

:download_file
set "filename=%~1"
set "url=%GITHUB_RAW%/%filename%"
set "destination=%INSTALL_DIR%\%filename%"

call :log_step "正在下载: %filename%"
call :log_info "URL: %url%"
call :log_info "目标: %destination%"

REM 检查目标文件是否存在
if exist "%destination%" (
    call :log_warn "目标文件已存在，正在删除: %destination%"
    del /f /q "%destination%"
)

REM 创建目标目录（如果不存在）
set "dest_dir=%destination:\.."
if not exist "%dest_dir%" (
    mkdir "%dest_dir%"
    call :log_info "创建目标目录: %dest_dir%"
)

REM 尝试下载文件
set "retry_count=0"
set "max_retries=3"

:download_retry
if %retry_count% lss %max_retries% (
    set /a "retry_count=%retry_count% + 1"
    
    REM 尝试使用 PowerShell 下载
    powershell -Command "Invoke-WebRequest -Uri '%url%' -OutFile '%destination%' -UseBasicParsing -TimeoutSec 30" 2>nul
    if %errorlevel% equ 0 (
        call :log_info "  已下载: %filename%"
        goto :download_success
    ) else (
        call :log_warn "  下载失败，重试 %retry_count%/%max_retries%..."
        timeout /t 2 >nul
        goto :download_retry
    )
)

call :log_error " 下载失败: %filename%（已重试 %max_retries% 次）"
call :log_error "  URL: %url%"
call :log_error "  请检查网络连接或文件是否存在"
exit /b 1

:download_success
exit /b 0

REM ============================================================================
REM 下载并安装文件
REM ============================================================================

:install_files
call :log_step "从 GitHub 下载文件..."

REM 下载 Python 文件到安装目录
for %%f in (%PYTHON_FILES%) do (
    call :download_file "%%f"
    if %errorlevel% neq 0 (
        call :log_error "下载必需文件失败: %%f"
        exit /b 1
    )
)

REM 下载 requirements.txt
call :download_file "requirements.txt"
if %errorlevel% neq 0 (
    call :log_error "下载 requirements.txt 失败"
    exit /b 1
)

call :log_info "文件下载完成"

REM ============================================================================
REM 检查 Python 虚拟环境
REM ============================================================================

:check_venv
call :log_step "检查 Python 虚拟环境..."

if not exist "%VENV_DIR%" (
    call :log_info "虚拟环境不存在"
    goto :venv_not_exists
)

call :log_info "虚拟环境已存在: %VENV_DIR%"
goto :venv_exists

:venv_not_exists
call :log_info "当前未在虚拟环境中"
goto :eof

:venv_exists
call :log_info "当前已在虚拟环境中"
goto :eof

REM ============================================================================
REM 创建 Python 虚拟环境
REM ============================================================================

:create_venv
call :log_step "创建 Python 虚拟环境..."

REM 检查虚拟环境是否已存在
if exist "%VENV_DIR%" (
    call :log_warn "虚拟环境已存在: %VENV_DIR%"
    
    REM 询问是否重新创建
    call :print_ask "是否重新创建虚拟环境？[Y/N]: "
    set /p "RECREATE_VENV="
    set /p
    if not "%RECREATE_VENV%"=="" (
        goto :create_venv_confirm
    )
    
    call :log_info "保留现有虚拟环境"
    goto :eof

:create_venv_confirm
if /i "%RECREATE_VENV:Y"=="/i" goto :delete_venv
if /i "%RECREATE_VENV:Y"=="/y" goto :delete_venv

call :log_info "保留现有虚拟环境"
goto :eof

:delete_venv
call :log_info "正在删除现有虚拟环境..."
rmdir /s /q "%VENV_DIR%"

:create_venv_execute
call :log_info "正在创建虚拟环境: %VENV_DIR%"

%PYTHON_CMD% -m venv "%VENV_DIR%" >nul 2>&1
if %errorlevel% equ 0 (
    call :log_info "虚拟环境创建成功"
    goto :venv_created
) else (
    call :log_error "虚拟环境创建失败"
    exit /b 1
)

:venv_created
exit /b 0

REM ============================================================================
REM 激活虚拟环境
REM ============================================================================

:activate_venv
call :log_step "激活虚拟环境..."

if not exist "%VENV_DIR%\Scripts\activate.bat" (
    call :log_error "虚拟环境激活脚本不存在: %VENV_DIR%\Scripts\activate.bat"
    exit /b 1
)

call :log_info "激活虚拟环境: %VENV_DIR%"
call "%VENV_DIR%\Scripts\activate.bat"
call :log_info "虚拟环境已激活"
exit /b 0

REM ============================================================================
REM 安装 Python 包
REM ============================================================================

:install_python_packages
call :log_step "在虚拟环境中安装 Python 包..."

REM 检查虚拟环境是否存在
if not exist "%VENV_DIR%" (
    call :log_error "虚拟环境不存在，请先创建虚拟环境"
    exit /b 1
)

REM 激活虚拟环境
call "%VENV_DIR%\Scripts\activate.bat" >nul 2>&1

REM 升级 pip
call :log_info "升级 pip 到最新版本..."
%PYTHON_CMD% -m pip install --upgrade pip >nul 2>&1

REM 安装 Python 包
call :log_info "安装依赖包..."
%PYTHON_CMD% -m pip install -r "%INSTALL_DIR%\requirements.txt" >nul 2>&1
if %errorlevel% equ 0 (
    call :log_info "Python 包安装成功"
    
    REM 显示已安装的包
    call :log_info "已安装的包:"
    %PYTHON_CMD% -m pip list --format=columns 2>nul | findstr /i "cryptography pyyaml" || type nul
    goto :install_success
) else (
    call :log_error "Python 包安装失败"
    exit /b 1
)

:install_success
exit /b 0

REM ============================================================================
REM 交互式配置
REM ============================================================================

:interactive_setup
cls
echo.
echo %GREEN%========================================%NC%
echo %GREEN%  交互式设置%NC%
echo %GREEN%========================================%NC%
echo.

REM 询问是否创建虚拟环境
call :print_ask "是否创建 Python 虚拟环境？[Y/N]: "
set /p "CREATE_VENV="
set /p
if not "%CREATE_VENV%"=="" (
    goto :create_venv_confirm
)

call :log_info "跳过虚拟环境创建"
goto :download_client_files

:create_venv_confirm
if /i "%CREATE_VENV:Y"=="/i" goto :delete_venv
if /i "%CREATE_VENV:Y"=="/y" goto :delete_venv

call :log_info "保留现有虚拟环境"
goto :download_client_files

:delete_venv
call :log_info "正在删除现有虚拟环境..."
rmdir /s /q "%VENV_DIR%"

:create_venv_execute
call :log_info "正在创建虚拟环境: %VENV_DIR%"

%PYTHON_CMD% -m venv "%VENV_DIR%" >nul 2>&1
if %errorlevel% equ 0 (
    call :log_info "虚拟环境创建成功"
    goto :venv_created
) else (
    call :log_error "虚拟环境创建失败"
    exit /b 1
)

:venv_created
REM 激活虚拟环境
call "%VENV_DIR%\Scripts\activate.bat" >nul 2>&1

REM 安装 Python 包
call :log_info "安装依赖包..."
%PYTHON_CMD% -m pip install -r "%INSTALL_DIR%\requirements.txt" >nul 2>&1
if %errorlevel% equ 0 (
    call :log_info "Python 包安装成功"
    goto :install_success
) else (
    call :log_error "Python 包安装失败"
    exit /b 1
)

:install_success
goto :interactive_config

REM ============================================================================
REM 下载客户端文件
REM ============================================================================

:download_client_files
call :log_step "下载客户端文件..."

REM 询问是否下载客户端文件
call :print_ask "是否下载客户端文件？[Y/N]: "
set /p "DOWNLOAD_CLIENT="
set /p
if not "%DOWNLOAD_CLIENT%"=="" (
    goto :download_client_confirm
)

call :log_info "跳过客户端文件下载"
goto :create_shortcut

:download_client_confirm
if /i "%DOWNLOAD_CLIENT:Y"=="/i" goto :download_files
if /i "%DOWNLOAD_CLIENT:Y"=="/y" goto :download_files

call :log_info "跳过客户端文件下载"
goto :create_shortcut

:download_files
call :install_files

REM ============================================================================
REM 交互式配置
REM ============================================================================

:interactive_config
call :log_step "配置客户端..."

REM 询问服务器地址
call :print_ask "请输入服务器地址（域名或IP地址）:"
set /p "SERVER_ADDR="
set /p
if "%SERVER_ADDR%"=="" (
    call :log_error "服务器地址是必需的！"
    exit /b 1
)

call :log_info "使用服务器地址: %SERVER_ADDR%"

REM 询问服务器端口
call :print_ask "请输入服务器端口（默认: 587）:"
set /p "SERVER_PORT=587"
set /p
if not "%SERVER_PORT%"=="" (
    set "SERVER_PORT=587"
)

call :log_info "使用服务器端口: %SERVER_PORT%"

REM 创建配置文件
call :log_step "创建配置文件..."

if not exist "%CONFIG_DIR%" (
    mkdir "%CONFIG_DIR%"
)

set "CONFIG_FILE=%CONFIG_DIR%\config.yaml"

(
    echo # SMTP 隧道代理客户端配置
    echo # 由 install-client.bat 生成
    echo.
    echo client:
    echo   server_host: "%SERVER_ADDR%"
    echo   server_port: %SERVER_PORT%
    echo   socks_port: 1080
    echo   socks_host: "127.0.0.1"
    echo   ca_cert: "ca.crt"
) > "%CONFIG_FILE%"

call :log_info "已创建: %CONFIG_FILE%"

REM ============================================================================
REM 创建快捷方式
REM ============================================================================

:create_shortcut
call :log_step "创建快捷方式..."

REM 创建桌面快捷方式
set "DESKTOP_SHORTCUT=%USERPROFILE%\Desktop\SMTP Tunnel Client.lnk"
set "TARGET=%INSTALL_DIR%\client.py"
set "WORKING_DIR=%INSTALL_DIR%"

if exist "%DESKTOP_SHORTCUT%" (
    del "%DESKTOP_SHORTCUT%"
)

powershell -Command "$s = (New-Object -ComObjectObject).CreateShortcut('%DESKTOP_SHORTCUT%', '%TARGET%', '%WORKING_DIR%', 'SMTP Tunnel Client')" 2>nul

if exist "%DESKTOP_SHORTCUT%" (
    call :log_info "已创建桌面快捷方式"
) else (
    call :log_warn "桌面快捷方式创建失败"
)

REM 创建开始脚本
set "START_SCRIPT=%INSTALL_DIR%\start-client.bat"

(
    echo @echo off
    echo chcp 65001 ^>nul 2^>^&1
    echo title SMTP 隧道 - 客户端
    echo.
    echo REM 激活虚拟环境
    echo call "%VENV_DIR%\Scripts\activate.bat"
    echo.
    echo REM 启动客户端
    echo cd /d "%INSTALL_DIR%"
    echo python client.py
    echo.
    echo pause
) > "%START_SCRIPT%"

call :log_info "已创建: %START_SCRIPT%"

REM ============================================================================
REM 打印最终摘要
REM ============================================================================

:print_summary
cls
echo.
echo %GREEN%========================================%NC%
echo %GREEN%  安装完成！%NC%
echo %GREEN%========================================%NC%
echo.
echo 您的 SMTP 隧道代理客户端已安装！
echo.
echo %BLUE%快捷方式:%NC%
echo   桌面快捷方式: %DESKTOP_SHORTCUT%
echo   开始脚本: %START_SCRIPT%
echo.
echo %BLUE%配置文件:%NC%
echo   %CONFIG_FILE%
echo.
echo %BLUE%虚拟环境:%NC%
echo   %VENV_DIR%
echo.
echo %BLUE%下一步:%NC%
echo   1. 编辑配置文件: %CONFIG_FILE%
echo   2. 运行开始脚本: %START_SCRIPT%
echo   3. 或者手动运行:
echo      cd /d "%INSTALL_DIR%"
echo      call "%VENV_DIR%\Scripts\activate.bat"
echo      python client.py
echo.
echo %BLUE%卸载:%NC%
echo   运行: %INSTALL_DIR%\uninstall-client.bat
echo.
echo %CYAN%提示:%NC%
echo   如果您使用虚拟环境，请先激活虚拟环境
echo   如果遇到问题，请查看日志文件: %LOG_FILE%
echo.
echo %YELLOW%注意事项:%NC%
echo   1. 确保服务器地址和端口正确
echo   2. 首次运行时会创建虚拟环境
echo   3. 如果虚拟环境已存在，可以选择重新创建
echo   4. 配置文件位于: %CONFIG_DIR%
echo.

REM ============================================================================
REM 主安装流程
REM ============================================================================

:main
cls
echo.
echo %GREEN%========================================%NC%
echo %GREEN%  SMTP 隧道代理客户端安装程序%NC%
echo %GREEN%  版本 1.3.0%NC%
echo %GREEN%========================================%NC%
echo.

call :check_admin
call :detect_python
call :create_directories
call :download_file "requirements.txt"
call :interactive_setup
call :create_shortcut
call :print_summary

REM ============================================================================
REM 结束
REM ============================================================================

:eof
pause
