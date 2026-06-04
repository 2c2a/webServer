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
use App\Model\SystemConfig;
use App\Service\TaskQueue;

/**
 * API 控制器 - 通用 API 端点
 */
class ApiController
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
     * 获取异步任务状态
     */
    public function taskStatus(string $taskId): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return $this->response->json(['error' => '未登录'], 401);
        }

        $taskQueue = new TaskQueue();
        $status = $taskQueue->getTaskStatus($taskId);

        if ($status === null) {
            return $this->response->json(['error' => '任务不存在'], 404);
        }

        return $this->response->json($status);
    }

    /**
     * 验证码验证
     */
    public function captchaValidate(): Response
    {
        $token = $this->request->input('token', '');
        $scene = $this->request->input('scene', '');

        $config = SystemConfig::getConfig();
        $captchaConfig = SystemConfig::getCaptchaConfig($config, $scene);

        if (!($captchaConfig['enabled'] ?? false)) {
            return $this->response->json([
                'success' => true,
                'message' => '验证码未启用',
            ]);
        }

        // 根据验证码提供商进行验证
        $provider = $captchaConfig['provider'] ?? 'none';
        $valid = false;

        if ($provider === 'recaptcha') {
            $valid = $this->validateRecaptcha($token);
        } elseif ($provider === 'hcaptcha') {
            $valid = $this->validateHcaptcha($token);
        } elseif ($provider === 'custom') {
            $valid = $this->validateCustomCaptcha($token);
        } else {
            $valid = !empty($token);
        }

        if ($valid) {
            // 生成一个已验证的令牌，供后续请求使用
            $verifiedToken = bin2hex(random_bytes(16));
            $this->cache->set('captcha_verified:' . $verifiedToken, '1', 600); // 10 分钟有效

            return $this->response->json([
                'success' => true,
                'message' => '验证成功',
                'captcha_token' => $verifiedToken,
            ]);
        }

        return $this->response->json([
            'success' => false,
            'message' => '验证码验证失败',
        ], 400);
    }

    /**
     * 健康检查端点
     */
    public function healthCheck(): Response
    {
        $checks = [
            'status'   => 'healthy',
            'timestamp' => date('c'),
            'checks'   => [],
        ];

        // 检查数据库连接
        try {
            $this->database->fetchColumn('SELECT 1');
            $checks['checks']['database'] = 'ok';
        } catch (\Throwable $e) {
            $checks['checks']['database'] = 'error: ' . $e->getMessage();
            $checks['status'] = 'unhealthy';
        }

        // 检查 Redis 连接
        try {
            $redis = $this->cache->getRedis();
            if ($redis !== null) {
                $redis->ping();
                $checks['checks']['redis'] = 'ok';
            } else {
                $checks['checks']['redis'] = 'not_configured';
            }
        } catch (\Throwable $e) {
            $checks['checks']['redis'] = 'error: ' . $e->getMessage();
            $checks['status'] = 'degraded';
        }

        $statusCode = $checks['status'] === 'healthy' ? 200 : ($checks['status'] === 'degraded' ? 200 : 503);

        return $this->response->json($checks, $statusCode);
    }

    /**
     * 验证 Google reCAPTCHA
     */
    private function validateRecaptcha(string $token): bool
    {
        $config = SystemConfig::getConfig();
        $secret = $config['recaptcha_secret_key'] ?? '';

        if (empty($secret) || empty($token)) {
            return false;
        }

        $ch = curl_init('https://www.google.com/recaptcha/api/siteverify');
        curl_setopt_array($ch, [
            CURLOPT_POST       => true,
            CURLOPT_POSTFIELDS => http_build_query([
                'secret'   => $secret,
                'response' => $token,
                'remoteip' => $this->request->ip(),
            ]),
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT        => 10,
        ]);

        $response = curl_exec($ch);
        curl_close($ch);

        if ($response === false) {
            return false;
        }

        $result = json_decode($response, true);

        return ($result['success'] ?? false) === true;
    }

    /**
     * 验证 hCaptcha
     */
    private function validateHcaptcha(string $token): bool
    {
        $config = SystemConfig::getConfig();
        $secret = $config['hcaptcha_secret_key'] ?? '';

        if (empty($secret) || empty($token)) {
            return false;
        }

        $ch = curl_init('https://api.hcaptcha.com/siteverify');
        curl_setopt_array($ch, [
            CURLOPT_POST       => true,
            CURLOPT_POSTFIELDS => http_build_query([
                'secret'   => $secret,
                'response' => $token,
                'remoteip' => $this->request->ip(),
            ]),
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT        => 10,
        ]);

        $response = curl_exec($ch);
        curl_close($ch);

        if ($response === false) {
            return false;
        }

        $result = json_decode($response, true);

        return ($result['success'] ?? false) === true;
    }

    /**
     * 验证自定义验证码
     */
    private function validateCustomCaptcha(string $token): bool
    {
        if (empty($token)) {
            return false;
        }

        // 从 Redis 中查找验证码令牌
        $data = $this->cache->get('captcha:' . $token);

        if ($data !== null) {
            $this->cache->delete('captcha:' . $token);
            return true;
        }

        return false;
    }
}
