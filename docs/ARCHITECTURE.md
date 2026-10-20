# 习得 · 架构说明

## 1. 分层

```
Web 页面（Jinja / 原生 JS / SVG）
  │  fetch JSON
Flask 路由（app.py）
  │
服务层
  ├─ seats.py        座位/预约/签到/结束/到期扫描
  ├─ navigation.py   A* 室内导航
  ├─ content.py      抽帧/AI 初筛/帧级复核/匹配
  ├─ relay.py        接棒推送/反馈/幂等
  ├─ agents.py       意图路由 + 只读查库
  ├─ tutor.py        苏格拉底辅导
  ├─ flow.py         工作流引擎
  └─ devices.py      ESP32 上报 + 模拟器
  │
SQLite（本地）/ RDS MySQL（云上）
本地文件（本地）/ OBS（云上）
```

## 2. 核心对象

**学习场次（Study Session）** 是唯一主线：

```
预约 booked
  → 签到 checked_in（创建场次 active）
  → 学习 studying
  → 结束/到期 ended
  → 接棒 relayed
  → 反馈 feedback
```

场次携带：学科、座位、开始/结束、时长、卡点、接棒内容、推送时间、反馈。

## 3. 数据模型

| 表 | 作用 |
|---|---|
| `users` | 学生/教师/审核员/管理员 |
| `floors` / `seats` | 场馆与 48 个座位 |
| `nav_nodes` / `nav_edges` | 室内路网 |
| `reservations` | 预约（状态机） |
| `study_sessions` | 学习场次 |
| `contents` / `content_frames` | 交棒内容与关键帧 |
| `reviews` | 人工复核记录 |
| `relay_pushes` | 接棒推送与反馈 |
| `messages` | 站内消息 |
| `workflow_runs` / `workflow_steps` | 工作流运行轨迹 |
| `agent_logs` | 智能体调用审计 |
| `devices` / `seat_events` | 空间感知 |

## 4. 五条工作流

| 流 | 触发 | 节点 |
|---|---|---|
| 学习计划 | 目标输入 | 目标理解 → 拆解任务 → 排期预约 → 提醒 |
| 预约履约 | 确认预约 | 意图约束 → 座位匹配 → 锁座 → RDS 落库 → 导航 → 通知 |
| 学习辅导 | 签到/卡住了 | 签到 → 学习计划 → 专注计时 → 苏格拉底 → 推荐视频 → 结束 |
| 接棒推送 | 结束/到期 | 事件 → 上下文 → 候选检索 → 匹配排序 → 决策 → 推送 |
| 交棒审核 | 上传 | 上传 → 抽帧 → AI 初筛 → 人工帧级复核 → 入池 |

工作流引擎 API（`services/flow.py`）：

```python
run_id = flow.start(flow_key, context, user_id, title)
flow.step(run_id, node_id, node_name, fn)   # fn(context) 返回 dict 合并进上下文
flow.finish(run_id, status)
flow.get_run(run_id) / flow.list_runs() / flow.flow_defs()
```

每个 step 落 `workflow_steps`，记录 input/output/error/开始结束时间；编排页可回放。

## 5. 接棒推送的决策

```
触发：手动结束 / 预约到期（仅 checked_in 场次）
  ↓
上下文：学科、时长、座位区、卡点、历史、已看内容
  ↓
候选：只取 contents.status='approved'
  ↓
打分：主题 45% / 知识点 25% / 时长 15% / 新鲜度 10% / 质量 5%
  ↓
决策：有匹配→推送；无匹配→兜底建议；免打扰→定时；已推→跳过
  ↓
写入 relay_pushes + messages；场次状态 relayed
```

幂等：先查 `relay_pushes.session_id`，存在则直接返回；数据库唯一语义由该检查保证。

## 6. 抢座一致性

- 单机：`threading.RLock` + SQLite `BEGIN IMMEDIATE` + 时间段重叠查询
- 云上：Redis `SETNX` 锁 + RDS 事务 + 唯一索引兜底
- 冲突语义：同一座位同一时段只能有一条 `booked/checked_in`；第二个请求返回 400
- 演示压测见 `docs/HUAWEI-CLOUD.md`

## 7. 内容审核

- 抽帧：按时间均匀取样，最多 12 帧，帧存 `data/media/content_<id>/frames/`
- 初筛：亮度、对比度、模糊、红色占比、暗部占比、文本关键词
- 帧级状态：`pending` / `cleared` / `flagged`
- 人工复核：四项清单（合规/质量/相关性/版权与隐私）+ 复核意见
- 只有 `approved` 内容进入 `match_for_session`
- `labels` 逗号分隔，`reasons` 用「；」分隔，前端按此解析

## 8. 智能体

- `agents.ask(text, user_id, session_id)`：规则意图路由（find_seat/book_seat/my_session/stuck/recommend_content/rules/greeting/unknown），返回 `{intent, reply, slots, data, suggestions, tool_calls, agent}`
- `tutor.start(topic)` / `tutor.answer(tutor_id, text)`：2–3 个主题的苏格拉底脚本，每轮只问一个问题，不会就承认
- 所有 AI 能力都有规则兜底；无大模型也能完整跑通

## 9. 设备接入

- `POST /api/sensor/register` / `POST /api/sensor/report`
- 设备状态只补充“此刻有没有人”，不覆盖预约
- 管理端模拟器：`POST /api/devices/simulate {seat_code, occupied}`

## 10. 扩展点

- `content.py` 的 `process/review/match_for_session` 可替换为华为云内容审核/MaaS 实现
- `db.py` 可替换为 RDS MySQL 适配器（`docs/HUAWEI-CLOUD.md`）
- `flow.py` 的 node 类型可对接 AgentArts 工作流节点
- `devices.py` 可接真实 ESP32 固件
