<?php
/**
 * @var array $user 当前用户数据
 * @var array $profile 用户资料
 * @var bool $isDemoMode 是否演示模式
 * @var string $error 错误信息
 * @var string $success 成功信息
 * @var App\Core\Template $this
 */
$this->extends('layouts/base');

$user = $user ?? [];
$profile = $profile ?? [];
$isDemoMode = $isDemoMode ?? DEMO_MODE;
$error = $error ?? '';
$success = $success ?? '';
$csrfToken = $csrfToken ?? '';
?>

<?php $this->section('title') ?>个人资料<?php $this->endSection() ?>

<?php $this->section('content') ?>
<div class="max-w-4xl mx-auto">
    <h1 class="text-2xl font-bold text-gray-900 mb-6">个人资料</h1>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <!-- 左侧：头像和基本信息 -->
        <div class="lg:col-span-1">
            <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <!-- 头像 -->
                <div class="text-center">
                    <?php
                    $avatar = $user['avatar'] ?? '';
                    $initial = mb_substr($user['username'] ?? 'U', 0, 1);
                    ?>
                    <?php if (!empty($avatar)): ?>
                    <img src="<?= $e($avatar) ?>" alt="头像" class="w-24 h-24 rounded-full mx-auto object-cover border-4 border-gray-100">
                    <?php else: ?>
                    <div class="w-24 h-24 rounded-full mx-auto bg-blue-600 text-white flex items-center justify-center text-3xl font-bold border-4 border-gray-100"><?= $e($initial) ?></div>
                    <?php endif; ?>

                    <h2 class="mt-4 text-lg font-semibold text-gray-900"><?= $e($user['username'] ?? '') ?></h2>
                    <p class="text-sm text-gray-500"><?= $e($user['email'] ?? '') ?></p>

                    <?php if (($user['role'] ?? '') === 'admin'): ?>
                    <span class="inline-flex items-center mt-2 px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">管理员</span>
                    <?php endif; ?>

                    <!-- 头像上传 -->
                    <?php if (!$isDemoMode): ?>
                    <form method="POST" action="/accounts/api/avatar" enctype="multipart/form-data" class="mt-4">
                        <input type="hidden" name="<?= CSRF_TOKEN_NAME ?>" value="<?= $e($csrfToken) ?>">
                        <label class="cursor-pointer inline-flex items-center px-3 py-1.5 text-sm font-medium text-blue-600 bg-blue-50 hover:bg-blue-100 rounded-lg border border-blue-200 transition">
                            <svg class="w-4 h-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
                            更换头像
                            <input type="file" name="avatar" accept="image/*" class="hidden" onchange="this.form.submit()">
                        </label>
                    </form>
                    <?php else: ?>
                    <p class="mt-2 text-xs text-amber-600">演示模式下无法更换头像</p>
                    <?php endif; ?>
                </div>

                <!-- 账户信息 -->
                <div class="mt-6 pt-6 border-t border-gray-100 space-y-3">
                    <div class="flex justify-between text-sm">
                        <span class="text-gray-500">注册时间</span>
                        <span class="text-gray-900"><?= $e($user['created_at'] ?? '-') ?></span>
                    </div>
                    <div class="flex justify-between text-sm">
                        <span class="text-gray-500">最后登录</span>
                        <span class="text-gray-900"><?= $e($user['last_login_ip'] ?? '-') ?></span>
                    </div>
                    <div class="flex justify-between text-sm">
                        <span class="text-gray-500">邮箱验证</span>
                        <?php if ($user['is_verified'] ?? false): ?>
                        <span class="text-green-600">已验证</span>
                        <?php else: ?>
                        <span class="text-amber-600">未验证</span>
                        <?php endif; ?>
                    </div>
                </div>
            </div>
        </div>

        <!-- 右侧：编辑表单 -->
        <div class="lg:col-span-2 space-y-6">
            <!-- 基本信息编辑 -->
            <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <h3 class="text-lg font-semibold text-gray-900 mb-4">基本信息</h3>

                <?php if (!empty($success)): ?>
                <div class="mb-4 rounded-lg bg-green-50 p-3 text-sm text-green-700"><?= $e($success) ?></div>
                <?php endif; ?>

                <?php if (!empty($error)): ?>
                <div class="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700"><?= $e($error) ?></div>
                <?php endif; ?>

                <form method="POST" action="/accounts/profile" class="space-y-4">
                    <input type="hidden" name="<?= CSRF_TOKEN_NAME ?>" value="<?= $e($csrfToken) ?>">

                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div>
                            <label for="nickname" class="block text-sm font-medium text-gray-700 mb-1">昵称</label>
                            <input type="text" id="nickname" name="nickname"
                                class="block w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                                value="<?= $e($profile['nickname'] ?? $user['first_name'] ?? '') ?>">
                        </div>
                        <div>
                            <label for="email" class="block text-sm font-medium text-gray-700 mb-1">邮箱</label>
                            <input type="email" id="email" name="email"
                                class="block w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                                value="<?= $e($user['email'] ?? '') ?>">
                        </div>
                    </div>

                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div>
                            <label for="phone" class="block text-sm font-medium text-gray-700 mb-1">手机号</label>
                            <input type="tel" id="phone" name="phone"
                                class="block w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                                value="<?= $e($user['phone'] ?? '') ?>">
                        </div>
                    </div>

                    <div>
                        <label for="bio" class="block text-sm font-medium text-gray-700 mb-1">个人简介</label>
                        <textarea id="bio" name="bio" rows="3"
                            class="block w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                            placeholder="介绍一下自己..."><?= $e($profile['bio'] ?? '') ?></textarea>
                    </div>

                    <div class="flex justify-end">
                        <button type="submit" class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500">
                            保存修改
                        </button>
                    </div>
                </form>
            </div>

            <!-- 修改密码 -->
            <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <h3 class="text-lg font-semibold text-gray-900 mb-4">修改密码</h3>

                <?php if ($isDemoMode): ?>
                <div class="rounded-lg bg-amber-50 p-3 text-sm text-amber-700">
                    <svg class="h-5 w-5 inline mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"/></svg>
                    演示模式下无法修改密码
                </div>
                <?php else: ?>
                <form method="POST" action="/accounts/api/password/change" class="space-y-4">
                    <input type="hidden" name="<?= CSRF_TOKEN_NAME ?>" value="<?= $e($csrfToken) ?>">

                    <div>
                        <label for="current_password" class="block text-sm font-medium text-gray-700 mb-1">当前密码</label>
                        <input type="password" id="current_password" name="current_password" required
                            class="block w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                            placeholder="请输入当前密码">
                    </div>

                    <div>
                        <label for="new_password" class="block text-sm font-medium text-gray-700 mb-1">新密码</label>
                        <input type="password" id="new_password" name="new_password" required minlength="8"
                            class="block w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                            placeholder="请输入新密码（至少8位）">
                    </div>

                    <div>
                        <label for="new_password_confirm" class="block text-sm font-medium text-gray-700 mb-1">确认新密码</label>
                        <input type="password" id="new_password_confirm" name="new_password_confirm" required
                            class="block w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                            placeholder="请再次输入新密码">
                    </div>

                    <div class="flex justify-end">
                        <button type="submit" class="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg transition focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500">
                            修改密码
                        </button>
                    </div>
                </form>
                <?php endif; ?>
            </div>
        </div>
    </div>
</div>
<?php $this->endSection() ?>
