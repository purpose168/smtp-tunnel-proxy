#!/usr/bin/env python3
"""
为 SMTP 隧道生成自签名 TLS 证书。
创建模拟真实邮件服务器的服务器证书。

版本: 1.3.0
"""

import os
import sys
import argparse
from datetime import datetime, timedelta

from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend


def generate_private_key(key_size: int = 2048) -> rsa.RSAPrivateKey:
    """生成 RSA 私钥。"""
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
        backend=default_backend(),
    )


def generate_ca_certificate(
    private_key: rsa.RSAPrivateKey,
    common_name: str = "SMTP Tunnel CA",
    days_valid: int = 3650
) -> x509.Certificate:
    """生成自签名 CA 证书。"""
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SMTP Tunnel"),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=days_valid))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=0),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=False,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(private_key, hashes.SHA256(), default_backend())
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
    生成由 CA 签名的服务器证书。
    模拟真实的邮件服务器证书。
    """
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Example Mail Services"),
        x509.NameAttribute(NameOID.COMMON_NAME, hostname),
    ])

    # 主题备用名称（对 TLS 验证很重要）
    san = x509.SubjectAlternativeName([
        x509.DNSName(hostname),
        x509.DNSName(f"smtp.{hostname.split('.', 1)[-1] if '.' in hostname else hostname}"),
        x509.DNSName("localhost"),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=days_valid))
        .add_extension(san, critical=False)
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([
                ExtendedKeyUsageOID.SERVER_AUTH,
                ExtendedKeyUsageOID.CLIENT_AUTH,
            ]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256(), default_backend())
    )

    return cert


def save_private_key(key: rsa.RSAPrivateKey, path: str, password: bytes = None):
    """保存私钥到 PEM 文件。"""
    encryption = (
        serialization.BestAvailableEncryption(password)
        if password
        else serialization.NoEncryption()
    )

    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=encryption,
    )

    with open(path, 'wb') as f:
        f.write(pem)

    # 安全的文件权限（仅所有者可读）
    try:
        os.chmod(path, 0o600)
    except (OSError, AttributeError):
        pass  # Windows 不以相同方式支持 chmod


def save_certificate(cert: x509.Certificate, path: str):
    """保存证书到 PEM 文件。"""
    pem = cert.public_bytes(serialization.Encoding.PEM)

    with open(path, 'wb') as f:
        f.write(pem)


def main():
    parser = argparse.ArgumentParser(
        description='为 SMTP 隧道生成 TLS 证书'
    )
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

    args = parser.parse_args()

    # 如需要，创建输出目录
    os.makedirs(args.output_dir, exist_ok=True)

    print(f"为主机名生成证书: {args.hostname}")
    print(f"密钥大小: {args.key_size} 位")
    print(f"有效期: {args.days} 天")
    print()

    # 生成 CA
    print("正在生成 CA 私钥...")
    ca_key = generate_private_key(args.key_size)

    print("正在生成 CA 证书...")
    ca_cert = generate_ca_certificate(ca_key, days_valid=args.days * 10)

    # 生成服务器证书
    print("正在生成服务器私钥...")
    server_key = generate_private_key(args.key_size)

    print("正在生成服务器证书...")
    server_cert = generate_server_certificate(
        ca_key, ca_cert, server_key,
        hostname=args.hostname,
        days_valid=args.days
    )

    # 保存文件
    ca_key_path = os.path.join(args.output_dir, 'ca.key')
    ca_cert_path = os.path.join(args.output_dir, 'ca.crt')
    server_key_path = os.path.join(args.output_dir, 'server.key')
    server_cert_path = os.path.join(args.output_dir, 'server.crt')

    print()
    print("正在保存文件...")

    save_private_key(ca_key, ca_key_path)
    print(f"  CA 私钥:            {ca_key_path}")

    save_certificate(ca_cert, ca_cert_path)
    print(f"  CA 证书:            {ca_cert_path}")

    save_private_key(server_key, server_key_path)
    print(f"  服务器私钥:        {server_key_path}")

    save_certificate(server_cert, server_cert_path)
    print(f"  服务器证书:        {server_cert_path}")

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
