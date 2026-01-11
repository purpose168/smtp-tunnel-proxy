#!/usr/bin/env python3
"""
为 SMTP 隧道生成自签名 TLS 证书。
创建模拟真实邮件服务器的服务器证书。

版本: 1.3.0

功能概述:
本脚本用于生成自签名 TLS 证书，用于 SMTP 隧道代理系统的加密通信。
生成的证书包括:
1. CA（证书颁发机构）证书 - 用于签署服务器证书
2. 服务器证书 - 用于 SMTP 服务器 TLS 加密

证书特性:
- 使用 RSA 算法生成密钥对
- 支持 X.509 v3 证书标准
- 包含基本约束、密钥用法、扩展密钥用法等扩展
- 支持主题备用名称（SAN）以支持多个主机名

使用示例:
    # 使用默认参数生成证书
    python generate_certs.py

    # 指定主机名和输出目录
    python generate_certs.py --hostname mail.mydomain.com --output-dir ./certs

    # 指定密钥大小和有效期
    python generate_certs.py --key-size 4096 --days 365
"""

# 标准库导入
import os           # 用于文件和目录操作
import sys          # 用于系统相关功能
import argparse     # 用于命令行参数解析
from datetime import datetime, timedelta, timezone  # 用于日期时间处理

# 加密库导入
from cryptography import x509                                   # 用于 X.509 证书操作
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID  # 用于证书对象标识符
from cryptography.hazmat.primitives import hashes               # 用于哈希算法
from cryptography.hazmat.primitives.asymmetric import rsa       # 用于 RSA 密钥生成
from cryptography.hazmat.primitives import serialization        # 用于密钥和证书序列化
from cryptography.hazmat.backends import default_backend        # 用于加密后端


def generate_private_key(key_size: int = 2048) -> rsa.RSAPrivateKey:
    """
    生成 RSA 私钥
    
    生成用于 TLS 证书的 RSA 私钥对。RSA 是最常用的非对称加密算法，
    广泛用于 TLS/SSL 证书中。
    
    密钥参数说明:
    - public_exponent (65537): 公钥指数，使用 65537 (0x10001) 是行业标准
      该值是费马素数 F4，在安全性和性能之间取得了良好平衡
    - key_size: 密钥大小（位），推荐值:
      - 2048 位: 当前标准，安全性足够
      - 4096 位: 更高安全性，但计算开销更大
    
    Args:
        key_size: RSA 密钥大小（位），默认 2048
                  常见值: 2048, 4096
    
    Returns:
        rsa.RSAPrivateKey: 生成的 RSA 私钥对象
    
    Raises:
        ValueError: 如果密钥大小不是有效值
    
    使用示例:
        # 生成 2048 位密钥
        key = generate_private_key(2048)
        
        # 生成 4096 位密钥（更高安全性）
        key = generate_private_key(4096)
    """
    return rsa.generate_private_key(
        public_exponent=65537,  # 使用标准的公钥指数 65537 (F4)
        key_size=key_size,
        backend=default_backend(),
    )


