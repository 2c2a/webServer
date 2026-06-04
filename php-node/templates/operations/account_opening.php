<?php
/**
 * @var array $products 产品列表
 * @var array $productGroups 产品分组
 * @var int $selectedProductId 已选产品 ID
 * @var string $error 错误信息
 * @var bool $enableDiskQuota 是否启用磁盘配额
 * @var array $diskQuotaOptions 磁盘配额选项
 * @var array $registrationLinkToken 注册链接令牌（用于预填充）
 * @var App\Core\Template $this
 */
$this->extends('layouts/base');

$products = $products ?? [];
$productGroups = $productGroups ?? [];
$selectedProductId = $selectedProductId ?? 0;
$error = $error ?? '';
$enableDiskQuota = $enableDiskQuota ?? false;
$diskQuotaOptions = $diskQuotaOptions ?? [];
$csrfToken = $csrfToken ?? '';
?>

<?php $this->section('title') ?>申请开户<?php $this->endSection() ?>

<?php $this->section('content') ?>
<div class="max-w-2xl mx-auto">
    <h1 class="text-2xl font-bold text-gray-900 mb-6">申请开户</h1>

    <?php if (!empty($error)): ?>
    <div class="mb-4 rounded-lg bg-red-50 p-3 flex items-center">
        <svg class="h-5 w-5 text-red-400 mr-2 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
        <span class="text-sm text-red-700"><?= $e($error) ?></span>
    </div>
    <?php endif; ?>

    <!-- 进度时间线 -->
    <div class="mb-8">
        <div class="flex items-center justify-between">
            <div class="flex-1 text-center">
                <div class="w-8 h-8 mx-auto bg-blue-600 text-white rounded-full flex items-center justify-center text-sm font-medium" id="step-1-circle">1</div>
                <p class="mt-1 text-xs font-medium text-blue-600">填写信息</p>
            </div>
            <div class="flex-1 h-0.5 bg-gray-200" id="step-line-1"></div>
            <div class="flex-1 text-center">
                <div class="w-8 h-8 mx-auto bg-gray-200 text-gray-500 rounded-full flex items-center justify-center text-sm font-medium" id="step-2-circle">2</div>
                <p class="mt-1 text-xs font-medium text-gray-500">确认提交</p>
            </div>
            <div class="flex-1 h-0.5 bg-gray-200" id="step-line-2"></div>
            <div class="flex-1 text-center">
                <div class="w-8 h-8 mx-auto bg-gray-200 text-gray-500 rounded-full flex items-center justify-center text-sm font-medium" id="step-3-circle">3</div>
                <p class="mt-1 text-xs font-medium text-gray-500">等待审核</p>
            </div>
        </div>
    </div>

    <!-- 开户表单 -->
    <form method="POST" action="/operations/account-openings" id="opening-form" class="space-y-6">
        <input type="hidden" name="<?= CSRF_TOKEN_NAME ?>" value="<?= $e($csrfToken) ?>">

        <!-- 第一步：填写信息 -->
        <div id="form-step-1">
            <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-5">
                <h3 class="text-lg font-semibold text-gray-900">开户信息</h3>

                <!-- 产品选择 -->
                <div>
                    <label for="product_id" class="block text-sm font-medium text-gray-700 mb-1">选择产品 <span class="text-red-500">*</span></label>
                    <select id="product_id" name="product_id" required
                        class="block w-full px-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm">
                        <option value="">请选择产品</option>
                        <?php foreach ($productGroups as $group): ?>
                        <optgroup label="<?= $e($group['name'] ?? '') ?>">
                            <?php
                            $groupProducts = array_filter($products, fn($p) => ($p['product_group_id'] ?? null) == ($group['id'] ?? null));
                            ?>
                            <?php foreach ($groupProducts as $product): ?>
                            <?php
                            $isFull = ($product['status'] ?? '') === 'full';
                            $isInactive = ($product['status'] ?? '') === 'inactive';
                            ?>
                            <option value="<?= (int) $product['id'] ?>"
                                <?= $selectedProductId == $product['id'] ? 'selected' : '' ?>
                                <?= ($isFull || $isInactive) ? 'disabled' : '' ?>>
                                <?= $e($product['name']) ?>
                                <?php if ($isFull): ?>（已满）<?php endif; ?>
                                <?php if ($isInactive): ?>（停用）<?php endif; ?>
                            </option>
                            <?php endforeach; ?>
                        </optgroup>
                        <?php endforeach; ?>
                        <?php
                        $ungrouped = array_filter($products, fn($p) => empty($p['product_group_id']));
                        ?>
                        <?php foreach ($ungrouped as $product): ?>
                        <option value="<?= (int) $product['id'] ?>" <?= $selectedProductId == $product['id'] ? 'selected' : '' ?>>
                            <?= $e($product['name']) ?>
                        </option>
                        <?php endforeach; ?>
                    </select>
                </div>

                <!-- 用户名 -->
                <div>
                    <label for="username" class="block text-sm font-medium text-gray-700 mb-1">用户名 <span class="text-red-500">*</span></label>
                    <input type="text" id="username" name="username" required
                        class="block w-full px-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm placeholder-gray-400"
                        placeholder="请输入云电脑登录用户名" minlength="3" maxlength="20"
                        pattern="[a-zA-Z][a-zA-Z0-9_]{2,19}">
                    <p class="mt-1 text-xs text-gray-500">以字母开头，3-20位，仅支持字母、数字和下划线</p>
                </div>

                <!-- 姓名 -->
                <div>
                    <label for="full_name" class="block text-sm font-medium text-gray-700 mb-1">姓名 <span class="text-red-500">*</span></label>
                    <input type="text" id="full_name" name="full_name" required
                        class="block w-full px-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm placeholder-gray-400"
                        placeholder="请输入您的真实姓名">
                </div>

                <!-- 描述 -->
                <div>
                    <label for="description" class="block text-sm font-medium text-gray-700 mb-1">用途说明</label>
                    <textarea id="description" name="description" rows="3"
                        class="block w-full px-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm placeholder-gray-400"
                        placeholder="请简要描述使用用途（可选）"></textarea>
                </div>

                <!-- 磁盘配额 -->
                <?php if ($enableDiskQuota && !empty($diskQuotaOptions)): ?>
                <div>
                    <label for="disk_quota" class="block text-sm font-medium text-gray-700 mb-1">磁盘配额</label>
                    <select id="disk_quota" name="disk_quota"
                        class="block w-full px-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm">
                        <option value="">默认配额</option>
                        <?php foreach ($diskQuotaOptions as $quota): ?>
                        <option value="<?= $e($quota['value'] ?? '') ?>"><?= $e($quota['label'] ?? '') ?></option>
                        <?php endforeach; ?>
                    </select>
                </div>
                <?php endif; ?>
            </div>

            <!-- 下一步按钮 -->
            <div class="mt-6 flex justify-end">
                <button type="button" onclick="goToStep2()"
                    class="px-6 py-2.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500">
                    下一步：确认信息
                </button>
            </div>
        </div>

        <!-- 第二步：确认信息 -->
        <div id="form-step-2" class="hidden">
            <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <h3 class="text-lg font-semibold text-gray-900 mb-4">确认开户信息</h3>

                <div class="space-y-3">
                    <div class="flex justify-between py-2 border-b border-gray-100">
                        <span class="text-sm text-gray-500">产品</span>
                        <span class="text-sm font-medium text-gray-900" id="confirm-product">-</span>
                    </div>
                    <div class="flex justify-between py-2 border-b border-gray-100">
                        <span class="text-sm text-gray-500">用户名</span>
                        <span class="text-sm font-medium text-gray-900" id="confirm-username">-</span>
                    </div>
                    <div class="flex justify-between py-2 border-b border-gray-100">
                        <span class="text-sm text-gray-500">姓名</span>
                        <span class="text-sm font-medium text-gray-900" id="confirm-fullname">-</span>
                    </div>
                    <div class="flex justify-between py-2 border-b border-gray-100">
                        <span class="text-sm text-gray-500">用途说明</span>
                        <span class="text-sm font-medium text-gray-900" id="confirm-description">-</span>
                    </div>
                    <?php if ($enableDiskQuota): ?>
                    <div class="flex justify-between py-2 border-b border-gray-100">
                        <span class="text-sm text-gray-500">磁盘配额</span>
                        <span class="text-sm font-medium text-gray-900" id="confirm-quota">-</span>
                    </div>
                    <?php endif; ?>
                </div>

                <div class="mt-4 rounded-lg bg-blue-50 p-3">
                    <p class="text-sm text-blue-700">提交后，管理员将审核您的申请。审核通过后将自动创建云电脑账户。</p>
                </div>
            </div>

            <!-- 操作按钮 -->
            <div class="mt-6 flex justify-between">
                <button type="button" onclick="goToStep1()"
                    class="px-6 py-2.5 text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 rounded-lg border border-gray-300 transition">
                    上一步
                </button>
                <button type="submit"
                    class="px-6 py-2.5 text-sm font-medium text-white bg-green-600 hover:bg-green-700 rounded-lg transition focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500">
                    确认提交
                </button>
            </div>
        </div>
    </form>
