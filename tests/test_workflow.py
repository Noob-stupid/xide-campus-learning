# -*- coding: utf-8 -*-
"""services/workflow.py 的测试（对端 A）。

跑法：
    cd D:\\华为ICT\\zhixue-space && python -m pytest -q
每个用例用 tmp_path 下的独立 SQLite 文件（monkeypatch db.DB_PATH），不碰真实 data/。
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if 'ZX_DATA_DIR' not in os.environ:
    os.environ['ZX_DATA_DIR'] = tempfile.mkdtemp(prefix='zx-test-')

import pytest

import db
from services import workflow


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / 'zhixue.db'))
    db.init_db()
    yield


# ---------------------------------------------------------------- run 生命周期

def test_start_creates_running_run(fresh_db):
    rid = workflow.start('plan', {'subject': '高等数学'}, user_id=7)
    assert isinstance(rid, int) and rid > 0

    run = workflow.get_run(rid)
    assert run['id'] == rid
    assert run['flow_key'] == 'plan'
    assert run['title'] == '学习计划编排'
    assert run['status'] == 'running'
    assert run['finished_at'] is None
    assert run['started_at']
    assert run['context']['subject'] == '高等数学'
    assert run['context']['user_id'] == 7          # start 的 user_id 落进 context
    assert run['steps'] == []
    assert run['step_count'] == 0


def test_start_keeps_trigger_column(fresh_db):
    rid = workflow.start('relay', {'trigger': 'timeout', 'user_id': 3})
    run = workflow.get_run(rid)
    assert run['trigger'] == 'timeout'
    assert run['context']['trigger'] == 'timeout'  # context 里也留着，方便前端展示


def test_step_success_merges_context(fresh_db):
    rid = workflow.start('study', {'subject': '高等数学'})
    out = workflow.step(rid, 'study_trigger', '签到落座', lambda ctx: {'checked_in': True})

    assert out['status'] == 'succeeded'
    assert out['run_id'] == rid
    assert out['node_id'] == 'study_trigger'
    assert out['result'] == {'checked_in': True}

    run = workflow.get_run(rid)
    assert run['context']['checked_in'] is True
    assert run['context']['subject'] == '高等数学'   # 原有 context 不被覆盖
    assert run['status'] == 'running'
    assert run['ok_steps'] == 1

    step = run['steps'][0]
    assert step['status'] == 'succeeded'
    assert step['node_id'] == 'study_trigger'
    assert step['node_name'] == '签到落座'
    assert step['started_at'] and step['finished_at']
    assert step['detail']['result'] == {'checked_in': True}


def test_step_gets_context_copy(fresh_db):
    """fn 拿到的是 context，改它不会污染库里（以返回值合并为准）。"""
    rid = workflow.start('plan', {'subject': '英语'})
    seen = {}

    def fn(ctx):
        seen.update(ctx)
        ctx['subject'] = '被改脏了'
        return {'parsed': True}

    workflow.step(rid, 'plan_parse', '目标解析', fn)
    assert seen['subject'] == '英语'
    run = workflow.get_run(rid)
    assert run['context']['subject'] == '英语'
    assert run['context']['parsed'] is True


def test_step_returning_none_keeps_context(fresh_db):
    rid = workflow.start('plan', {'subject': '英语'})
    out = workflow.step(rid, 'plan_parse', '目标解析', lambda ctx: None)
    assert out['result'] is None
    run = workflow.get_run(rid)
    assert run['context'] == {'subject': '英语'}
    assert run['steps'][0]['status'] == 'succeeded'


# ---------------------------------------------------------------- 失败路径（回滚语义）

def test_step_failure_marks_step_and_run_failed(fresh_db):
    rid = workflow.start('relay', {'subject': '大学英语'})
    workflow.step(rid, 'relay_trigger', '学习结束', lambda ctx: {'ended': True})

    def boom(ctx):
        raise ValueError('内容池为空')

    with pytest.raises(ValueError, match='内容池为空'):
        workflow.step(rid, 'relay_match', '匹配已过审内容', boom, detail={'limit': 5})

    run = workflow.get_run(rid)
    assert run['status'] == 'failed'
    assert run['finished_at']
    assert len(run['steps']) == 2

    ok_step, bad_step = run['steps']
    assert ok_step['status'] == 'succeeded'
    assert bad_step['status'] == 'failed'
    assert bad_step['node_id'] == 'relay_match'
    assert '内容池为空' in bad_step['detail']['error']
    assert bad_step['detail']['limit'] == 5        # detail 入参也留档
    assert bad_step['finished_at']

    # 失败不是「清空」：前一步写下的成果保留在 context 里
    assert run['context']['ended'] is True


def test_step_rejected_after_run_failed(fresh_db):
    rid = workflow.start('relay', {})
    with pytest.raises(RuntimeError):
        workflow.step(rid, 'relay_trigger', '结束', lambda ctx: (_ for _ in ()).throw(RuntimeError('炸了')))
    with pytest.raises(ValueError):
        workflow.step(rid, 'relay_match', '匹配', lambda ctx: {'matched': 1})
    assert workflow.get_run(rid)['status'] == 'failed'


def test_step_on_missing_run_raises(fresh_db):
    with pytest.raises(LookupError):
        workflow.step(99999, 'x', 'x', lambda ctx: {})


# ---------------------------------------------------------------- finish

def test_finish_sets_status_and_merges_context(fresh_db):
    rid = workflow.start('booking', {'seat_code': 'A12'})
    workflow.step(rid, 'booking_rules', '规则校验', lambda ctx: {'rule_ok': True})
    workflow.finish(rid, 'succeeded', {'reservation_id': 42})

    run = workflow.get_run(rid)
    assert run['status'] == 'succeeded'
    assert run['finished_at']
    assert run['context']['reservation_id'] == 42
    assert run['context']['rule_ok'] is True


def test_finish_does_not_mask_failure(fresh_db):
    rid = workflow.start('relay', {})
    with pytest.raises(RuntimeError):
        workflow.step(rid, 'relay_match', '匹配', lambda ctx: (_ for _ in ()).throw(RuntimeError('x')))
    workflow.finish(rid, 'succeeded')
    assert workflow.get_run(rid)['status'] == 'failed'


def test_finish_on_missing_run_raises(fresh_db):
    with pytest.raises(LookupError):
        workflow.finish(424242)


def test_get_run_missing_returns_none(fresh_db):
    assert workflow.get_run(424242) is None


# ---------------------------------------------------------------- list_runs

def test_list_runs_orders_newest_first_and_limits(fresh_db):
    ids = [workflow.start('plan', {'i': i}) for i in range(3)]
    workflow.step(ids[2], 'plan_parse', '解析', lambda ctx: {'parsed': True})
    workflow.finish(ids[2], 'succeeded')

    runs = workflow.list_runs()
    assert [r['id'] for r in runs] == list(reversed(ids))
    assert runs[0]['context']['i'] == 2
    assert runs[0]['status'] == 'succeeded'
    assert runs[0]['step_count'] == 1 and runs[0]['ok_steps'] == 1
    assert runs[1]['steps'] == []
    assert len(workflow.list_runs(limit=2)) == 2
    assert workflow.list_runs(limit=0)[0]['id'] == ids[2]     # 非法 limit 归一化成 1


# ---------------------------------------------------------------- flow_defs

def test_flow_defs_has_five_flows():
    defs = workflow.flow_defs()
    assert [d['key'] for d in defs] == ['plan', 'booking', 'study', 'relay', 'content']
    assert workflow.flow_keys() == ['plan', 'booking', 'study', 'relay', 'content']
    for d in defs:
        assert d['name'] and d['desc']
        assert d['entry'] in [n['id'] for n in d['nodes']]
        assert len(d['nodes']) >= 5 and len(d['edges']) >= 4


def test_flow_defs_nodes_and_edges_consistent():
    for d in workflow.flow_defs():
        ids = [n['id'] for n in d['nodes']]
        assert len(ids) == len(set(ids)), '%s 有重复 node id' % d['key']
        for n in d['nodes']:
            assert n['type'] in workflow.NODE_TYPES, n
            assert n['name'] and n['desc'], n
        for e in d['edges']:
            assert e['from'] in ids, (d['key'], e)
            assert e['to'] in ids, (d['key'], e)
        # 每条流都要有入口 trigger 和出口 notify / human_review
        types = {n['type'] for n in d['nodes']}
        assert 'trigger' in types
        assert types & {'notify', 'human_review'}
        assert d['entry'] in ids
    # 契约里的六种节点类型都被用到过
    used = {n['type'] for d in workflow.flow_defs() for n in d['nodes']}
    assert used == workflow.NODE_TYPES


def test_flow_defs_returns_copy():
    first = workflow.flow_defs()
    first[0]['nodes'][0]['name'] = '被改脏了'
    first[0]['nodes'].append({'id': 'x'})
    again = workflow.flow_defs()
    assert again[0]['nodes'][0]['name'] == '提出学习目标'
    assert len(again[0]['nodes']) == len(first[0]['nodes']) - 1
    assert workflow.flow_def('plan')['key'] == 'plan'
    assert workflow.flow_def('nope') is None


# ---------------------------------------------------------------- run_flow（加法）

def test_run_flow_runs_all_steps_and_finishes(fresh_db):
    rid = workflow.run_flow('content', {'title': '极限 12 分钟讲透'}, [
        ('content_trigger', '上传', lambda ctx: {'uploaded': 1}),
        ('content_extract', '抽帧', lambda ctx: {'frames': 3}),
        ('content_screen', 'AI 初筛', lambda ctx: {'ai_risk': 0.12}),
    ], user_id=5)

    run = workflow.get_run(rid)
    assert run['status'] == 'succeeded'
    assert [s['node_id'] for s in run['steps']] == ['content_trigger', 'content_extract', 'content_screen']
    assert run['context']['frames'] == 3
    assert run['context']['ai_risk'] == 0.12
    assert run['context']['user_id'] == 5
    assert run['finished_at']


def test_run_flow_propagates_failure(fresh_db):
    with pytest.raises(ValueError):
        workflow.run_flow('relay', {}, [
            ('relay_trigger', '结束', lambda ctx: {'ended': True}),
            ('relay_match', '匹配', lambda ctx: (_ for _ in ()).throw(ValueError('空池'))),
        ])
    runs = workflow.list_runs()
    assert runs[0]['status'] == 'failed'
