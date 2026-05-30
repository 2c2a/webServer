from django.db import models
from django.conf import settings
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import NameOID
from cryptography.fernet import Fernet, InvalidToken
from django.core.exceptions import ValidationError
import datetime
import base64
import hashlib
import ipaddress
import secrets
import string


def _get_fernet():
    key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


class CertificateAuthority(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name="CA名称")
    _private_key = models.TextField(db_column='private_key', verbose_name="私钥(加密)")
    certificate = models.TextField(verbose_name="CA证书(PEM)")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "证书颁发机构"
        verbose_name_plural = "证书颁发机构"
        db_table = "certificate_authority"

    @property
    def private_key(self):
        if not self._private_key:
            return None
        try:
            return _get_fernet().decrypt(self._private_key.encode()).decode()
        except InvalidToken:
            raise ValueError("私钥解密失败，数据可能已损坏或密钥已变更")

    @private_key.setter
    def private_key(self, value):
        if value:
            self._private_key = _get_fernet().encrypt(value.encode()).decode()
        else:
            self._private_key = ''

    def generate_self_signed_cert(self):
        private_key = ec.generate_private_key(
            ec.SECP256R1(), default_backend()
        )

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, self.name),
        ])

        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            private_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.datetime.utcnow()
        ).not_valid_after(
            datetime.datetime.utcnow() + datetime.timedelta(days=3650)
        ).add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        ).add_extension(
            x509.KeyUsage(
                key_cert_sign=True,
                crl_sign=True,
                digital_signature=True,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                content_commitment=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        ).add_extension(
            x509.SubjectKeyIdentifier.from_public_key(
                private_key.public_key()
            ),
            critical=False,
        ).add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(
                private_key.public_key()
            ),
            critical=False,
        ).sign(private_key, hashes.SHA256(), default_backend())

        self.private_key = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')

        self.certificate = cert.public_bytes(
            serialization.Encoding.PEM
        ).decode('utf-8')
        self.expires_at = (
            datetime.datetime.utcnow() + datetime.timedelta(days=3650)
        )

    def __str__(self):
        return f"CA: {self.name}"


class ServerCertificate(models.Model):
    hostname = models.CharField(
        max_length=255, unique=True, verbose_name="主机名"
    )
    ip_address = models.GenericIPAddressField(
        null=True, blank=True, verbose_name='IP地址'
    )
    ca = models.ForeignKey(CertificateAuthority, on_delete=models.CASCADE)
    thumbprint = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_revoked = models.BooleanField(default=False)
    revocation_reason = models.CharField(max_length=255, blank=True, null=True)
    revocation_date = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name = "服务器证书"
        verbose_name_plural = "服务器证书"
        db_table = "server_certificate"

    def revoke(self, reason=""):
        self.is_revoked = True
        self.revocation_reason = reason
        self.revocation_date = datetime.datetime.utcnow()
        self.save()

    def __str__(self):
        return f"Server Cert: {self.hostname}"


class ClientCertificate(models.Model):
    name = models.CharField(max_length=255)
    upn_value = models.CharField(
        max_length=255, blank=True, default='',
        verbose_name='UPN值'
    )
    ca = models.ForeignKey(CertificateAuthority, on_delete=models.CASCADE)
    thumbprint = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    assigned_to_user = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True
    )
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "客户端证书"
        verbose_name_plural = "客户端证书"
        db_table = "client_certificate"

    def __str__(self):
        user_info = (
            f" (User: {self.assigned_to_user.username})"
            if self.assigned_to_user else ""
        )
        return f"Client Cert: {self.name}{user_info}"
