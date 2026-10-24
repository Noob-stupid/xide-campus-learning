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