def generate_ca_certificate(
    private_key: rsa.RSAPrivateKey,
    common_name: str = "SMTP Tunnel CA",
    days_valid: int = 3650
) -> x509.Certificate:
    """
    生成自签名 CA（证书颁发机构）证书
    
    生成一个自签名的 CA 证书，用于签署后续的服务器证书。
    CA 证书是信任链的根，客户端需要信任此 CA 才能验证服务器证书。
    
    证书扩展说明:
    1. BasicConstraints (ca=True, path_length=0):
       - ca=True: 标识这是一个 CA 证书
       - path_length=0: 此 CA 不能签署其他 CA 证书（只能签署终端实体证书）
    
    2. KeyUsage:
       - digital_signature=True: 允许数字签名
       - key_cert_sign=True: 允许签署证书（CA 特有）
       - crl_sign=True: 允许签署证书撤销列表（CRL）
       - 其他用法设为 False，因为 CA 不需要这些功能
    
    3. SubjectKeyIdentifier:
       - 从公钥派生，用于唯一标识此证书的公钥
       - 非关键扩展，用于证书链验证
    
    Args:
        private_key: 用于签署证书的 RSA 私钥
        common_name: CA 的通用名称，默认 "SMTP Tunnel CA"
        days_valid: 证书有效期（天），默认 3650 天（10 年）
    
    Returns:
        x509.Certificate: 生成的自签名 CA 证书
    
    使用示例:
        # 生成密钥对
        ca_key = generate_private_key(2048)
        
        # 生成 CA 证书（10 年有效期）
        ca_cert = generate_ca_certificate(ca_key, days_valid=3650)
    """
    # 证书主题（Subject）和颁发者（Issuer）- 自签名证书两者相同
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),                     # 国家代码
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),   # 州/省
        x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),         # 城市
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SMTP Tunnel"),       # 组织名称 
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),               # 通用名称
    ])

    # 构建证书
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)                          # 设置主题（CA 证书的通用名称）
        .issuer_name(issuer)                            # 设置颁发者（自签名）  
        .public_key(private_key.public_key())           # 设置公钥
        .serial_number(x509.random_serial_number())     # 生成随机序列号
        .not_valid_before(datetime.now(timezone.utc))   # 生效时间（当前 UTC 时间）
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=days_valid))  # 过期时间
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=0),  # 基本约束：CA 证书，不能签署其他 CA
            critical=True,  # 关键扩展
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,     # 允许数字签名
                key_encipherment=False,     # 不允许密钥加密
                content_commitment=False,   # 不允许内容承诺（不可否认性）
                data_encipherment=False,    # 不允许数据加密
                key_agreement=False,        # 不允许密钥协商
                key_cert_sign=True,         # 允许签署证书（CA 特有）
                crl_sign=True,              # 允许签署 CRL（CA 特有）
                encipher_only=False,        # 不允许仅加密
                decipher_only=False,        # 不允许仅解密  
            ),
            critical=True,  # 关键扩展
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()),  # 主题密钥标识符
            critical=False,  # 非关键扩展
        )
        .sign(private_key, hashes.SHA256(), default_backend())  # 使用 SHA256 签名
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
    
    生成一个模拟真实邮件服务器的 TLS 证书，由 CA 签名。
    此证书用于 SMTP 服务器的 TLS 加密通信。
    
    证书特性:
    1. 主题备用名称（SAN）:
       - 包含指定的主机名
       - 包含 smtp.域名 格式（如 smtp.example.com）
       - 包含 localhost（用于本地测试）
    
    2. 证书扩展:
       - BasicConstraints (ca=False): 标识这是终端实体证书，不是 CA
       - KeyUsage: 允许数字签名和密钥加密（用于 TLS 握手）
       - ExtendedKeyUsage: SERVER_AUTH 和 CLIENT_AUTH（用于 TLS 服务器和客户端认证）
       - AuthorityKeyIdentifier: 标识签署此证书的 CA
    
    Args:
        ca_key: CA 的私钥，用于签署服务器证书
        ca_cert: CA 的证书，用于设置颁发者信息
        server_key: 服务器的私钥，用于生成公钥
        hostname: 服务器的主机名，默认 "mail.example.com"
        days_valid: 证书有效期（天），默认 1095 天（3 年）
    
    Returns:
        x509.Certificate: 由 CA 签名的服务器证书
    
    使用示例:
        # 生成 CA 密钥和证书
        ca_key = generate_private_key(2048)
        ca_cert = generate_ca_certificate(ca_key)
        
        # 生成服务器密钥
        server_key = generate_private_key(2048)
        
        # 生成服务器证书（3 年有效期）
        server_cert = generate_server_certificate(
            ca_key, ca_cert, server_key,
            hostname="mail.mydomain.com",
            days_valid=1095
        )
    """
    # 服务器证书主题
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),                         # 国家代码
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),       # 州/省
        x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),             # 城市
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Example Mail Services"), # 组织名称
        x509.NameAttribute(NameOID.COMMON_NAME, hostname),                      # 通用名称（主机名）
    ])

    # 主题备用名称（Subject Alternative Name, SAN）
    # SAN 对 TLS 验证非常重要，允许证书用于多个主机名
    san = x509.SubjectAlternativeName([
        x509.DNSName(hostname),     # 指定的主机名
        x509.DNSName(f"smtp.{hostname.split('.', 1)[-1] if '.' in hostname else hostname}"),  # smtp.域名
        x509.DNSName("localhost"),  # 本地主机（用于测试）
    ])

    # 构建服务器证书
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)                          # 设置主题
        .issuer_name(ca_cert.subject)                   # 设置颁发者（CA 的主题）
        .public_key(server_key.public_key())            # 设置公钥
        .serial_number(x509.random_serial_number())     # 生成随机序列号
        .not_valid_before(datetime.now(timezone.utc))   # 生效时间  
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=days_valid))  # 过期时间
        .add_extension(san, critical=False)             # 添加主题备用名称
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),  # 基本约束：不是 CA 证书
            critical=True,  # 关键扩展
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,     # 允许数字签名（用于 TLS 握手）
                key_encipherment=True,      # 允许密钥加密（用于 TLS 握手）
                content_commitment=False,   # 不允许内容承诺
                data_encipherment=False,    # 不允许数据加密
                key_agreement=False,        # 不允许密钥协商    
                key_cert_sign=False,        # 不允许签署证书（不是 CA）
                crl_sign=False,             # 不允许签署 CRL（不是 CA）
                encipher_only=False,        # 不允许仅加密
                decipher_only=False,        # 不允许仅解密
            ),
            critical=True,  # 关键扩展
        )
        .add_extension(
            x509.ExtendedKeyUsage([
                ExtendedKeyUsageOID.SERVER_AUTH,  # 服务器认证（用于 TLS 服务器）
                ExtendedKeyUsageOID.CLIENT_AUTH,  # 客户端认证（用于 TLS 客户端）
            ]),
            critical=False,  # 非关键扩展
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),  # 颁发者密钥标识符
            critical=False,  # 非关键扩展
        )
        .sign(ca_key, hashes.SHA256(), default_backend())  # 使用 CA 的私钥和 SHA256 签名
    )

    return cert


def save_private_key(key: rsa.RSAPrivateKey, path: str, password: bytes = None):
    """
    保存私钥到 PEM 文件
    
    将 RSA 私钥以 PEM 格式保存到文件，可选择使用密码加密。
    PEM（Privacy-Enhanced Mail）是 Base64 编码的文本格式，广泛用于 TLS/SSL 证书。
    
    私钥格式说明:
    - 使用 TraditionalOpenSSL 格式，这是 OpenSSL 的传统格式
    - 格式包含: -----BEGIN RSA PRIVATE KEY----- ... -----END RSA PRIVATE KEY-----
    
    加密选项:
    - 如果提供密码，使用 BestAvailableEncryption（最佳可用加密）进行加密
    - 如果不提供密码，使用 NoEncryption（不加密），私钥以明文形式保存
    
    文件权限:
    - 在 Unix/Linux 系统上，设置文件权限为 0o600（仅所有者可读写）
    - 在 Windows 系统上，chmod 不可用，跳过权限设置
    
    Args:
        key: 要保存的 RSA 私钥对象
        path: 保存私钥的文件路径
        password: 可选的密码，用于加密私钥（bytes 类型）
                  如果为 None，私钥将以明文形式保存
    
    Raises:
        OSError: 文件写入失败
        PermissionError: 没有写入权限
    
    使用示例:
        # 生成密钥对
        key = generate_private_key(2048)
        
        # 保存未加密的私钥
        save_private_key(key, "server.key")
        
        # 保存加密的私钥
        save_private_key(key, "server.key", password=b"my_password")
    
    安全提示:
        - 生产环境中建议使用密码加密私钥
        - 私钥文件应设置为仅所有者可读（0o600）
        - 不要将私钥提交到版本控制系统
    """
    # 根据是否提供密码选择加密算法
    encryption = (
        serialization.BestAvailableEncryption(password)  # 使用最佳可用加密
        if password
        else serialization.NoEncryption()  # 不加密
    )

    # 将私钥序列化为 PEM 格式
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,  # PEM 编码
        format=serialization.PrivateFormat.TraditionalOpenSSL,  # 传统 OpenSSL 格式
        encryption_algorithm=encryption,  # 加密算法
    )

    # 写入文件
    with open(path, 'wb') as f:
        f.write(pem)

    # 设置安全的文件权限（仅所有者可读）
    # Unix/Linux: 0o600 = rw------- (仅所有者可读写)
    # Windows: chmod 不支持，跳过
    try:
        os.chmod(path, 0o600)
    except (OSError, AttributeError):
        pass  # Windows 不以相同方式支持 chmod


def save_certificate(cert: x509.Certificate, path: str):
    """
    保存证书到 PEM 文件
    
    将 X.509 证书以 PEM 格式保存到文件。
    PEM（Privacy-Enhanced Mail）是 Base64 编码的文本格式，广泛用于 TLS/SSL 证书。
    
    证书格式说明:
    - 使用 PEM 编码，这是最常用的证书格式
    - 格式包含: -----BEGIN CERTIFICATE----- ... -----END CERTIFICATE-----
    - 证书包含公钥、主题、颁发者、有效期、签名等信息
    
    证书内容:
    - 版本号（X.509 版本）
    - 序列号（唯一标识符）
    - 签名算法（如 SHA256withRSA）
    - 颁发者（Issuer）- 签署此证书的 CA
    - 有效期（not_valid_before 和 not_valid_after）
    - 主题（Subject）- 证书持有者的信息
    - 公钥信息
    - 扩展（如 KeyUsage、ExtendedKeyUsage、SAN 等）
    - 签名（CA 的签名）
    
    Args:
        cert: 要保存的 X.509 证书对象
        path: 保存证书的文件路径
    
    Raises:
        OSError: 文件写入失败
        PermissionError: 没有写入权限
    
    使用示例:
        # 生成 CA 证书
        ca_key = generate_private_key(2048)
        ca_cert = generate_ca_certificate(ca_key)
        
        # 保存 CA 证书
        save_certificate(ca_cert, "ca.crt")
        
        # 生成服务器证书
        server_key = generate_private_key(2048)
        server_cert = generate_server_certificate(ca_key, ca_cert, server_key)
        
        # 保存服务器证书
        save_certificate(server_cert, "server.crt")
    
    注意事项:
        - 证书文件通常使用 .crt 或 .pem 扩展名
        - CA 证书需要分发给客户端以验证服务器证书
        - 服务器证书和私钥需要部署在服务器上
    """
    # 将证书序列化为 PEM 格式
    pem = cert.public_bytes(serialization.Encoding.PEM)

    # 写入文件
    with open(path, 'wb') as f:
        f.write(pem)


def main():
    """
    主函数 - 命令行入口点
    
    解析命令行参数，生成 CA 证书和服务器证书，并保存到指定目录。
    
    执行流程:
    1. 解析命令行参数（主机名、输出目录、有效期、密钥大小）
    2. 创建输出目录（如果不存在）
    3. 生成 CA 私钥和证书（有效期是服务器证书的 10 倍）
    4. 生成服务器私钥和证书
    5. 保存所有文件到输出目录
    6. 打印使用说明
    
    生成的文件:
    - ca.key: CA 私钥（用于签署其他证书）
    - ca.crt: CA 证书（用于客户端验证）
    - server.key: 服务器私钥（用于 TLS 服务器）
    - server.crt: 服务器证书（包含公钥）
    
    命令行参数:
    --hostname: 服务器主机名（默认: mail.example.com）
    --output-dir: 输出目录（默认: 当前目录）
    --days: 证书有效期（天，默认: 1095 = 3 年）
    --key-size: RSA 密钥大小（位，默认: 2048）
    
    使用示例:
        # 使用默认参数
        python generate_certs.py
        
        # 指定主机名
        python generate_certs.py --hostname mail.mydomain.com
        
        # 指定输出目录
        python generate_certs.py --output-dir ./certs
        
        # 指定密钥大小和有效期
        python generate_certs.py --key-size 4096 --days 365
        
        # 组合使用
        python generate_certs.py --hostname mail.example.com --output-dir ./certs --days 1825 --key-size 4096
    
    部署说明:
    服务器端:
        - 部署 server.crt 和 server.key 到 SMTP 服务器
        - 在服务器配置中指定证书和私钥路径
    
    客户端:
        - 复制 ca.crt 到客户端
        - 在客户端配置中指定 CA 证书路径
        - 或禁用证书验证（不推荐，安全性较低）
    """
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(
        description='为 SMTP 隧道生成 TLS 证书'
    )
    
    # 添加命令行参数
    parser.add_argument(
        '--hostname',
        default='mail.example.com',
        help='证书的服务器主机名（默认: mail.example.com）'
    )
    parser.add_argument(
        '--output-dir',
        default='.',
        help='证书的输出目录（默认: 当前目录）'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=1095,
        help='证书有效期（天）（默认: 1095 = 3 年）'
    )
    parser.add_argument(
        '--key-size',
        type=int,
        default=2048,
        help='RSA 密钥大小（位）（默认: 2048）'
    )

    # 解析命令行参数
    args = parser.parse_args()

    # 如需要，创建输出目录
    os.makedirs(args.output_dir, exist_ok=True)

    # 打印配置信息
    print(f"为主机名生成证书: {args.hostname}")
    print(f"密钥大小: {args.key_size} 位")
    print(f"有效期: {args.days} 天")
    print()

    # ========== 生成 CA 证书 ==========
    print("正在生成 CA 私钥...")
    ca_key = generate_private_key(args.key_size)

    print("正在生成 CA 证书...")
    # CA 证书有效期是服务器证书的 10 倍（减少 CA 证书更新频率）
    ca_cert = generate_ca_certificate(ca_key, days_valid=args.days * 10)

    # ========== 生成服务器证书 ==========
    print("正在生成服务器私钥...")
    server_key = generate_private_key(args.key_size)

    print("正在生成服务器证书...")
    server_cert = generate_server_certificate(
        ca_key, ca_cert, server_key,
        hostname=args.hostname,
        days_valid=args.days
    )

    # ========== 保存文件 ==========
    # 构建文件路径
    ca_key_path = os.path.join(args.output_dir, 'ca.key')
    ca_cert_path = os.path.join(args.output_dir, 'ca.crt')
    server_key_path = os.path.join(args.output_dir, 'server.key')
    server_cert_path = os.path.join(args.output_dir, 'server.crt')

    print()
    print("正在保存文件...")

    # 保存 CA 文件
    save_private_key(ca_key, ca_key_path)
    print(f"  CA 私钥:            {ca_key_path}")

    save_certificate(ca_cert, ca_cert_path)
    print(f"  CA 证书:            {ca_cert_path}")

    # 保存服务器文件
    save_private_key(server_key, server_key_path)
    print(f"  服务器私钥:        {server_key_path}")

    save_certificate(server_cert, server_cert_path)
    print(f"  服务器证书:        {server_cert_path}")

    # ========== 打印使用说明 ==========
    print()
    print("证书生成完成！")
    print()
    print("对于服务器，您需要:")
    print(f"  - {server_cert_path}")
    print(f"  - {server_key_path}")
    print()
    print("对于客户端（用于验证服务器），复制:")
    print(f"  - {ca_cert_path}")
    print()
    print("或在客户端配置中禁用证书验证（不太安全）。")


if __name__ == '__main__':
    main()
