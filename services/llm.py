# -*- coding: utf-8 -*-
"""可选大模型适配层（OpenAI 兼容）+ 多供应商自动切换。

配置来源优先级：
1. 管理后台写入 settings.llm_providers（可视化、免重启）
2. 环境变量 ZX_LLM_*（冷启动兜底）

不配置时 available() 为 False，所有调用方自动回退规则引擎。
"""
import json
import re
import time
import urllib.error
import urllib.request

import db
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TIMEOUT

_LAST_PROVIDER = ''
_LAST_ERROR = ''


def _mask(key):
    key = str(key or '')
    if not key:
        return ''
    if len(key) <= 8:
        return '****'
    return key[:4] + '****' + key[-4:]


def _env_providers():
    if not (LLM_BASE_URL and LLM_API_KEY):
        return []
    return [{
        'id': 'env',
        'name': '环境变量默认',
        'base_url': LLM_BASE_URL,
        'model': LLM_MODEL,
        'api_key': LLM_API_KEY,
        'enabled': True,
        'priority': 100,
    }]


def _load_providers(include_secrets=True):
    items = []
    try:
        raw = db.get_setting('llm_providers', '')
        if raw:
            data = json.loads(raw)
            if isinstance(data, list):
                for x in data:
                    if not isinstance(x, dict):
                        continue
                    if not (x.get('base_url') and x.get('model')):
                        continue
                    items.append({
                        'id': str(x.get('id') or ('p%d' % len(items))),
                        'name': str(x.get('name') or '未命名供应商'),
                        'base_url': str(x.get('base_url') or '').rstrip('/'),
                        'model': str(x.get('model') or ''),
                        'api_key': str(x.get('api_key') or ''),
                        'enabled': bool(x.get('enabled', True)),
                        'priority': int(x.get('priority') or 50),
                    })
    except Exception:
        items = []
    if not items:
        items = _env_providers()
    items.sort(key=lambda p: (0 if p['enabled'] else 1, p.get('priority', 50), p.get('id', '')))
    if include_secrets:
        return items
    out = []
    for p in items:
        q = dict(p)
        q['api_key'] = _mask(q.get('api_key'))
        out.append(q)
    return out


def _active_id():
    try:
        return db.get_setting('llm_active_id', '')
    except Exception:
        return ''


def active_provider():
    providers = _load_providers(True)
    if not providers:
        return None
    aid = _active_id()
    for p in providers:
        if p['id'] == aid and p['enabled']:
            return p
    for p in providers:
        if p['enabled']:
            return p
    return None


def available():
    return active_provider() is not None


def _endpoint(base):
    base = str(base or '').rstrip('/')
    if base.endswith('/chat/completions'):
        return base
    return base + '/chat/completions'


