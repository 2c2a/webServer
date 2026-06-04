<?php
/**
 * @var string $siteName 站点名称
 * @var string $siteIcon 站点图标
 * @var string $siteLogo 站点 Logo
 * @var string $sitePrimaryColor 主色调
 * @var string $siteCustomCss 自定义 CSS
 * @var array|null $user 当前用户
 * @var bool $isDemoMode 是否演示模式
 * @var string $icpNumber ICP 备案号
 * @var string $policeNumber 公安备案号
 * @var App\Core\Template $this 模板引擎实例
 */
$siteName = $siteName ?? APP_NAME;
$siteIcon = $siteIcon ?? '';
$siteLogo = $siteLogo ?? '';
$sitePrimaryColor = $sitePrimaryColor ?? '#3b82f6';
$siteCustomCss = $siteCustomCss ?? '';
$user = $user ?? null;
$isDemoMode = $isDemoMode ?? DEMO_MODE;
$icpNumber = $icpNumber ?? '';
$policeNumber = $policeNumber ?? '';
?>
<!DOCTYPE html>
<html lang="zh-CN" class="h-full">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="csrf-token" content="<?= $e($csrfToken ?? '') ?>">
    <meta name="color-scheme" content="light dark">
    <title><?= $this->yield('title', $siteName) ?> - <?= $e($siteName) ?></title>

    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        primary: {
                            50:  '<?= $sitePrimaryColor ?>1a',
                            100: '<?= $sitePrimaryColor ?>33',
                            200: '<?= $sitePrimaryColor ?>4d',
                            300: '<?= $sitePrimaryColor ?>66',
                            400: '<?= $sitePrimaryColor ?>80',
                            500: '<?= $sitePrimaryColor ?>',
                            600: '<?= $sitePrimaryColor ?>cc',
                            700: '<?= $sitePrimaryColor ?>99',
                            800: '<?= $sitePrimaryColor ?>66',
                            900: '<?= $sitePrimaryColor ?>33',
                        }
                    }
                }
            }
        }
    </script>

    <!-- 自定义主题 CSS -->
    <?php if (!empty($siteCustomCss)): ?>
    <style><?= $siteCustomCss ?></style>
    <?php endif; ?>

    <!-- 额外头部内容 -->
    <?= $this->yield('head_extra') ?>

    <style>
        [x-cloak] { display: none !important; }
    </style>
