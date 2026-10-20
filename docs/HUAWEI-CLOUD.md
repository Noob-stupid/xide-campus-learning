# 习得 · 华为云部署与 CodeArts 证据

> 目标：作品形态是 Web；智能体/工作流是后台能力；CodeArts 是开发工具；RDS/Redis/OBS/MaaS 是运行支撑。

## 1. 资源映射

| 华为云 | 在本项目里承担什么 | 证据 |
|---|---|---|
| CodeArts 代码智能体 | 需求理解、代码生成、构建、修复、部署 | 5 环节截图 + 对话 + 流水线日志 |
| RDS MySQL | 用户、场次、内容、审核、推送、工作流记录 | 实例截图 + 脱敏连接串 + 表清单 |
| Redis | 抢座分布式锁、推送幂等、队列/限流 | 实例截图 + 锁 key 示例 |
| OBS | 学习视频、关键帧 | bucket 截图 + 对象路径 |
| MaaS | 意图路由/辅导/推送理由（可选，规则兜底） | 模型调用记录（脱敏） |
| 内容审核（可选） | 帧图合规初筛 | 调用记录 |

## 2. CodeArts 五环节证据清单

### ① 需求理解
- 把 `docs/PRODUCT.md` + `docs/ARCHITECTURE.md` 粘给 CodeArts，让它输出任务拆分/架构建议
- 截图：对话 + 生成的任务清单
- 落盘：`docs/codearts/01-requirements.md`

### ② 代码生成
- 让 CodeArts 生成一个真实模块（例如 `services/relay.py` 的推送决策，或审核工作台的帧时间轴）
- 截图：prompt + 生成 diff
- 记录：commit hash

### ③ 项目构建
- 用 CodeArts 流水线执行 `python -m pytest -q` 与依赖安装
- 截图：流水线成功日志

### ④ 问题修复
- 故意留一个真实失败测试/缺陷（如 `_duration_text` 的边界），让 CodeArts 诊断并修复
- 截图：失败 → 诊断 → 修复 → 测试通过
- 记录：修复前后 commit

### ⑤ 部署上线
- 用 CodeArts 一键部署 Skill（或 ECS + Docker）部署到华为云
- 截图：部署流水线 + 公网 URL + 健康检查

> 红线：证据必须真实发生；不要补拍/编造。

## 3. 推荐部署形态

### 方案 A：ECS + Docker + Nginx（最可控）

```bash
# ECS 上
cd /opt/xide
git clone <repo> .
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt gunicorn PyMySQL redis obs-sdk
export ZX_DB_BACKEND=mysql
# ... RDS/Redis/OBS 环境变量
gunicorn -b 0.0.0.0:5820 -w 2 app:app
```

Nginx 反代 5820，安全组只开 80/443。

### 方案 B：CodeArts 一键部署

按 CodeArts 提供的部署 Skill 选择 ECS/CCE 目标；构建命令：

```bash
pip install -r requirements.txt
python -m pytest -q
```

启动命令：`gunicorn -b 0.0.0.0:5820 -w 2 app:app`

## 4. 环境变量

```bash
ZX_HOST=0.0.0.0
ZX_PORT=5820
ZX_SECRET_KEY=<随机长串>
ZX_DB_BACKEND=sqlite|mysql
ZX_MYSQL_HOST=<RDS 内网地址>
ZX_MYSQL_PORT=3306
ZX_MYSQL_USER=<用户>
ZX_MYSQL_PASSWORD=<密码>
ZX_MYSQL_DB=zhixue
ZX_REDIS_HOST=<Redis 内网地址>
ZX_REDIS_PORT=6379
ZX_REDIS_PASSWORD=<密码>
ZX_OBS_BUCKET=<bucket>
ZX_LLM_BASE_URL=<MaaS OpenAI 兼容端点>
ZX_LLM_API_KEY=<key>
ZX_LLM_MODEL=<模型名>
```

## 5. RDS 迁移注意

本地 SQLite 表结构在 `db.py`；云上需要：

1. 建库 `zhixue`（utf8mb4）
2. 把 `INTEGER PRIMARY KEY AUTOINCREMENT` 改为 `INT AUTO_INCREMENT PRIMARY KEY`
3. `TEXT` 唯一键/主键改为 `VARCHAR(191)`
4. `REAL` 改为 `DOUBLE`
5. 时间统一 `DATETIME` / 字符串 `YYYY-MM-DD HH:MM:SS`
6. 所有 `?` 占位符在 MySQL 适配器里转 `%s`

> 当前仓库的 `db.py` 是 SQLite 实现；RDS 适配器是下一步接线点（`docs/CONTRACT.md` 的 `db.py` 接口不变）。比赛前请用真实 RDS 跑一次预约/审核/接棒三条链路。

## 6. Redis 抢座

```python
# 伪代码
ok = redis.set('seat:%s:%s' % (seat_id, slot), '1', nx=True, ex=30)
if not ok:
    raise ValueError('该时段已被预约')
try:
    # RDS 事务 + 唯一索引兜底
finally:
    redis.delete(key)
```

量化目标：200 并发抢同一座位同一时段 → 0 超卖；预约接口 P95 < 300ms。

## 7. 开源与提交

- 决赛要求开源到 Gitee/GitHub；初赛建议准备：源码、依赖、部署指导、使用文档、LICENSE、Demo 截图/视频链接。
- 本仓库已含 `LICENSE`（MIT）、`README.md`、`docs/`。

## 8. 演示证据包

```
docs/
  screenshots/
    01-home.png
    02-seats.png
    03-review.png
    04-workflow.png
    05-profile.png
  demo-video.mp4
  codearts/
    01-requirements.md
    02-codegen.md
    03-build.log
    04-fix.md
    05-deploy.md
```
