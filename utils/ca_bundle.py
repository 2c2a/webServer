#!/usr/bin/env python3
"""
WinRM PKI 证书生成器

生成 WinRM HTTPS 所需的 CA、服务器、客户端证书（含 UPN SAN）。
依赖: pip install cryptography
"""

import datetime
import ipaddress
import shutil
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    Encoding,
    NoEncryption,
    PrivateFormat,
    pkcs12,
)
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID, ObjectIdentifier

# ============================================================
# 配置项（按需修改）
# ============================================================
WINDOWS_IP = "192.168.122.234"
WINDOWS_HOSTNAME = "WIN-R8S5ITT8IC9"
OUTPUT_DIR = "winrm-pki"
VALIDITY_DAYS = 3650
PFX_PASSWORD = b"changeit"
UPN_VALUE = "test@localhost"
UPN_OID = "1.3.6.1.4.1.311.20.2.3"


# ============================================================
# 基础工具函数
# ============================================================

def ensure_output_dir(output_dir: str) -> Path:
    """确保输出目录存在并切换工作目录。"""
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    import os
    os.chdir(path)
    return path


def generate_ec_key() -> ec.EllipticCurvePrivateKey:
    """生成 EC 私钥（prime256v1 / P-256 曲线）。"""
    return ec.generate_private_key(ec.SECP256R1(), default_backend())


def save_private_key(key: ec.EllipticCurvePrivateKey, filename: str) -> None:
    """将私钥保存为 PEM 文件（SEC1 格式，与 openssl ecparam 输出一致）。"""
    pem = key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=NoEncryption(),
    )
    Path(filename).write_bytes(pem)
    print(f"  已保存私钥: {filename}")


def save_certificate(cert: x509.Certificate, filename: str) -> None:
    """将证书保存为 PEM 文件。"""
    pem = cert.public_bytes(Encoding.PEM)
    Path(filename).write_bytes(pem)
    print(f"  已保存证书: {filename}")


def export_pfx(
    cert: x509.Certificate,
    key: ec.EllipticCurvePrivateKey,
    ca_cert: x509.Certificate,
    password: bytes,
    filename: str,
) -> None:
    """将证书 + 私钥 + CA 证书导出为 PKCS#12 (.pfx) 文件。"""
    pfx_data = pkcs12.serialize_key_and_certificates(
        name=None,
        key=key,
        cert=cert,
        cas=[ca_cert],
        encryption_algorithm=BestAvailableEncryption(password),
    )
    Path(filename).write_bytes(pfx_data)
    print(f"  已导出 PFX: {filename}")


def _validity_period():
    """返回证书的有效期起止时间。"""
    now = datetime.datetime.now(datetime.timezone.utc)
    return now, now + datetime.timedelta(days=VALIDITY_DAYS)


def _encode_upn_other_name(upn: str) -> x509.OtherName:
    """
    编码 UPN OtherName（OID 1.3.6.1.4.1.311.20.2.3）。
    值为 DER 编码的 UTF8String。
    """
    oid = ObjectIdentifier(UPN_OID)
    encoded = upn.encode("utf-8")
    # DER: tag(0x0C=UTF8String) + length + value
    der_value = b"\x0c" + bytes([len(encoded)]) + encoded
    return x509.OtherName(oid, der_value)


# ============================================================
# 步骤 1：创建 CA
# ============================================================

def build_ca_certificate(ca_key: ec.EllipticCurvePrivateKey) -> x509.Certificate:
    """创建自签名 CA 证书（对应 bash 中 ca.cnf 的扩展配置）。"""
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "WinRM-CA"),
    ])
    not_before, not_after = _validity_period()

    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        # basicConstraints = critical, CA:TRUE
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None), critical=True
        )
        # keyUsage = critical, digitalSignature, keyCertSign, cRLSign
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        # subjectKeyIdentifier = hash
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
            critical=False,
        )
        # authorityKeyIdentifier = keyid:always, issuer
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
    )
    return builder.sign(ca_key, hashes.SHA256(), default_backend())


