<?php

declare(strict_types=1);

namespace App\Service;

/**
 * 邮件服务 - SMTP 发送
 */
class EmailService
{
    /**
     * 发送验证码邮件
     */
    public function sendVerificationCode(string $to, string $code, int $ttlMinutes = 5): bool
    {
        $subject = sprintf('[%s] 邮箱验证码', APP_NAME);
        $body = $this->renderCodeTemplate($code, $ttlMinutes);

        return $this->send($to, $subject, $body);
    }

    /**
     * 发送密码重置邮件
     */
    public function sendPasswordResetCode(string $to, string $code, int $ttlMinutes = 5): bool
    {
        $subject = sprintf('[%s] 密码重置验证码', APP_NAME);
        $body = $this->renderResetCodeTemplate($code, $ttlMinutes);

        return $this->send($to, $subject, $body);
    }

    /**
     * 发送邮件
     */
    public function send(string $to, string $subject, string $body, bool $isHtml = true): bool
    {
        if (empty(SMTP_HOST) || empty(SMTP_USER)) {
            // SMTP 未配置，记录日志
            $this->log("SMTP 未配置，跳过发送邮件到 {$to}: {$subject}");
            return false;
        }

        $headers = [];
        $headers[] = 'From: ' . $this->formatAddress(SMTP_FROM, SMTP_FROM_NAME);
        $headers[] = 'Reply-To: ' . $this->formatAddress(SMTP_FROM, SMTP_FROM_NAME);
        $headers[] = 'X-Mailer: PHP/' . PHP_VERSION;

        if ($isHtml) {
            $headers[] = 'MIME-Version: 1.0';
            $headers[] = 'Content-Type: text/html; charset=UTF-8';
        }

        // 使用 PHP mail() 函数或 SMTP 直连
        // 生产环境建议使用 phpmailer 等库，此处提供基础实现
        $sent = mail($to, $subject, $body, implode("\r\n", $headers));

        if (!$sent) {
            $this->log("邮件发送失败: {$to} - {$subject}");
        }

        return $sent;
    }

    /**
     * 通过 SMTP 直连发送邮件
     */
    public function sendSmtp(string $to, string $subject, string $body): bool
    {
        if (empty(SMTP_HOST)) {
            return false;
        }

        $socket = @fsockopen(
            SMTP_HOST,
            SMTP_PORT,
            $errno,
            $errstr,
            10
        );

        if (!$socket) {
            $this->log("SMTP 连接失败: {$errno} - {$errstr}");
            return false;
        }

        try {
            $this->smtpRead($socket);

            $this->smtpSend($socket, 'EHLO ' . gethostname());
            $this->smtpRead($socket);

            if (SMTP_ENCRYPTION === 'starttls') {
                $this->smtpSend($socket, 'STARTTLS');
                $this->smtpRead($socket);
                stream_socket_enable_crypto($socket, true, STREAM_CRYPTO_METHOD_TLS_CLIENT);
                $this->smtpSend($socket, 'EHLO ' . gethostname());
                $this->smtpRead($socket);
            }

            if (!empty(SMTP_USER) && !empty(SMTP_PASS)) {
                $this->smtpSend($socket, 'AUTH LOGIN');
                $this->smtpRead($socket);
                $this->smtpSend($socket, base64_encode(SMTP_USER));
                $this->smtpRead($socket);
                $this->smtpSend($socket, base64_encode(SMTP_PASS));
                $this->smtpRead($socket);
            }

            $this->smtpSend($socket, 'MAIL FROM: <' . SMTP_FROM . '>');
            $this->smtpRead($socket);
            $this->smtpSend($socket, 'RCPT TO: <' . $to . '>');
            $this->smtpRead($socket);
            $this->smtpSend($socket, 'DATA');
            $this->smtpRead($socket);

            $message = $this->buildMessage($to, $subject, $body);
            $this->smtpSend($socket, $message . "\r\n.");
            $this->smtpRead($socket);

            $this->smtpSend($socket, 'QUIT');

            return true;
        } finally {
            fclose($socket);
        }
    }

    /**
     * 构建邮件消息
     */
    private function buildMessage(string $to, string $subject, string $body): string
    {
        $boundary = md5((string) time());

        $headers = [];
        $headers[] = 'From: ' . $this->formatAddress(SMTP_FROM, SMTP_FROM_NAME);
        $headers[] = 'To: ' . $to;
        $headers[] = 'Subject: =?UTF-8?B?' . base64_encode($subject) . '?=';
        $headers[] = 'MIME-Version: 1.0';
        $headers[] = 'Content-Type: multipart/alternative; boundary="' . $boundary . '"';
        $headers[] = 'Date: ' . date('r');

        $message = implode("\r\n", $headers) . "\r\n\r\n";
        $message .= "--{$boundary}\r\n";
        $message .= "Content-Type: text/html; charset=UTF-8\r\n";
        $message .= "Content-Transfer-Encoding: base64\r\n\r\n";
        $message .= chunk_split(base64_encode($body)) . "\r\n";
        $message .= "--{$boundary}--";

        return $message;
    }

    private function smtpSend($socket, string $data): void
    {
        fwrite($socket, $data . "\r\n");
    }

    private function smtpRead($socket): string
    {
        $response = '';
        while ($line = fgets($socket, 515)) {
            $response .= $line;
            if (substr($line, 3, 1) === ' ') {
                break;
            }
        }
        return $response;
    }

    /**
     * 格式化邮件地址
     */
    private function formatAddress(string $email, string $name = ''): string
    {
        if ($name !== '') {
            return '=?UTF-8?B?' . base64_encode($name) . '?= <' . $email . '>';
        }
        return $email;
    }

    /**
     * 渲染验证码模板
     */
    private function renderCodeTemplate(string $code, int $ttlMinutes): string
    {
        return <<<HTML
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background: #f5f5f5; border-radius: 8px; padding: 30px; text-align: center;">
        <h2 style="color: #333;">邮箱验证码</h2>
        <p style="color: #666; font-size: 14px;">您正在进行邮箱验证，验证码为：</p>
        <div style="font-size: 32px; font-weight: bold; color: #1976d2; letter-spacing: 8px; margin: 20px 0;">
            {$code}
        </div>
        <p style="color: #999; font-size: 12px;">验证码有效期为 {$ttlMinutes} 分钟，请勿泄露给他人。</p>
    </div>
</body>
</html>
HTML;
    }

    /**
     * 渲染密码重置验证码模板
     */
    private function renderResetCodeTemplate(string $code, int $ttlMinutes): string
    {
        return <<<HTML
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background: #f5f5f5; border-radius: 8px; padding: 30px; text-align: center;">
        <h2 style="color: #333;">密码重置验证码</h2>
        <p style="color: #666; font-size: 14px;">您正在重置密码，验证码为：</p>
        <div style="font-size: 32px; font-weight: bold; color: #d32f2f; letter-spacing: 8px; margin: 20px 0;">
            {$code}
        </div>
        <p style="color: #999; font-size: 12px;">验证码有效期为 {$ttlMinutes} 分钟。如非本人操作，请忽略此邮件。</p>
    </div>
</body>
</html>
HTML;
    }

    /**
     * 记录日志
     */
    private function log(string $message): void
    {
        $logDir = LOG_PATH;
        if (!is_dir($logDir)) {
            @mkdir($logDir, 0755, true);
        }

        $logFile = $logDir . '/' . date('Y-m-d') . '.log';
        @file_put_contents(
            $logFile,
            sprintf("[%s] [Email] %s\n", date('Y-m-d H:i:s'), $message),
            FILE_APPEND | LOCK_EX
        );
    }
}
