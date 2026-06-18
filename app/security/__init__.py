"""安全与加密模块。

设计依据（来自架构要求）：
- 用户密码：前端 BLAKE2b 预哈希（防 DoS 截断）+ 后端 Argon2id 加盐慢哈希
- 敏感字段：HKDF-SHA256 按字段名派生子密钥 + AES-256-GCM 加密（字段级密钥隔离 + 防篡改）
- 缓存键 / ETag：keyed-BLAKE2b 对域名+路径+参数带密钥哈希
- Access Token：Ed25519 签名的 JWT，5 分钟有效期，存放前端内存
- Refresh Token：AES-GCM 加密，7 天有效期，存放 HttpOnly Cookie
- 令牌撤销：ban_version 机制，JWT Payload 携带版本号，封禁时递增数据库版本，无需 Redis 黑名单
"""