</div>
<?php $this->endSection() ?>

<?php $this->section('scripts') ?>
<script>
function goToStep2() {
    const form = document.getElementById('opening-form');
    const productId = document.getElementById('product_id');
    const username = document.getElementById('username');
    const fullName = document.getElementById('full_name');

    // 验证必填字段
    if (!productId.value) {
        alert('请选择产品');
        productId.focus();
        return;
    }
    if (!username.value) {
        alert('请输入用户名');
        username.focus();
        return;
    }
    if (!fullName.value) {
        alert('请输入姓名');
        fullName.focus();
        return;
    }

    // 填充确认信息
    document.getElementById('confirm-product').textContent = productId.options[productId.selectedIndex].text;
    document.getElementById('confirm-username').textContent = username.value;
    document.getElementById('confirm-fullname').textContent = fullName.value;
    document.getElementById('confirm-description').textContent = document.getElementById('description').value || '无';

    const quotaEl = document.getElementById('disk_quota');
    if (quotaEl) {
        document.getElementById('confirm-quota').textContent = quotaEl.value
            ? quotaEl.options[quotaEl.selectedIndex].text
            : '默认配额';
    }

    // 切换步骤
    document.getElementById('form-step-1').classList.add('hidden');
    document.getElementById('form-step-2').classList.remove('hidden');

    // 更新进度条
    document.getElementById('step-1-circle').className = 'w-8 h-8 mx-auto bg-green-600 text-white rounded-full flex items-center justify-center text-sm font-medium';
    document.getElementById('step-line-1').className = 'flex-1 h-0.5 bg-green-600';
    document.getElementById('step-2-circle').className = 'w-8 h-8 mx-auto bg-blue-600 text-white rounded-full flex items-center justify-center text-sm font-medium';
}

function goToStep1() {
    document.getElementById('form-step-1').classList.remove('hidden');
    document.getElementById('form-step-2').classList.add('hidden');

    // 恢复进度条
    document.getElementById('step-1-circle').className = 'w-8 h-8 mx-auto bg-blue-600 text-white rounded-full flex items-center justify-center text-sm font-medium';
    document.getElementById('step-line-1').className = 'flex-1 h-0.5 bg-gray-200';
    document.getElementById('step-2-circle').className = 'w-8 h-8 mx-auto bg-gray-200 text-gray-500 rounded-full flex items-center justify-center text-sm font-medium';
}
</script>
<?php $this->endSection() ?>
