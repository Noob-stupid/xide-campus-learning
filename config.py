# -*- coding: utf-8 -*-
"""智学空间 · 全局配置。

所有路径都从本文件位置推导，换机器/换盘符无需改代码。
"""
import os
import secrets


_ALIASES = {
    'DEEPSEEK_BASE_URL': 'ZX_LLM_BASE_URL',
    'DEEPSEEK_API_KEY': 'ZX_LLM_API_KEY',
    'DEEPSEEK_MODEL': 'ZX_LLM_MODEL',
}


def _load_dotenv():
    """读取项目根 .env 与 .codearts-agent.env，不覆盖已有环境变量。

    .codearts-agent.env 里的 DEEPSEEK_* 会额外映射为应用使用的 ZX_LLM_*，
    这样本地/CodeArts 已有的模型配置无需复制。
    """
    base = os.path.dirname(os.path.abspath(__file__))
    for name in ('.env', '.codearts-agent.env'):
        path = os.path.join(base, name)
        if not os.path.exists(path):
            continue
        try:
            for raw in open(path, encoding='utf-8'):
                line = raw.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if not k:
                    continue
                if k not in os.environ:
                    os.environ[k] = v
                target = _ALIASES.get(k)
                if target and target not in os.environ:
                    os.environ[target] = v
        except Exception:
            pass


_load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("ZX_DATA_DIR") or os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "zhixue.db")
MEDIA_DIR = os.path.join(DATA_DIR, "media")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

HOST = os.environ.get("ZX_HOST", "0.0.0.0")
PORT = int(os.environ.get("ZX_PORT", "5820"))
def _secret_key():
    """优先环境变量；否则在 data/ 下生成并复用随机 key，避免硬编码默认密钥。"""
    env = os.environ.get("ZX_SECRET_KEY")
    if env:
        return env
    path = os.path.join(DATA_DIR, ".secret_key")
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                val = fh.read().strip()
            if val:
                return val
    except Exception:
        pass
    val = secrets.token_hex(32)
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(val)
    except Exception:
        pass
    return val


SECRET_KEY = _secret_key()

# 设备上报（可选加固）：设置后 /api/sensor/* 需带 X-Sensor-Token
SENSOR_TOKEN = os.environ.get("ZX_SENSOR_TOKEN", "")

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