def _call_provider(provider, messages, temperature=0.3, max_tokens=600):
    """调用单个供应商；成功返回文本，失败返回 None。"""
    if not provider or not provider.get('base_url') or not provider.get('api_key'):
        return None
    payload = {
        'model': provider.get('model') or LLM_MODEL,
        'messages': messages,
        'temperature': temperature,
        'max_tokens': max_tokens,
    }
    req = urllib.request.Request(
        _endpoint(provider['base_url']),
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + str(provider['api_key']),
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        choices = data.get('choices') or []
        if not choices:
            return None
        content = (choices[0].get('message') or {}).get('content') or ''
        return str(content).strip() or None
    except Exception:
        return None


def chat(messages, temperature=0.3, max_tokens=600):
    """按优先级尝试所有启用的供应商，自动切换；全失败返回 None。"""
    global _LAST_PROVIDER, _LAST_ERROR
    if not messages:
        return None
    for p in _load_providers(True):
        if not p.get('enabled'):
            continue
        text = _call_provider(p, messages, temperature, max_tokens)
        if text:
            _LAST_PROVIDER = p.get('name') or p.get('id') or ''
            _LAST_ERROR = ''
            return text
        _LAST_ERROR = '调用失败，已尝试下一个供应商'
    if not _load_providers(True):
        _LAST_ERROR = '未配置任何 LLM 供应商'
    return None


def save_config(providers, active_id=''):
    """保存供应商列表；空/掩码 api_key 保留旧 Key，避免前端回显覆盖。"""
    old = {p['id']: p for p in _load_providers(True)}
    clean = []
    for i, x in enumerate(providers or []):
        if not isinstance(x, dict):
            continue
        pid = str(x.get('id') or ('p%d' % i))
        key = str(x.get('api_key') or '')
        if (not key) or ('****' in key):
            key = (old.get(pid) or {}).get('api_key', '')
        if not (x.get('base_url') and x.get('model')):
            continue
        clean.append({
            'id': pid,
            'name': str(x.get('name') or '未命名供应商'),
            'base_url': str(x.get('base_url') or '').rstrip('/'),
            'model': str(x.get('model') or ''),
            'api_key': key,
            'enabled': bool(x.get('enabled', True)),
            'priority': int(x.get('priority') or 50),
        })
    db.set_setting('llm_providers', json.dumps(clean, ensure_ascii=False))
    db.set_setting('llm_active_id', str(active_id or ''))
    return status()


def test_provider(provider=None):
    """测试一个供应商；provider 可含掩码 Key，掩码时用已保存 Key。"""
    if provider:
        pid = str(provider.get('id') or '')
        if pid and (not provider.get('api_key') or '****' in str(provider.get('api_key'))):
            saved = {p['id']: p for p in _load_providers(True)}
            if pid in saved:
                provider = dict(provider)
                provider['api_key'] = saved[pid].get('api_key', '')
    else:
        provider = active_provider()
    if not provider:
        return {'ok': False, 'error': '没有可测试的供应商'}
    start = time.time()
    text = _call_provider(provider, [
        {'role': 'user', 'content': '只回复两个字：可用'}
    ], temperature=0, max_tokens=16)
    ms = int((time.time() - start) * 1000)
    return {
        'ok': bool(text),
        'provider': provider.get('name') or provider.get('id') or '',
        'model': provider.get('model') or '',
        'latency_ms': ms,
        'reply': text or '',
        'error': '' if text else '调用失败：检查 Base URL / Key / 模型名',
    }


def status():
    providers = _load_providers(False)
    active = active_provider()
    return {
        'ok': True,
        'available': active is not None,
        'active': None if active is None else {
            'id': active.get('id'),
            'name': active.get('name'),
            'base_url': active.get('base_url'),
            'model': active.get('model'),
            'api_key': _mask(active.get('api_key')),
        },
        'providers': providers,
        'last_provider': _LAST_PROVIDER,
        'last_error': _LAST_ERROR,
        'env_configured': bool(LLM_BASE_URL and LLM_API_KEY),
    }


def _json_object(text):
    if not text:
        return None
    s = str(text).strip()
    s = re.sub(r'^```(?:json)?\s*', '', s, flags=re.I)
    s = re.sub(r'\s*```$', '', s)
    start = s.find('{')
    end = s.rfind('}')
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(s[start:end + 1])
    except Exception:
        return None


def rerank(session, candidates):
    """让 LLM 在规则候选里重排；失败返回 None。"""
    if not available() or not candidates:
        return None
    session = dict(session or {})
    compact = []
    for c in candidates[:6]:
        compact.append({
            'id': int(c.get('id')),
            'title': c.get('title') or '',
            'subject': c.get('subject') or '',
            'knowledge_point': c.get('knowledge_point') or '',
            'duration_sec': c.get('duration_sec') or 0,
            'rule_score': c.get('score') or 0,
            'rule_reason': c.get('reason') or '',
        })
    prompt = (
        '你是校园学习内容推荐器。根据这次学习场次，给候选学习视频排序。\n'
        '场次：学科=%s；卡点=%s；时长=%s分钟；座位区=%s。\n'
        '候选：%s\n'
        '只返回 JSON，格式：{"ordered_ids":[id...],"reason":"一句中文理由"}。\n'
        '要求：只能使用候选里出现的 id；优先匹配学科和卡点；不要编造视频。'
        % (session.get('subject') or '', session.get('knowledge_point') or session.get('stuck_points') or '',
           session.get('duration_min') or 0, session.get('zone') or '',
           json.dumps(compact, ensure_ascii=False))
    )
    text = chat([
        {'role': 'system', 'content': '你只输出 JSON，不要 Markdown，不要解释。'},
        {'role': 'user', 'content': prompt},
    ], temperature=0.2, max_tokens=400)
    data = _json_object(text)
    if not isinstance(data, dict):
        return None
    ids = data.get('ordered_ids') or []
    by_id = {int(c.get('id')): c for c in candidates}
    ordered = []
    for raw in ids:
        try:
            cid = int(raw)
        except Exception:
            continue
        c = by_id.get(cid)
        if c is not None and c not in ordered:
            ordered.append(c)
    if not ordered:
        return None
    for c in candidates:
        if c not in ordered:
            ordered.append(c)
    reason = str(data.get('reason') or '').strip()
    for c in ordered:
        c['ai_reranked'] = True
        c['ai_reason'] = reason
    return ordered


def tutor_hint(topic, step, student_text):
    """给苏格拉底辅导生成一个更小的追问；失败返回 None。"""
    if not available():
        return None
    prompt = (
        '你是苏格拉底式辅导老师。知识点：%s。\n当前问题：%s\n学生回答：%s\n'
        '请只给一个更小的追问或提示，不要直接给出最终答案，80 字以内。'
        % (topic.get('name') or '', step.get('question') or '', student_text or '')
    )
    return chat([
        {'role': 'system', 'content': '你是耐心的中文学习辅导老师，只输出一句追问或提示。'},
        {'role': 'user', 'content': prompt},
    ], temperature=0.4, max_tokens=180)


def agent_reply(text, rule_result):
    """助手回复润色；只用于未知/卡住类意图，不能改座位号等事实。"""
    if not available():
        return None
    prompt = (
        '你在校园学习助手里回答学生。学生说：%s\n'
        '规则引擎的回复：%s\n'
        '请改写成自然、简短的中文回复，保留所有座位号、时间、数字，不要编造新信息。'
        % (text or '', rule_result.get('reply') or '')
    )
    return chat([
        {'role': 'system', 'content': '你是简洁、友好的校园学习助手。'},
        {'role': 'user', 'content': prompt},
    ], temperature=0.4, max_tokens=240)
