<?php
/**
 * @var array $cloudComputers 云电脑列表（按产品分组）
 * @var array $products 产品列表（用于筛选）
 * @var string $searchQuery 搜索关键词
 * @var string $filterProduct 产品筛选
 * @var string $filterStatus 状态筛选
 * @var App\Core\Template $this
 */
$this->extends('layouts/base');

$cloudComputers = $cloudComputers ?? [];
$products = $products ?? [];
$searchQuery = $searchQuery ?? '';
$filterProduct = $filterProduct ?? '';
$filterStatus = $filterStatus ?? '';
$csrfToken = $csrfToken ?? '';
?>

<?php $this->section('title') ?>我的云电脑<?php $this->endSection() ?>

<?php $this->section('content') ?>
<div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <h1 class="text-2xl font-bold text-gray-900">我的云电脑</h1>
        <a href="/operations/account-openings/create"
            class="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition">
            <svg class="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
            申请开户
        </a>
    </div>

    <!-- 搜索和筛选 -->
    <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
        <form method="GET" action="/operations/my-cloud-computers" class="flex flex-col sm:flex-row gap-3">
            <div class="flex-1">
                <div class="relative">
                    <svg class="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
                    <input type="text" name="q" value="<?= $e($searchQuery) ?>"
                        class="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm placeholder-gray-400"
                        placeholder="搜索用户名、主机名...">
                </div>
            </div>
            <select name="product_id" class="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500">
                <option value="">全部产品</option>
                <?php foreach ($products as $product): ?>
                <option value="<?= (int) $product['id'] ?>" <?= $filterProduct == $product['id'] ? 'selected' : '' ?>><?= $e($product['name']) ?></option>
                <?php endforeach; ?>
            </select>
            <select name="status" class="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500">
                <option value="">全部状态</option>
                <option value="active" <?= $filterStatus === 'active' ? 'selected' : '' ?>>活跃</option>
                <option value="disabled" <?= $filterStatus === 'disabled' ? 'selected' : '' ?>>已禁用</option>
            </select>
            <button type="submit" class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition">
                筛选
            </button>
        </form>
    </div>

    <!-- 云电脑列表（按产品分组） -->
    <?php foreach ($cloudComputers as $groupName => $computers): ?>
    <div>
        <h2 class="text-lg font-semibold text-gray-900 mb-3"><?= $e($groupName) ?></h2>
        <div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
            <div class="overflow-x-auto">
                <table class="min-w-full divide-y divide-gray-200">
                    <thead class="bg-gray-50">
                        <tr>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">用户名</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">主机</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">状态</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">创建时间</th>
                            <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">操作</th>
                        </tr>
                    </thead>
                    <tbody class="bg-white divide-y divide-gray-200">
                        <?php foreach ($computers as $computer): ?>
                        <tr class="hover:bg-gray-50">
                            <td class="px-6 py-4 whitespace-nowrap">
                                <div class="text-sm font-medium text-gray-900"><?= $e($computer['username'] ?? '') ?></div>
                                <?php if (!empty($computer['full_name'])): ?>
                                <div class="text-xs text-gray-500"><?= $e($computer['full_name']) ?></div>
                                <?php endif; ?>
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap">
                                <div class="text-sm text-gray-900"><?= $e($computer['host_name'] ?? '') ?></div>
                                <div class="text-xs text-gray-500"><?= $e($computer['host_address'] ?? '') ?></div>
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap">
                                <?php
                                $ccStatus = $computer['status'] ?? 'active';
                                $ccStatusColors = [
                                    'active'   => 'bg-green-100 text-green-800',
                                    'disabled' => 'bg-red-100 text-red-800',
                                    'expired'  => 'bg-gray-100 text-gray-800',
                                ];
                                $ccStatusLabels = [
                                    'active'   => '活跃',
                                    'disabled' => '已禁用',
                                    'expired'  => '已过期',
                                ];
                                ?>
                                <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium <?= $ccStatusColors[$ccStatus] ?? 'bg-gray-100 text-gray-800' ?>">
                                    <?= $e($ccStatusLabels[$ccStatus] ?? $ccStatus) ?>
                                </span>
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                <?= $e($computer['created_at'] ?? '') ?>
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-right text-sm space-x-2">
                                <!-- 获取密码按钮 -->
                                <?php if (($computer['password_retrieved'] ?? false) === false && $ccStatus === 'active'): ?>
                                <button onclick="getPassword(<?= (int) ($computer['id'] ?? 0) ?>)"
                                    class="inline-flex items-center px-3 py-1 text-xs font-medium text-amber-600 bg-amber-50 hover:bg-amber-100 rounded-lg border border-amber-200 transition">
                                    <svg class="h-3.5 w-3.5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z"/></svg>
                                    获取密码
                                </button>
                                <?php elseif ($computer['password_retrieved'] ?? false): ?>
                                <span class="inline-flex items-center px-3 py-1 text-xs font-medium text-gray-400 bg-gray-50 rounded-lg border border-gray-200">
                                    密码已获取
                                </span>
                                <?php endif; ?>

                                <!-- RDP 连接按钮 -->
                                <?php if ($ccStatus === 'active'): ?>
                                <a href="/operations/api/rdp-connect/<?= (int) ($computer['id'] ?? 0) ?>"
                                    class="inline-flex items-center px-3 py-1 text-xs font-medium text-blue-600 bg-blue-50 hover:bg-blue-100 rounded-lg border border-blue-200 transition">
                                    <svg class="h-3.5 w-3.5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
                                    RDP 连接
                                </a>
                                <?php endif; ?>
                            </td>
                        </tr>
                        <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    <?php endforeach; ?>

    <?php if (empty($cloudComputers)): ?>
    <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center">
        <svg class="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
        <h3 class="mt-4 text-lg font-medium text-gray-900">暂无云电脑</h3>
        <p class="mt-2 text-sm text-gray-500">您还没有开通云电脑，请先申请开户</p>
        <a href="/operations/account-openings/create" class="mt-4 inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition">
            申请开户
        </a>
    </div>
    <?php endif; ?>
