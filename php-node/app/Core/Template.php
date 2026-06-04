<?php

declare(strict_types=1);

namespace App\Core;

/**
 * 简易模板引擎 - 纯 PHP 模板，支持布局和区块
 */
class Template
{
    /** @var string 模板根目录 */
    private readonly string $templateDir;

    /** @var string 当前布局名称 */
    private string $layout = '';

    /** @var array<string, string> 区块内容 */
    private array $sections = [];

    /** @var array<string, string> 已填充的区块 */
    private array $filledSections = [];

    /** @var string 当前正在填充的区块名 */
    private string $currentSection = '';

    /** @var bool 是否正在捕获区块内容 */
    private bool $capturing = false;

    public function __construct(?string $templateDir = null)
    {
        $this->templateDir = $templateDir ?? dirname(__DIR__, 2) . '/templates';
    }

    /**
     * 渲染模板
     *
     * @param string $template 模板路径（如 'dashboard/index'）
     * @param array $data 传递给模板的数据
     */
    public function render(string $template, array $data = []): string
    {
        $templateFile = $this->resolveTemplatePath($template);

        if (!file_exists($templateFile)) {
            return $this->renderError("模板文件不存在: {$template}", 500);
        }

        // 将数据提取为变量
        $e = $this->e(...); // 传递转义函数
        extract($data, EXTR_SKIP);

        // 开启输出缓冲
        ob_start();

        try {
            include $templateFile;
        } catch (\Throwable $e) {
            ob_end_clean();
            return $this->renderError("模板渲染错误: {$e->getMessage()}", 500);
        }

        $content = ob_get_clean();

        // 如果设置了布局，渲染布局
        if ($this->layout !== '') {
            $this->filledSections['content'] = $content;
            $content = $this->renderLayout();
        }

        // 重置状态
        $this->layout = '';
        $this->sections = [];
        $this->filledSections = [];
        $this->currentSection = '';
        $this->capturing = false;

        return $content;
    }

    /**
     * 在模板中声明继承布局
     * 用法: $this->extends('layouts/base')
     */
    public function extends(string $layout): void
    {
        $this->layout = $layout;
    }

    /**
     * 开始定义区块
     * 用法: $this->section('content') ... $this->endSection()
     */
    public function section(string $name): void
    {
        $this->currentSection = $name;
        $this->capturing = true;
        ob_start();
    }

    /**
     * 结束区块定义
     */
    public function endSection(): void
    {
        if (!$this->capturing) {
            return;
        }

        $content = ob_get_clean();
        $this->filledSections[$this->currentSection] = $content;
        $this->capturing = false;
        $this->currentSection = '';
    }

    /**
     * 在布局中输出区块内容
     * 用法: $this->yield('content')
     */
    public function yield(string $name, string $default = ''): string
    {
        return $this->filledSections[$name] ?? $this->sections[$name] ?? $default;
    }

    /**
     * 包含子模板
     * 用法: $this->include('partials/header', ['title' => '首页'])
     */
    public function include(string $template, array $data = []): string
    {
        return $this->render($template, $data);
    }

    /**
     * HTML 转义
     */
    public function e(string $value): string
    {
        return htmlspecialchars($value, ENT_QUOTES | ENT_HTML5, 'UTF-8', true);
    }

    /**
     * 属性转义（用于 HTML 属性）
     */
    public function eAttr(string $value): string
    {
        return htmlspecialchars($value, ENT_QUOTES | ENT_HTML5, 'UTF-8', true);
    }

    /**
     * JavaScript 转义
     */
    public function eJs(string $value): string
    {
        return json_encode($value, JSON_UNESCAPED_UNICODE | JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT);
    }

    /**
     * CSS 转义
     */
    public function eCss(string $value): string
    {
        return preg_replace('/[^a-zA-Z0-9\-_]/', '', $value);
    }

    /**
     * URL 转义
     */
    public function eUrl(string $value): string
    {
        return rawurlencode($value);
    }

    /**
     * 生成 CSRF 隐藏字段 HTML
     */
    public function csrfField(): string
    {
        $csrf = Csrf::class;
        // 延迟获取 CSRF 实例
        $session = Session::getInstance();
        $csrfInstance = new Csrf($session);
        $token = $csrfInstance->token();

        return '<input type="hidden" name="' . CSRF_TOKEN_NAME . '" value="' . $this->e($token) . '">';
    }

    /**
     * 生成 HTTP 方法隐藏字段
     */
    public function methodField(string $method): string
    {
        return '<input type="hidden" name="_method" value="' . $this->e(strtoupper($method)) . '">';
    }

    /**
     * 解析模板文件路径
     */
    private function resolveTemplatePath(string $template): string
    {
        // 规范化路径分隔符
        $template = str_replace('.', '/', $template);

        return $this->templateDir . '/' . $template . '.php';
    }

    /**
     * 渲染布局
     */
    private function renderLayout(): string
    {
        $layoutFile = $this->resolveTemplatePath($this->layout);

        if (!file_exists($layoutFile)) {
            return $this->renderError("布局文件不存在: {$this->layout}", 500);
        }

        ob_start();

        try {
            include $layoutFile;
        } catch (\Throwable $e) {
            ob_end_clean();
            return $this->renderError("布局渲染错误: {$e->getMessage()}", 500);
        }

        return ob_get_clean();
    }

    /**
     * 渲染错误页面
     */
    private function renderError(string $message, int $code): string
    {
        if (APP_DEBUG) {
            return "<html><body><h1>模板错误</h1><p>{$message}</p></body></html>";
        }

        return "<html><body><h1>{$code} - 服务器错误</h1><p>页面渲染失败</p></body></html>";
    }
}
