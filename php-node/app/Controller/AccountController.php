<?php

declare(strict_types=1);

namespace App\Controller;

use App\Core\Request;
use App\Core\Response;
use App\Core\Database;
use App\Core\Session;
use App\Core\Auth;
use App\Core\Cache;
use App\Core\Template;
use App\Core\Csrf;
use App\Core\RateLimit;
use App\Core\Validator;
use App\Model\User;
use App\Model\SystemConfig;
use App\Model\AuditLog;
use App\Service\EmailService;
use App\Service\CryptoService;

/**
 * 账号控制器 - 登录、注册、个人资料等
 */
class AccountController
{
    public function __construct(
        private Request $request,
        private Response $response,
        private Database $database,
        private Session $session,
        private Auth $auth,
        private Cache $cache,
        private Template $template,
        private Csrf $csrf
    ) {}

    /**
     * 显示登录表单
     */
    public function login(): Response
    {
        // 已登录用户重定向
        if ($this->auth->check()) {
            return redirect('/dashboard');
        }

        $config = SystemConfig::getConfig();
        $hostname = $this->request->server('HTTP_HOST', '');
        $siteName = SystemConfig::getSiteNameForHostname($config, $hostname);
        $branding = SystemConfig::getBrandingForHostname($config, $hostname);
        $captchaConfig = SystemConfig::getCaptchaConfig($config, 'login');

        $html = $this->template->render('accounts/login', [
            'siteName'      => $siteName,
            'branding'      => $branding,
            'captchaConfig' => $captchaConfig,
            'csrfToken'     => $this->csrf->token(),
            'error'         => $this->session->flash('error'),
            'old'           => $this->session->flash('old_input'),
            'enableRegistration' => $config['enable_registration'] ?? false,
        ]);

        return $this->response->html($html);
    }

    /**
     * 处理登录请求
     */
    public function loginPost(): Response
    {
        $username = trim($this->request->input('username', ''));
        $password = $this->request->input('password', '');
        $remember = (bool) $this->request->input('remember', false);
        $ip = $this->request->ip();

        // 频率限制
        $rateLimit = new RateLimit($this->cache);
        $key = 'login:' . $ip;

        if ($rateLimit->tooManyAttempts($key, RATE_LIMIT_LOGIN_MAX, RATE_LIMIT_LOGIN_DECAY)) {
            $seconds = $rateLimit->availableIn($key, RATE_LIMIT_LOGIN_MAX, RATE_LIMIT_LOGIN_DECAY);
            $this->session->flash('error', "登录尝试次数过多，请 {$seconds} 秒后再试");
            $this->session->flash('old_input', ['username' => $username]);
            return redirect('/login');
        }

        $rateLimit->hit($key, RATE_LIMIT_LOGIN_DECAY);

        // 验证输入
        $validator = new Validator($this->request->all());
        $validator->rule('required', ['username', 'password']);

        if (!$validator->validate()) {
            $this->session->flash('error', '请输入用户名和密码');
            $this->session->flash('old_input', ['username' => $username]);
            return redirect('/login');
        }

        // 验证码校验
        $config = SystemConfig::getConfig();
        $captchaConfig = SystemConfig::getCaptchaConfig($config, 'login');
        if ($captchaConfig['enabled']) {
            $captchaToken = $this->request->input('captcha_token', '');
            if (!$this->validateCaptcha($captchaToken, $captchaConfig)) {
                $this->session->flash('error', '验证码验证失败，请重试');
                $this->session->flash('old_input', ['username' => $username]);
                return redirect('/login');
            }
        }

        // 尝试验证
        $user = $this->auth->attempt($username, $password);

        if ($user === null) {
            $existingUser = User::findByUsername($username) ?? User::findByEmail($username);
            User::logLoginFailure($existingUser['id'] ?? null, $ip, '密码错误');
            AuditLog::log('login_failed', $existingUser['id'] ?? null, null, ['username' => $username], false);

            $this->session->flash('error', '用户名或密码错误');
            $this->session->flash('old_input', ['username' => $username]);
            return redirect('/login');
        }

        // 检查账号是否被禁用
        if (!($user['is_active'] ?? true)) {
            AuditLog::log('login_disabled', (int) $user['id'], null, ['username' => $username], false);
            $this->session->flash('error', '账号已被禁用，请联系管理员');
            return redirect('/login');
        }

        // 登录成功
        $this->auth->login($user);
        $rateLimit->clear($key);

        // 记住我
        if ($remember) {
            $this->setRememberCookie((int) $user['id']);
        }

        // 更新最后登录信息
        User::updateLastLogin((int) $user['id'], $ip);

        AuditLog::log('login_success', (int) $user['id'], null, ['username' => $username]);

        // 重定向到目标页面
        $redirectTo = $this->session->get('intended_url', '/dashboard');
        $this->session->delete('intended_url');

        return redirect($redirectTo);
    }

