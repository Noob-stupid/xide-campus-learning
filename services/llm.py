# -*- coding: utf-8 -*-
"""可选大模型适配层（OpenAI 兼容）。

不配置 ZX_LLM_* 时 available() 为 False，所有调用方自动回退规则引擎。
配置后用于：接棒匹配重排、辅导追问、助手回复润色。
"""
import json
import re
import urllib.error
import urllib.request

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TIMEOUT


def available():
    return bool(LLM_BASE_URL and LLM_API_KEY)


def _endpoint():
    base = (LLM_BASE_URL or '').rstrip('/')
    if base.endswith('/chat/completions'):
        return base
    return base + '/chat/completions'


def chat(messages, temperature=0.3, max_tokens=600):
    """返回文本；失败/未配置返回 None，绝不把异常抛给业务。"""
    if not available() or not messages:
        return None
    payload = {
        'model': LLM_MODEL,
        'messages': messages,
        'temperature': temperature,
        'max_tokens': max_tokens,
    }
    req = urllib.request.Request(
        _endpoint(),
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + LLM_API_KEY,
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
    """让 LLM 在规则候选里重排；失败返回 None。

    约束：只能从给定候选里选，不能编造内容 id；返回有序 id 和一句总理由。
    """
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
    """助手回复润色；只用于未知/卡住/推荐类意图，不能改座位号等事实。"""
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
