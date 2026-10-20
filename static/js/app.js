/* 习得 · 前端公共层 */
(function () {
  const ZX = window.ZX = {};

  ZX.escapeHtml = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  };

  ZX.api = async function (url, opts) {
    opts = opts || {};
    const headers = Object.assign({}, opts.headers || {});
    let body = opts.body;
    if (body && !(body instanceof FormData) && typeof body !== 'string') {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(body);
    }
    const res = await fetch(url, Object.assign({}, opts, { headers, body, credentials: 'same-origin' }));
    if (res.status === 401 && !location.pathname.startsWith('/login')) {
      location.href = '/login?next=' + encodeURIComponent(location.pathname + location.search);
      throw new Error('请先登录');
    }
    let data = null;
    try { data = await res.json(); } catch (e) { data = { ok: res.ok }; }
    if (!res.ok || data.ok === false) {
      throw new Error((data && data.error) || ('请求失败（' + res.status + '）'));
    }
    return data;
  };

  ZX.toast = function (msg, type) {
    const wrap = document.getElementById('toastWrap');
    if (!wrap) return;
    const el = document.createElement('div');
    el.className = 'toast ' + (type || '');
    el.textContent = msg;
    wrap.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = '.25s'; }, 2600);
    setTimeout(() => el.remove(), 3000);
  };

  ZX.openModal = function (html, cls) {
    const root = document.getElementById('modalRoot');
    root.innerHTML = '<div class="modal-mask" data-close></div><div class="modal ' + (cls || '') + '">' + html + '</div>';
    root.classList.add('open');
    root.querySelectorAll('[data-close]').forEach(x => x.addEventListener('click', ZX.closeModal));
    document.addEventListener('keydown', ZX._esc);
    return root;
  };
  ZX.closeModal = function () {
    const root = document.getElementById('modalRoot');
    root.classList.remove('open');
    root.innerHTML = '';
    document.removeEventListener('keydown', ZX._esc);
  };
  ZX._esc = function (e) { if (e.key === 'Escape') ZX.closeModal(); };

  ZX.fmtDate = function (s) {
    if (!s) return '—';
    return String(s).replace('T', ' ').slice(0, 16);
  };
  ZX.fmtDuration = function (sec) {
    sec = Math.max(0, Math.round(Number(sec) || 0));
    const m = Math.floor(sec / 60), s = sec % 60;
    return m + ':' + String(s).padStart(2, '0');
  };
  ZX.fmtMinutes = function (min) {
    min = Math.max(0, Math.round(Number(min) || 0));
    if (min < 60) return min + ' 分钟';
    return Math.floor(min / 60) + ' 小时' + (min % 60 ? ' ' + (min % 60) + ' 分' : '');
  };
  ZX.statusBadge = function (status) {
    const map = {
      free: ['green', '空闲'], booked: ['amber', '已预约'], using: ['red', '使用中'],
      occupied: ['amber', '临时占用'], maintenance: ['gray', '维护中'],
      booked_r: ['amber', '已预约'], checked_in: ['red', '学习中'], completed: ['gray', '已完成'],
      no_show: ['gray', '爽约'], cancelled: ['gray', '已取消'],
      pending_review: ['amber', '待审核'], approved: ['green', '已入池'], rejected: ['red', '未通过'],
      processing: ['blue', '处理中'],
    };
    const x = map[status] || ['gray', status || '—'];
    return '<span class="badge ' + x[0] + '">' + ZX.escapeHtml(x[1]) + '</span>';
  };

  /* ---------- 全局助手 ---------- */
  const panel = document.getElementById('assistantPanel');
  const fab = document.getElementById('assistantFab');
  const body = document.getElementById('assistantBody');
  if (panel && fab && body) {
    const open = () => { panel.classList.add('open'); panel.setAttribute('aria-hidden', 'false'); setTimeout(() => document.getElementById('assistantText').focus(), 50); };
    const close = () => { panel.classList.remove('open'); panel.setAttribute('aria-hidden', 'true'); };
    fab.addEventListener('click', () => panel.classList.contains('open') ? close() : open());
    document.getElementById('assistantClose').addEventListener('click', close);

    const add = (text, cls) => {
      const el = document.createElement('div');
      el.className = 'bubble ' + (cls || 'agent');
      el.textContent = text;
      body.appendChild(el);
      body.scrollTop = body.scrollHeight;
      return el;
    };
    const ask = async (text) => {
      if (!text) return;
      add(text, 'user');
      const tip = add('小习正在想…', 'note');
      try {
        const res = await ZX.api('/api/agent/ask', { method: 'POST', body: { text } });
        tip.remove();
        add(res.reply || '我在。');
        if (res.tool_calls && res.tool_calls.length) {
          add('调用：' + res.tool_calls.map(t => (t.tool || t.name || 'tool')).join(' · '), 'note');
        }
        if (res.suggestions && res.suggestions.length) {
          const chips = document.createElement('div');
          chips.className = 'chips';
          res.suggestions.forEach(s => {
            const b = document.createElement('button');
            b.textContent = s;
            b.addEventListener('click', () => ask(s));
            chips.appendChild(b);
          });
          body.appendChild(chips);
          body.scrollTop = body.scrollHeight;
        }
      } catch (e) {
        tip.remove();
        add('刚才没连上：' + e.message, 'note');
      }
    };
    document.querySelectorAll('#assistantChips button').forEach(b => b.addEventListener('click', () => ask(b.dataset.q || b.textContent)));
    document.getElementById('assistantForm').addEventListener('submit', (e) => {
      e.preventDefault();
      const input = document.getElementById('assistantText');
      const text = input.value.trim();
      input.value = '';
      ask(text);
    });
  }
})();

/* 退出登录 */
(function () {
  const btn = document.getElementById('logoutBtn');
  if (!btn) return;
  btn.addEventListener('click', async () => {
    if (!confirm('退出登录？')) return;
    try { await ZX.api('/api/auth/logout', { method: 'POST', body: {} }); } catch (e) {}
    location.href = '/login';
  });
})();