def create_ca() -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
    """步骤 1：创建 CA 私钥和自签名证书。"""
    print("\n" + "=" * 50)
    print("1. 创建 CA")
    print("=" * 50)

    ca_key = generate_ec_key()
    save_private_key(ca_key, "ca.key")

    ca_cert = build_ca_certificate(ca_key)
    save_certificate(ca_cert, "ca.crt")

    print_ca_info(ca_cert)
    return ca_key, ca_cert


# ============================================================
# 步骤 2：签发服务器证书
# ============================================================

def build_server_csr(
    server_key: ec.EllipticCurvePrivateKey, hostname: str
) -> x509.CertificateSigningRequest:
    """生成服务器证书签名请求。"""
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    )
    return builder.sign(server_key, hashes.SHA256(), default_backend())


def sign_server_certificate(
    csr: x509.CertificateSigningRequest,
    ca_key: ec.EllipticCurvePrivateKey,
    ca_cert: x509.Certificate,
    hostname: str,
    ip_address: str,
) -> x509.Certificate:
    """用 CA 签发服务器证书（对应 bash 中 server_ext.cnf 的扩展配置）。"""
    not_before, not_after = _validity_period()

    san = x509.SubjectAlternativeName([
        x509.DNSName(hostname),
        x509.IPAddress(ipaddress.ip_address(ip_address)),
    ])

    builder = (
        x509.CertificateBuilder()
        .subject_name(csr.subject)
        .issuer_name(ca_cert.subject)
        .public_key(csr.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        # basicConstraints = CA:FALSE
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=False
        )
        # keyUsage = critical, digitalSignature, keyEncipherment
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                content_commitment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                data_encipherment=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        # extendedKeyUsage = serverAuth
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        # subjectAltName
        .add_extension(san, critical=False)
        # subjectKeyIdentifier = hash
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(csr.public_key()),
            critical=False,
        )
        # authorityKeyIdentifier = keyid,issuer
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
    )
    return builder.sign(ca_key, hashes.SHA256(), default_backend())


def create_server_cert(
    ca_key: ec.EllipticCurvePrivateKey,
    ca_cert: x509.Certificate,
) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
    """步骤 2：签发服务器证书。"""
    print("\n" + "=" * 50)
    print("2. 签发服务器证书")
    print("=" * 50)

    server_key = generate_ec_key()
    save_private_key(server_key, "server.key")

    csr = build_server_csr(server_key, WINDOWS_HOSTNAME)
    server_cert = sign_server_certificate(
        csr, ca_key, ca_cert, WINDOWS_HOSTNAME, WINDOWS_IP
    )
    save_certificate(server_cert, "server.crt")

    export_pfx(server_cert, server_key, ca_cert, PFX_PASSWORD, "server.pfx")

    print_server_info(server_cert)
    return server_key, server_cert


# ============================================================
# 步骤 3：签发客户端证书（含 UPN SAN）
# ============================================================

def build_client_csr(
    client_key: ec.EllipticCurvePrivateKey,
) -> x509.CertificateSigningRequest:
    """生成客户端证书签名请求。"""
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "winrm-client")])
    )
    return builder.sign(client_key, hashes.SHA256(), default_backend())


def sign_client_certificate(
    csr: x509.CertificateSigningRequest,
    ca_key: ec.EllipticCurvePrivateKey,
    ca_cert: x509.Certificate,
) -> x509.Certificate:
    """用 CA 签发客户端证书（对应 bash 中 client_ext.cnf，含 UPN SAN）。"""
    not_before, not_after = _validity_period()

    san = x509.SubjectAlternativeName([_encode_upn_other_name(UPN_VALUE)])

    builder = (
        x509.CertificateBuilder()
        .subject_name(csr.subject)
        .issuer_name(ca_cert.subject)
        .public_key(csr.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        # basicConstraints = CA:FALSE
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=False
        )
        # keyUsage = critical, digitalSignature
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=False,
                content_commitment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                data_encipherment=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        # extendedKeyUsage = clientAuth
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
            critical=False,
        )
        # subjectKeyIdentifier = hash
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(csr.public_key()),
            critical=False,
        )
        # authorityKeyIdentifier = keyid,issuer
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        # ★ subjectAltName = UPN otherName ★
        .add_extension(san, critical=False)
    )
    return builder.sign(ca_key, hashes.SHA256(), default_backend())


