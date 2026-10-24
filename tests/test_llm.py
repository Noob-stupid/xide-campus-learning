# -*- coding: utf-8 -*-
from services import llm


def test_json_object_accepts_code_fence():
    data = llm._json_object('```json\n{"ordered_ids":[2,1],"reason":"ok"}\n```')
    assert data['ordered_ids'] == [2, 1]
    assert data['reason'] == 'ok'


def test_json_object_rejects_garbage():
    assert llm._json_object('not json') is None


def test_rerank_orders_candidates_and_marks_ai(monkeypatch):
    monkeypatch.setattr(llm, 'available', lambda: True)
    monkeypatch.setattr(llm, 'chat', lambda *a, **k: '{"ordered_ids":[2,1],"reason":"更贴合卡点"}')
    candidates = [
        {'id': 1, 'title': 'A', 'subject': '高等数学', 'knowledge_point': '极限', 'duration_sec': 180, 'score': 80, 'reason': '规则A'},
        {'id': 2, 'title': 'B', 'subject': '高等数学', 'knowledge_point': 'ε-δ', 'duration_sec': 180, 'score': 75, 'reason': '规则B'},
    ]
    out = llm.rerank({'subject': '高等数学', 'knowledge_point': 'ε-δ'}, candidates)
    assert [c['id'] for c in out] == [2, 1]
    assert out[0]['ai_reranked'] is True
    assert out[0]['ai_reason'] == '更贴合卡点'


def test_rerank_falls_back_when_model_returns_bad_json(monkeypatch):
    monkeypatch.setattr(llm, 'available', lambda: True)
    monkeypatch.setattr(llm, 'chat', lambda *a, **k: '我不知道')
    assert llm.rerank({'subject': '高等数学'}, [{'id': 1, 'title': 'A'}]) is None


def test_mask_key_keeps_edges():
    assert llm._mask('sk-1234567890') == 'sk-1****7890'
    assert llm._mask('short') == '****'


def test_chat_failover_tries_next_provider(monkeypatch):
    providers = [
        {'id': 'a', 'name': 'A', 'base_url': 'https://a/v1', 'model': 'm', 'api_key': 'k', 'enabled': True, 'priority': 1},
        {'id': 'b', 'name': 'B', 'base_url': 'https://b/v1', 'model': 'm', 'api_key': 'k', 'enabled': True, 'priority': 2},
    ]
    monkeypatch.setattr(llm, '_load_providers', lambda include_secrets=True: providers)
    calls = []
    def fake_call(p, *args, **kwargs):
        calls.append(p['id'])
        return None if p['id'] == 'a' else 'ok'
    monkeypatch.setattr(llm, '_call_provider', fake_call)
    assert llm.chat([{'role': 'user', 'content': 'hi'}]) == 'ok'
    assert calls == ['a', 'b']