    /**
     * 显示注册表单
     */
    public function register(): Response
    {
        if ($this->auth->check()) {
            return redirect('/dashboard');
        }

        $config = SystemConfig::getConfig();

        if (!($config['enable_registration'] ?? false)) {
            $this->session->flash('error', '注册功能未开放');
            return redirect('/login');
        }

        $hostname = $this->request->server('HTTP_HOST', '');
        $siteName = SystemConfig::getSiteNameForHostname($config, $hostname);
        $captchaConfig = SystemConfig::getCaptchaConfig($config, 'register');

        $html = $this->template->render('accounts/register', [
            'siteName'      => $siteName,
            'captchaConfig' => $captchaConfig,
            'csrfToken'     => $this->csrf->token(),
            'error'         => $this->session->flash('error'),
            'old'           => $this->session->flash('old_input'),
        ]);

        return $this->response->html($html);
    }

    /**
     * 处理注册请求
     */
    public function registerPost(): Response
    {
        $config = SystemConfig::getConfig();

        if (!($config['enable_registration'] ?? false)) {
            $this->session->flash('error', '注册功能未开放');
            return redirect('/login');
        }

        $username = trim($this->request->input('username', ''));
        $email = trim($this->request->input('email', ''));
        $password = $this->request->input('password', '');
        $confirmPassword = $this->request->input('confirm_password', '');
        $emailCode = trim($this->request->input('email_code', ''));
        $firstName = trim($this->request->input('first_name', ''));
        $lastName = trim($this->request->input('last_name', ''));

        // 验证输入
        $validator = new Validator($this->request->all());
        $validator->rule('required', ['username', 'email', 'password', 'confirm_password', 'email_code']);
        $validator->rule('lengthMin', 'username', 3);
        $validator->rule('lengthMax', 'username', 50);
        $validator->rule('lengthMin', 'password', 8);
        $validator->rule('email', 'email');
        $validator->rule('equals', 'confirm_password', 'password');

        if (!$validator->validate()) {
            $this->session->flash('error', implode('; ', $validator->errors()));
            $this->session->flash('old_input', compact('username', 'email', 'first_name', 'lastName'));
            return redirect('/register');
        }

        // 验证码校验
        $captchaConfig = SystemConfig::getCaptchaConfig($config, 'register');
        if ($captchaConfig['enabled']) {
            $captchaToken = $this->request->input('captcha_token', '');
            if (!$this->validateCaptcha($captchaToken, $captchaConfig)) {
                $this->session->flash('error', '验证码验证失败');
                $this->session->flash('old_input', compact('username', 'email', 'first_name', 'lastName'));
                return redirect('/register');
            }
        }

        // 验证邮箱验证码
        if (!$this->verifyEmailCode($email, $emailCode, 'register')) {
            $this->session->flash('error', '邮箱验证码错误或已过期');
            $this->session->flash('old_input', compact('username', 'email', 'first_name', 'lastName'));
            return redirect('/register');
        }

        // 检查邮箱后缀
        if (!SystemConfig::isEmailSuffixAllowed($email)) {
            $this->session->flash('error', '该邮箱域名不在允许列表中');
            $this->session->flash('old_input', compact('username', 'email', 'first_name', 'lastName'));
            return redirect('/register');
        }

        // 检查用户名和邮箱唯一性
        if (User::findByUsername($username) !== null) {
            $this->session->flash('error', '用户名已存在');
            $this->session->flash('old_input', compact('email', 'first_name', 'lastName'));
            return redirect('/register');
        }

        if (User::findByEmail($email) !== null) {
            $this->session->flash('error', '邮箱已被注册');
            $this->session->flash('old_input', compact('username', 'first_name', 'lastName'));
            return redirect('/register');
        }

        // 创建用户
        $user = User::create([
            'username'    => $username,
            'password'    => $this->auth->hashPassword($password),
            'email'       => $email,
            'first_name'  => $firstName,
            'last_name'   => $lastName,
            'is_verified' => true,
        ]);

        // 清除验证码
        $this->clearEmailCode($email, 'register');

        AuditLog::log('user_registered', (int) $user['id'], null, ['username' => $username, 'email' => $email]);

        // 自动登录
        $this->auth->login($user);

        $this->session->flash('success', '注册成功，欢迎加入！');
        return redirect('/dashboard');
    }

