from django.conf import settings

class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if not settings.DEBUG:
            csp_parts = [
                "default-src 'self'",
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
                "https://static.2c2a.cc.cd",
                "style-src 'self' 'unsafe-inline' "
                "https://static.2c2a.cc.cd",
                "img-src 'self' data: blob: "
                "https://static.2c2a.cc.cd",
                "font-src 'self' "
                "https://static.2c2a.cc.cd",
                "connect-src 'self' wss://rdp.2c2a.com ws://rdp.2c2a.com",
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
