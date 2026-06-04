<?php
/**
 * @var string $siteName 站点名称
 * @var string $siteLogo 站点 Logo
 * @var string $sitePrimaryColor 主色调
 * @var string $siteWelcomeText 欢迎语
 * @var string $error 错误信息
 * @var string $next 登录后跳转地址
 * @var bool $enableRegistration 是否开放注册
 * @var bool $isDemoMode 是否演示模式
 * @var string $captchaProvider 验证码提供商
 * @var App\Core\Template $this
 */
$this->extends('layouts/base');

$siteName = $siteName ?? APP_NAME;
$siteLogo = $siteLogo ?? '';
$sitePrimaryColor = $sitePrimaryColor ?? '#3b82f6';
$siteWelcomeText = $siteWelcomeText ?? '';
$error = $error ?? '';
$next = $next ?? '';
$enableRegistration = $enableRegistration ?? false;
$isDemoMode = $isDemoMode ?? DEMO_MODE;
$captchaProvider = $captchaProvider ?? 'none';
$csrfToken = $csrfToken ?? '';
?>

<?php $this->section('title') ?>登录<?php $this->endSection() ?>

<?php $this->section('head_extra') ?>
<style>
    .login-bg {
        background: linear-gradient(135deg, <?= $e($sitePrimaryColor) ?>15 0%, <?= $e($sitePrimaryColor) ?>05 100%);
    }
</style>
<?php $this->endSection() ?>

<?php $this->section('content') ?>
<div class="min-h-[calc(100vh-12rem)] flex items-center justify-center login-bg">
    <div class="w-full max-w-md">
        <!-- 登录卡片 -->
        <div class="bg-white rounded-2xl shadow-xl p-8">
            <!-- Logo 和标题 -->
            <div class="text-center mb-8">
                <?php if (!empty($siteLogo)): ?>
                <img src="<?= $e($siteLogo) ?>" alt="<?= $e($siteName) ?>" class="h-12 mx-auto mb-4">
                <?php endif; ?>
                <h1 class="text-2xl font-bold text-gray-900"><?= $e($siteName) ?></h1>
                <?php if (!empty($siteWelcomeText)): ?>
                <p class="mt-2 text-sm text-gray-500"><?= $e($siteWelcomeText) ?></p>
                <?php endif; ?>
            </div>

            <?php if ($isDemoMode): ?>
            <div class="mb-4 rounded-lg bg-amber-50 p-3 flex items-center">
                <svg class="h-5 w-5 text-amber-400 mr-2 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"/></svg>
                <span class="text-sm text-amber-700">演示模式 - 数据为示例数据，修改不会保存</span>
            </div>
            <?php endif; ?>

            <!-- 错误提示 -->
            <?php if (!empty($error)): ?>
            <div class="mb-4 rounded-lg bg-red-50 p-3 flex items-center">
                <svg class="h-5 w-5 text-red-400 mr-2 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                <span class="text-sm text-red-700"><?= $e($error) ?></span>
            </div>
            <?php endif; ?>

            <!-- 登录表单 -->
            <form method="POST" action="/accounts/login" class="space-y-5">
                <input type="hidden" name="<?= CSRF_TOKEN_NAME ?>" value="<?= $e($csrfToken) ?>">
                <?php if (!empty($next)): ?>
                <input type="hidden" name="next" value="<?= $e($next) ?>">
                <?php endif; ?>

                <!-- 用户名 -->
                <div>
                    <label for="username" class="block text-sm font-medium text-gray-700 mb-1">用户名 / 邮箱</label>
                    <div class="relative">
                        <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                            <svg class="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/></svg>
                        </div>
                        <input type="text" id="username" name="username" required autocomplete="username"
                            class="block w-full pl-10 pr-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm placeholder-gray-400"
                            placeholder="请输入用户名或邮箱" value="<?= $e($oldUsername ?? '') ?>">
                    </div>
                </div>

                <!-- 密码 -->
                <div>
                    <label for="password" class="block text-sm font-medium text-gray-700 mb-1">密码</label>
                    <div class="relative">
                        <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                            <svg class="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/></svg>
                        </div>
                        <input type="password" id="password" name="password" required autocomplete="current-password"
                            class="block w-full pl-10 pr-10 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm placeholder-gray-400"
                            placeholder="请输入密码">
                        <button type="button" onclick="togglePassword()" class="absolute inset-y-0 right-0 pr-3 flex items-center">
                            <svg id="eye-icon" class="h-5 w-5 text-gray-400 hover:text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                        </button>
                    </div>
                </div>

                <!-- 记住我 & 忘记密码 -->
                <div class="flex items-center justify-between">
                    <label class="flex items-center">
                        <input type="checkbox" name="remember" value="1"
                            class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded">
                        <span class="ml-2 text-sm text-gray-600">记住我</span>
                    </label>
                    <a href="/accounts/forgot-password" class="text-sm text-blue-600 hover:text-blue-500">忘记密码？</a>
                </div>

                <!-- 验证码占位 -->
                <?php if ($captchaProvider !== 'none'): ?>
                <div id="captcha-container" class="space-y-2">
                    <label class="block text-sm font-medium text-gray-700 mb-1">验证码</label>
                    <div id="captcha-widget" class="min-h-[40px] bg-gray-50 rounded-lg border border-gray-200 flex items-center justify-center">
                        <span class="text-sm text-gray-400">验证码加载中...</span>
                    </div>
                </div>
                <?php endif; ?>

                <!-- 登录按钮 -->
                <button type="submit" class="w-full flex justify-center py-2.5 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition">
                    登录
                </button>
            </form>

            <!-- 注册链接 -->
            <?php if ($enableRegistration): ?>
            <div class="mt-6 text-center">
                <p class="text-sm text-gray-500">
                    还没有账号？
                    <a href="/accounts/register" class="font-medium text-blue-600 hover:text-blue-500">立即注册</a>
                </p>
            </div>
            <?php endif; ?>
        </div>
    </div>
</div>
<?php $this->endSection() ?>

<?php $this->section('scripts') ?>
<script>
function togglePassword() {
    const input = document.getElementById('password');
    input.type = input.type === 'password' ? 'text' : 'password';
}
</script>
<?php $this->endSection() ?>