</head>
<body class="h-full bg-gray-50 text-gray-900 antialiased">

    <!-- 导航栏 -->
    <nav class="bg-white shadow-sm border-b border-gray-200">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex justify-between h-16">
                <!-- 左侧 Logo 和导航 -->
                <div class="flex">
                    <div class="flex-shrink-0 flex items-center">
                        <?php if (!empty($siteLogo)): ?>
                            <img class="h-8 w-auto" src="<?= $e($siteLogo) ?>" alt="<?= $e($siteName) ?>">
                        <?php elseif (!empty($siteIcon)): ?>
                            <img class="h-8 w-auto" src="<?= $e($siteIcon) ?>" alt="<?= $e($siteName) ?>">
                        <?php else: ?>
                            <span class="text-xl font-bold" style="color: <?= $e($sitePrimaryColor) ?>"><?= $e($siteName) ?></span>
                        <?php endif; ?>
                    </div>
                    <?php if ($user !== null): ?>
                    <div class="hidden sm:ml-8 sm:flex sm:space-x-4">
                        <a href="/" class="inline-flex items-center px-3 py-2 text-sm font-medium text-gray-700 hover:text-blue-600 hover:bg-gray-50 rounded-md transition">首页</a>
                        <a href="/operations/my-cloud-computers" class="inline-flex items-center px-3 py-2 text-sm font-medium text-gray-700 hover:text-blue-600 hover:bg-gray-50 rounded-md transition">我的云电脑</a>
                        <a href="/operations/account-openings/create" class="inline-flex items-center px-3 py-2 text-sm font-medium text-gray-700 hover:text-blue-600 hover:bg-gray-50 rounded-md transition">申请开户</a>
                        <a href="/tickets" class="inline-flex items-center px-3 py-2 text-sm font-medium text-gray-700 hover:text-blue-600 hover:bg-gray-50 rounded-md transition">工单</a>
                    </div>
                    <?php endif; ?>
                </div>

                <!-- 右侧用户菜单 -->
                <div class="flex items-center">
                    <?php if ($isDemoMode): ?>
                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800 mr-3">
                        演示模式
                    </span>
                    <?php endif; ?>

                    <?php if ($user !== null): ?>
                    <!-- 用户下拉菜单 -->
                    <div class="relative ml-3" id="user-menu-container">
                        <button type="button" class="flex items-center max-w-xs rounded-full bg-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2" id="user-menu-button" aria-expanded="false" aria-haspopup="true" onclick="toggleUserMenu()">
                            <span class="sr-only">打开用户菜单</span>
                            <?php
                            $avatar = $user['avatar'] ?? '';
                            $initial = mb_substr($user['username'] ?? 'U', 0, 1);
                            ?>
                            <?php if (!empty($avatar)): ?>
                                <img class="h-8 w-8 rounded-full object-cover" src="<?= $e($avatar) ?>" alt="<?= $e($user['username'] ?? '') ?>">
                            <?php else: ?>
                                <span class="h-8 w-8 rounded-full bg-blue-600 text-white flex items-center justify-center text-sm font-medium"><?= $e($initial) ?></span>
                            <?php endif; ?>
                            <span class="ml-2 text-gray-700 hidden sm:block"><?= $e($user['username'] ?? '') ?></span>
                            <svg class="ml-1 h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
                        </button>

                        <div id="user-menu" class="hidden absolute right-0 z-10 mt-2 w-48 origin-top-right rounded-md bg-white py-1 shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none" role="menu">
                            <a href="/accounts/profile" class="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100" role="menuitem">个人资料</a>
                            <?php if (($user['role'] ?? '') === 'admin'): ?>
                            <a href="/dashboard/sitegroup" class="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100" role="menuitem">系统管理</a>
                            <?php endif; ?>
                            <hr class="my-1">
                            <form method="POST" action="/accounts/logout" class="block">
                                <input type="hidden" name="<?= CSRF_TOKEN_NAME ?>" value="<?= $e($csrfToken ?? '') ?>">
                                <button type="submit" class="block w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-gray-100" role="menuitem">退出登录</button>
                            </form>
                        </div>
                    </div>
                    <?php else: ?>
                    <a href="/accounts/login" class="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition">
                        登录
                    </a>
                    <?php endif; ?>

                    <!-- 移动端菜单按钮 -->
                    <button type="button" class="ml-3 sm:hidden inline-flex items-center justify-center rounded-md p-2 text-gray-400 hover:text-gray-500 hover:bg-gray-100" onclick="toggleMobileMenu()">
                        <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/></svg>
                    </button>
                </div>
            </div>
        </div>

        <!-- 移动端菜单 -->
        <div id="mobile-menu" class="hidden sm:hidden border-t border-gray-200">
            <div class="pt-2 pb-3 space-y-1">
                <?php if ($user !== null): ?>
                <a href="/" class="block px-4 py-2 text-base font-medium text-gray-700 hover:text-blue-600 hover:bg-gray-50">首页</a>
                <a href="/operations/my-cloud-computers" class="block px-4 py-2 text-base font-medium text-gray-700 hover:text-blue-600 hover:bg-gray-50">我的云电脑</a>
                <a href="/operations/account-openings/create" class="block px-4 py-2 text-base font-medium text-gray-700 hover:text-blue-600 hover:bg-gray-50">申请开户</a>
                <a href="/tickets" class="block px-4 py-2 text-base font-medium text-gray-700 hover:text-blue-600 hover:bg-gray-50">工单</a>
                <?php endif; ?>
            </div>
        </div>
    </nav>

    <!-- Flash 消息 -->
    <?php
    $flashSuccess = $flashSuccess ?? '';
    $flashError = $flashError ?? '';
    $flashWarning = $flashWarning ?? '';
    $flashInfo = $flashInfo ?? '';
    ?>
    <?php if (!empty($flashSuccess)): ?>
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-4">
        <div class="rounded-md bg-green-50 p-4">
            <div class="flex">
                <svg class="h-5 w-5 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                <div class="ml-3"><p class="text-sm font-medium text-green-800"><?= $e($flashSuccess) ?></p></div>
                <div class="ml-auto pl-3"><button onclick="this.closest('.rounded-md').remove()" class="text-green-500 hover:text-green-700"><svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg></button></div>
            </div>
        </div>
    </div>
    <?php endif; ?>

    <?php if (!empty($flashError)): ?>
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-4">
        <div class="rounded-md bg-red-50 p-4">
            <div class="flex">
                <svg class="h-5 w-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                <div class="ml-3"><p class="text-sm font-medium text-red-800"><?= $e($flashError) ?></p></div>
                <div class="ml-auto pl-3"><button onclick="this.closest('.rounded-md').remove()" class="text-red-500 hover:text-red-700"><svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg></button></div>
            </div>
        </div>
    </div>
    <?php endif; ?>

    <?php if (!empty($flashWarning)): ?>
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-4">
        <div class="rounded-md bg-amber-50 p-4">
            <div class="flex">
                <svg class="h-5 w-5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"/></svg>
                <div class="ml-3"><p class="text-sm font-medium text-amber-800"><?= $e($flashWarning) ?></p></div>
                <div class="ml-auto pl-3"><button onclick="this.closest('.rounded-md').remove()" class="text-amber-500 hover:text-amber-700"><svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg></button></div>
            </div>
        </div>
    </div>
    <?php endif; ?>

    <?php if (!empty($flashInfo)): ?>
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-4">
        <div class="rounded-md bg-blue-50 p-4">
            <div class="flex">
                <svg class="h-5 w-5 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                <div class="ml-3"><p class="text-sm font-medium text-blue-800"><?= $e($flashInfo) ?></p></div>
                <div class="ml-auto pl-3"><button onclick="this.closest('.rounded-md').remove()" class="text-blue-500 hover:text-blue-700"><svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg></button></div>
            </div>
        </div>
    </div>
    <?php endif; ?>

    <!-- 主内容 -->
    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <?= $this->yield('content') ?>
    </main>

    <!-- 页脚 -->
    <footer class="bg-white border-t border-gray-200 mt-auto">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
            <div class="flex flex-col sm:flex-row justify-between items-center space-y-2 sm:space-y-0">
                <p class="text-sm text-gray-500">&copy; <?= date('Y') ?> <?= $e($siteName) ?>. All rights reserved.</p>
                <div class="flex items-center space-x-4 text-sm text-gray-400">
                    <?php if (!empty($icpNumber)): ?>
                    <a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer" class="hover:text-gray-500"><?= $e($icpNumber) ?></a>
                    <?php endif; ?>
                    <?php if (!empty($policeNumber)): ?>
                    <span class="hover:text-gray-500"><?= $e($policeNumber) ?></span>
                    <?php endif; ?>
                </div>
            </div>
        </div>
    </footer>

    <!-- JavaScript -->
    <script>
        // 用户菜单切换
        function toggleUserMenu() {
            const menu = document.getElementById('user-menu');
            menu.classList.toggle('hidden');
        }

        // 移动端菜单切换
        function toggleMobileMenu() {
            const menu = document.getElementById('mobile-menu');
            menu.classList.toggle('hidden');
        }

        // 点击外部关闭菜单
        document.addEventListener('click', function(e) {
            const container = document.getElementById('user-menu-container');
            const menu = document.getElementById('user-menu');
            if (container && menu && !container.contains(e.target)) {
                menu.classList.add('hidden');
            }
        });

        // CSRF Token 全局设置（用于 AJAX 请求）
        window.CSRF_TOKEN = '<?= $e($csrfToken ?? '') ?>';
        window.CSRF_TOKEN_NAME = '<?= CSRF_TOKEN_NAME ?>';
    </script>

    <!-- 额外脚本 -->
    <?= $this->yield('scripts') ?>
</body>
</html>
