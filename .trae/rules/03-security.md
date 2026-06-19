# 03 - 安全与加密

## 密钥体系

项目使用 5 类密钥，全部通过环境变量配置（`app/core/config.py`）。

| 密钥 | 环境变量 | 用途 | 生成命令 |
| --- | --- | --- | --- |
| SECRET_KEY | `SECRET_KEY` | 通用密钥 | `2c2a keys secret` |
| Ed25519 私钥 | `ED25519_PRIVATE_KEY_PEM` | JWT 签名 | `2c2a keys ed25519` |
| Ed25519 公钥 | `ED25519_PUBLIC_KEY_PEM` | JWT 验签 | 同上 |
| AES-GCM 主密钥 | `CRYPTO_MASTER_KEY_B64` | Refresh Token + 字段加密 | `2c2a keys aes` |
| BLAKE2b 签名密钥 | `CACHE_SIGNING_KEY` | 缓存键签名 | `2c2a keys blake2b` |

一次性生成全部：`2c2a keys generate`

## 密码哈希链路

```
用户输入原始密码 → 前端 BLAKE2b（digest_size=64，输出 hex）
    → BLAKE2b 预哈希（128 字符 hex）
    → 后端 server_side_prehash 校验格式
    → Argon2id 加盐慢哈希
    → PHC 字符串（存数据库 password_hash 字段）
```

```python
from app.security.password import hash_password, verify_password

# 创建
phc = hash_password(blake2b_prehash_hex)
user.password_hash = phc

# 验证
if verify_password(blake2b_prehash_hex, user.password_hash):
    # 登录成功
```

CLI 中创建用户用 `blake2b_prehash_interactive` 模拟前端预哈希。

## JWT（Access Token）

- 算法：Ed25519 非对称签名
- 有效期：5 分钟
- 存储：前端内存，`Authorization: Bearer <token>` 头发送

## Refresh Token

- 算法：AES-256-GCM 加密
- 有效期：7 天
- 存储：HttpOnly Cookie（`2c2a_rt`），防 XSS

## ban_version 无状态撤销

JWT Payload 携带 `ban_version`。封禁/改密码时递增 `user.ban_version += 1`。验签时比对，不等则令牌失效。

优点：无需 Redis 黑名单，秒级生效，无状态。

## 字段级加密

HKDF-SHA256 按字段名派生子密钥 → AES-256-GCM 加密。

```python
from app.security.field_cipher import encrypt_field, decrypt_field

user.phone = encrypt_field("13800138000", field_name="phone")
phone = decrypt_field(user.phone, field_name="phone")
```

## keyed-BLAKE2b 缓存签名

```python
from app.security.crypto import keyed_blake2b_short

cache_key = f"shell:{keyed_blake2b_short(domain, context='domain')}:{keyed_blake2b_short(path, context='path')}"
etag = f'W/"{keyed_blake2b_short(content, context="etag")}"'
```

## 禁止

1. 禁止把密钥写进代码或提交到 Git
2. 禁止在日志中打印密钥
3. 禁止在生产用开发模式派生的密钥
4. `.env` 必须在 `.gitignore` 中（已配置）
5. 密钥泄漏后必须立即轮换