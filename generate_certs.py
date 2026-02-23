#!/usr/bin/env python3
"""
为 SMTP 隧道生成自签名 TLS 证书
创建模拟真实邮件服务器的服务器证书

版本: 1.3.0

功能说明:
- 生成证书颁发机构 (CA) 证书和私钥
- 生成由 CA 签名的服务器证书和私钥
- 支持自定义主机名、密钥大小和有效期
- 自动设置安全的文件权限
"""

import os
import sys
import argparse
import re
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend


def generate_private_key(key_size: int = 2048) -> rsa.RSAPrivateKey:
    """
    生成 RSA 私钥
    
    参数:
        key_size: RSA 密钥大小 (位数),默认为 2048 位
                  推荐值: 2048 (标准), 4096 (更安全但更慢)
                  
    返回:
        rsa.RSAPrivateKey: 生成的 RSA 私钥对象
    """
    return rsa.generate_private_key(
        public_exponent=65537,  # 公共指数,使用标准值 65537 (0x10001)
        key_size=key_size,
        backend=default_backend(),
    )


def generate_ca_certificate(
    private_key: rsa.RSAPrivateKey,
    common_name: str = "SMTP Tunnel CA",
    days_valid: int = 3650
) -> x509.Certificate:
    """
    生成自签名证书颁发机构 (CA) 证书
    
    CA 证书用于签名服务器证书,客户端使用 CA 证书来验证服务器身份
    
    参数:
        private_key: CA 的私钥,用于签名证书
        common_name: CA 的通用名称 (CN),默认为 "SMTP Tunnel CA"
        days_valid: 证书有效期 (天数),默认为 3650 天 (10 年)
        
    返回:
        x509.Certificate: 生成的 CA 证书对象
    """
    # 创建证书主体和颁发者 (自签名证书中两者相同)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),                    # 国家代码
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),  # 州/省
        x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),       # 城市
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SMTP Tunnel"),      # 组织名称
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),              # 通用名称
    ])

    # 构建证书
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)           # 设置证书主体
        .issuer_name(issuer)            # 设置证书颁发者
        .public_key(private_key.public_key())  # 设置公钥
        .serial_number(x509.random_serial_number())  # 生成随机序列号
        .not_valid_before(datetime.now(timezone.utc))        # 证书生效时间 (当前 UTC 时间)
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=days_valid))  # 证书过期时间
        .add_extension(
            # 基本约束: 标识为 CA 证书,不允许下级 CA (path_length=0)
            x509.BasicConstraints(ca=True, path_length=0),
            critical=True,  # 标记为关键扩展
        )
        .add_extension(
            # 密钥用途: 定义证书密钥的用途
            x509.KeyUsage(
                digital_signature=True,    # 数字签名
                key_encipherment=False,    # 密钥加密 (CA 不需要)
                content_commitment=False,  # 内容承诺 (旧称 nonRepudiation)
                data_encipherment=False,   # 数据加密
                key_agreement=False,       # 密钥协商
                key_cert_sign=True,       # 证书签名 (CA 必需)
                crl_sign=True,            # CRL 签名 (吊销列表签名)
                encipher_only=False,      # 仅加密
                decipher_only=False,      # 仅解密
            ),
            critical=True,
        )
        .add_extension(
            # 主题密钥标识符: 标识证书中的公钥
            x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()),
            critical=False,
        )
        .add_extension(
            # 颁发者密钥标识符: 标识签发此证书的CA的公钥
            # 对于自签名CA证书，颁发者密钥标识符指向自己的公钥
            x509.AuthorityKeyIdentifier.from_issuer_public_key(private_key.public_key()),
            critical=False,
        )
        .sign(private_key, hashes.SHA256(), default_backend())  # 使用私钥签名
    )

    return cert


