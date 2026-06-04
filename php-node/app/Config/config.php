<?php

declare(strict_types=1);

/**
 * 环境配置加载器 - 手动解析 .env 文件，无外部依赖
 */
function loadEnv(string $path): void
{
    if (!file_exists($path)) {
        return;
    }

    $lines = file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);

    foreach ($lines as $line) {
        $line = trim($line);

        // 跳过注释行
        if (str_starts_with($line, '#')) {
            continue;
        }

        // 解析 KEY=VALUE
        if (!str_contains($line, '=')) {
            continue;
        }

        [$key, $value] = explode('=', $line, 2);
        $key = trim($key);
        $value = trim($value);

        // 去除引号包裹
        if (preg_match('/^["\'](.*)["\']\s*$/', $value, $matches)) {
            $value = $matches[1];
        }

        // 仅当环境变量不存在时设置（不覆盖已有值）
        if (getenv($key) === false) {
            putenv("{$key}={$value}");
            $_ENV[$key] = $value;
        }
    }
}

// 加载 .env 文件
loadEnv(dirname(__DIR__, 2) . '/.env');

/**
 * 获取环境变量值，支持默认值
 */
function env(string $key, string $default = ''): string
{
    $value = getenv($key);
    return $value !== false ? $value : $default;
}

/**
 * 获取环境变量布尔值
 */
function envBool(string $key, bool $default = false): bool
{
    $value = getenv($key);
    if ($value === false) {
        return $default;
    }
    return match (strtolower($value)) {
        'true', '1', 'yes', 'on' => true,
        'false', '0', 'no', 'off' => false,
        default => $default,
    };
}

/**
 * 获取环境变量整数值
 */
function envInt(string $key, int $default = 0): int
{
    $value = getenv($key);
    return $value !== false ? (int) $value : $default;
}

// ============================================================================
// 数据库配置
// ============================================================================
defined('DB_HOST') || define('DB_HOST', env('DB_HOST', '127.0.0.1'));
defined('DB_PORT') || define('DB_PORT', envInt('DB_PORT', 5432));
defined('DB_NAME') || define('DB_NAME', env('DB_NAME', '2c2a'));
defined('DB_USER') || define('DB_USER', env('DB_USER', 'postgres'));
defined('DB_PASS') || define('DB_PASS', env('DB_PASS', ''));
defined('DB_CHARSET') || define('DB_CHARSET', env('DB_CHARSET', 'utf8'));
defined('DB_SCHEMA') || define('DB_SCHEMA', env('DB_SCHEMA', 'public'));
defined('DB_POOL_MAX') || define('DB_POOL_MAX', envInt('DB_POOL_MAX', 10));
defined('DB_POOL_MIN') || define('DB_POOL_MIN', envInt('DB_POOL_MIN', 2));

// ============================================================================
// Redis 配置
// ============================================================================
defined('REDIS_HOST') || define('REDIS_HOST', env('REDIS_HOST', '127.0.0.1'));
defined('REDIS_PORT') || define('REDIS_PORT', envInt('REDIS_PORT', 6379));
defined('REDIS_PASSWORD') || define('REDIS_PASSWORD', env('REDIS_PASSWORD', ''));
defined('REDIS_DATABASE') || define('REDIS_DATABASE', envInt('REDIS_DATABASE', 0));
defined('REDIS_PREFIX') || define('REDIS_PREFIX', env('REDIS_PREFIX', '2c2a:'));
defined('REDIS_TIMEOUT') || define('REDIS_TIMEOUT', envInt('REDIS_TIMEOUT', 2));

// ============================================================================
// 应用配置
// ============================================================================
defined('APP_NAME') || define('APP_NAME', env('APP_NAME', '2C2A'));
defined('APP_ENV') || define('APP_ENV', env('APP_ENV', 'production'));
defined('APP_DEBUG') || define('APP_DEBUG', envBool('APP_DEBUG', false));
defined('APP_URL') || define('APP_URL', env('APP_URL', 'http://localhost'));
defined('APP_KEY') || define('APP_KEY', env('APP_KEY', 'base64:change-me-in-production'));
defined('APP_TIMEZONE') || define('APP_TIMEZONE', env('APP_TIMEZONE', 'Asia/Shanghai'));
defined('APP_LOCALE') || define('APP_LOCALE', env('APP_LOCALE', 'zh_CN'));
defined('APP_VERSION') || define('APP_VERSION', env('APP_VERSION', '1.0.0'));

// ============================================================================
// 会话配置
// ============================================================================
defined('SESSION_LIFETIME') || define('SESSION_LIFETIME', envInt('SESSION_LIFETIME', 7200));
defined('SESSION_NAME') || define('SESSION_NAME', env('SESSION_NAME', '2c2a_sid'));
defined('SESSION_DRIVER') || define('SESSION_DRIVER', env('SESSION_DRIVER', 'redis'));
defined('SESSION_COOKIE_SECURE') || define('SESSION_COOKIE_SECURE', envBool('SESSION_COOKIE_SECURE', false));
defined('SESSION_COOKIE_HTTPONLY') || define('SESSION_COOKIE_HTTPONLY', envBool('SESSION_COOKIE_HTTPONLY', true));
defined('SESSION_COOKIE_SAMESITE') || define('SESSION_COOKIE_SAMESITE', env('SESSION_COOKIE_SAMESITE', 'Lax'));