    /**
     * 通过邀请链接注册 - 显示表单
     */
    public function registerByLink(string $token): Response
    {
        if ($this->auth->check()) {
            return redirect('/dashboard');
        }

        // 验证链接
        $link = $this->database->fetch(
            'SELECT * FROM registration_links WHERE token = :token AND is_active = true',
            [':token' => $token]
        );

        if ($link === null) {
            $this->session->flash('error', '注册链接无效或已过期');
            return redirect('/login');
        }

        // 检查过期
        if ($link['expires_at'] !== null && strtotime($link['expires_at']) < time()) {
            $this->session->flash('error', '注册链接已过期');
            return redirect('/login');
        }

        // 检查使用次数
        if ($link['max_uses'] > 0 && $link['used_count'] >= $link['max_uses']) {
            $this->session->flash('error', '注册链接已用完');
            return redirect('/login');
        }

        $config = SystemConfig::getConfig();
        $hostname = $this->request->server('HTTP_HOST', '');
        $siteName = SystemConfig::getSiteNameForHostname($config, $hostname);

        $html = $this->template->render('accounts/register_by_link', [
            'siteName'  => $siteName,
            'csrfToken' => $this->csrf->token(),
            'token'     => $token,
            'link'      => $link,
            'error'     => $this->session->flash('error'),
            'old'       => $this->session->flash('old_input'),
        ]);

        return $this->response->html($html);
    }

