<?php
/**
 * @var array $productGroups 产品分组
 * @var array $products 产品列表
 * @var array $stats 统计数据
 * @var array $recentRequests 最近请求（管理员）
 * @var bool $isAdmin 是否管理员
 * @var string $searchQuery 搜索关键词
 * @var App\Core\Template $this
 */
$this->extends('layouts/base');

$productGroups = $productGroups ?? [];
$products = $products ?? [];
$stats = $stats ?? ['pending_requests' => 0, 'cloud_users' => 0, 'active_hosts' => 0, 'total_products' => 0];
$recentRequests = $recentRequests ?? [];
$isAdmin = $isAdmin ?? false;
$searchQuery = $searchQuery ?? '';
$csrfToken = $csrfToken ?? '';
?>

<?php $this->section('title') ?>仪表盘<?php $this->endSection() ?>

<?php $this->section('content') ?>
<!-- 统计卡片 -->
<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
    <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
        <div class="flex items-center">
            <div class="flex-shrink-0 p-3 bg-amber-100 rounded-lg">
                <svg class="h-6 w-6 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            </div>
            <div class="ml-4">
                <p class="text-sm font-medium text-gray-500">待处理请求</p>
                <p class="text-2xl font-semibold text-gray-900"><?= (int) ($stats['pending_requests'] ?? 0) ?></p>
            </div>
        </div>
    </div>

    <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
        <div class="flex items-center">
            <div class="flex-shrink-0 p-3 bg-blue-100 rounded-lg">
                <svg class="h-6 w-6 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
            </div>
            <div class="ml-4">
                <p class="text-sm font-medium text-gray-500">云电脑用户</p>
                <p class="text-2xl font-semibold text-gray-900"><?= (int) ($stats['cloud_users'] ?? 0) ?></p>
            </div>
        </div>
    </div>

    <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
        <div class="flex items-center">
            <div class="flex-shrink-0 p-3 bg-green-100 rounded-lg">
                <svg class="h-6 w-6 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2"/></svg>
            </div>
            <div class="ml-4">
                <p class="text-sm font-medium text-gray-500">活跃主机</p>
                <p class="text-2xl font-semibold text-gray-900"><?= (int) ($stats['active_hosts'] ?? 0) ?></p>
            </div>
        </div>
    </div>

    <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
        <div class="flex items-center">
            <div class="flex-shrink-0 p-3 bg-purple-100 rounded-lg">
                <svg class="h-6 w-6 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/></svg>
            </div>
            <div class="ml-4">
                <p class="text-sm font-medium text-gray-500">产品总数</p>
                <p class="text-2xl font-semibold text-gray-900"><?= (int) ($stats['total_products'] ?? 0) ?></p>
            </div>
        </div>
    </div>
</div>

<!-- 搜索和筛选 -->
<div class="bg-white rounded-xl shadow-sm border border-gray-200 p-4 mb-6">
    <form method="GET" action="/" class="flex flex-col sm:flex-row gap-3">
        <div class="flex-1">
            <div class="relative">
                <svg class="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
                <input type="text" name="q" value="<?= $e($searchQuery) ?>"
                    class="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm placeholder-gray-400"
                    placeholder="搜索产品...">
            </div>
        </div>
        <button type="submit" class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition">
            搜索
        </button>
    </form>
</div>

