from django.db import models
import datetime

from utils.cert_storage import (
    get_ca_file_paths,
    save_ca_files,
    generate_ca_paths,
)


class CertificateAuthority(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name="CA名称")
    cert_root = models.CharField(
        max_length=2, default="", blank=True, verbose_name="证书存储根路径"
    )
    cert_sub = models.CharField(
        max_length=2, default="", blank=True, verbose_name="证书存储子路径"
    )
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
        paths = get_ca_file_paths(self.cert_root, self.cert_sub)
        key_path = paths["key"]
        if not key_path.exists():
            return None
        return key_path.read_text(encoding="utf-8")

    @property
    def certificate(self):
        paths = get_ca_file_paths(self.cert_root, self.cert_sub)
        cert_path = paths["cert"]
        if not cert_path.exists():
            return None
        return cert_path.read_text(encoding="utf-8")

    def save_ca_files(self, ca_key_pem: bytes, ca_cert_pem: bytes):
        if not self.cert_root or not self.cert_sub:
            self.cert_root, self.cert_sub = generate_ca_paths()
        save_ca_files(self.cert_root, self.cert_sub, ca_key_pem, ca_cert_pem)

    def __str__(self):
        return f"CA: {self.name}"


class ServerCertificate(models.Model):
    hostname = models.CharField(max_length=255, unique=True, verbose_name="主机名")
    ip_address = models.GenericIPAddressField(
        null=True, blank=True, verbose_name="IP地址"
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
        max_length=255, blank=True, default="", verbose_name="UPN值"
    )
    ca = models.ForeignKey(CertificateAuthority, on_delete=models.CASCADE)
    thumbprint = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    assigned_to_user = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True
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
            if self.assigned_to_user
            else ""
        )
        return f"Client Cert: {self.name}{user_info}"
