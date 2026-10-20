# 《习得》MVP 契约 v0.1

> 本文件是三个会话并行开发的唯一接口约定。改接口必须先改本文件并通知对端。

## 0. 项目与边界

- 项目根：`D:\华为ICT\zhixue-space`
- 产品：校园学习空间智能体「习得」——预约 → 学习 → 辅导 → 结束/到期 → 接棒推送 → 反馈；交棒上传 → 抽帧 → AI 初筛 → 人工帧级复核 → 入池。
- 技术栈：Python 3.14 + Flask + SQLite（本地）/ MySQL（云上）+ 原生 HTML/CSS/JS + SVG。**不引入 Vue/Element/Fabric/ECharts/CDN。**
- 所有路径从 `config.py` 推导，禁止硬编码本机绝对路径。

## 1. 文件归属（避免双写）

| 目录/文件 | 归属 |
|---|---|
| `config.py`, `db.py`, `app.py`, `seed.py`, `routes_*.py` | 主会话 |
| `templates/**`, `static/**`, `docs/**` | 主会话 |
| `services/workflow.py`, `services/agents.py`, `services/tutor.py`, `tests/test_workflow.py`, `tests/test_agents.py` | 对端 A（session-f51d6b6f） |
| `services/content.py`, `tools/make_demo_video.py`, `tests/test_content.py` | 对端 B（session-ab23034b） |
| `services/seats.py`, `services/navigation.py`, `services/relay.py`, `tests/test_seats.py`, `tests/test_relay.py` | 主会话 |

对端只写自己归属的文件；需要改别人的文件，先发消息。

## 2. 数据库表（SQLite，`db.py` 建表）

- `users(id, username, password_hash, name, role, college, avatar, cover, signature, interests, created_at)`
  - role: `student` / `reviewer` / `admin` / `teacher`
- `floors(id, name, building, floor_no, plan_w, plan_h)`
- `seats(id, floor_id, code, zone, x, y, w, h, seat_type, features, status)`
  - seat_type: `window` / `quiet` / `power` / `normal`
  - status: `free` / `maintenance`
- `nav_nodes(id, floor_id, code, x, y, kind)`
- `nav_edges(id, floor_id, from_node, to_node, distance)`
- `reservations(id, user_id, seat_id, subject, goal, start_at, end_at, checkin_at, checkout_at, status, source, created_at)`
  - status: `booked` / `checked_in` / `completed` / `cancelled` / `no_show` / `expired`
- `study_sessions(id, reservation_id, user_id, seat_id, subject, started_at, ended_at, duration_min, status, stuck_points, relay_content_id, pushed_at, feedback, created_at)`
  - status: `active` / `ended` / `relayed`
- `contents(id, owner_id, title, subject, knowledge_point, description, source_type, file_path, cover_path, duration_sec, status, ai_summary, ai_risk, review_note, reviewer_id, reviewed_at, published_at, views, helpful, unhelpful, created_at)`
  - source_type: `student` / `teacher` / `platform`
  - status: `processing` / `pending_review` / `approved` / `rejected`
- `content_frames(id, content_id, idx, ts_sec, path, risk, labels, reasons, status)`
  - status: `pending` / `cleared` / `flagged`
- `reviews(id, content_id, reviewer_id, decision, note, checklist, frames_reviewed, created_at)`
- `messages(id, user_id, kind, title, body, payload, read, created_at)`
- `relay_pushes(id, session_id, user_id, content_id, reason, score_json, created_at, opened_at, feedback)`
- `workflow_runs(id, flow_key, title, trigger, status, context, started_at, finished_at)`
- `workflow_steps(id, run_id, node_id, node_name, status, detail, started_at, finished_at)`
- `agent_logs(id, user_id, session_id, intent, input, output, tool_calls, created_at)`
- `settings(key, value)`

时间统一存本地时间字符串 `YYYY-MM-DD HH:MM:SS`，由 `db.now()` 生成。

## 3. `db.py` 接口

```python
db.connect() -> sqlite3.Connection
db.query(sql, args=()) -> list[sqlite3.Row]
db.one(sql, args=()) -> sqlite3.Row | None
db.execute(sql, args=()) -> lastrowid
db.executemany(sql, seq) -> None
db.init_db() -> None
db.now() -> str
db.dumps(obj) -> str
db.loads(s, default=None) -> Any
```

## 4. `services/workflow.py`（对端 A）

