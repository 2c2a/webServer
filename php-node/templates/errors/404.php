<?php
/**
 * @var string $siteName 站点名称
 * @var App\Core\Template $this
 */
$siteName = $siteName ?? APP_NAME;
?>
<!DOCTYPE html>
<html lang="zh-CN" class="h-full">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>404 - 页面未找到 - <?= $e($siteName) ?></title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="h-full bg-gray-50 flex items-center justify-center">
    <div class="text-center px-4">
        <h1 class="text-8xl font-extrabold text-gray-200 tracking-wider">404</h1>
        <div class="mt-4">
            <h2 class="text-2xl font-bold text-gray-900">页面未找到</h2>
            <p class="mt-2 text-gray-500">抱歉，您访问的页面不存在或已被移除。</p>
        </div>
        <div class="mt-8 flex items-center justify-center space-x-4">
            <a href="/" class="inline-flex items-center px-5 py-2.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition">
                <svg class="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"/></svg>
                返回首页
            </a>
            <button onclick="history.back()" class="inline-flex items-center px-5 py-2.5 text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 rounded-lg border border-gray-300 transition">
                返回上页
            </button>
        </div>
    </div>
</body>
</html>