    /**
     * 通过邀请链接注册 - 处理提交
     */
    public function registerByLinkPost(string $token): Response
    {
        // 验证链接
        $link = $this->database->fetch(
            'SELECT * FROM registration_links WHERE token = :token AND is_active = true',
            [':token' => $token]
        );

        if ($link === null || ($link['expires_at'] !== null && strtotime($link['expires_at']) < time())) {
            $this->session->flash('error', '注册链接无效或已过期');
            return redirect('/login');
        }

        $username = trim($this->request->input('username', ''));
        $email = trim($this->request->input('email', ''));
        $password = $this->request->input('password', '');
        $confirmPassword = $this->request->input('confirm_password', '');
        $firstName = trim($this->request->input('first_name', ''));
        $lastName = trim($this->request->input('last_name', ''));

        // 验证输入
        $validator = new Validator($this->request->all());
        $validator->rule('required', ['username', 'email', 'password', 'confirm_password']);
        $validator->rule('lengthMin', 'username', 3);
        $validator->rule('lengthMin', 'password', 8);
        $validator->rule('email', 'email');
        $validator->rule('equals', 'confirm_password', 'password');

        if (!$validator->validate()) {
            $this->session->flash('error', implode('; ', $validator->errors()));
            $this->session->flash('old_input', compact('username', 'email', 'first_name', 'lastName'));
            return redirect('/register/' . $token);
        }

        // 检查唯一性
        if (User::findByUsername($username) !== null) {
            $this->session->flash('error', '用户名已存在');
            return redirect('/register/' . $token);
        }

        if (User::findByEmail($email) !== null) {
            $this->session->flash('error', '邮箱已被注册');
            return redirect('/register/' . $token);
        }

        // 创建用户
        $user = User::create([
            'username'    => $username,
            'password'    => $this->auth->hashPassword($password),
            'email'       => $email,
            'first_name'  => $firstName,
            'last_name'   => $lastName,
            'is_verified' => true,
        ]);

        // 将用户加入链接指定的组
        if (!empty($link['group_id'])) {
            User::addToGroup((int) $user['id'], (int) $link['group_id']);
            User::syncStaffStatus((int) $user['id']);
        }

        // 将用户加入站点组
        if (!empty($link['site_group_id'])) {
            User::addToSiteGroup((int) $user['id'], (int) $link['site_group_id']);
        }

        // 更新链接使用次数
        $this->database->query(
            'UPDATE registration_links SET used_count = used_count + 1 WHERE id = :id',
            [':id' => $link['id']]
        );

        AuditLog::log('user_registered_by_link', (int) $user['id'], null, [
            'username' => $username,
            'link_id'  => (int) $link['id'],
        ]);

        $this->auth->login($user);
        $this->session->flash('success', '注册成功！');
        return redirect('/dashboard');
    }

