(function () {
    function qs(sel) { return document.querySelector(sel); }
    var btn = qs('#get-email-code');
    if (!btn) return;

    var countdownTimers = {};

    function startCountdown(button, initialText) {
        var buttonId = button.id || 'unknown-button';
        if (countdownTimers[buttonId]) {
            clearInterval(countdownTimers[buttonId]);
        }
        var count = 60;
        var originalText = initialText || button.textContent || '获取验证码';
        button.disabled = true;
        button.textContent = originalText + ' (' + count + 's)';
        countdownTimers[buttonId] = setInterval(function () {
            count--;
            button.textContent = originalText + ' (' + count + 's)';
            if (count <= 0) {
                clearInterval(countdownTimers[buttonId]);
                delete countdownTimers[buttonId];
                button.disabled = false;
                button.textContent = originalText;
            }
        }, 1000);
    }

    btn.addEventListener('click', function (e) {
        e.preventDefault();
        var emailInput = document.querySelector('input[name="email"]') || document.querySelector('input[type="email"]');
        var email = emailInput && emailInput.value && emailInput.value.trim();
        if (!email) { alert('请先输入邮箱'); return; }

        var isForgotPassword = window.location.pathname.includes('forgot-password');
        var endpoint = isForgotPassword ? '/accounts/email/send-forgot-password-code/' : '/accounts/email/send-code/';
        var provider = window.CAPTCHA_PROVIDER || 'none';

        if (provider === 'tianai') {
            return;
        }

        function postCode(payload, buttonRef) {
            fetch(endpoint, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]') ? document.querySelector('[name=csrfmiddlewaretoken]').value : ''
                },
                body: payload
            }).then(function (resp) {
                if (resp.ok) {
                    alert('验证码已发送，请注意查收');
                    if (buttonRef) startCountdown(buttonRef, '获取验证码');
                } else {
                    if (buttonRef) {
                        buttonRef.disabled = false;
                        buttonRef.textContent = '获取验证码';
                    }
                    resp.json().then(function (j) { alert('发送失败：' + (j.message || JSON.stringify(j))); }).catch(function () { alert('发送失败'); });
                }
            }).catch(function (err) {
                console.error(err);
                if (buttonRef) {
                    buttonRef.disabled = false;
                    buttonRef.textContent = '获取验证码';
                }
                alert('网络错误');
            });
        }

        var fd = new FormData();
        fd.append('email', email);
        postCode(fd, btn);
    });
})();
