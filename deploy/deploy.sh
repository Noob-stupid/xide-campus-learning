#!/usr/bin/env bash
# 习得 KeepLit · 云主机一键部署（venv + gunicorn，无需 Docker）
# 用法：sudo bash deploy/deploy.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/xide}"
PORT="${PORT:-5820}"
REPO="${REPO:-https://codehub.devcloud.cn-north-4.huaweicloud.com/a536e0133fe04108987565f2a828822c/xide-campus-learning.git}"

mkdir -p "$APP_DIR"
cd "$APP_DIR"

if [ ! -d .git ]; then
  git clone "$REPO" .
else
  git pull --ff-only
fi

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
pip install -U pip
pip install -r requirements.txt gunicorn

# 首次部署：没有数据库时生成演示数据（会清空已有 data）
if [ ! -f data/zhixue.db ]; then
  python seed.py --reset
fi

export ZX_HOST=0.0.0.0
export ZX_PORT="$PORT"
export ZX_ENABLE_SWEEPER=1

# 先停旧进程（如果存在）
if [ -f .gunicorn.pid ]; then
  kill "$(cat .gunicorn.pid)" 2>/dev/null || true
  rm -f .gunicorn.pid
fi

nohup gunicorn -b "0.0.0.0:$PORT" -w 1 --threads 4 --pid .gunicorn.pid app:app > server.log 2>&1 &
sleep 2

echo "启动完成，检查："
curl -fsS "http://127.0.0.1:$PORT/api/health" || {
  echo "健康检查失败，查看 $APP_DIR/server.log"
  exit 1
}
echo
echo "本机验证： http://127.0.0.1:$PORT/login"
echo "公网访问： 需在安全组/端口映射放行 $PORT，或按 deploy/nginx-xide.conf 反代 80/443"