<!-- 产品分组和产品列表 -->
<?php foreach ($productGroups as $group): ?>
<div class="mb-8">
    <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
        <?php if (!empty($group['icon'])): ?>
        <span class="mr-2"><?= $e($group['icon']) ?></span>
        <?php endif; ?>
        <?= $e($group['name'] ?? '未分组') ?>
        <?php if (!empty($group['description'])): ?>
        <span class="ml-2 text-sm font-normal text-gray-500"><?= $e($group['description']) ?></span>
        <?php endif; ?>
    </h2>

    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        <?php
        $groupProducts = array_filter($products, fn($p) => ($p['product_group_id'] ?? null) == ($group['id'] ?? null));
        ?>
        <?php foreach ($groupProducts as $product): ?>
        <div class="bg-white rounded-xl shadow-sm border border-gray-200 hover:shadow-md transition-shadow p-5">
            <div class="flex items-start justify-between">
                <div class="flex-1 min-w-0">
                    <h3 class="text-sm font-semibold text-gray-900 truncate"><?= $e($product['name'] ?? '') ?></h3>
                    <?php if (!empty($product['description'])): ?>
                    <p class="mt-1 text-xs text-gray-500 line-clamp-2"><?= $e($product['description']) ?></p>
                    <?php endif; ?>
                </div>
                <?php
                $status = $product['status'] ?? 'active';
                $statusColors = [
                    'active'   => 'bg-green-100 text-green-800',
                    'inactive' => 'bg-gray-100 text-gray-800',
                    'full'     => 'bg-red-100 text-red-800',
                ];
                $statusLabels = [
                    'active'   => '可用',
                    'inactive' => '停用',
                    'full'     => '已满',
                ];
                $statusClass = $statusColors[$status] ?? $statusColors['active'];
                $statusLabel = $statusLabels[$status] ?? $status;
                ?>
                <span class="ml-2 flex-shrink-0 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium <?= $statusClass ?>"><?= $e($statusLabel) ?></span>
            </div>

            <!-- 产品信息 -->
            <div class="mt-3 flex items-center text-xs text-gray-500 space-x-3">
                <?php if (isset($product['host_count'])): ?>
                <span class="flex items-center">
                    <svg class="h-3.5 w-3.5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2"/></svg>
                    <?= (int) $product['host_count'] ?> 台主机
                </span>
                <?php endif; ?>
                <?php if (isset($product['user_count'])): ?>
                <span class="flex items-center">
                    <svg class="h-3.5 w-3.5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"/></svg>
                    <?= (int) $product['user_count'] ?> 用户
                </span>
                <?php endif; ?>
            </div>

            <!-- 快捷操作 -->
            <div class="mt-4 flex space-x-2">
                <a href="/operations/account-openings/create?product_id=<?= (int) ($product['id'] ?? 0) ?>"
                    class="flex-1 text-center px-3 py-1.5 text-xs font-medium text-blue-600 bg-blue-50 hover:bg-blue-100 rounded-lg border border-blue-200 transition">
                    申请开户
                </a>
                <?php if ($status === 'active'): ?>
                <a href="/operations/my-cloud-computers?product_id=<?= (int) ($product['id'] ?? 0) ?>"
                    class="flex-1 text-center px-3 py-1.5 text-xs font-medium text-green-600 bg-green-50 hover:bg-green-100 rounded-lg border border-green-200 transition">
                    我的云电脑
                </a>
                <?php endif; ?>
            </div>
        </div>
        <?php endforeach; ?>

        <?php if (empty($groupProducts)): ?>
        <div class="bg-gray-50 rounded-xl border border-dashed border-gray-300 p-5 text-center">
            <p class="text-sm text-gray-400">暂无产品</p>
        </div>
        <?php endif; ?>
    </div>
</div>
<?php endforeach; ?>

<?php if (empty($productGroups)): ?>
<div class="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center">
    <svg class="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"/></svg>
    <h3 class="mt-4 text-lg font-medium text-gray-900">暂无可用产品</h3>
    <p class="mt-2 text-sm text-gray-500">请联系管理员添加产品</p>
</div>
<?php endif; ?>

<!-- 管理员：最近请求 -->
<?php if ($isAdmin && !empty($recentRequests)): ?>
<div class="mt-8">
    <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-gray-900">最近的开通请求</h2>
        <a href="/dashboard/sitegroup/requests" class="text-sm text-blue-600 hover:text-blue-500">查看全部</a>
    </div>

    <div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-gray-50">
                <tr>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">用户</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">产品</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">状态</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">时间</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">操作</th>
                </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-200">
                <?php foreach ($recentRequests as $req): ?>
                <tr class="hover:bg-gray-50">
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900"><?= $e($req['username'] ?? '') ?></td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500"><?= $e($req['product_name'] ?? '') ?></td>
                    <td class="px-6 py-4 whitespace-nowrap">
                        <?php
                        $reqStatus = $req['status'] ?? 'pending';
                        $reqStatusColors = [
                            'pending'  => 'bg-amber-100 text-amber-800',
                            'approved' => 'bg-green-100 text-green-800',
                            'rejected' => 'bg-red-100 text-red-800',
                            'processing' => 'bg-blue-100 text-blue-800',
                            'completed' => 'bg-gray-100 text-gray-800',
                        ];
                        $reqStatusLabels = [
                            'pending'    => '待审核',
                            'approved'   => '已批准',
                            'rejected'   => '已拒绝',
                            'processing' => '处理中',
                            'completed'  => '已完成',
                        ];
                        ?>
                        <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium <?= $reqStatusColors[$reqStatus] ?? 'bg-gray-100 text-gray-800' ?>"><?= $e($reqStatusLabels[$reqStatus] ?? $reqStatus) ?></span>
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500"><?= $e($req['created_at'] ?? '') ?></td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm">
                        <a href="/dashboard/sitegroup/requests/<?= (int) ($req['id'] ?? 0) ?>" class="text-blue-600 hover:text-blue-500">查看</a>
                    </td>
                </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
    </div>
</div>
<?php endif; ?>
<?php $this->endSection() ?>
