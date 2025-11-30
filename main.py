import json
import uuid
import time
import random
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from config import logger, MODEL_MAPPING, last_account_index, CHAT_ID_TO_ACCOUNT, SESSION_CACHE, IMAGE_SAVE_DIR
from models import Message, ChatRequest, ChatImage
from auth import Account, accounts
from chat import parse_last_message, build_full_context_text, create_chunk, stream_chat_generator, get_conversation_key
from session import create_google_session, list_session_files, save_generated_image, upload_context_file

def estimate_tokens(text: str) -> int:
    """简单估算token数，大约4个字符1个token"""
    return len(text) // 4

def calculate_usage(prompt_text: str, completion_text: str) -> dict:
    """计算token使用情况"""
    prompt_tokens = estimate_tokens(prompt_text)
    completion_tokens = estimate_tokens(completion_text)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens
    }

# ---------- OpenAI 兼容接口 ----------
app = FastAPI(title="Gemini-Business OpenAI Gateway")

# 挂载静态文件
app.mount("/images", StaticFiles(directory=str(IMAGE_SAVE_DIR)), name="images")

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

    # 2. 获取对话指纹
    conv_key = get_conversation_key([msg.dict() for msg in req.messages])
    
    # 3. 检查 Session 缓存
    cached_session = SESSION_CACHE.get(conv_key)
    google_session = None
    account = None
    
    if cached_session:
        # 检查缓存是否过期 (5分钟)
        if time.time() - cached_session["updated_at"] < 300:
            google_session = cached_session["session_id"]
            account_name = cached_session["account"]
            account = next((a for a in accounts if a.name == account_name), None)
            if account:
                logger.info(f"🔄 使用缓存 Session: {google_session} 账户: {account.name}")
    
    # 4. 如果没有缓存或过期，选择账户并创建新 Session
    if not google_session or not account:
        # 选择账户 (负载均衡 - 轮询)
        global last_account_index
        last_account_index = (last_account_index + 1) % len(accounts)
        account = accounts[last_account_index]
        logger.info(f"🆕 开启新对话 [{req.model}] 使用账户: {account.name}")
        
        # 创建新 Session
        google_session = await create_google_session(account)
        
        # 更新缓存
        SESSION_CACHE[conv_key] = {
            "session_id": google_session,
            "updated_at": time.time(),
            "account": account.name
        }

    # 5. 解析请求内容
    last_text, current_images = await parse_last_message(req.messages)
    
    # 新对话使用全量文本上下文 (图片只传当前的)
    text_to_send = build_full_context_text(req.messages)

    chat_id = f"chatcmpl-{uuid.uuid4()}"
    created_time = int(time.time())

    # 封装生成器 (含图片上传和重试逻辑)
    async def response_wrapper(session: str, acc: Account):
        # 图片 ID 列表 (每次 Session 变化都需要重新上传，因为 fileId 绑定在 Session 上)
        file_ids = []
        
        # 如果有图片，先上传
        if current_images:
            for img in current_images:
                fid = await upload_context_file(acc, session, img["mime"], img["data"])
                file_ids.append(fid)

        # 发起对话
        async for chunk in stream_chat_generator(
            acc,
            session, 
            text_to_send, 
            file_ids, 
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

    # 检查是否有AI生成的图片
    ai_files = await list_session_files(account, google_session)
    generated_images = []
    if ai_files:
        for i, file_meta in enumerate(ai_files):
            try:
                chat_image = await save_generated_image(
                    account, google_session, file_meta["fileId"], 
                    file_meta.get("fileName"), file_meta.get("mimeType", "image/png"), 
                    chat_id, i+1
                )
                generated_images.append(chat_image)
            except Exception as e:
                logger.error(f"保存图片失败: {e}")

    # 如果有生成的图片，返回第一个图片的URL，否则返回文本
    if generated_images:
        content = generated_images[0].url
    else:
        content = full_content

    CHAT_ID_TO_ACCOUNT[chat_id] = account.name
    
    # 计算usage
    usage = calculate_usage(text_to_send, content)
    
    return {
        "id": chat_id,
        "object": "chat.completion",
        "created": created_time,
        "model": req.model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": usage
    }