</div>
<?php $this->endSection() ?>

<?php $this->section('scripts') ?>
<script>
function getPassword(computerId) {
    if (!confirm('密码仅可获取一次，获取后将无法再次查看原始密码。确认获取？')) {
        return;
    }

    fetch('/operations/api/get-password/' + computerId, {
        method: 'POST',
        headers: {
            'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').content,
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/json'
        }
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            const password = data.password;
            const modal = document.createElement('div');
            modal.className = 'fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center z-50';
            modal.innerHTML = `
                <div class="bg-white rounded-xl shadow-xl p-6 max-w-md w-full mx-4">
                    <h3 class="text-lg font-semibold text-gray-900 mb-4">云电脑密码</h3>
                    <p class="text-sm text-gray-500 mb-3">请妥善保存此密码，关闭后将无法再次查看：</p>
                    <div class="bg-gray-50 rounded-lg p-3 font-mono text-sm select-all break-all">${password}</div>
                    <div class="mt-4 flex justify-end space-x-3">
                        <button onclick="navigator.clipboard.writeText('${password}');this.textContent='已复制'" class="px-4 py-2 text-sm font-medium text-blue-600 bg-blue-50 hover:bg-blue-100 rounded-lg border border-blue-200 transition">复制密码</button>
                        <button onclick="this.closest('.fixed').remove();location.reload()" class="px-4 py-2 text-sm font-medium text-white bg-gray-600 hover:bg-gray-700 rounded-lg transition">关闭</button>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        } else {
            alert(data.message || '获取密码失败');
        }
    })
    .catch(() => alert('请求失败，请稍后重试'));
}
</script>
<?php $this->endSection() ?>
