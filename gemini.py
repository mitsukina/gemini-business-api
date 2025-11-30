import json, time, hmac, hashlib, base64, os, asyncio, uuid, ssl, re, random
from datetime import datetime
from typing import List, Optional, Union, Dict, Any
import logging

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ---------- 日志配置 ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("gemini")

# ---------- 账户和JWT管理 ----------
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
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        return [Account(acc) for acc in data.get('accounts', [])]
    except FileNotFoundError:
        logger.error("❌ config.json 未找到，请创建配置文件")
        return []
    except Exception as e:
        logger.error(f"❌ 加载config.json失败: {e}")
        return []

accounts = load_accounts()

# ---------- 配置 ----------
TIMEOUT_SECONDS = 600
PROXY = os.getenv("PROXY") or "http://127.0.0.1:10808"

# ---------- 模型映射配置 ----------
MODEL_MAPPING = {
    "gemini-auto": None,
    "gemini-2.5-flash": "gemini-2.5-flash",
    "gemini-2.5-pro": "gemini-2.5-pro",
    "gemini-3-pro-preview": "gemini-3-pro-preview"
}

# ---------- 全局 Session 缓存 ----------
SESSION_CACHE: Dict[str, dict] = {}
CHAT_ID_TO_ACCOUNT: Dict[str, str] = {}

# ---------- 负载均衡 ----------
last_account_index = -1

# ---------- HTTP 客户端 ----------
http_client = httpx.AsyncClient(
    proxies=PROXY,
    verify=False,
    http2=False,
    timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=60.0),
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=50)
)

# ---------- 工具函数 ----------
def get_common_headers(jwt: str) -> dict:
    return {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "authorization": f"Bearer {jwt}",
        "content-type": "application/json",
        "origin": "https://business.gemini.google",
        "referer": "https://business.gemini.google/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "x-server-timeout": "1800",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
    }

def urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")

def kq_encode(s: str) -> str:
    b = bytearray()
    for ch in s:
        v = ord(ch)
        if v > 255:
            b.append(v & 255)
            b.append(v >> 8)
        else:
            b.append(v)
    return urlsafe_b64encode(bytes(b))

def create_jwt(key_bytes: bytes, key_id: str, csesidx: str) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT", "kid": key_id}
    payload = {
        "iss": "https://business.gemini.google",
        "aud": "https://biz-discoveryengine.googleapis.com",
        "sub": f"csesidx/{csesidx}",
        "iat": now,
        "exp": now + 300,
        "nbf": now,
    }
    header_b64  = kq_encode(json.dumps(header, separators=(",", ":")))
    payload_b64 = kq_encode(json.dumps(payload, separators=(",", ":")))
    message     = f"{header_b64}.{payload_b64}"
    sig         = hmac.new(key_bytes, message.encode(), hashlib.sha256).digest()
    return f"{message}.{urlsafe_b64encode(sig)}"

# ---------- Session & File 管理 ----------
async def create_google_session(account: Account) -> str:
    jwt = await account.jwt_mgr.get()
    headers = get_common_headers(jwt)
    body = {
        "configId": account.config_id,
        "additionalParams": {"token": "-"},
        "createSessionRequest": {
            "session": {"name": "", "displayName": ""}
        }
    }
    
    logger.debug("🌐 申请新 Session...")
    r = await http_client.post(
        "https://biz-discoveryengine.googleapis.com/v1alpha/locations/global/widgetCreateSession",
        headers=headers,
        json=body,
    )
    if r.status_code != 200:
        logger.error(f"❌ createSession 失败: {r.status_code} {r.text}")
        raise HTTPException(r.status_code, "createSession failed")
    sess_name = r.json()["session"]["name"]
    return sess_name

async def upload_context_file(account: Account, session_name: str, mime_type: str, base64_content: str) -> str:
    """上传文件到指定 Session，返回 fileId"""
    jwt = await account.jwt_mgr.get()
    headers = get_common_headers(jwt)
    
    # 生成随机文件名
    ext = mime_type.split('/')[-1] if '/' in mime_type else "bin"
    file_name = f"upload_{int(time.time())}_{uuid.uuid4().hex[:6]}.{ext}"

    body = {
        "configId": account.config_id,
        "additionalParams": {"token": "-"},
        "addContextFileRequest": {
            "name": session_name,
            "fileName": file_name,
            "mimeType": mime_type,
            "fileContents": base64_content
        }
    }

    logger.info(f"� 上传图片 [{mime_type}] 到 Session...")
    r = await http_client.post(
        "https://biz-discoveryengine.googleapis.com/v1alpha/locations/global/widgetAddContextFile",
        headers=headers,
        json=body,
    )

    if r.status_code != 200:
        logger.error(f"❌ 上传文件失败: {r.status_code} {r.text}")
        raise HTTPException(r.status_code, f"Upload failed: {r.text}")
    
    data = r.json()
    file_id = data.get("addContextFileResponse", {}).get("fileId")
    logger.info(f"✅ 图片上传成功, ID: {file_id}")
    return file_id

