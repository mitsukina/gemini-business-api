import os
import logging
import httpx
import json
from typing import Dict, Any
from pathlib import Path

# ---------- 日志配置 ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("gemini")

# ---------- 读取应用配置 ----------
APP_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "app.json"
try:
    with open(APP_CONFIG_PATH, 'r', encoding='utf-8') as f:
        app_config = json.load(f)
except FileNotFoundError:
    logger.warning(f"⚠️ 应用配置文件未找到: {APP_CONFIG_PATH}，使用默认配置")
    app_config = {}
except Exception as e:
    logger.error(f"❌ 加载应用配置失败: {e}，使用默认配置")
    app_config = {}

# ---------- 配置 ----------
TIMEOUT_SECONDS = 600
PROXY = app_config.get("proxy", "http://127.0.0.1:10808")
HOST = app_config.get("host", "0.0.0.0")
PORT = app_config.get("port", 8000)
BASE_URL = app_config.get("base_url", "http://localhost:8000")

# ---------- 图片生成相关常量 ----------
BASE_DIR = Path(__file__).resolve().parent
IMAGE_SAVE_DIR = BASE_DIR.parent / "generated_images"
IMAGE_SAVE_DIR.mkdir(exist_ok=True)

# ---------- 模型映射配置 ----------
MODEL_MAPPING = {
    "gemini-auto": None,
    "gemini-2.5-flash": "gemini-2.5-flash",
    "gemini-2.5-pro": "gemini-2.5-pro",
    "gemini-3-pro-preview": "gemini-3-pro-preview"
}

# ---------- 全局 Session 缓存 ----------
# key: conversation_key -> {"session_id": str, "updated_at": float, "account": str}
SESSION_CACHE: Dict[str, Dict[str, Any]] = {}
CHAT_ID_TO_ACCOUNT: Dict[str, str] = {}

# ---------- 负载均衡 ----------
last_account_index = -1

# ---------- HTTP 客户端 ----------
http_client = httpx.AsyncClient(
    verify=False,
    http2=False,
    timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=60.0),
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=50)
)