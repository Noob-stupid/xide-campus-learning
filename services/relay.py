# -*- coding: utf-8 -*-
"""接棒推送：结束/到期事件 → 场次上下文 → 内容匹配 → 接力卡 → 反馈。"""
import db
from . import flow


def _candidates(session):
    try:
        from . import content as content_svc
        if hasattr(content_svc, 'match_for_session'):
            out = content_svc.match_for_session(session, limit=5)
            if out:
                return out
    except Exception:
        pass
    return _fallback_match(session)


def _fallback_match(session):
    rows = db.query("SELECT * FROM contents WHERE status='approved' ORDER BY id DESC")
    subject = (session.get('subject') or '').strip()
    stuck = (session.get('stuck_points') or '').strip()
    out = []
    for r in rows:
        d = dict(r)
        score = 0.0
        why = []
        if subject and subject in (d.get('subject') or ''):
            score += 0.45
            why.append('主题匹配')
        if stuck and (d.get('knowledge_point') or '') and any(k in stuck for k in (d.get('knowledge_point') or '').split(',')):
            score += 0.25
            why.append('命中你的卡点')
        dur = d.get('duration_sec') or 0
        if 60 <= dur <= 600:
            score += 0.15
            why.append('%d 分钟适合课间' % max(1, round(dur / 60)))
        score += 0.1
        d['score'] = round(min(score, 1.0), 2)
        d['reason'] = ' · '.join(why) if why else '已通过人工复核，适合自习后观看'
        d['breakdown'] = {'subject': 0.45 if subject and subject in (d.get('subject') or '') else 0,
                          'stuck': 0.25 if stuck else 0, 'duration': 0.15, 'quality': 0.1}
        out.append(d)
    out.sort(key=lambda x: x['score'], reverse=True)
    return out[:5]


def trigger(session_id, trigger='manual'):
    sess = db.one('SELECT ss.*, s.code AS seat_code, s.zone FROM study_sessions ss '
                  'JOIN seats s ON s.id=ss.seat_id WHERE ss.id=?', (session_id,))
    if not sess:
        raise ValueError('场次不存在')
    sess = dict(sess)
    old = db.one('SELECT * FROM relay_pushes WHERE session_id=? ORDER BY id DESC LIMIT 1', (session_id,))
    if old:
        return {'ok': True, 'push': dict(old), 'idempotent': True}

    run_id = flow.start('relay', {'session_id': session_id, 'trigger': trigger, 'subject': sess.get('subject')},
                        user_id=sess['user_id'], title='接棒 · %s' % (sess.get('subject') or '学习'))
    ctx = {}
    try:
        flow.step(run_id, 'trigger', '结束/到期事件', lambda c: {'trigger': trigger, 'session_id': session_id})

        def _context(c):
            user = db.one('SELECT * FROM users WHERE id=?', (sess['user_id'],))
            return {'context': {'user_name': user['name'] if user else '',
                                'seat_code': sess.get('seat_code'), 'zone': sess.get('zone'),
                                'subject': sess.get('subject'), 'duration_min': sess.get('duration_min'),
                                'stuck_points': sess.get('stuck_points') or ''}}
        flow.step(run_id, 'context', '聚合场次上下文', _context)

        def _recall(c):
            candidates = _candidates({**sess, **c.get('context', {})})
            return {'candidates': candidates}
        flow.step(run_id, 'recall', '候选内容检索', _recall)

        def _rank(c):
            cs = c.get('candidates') or []
            return {'top': cs[0] if cs else None, 'ranked': cs[:3]}
        rank_out = flow.step(run_id, 'rank', '匹配与排序', _rank)

        top = rank_out.get('top')
        if top:
            def _push(c):
                push_id = db.execute(
                    'INSERT INTO relay_pushes(session_id,user_id,content_id,reason,score_json,created_at) '
                    'VALUES(?,?,?,?,?,?)',
                    (session_id, sess['user_id'], top['id'], top.get('reason', ''),
                     db.dumps({'score': top.get('score'), 'breakdown': top.get('breakdown')}), db.now()))
                db.execute(
                    'INSERT INTO messages(user_id,kind,title,body,payload,read,created_at) VALUES(?,?,?,?,?,0,?)',
                    (sess['user_id'], 'relay', '学习接力 · 为你找到一条视频',
                     '你刚在 %s 完成 %s 分钟学习。%s' % (sess.get('seat_code'), sess.get('duration_min'),
                                                          top.get('reason') or '为你匹配到一条已过审学习视频'),
                     db.dumps({'push_id': push_id, 'content_id': top['id']}), db.now()))
                db.execute("UPDATE study_sessions SET status='relayed', relay_content_id=?, pushed_at=? WHERE id=?",
                           (top['id'], db.now(), session_id))
                return {'push_id': push_id, 'content_id': top['id'], 'reason': top.get('reason')}
            flow.step(run_id, 'decide', '推送决策', lambda c: {'decision': 'push'})
            flow.step(run_id, 'push', '推送接力卡', _push)
        else:
            def _fallback(c):
                db.execute(
                    'INSERT INTO messages(user_id,kind,title,body,payload,read,created_at) VALUES(?,?,?,?,?,0,?)',
                    (sess['user_id'], 'relay', '学习接力 · 给你一个建议',
                     '这次没有完全匹配的视频。建议把今天卡住的点写成三句话，下次交棒给同学。',
                     db.dumps({'session_id': session_id}), db.now()))
                db.execute("UPDATE study_sessions SET status='relayed', pushed_at=? WHERE id=?", (db.now(), session_id))
                return {'fallback': True}
            flow.step(run_id, 'decide', '推送决策', lambda c: {'decision': 'fallback'})
            flow.step(run_id, 'push', '兜底建议', _fallback)

        flow.finish(run_id, 'succeeded')
    except Exception as e:
        flow.finish(run_id, 'failed')
        raise
    push = db.one('SELECT * FROM relay_pushes WHERE session_id=? ORDER BY id DESC LIMIT 1', (session_id,))
    return {'ok': True, 'run_id': run_id, 'push': dict(push) if push else None}