def create_client_cert(
    ca_key: ec.EllipticCurvePrivateKey,
    ca_cert: x509.Certificate,
) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
    """步骤 3：签发客户端证书。"""
    print("\n" + "=" * 50)
    print("3. 签发客户端证书")
    print("=" * 50)

    client_key = generate_ec_key()
    save_private_key(client_key, "client.key")

    csr = build_client_csr(client_key)
    client_cert = sign_client_certificate(csr, ca_key, ca_cert)
    save_certificate(client_cert, "client.crt")

    # 复制为兼容命名的 PEM 文件
    shutil.copy2("client.crt", "client-cert.pem")
    shutil.copy2("client.key", "client-key.pem")
    print("  已复制: client.crt -> client-cert.pem")
    print("  已复制: client.key -> client-key.pem")

    export_pfx(client_cert, client_key, ca_cert, PFX_PASSWORD, "client.pfx")

    print_client_info(client_cert)
    return client_key, client_cert


# ============================================================
# 证书信息打印
# ============================================================

def print_ca_info(cert: x509.Certificate) -> None:
    """打印 CA 证书关键信息。"""
    print("\n=== CA 证书 ===")
    print(f"  Subject: {cert.subject.rfc4514_string()}")
    for ext in cert.extensions:
        if isinstance(ext.value, x509.BasicConstraints):
            print(f"  Basic Constraints: CA={ext.value.ca}")
        elif isinstance(ext.value, x509.KeyUsage):
            usages = []
            if ext.value.digital_signature:
                usages.append("digitalSignature")
            if ext.value.key_cert_sign:
                usages.append("keyCertSign")
            if ext.value.crl_sign:
                usages.append("cRLSign")
            print(f"  Key Usage: {', '.join(usages)}")
    fingerprint = cert.fingerprint(hashes.SHA256()).hex(":")
    print(f"  SHA256 Fingerprint: {fingerprint}")


def print_server_info(cert: x509.Certificate) -> None:
    """打印服务器证书关键信息。"""
    print("\n=== 服务器证书 ===")
    print(f"  Subject: {cert.subject.rfc4514_string()}")
    print(f"  Issuer:  {cert.issuer.rfc4514_string()}")


def print_client_info(cert: x509.Certificate) -> None:
    """打印客户端证书关键信息（含 SAN）。"""
    print("\n=== 客户端证书 ===")
    print(f"  Subject: {cert.subject.rfc4514_string()}")
    print(f"  Issuer:  {cert.issuer.rfc4514_string()}")
    print("  --- SAN ---")
    for ext in cert.extensions:
        if isinstance(ext.value, x509.SubjectAlternativeName):
            for name in ext.value:
                if isinstance(name, x509.OtherName):
                    print(
                        f"    OtherName (OID {name.type_id.dotted_string}): "
                        f"{name.value!r}"
                    )


def print_summary() -> None:
    """打印最终汇总信息。"""
    print("\n" + "=" * 50)
    print("生成完毕！需要导入 Windows 的文件：")
    print("  ca.crt     → LocalMachine\\Root")
    print("  server.pfx → LocalMachine\\My")
    print("  client.crt → LocalMachine\\TrustedPeople")
    print("=" * 50)


# ============================================================
# 主入口
# ============================================================

def main() -> None:
    """主入口：按顺序执行 CA → 服务器证书 → 客户端证书。"""
    ensure_output_dir(OUTPUT_DIR)

    ca_key, ca_cert = create_ca()
    create_server_cert(ca_key, ca_cert)
    create_client_cert(ca_key, ca_cert)

    print_summary()


if __name__ == "__main__":
    main()
