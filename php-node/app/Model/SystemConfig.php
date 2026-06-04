<?php

declare(strict_types=1);

namespace App\Model;

use App\Core\Database;
use App\Core\Cache;

/**
 * 系统配置模型
 */
class SystemConfig
{
    /** 缓存键 */
    private const CACHE_KEY = 'system_config';
    private const CACHE_TTL = 300;

    /**
     * 获取系统配置（带缓存）
     */
    public static function getConfig(): array
    {
        $cache = Cache::getInstance();

        return $cache->remember(self::CACHE_KEY, self::CACHE_TTL, function (): array {
            $config = Database::getInstance()->fetch('SELECT * FROM system_configs WHERE id = 1');

            if ($config === null) {
                return [
                    'id'                     => 1,
                    'site_name'              => '2c2a',
                    'enable_registration'    => false,
                    'captcha_provider'       => 'none',
                    'hostname_branding'      => [],
                    'email_suffix_whitelist' => null,
                    'email_suffix_blacklist' => null,
                ];
            }

            // 解析 JSONB 字段
            if (is_string($config['hostname_branding'] ?? null)) {
                $config['hostname_branding'] = json_decode($config['hostname_branding'], true) ?? [];
            }

            return $config;
        });
    }

    /**
     * 更新系统配置
     */
    public static function updateConfig(int $id, array $data): bool
    {
        $allowed = [
            'smtp_host', 'smtp_port', 'smtp_use_tls', 'smtp_username', 'smtp_password',
            'smtp_from_email', 'captcha_provider', 'captcha_type',
            'login_captcha_type', 'register_captcha_type', 'email_captcha_type',
            'site_name', 'enable_registration', 'icp_number', 'police_number',
            'email_suffix_whitelist', 'email_suffix_blacklist',
            'local_access_locked', 'hostname_branding',
        ];

        $updateData = array_intersect_key($data, array_flip($allowed));

        if (empty($updateData)) {
            return false;
        }

        // 编码 JSONB 字段
        if (isset($updateData['hostname_branding']) && is_array($updateData['hostname_branding'])) {
            $updateData['hostname_branding'] = json_encode($updateData['hostname_branding'], JSON_UNESCAPED_UNICODE);
        }

        $rows = Database::getInstance()->update('system_configs', $updateData, 'id = :id', [':id' => $id]);

        // 清除缓存
        Cache::getInstance()->delete(self::CACHE_KEY);

        return $rows > 0;
    }

    /**
     * 获取指定场景的验证码配置
     */
    public static function getCaptchaConfig(array $config, ?string $scene = null): array
    {
        $provider = $config['captcha_provider'] ?? 'none';

        if ($provider === 'none') {
            return ['enabled' => false, 'provider' => 'none', 'type' => 'none'];
        }

        // 根据场景选择验证码类型
        $type = match ($scene) {
            'login'    => $config['login_captcha_type'] ?? $config['captcha_type'] ?? 'SLIDER',
            'register' => $config['register_captcha_type'] ?? $config['captcha_type'] ?? 'SLIDER',
            'email'    => $config['email_captcha_type'] ?? $config['captcha_type'] ?? 'SLIDER',
            default    => $config['captcha_type'] ?? 'SLIDER',
        };

        return [
            'enabled'  => true,
            'provider' => $provider,
            'type'     => $type,
        ];
    }

    /**
     * 根据主机名获取品牌配置
     */
    public static function getBrandingForHostname(array $config, string $hostname): array
    {
        $branding = $config['hostname_branding'] ?? [];

        if (empty($branding) || !is_array($branding)) {
            return [];
        }

        // 查找精确匹配
        if (isset($branding[$hostname])) {
            return $branding[$hostname];
        }

        // 查找通配符匹配
        foreach ($branding as $pattern => $brand) {
            if (fnmatch($pattern, $hostname)) {
                return $brand;
            }
        }

        return [];
    }

    /**
     * 根据主机名获取站点名称
     */
    public static function getSiteNameForHostname(array $config, string $hostname): string
    {
        $branding = self::getBrandingForHostname($config, $hostname);

        if (!empty($branding['site_name'])) {
            return $branding['site_name'];
        }

        return $config['site_name'] ?? APP_NAME;
    }

    /**
     * 获取邮箱后缀白名单/黑名单
     */
    public static function getEmailSuffixes(array $config): array
    {
        $whitelist = $config['email_suffix_whitelist'] ?? null;
        $blacklist = $config['email_suffix_blacklist'] ?? null;

        $parseList = function (?string $value): array {
            if (empty($value)) {
                return [];
            }

            // 支持逗号分隔或换行分隔
            $items = preg_split('/[,\n]+/', $value);
            return array_map('trim', array_filter($items));
        };

        return [
            'whitelist' => $parseList($whitelist),
            'blacklist' => $parseList($blacklist),
        ];
    }

    /**
     * 检查邮箱后缀是否被允许
     */
    public static function isEmailSuffixAllowed(string $email): bool
    {
        $config = self::getConfig();
        $suffixes = self::getEmailSuffixes($config);

        $domain = strtolower(substr(strrchr($email, '@'), 1));

        if ($domain === false) {
            return false;
        }

        // 黑名单优先
        if (!empty($suffixes['blacklist']) && in_array($domain, $suffixes['blacklist'], true)) {
            return false;
        }

        // 白名单存在时检查
        if (!empty($suffixes['whitelist']) && !in_array($domain, $suffixes['whitelist'], true)) {
            return false;
        }

        return true;
    }

    /**
     * 清除配置缓存
     */
    public static function clearCache(): void
    {
        Cache::getInstance()->delete(self::CACHE_KEY);
    }
}
