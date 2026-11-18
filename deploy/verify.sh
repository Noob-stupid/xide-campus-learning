#!/usr/bin/env bash
# 部署后自检：健康检查 + 登录页 + 媒体鉴权
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:5820}"

echo "== health =="
curl -fsS "$BASE/api/health"
echo
echo "== login page =="
curl -fsS -o /dev/null -w "HTTP %{http_code}\n" "$BASE/login"
echo "== media (video should be 401 without login) =="
curl -s -o /dev/null -w "HTTP %{http_code}\n" "$BASE/media/content_1/video.mp4"
echo "== media (image should be 404 or 200, not 401) =="
curl -s -o /dev/null -w "HTTP %{http_code}\n" "$BASE/media/content_1/frames/f_01.jpg"

echo
echo "下一步人工验证："
echo "  1) 浏览器打开 $BASE/login，用 student/123456 走预约→签到→结束→接棒"
echo "  2) reviewer/123456 审核；admin/123456 编排"
echo "  3) 若配置了 LLM：python -c \"from services import llm; print(llm.test_provider())\""