def pending(user_id):
    rows = db.query(
        'SELECT p.*, c.title, c.subject, c.knowledge_point, c.duration_sec, c.cover_path, c.file_path, '
        'c.source_type, c.reviewer_id, c.reviewed_at, u.name AS owner_name, r.code AS seat_code '
        'FROM relay_pushes p JOIN contents c ON c.id=p.content_id '
        'LEFT JOIN users u ON u.id=c.owner_id LEFT JOIN study_sessions ss ON ss.id=p.session_id '
        'LEFT JOIN seats r ON r.id=ss.seat_id '
        'WHERE p.user_id=? ORDER BY p.id DESC LIMIT 20', (user_id,))
    return [dict(x) for x in rows]


def open_push(push_id, user_id):
    p = db.one('SELECT * FROM relay_pushes WHERE id=? AND user_id=?', (push_id, user_id))
    if not p:
        raise ValueError('接力卡不存在')
    if not p['opened_at']:
        db.execute('UPDATE relay_pushes SET opened_at=? WHERE id=?', (db.now(), push_id))
        db.execute('UPDATE contents SET views=views+1 WHERE id=?', (p['content_id'],))
    return dict(db.one('SELECT * FROM relay_pushes WHERE id=?', (push_id,)))


def feedback(push_id, user_id, value):
    p = db.one('SELECT * FROM relay_pushes WHERE id=? AND user_id=?', (push_id, user_id))
    if not p:
        raise ValueError('接力卡不存在')
    value = 'helpful' if value in ('helpful', 'up', '1', True) else 'unhelpful'
    db.execute('UPDATE relay_pushes SET feedback=? WHERE id=?', (value, push_id))
    col = 'helpful' if value == 'helpful' else 'unhelpful'
    db.execute('UPDATE contents SET %s=%s+1 WHERE id=?' % (col, col), (p['content_id'],))
    return {'ok': True, 'feedback': value}
