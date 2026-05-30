import logging
from typing import Tuple, Optional
from django.http import HttpRequest

logger = logging.getLogger(__name__)


class CaptchaValidationError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class CaptchaService:

    @staticmethod
    def validate_captcha(
        request: HttpRequest,
        scene: str,
        raise_exception: bool = False
    ) -> Tuple[bool, Optional[str]]:
        from apps.dashboard.models import SystemConfig

        provider = SystemConfig.get_config().get_captcha_config(scene=scene)

        try:
            if provider == 'tianai':
                return CaptchaService._validate_tianai(request)
            else:
                logger.debug(f"No captcha validation required for scene '{scene}', provider: {provider}")
                return True, None
        except CaptchaValidationError as e:
            if raise_exception:
                raise
            return False, e.message

    @staticmethod
    def _validate_tianai(request: HttpRequest) -> Tuple[bool, Optional[str]]:
        token = request.POST.get('captcha_token')

        if not token:
            logger.warning("Tianai captcha validation failed: missing token")
            raise CaptchaValidationError('请完成验证码验证')

        from django_tianai_captcha.conf import get_captcha_application
        app = get_captcha_application()

        is_valid = app.secondary_verification(token)

        if not is_valid:
            logger.warning("Tianai captcha secondary verification failed")
            raise CaptchaValidationError('验证码校验失败')

        logger.info("Tianai captcha validation succeeded")
        return True, None


def validate_captcha(request: HttpRequest, scene: str) -> Tuple[bool, Optional[str]]:
    return CaptchaService.validate_captcha(request, scene, raise_exception=False)
