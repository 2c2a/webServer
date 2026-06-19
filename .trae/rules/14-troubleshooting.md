# 14 - 故障排查

## 环境问题

### Python 版本

```bash
python --version   # 需要 >= 3.12
```

### 依赖

```bash
pip install -e .            # 安装全部依赖
pip install <package>       # 添加依赖
```

## 数据库问题

### 连接失败

```bash
2c2a serve check
# 检查 DB_ENGINE/DB_HOST/DB_PORT/DB_USER/DB_PASSWORD
```

### DetachedInstanceError

**原因**：异步会话关闭后访问懒加载关系。

**修复**：用 `selectinload` 预加载。

### 迁移失败

```bash
2c2a db current    # 查看当前版本
2c2a db history    # 查看历史
2c2a db downgrade -1  # 回滚一个版本
2c2a db reset      # 重置（危险！开发用）
```

## 启动问题

### 端口被占用

```bash
lsof -i :8000   # Linux/Mac
2c2a serve serve --port 8001  # 换端口
```

### 密钥未配置

生产环境必须显式配置所有密钥。查看状态：`2c2a keys show`

### Redis 连接失败

```bash
redis-cli ping
# 或禁用：REDIS_ENABLED=false
```

## 认证问题

```bash
2c2a account info <username>   # 查看用户状态
2c2a account activate <username>  # 激活
2c2a account changepassword <username>  # 重置密码（递增 ban_version）
```

### ban_version 不匹配

封禁或改密码后所有已签发令牌失效，用户需重新登录。

## 缓存问题

```bash
# 清除租户缓存
2c2a tenant invalidate-cache

# 清除所有 Redis 缓存
redis-cli FLUSHDB
```

## 诊断命令

```bash
2c2a serve check         # 配置检查
2c2a keys show           # 密钥状态
2c2a db current          # 数据库版本
2c2a plugin list         # 插件状态
2c2a tenant list         # 租户列表
2c2a account list        # 用户列表
```