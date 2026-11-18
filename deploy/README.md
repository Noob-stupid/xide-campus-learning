# 习得 KeepLit · 部署说明（云主机 / 开发者空间）

> 目标：把当前仓库跑在 Linux 云主机上，提供可访问的 Web 地址，并留下可核验的部署证据。

## 0. 部署前必做

```bash
# 本机（Windows）先把最新代码推到远程，云主机才能 clone 到新代码
git add -A
git commit -m "fix: 修复高/中优先级缺陷并加固安全配置"
git push origin master
git push huaweicloud master
```

- [ ] `git status` 干净
- [ ] 远程（GitHub / CodeArts CodeHub）能看到本次提交

> 不推送也可以：把整个项目打包上传到云主机，但后续更新更麻烦。

## 1. 环境要求

| 项 | 要求 |
|---|---|
| 系统 | Ubuntu 22.04 / Huawei Cloud EulerOS 均可 |
| Python | 3.10+ |
| 内存 | 2C2G 起（opencv 抽帧会占内存） |
| 端口 | 内网 5820；公网 80/443（或开发者空间端口映射） |
| 系统库 | `libgl1 libglib2.0-0 fonts-noto-cjk`（opencv/PIL 中文） |

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip libgl1 libglib2.0-0 fonts-noto-cjk
```

## 2. 方式 A：一键脚本（推荐）

```bash
sudo APP_DIR=/opt/xide bash deploy/deploy.sh
```

脚本会：clone/更新代码 → 建 venv → 装依赖 → 首次 seed → gunicorn 启动 → 健康检查。

- [ ] `curl http://127.0.0.1:5820/api/health` 返回 `{"ok":true,"service":"xide"}`
- [ ] 日志：`/opt/xide/server.log`

## 3. 方式 B：systemd 常驻

```bash
sudo cp deploy/xide.service /etc/systemd/system/
sudo cp deploy/env.production.example /opt/xide/.env   # 按需填写
sudo systemctl daemon-reload
sudo systemctl enable --now xide
sudo systemctl status xide
```

## 4. 方式 C：Docker

```bash
mkdir -p /opt/xide/data
cp deploy/env.production.example /opt/xide/.env
docker build -t xide .
docker run -d --name xide -p 5820:5820 \
  -v /opt/xide/data:/app/data \
  --env-file /opt/xide/.env \
  xide
docker exec xide python seed.py --reset   # 首次：空挂载目录需要 seed
```

> `.dockerignore` 已排除 `.env`、`.codearts-agent.env`、`data/`，不会把密钥打进镜像。

## 5. Nginx + HTTPS

```bash
sudo cp deploy/nginx-xide.conf /etc/nginx/conf.d/xide.conf
sudo nginx -t && sudo systemctl reload nginx
```

- 华为云 SSL 证书：控制台申请后配置 443；
- 或 `sudo certbot --nginx -d your.domain`。
- 启用 HTTPS 后：`/opt/xide/.env` 设 `ZX_COOKIE_SECURE=1`，重启服务。

## 6. 华为 AI 开发者空间里部署

1. 打开 <https://devstation.developer.huaweicloud.com/aidevspace>，登录；
2. 进入「云主机 / 开发桌面」或带终端的 Notebook；
3. 在终端执行：

```bash
git clone https://codehub.devcloud.cn-north-4.huaweicloud.com/a536e0133fe04108987565f2a828822c/xide-campus-learning.git /opt/xide
cd /opt/xide
bash deploy/deploy.sh
```

4. 端口：
   - 若开发者空间支持端口映射/公网访问，映射 5820 或 80/443；
   - 若不支持，先用 `curl http://127.0.0.1:5820/api/health` 做内部验证，再通过其 Web 预览功能打开。
5. 验证：

```bash
BASE=http://127.0.0.1:5820 bash deploy/verify.sh
```

## 7. 已知边界（务必如实写进材料）

- 当前是 **SQLite + 本地文件**，适合单实例演示；多副本需换 RDS/共享存储。
- **RDS / Redis / OBS 代码尚未接入**，不要写成“已使用”。
- `RDS/Redis/OBS` 若要做，需先改 `db.py` 与媒体层；参见 `docs/HUAWEI-CLOUD.md`。
- `/media` 视频需登录、图片匿名可读（兼容移动端 Image）。
- 未配置 LLM 时走规则引擎；配置后需在目标网络验证 `llm.test_provider()`。

## 8. 部署证据（补 CodeArts 第 5 环节）

留存：

- [ ] `docker build` / `deploy.sh` 完整日志
- [ ] `curl /api/health` 输出
- [ ] 公网 URL 或开发者空间访问地址截图
- [ ] 登录后首页截图
- [ ] 更新 `docs/evidence/codearts-agent/05-部署上线.json`（把“未实际构建”改为真实结果）

## 9. 常见问题

| 现象 | 处理 |
|---|---|
| `ModuleNotFoundError: cv2` | 装 `libgl1 libglib2.0-0`；确认 `pip install -r requirements.txt` |
| 502 Bad Gateway | `gunicorn` 未启动或端口不对；看 `server.log` |
| 登录后立刻退出 | HTTPS 下 `ZX_COOKIE_SECURE=1` 必须配合 HTTPS；HTTP 下保持 0 |
| 数据重启丢失 | 没挂载 `/app/data` 或没在宿主机持久化 `data/` |
| SQLite `database is locked` | 只用 `-w 1`，不要多 worker；高并发再换 RDS |