<?php

declare(strict_types=1);

namespace App\Service;

/**
 * 加密服务 - AES-256-CBC 对称加密
 */
class CryptoService
{
    private string $key;

    private string $cipher = 'aes-256-cbc';

    public function __construct()
    {
        $key = APP_KEY;

        // 处理 base64: 前缀
        if (str_starts_with($key, 'base64:')) {
            $key = base64_decode(substr($key, 7));
        }

        // 确保密钥长度为 32 字节（AES-256）
        $this->key = hash('sha256', $key, true);
    }

    /**
     * 加密数据
     */
    public function encrypt(string $data): string
    {
        $ivLength = openssl_cipher_iv_length($this->cipher);
        $iv = openssl_random_pseudo_bytes($ivLength);

        $encrypted = openssl_encrypt($data, $this->cipher, $this->key, OPENSSL_RAW_DATA, $iv);

        if ($encrypted === false) {
            throw new \RuntimeException('加密失败');
        }

        // 格式: base64(iv + encrypted)
        return base64_encode($iv . $encrypted);
    }

    /**
     * 解密数据
     */
    public function decrypt(string $data): ?string
    {
        $decoded = base64_decode($data, true);

        if ($decoded === false) {
            return null;
        }

        $ivLength = openssl_cipher_iv_length($this->cipher);

        if (strlen($decoded) < $ivLength) {
            return null;
        }

        $iv = substr($decoded, 0, $ivLength);
        $encrypted = substr($decoded, $ivLength);

        $decrypted = openssl_decrypt($encrypted, $this->cipher, $this->key, OPENSSL_RAW_DATA, $iv);

        if ($decrypted === false) {
            return null;
        }

        return $decrypted;
    }

    /**
     * 生成随机令牌
     */
    public static function generateToken(int $length = 32): string
    {
        return bin2hex(random_bytes($length));
    }

    /**
     * 生成数字验证码
     */
    public static function generateCode(int $length = 6): string
    {
        $code = '';
        for ($i = 0; $i < $length; $i++) {
            $code .= random_int(0, 9);
        }
        return $code;
    }
}