    /**
     * 显示个人资料表单
     */
    public function profile(): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return redirect('/login');
        }

        $html = $this->template->render('accounts/profile', [
            'user'      => $user,
            'csrfToken' => $this->csrf->token(),
            'error'     => $this->session->flash('error'),
            'success'   => $this->session->flash('success'),
        ]);

        return $this->response->html($html);
    }

    /**
     * 更新个人资料
     */
    public function profilePost(): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return redirect('/login');
        }

        $action = $this->request->input('action', 'update_profile');

        if ($action === 'change_password') {
            return $this->handlePasswordChange($user);
        }

        // 更新基本信息
        $firstName = trim($this->request->input('first_name', ''));
        $lastName = trim($this->request->input('last_name', ''));
        $phone = trim($this->request->input('phone', ''));
        $email = trim($this->request->input('email', ''));

        $validator = new Validator($this->request->all());
        $validator->rule('required', ['email']);
        $validator->rule('email', 'email');

        if (!$validator->validate()) {
            $this->session->flash('error', implode('; ', $validator->errors()));
            return redirect('/profile');
        }

        // 检查邮箱唯一性
        $existingUser = User::findByEmail($email);
        if ($existingUser !== null && (int) $existingUser['id'] !== (int) $user['id']) {
            $this->session->flash('error', '该邮箱已被其他用户使用');
            return redirect('/profile');
        }

        User::update((int) $user['id'], [
            'first_name' => $firstName,
            'last_name'  => $lastName,
            'phone'      => $phone,
            'email'      => $email,
        ]);

        AuditLog::log('profile_updated', (int) $user['id']);

        $this->session->flash('success', '个人资料已更新');
        return redirect('/profile');
    }

    /**
     * 处理密码修改
     */
    private function handlePasswordChange(array $user): Response
    {
        $currentPassword = $this->request->input('current_password', '');
        $newPassword = $this->request->input('new_password', '');
        $confirmPassword = $this->request->input('confirm_password', '');

        if (!$this->auth->verifyPassword($currentPassword, $user['password'])) {
            $this->session->flash('error', '当前密码错误');
            return redirect('/profile');
        }

        if (strlen($newPassword) < 8) {
            $this->session->flash('error', '新密码长度至少 8 位');
            return redirect('/profile');
        }

        if ($newPassword !== $confirmPassword) {
            $this->session->flash('error', '两次输入的新密码不一致');
            return redirect('/profile');
        }

        User::update((int) $user['id'], [
            'password' => $this->auth->hashPassword($newPassword),
        ]);

        AuditLog::log('password_changed', (int) $user['id']);

        $this->session->flash('success', '密码已修改');
        return redirect('/profile');
    }

    /**
     * 退出登录
     */
    public function logout(): Response
    {
        $userId = $this->auth->id();

        $this->auth->logout();

        // 清除记住我 Cookie
        if (isset($_COOKIE['remember_token'])) {
            setcookie('remember_token', '', time() - 3600, '/', '', true, true);
        }

        if ($userId !== null) {
            AuditLog::log('logout', $userId);
        }

        return redirect('/login');
    }

    /**
     * 发送注册邮箱验证码
     */
    public function sendEmailCode(): Response
    {
        $email = trim($this->request->input('email', ''));
        $ip = $this->request->ip();

        // 频率限制
        $rateLimit = new RateLimit($this->cache);
        $key = 'email_code:' . $ip;

        if ($rateLimit->tooManyAttempts($key, RATE_LIMIT_EMAIL_MAX, RATE_LIMIT_EMAIL_DECAY)) {
            $seconds = $rateLimit->availableIn($key, RATE_LIMIT_EMAIL_MAX, RATE_LIMIT_EMAIL_DECAY);
            return $this->response->json([
                'success' => false,
                'message' => "发送频率过高，请 {$seconds} 秒后再试",
            ], 429);
        }

        // 验证输入
        if (empty($email) || !filter_var($email, FILTER_VALIDATE_EMAIL)) {
            return $this->response->json([
                'success' => false,
                'message' => '请输入有效的邮箱地址',
            ], 400);
        }

        // 检查邮箱后缀
        if (!SystemConfig::isEmailSuffixAllowed($email)) {
            return $this->response->json([
                'success' => false,
                'message' => '该邮箱域名不在允许列表中',
            ], 400);
        }

        // 验证码校验
        $config = SystemConfig::getConfig();
        $captchaConfig = SystemConfig::getCaptchaConfig($config, 'email');
        if ($captchaConfig['enabled']) {
            $captchaToken = $this->request->input('captcha_token', '');
            if (!$this->validateCaptcha($captchaToken, $captchaConfig)) {
                return $this->response->json([
                    'success' => false,
                    'message' => '验证码验证失败',
                ], 400);
            }
        }

        // 检查邮箱是否已注册
        if (User::findByEmail($email) !== null) {
            return $this->response->json([
                'success' => false,
                'message' => '该邮箱已被注册',
            ], 400);
        }

        $rateLimit->hit($key, RATE_LIMIT_EMAIL_DECAY);

        // 生成验证码
        $code = CryptoService::generateCode(6);
        $cacheKey = 'email_code:register:' . md5($email);
        $this->cache->set($cacheKey, $code, 300); // 5 分钟有效

        // 发送邮件
        $emailService = new EmailService();
        $sent = $emailService->sendVerificationCode($email, $code, 5);

        if (!$sent) {
            return $this->response->json([
                'success' => false,
                'message' => '邮件发送失败，请稍后重试',
            ], 500);
        }

        return $this->response->json([
            'success' => true,
            'message' => '验证码已发送',
        ]);
    }

    /**
     * 显示忘记密码表单
     */
    public function forgotPassword(): Response
    {
        if ($this->auth->check()) {
            return redirect('/dashboard');
        }

        $config = SystemConfig::getConfig();
        $hostname = $this->request->server('HTTP_HOST', '');
        $siteName = SystemConfig::getSiteNameForHostname($config, $hostname);

        $html = $this->template->render('accounts/forgot_password', [
            'siteName'  => $siteName,
            'csrfToken' => $this->csrf->token(),
            'error'     => $this->session->flash('error'),
            'success'   => $this->session->flash('success'),
        ]);

        return $this->response->html($html);
    }

    /**
     * 处理忘记密码请求
     */
    public function forgotPasswordPost(): Response
    {
        $email = trim($this->request->input('email', ''));
        $emailCode = trim($this->request->input('email_code', ''));
        $newPassword = $this->request->input('new_password', '');
        $confirmPassword = $this->request->input('confirm_password', '');

        // 验证输入
        $validator = new Validator($this->request->all());
        $validator->rule('required', ['email', 'email_code', 'new_password', 'confirm_password']);
        $validator->rule('email', 'email');
        $validator->rule('lengthMin', 'new_password', 8);
        $validator->rule('equals', 'confirm_password', 'new_password');

        if (!$validator->validate()) {
            $this->session->flash('error', implode('; ', $validator->errors()));
            $this->session->flash('old_input', ['email' => $email]);
            return redirect('/forgot-password');
        }

        // 验证邮箱验证码
        if (!$this->verifyEmailCode($email, $emailCode, 'forgot')) {
            $this->session->flash('error', '验证码错误或已过期');
            $this->session->flash('old_input', ['email' => $email]);
            return redirect('/forgot-password');
        }

        // 查找用户
        $user = User::findByEmail($email);

        if ($user === null) {
            $this->session->flash('error', '该邮箱未注册');
            return redirect('/forgot-password');
        }

        // 重置密码
        User::update((int) $user['id'], [
            'password' => $this->auth->hashPassword($newPassword),
        ]);

        $this->clearEmailCode($email, 'forgot');

        AuditLog::log('password_reset', (int) $user['id'], null, ['email' => $email]);

        $this->session->flash('success', '密码已重置，请使用新密码登录');
        return redirect('/login');
    }

    /**
     * 发送密码重置验证码
     */
    public function sendForgotPasswordCode(): Response
    {
        $email = trim($this->request->input('email', ''));
        $ip = $this->request->ip();

        // 频率限制
        $rateLimit = new RateLimit($this->cache);
        $key = 'email_code:' . $ip;

        if ($rateLimit->tooManyAttempts($key, RATE_LIMIT_EMAIL_MAX, RATE_LIMIT_EMAIL_DECAY)) {
            $seconds = $rateLimit->availableIn($key, RATE_LIMIT_EMAIL_MAX, RATE_LIMIT_EMAIL_DECAY);
            return $this->response->json([
                'success' => false,
                'message' => "发送频率过高，请 {$seconds} 秒后再试",
            ], 429);
        }

        if (empty($email) || !filter_var($email, FILTER_VALIDATE_EMAIL)) {
            return $this->response->json([
                'success' => false,
                'message' => '请输入有效的邮箱地址',
            ], 400);
        }

        // 检查用户是否存在（不泄露信息，统一返回成功）
        $user = User::findByEmail($email);

        $rateLimit->hit($key, RATE_LIMIT_EMAIL_DECAY);

        if ($user !== null) {
            $code = CryptoService::generateCode(6);
            $cacheKey = 'email_code:forgot:' . md5($email);
            $this->cache->set($cacheKey, $code, 300);

            $emailService = new EmailService();
            $emailService->sendPasswordResetCode($email, $code, 5);
        }

        return $this->response->json([
            'success' => true,
            'message' => '如果该邮箱已注册，验证码已发送',
        ]);
    }

    /**
     * 上传头像
     */
    public function uploadAvatar(): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return $this->response->json(['success' => false, 'message' => '未登录'], 401);
        }

        $file = $this->request->file('avatar');

        if ($file === null || $file['error'] !== UPLOAD_ERR_OK) {
            return $this->response->json(['success' => false, 'message' => '请选择要上传的图片'], 400);
        }

        // 验证文件类型
        $allowedTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
        $finfo = finfo_open(FILEINFO_MIME_TYPE);
        $mimeType = finfo_file($finfo, $file['tmp_name']);
        finfo_close($finfo);

        if (!in_array($mimeType, $allowedTypes, true)) {
            return $this->response->json(['success' => false, 'message' => '仅支持 JPG、PNG、GIF、WebP 格式'], 400);
        }

        // 验证文件大小（最大 2MB）
        if ($file['size'] > 2 * 1024 * 1024) {
            return $this->response->json(['success' => false, 'message' => '图片大小不能超过 2MB'], 400);
        }

        // 保存文件
        $uploadDir = UPLOAD_PATH . '/avatars';
        if (!is_dir($uploadDir)) {
            mkdir($uploadDir, 0755, true);
        }

        $extension = pathinfo($file['name'], PATHINFO_EXTENSION) ?: 'jpg';
        $filename = $user['id'] . '_' . time() . '.' . $extension;
        $filepath = $uploadDir . '/' . $filename;

        if (!move_uploaded_file($file['tmp_name'], $filepath)) {
            return $this->response->json(['success' => false, 'message' => '上传失败'], 500);
        }

        // 更新用户头像
        $avatarUrl = '/uploads/avatars/' . $filename;
        User::update((int) $user['id'], ['avatar' => $avatarUrl]);

        AuditLog::log('avatar_uploaded', (int) $user['id']);

        return $this->response->json([
            'success' => true,
            'message' => '头像已更新',
            'avatar'  => $avatarUrl,
        ]);
    }

    /**
     * 修改密码 API
     */
    public function changePassword(): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return $this->response->json(['success' => false, 'message' => '未登录'], 401);
        }

        $currentPassword = $this->request->input('current_password', '');
        $newPassword = $this->request->input('new_password', '');

        if (!$this->auth->verifyPassword($currentPassword, $user['password'])) {
            return $this->response->json(['success' => false, 'message' => '当前密码错误'], 400);
        }

        if (strlen($newPassword) < 8) {
            return $this->response->json(['success' => false, 'message' => '新密码长度至少 8 位'], 400);
        }

        User::update((int) $user['id'], [
            'password' => $this->auth->hashPassword($newPassword),
        ]);

        AuditLog::log('password_changed_api', (int) $user['id']);

        return $this->response->json(['success' => true, 'message' => '密码已修改']);
    }

    /**
     * 验证邮箱验证码
     */
    private function verifyEmailCode(string $email, string $code, string $scene): bool
    {
        $cacheKey = "email_code:{$scene}:" . md5($email);
        $storedCode = $this->cache->get($cacheKey);

        if ($storedCode === null || $storedCode !== $code) {
            return false;
        }

        return true;
    }

    /**
     * 清除邮箱验证码
     */
    private function clearEmailCode(string $email, string $scene): void
    {
        $cacheKey = "email_code:{$scene}:" . md5($email);
        $this->cache->delete($cacheKey);
    }

    /**
     * 验证验证码
     */
    private function validateCaptcha(string $token, array $config): bool
    {
        if (!($config['enabled'] ?? false)) {
            return true;
        }

        // 根据验证码提供商验证
        $provider = $config['provider'] ?? 'none';

        if ($provider === 'none') {
            return true;
        }

        // 这里集成第三方验证码服务
        // 例如：Google reCAPTCHA, hCaptcha, 自建滑动验证码等
        // 目前返回 true 作为占位
        return !empty($token);
    }

    /**
     * 设置记住我 Cookie
     */
    private function setRememberCookie(int $userId): void
    {
        $token = bin2hex(random_bytes(32));
        $hash = hash('sha256', $token);

        // 存储到数据库
        $this->database->query(
            'INSERT INTO remember_tokens (user_id, token_hash, expires_at) VALUES (:user_id, :token_hash, :expires_at)',
            [
                ':user_id'    => $userId,
                ':token_hash' => $hash,
                ':expires_at' => date('c', time() + 30 * 86400), // 30 天
            ]
        );

        setcookie('remember_token', $userId . ':' . $token, time() + 30 * 86400, '/', '', true, true);
    }
}