async def list_session_files(account: Account, session_name: str, filter_str: str = "file_origin_type = AI_GENERATED") -> List[dict]:
    jwt = await account.jwt_mgr.get()
    headers = get_common_headers(jwt)
    body = {
        "configId": account.config_id,
        "additionalParams": {"token": "-"},
        "listSessionFileMetadataRequest": {
            "name": session_name,
            "filter": filter_str
        }
    }
    
    logger.debug("📋 列出会话文件...")
    r = await http_client.post(
        "https://biz-discoveryengine.googleapis.com/v1alpha/locations/global/widgetListSessionFileMetadata",
        headers=headers,
        json=body,
    )
    if r.status_code != 200:
        logger.error(f"❌ listSessionFiles 失败: {r.status_code} {r.text}")
        return []
    
    data = r.json()
    files = data.get("listSessionFileMetadataResponse", {}).get("fileMetadata", [])
    logger.info(f"✅ 找到 {len(files)} 个文件")
    return files

async def download_file(account: Account, session_id: str, file_id: str) -> bytes:
    jwt = await account.jwt_mgr.get()
    headers = get_common_headers(jwt)
    headers["x-goog-encode-response-if-executable"] = "base64"
    
    url = f"https://biz-discoveryengine.googleapis.com/download/v1alpha/projects/{account.project_id}/locations/global/collections/default_collection/engines/agentspace-engine/sessions/{session_id}:downloadFile?fileId={file_id}&alt=media"
    
    logger.debug(f"📥 下载文件 {file_id}...")
    r = await http_client.get(url, headers=headers)
    if r.status_code != 200:
        logger.error(f"❌ downloadFile 失败: {r.status_code} {r.text}")
        return b""
    
    logger.info(f"✅ 文件下载成功, 大小: {len(r.content)} bytes")
    return r.content

# ---------- 消息处理逻辑 ----------
def get_conversation_key(messages: List[dict]) -> str:
    if not messages: return "empty"
    # 仅使用第一条消息的内容生成指纹，忽略图片数据防止指纹过大
    first_msg = messages[0].copy()
    if isinstance(first_msg.get("content"), list):
        # 如果第一条是多模态，只取文本部分做 Hash
        text_part = "".join([x["text"] for x in first_msg["content"] if x["type"] == "text"])
        first_msg["content"] = text_part
    
    key_str = json.dumps(first_msg, sort_keys=True)
    return hashlib.md5(key_str.encode()).hexdigest()

def parse_last_message(messages: List['Message']):
    """解析最后一条消息，分离文本和图片"""
    if not messages:
        return "", []
    
    last_msg = messages[-1]
    content = last_msg.content
    
    text_content = ""
    images = [] # List of {"mime": str, "data": str_base64}

    if isinstance(content, str):
        text_content = content
    elif isinstance(content, list):
        for part in content:
            if part.get("type") == "text":
                text_content += part.get("text", "")
            elif part.get("type") == "image_url":
                url = part.get("image_url", {}).get("url", "")
                # 解析 Data URI: data:image/png;base64,xxxxxx
                match = re.match(r"data:(image/[^;]+);base64,(.+)", url)
                if match:
                    images.append({"mime": match.group(1), "data": match.group(2)})
                else:
                    logger.warning(f"⚠️ 暂不支持非 Base64 图片链接: {url[:30]}...")

    return text_content, images

def build_full_context_text(messages: List['Message']) -> str:
    """仅拼接历史文本，图片只处理当次请求的"""
    prompt = ""
    for msg in messages:
        role = "User" if msg.role in ["user", "system"] else "Assistant"
        content_str = ""
        if isinstance(msg.content, str):
            content_str = msg.content
        elif isinstance(msg.content, list):
            for part in msg.content:
                if part.get("type") == "text":
                    content_str += part.get("text", "")
                elif part.get("type") == "image_url":
                    content_str += "[图片]"
        
        prompt += f"{role}: {content_str}\n\n"
    return prompt

