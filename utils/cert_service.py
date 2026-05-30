import datetime
import ipaddress
import secrets
import string

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    pkcs12,
)
from cryptography.x509.oid import (
    ExtendedKeyUsageOID,
    NameOID,
    ObjectIdentifier,
)


def generate_ec_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1(), default_backend())


def generate_ca(
    ca_name: str = "WinRM-CA",
    validity_days: int = 3650,
) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
    ca_key = generate_ec_key()
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, ca_name),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    not_before = now
    not_after = now + datetime.timedelta(days=validity_days)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
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
            x509.AuthorityKeyIdentifier.from_issuer_public_key(
                ca_key.public_key()
            ),
            critical=False,
        )
    )
    ca_cert = builder.sign(ca_key, hashes.SHA256(), default_backend())
    return ca_key, ca_cert


def issue_server_cert(
    ca_key: ec.EllipticCurvePrivateKey,
    ca_cert: x509.Certificate,
    hostname: str,
    ip_address: str | None = None,
    validity_days: int = 3650,
    pfx_password: str | None = None,
) -> dict:
    server_key = generate_ec_key()
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, hostname),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    not_before = now
    not_after = now + datetime.timedelta(days=validity_days)
    san_entries = [x509.DNSName(hostname)]
    if ip_address:
        try:
            san_entries.append(
                x509.IPAddress(ipaddress.ip_address(ip_address))
            )
        except ValueError:
            # Invalid IP input is intentionally ignored; DNS SAN is still used.
            pass
    san = x509.SubjectAlternativeName(san_entries)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
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
            x509.AuthorityKeyIdentifier.from_issuer_public_key(
                ca_key.public_key()
            ),
            critical=False,
        )
    )
    server_cert = builder.sign(ca_key, hashes.SHA256(), default_backend())
    if pfx_password is None:
        pfx_password = generate_random_pfx_password()
    pfx_data = export_pfx(
        server_cert, server_key, ca_cert,
        pfx_password.encode("utf-8"),
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
    client_key = generate_ec_key()
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "winrm-client"),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    not_before = now
    not_after = now + datetime.timedelta(days=validity_days)
    san = x509.SubjectAlternativeName([
        encode_upn_other_name(upn_value),
    ])
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(client_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
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
            x509.AuthorityKeyIdentifier.from_issuer_public_key(
                ca_key.public_key()
            ),
            critical=False,
        )
        .add_extension(san, critical=False)
    )
    client_cert = builder.sign(ca_key, hashes.SHA256(), default_backend())
    return client_key, client_cert


def encode_upn_other_name(upn: str) -> x509.OtherName:
    oid = ObjectIdentifier("1.3.6.1.4.1.311.20.2.3")
    encoded = upn.encode("utf-8")
    der_value = b"\x0c" + bytes([len(encoded)]) + encoded
    return x509.OtherName(oid, der_value)


def export_pfx(
    cert: x509.Certificate,
    key: ec.EllipticCurvePrivateKey,
    ca_cert: x509.Certificate,
    password_bytes: bytes,
) -> bytes:
    return pkcs12.serialize_key_and_certificates(
        name=None,
        key=key,
        cert=cert,
        cas=[ca_cert],
        encryption_algorithm=BestAvailableEncryption(password_bytes),
    )


def generate_random_pfx_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_random_username(prefix: str = "c2a_", length: int = 8) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return prefix + "".join(secrets.choice(alphabet) for _ in range(length))


def generate_random_password(length: int = 16) -> str:
    if length < 4:
        raise ValueError(
            "Password length must be at least 4 "
            "to meet complexity requirements"
        )
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