def generate_server_certificate(
    ca_key: rsa.RSAPrivateKey,
    ca_cert: x509.Certificate,
    server_key: rsa.RSAPrivateKey,
    hostname: str = "mail.example.com",
    days_valid: int = 1095
) -> x509.Certificate:
    """
    生成由 CA 签名的服务器证书
    模拟真实邮件服务器的证书,用于 SMTP 隧道服务器
    
    参数:
        ca_key: CA 的私钥,用于签名服务器证书
        ca_cert: CA 的证书,作为颁发者
        server_key: 服务器的私钥对应的公钥
        hostname: 服务器主机名,将作为证书的通用名称 (CN)
                  默认为 "mail.example.com"
        days_valid: 证书有效期 (天数),默认为 1095 天 (3 年)
        
    返回:
        x509.Certificate: 生成的服务器证书对象
    """
    # 创建服务器证书主体
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),                    # 国家代码
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),  # 州/省
        x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),       # 城市
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Example Mail Services"),  # 组织名称
        x509.NameAttribute(NameOID.COMMON_NAME, hostname),                  # 通用名称 (主机名)
    ])

    # 主题备用名称 (SAN) - 对 TLS 验证非常重要
    # 允许客户端使用多个名称连接到服务器
    san = x509.SubjectAlternativeName([
        x509.DNSName(hostname),  # 主机名
        # 自动生成 smtp. 前缀的域名 (例如: smtp.example.com)
        x509.DNSName(f"smtp.{hostname.split('.', 1)[-1] if '.' in hostname else hostname}"),
        x509.DNSName("localhost"),  # 本地访问
    ])

    # 构建服务器证书
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)              # 设置证书主体
        .issuer_name(ca_cert.subject)       # 设置证书颁发者 (CA)
        .public_key(server_key.public_key())  # 设置服务器公钥
        .serial_number(x509.random_serial_number())  # 生成随机序列号
        .not_valid_before(datetime.now(timezone.utc))        # 证书生效时间
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=days_valid))  # 证书过期时间
        .add_extension(san, critical=False)  # 添加主题备用名称扩展
        .add_extension(
            # 基本约束: 标识为非 CA 证书
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            # 密钥用途: 定义服务器证书密钥的用途
            x509.KeyUsage(
                digital_signature=True,   # 数字签名 (TLS 握手需要)
                key_encipherment=True,   # 密钥加密 (用于加密会话密钥)
                content_commitment=False, # 内容承诺
                data_encipherment=False,  # 数据加密
                key_agreement=False,      # 密钥协商
                key_cert_sign=False,      # 证书签名 (服务器不需要)
                crl_sign=False,           # CRL 签名
                encipher_only=False,      # 仅加密
                decipher_only=False,      # 仅解密
            ),
            critical=True,
        )
        .add_extension(
            # 扩展密钥用途: 定义证书的具体用途
            x509.ExtendedKeyUsage([
                ExtendedKeyUsageOID.SERVER_AUTH,  # 服务器认证 (TLS 服务器)
                ExtendedKeyUsageOID.CLIENT_AUTH,  # 客户端认证 (可选)
            ]),
            critical=False,
        )
        .add_extension(
            # 主题密钥标识符: 标识证书中的公钥
            x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()),
            critical=False,
        )
        .add_extension(
            # 颁发者密钥标识符: 标识签发此证书的CA的公钥
            # 从CA证书中提取颁发者密钥标识符
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_cert.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256(), default_backend())  # 使用 CA 私钥签名
    )

    return cert


def save_private_key(key: rsa.RSAPrivateKey, path: str, password: bytes = None):
    """
    保存私钥到 PEM 格式文件
    
    参数:
        key: 要保存的 RSA 私钥对象
        path: 保存路径
        password: 可选的加密密码,如果提供则使用 AES 加密私钥
                 如果为 None,则保存为未加密的私钥
    """
    # 根据是否提供密码选择加密方式
    encryption = (
        serialization.BestAvailableEncryption(password)  # 使用最佳可用加密 (AES)
        if password
        else serialization.NoEncryption()  # 不加密
    )

    # 将私钥序列化为 PEM 格式
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,  # PEM 编码 (Base64 + 头尾标记)
        format=serialization.PrivateFormat.TraditionalOpenSSL,  # 传统 OpenSSL 格式
        encryption_algorithm=encryption,  # 加密算法
    )

    # 写入文件
    with open(path, 'wb') as f:
        f.write(pem)

    # 设置安全的文件权限 (仅所有者可读)
    # 在 Linux/Unix 系统上设置为 0o600 (rw-------)
    try:
        os.chmod(path, 0o600)
    except (OSError, AttributeError):
        pass  # Windows 系统不支持 chmod,忽略错误


def save_certificate(cert: x509.Certificate, path: str):
    """
    保存证书到 PEM 格式文件
    
    参数:
        cert: 要保存的证书对象
        path: 保存路径
    """
    # 将证书序列化为 PEM 格式
    pem = cert.public_bytes(serialization.Encoding.PEM)

    # 写入文件
    with open(path, 'wb') as f:
        f.write(pem)


