(function () {
    function qs(sel) { return document.querySelector(sel); }
    function $all(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }

    var _countdownTimer = null;
    var _activeOverlay = null;
    var _activeCaptchaBox = null;

    function startCountdown(button, initialText) {
        if (_countdownTimer) clearInterval(_countdownTimer);
        var count = 60;
        var originalText = initialText || '获取验证码';
        button.disabled = true;
        button.textContent = originalText + ' (' + count + 's)';
        _countdownTimer = setInterval(function () {
            count--;
            button.textContent = originalText + ' (' + count + 's)';
            if (count <= 0) {
                clearInterval(_countdownTimer);
                _countdownTimer = null;
                button.disabled = false;
                button.textContent = originalText;
            }
        }, 1000);
    }

    function getGenerateUrl(captchaType) {
        var baseUrl = '/captcha/generate';
        if (captchaType && captchaType !== 'SLIDER') {
            return baseUrl + '?type=' + encodeURIComponent(captchaType);
        }
        return baseUrl;
    }

    function createModal() {
        if (_activeOverlay) return _activeOverlay.querySelector('#tianai-captcha-box');

        var overlay = document.createElement('div');
        overlay.id = 'tianai-captcha-overlay';
        overlay.style.cssText = 'position:fixed;inset:0;z-index:9998;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;';

        var captchaBox = document.createElement('div');
        captchaBox.id = 'tianai-captcha-box';
        captchaBox.style.cssText = 'position:relative;';

        overlay.appendChild(captchaBox);
        document.body.appendChild(overlay);

        _activeOverlay = overlay;
        _activeCaptchaBox = captchaBox;

        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) {
                destroyModal();
            }
        });

        return captchaBox;
    }

    function destroyModal() {
        if (_activeOverlay) {
            _activeOverlay.remove();
            _activeOverlay = null;
            _activeCaptchaBox = null;
        }
    }

    function showTianaiCaptcha(onSuccess, captchaType) {
        var captchaBox = createModal();

        var config = {
            requestCaptchaDataUrl: getGenerateUrl(captchaType),
            validCaptchaUrl: "/captcha/check",
            bindEl: "#tianai-captcha-box",
            validSuccess: function (res, c, tac) {
                var token = null;
                if (res && res.data && res.data.token) {
                    token = res.data.token;
                } else if (res && res.token) {
                    token = res.token;
                }
                tac.destroyWindow();
                destroyModal();
                if (onSuccess) onSuccess(token);
            },
            validFail: function (res, c, tac) {
                tac.reloadCaptcha();
            },
            btnCloseFun: function (el, tac) {
                tac.destroyWindow();
                destroyModal();
            }
        };
        var style = {};
        var tac = new window.TAC(config, style);
        tac.init();
    }

    function setTokenField(form, token) {
        var input = form.querySelector('input[name="captcha_token"]');
        if (!input) {
            input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'captcha_token';
            form.appendChild(input);
        }
        input.value = token || '';
    }

    function postEmailCode(email, token, button) {
        var isForgotPassword = window.location.pathname.includes('forgot-password');
        var endpoint = isForgotPassword ? '/accounts/email/send-forgot-password-code/' : '/accounts/email/send-code/';

        var formData = new FormData();
        formData.append('email', email);
        if (token) {
            formData.append('captcha_token', token);
        }

        fetch(endpoint, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]') ? document.querySelector('[name=csrfmiddlewaretoken]').value : ''
            },
            body: formData
        }).then(function (resp) {
            if (resp.ok) {
                alert('验证码已发送，请注意查收');
                if (button) startCountdown(button, '获取验证码');
            } else {
                if (button) {
                    button.disabled = false;
                    button.textContent = '获取验证码';
                }
                resp.json().then(function (j) { alert('发送失败：' + (j.message || JSON.stringify(j))); }).catch(function () { alert('发送失败'); });
            }
        }).catch(function (err) {
            console.error(err);
            if (button) {
                button.disabled = false;
                button.textContent = '获取验证码';
            }
            alert('网络错误');
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (window.CAPTCHA_PROVIDER !== 'tianai') return;

        var captchaType = window.CAPTCHA_TYPE || 'SLIDER';

        $all('[data-tianai-captcha-trigger]').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopImmediatePropagation();

                var form = btn.closest('form');
                showTianaiCaptcha(function (token) {
                    if (form) setTokenField(form, token);
                    var action = btn.dataset.action;
                    if (action === 'submit') {
                        form.submit();
                    }
                }, captchaType);
            });
        });

        $all('#get-email-code[data-tianai-email-trigger]').forEach(function (button) {
            var newBtn = button.cloneNode(true);
            button.parentNode.replaceChild(newBtn, button);

            newBtn.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopImmediatePropagation();
                if (this.disabled) return;

                var emailField = document.querySelector('input[type="email"]');
                if (!emailField || !emailField.value) {
                    alert('请先输入邮箱');
                    emailField && emailField.focus();
                    return;
                }

                var emailCaptchaType = window.CAPTCHA_TYPE_EMAIL || captchaType;
                showTianaiCaptcha(function (token) {
                    postEmailCode(emailField.value, token, newBtn);
                }, emailCaptchaType);
            });
        });

        $all('form').forEach(function (form) {
            var hasCaptchaTrigger = form.querySelector('[data-tianai-captcha-trigger]');
            if (!hasCaptchaTrigger) return;

            form.addEventListener('submit', function (e) {
                var tokenField = form.querySelector('input[name="captcha_token"]');
                if (!tokenField || !tokenField.value) {
                    if (window.CAPTCHA_PROVIDER === 'tianai') {
                        e.preventDefault();
                        showTianaiCaptcha(function (token) {
                            setTokenField(form, token);
                            form.submit();
                        }, captchaType);
                    }
                }
            });
        });
    });
})();