```python
NODE_TYPES = {'trigger','agent','tool','condition','human_review','notify'}

def start(flow_key: str, context: dict, user_id: int|None = None, title: str = '') -> int:
    """创建 workflow_run，返回 run_id；status='running'。"""

def step(run_id: int, node_id: str, node_name: str, fn: callable, detail: dict|None = None) -> dict:
    """执行一个节点：写 workflow_steps(running) → 调 fn(context) → 写 succeeded/failed。
    fn 返回 dict 会合并进 run.context；抛异常则步骤 failed，run 标记 failed 并向上抛。"""

def finish(run_id: int, status: str = 'succeeded', context: dict|None = None) -> None:

def get_run(run_id: int) -> dict:
    """返回 {id, flow_key, title, trigger, status, context, started_at, finished_at, steps:[...]}"""

def list_runs(limit: int = 20) -> list[dict]:

def flow_defs() -> list[dict]:
    """返回五条流的静态定义（节点/边），供编排页画图。"""
```

## 5. `services/agents.py` + `services/tutor.py`（对端 A）

```python
# agents.py
def ask(text: str, user_id: int, session_id: int|None = None) -> dict:
    """返回 {intent, reply, slots, data, suggestions, tool_calls, agent}
    intent ∈ find_seat | book_seat | my_session | stuck | recommend_content | rules | greeting | unknown
    """

# tutor.py
def start(topic: str, user_id: int, session_id: int|None = None) -> dict:
    """返回 {tutor_id, question, options, step}；tutor_id 存在内存或 settings 均可"""

def answer(tutor_id: str, text: str) -> dict:
    """返回 {done, question, explanation, check_question, resource, step}"""
```

## 6. `services/content.py`（对端 B）

```python
def process(content_id: int) -> dict:
    """抽帧 + AI 初筛 + 写 content_frames + 更新 contents.status='pending_review' + ai_summary/ai_risk。
    返回 {content_id, frames, suspicious, duration_sec, status}。"""

def review(content_id: int, reviewer_id: int, decision: str, note: str = '', checklist: dict|None = None,
           frame_status: dict|None = None) -> dict:
    """decision ∈ approve | reject。写 reviews；approve → contents.status='approved', published_at=now；
    reject → status='rejected'。返回 {content_id, status, frames_reviewed}。"""

def match_for_session(session: dict, limit: int = 5) -> list[dict]:
    """从 approved 内容中按 subject/knowledge_point/时长/新鲜度打分，返回
    [{id,title,subject,duration_sec,reason,score,breakdown,cover_path,file_path,source_type}]，按 score 降序。"""
```

## 7. API 路由（主会话实现，前端按此调用）

- `POST /api/auth/login {username,password}`
- `POST /api/auth/logout`
- `GET  /api/me`
- `GET  /api/seats?floor_id=1`
- `POST /api/bookings {seat_id, subject, goal, start_at, end_at}`
- `POST /api/bookings/<id>/checkin`
- `POST /api/bookings/<id>/end`
- `GET  /api/nav?seat_id=..&from=entry`
- `GET  /api/sessions/current`
- `POST /api/tutor/start {topic}` / `POST /api/tutor/answer {tutor_id,text}`
- `POST /api/agent/ask {text}`
- `GET  /api/contents?status=approved&subject=`
- `POST /api/contents` (multipart: file,title,subject,knowledge_point,description,source_type)
- `GET  /api/contents/<id>`
- `GET  /api/review/queue` / `GET /api/review/<id>` / `POST /api/review/<id>/decision`
- `GET  /api/relay/pending` / `POST /api/relay/<id>/open` / `POST /api/relay/<id>/feedback`
- `GET  /api/messages` / `POST /api/messages/read`
- `GET  /api/workflow/runs` / `GET /api/workflow/runs/<id>` / `GET /api/workflow/defs`
- `GET  /api/stats`

## 8. UI 设计令牌（主会话实现）

- 主色 `#0F2A4A`，点缀 `#C98A2E`，青绿 `#0E7C6B`，背景 `#F5F7FA`，卡片 `#FFFFFF`，线 `#E4E8EF`
- 字体：`system-ui, "PingFang SC", "Microsoft YaHei"`
- 圆角 16px，阴影 `0 6px 24px rgba(15,42,74,.06)`
- 个人主页采用视频站风格：封面 + 头像 + 数据栏 + Tab + 卡片网格；**不做粉丝/点赞/评论/关注**

## 9. 运行与测试

```bash
cd D:\华为ICT\zhixue-space
python app.py            # http://127.0.0.1:5820
python -m pytest -q      # tests/
```

演示账号：`student/123456`、`reviewer/123456`、`admin/123456`、`teacher/123456`。
