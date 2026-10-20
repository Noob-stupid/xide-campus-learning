# -*- coding: utf-8 -*-
"""智学空间 · 全局配置。

所有路径都从本文件位置推导，换机器/换盘符无需改代码。
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("ZX_DATA_DIR") or os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "zhixue.db")
MEDIA_DIR = os.path.join(DATA_DIR, "media")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

HOST = os.environ.get("ZX_HOST", "0.0.0.0")
PORT = int(os.environ.get("ZX_PORT", "5820"))
SECRET_KEY = os.environ.get("ZX_SECRET_KEY", "zhixue-space-demo-2026")

# 预约规则
MAX_ACTIVE_RESERVATIONS = 1
MIN_DURATION_MIN = 30
MAX_DURATION_MIN = 240
CHECKIN_TIMEOUT_MIN = 15

# 内容审核
FRAME_INTERVAL_SEC = 1.2          # 抽帧间隔（秒）
MAX_FRAMES = 12                   # 单条内容最多抽帧数
SUSPICIOUS_RISK = 0.55            # 可疑帧阈值

# 可选大模型（OpenAI 兼容）。不配置时全部走规则引擎，功能仍可用。
LLM_BASE_URL = os.environ.get("ZX_LLM_BASE_URL", "")
LLM_API_KEY = os.environ.get("ZX_LLM_API_KEY", "")
LLM_MODEL = os.environ.get("ZX_LLM_MODEL", "deepseek-chat")
LLM_TIMEOUT = int(os.environ.get("ZX_LLM_TIMEOUT", "20"))

for _d in (DATA_DIR, MEDIA_DIR, UPLOAD_DIR):
    os.makedirs(_d, exist_ok=True)

# 室外导航（可选）：配置高德 JS Key 后可在页面上显示高德地图/路线；不配置则用相对方向示意图。
AMAP_JS_KEY = os.environ.get('AMAP_JS_KEY', '')
AMAP_SECURITY_CODE = os.environ.get('AMAP_SECURITY_CODE', '')
