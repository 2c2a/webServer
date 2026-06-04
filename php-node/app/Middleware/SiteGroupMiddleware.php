<?php

declare(strict_types=1);

namespace App\Middleware;

use App\Core\Request;
use App\Core\Response;
use App\Core\Database;
use App\Core\Cache;

/**
 * 站点组中间件 - 根据 HTTP Host 头确定当前站点组
 *
 * 从 site_group_hostnames 表查找主机名对应的站点组，
 * 将站点组信息设置到请求属性中，供后续控制器使用
 */
class SiteGroupMiddleware
{
    private Database $database;
    private Cache $cache;

    public function __construct(Database $database, Cache $cache)
    {
        $this->database = $database;
        $this->cache = $cache;
    }

    /**
     * 处理请求
     *
     * @param Request $request 请求对象
     * @param callable $next 下一个中间件/处理器
     * @return Response 响应对象
     */
    public function handle(Request $request, callable $next): Response
    {
        $host = $request->getHost();

        // 查找站点组
        $siteGroup = $this->resolveSiteGroup($host);

        if ($siteGroup !== null) {
            // 设置站点组信息到请求属性
            $request->attributes['site_group'] = $siteGroup;
            $request->attributes['site_group_id'] = (int) $siteGroup['id'];
            $request->attributes['site_group_name'] = $siteGroup['name'];
            $request->attributes['site_group_slug'] = $siteGroup['slug'];

            // 从站点组获取品牌配置
            $this->setBrandingAttributes($request, $siteGroup);
        } else {
            // 没有匹配的站点组，使用默认值
            $request->attributes['site_group'] = null;
            $request->attributes['site_group_id'] = null;
            $request->attributes['site_group_name'] = APP_NAME;
            $request->attributes['site_group_slug'] = 'default';

            // 从系统配置获取品牌信息
            $this->setDefaultBranding($request);
        }

        return $next($request);
    }

    /**
     * 解析主机名对应的站点组
     */
    private function resolveSiteGroup(string $host): ?array
    {
        $cacheKey = 'sitegroup:host:' . $host;

        return $this->cache->remember($cacheKey, 3600, function () use ($host): ?array {
            $row = $this->database->fetch(
                'SELECT sg.id, sg.name, sg.slug, sg.site_name, sg.site_icon, sg.description
                 FROM site_groups sg
                 INNER JOIN site_group_hostnames sgh ON sgh.site_group_id = sg.id
                 WHERE sgh.hostname = :hostname AND sg.is_active = true',
                [':hostname' => $host]
            );

            return $row;
        });
    }

    /**
     * 设置品牌属性
     */
    private function setBrandingAttributes(Request $request, array $siteGroup): void
    {
        $siteName = !empty($siteGroup['site_name']) ? $siteGroup['site_name'] : APP_NAME;
        $siteIcon = $siteGroup['site_icon'] ?? '';

        // 从 hostname_branding JSONB 获取更多品牌配置
        $branding = $this->getBrandingConfig();

        $request->attributes['site_name'] = $siteName;
        $request->attributes['site_icon'] = $siteIcon;
        $request->attributes['site_logo'] = $branding['logo'] ?? $siteIcon;
        $request->attributes['site_welcome_text'] = $branding['welcome_text'] ?? '';
        $request->attributes['site_primary_color'] = $branding['primary_color'] ?? '#3b82f6';
        $request->attributes['site_custom_css'] = $branding['custom_css'] ?? '';
    }

    /**
     * 设置默认品牌属性
     */
    private function setDefaultBranding(Request $request): void
    {
        $branding = $this->getBrandingConfig();

        $request->attributes['site_name'] = $branding['site_name'] ?? APP_NAME;
        $request->attributes['site_icon'] = $branding['site_icon'] ?? '';
        $request->attributes['site_logo'] = $branding['logo'] ?? '';
        $request->attributes['site_welcome_text'] = $branding['welcome_text'] ?? '';
        $request->attributes['site_primary_color'] = $branding['primary_color'] ?? '#3b82f6';
        $request->attributes['site_custom_css'] = $branding['custom_css'] ?? '';
    }

    /**
     * 获取品牌配置
     */
    private function getBrandingConfig(): array
    {
        return $this->cache->remember('branding_config', 3600, function (): array {
            $row = $this->database->fetch(
                'SELECT hostname_branding, site_name FROM system_configs WHERE id = 1'
            );

            if ($row === null) {
                return [];
            }

            $branding = [];
            if (is_string($row['hostname_branding'])) {
                $branding = json_decode($row['hostname_branding'], true) ?? [];
            } elseif (is_array($row['hostname_branding'])) {
                $branding = $row['hostname_branding'];
            }

            if (!empty($row['site_name'])) {
                $branding['site_name'] = $row['site_name'];
            }

            return $branding;
        });
    }
}
