<?php
/**
 * @var string $siteName 站点名称
 * @var string $siteLogo 站点 Logo
 * @var string $sitePrimaryColor 主色调
 * @var string $error 错误信息
 * @var bool $enableRegistration 是否开放注册
 * @var string $registrationToken 注册链接令牌
 * @var string $captchaProvider 验证码提供商
 * @var string $emailSuffixWhitelist 邮箱后缀白名单
 * @var App\Core\Template $this
 */
$this->extends('layouts/base');

$siteName = $siteName ?? APP_NAME;
$siteLogo = $siteLogo ?? '';
$sitePrimaryColor = $sitePrimaryColor ?? '#3b82f6';
$error = $error ?? '';
$enableRegistration = $enableRegistration ?? false;
$registrationToken = $registrationToken ?? '';
$captchaProvider = $captchaProvider ?? 'none';
$emailSuffixWhitelist = $emailSuffixWhitelist ?? '';
$csrfToken = $csrfToken ?? '';
?>

<?php $this->section('title') ?>注册<?php $this->endSection() ?>

<?php $this->section('head_extra') ?>
<style>
    .register-bg {
        background: linear-gradient(135deg, <?= $e($sitePrimaryColor) ?>15 0%, <?= $e($sitePrimaryColor) ?>05 100%);
    }
</style>
<?php $this->endSection() ?>

<?php $this->section('content') ?>
<div class="min-h-[calc(100vh-12rem)] flex items-center justify-center register-bg">
    <div class="w-full max-w-md">
        <div class="bg-white rounded-2xl shadow-xl p-8">
            <!-- 标题 -->
            <div class="text-center mb-8">
                <?php if (!empty($siteLogo)): ?>
                <img src="<?= $e($siteLogo) ?>" alt="<?= $e($siteName) ?>" class="h-12 mx-auto mb-4">
                <?php endif; ?>
                <h1 class="text-2xl font-bold text-gray-900">创建账号</h1>
                <p class="mt-2 text-sm text-gray-500">注册一个新账号以使用 <?= $e($siteName) ?> 服务</p>
            </div>

            <?php if (!$enableRegistration && empty($registrationToken)): ?>
            <div class="rounded-lg bg-amber-50 p-4 text-center">
                <svg class="h-10 w-10 text-amber-400 mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"/></svg>
                <p class="text-sm text-amber-700">当前未开放公开注册，请使用邀请链接注册</p>
            </div>
            <?php else: ?>

            <!-- 错误提示 -->
            <?php if (!empty($error)): ?>
            <div class="mb-4 rounded-lg bg-red-50 p-3 flex items-center">
                <svg class="h-5 w-5 text-red-400 mr-2 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                <span class="text-sm text-red-700"><?= $e($error) ?></span>
            </div>
            <?php endif; ?>

            <!-- 注册表单 -->
            <form method="POST" action="<?= !empty($registrationToken) ? "/accounts/register/{$registrationToken}" : '/accounts/register' ?>" class="space-y-5">
                <input type="hidden" name="<?= CSRF_TOKEN_NAME ?>" value="<?= $e($csrfToken) ?>">

                <!-- 用户名 -->
                <div>
                    <label for="username" class="block text-sm font-medium text-gray-700 mb-1">用户名</label>
                    <input type="text" id="username" name="username" required autocomplete="username"
                        class="block w-full px-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm placeholder-gray-400"
                        placeholder="请输入用户名" value="<?= $e($oldUsername ?? '') ?>" minlength="3" maxlength="150">
                </div>

                <!-- 邮箱 -->
                <div>
                    <label for="email" class="block text-sm font-medium text-gray-700 mb-1">邮箱</label>
                    <input type="email" id="email" name="email" required autocomplete="email"
                        class="block w-full px-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm placeholder-gray-400"
                        placeholder="请输入邮箱地址" value="<?= $e($oldEmail ?? '') ?>">
                    <?php if (!empty($emailSuffixWhitelist)): ?>
                    <p class="mt-1 text-xs text-gray-500">仅支持: <?= $e($emailSuffixWhitelist) ?></p>
                    <?php endif; ?>
                </div>

                <!-- 邮箱验证码 -->
                <div>
                    <label for="email_code" class="block text-sm font-medium text-gray-700 mb-1">邮箱验证码</label>
                    <div class="flex space-x-2">
                        <input type="text" id="email_code" name="email_code" required
                            class="block flex-1 px-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm placeholder-gray-400"
                            placeholder="请输入验证码" maxlength="6">
                        <button type="button" onclick="sendEmailCode()" id="send-code-btn"
                            class="flex-shrink-0 px-4 py-2.5 text-sm font-medium text-blue-600 bg-blue-50 hover:bg-blue-100 rounded-lg border border-blue-200 transition whitespace-nowrap">
                            发送验证码
                        </button>
                    </div>
                </div>

                <!-- 密码 -->
                <div>
                    <label for="password" class="block text-sm font-medium text-gray-700 mb-1">密码</label>
                    <input type="password" id="password" name="password" required autocomplete="new-password"
                        class="block w-full px-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm placeholder-gray-400"
                        placeholder="请输入密码（至少8位）" minlength="8">
                </div>

                <!-- 确认密码 -->
                <div>
                    <label for="password_confirm" class="block text-sm font-medium text-gray-700 mb-1">确认密码</label>
                    <input type="password" id="password_confirm" name="password_confirm" required autocomplete="new-password"
                        class="block w-full px-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm placeholder-gray-400"
                        placeholder="请再次输入密码">
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

                <!-- 注册按钮 -->
                <button type="submit" class="w-full flex justify-center py-2.5 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition">
                    注册
                </button>
            </form>

            <!-- 登录链接 -->
            <div class="mt-6 text-center">
                <p class="text-sm text-gray-500">
                    已有账号？
                    <a href="/accounts/login" class="font-medium text-blue-600 hover:text-blue-500">立即登录</a>
                </p>
            </div>

            <?php endif; ?>
        </div>
    </div>
</div>
<?php $this->endSection() ?>

<?php $this->section('scripts') ?>
<script>
let codeCountdown = 0;

function sendEmailCode() {
    const email = document.getElementById('email').value;
    if (!email) {
        alert('请先输入邮箱地址');
        return;
    }

    const btn = document.getElementById('send-code-btn');
    btn.disabled = true;

    fetch('/accounts/email/send-code', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').content,
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: 'email=' + encodeURIComponent(email)
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            codeCountdown = 60;
            const timer = setInterval(() => {
                codeCountdown--;
                btn.textContent = codeCountdown > 0 ? codeCountdown + '秒后重试' : '发送验证码';
                btn.disabled = codeCountdown > 0;
                if (codeCountdown <= 0) clearInterval(timer);
            }, 1000);
        } else {
            alert(data.message || '发送失败');
            btn.disabled = false;
        }
    })
    .catch(() => {
        alert('发送失败，请稍后重试');
        btn.disabled = false;
    });
}
</script>
<?php $this->endSection() ?>
