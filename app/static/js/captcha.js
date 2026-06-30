/* 2c2a 行为验证码前端组件
 *
 * 支持 7 种类型：slider / slider_image / rotate / text_click /
 * sequence_click / region_click / reasoning_click
 *
 * 用法：
 *   <div id="captcha-container"></div>
 *   <script src="/static/js/captcha.js"></script>
 *   <script>
 *     Captcha.mount('captcha-container', {
 *       type: 'slider_image',          // 可选，留空随机
 *       onSuccess: (captcha_id) => {...},
 *       onError: (msg) => {...}
 *     });
 *   </script>
 *
 * 也可直接通过 HTMX 加载 widget 片段：
 *   <div hx-get="/captcha/widget?target=captcha-container"
 *        hx-trigger="load" hx-target="this"></div>
 *   <script src="/static/js/captcha.js" defer></script>
 *   加载后会自动初始化页面中所有 [data-captcha-image] 元素
 */
(function () {
  'use strict';

  const API = {
    generate: '/captcha/generate',
    verify: '/captcha/verify',
    verifyFragment: '/captcha/verify-fragment',
    widget: '/captcha/widget',
  };

  // 注入全局样式（拼图块层 SVG 自适应填充）
  if (!document.getElementById('captcha-global-style')) {
    const style = document.createElement('style');
    style.id = 'captcha-global-style';
    style.textContent = [
      '.captcha-piece-layer > svg { width: 100% !important; height: 100% !important; display: block; }',
      '.captcha-image-inner > svg { width: 100% !important; height: 100% !important; display: block; }',
    ].join('\n');
    document.head.appendChild(style);
  }

  // ──────────────────────────────────────────────────────────
  // 工具函数
  // ──────────────────────────────────────────────────────────

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

  function svgToDataUri(svg) {
    return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
  }

  // 将内嵌 <svg> 元素替换为 <img> 以便点击 / 拖拽事件不被 SVG 子元素干扰
  // 关键：把 SVG 的 width/height 放大 2x（viewBox 不变），让浏览器以 2x
  // 分辨率光栅化为位图，CSS 再缩放到容器宽度，避免拉伸模糊。
  function freezeSvg(container) {
    const svgEl = container.querySelector('svg');
    if (!svgEl) return;
    const w = parseInt(svgEl.getAttribute('width') || '300', 10);
    const h = parseInt(svgEl.getAttribute('height') || '180', 10);
    // 确保 viewBox 存在（保证放大后内容不变）
    if (!svgEl.getAttribute('viewBox')) {
      svgEl.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    }
    // 2x 分辨率渲染
    const scale = 2;
    svgEl.setAttribute('width', String(w * scale));
    svgEl.setAttribute('height', String(h * scale));
    const src = svgToDataUri(svgEl.outerHTML);
    const img = document.createElement('img');
    img.src = src;
    img.style.width = '100%';
    img.style.height = '100%';
    img.style.display = 'block';
    img.style.userSelect = 'none';
    img.style.draggable = 'false';
    img.setAttribute('data-captcha-img', '1');
    // 关键：在 img 上也挂 _w/_h，否则 getRelativePoint 会 fallback 到
    // naturalWidth（已被放大到 2x），导致点击坐标被放大 2 倍 → 全部出界
    img._w = w;
    img._h = h;
    svgEl.replaceWith(img);
    container._img = img;
    container._w = w;
    container._h = h;
  }

  // 获取相对图片的坐标 (0~width, 0~height)
  function getRelativePoint(evt, img) {
    const rect = img.getBoundingClientRect();
    // SVG 用 viewBox 的 _w/_h；<img> 用 naturalWidth 映射回原始像素坐标
    const baseW = img._w || img.naturalWidth || rect.width;
    const baseH = img._h || img.naturalHeight || rect.height;
    const scaleX = baseW / rect.width;
    const scaleY = baseH / rect.height;
    return {
      x: (evt.clientX - rect.left) * scaleX,
      y: (evt.clientY - rect.top) * scaleY,
      px: evt.clientX - rect.left,
      py: evt.clientY - rect.top,
    };
  }

  // ──────────────────────────────────────────────────────────
  // 类型分发
  // ──────────────────────────────────────────────────────────

  const handlers = {
    slider: SliderHandler,
    slider_image: SliderHandler,
    rotate: RotateHandler,
    text_click: ClickHandler,
    sequence_click: ClickHandler,
    region_click: ClickHandler,
    reasoning_click: ClickHandler,
  };

  // ──────────────────────────────────────────────────────────
  // 滑块（slider / slider_image）
  // ──────────────────────────────────────────────────────────

  function SliderHandler(root) {
    const imgWrap = $('.captcha-image-wrapper', root);
    const track = $('.captcha-slider-track', root);
    const knob = $('.captcha-slider-knob', track);
    const progress = $('.captcha-slider-progress', track);
    const hintEl = $('.captcha-slider-hint', track);
    const answerInput = $('[data-captcha-answer-input]', root);
    const pieceLayer = $('[data-captcha-piece]', root);

    if (!knob) return;

    // 拼图块同步移动：把滑块位移按图片宽度比例映射为拼图块位移
    // pieceLayer 内部 SVG viewBox = challenge.width × challenge.height
    // ── 分段线性随机映射（反爬核心）──
    // f(0)=0, f(1)=1 端点固定，中间 N 段随机斜率。
    // 滑块比例 r ∈ [0,1] → 拼图块比例 f(r) ∈ [0,1] → SVG 位移 f(r) × full_travel
    // 攻击者无法用单一线性公式拟合，必须采样多个点重建映射。
    const imgWidth = pieceLayer
      ? parseInt(pieceLayer.getAttribute('data-captcha-width') || '320', 10)
      : 320;
    const pieceW = 50;  // 与后端 slider_image.py 一致
    const fullTravel = imgWidth - pieceW - 10;  // 拼图块满程 SVG 位移（piece_x0=10）
    let ys = [0, 1];
    if (pieceLayer) {
      try {
        ys = JSON.parse(pieceLayer.getAttribute('data-captcha-ys') || '[0,1]');
        if (!Array.isArray(ys) || ys.length < 2) ys = [0, 1];
      } catch (e) { ys = [0, 1]; }
    }

    // 分段线性插值：r ∈ [0,1] → f(r) ∈ [0,1]
    // x 等距分 N = ys.length - 1 段，段内线性
    function pieceRatio(r) {
      if (r <= 0) return 0;
      if (r >= 1) return 1;
      const n = ys.length - 1;
      let i = Math.floor(r * n);
      if (i >= n) i = n - 1;
      if (i < 0) i = 0;
      const x0 = i / n;
      const x1 = (i + 1) / n;
      const t = (r - x0) / (x1 - x0);
      return ys[i] + t * (ys[i + 1] - ys[i]);
    }

    let dragging = false;
    let startX = 0;
    let knobLeft = 0;
    const trackWidth = () => track.offsetWidth - knob.offsetWidth;
    const behavior = [];

    function syncPiece(knobLeftPx) {
      if (!pieceLayer) return;
      // 滑块比例 → 拼图块比例 → SVG 位移
      const r = trackWidth() > 0 ? knobLeftPx / trackWidth() : 0;
      const moveX = pieceRatio(r) * fullTravel;
      pieceLayer.style.transform = 'translateX(' + (moveX / imgWidth * 100) + '%)';
    }

    function onDown(evt) {
      dragging = true;
      startX = (evt.touches ? evt.touches[0].clientX : evt.clientX);
      knobLeft = knob.offsetLeft;
      knob.style.cursor = 'grabbing';
      hintEl.style.opacity = '0';
      evt.preventDefault();
    }

    function onMove(evt) {
      if (!dragging) return;
      const cx = evt.touches ? evt.touches[0].clientX : evt.clientX;
      const dx = cx - startX;
      let newLeft = knobLeft + dx;
      newLeft = Math.max(0, Math.min(trackWidth(), newLeft));
      knob.style.left = newLeft + 'px';
      progress.style.width = (newLeft + knob.offsetWidth / 2) + 'px';
      syncPiece(newLeft);
      behavior.push([newLeft, Date.now()]);
      if (behavior.length > 200) behavior.shift();
    }

    function onUp() {
      if (!dragging) return;
      dragging = false;
      knob.style.cursor = 'grab';
      const finalX = knob.offsetLeft;
      // 提交答案：
      // - slider 类型：x = 滑块像素位移（后端校验是否到达终点）
      // - slider_image 类型：滑块比例 → pieceRatio → SVG 拼图块 x
      //   拼图块初始 SVG x=0，位移 = pieceRatio(r) × fullTravel
      let x = finalX;
      if (pieceLayer) {
        const r = trackWidth() > 0 ? finalX / trackWidth() : 0;
        x = pieceRatio(r) * fullTravel;
      }
      const payload = { x: x, behavior: behavior };
      submit(root, payload);
    }

    knob.addEventListener('mousedown', onDown);
    knob.addEventListener('touchstart', onDown, { passive: false });
    document.addEventListener('mousemove', onMove);
    document.addEventListener('touchmove', onMove, { passive: false });
    document.addEventListener('mouseup', onUp);
    document.addEventListener('touchend', onUp);

    // 清理函数挂到 root 上
    root._cleanup = function () {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('touchmove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.removeEventListener('touchend', onUp);
    };
  }

  // ──────────────────────────────────────────────────────────
  // 旋转
  // ──────────────────────────────────────────────────────────

  function RotateHandler(root) {
    const imgInner = $('.captcha-image-inner', root);
    const rotateInnerLayer = $('[data-captcha-rotate-inner]', root);
    const track = $('.captcha-slider-track', root);
    const knob = $('.captcha-slider-knob', track);
    const progress = $('.captcha-slider-progress', track);
    const hintEl = $('.captcha-slider-hint', track);
    if (!knob) return;

    // 外圈 <img>（image-inner 中），内圈 <img>（rotate-inner layer 中）
    // freezeSvg 后这两个 <img> 分别挂在各自容器的 _img 上
    const outerImg = imgInner ? imgInner._img : null;
    const innerImg = rotateInnerLayer ? rotateInnerLayer._img : null;

    // 差速旋转：外圈 +angle，内圈 +2*angle
    // 后端持有 target_outer / target_inner，校验两圈标记是否同时归位
    let dragging = false;
    let startX = 0;
    let knobLeft = 0;
    const trackWidth = () => track.offsetWidth - knob.offsetWidth;

    function angleFromLeft(left) {
      return (left / trackWidth()) * 360;
    }

    function applyRotation(angle) {
      if (outerImg) outerImg.style.transform = 'rotate(' + angle + 'deg)';
      if (innerImg) innerImg.style.transform = 'rotate(' + (2 * angle) + 'deg)';
    }

    function onDown(evt) {
      dragging = true;
      startX = (evt.touches ? evt.touches[0].clientX : evt.clientX);
      knobLeft = knob.offsetLeft;
      knob.style.cursor = 'grabbing';
      hintEl.style.opacity = '0';
      evt.preventDefault();
    }

    function onMove(evt) {
      if (!dragging) return;
      const cx = evt.touches ? evt.touches[0].clientX : evt.clientX;
      const dx = cx - startX;
      let newLeft = knobLeft + dx;
      newLeft = Math.max(0, Math.min(trackWidth(), newLeft));
      knob.style.left = newLeft + 'px';
      progress.style.width = (newLeft + knob.offsetWidth / 2) + 'px';
      applyRotation(angleFromLeft(newLeft));
    }

    function onUp() {
      if (!dragging) return;
      dragging = false;
      knob.style.cursor = 'grab';
      const angle = angleFromLeft(knob.offsetLeft);
      submit(root, { angle: angle });
    }

    knob.addEventListener('mousedown', onDown);
    knob.addEventListener('touchstart', onDown, { passive: false });
    document.addEventListener('mousemove', onMove);
    document.addEventListener('touchmove', onMove, { passive: false });
    document.addEventListener('mouseup', onUp);
    document.addEventListener('touchend', onUp);

    root._cleanup = function () {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('touchmove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.removeEventListener('touchend', onUp);
    };
  }

  // ──────────────────────────────────────────────────────────
  // 点选
  // ──────────────────────────────────────────────────────────

  function ClickHandler(root) {
    const imgWrap = $('.captcha-image-wrapper', root);
    const img = imgWrap ? imgWrap.querySelector('img, svg') : null;
    const countEl = $('[data-captcha-click-count]', root);
    const answerInput = $('[data-captcha-answer-input]', root);
    const refreshBtn = $('[data-captcha-refresh]', root);
    if (!img) return;

    const points = [];
    // 预期点击次数：优先从后端 data-captcha-expected-clicks 读取
    // 后端未提供时（=0）按类型兜底：reasoning_click=1，其他=1
    let expectedCount = parseInt(root.getAttribute('data-captcha-expected-clicks') || '0', 10);
    if (!expectedCount || expectedCount < 1) {
      expectedCount = 1;
    }

    function onClick(evt) {
      const pt = getRelativePoint(evt, img);
      points.push([pt.x, pt.y]);
      if (countEl) countEl.textContent = points.length;
      // 在图片上叠加点击标记
      const marker = document.createElement('div');
      marker.className = 'captcha-click-marker';
      marker.style.cssText =
        'position:absolute;left:' + pt.px + 'px;top:' + pt.py + 'px;' +
        'width:20px;height:20px;margin-left:-10px;margin-top:-10px;' +
        'border-radius:50%;background:rgba(75,63,227,0.85);color:#fff;' +
        'font-size:11px;display:flex;align-items:center;justify-content:center;' +
        'font-weight:600;pointer-events:none;z-index:5;';
      marker.textContent = String(points.length);
      imgWrap.style.position = 'relative';
      imgWrap.appendChild(marker);

      if (points.length >= expectedCount) {
        submit(root, { points: points });
      }
    }

    img.addEventListener('click', onClick);

    if (refreshBtn) {
      refreshBtn.addEventListener('click', function () {
        reloadWidget(root);
      });
    }

    root._cleanup = function () {
      img.removeEventListener('click', onClick);
    };
  }

  // ──────────────────────────────────────────────────────────
  // HMAC-SHA256 签名（Web Crypto API）
  // ──────────────────────────────────────────────────────────

  // base64url → Uint8Array（还原后端下发的 sign_key）
  function b64urlToBytes(s) {
    const pad = '='.repeat((4 - s.length % 4) % 4);
    const b64 = (s + pad).replace(/-/g, '+').replace(/_/g, '/');
    const bin = atob(b64);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  // bytes → hex
  function bytesToHex(bytes) {
    let s = '';
    for (let i = 0; i < bytes.length; i++) {
      s += (bytes[i] < 16 ? '0' : '') + bytes[i].toString(16);
    }
    return s;
  }

  // 用 Web Crypto API 计算 HMAC-SHA256，返回 hex 字符串
  async function hmacSha256(keyBytes, msg) {
    const key = await crypto.subtle.importKey(
      'raw', keyBytes, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
    );
    const sig = await crypto.subtle.sign(
      'HMAC', key, new TextEncoder().encode(msg)
    );
    return bytesToHex(new Uint8Array(sig));
  }

  // ──────────────────────────────────────────────────────────
  // 提交答案
  // ──────────────────────────────────────────────────────────

  async function submit(root, payload) {
    const captchaId = root.getAttribute('data-captcha-id');
    if (!captchaId) return;
    // 防止重复提交（mouseup / touchend 可能同时触发）
    if (root._submitting) return;
    root._submitting = true;

    const answerInput = $('[data-captcha-answer-input]', root);
    if (answerInput) answerInput.value = JSON.stringify(payload);

    // 构造请求体（JSON 字符串必须与后端读取的原始 body 完全一致）
    const bodyObj = { captcha_id: captchaId, answer: payload };
    const bodyText = JSON.stringify(bodyObj);

    // 生成 HMAC-SHA256 签名
    const signKeyB64 = root.getAttribute('data-captcha-sign-key') || '';
    const headers = { 'Content-Type': 'application/json' };
    if (signKeyB64) {
      const ts = Math.floor(Date.now() / 1000);
      const msg = bodyText + '|' + ts;
      try {
        const sign = await hmacSha256(b64urlToBytes(signKeyB64), msg);
        headers['X-Captcha-Ts'] = String(ts);
        headers['X-Captcha-Sign'] = sign;
      } catch (e) {
        console.error('[captcha] HMAC sign failed:', e);
      }
    }

    try {
      const r = await fetch(API.verify, {
        method: 'POST',
        headers: headers,
        body: bodyText,
      });
      let data;
      if (!r.ok) {
        try {
          data = await r.json();
        } catch (_) {
          throw new Error('HTTP ' + r.status);
        }
        throw new Error(data.message || data.error || 'HTTP ' + r.status);
      }
      data = await r.json();
      root._submitting = false;
      if (data.success) {
        fire(root, 'captcha:success', { captcha_id: captchaId });
        showSuccess(root, data.message);
      } else {
        fire(root, 'captcha:error', { message: data.message });
        if (data.need_refresh) {
          reloadWidget(root);
        } else {
          showError(root, data.message);
          resetInteractions(root);
        }
      }
    } catch (e) {
      root._submitting = false;
      const msg = (e && e.message) ? e.message : '网络错误';
      console.error('[captcha] submit error:', e);
      fire(root, 'captcha:error', { message: msg });
      showError(root, msg);
    }
  }

  // ──────────────────────────────────────────────────────────
  // 状态切换
  // ──────────────────────────────────────────────────────────

  function showSuccess(root, msg) {
    // 简单地替换为成功状态显示
    let successHtml =
      '<div class="captcha-state captcha-state-success" ' +
      'style="display:flex;align-items:center;justify-content:center;gap:8px;' +
      'padding:12px;border:1px solid var(--c-success,#22c55e);' +
      'border-radius:8px;background:rgba(34,197,94,0.08);' +
      'color:var(--c-success,#22c55e);font-size:14px;">' +
      '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>' +
      '<span>' + (msg || '验证通过') + '</span></div>';
    // 保留隐藏字段
    const captchaId = root.getAttribute('data-captcha-id');
    successHtml +=
      '<input type="hidden" name="captcha_id" value="' + captchaId + '" data-captcha-id-input>' +
      '<input type="hidden" name="captcha" value="verified" data-captcha-answer-input>';
    root.innerHTML = successHtml;
  }

  function showError(root, msg) {
    let err = $('.captcha-error-overlay', root);
    if (!err) {
      const wrap = $('.captcha-image-wrapper', root);
      if (wrap) {
        err = document.createElement('div');
        err.className = 'captcha-error-overlay';
        err.style.cssText =
          'position:absolute;top:8px;left:8px;right:8px;' +
          'padding:6px 10px;background:rgba(255,71,87,0.95);color:#fff;' +
          'font-size:12px;border-radius:6px;text-align:center;pointer-events:none;';
        wrap.appendChild(err);
      }
    }
    if (err) {
      err.textContent = msg;
      err.style.display = 'block';
      setTimeout(function () { err.style.display = 'none'; }, 2000);
    }
  }

  function resetInteractions(root) {
    // 清除点击标记
    $all('.captcha-click-marker', root).forEach(function (m) { m.remove(); });
    // 重置滑块
    const knob = $('.captcha-slider-knob', root);
    const progress = $('.captcha-slider-progress', root);
    if (knob) knob.style.left = '0px';
    if (progress) progress.style.width = '0px';
    // 重置图片旋转（rotate 类型失败后外圈和内圈都要还原）
    const imgInner = $('.captcha-image-inner', root);
    if (imgInner && imgInner._img) imgInner._img.style.transform = '';
    const rotateInnerLayer = $('[data-captcha-rotate-inner]', root);
    if (rotateInnerLayer && rotateInnerLayer._img) {
      rotateInnerLayer._img.style.transform = '';
    }
    // 重置点击计数
    const countEl = $('[data-captcha-click-count]', root);
    if (countEl) countEl.textContent = '0';
    // 清除内部状态需要重建 handler
    if (root._cleanup) root._cleanup();
    initRoot(root);
  }

  // ──────────────────────────────────────────────────────────
  // 重新加载
  // ──────────────────────────────────────────────────────────

  function reloadWidget(root) {
    const target = root.getAttribute('data-target') || root.id;
    const type = root.getAttribute('data-captcha-type') || '';
    const url = API.widget + '?target=' + encodeURIComponent(target) +
                (type ? '&type=' + encodeURIComponent(type) : '');
    fetch(url, { headers: { 'HX-Request': 'true' } })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        // 创建临时容器解析 HTML
        const tmp = document.createElement('div');
        tmp.innerHTML = html;
        const newWidget = tmp.firstElementChild;
        if (newWidget) {
          if (root._cleanup) root._cleanup();
          root.replaceWith(newWidget);
          initRoot(newWidget);
        }
      });
  }

  // ──────────────────────────────────────────────────────────
  // 事件
  // ──────────────────────────────────────────────────────────

  function fire(root, name, detail) {
    root.dispatchEvent(new CustomEvent(name, { detail: detail, bubbles: true }));
  }

  // ──────────────────────────────────────────────────────────
  // 初始化
  // ──────────────────────────────────────────────────────────

  function initRoot(root) {
    const imgInner = $('.captcha-image-inner', root);
    if (imgInner && imgInner.querySelector('svg')) {
      // 把主图内嵌 SVG 替换为 <img>，便于点击 / 拖拽事件统一
      // 注意：只在 image-inner 上操作，不影响拼图块层
      freezeSvg(imgInner);
    }
    // rotate 类型的内圈层也需要转成 <img>，便于对其应用 CSS rotate
    const rotateInnerLayer = $('[data-captcha-rotate-inner]', root);
    if (rotateInnerLayer && rotateInnerLayer.querySelector('svg')) {
      freezeSvg(rotateInnerLayer);
    }
    const type = root.getAttribute('data-captcha-type');
    const handler = handlers[type];
    if (handler) handler(root);

    // 绑定"获取验证码"按钮（无题目状态）
    const loadBtn = $('[data-captcha-load]', root);
    if (loadBtn) {
      loadBtn.addEventListener('click', function () { reloadWidget(root); });
    }
  }

  function scan() {
    $all('[data-captcha-image]').forEach(function (el) {
      const root = el.closest('.captcha-widget');
      if (root && !root._init) {
        root._init = true;
        initRoot(root);
      }
    });
  }

  // ──────────────────────────────────────────────────────────
  // 弹出式模态框
  // ──────────────────────────────────────────────────────────

  // 全局唯一的 modal 实例（避免重复创建）
  let _modalInstance = null;

  function openModal(opts) {
    opts = opts || {};
    return new Promise(function (resolve, reject) {
      // 如果已有 modal 打开，先关闭
      if (_modalInstance) {
        closeModal();
      }

      // 创建遮罩层
      const overlay = document.createElement('div');
      overlay.className = 'captcha-modal-overlay';
      overlay.setAttribute('role', 'dialog');
      overlay.setAttribute('aria-modal', 'true');
      overlay.style.cssText = [
        'position:fixed', 'inset:0', 'z-index:9999',
        'display:flex', 'align-items:center', 'justify-content:center',
        'background:rgba(0,0,0,0.5)', 'backdrop-filter:blur(2px)',
        'padding:16px',
      ].join(';');

      // modal 容器
      const dialog = document.createElement('div');
      dialog.className = 'captcha-modal-dialog';
      dialog.style.cssText = [
        'position:relative', 'width:100%', 'max-width:380px',
        'background:#fff', 'border-radius:12px',
        'box-shadow:0 20px 60px rgba(0,0,0,0.3)',
        'padding:20px', 'max-height:90vh', 'overflow:auto',
      ].join(';');

      // 标题栏
      const header = document.createElement('div');
      header.style.cssText = 'display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;';
      const title = document.createElement('h3');
      title.textContent = opts.title || '安全验证';
      title.style.cssText = 'margin:0;font-size:16px;font-weight:600;color:#171717;';
      const closeBtn = document.createElement('button');
      closeBtn.type = 'button';
      closeBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>';
      closeBtn.style.cssText = 'background:none;border:none;cursor:pointer;padding:4px;color:#737373;display:flex;align-items:center;border-radius:4px;';
      closeBtn.onmouseenter = function () { this.style.color = '#171717'; this.style.background = '#f5f5f5'; };
      closeBtn.onmouseleave = function () { this.style.color = '#737373'; this.style.background = 'none'; };
      header.appendChild(title);
      header.appendChild(closeBtn);
      dialog.appendChild(header);

      // widget 容器
      const widgetWrap = document.createElement('div');
      widgetWrap.id = 'captcha-modal-container';
      widgetWrap.style.cssText = 'min-height:120px;';
      dialog.appendChild(widgetWrap);

      // 底部提示
      const tip = document.createElement('p');
      tip.textContent = '请完成验证后继续操作';
      tip.style.cssText = 'margin:12px 0 0;font-size:12px;color:#737373;text-align:center;';
      dialog.appendChild(tip);

      overlay.appendChild(dialog);
      document.body.appendChild(overlay);
      _modalInstance = { overlay: overlay, dialog: dialog, resolved: false };

      // 关闭函数
      function closeModal() {
        if (!_modalInstance) return;
        const inst = _modalInstance;
        _modalInstance = null;
        // 移除键盘监听
        document.removeEventListener('keydown', onKeydown);
        // 移除 DOM
        if (inst.overlay.parentNode) {
          inst.overlay.parentNode.removeChild(inst.overlay);
        }
      }

      function onKeydown(e) {
        if (e.key === 'Escape') {
          if (!_modalInstance || !_modalInstance.resolved) {
            closeModal();
            reject(new Error('用户取消验证'));
          }
        }
      }

      // 点击遮罩关闭
      overlay.addEventListener('click', function (e) {
        if (e.target === overlay) {
          if (!_modalInstance || !_modalInstance.resolved) {
            closeModal();
            reject(new Error('用户取消验证'));
          }
        }
      });
      closeBtn.addEventListener('click', function () {
        if (!_modalInstance || !_modalInstance.resolved) {
          closeModal();
          reject(new Error('用户取消验证'));
        }
      });
      document.addEventListener('keydown', onKeydown);

      // 挂载 widget
      const target = widgetWrap.id;
      const url = API.widget + '?target=' + encodeURIComponent(target) +
                  (opts.type ? '&type=' + encodeURIComponent(opts.type) : '');
      fetch(url, { headers: { 'HX-Request': 'true' } })
        .then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.text();
        })
        .then(function (html) {
          widgetWrap.innerHTML = html;
          const widget = widgetWrap.querySelector('.captcha-widget');
          if (widget) {
            initRoot(widget);
            // 监听成功事件
            widget.addEventListener('captcha:success', function (e) {
              if (_modalInstance) _modalInstance.resolved = true;
              const captchaId = e.detail.captcha_id;
              // 短暂展示成功状态后关闭
              setTimeout(function () {
                closeModal();
                resolve(captchaId);
              }, 600);
            });
          }
        })
        .catch(function (err) {
          closeModal();
          reject(err);
        });

      // 暴露关闭方法
      _modalInstance.close = closeModal;
    });
  }

  function closeModal() {
    if (_modalInstance && _modalInstance.close) {
      _modalInstance.close();
    }
  }

  // ──────────────────────────────────────────────────────────
  // 暴露 API
  // ──────────────────────────────────────────────────────────

  window.Captcha = {
    mount: function (selector, opts) {
      opts = opts || {};
      let container;
      if (typeof selector === 'string') {
        // 兼容裸 ID 与 CSS 选择器
        const sel = selector.match(/^[A-Za-z][\w-]*$/) ? '#' + selector : selector;
        container = document.querySelector(sel);
      } else {
        container = selector;
      }
      if (!container) {
        console.error('[captcha] mount failed: container not found for', selector);
        return;
      }
      const target = container.id || 'captcha-container';
      const url = API.widget + '?target=' + encodeURIComponent(target) +
                  (opts.type ? '&type=' + encodeURIComponent(opts.type) : '');
      fetch(url, { headers: { 'HX-Request': 'true' } })
        .then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.text();
        })
        .then(function (html) {
          container.innerHTML = html;
          const widget = container.querySelector('.captcha-widget');
          if (widget) {
            initRoot(widget);
            if (opts.onSuccess) {
              widget.addEventListener('captcha:success', function (e) {
                opts.onSuccess(e.detail.captcha_id);
              });
            }
            if (opts.onError) {
              widget.addEventListener('captcha:error', function (e) {
                opts.onError(e.detail.message);
              });
            }
          }
        })
        .catch(function (err) {
          console.error('[captcha] mount failed:', err);
        });
    },
    openModal: openModal,
    closeModal: closeModal,
    initRoot: initRoot,
    scan: scan,
  };

  // 自动扫描
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', scan);
  } else {
    scan();
  }

  // 监听 HTMX 加载完成事件
  document.addEventListener('htmx:afterSwap', scan);
})();
