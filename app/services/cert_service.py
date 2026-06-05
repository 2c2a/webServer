"""
证书服务

生成 CA、服务器证书、客户端证书，使用 ECC P-256 算法。
纯函数式实现，无状态，可同步调用。
"""
import datetime
import ipaddress
import secrets
import string

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    Encoding,
    NoEncryption,
    PrivateFormat,
    pkcs12,
)
from cryptography.x509.oid import (
    ExtendedKeyUsageOID,
    NameOID,
    ObjectIdentifier,
)


def _generate_ec_key() -> ec.EllipticCurvePrivateKey:
    """生成 ECC P-256 私钥"""
    return ec.generate_private_key(ec.SECP256R1())


def generate_ca(
    ca_name: str = "WinRM-CA",
    validity_days: int = 3650,
) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
    """
    生成 CA 根证书

    返回:
        (ca_private_key, ca_certificate)
    """
    ca_key = _generate_ec_key()
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, ca_name),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=validity_days))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
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
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
    )
    ca_cert = builder.sign(ca_key, hashes.SHA256())
    return ca_key, ca_cert


def issue_server_cert(
    ca_key: ec.EllipticCurvePrivateKey,
    ca_cert: x509.Certificate,
    hostname: str,
    ip_address: str | None = None,
    validity_days: int = 3650,
    pfx_password: str | None = None,
) -> dict:
    """
    签发服务器证书

    返回:
        dict: {
            "server_key": EllipticCurvePrivateKey,
            "server_cert": Certificate,
            "pfx_data": bytes,
            "pfx_password": str,
        }
    """
    server_key = _generate_ec_key()
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, hostname),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)

    san_entries = [x509.DNSName(hostname)]
    if ip_address:
        try:
            san_entries.append(x509.IPAddress(ipaddress.ip_address(ip_address)))
        except ValueError:
            pass
    san = x509.SubjectAlternativeName(san_entries)

    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=validity_days))
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=False,
        )
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
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .add_extension(san, critical=False)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
    )
    server_cert = builder.sign(ca_key, hashes.SHA256())

    if pfx_password is None:
        pfx_password = generate_random_password(16)

    pfx_data = pkcs12.serialize_key_and_certificates(
        name=None,
        key=server_key,
        cert=server_cert,
        cas=[ca_cert],
        encryption_algorithm=BestAvailableEncryption(pfx_password.encode("utf-8")),
    )

    return {
        "server_key": server_key,
        "server_cert": server_cert,
        "pfx_data": pfx_data,
        "pfx_password": pfx_password,
    }


def issue_client_cert(
    ca_key: ec.EllipticCurvePrivateKey,
    ca_cert: x509.Certificate,
    upn_value: str,
    validity_days: int = 3650,
) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
    """
    签发客户端证书（用于 WinRM 证书认证）

    返回:
        (client_private_key, client_certificate)
    """
    client_key = _generate_ec_key()
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "winrm-client"),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    san = x509.SubjectAlternativeName([
        _encode_upn_other_name(upn_value),
    ])

    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(client_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=validity_days))
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=False,
        )
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
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
            critical=False,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(client_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .add_extension(san, critical=False)
    )
    client_cert = builder.sign(ca_key, hashes.SHA256())
    return client_key, client_cert


def _encode_upn_other_name(upn: str) -> x509.OtherName:
    """编码 UPN 为 OtherName 扩展（用于 WinRM 证书认证）"""
    oid = ObjectIdentifier("1.3.6.1.4.1.311.20.2.3")
    encoded = upn.encode("utf-8")
    der_value = b"\x0c" + bytes([len(encoded)]) + encoded
    return x509.OtherName(oid, der_value)


def key_to_pem(key: ec.EllipticCurvePrivateKey) -> bytes:
    """将私钥导出为 PEM 格式"""
    return key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    )


def cert_to_pem(cert: x509.Certificate) -> bytes:
    """将证书导出为 PEM 格式"""
    return cert.public_bytes(Encoding.PEM)


def generate_random_username(prefix: str = "c2a_", length: int = 8) -> str:
    """生成随机用户名"""
    alphabet = string.ascii_lowercase + string.digits
    return prefix + "".join(secrets.choice(alphabet) for _ in range(length))


def generate_random_password(length: int = 16) -> str:
    """生成随机密码（满足复杂性要求）"""
    if length < 4:
        raise ValueError("密码长度至少为4位")
    parts = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*"),
    ]
    remaining = length - len(parts)
    pool = string.ascii_letters + string.digits + "!@#$%^&*"
    parts.extend(secrets.choice(pool) for _ in range(remaining))
    shuffled = list(parts)
    for i in range(len(shuffled) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
    return "".join(shuffled)