# ---------- OpenAI 兼容接口 ----------
app = FastAPI(title="Gemini-Business OpenAI Gateway")

class Message(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]]]

class ChatRequest(BaseModel):
    model: str = "gemini-auto"
    messages: List[Message]
    stream: bool = False
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 1.0

def create_chunk(id: str, created: int, model: str, delta: dict, finish_reason: Union[str, None]) -> str:
    chunk = {
        "id": id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": delta,
            "finish_reason": finish_reason
        }]
    }
    return json.dumps(chunk)

@app.get("/v1/models")
async def list_models():
    data = []
    now = int(time.time())
    for m in MODEL_MAPPING.keys():
        data.append({
            "id": m,
            "object": "model",
            "created": now,
            "owned_by": "google",
            "permission": []
        })
    return {"object": "list", "data": data}

@app.get("/v1/chat/completions/{chat_id}/account")
async def get_account(chat_id: str):
    account = CHAT_ID_TO_ACCOUNT.get(chat_id)
    if account:
        return {"account": account}
    else:
        raise HTTPException(status_code=404, detail="Chat ID not found")

@app.post("/v1/chat/completions")
async def chat(req: ChatRequest):
    # 1. 模型校验
    if req.model not in MODEL_MAPPING:
        raise HTTPException(status_code=404, detail=f"Model '{req.model}' not found.")

    # 2. 解析请求内容
    last_text, current_images = parse_last_message(req.messages)
    
    # 3. 选择账户 (负载均衡 - 轮询)
    global last_account_index
    last_account_index = (last_account_index + 1) % len(accounts)
    account = accounts[last_account_index]
    logger.info(f"🆕 开启新对话 [{req.model}] 使用账户: {account.name}")
    
    # 4. 锚定 Session - 每次都开新对话 (带重试机制)
    google_session = None
    session_retry_count = 0
    max_session_retries = 2
    
    while session_retry_count <= max_session_retries:
        try:
            google_session = await create_google_session(account)
            break  # 成功创建，跳出循环
        except Exception as e:
            session_retry_count += 1
            logger.warning(f"⚠️ 创建 Session 失败 (重试 {session_retry_count}/{max_session_retries}): {e}")
            
            if session_retry_count <= max_session_retries:
                # 选择其他账户
                available_accounts = [a for a in accounts if a != account]
                if not available_accounts:
                    available_accounts = accounts
                account = random.choice(available_accounts)
                logger.info(f"🔄 切换到账户: {account.name} 重新创建 Session")
            else:
                logger.error(f"❌ 创建 Session 最终失败，跳过请求")
                raise HTTPException(status_code=503, detail="Failed to create session after retries")
    
    # 新对话使用全量文本上下文 (图片只传当前的)
    text_to_send = build_full_context_text(req.messages)
    is_retry_mode = True

    chat_id = f"chatcmpl-{uuid.uuid4()}"
    created_time = int(time.time())

    # 封装生成器 (含图片上传和重试逻辑)
    async def response_wrapper(initial_session: str, initial_account: Account):
        current_text = text_to_send
        current_retry_mode = is_retry_mode
        
        # 图片 ID 列表 (每次 Session 变化都需要重新上传，因为 fileId 绑定在 Session 上)
        current_file_ids = []
        current_session = initial_session
        current_account = initial_account

        # A. 如果有图片且还没上传到当前 Session，先上传
        if current_images and not current_file_ids:
            for img in current_images:
                fid = await upload_context_file(current_account, current_session, img["mime"], img["data"])
                current_file_ids.append(fid)

        # B. 准备文本 (重试模式下发全文)
        if current_retry_mode:
            current_text = build_full_context_text(req.messages)

        # C. 发起对话
        async for chunk in stream_chat_generator(
            current_account,
            current_session, 
            current_text, 
            current_file_ids, 
            req.model, 
            chat_id, 
            created_time, 
            req.stream
        ):
            yield chunk

    if req.stream:
        return StreamingResponse(response_wrapper(google_session, account), media_type="text/event-stream")
    
    full_content = ""
    async for chunk_str in response_wrapper(google_session, account):
        if chunk_str.startswith("data: [DONE]"): break
        if chunk_str.startswith("data: "):
            try:
                data = json.loads(chunk_str[6:])
                delta = data["choices"][0]["delta"]
                if "content" in delta: full_content += delta["content"]
            except: pass

    # 检查是否有AI生成的图片，如果没有则重试
    print(f"Checking for AI generated files in session: {google_session}")
    ai_files = await list_session_files(account, google_session)
    print(f"Found {len(ai_files)} AI generated files")
    if not ai_files:
        print("⚠️ 未找到AI生成的文件，尝试重试...")
        # 跳到下一个账户重试
        current_index = accounts.index(account)
        next_index = (current_index + 1) % len(accounts)
        account = accounts[next_index]
        logger.info(f"🔄 重试使用账户: {account.name}")
        print(f"🔄 重试使用账户: {account.name}")
        # 重新创建session并调用
        google_session = await create_google_session(account)
        full_content = ""
        async for chunk_str in response_wrapper(google_session, account):
            if chunk_str.startswith("data: [DONE]"): break
            if chunk_str.startswith("data: "):
                try:
                    data = json.loads(chunk_str[6:])
                    delta = data["choices"][0]["delta"]
                    if "content" in delta: full_content += delta["content"]
                except: pass
        # 再次检查
        ai_files = await list_session_files(account, google_session)
        print(f"重试后找到 {len(ai_files)} AI generated files")
    
    if ai_files:
        for file_meta in ai_files:
            session_id = google_session.split("/")[-1]  # 提取session ID
            file_id = file_meta["fileId"]
            file_data = await download_file(account, session_id, file_id)
            if file_data:
                b64_data = file_data.decode()  # Already base64
                print(f"Setting full_content to generated image base64: {b64_data[:50]}...")
                full_content = b64_data  # 直接覆盖
                break  # 只处理第一个
            else:
                print(f"Failed to download file {file_id}")

    CHAT_ID_TO_ACCOUNT[chat_id] = account.name
    return {
        "id": chat_id,
        "object": "chat.completion",
        "created": created_time,
        "model": req.model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": full_content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    }

async def stream_chat_generator(account: Account, session: str, text_content: str, file_ids: List[str], model_name: str, chat_id: str, created_time: int, is_stream: bool = True):
    jwt = await account.jwt_mgr.get()
    headers = get_common_headers(jwt)
    
    body = {
        "configId": account.config_id,
        "additionalParams": {"token": "-"},
        "streamAssistRequest": {
            "session": session,
            "query": {"parts": [{"text": text_content}]},
            "filter": "",
            "fileIds": file_ids, # 注入文件 ID
            "answerGenerationMode": "NORMAL",
            "toolsSpec": {
                "webGroundingSpec": {},
                "toolRegistry": "default_tool_registry",
                "imageGenerationSpec": {},
                "videoGenerationSpec": {}
            },
            "languageCode": "zh-CN",
            "userMetadata": {"timeZone": "Asia/Shanghai"},
            "assistSkippingMode": "REQUEST_ASSIST"
        }
    }

    target_model_id = MODEL_MAPPING.get(model_name)
    if target_model_id:
        body["streamAssistRequest"]["assistGenerationConfig"] = {
            "modelId": target_model_id
        }

    if is_stream:
        chunk = create_chunk(chat_id, created_time, model_name, {"role": "assistant"}, None)
        yield f"data: {chunk}\n\n"

    r = await http_client.post(
        "https://biz-discoveryengine.googleapis.com/v1alpha/locations/global/widgetStreamAssist",
        headers=headers,
        json=body,
    )
    
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=f"Upstream Error {r.text}")

    try:
        data_list = r.json()
    except Exception as e:
        logger.error(f"❌ JSON 解析失败: {e}")
        raise HTTPException(status_code=502, detail="Invalid JSON response")

    for data in data_list:
        for reply in data.get("streamAssistResponse", {}).get("answer", {}).get("replies", []):
            text = reply.get("groundedContent", {}).get("content", {}).get("text", "")
            if text and not reply.get("thought"):
                chunk = create_chunk(chat_id, created_time, model_name, {"content": text}, None)
                if is_stream:
                    yield f"data: {chunk}\n\n"
    
    if is_stream:
        final_chunk = create_chunk(chat_id, created_time, model_name, {}, "stop")
        yield f"data: {final_chunk}\n\n"
        yield "data: [DONE]\n\n"

if __name__ == "__main__":
    if not accounts:
        print("Error: No accounts loaded.")
        exit(1)
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)