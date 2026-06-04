<?php

declare(strict_types=1);

namespace App\Service;

use RuntimeException;

/**
 * 网关服务 - RDP 隧道连接与 PAA 令牌签发
 *
 * PAA (Pre-Authenticated Access) 令牌用于通过网关建立 RDP 连接
 */
class GatewayService
{
    /** @var string PAA 令牌签名密钥 */
    private readonly string $signingKey;

    /** @var string 网关地址 */
    private readonly string $gatewayAddress;

    /** @var int 网关端口 */
    private readonly int $gatewayPort;

    /** @var string RDP 域名 */
    private readonly string $rdpDomain;

    public function __construct()
    {
        $this->signingKey = env('GATEWAY_PAA_TOKEN_SIGNING_KEY', 'change-me-32-chars-minimum!!');
        $this->gatewayAddress = env('GATEWAY_ADDRESS', 'rdp.2c2a.com');
        $this->gatewayPort = (int) env('GATEWAY_PORT', '443');
        $this->rdpDomain = env('RDP_DOMAIN', '2c2a.com');
    }

    /**
     * 签发 PAA (Pre-Authenticated Access) 令牌
     *
     * @param string $userEmail 用户邮箱
     * @param string $tunnelToken 隧道令牌
     * @param string $clientIp 客户端 IP
     * @param int $expiresIn 过期时间（秒），默认 600 秒（10 分钟）
     * @return string PAA 令牌
     */
    public function issuePaaToken(string $userEmail, string $tunnelToken, string $clientIp, int $expiresIn = 600): string
    {
        if (strlen($this->signingKey) < 32) {
            throw new RuntimeException('PAA 令牌签名密钥长度不足（至少 32 字符）');
        }

        $issuedAt = time();
        $expiresAt = $issuedAt + $expiresIn;

        // 令牌载荷
        $payload = [
            'email'       => $userEmail,
            'tunnel'      => $tunnelToken,
            'ip'          => $clientIp,
            'iat'         => $issuedAt,
            'exp'         => $expiresAt,
            'jti'         => bin2hex(random_bytes(8)), // 唯一标识
        ];

        // 编码载荷
        $payloadJson = json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        $payloadB64 = $this->base64UrlEncode($payloadJson);

        // 使用 HMAC-SHA256 签名
        $signature = hash_hmac('sha256', $payloadB64, $this->signingKey, true);
        $signatureB64 = $this->base64UrlEncode($signature);

        // 组合令牌: payload.signature
        return $payloadB64 . '.' . $signatureB64;
    }

    /**
     * 验证 PAA 令牌
     *
     * @param string $token PAA 令牌
     * @return array|null 验证成功返回载荷，失败返回 null
     */
    public function verifyPaaToken(string $token): ?array
    {
        $parts = explode('.', $token);
        if (count($parts) !== 2) {
            return null;
        }

        [$payloadB64, $signatureB64] = $parts;

        // 验证签名
        $expectedSignature = hash_hmac('sha256', $payloadB64, $this->signingKey, true);
        $actualSignature = $this->base64UrlDecode($signatureB64);

        if (!hash_equals($expectedSignature, $actualSignature)) {
            return null;
        }

        // 解码载荷
        $payloadJson = $this->base64UrlDecode($payloadB64);
        if ($payloadJson === false) {
            return null;
        }

        $payload = json_decode($payloadJson, true);
        if (!is_array($payload)) {
            return null;
        }

        // 检查过期时间
        if (isset($payload['exp']) && $payload['exp'] < time()) {
            return null;
        }

        return $payload;
    }

    /**
     * 生成 .rdp 文件内容
     *
     * @param string $gatewayAddress 网关地址
     * @param int $gatewayPort 网关端口
     * @param string $userEmail 用户邮箱
     * @param string $paaToken PAA 令牌
     * @return string .rdp 文件内容
     */
    public function generateRdpFile(string $gatewayAddress, int $gatewayPort, string $userEmail, string $paaToken): string
    {
        $gatewayUrl = "https://{$gatewayAddress}:{$gatewayPort}";
        $rdpDomain = $this->rdpDomain;

        $lines = [
            // 会话类型
            'full address:s:localhost',
            'alternate full address:s:' . $rdpDomain,

            // 网关设置
            'gatewayhostname:s:' . $gatewayUrl,
            'gatewaycredentialssource:i:5',
            'gatewayusagemethod:i:1',
            'gatewayprofileusagemethod:i:1',

            // 认证设置
            'username:s:' . $userEmail,
            'domain:s:' . $rdpDomain,

            // PAA 令牌通过 gatewayaccesstoken 传递
            'gatewayaccesstoken:s:' . $paaToken,

            // 显示设置
            'screen mode id:i:2',
            'use multimon:i:0',
            'desktopwidth:i:1920',
            'desktopheight:i:1080',
            'desktopsizeid:i:0',

            // 颜色深度
            'session bpp:i:32',

            // 连接设置
            'compression:i:1',
            'keyboardhook:i:2',
            'audiocapturemode:i:0',
            'videoplaybackmode:i:1',
            'connection type:i:7',
            'networkautodetect:i:1',
            'bandwidthautodetect:i:1',

            // 重定向设置
            'redirectclipboard:i:1',
            'redirectprinters:i:0',
            'redirectcomports:i:0',
            'redirectsmartcards:i:0',
            'redirectposdevices:i:0',
            'drivestoredirect:s:',
            'autoreconnection enabled:i:1',

            // 安全设置
            'prompt for credentials:i:0',
            'negotiate security layer:i:1',
            'remoteapplicationmode:i:0',
            'alternate shell:s:',
            'shell working directory:s:',

            // 性能设置
            'allow font smoothing:i:1',
            'allow desktop composition:i:1',
            'disable full window drag:i:0',
            'disable menu anims:i:0',
            'disable themes:i:0',
            'disable cursor setting:i:0',
            'bitmapcachepersistenable:i:1',

            // 音频设置
            'audiomode:i:0',

            // 窗口标题
            'winposstr:s:0,3,0,0,1920,1080',
        ];

        return implode("\n", $lines) . "\n";
    }

    /**
     * 生成 RDP 连接的完整流程
     *
     * @param string $userEmail 用户邮箱
     * @param string $tunnelToken 隧道令牌
     * @param string $clientIp 客户端 IP
     * @param int $expiresIn 令牌过期时间（秒）
     * @return array{token: string, rdp_file: string, gateway_address: string, gateway_port: int}
     */
    public function createRdpConnection(string $userEmail, string $tunnelToken, string $clientIp, int $expiresIn = 600): array
    {
        $paaToken = $this->issuePaaToken($userEmail, $tunnelToken, $clientIp, $expiresIn);
        $rdpFile = $this->generateRdpFile($this->gatewayAddress, $this->gatewayPort, $userEmail, $paaToken);

        return [
            'token'           => $paaToken,
            'rdp_file'        => $rdpFile,
            'gateway_address' => $this->gatewayAddress,
            'gateway_port'    => $this->gatewayPort,
        ];
    }

    /**
     * Base64 URL 安全编码
     */
    private function base64UrlEncode(string $data): string
    {
        return rtrim(strtr(base64_encode($data), '+/', '-_'), '=');
    }

    /**
     * Base64 URL 安全解码
     */
    private function base64UrlDecode(string $data): string|false
    {
        $padded = str_pad(strtr($data, '-_', '+/'), strlen($data) % 4, '=', STR_PAD_RIGHT);
        return base64_decode($padded, true);
    }
}
