import json
import time
import asyncio
import base64
import os
from typing import List, Optional

from fastapi import HTTPException

from config import logger, http_client
from utils import create_jwt

class JWTManager:
    def __init__(self, secure_c_ses: str, host_c_oses: Optional[str], csesidx: str):
        self.secure_c_ses = secure_c_ses
        self.host_c_oses = host_c_oses
        self.csesidx = csesidx
        self.jwt: str = ""
        self.expires: float = 0
        self._lock = asyncio.Lock()

    async def get(self) -> str:
        async with self._lock:
            if time.time() > self.expires:
                await self._refresh()
            return self.jwt

    async def _refresh(self) -> None:
        cookie = f"__Secure-C_SES={self.secure_c_ses}"
        if self.host_c_oses:
            cookie += f"; __Host-C_OSES={self.host_c_oses}"
        
        logger.debug("🔑 正在刷新 JWT...")
        r = await http_client.get(
            "https://business.gemini.google/auth/getoxsrf",
            params={"csesidx": self.csesidx},
            headers={
                "cookie": cookie,
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
                "referer": "https://business.gemini.google/"
            },
        )
        if r.status_code != 200:
            logger.error(f"❌ getoxsrf 失败: {r.status_code} {r.text}")
            raise HTTPException(r.status_code, "getoxsrf failed")
        
        txt = r.text[4:] if r.text.startswith(")]}'") else r.text
        data = json.loads(txt)

        key_bytes = base64.urlsafe_b64decode(data["xsrfToken"] + "==")
        self.jwt     = create_jwt(key_bytes, data["keyId"], self.csesidx)
        self.expires = time.time() + 270
        logger.info(f"✅ JWT 刷新成功")

def parse_cookies(cookies_str: str) -> dict:
    """解析cookies字符串，提取需要的参数"""
    cookies = {}
    for cookie in cookies_str.split(';'):
        cookie = cookie.strip()
        if '=' in cookie:
            name, value = cookie.split('=', 1)
            cookies[name.strip()] = value.strip()
    
    # 提取需要的参数
    secure_c_ses = cookies.get('__Secure-C_SES')
    host_c_oses = cookies.get('__Host-C_OSES')
    
    if not secure_c_ses:
        raise ValueError("❌ cookies中缺少必要的参数: __Secure-C_SES")
    
    return {
        'secure_c_ses': secure_c_ses,
        'host_c_oses': host_c_oses
    }

class Account:
    def __init__(self, data: dict):
        self.name = data['name']
        self.config_id = data['config_id']
        
        # 检查必要的参数
        if 'cookies' not in data:
            raise ValueError(f"❌ 账户 {data.get('name', 'unknown')} 缺少必要的参数: cookies")
        if 'csesidx' not in data:
            raise ValueError(f"❌ 账户 {data.get('name', 'unknown')} 缺少必要的参数: csesidx")
        if 'project_id' not in data:
            raise ValueError(f"❌ 账户 {data.get('name', 'unknown')} 缺少必要的参数: project_id")
        
        # 解析cookies字符串
        parsed = parse_cookies(data['cookies'])
        self.secure_c_ses = parsed['secure_c_ses']
        self.host_c_oses = parsed['host_c_oses']
        # 使用config中明确指定的csesidx
        self.csesidx = data['csesidx']
        self.project_id = data['project_id']
        
        self.jwt_mgr = JWTManager(self.secure_c_ses, self.host_c_oses, self.csesidx)

def load_accounts() -> List[Account]:
    config_file = 'config.test.json' if os.path.exists('config.test.json') else 'config.json'
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"✅ 加载配置文件: {config_file}")
        return [Account(acc) for acc in data.get('accounts', [])]
    except FileNotFoundError:
        logger.error("❌ 配置文件未找到，请创建config.json或config.test.json")
        return []
    except Exception as e:
        logger.error(f"❌ 加载{config_file}失败: {e}")
        return []

accounts = load_accounts()