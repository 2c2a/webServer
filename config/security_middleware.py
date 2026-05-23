from django.conf import settings

class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if not settings.DEBUG:
            csp_parts = [
                "default-src 'self'",
                "script-src 'self' 'unsafe-inline' "
                "https://static.2c2a.cc.cd "
                "https://static.geetest.com https://static.geevisit.com "
                "https://gcaptcha4.geetest.com https://gcaptcha4.geevisit.com "
                "https://challenges.cloudflare.com",
                "style-src 'self' 'unsafe-inline' "
                "https://static.2c2a.cc.cd "
                "https://static.geetest.com https://static.geevisit.com",
                "img-src 'self' data: blob: "
                "https://static.2c2a.cc.cd "
                "https://static.geetest.com https://static.geevisit.com",
                "font-src 'self' "
                "https://static.2c2a.cc.cd "
                "https://static.geetest.com https://static.geevisit.com",
                "connect-src 'self' wss://rdp.2c2a.com ws://rdp.2c2a.com "
                "https://gcaptcha4.geetest.com https://gcaptcha4.geevisit.com "
                "https://challenges.cloudflare.com",
                "frame-src https://challenges.cloudflare.com",
                "frame-ancestors 'none'",
                "base-uri 'self'",
                "form-action 'self'",
            ]
            response['Content-Security-Policy'] = '; '.join(csp_parts)

            response['Permissions-Policy'] = (
                'geolocation=(), microphone=(), camera=(), '
                'payment=(), usb=(), magnetometer=(), gyroscope=(), '
                'accelerometer=()'
            )

        return response