// ============================================================================
// SMTP 邮件配置
// ============================================================================
defined('SMTP_HOST') || define('SMTP_HOST', env('SMTP_HOST', ''));
defined('SMTP_PORT') || define('SMTP_PORT', envInt('SMTP_PORT', 465));
defined('SMTP_USER') || define('SMTP_USER', env('SMTP_USER', ''));
defined('SMTP_PASS') || define('SMTP_PASS', env('SMTP_PASS', ''));
defined('SMTP_FROM') || define('SMTP_FROM', env('SMTP_FROM', ''));
defined('SMTP_FROM_NAME') || define('SMTP_FROM_NAME', env('SMTP_FROM_NAME', APP_NAME));
defined('SMTP_ENCRYPTION') || define('SMTP_ENCRYPTION', env('SMTP_ENCRYPTION', 'ssl'));

// ============================================================================
// 网关配置
// ============================================================================
defined('GATEWAY_API_URL') || define('GATEWAY_API_URL', env('GATEWAY_API_URL', ''));
defined('GATEWAY_API_KEY') || define('GATEWAY_API_KEY', env('GATEWAY_API_KEY', ''));
defined('GATEWAY_API_SECRET') || define('GATEWAY_API_SECRET', env('GATEWAY_API_SECRET', ''));
defined('GATEWAY_TIMEOUT') || define('GATEWAY_TIMEOUT', envInt('GATEWAY_TIMEOUT', 30));

// ============================================================================
// 文件上传配置
// ============================================================================
defined('UPLOAD_MAX_SIZE') || define('UPLOAD_MAX_SIZE', envInt('UPLOAD_MAX_SIZE', 5242880)); // 5MB
defined('UPLOAD_ALLOWED_TYPES') || define('UPLOAD_ALLOWED_TYPES', env('UPLOAD_ALLOWED_TYPES', 'jpg,jpeg,png,gif,pdf,doc,docx'));
defined('UPLOAD_PATH') || define('UPLOAD_PATH', env('UPLOAD_PATH', dirname(__DIR__, 2) . '/storage/uploads'));
defined('AVATAR_MAX_SIZE') || define('AVATAR_MAX_SIZE', envInt('AVATAR_MAX_SIZE', 2097152)); // 2MB
defined('AVATAR_ALLOWED_TYPES') || define('AVATAR_ALLOWED_TYPES', env('AVATAR_ALLOWED_TYPES', 'jpg,jpeg,png,gif'));

// ============================================================================
// 速率限制配置
// ============================================================================
defined('RATE_LIMIT_ENABLED') || define('RATE_LIMIT_ENABLED', envBool('RATE_LIMIT_ENABLED', true));
defined('RATE_LIMIT_LOGIN_MAX') || define('RATE_LIMIT_LOGIN_MAX', envInt('RATE_LIMIT_LOGIN_MAX', 5));
defined('RATE_LIMIT_LOGIN_DECAY') || define('RATE_LIMIT_LOGIN_DECAY', envInt('RATE_LIMIT_LOGIN_DECAY', 300));
defined('RATE_LIMIT_API_MAX') || define('RATE_LIMIT_API_MAX', envInt('RATE_LIMIT_API_MAX', 60));
defined('RATE_LIMIT_API_DECAY') || define('RATE_LIMIT_API_DECAY', envInt('RATE_LIMIT_API_DECAY', 60));
defined('RATE_LIMIT_EMAIL_MAX') || define('RATE_LIMIT_EMAIL_MAX', envInt('RATE_LIMIT_EMAIL_MAX', 5));
defined('RATE_LIMIT_EMAIL_DECAY') || define('RATE_LIMIT_EMAIL_DECAY', envInt('RATE_LIMIT_EMAIL_DECAY', 3600));

// ============================================================================
// 演示模式配置
// ============================================================================
defined('DEMO_MODE') || define('DEMO_MODE', envBool('DEMO_MODE', false));

// ============================================================================
// 日志配置
// ============================================================================
defined('LOG_PATH') || define('LOG_PATH', env('LOG_PATH', dirname(__DIR__, 2) . '/storage/logs'));
defined('LOG_LEVEL') || define('LOG_LEVEL', env('LOG_LEVEL', APP_DEBUG ? 'debug' : 'warning'));

// ============================================================================
// CSRF 配置
// ============================================================================
defined('CSRF_TOKEN_LENGTH') || define('CSRF_TOKEN_LENGTH', envInt('CSRF_TOKEN_LENGTH', 32));
defined('CSRF_TOKEN_NAME') || define('CSRF_TOKEN_NAME', env('CSRF_TOKEN_NAME', '_csrf_token'));

// ============================================================================
// 密码配置
// ============================================================================
defined('PASSWORD_ALGO') || define('PASSWORD_ALGO', env('PASSWORD_ALGO', 'bcrypt'));
defined('PASSWORD_COST') || define('PASSWORD_COST', envInt('PASSWORD_COST', 12));

// ============================================================================
// 分页配置
// ============================================================================
defined('PAGE_SIZE') || define('PAGE_SIZE', envInt('PAGE_SIZE', 20));
defined('PAGE_SIZE_MAX') || define('PAGE_SIZE_MAX', envInt('PAGE_SIZE_MAX', 100));

// 设置时区
date_default_timezone_set(APP_TIMEZONE);
