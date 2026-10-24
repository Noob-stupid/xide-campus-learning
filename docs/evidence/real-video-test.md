# 真实视频流水线试验（2026-10-24）

## 视频来源

- URL：https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4
- 授权：MDN CC0 示例视频
- 本地文件：data/uploads/real_flower.mp4（1,128,375 bytes）
- 时长：约 5 秒

## 上传与抽帧结果

```text
POST /api/contents
content_id = 7
frames = 5
suspicious = 1
frames_flagged = 2
max_risk = 0.7325
status = pending_review
```

真实抽帧覆盖：

- `data/media/content_7/frames/f_01.jpg` ~ `f_05.jpg`
- `docs/screenshots/17-real-video-frame.jpg`

## 人工复核

- 审核员通过，状态 `approved`
- 复核说明：真实视频抽帧测试；画面为花卉延时，人工复核通过
- 当前接力池可见：`花的延时：观察花瓣与花蕊`（自然观察）

> AI 初筛把花瓣/肤色误判成“人物特写/大面积红色”，人工复核纠正，
> 正好验证了“AI 初筛 + 人工帧级复核”的必要性，而不是全自动审核。

## 本地 Redis

```text
redis-server.exe 启动成功
redis-cli ping -> PONG
set xide:test ok
 get xide:test -> ok
```

说明：本机 Redis 可用；当前 Web 代码仍以 SQLite 为主，Redis 尚未接入抢座锁/幂等。
RDS/MySQL 本机已安装但未接入；OBS 目前用本地文件等价替代。