def main():
    """
    主函数 - 解析命令行参数并生成证书
    
    命令行参数:
        --hostname: 服务器主机名 (默认: mail.example.com)
        --output-dir: 证书输出目录 (默认: 当前目录)
        --days: 证书有效期天数 (默认: 1095 = 3 年)
        --key-size: RSA 密钥大小 (默认: 2048 位)
    """
    parser = argparse.ArgumentParser(
        description='为 SMTP 隧道生成 TLS 证书'
    )
    parser.add_argument(
        '--hostname',
        default='mail.example.com',
        help='证书的服务器主机名 (默认: mail.example.com)'
    )
    parser.add_argument(
        '--output-dir',
        default='.',
        help='证书输出目录 (默认: 当前目录)'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=1095,
        help='证书有效期天数 (默认: 1095 = 3 年)'
    )
    parser.add_argument(
        '--key-size',
        type=int,
        default=2048,
        help='RSA 密钥大小 (位) (默认: 2048)'
    )

    args = parser.parse_args()

    # 输入验证：验证主机名格式
    hostname_pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*$'
    if not re.match(hostname_pattern, args.hostname):
        print(f"错误: 无效的主机名格式: {args.hostname}")
        print("主机名只能包含字母、数字、连字符和点号")
        sys.exit(1)
    
    # 验证主机名长度
    if len(args.hostname) > 253:
        print(f"错误: 主机名太长: {len(args.hostname)} 字符 (最大 253)")
        sys.exit(1)
    
    # 输入验证：验证密钥大小
    MIN_KEY_SIZE = 2048
    MAX_KEY_SIZE = 8192
    if args.key_size < MIN_KEY_SIZE:
        print(f"警告: 密钥大小 {args.key_size} 位太小，不安全")
        print(f"自动调整为最小安全大小: {MIN_KEY_SIZE} 位")
        args.key_size = MIN_KEY_SIZE
    elif args.key_size > MAX_KEY_SIZE:
        print(f"警告: 密钥大小 {args.key_size} 位太大，生成会很慢")
        print(f"自动调整为最大推荐大小: {MAX_KEY_SIZE} 位")
        args.key_size = MAX_KEY_SIZE
    
    # 输入验证：验证有效期天数
    MIN_DAYS = 1
    MAX_DAYS = 3650  # 10年
    if args.days < MIN_DAYS:
        print(f"错误: 有效期天数不能小于 {MIN_DAYS}")
        sys.exit(1)
    if args.days > MAX_DAYS:
        print(f"警告: 有效期 {args.days} 天超过推荐最大值 {MAX_DAYS} 天 (10年)")
    
    # 输入验证：验证输出目录安全性
    output_dir = os.path.abspath(args.output_dir)
    
    # 检查输出目录是否在敏感位置
    sensitive_paths = ['/etc', '/root', '/var/log']
    for sensitive in sensitive_paths:
        if output_dir.startswith(sensitive):
            print(f"警告: 输出目录位于敏感位置: {output_dir}")
            response = input("是否继续? (y/N): ")
            if response.lower() != 'y':
                print("已取消")
                sys.exit(0)
            break
    
    # 检查输出目录是否已存在证书文件
    cert_files = ['ca.key', 'ca.crt', 'server.key', 'server.crt']
    existing_files = [f for f in cert_files if os.path.exists(os.path.join(output_dir, f))]
    if existing_files:
        print(f"警告: 以下证书文件已存在: {', '.join(existing_files)}")
        response = input("是否覆盖? (y/N): ")
        if response.lower() != 'y':
            print("已取消")
            sys.exit(0)

    # 如果需要,创建输出目录
    os.makedirs(output_dir, exist_ok=True)

    # 显示配置信息
    print(f"正在为以下主机名生成证书: {args.hostname}")
    print(f"密钥大小: {args.key_size} 位")
    print(f"有效期: {args.days} 天")
    print()

    # 生成 CA 证书和私钥
    print("正在生成 CA 私钥...")
    ca_key = generate_private_key(args.key_size)

    print("正在生成 CA 证书...")
    ca_cert = generate_ca_certificate(ca_key, days_valid=args.days * 10)

    # 生成服务器证书和私钥
    print("正在生成服务器私钥...")
    server_key = generate_private_key(args.key_size)

    print("正在生成服务器证书...")
    server_cert = generate_server_certificate(
        ca_key, ca_cert, server_key,
        hostname=args.hostname,
        days_valid=args.days
    )

    # 构建文件路径
    ca_key_path = os.path.join(args.output_dir, 'ca.key')
    ca_cert_path = os.path.join(args.output_dir, 'ca.crt')
    server_key_path = os.path.join(args.output_dir, 'server.key')
    server_cert_path = os.path.join(args.output_dir, 'server.crt')

    # 保存文件
    print()
    print("正在保存文件...")

    save_private_key(ca_key, ca_key_path)
    print(f"  CA 私钥:              {ca_key_path}")

    save_certificate(ca_cert, ca_cert_path)
    print(f"  CA 证书:              {ca_cert_path}")

    save_private_key(server_key, server_key_path)
    print(f"  服务器私钥:          {server_key_path}")

    save_certificate(server_cert, server_cert_path)
    print(f"  服务器证书:          {server_cert_path}")

    # 显示使用说明
    print()
    print("证书生成完成!")
    print()
    print("服务器端需要以下文件:")
    print(f"  - {server_cert_path}")
    print(f"  - {server_key_path}")
    print()
    print("客户端需要以下文件 (用于验证服务器):")
    print(f"  - {ca_cert_path}")
    print()
    print("或者在客户端配置中禁用证书验证 (安全性较低)。")


if __name__ == '__main__':
    main()
