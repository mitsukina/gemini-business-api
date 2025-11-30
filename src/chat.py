import json
import re
import hashlib
import random
import base64
from typing import List

from fastapi import HTTPException

from config import logger, MODEL_MAPPING, http_client
from auth import Account, accounts
from session import create_google_session, upload_context_file, list_session_files, download_file
from utils import get_common_headers
from models import Message

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

async def parse_last_message(messages: List[Message]):
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
                if url.startswith("data:"):
                    match = re.match(r"data:(image/[^;]+);base64,(.+)", url)
                    if match:
                        images.append({"mime": match.group(1), "data": match.group(2)})
                    else:
                        logger.warning(f"⚠️ 暂不支持非 Base64 数据URI: {url[:30]}...")
                elif url.startswith(("http://", "https://")):
                    # 下载远程图片
                    try:
                        r = await http_client.get(url)
                        if r.status_code == 200:
                            mime_type = r.headers.get("content-type", "image/png")
                            b64_data = base64.b64encode(r.content).decode()
                            images.append({"mime": mime_type, "data": b64_data})
                        else:
                            logger.warning(f"⚠️ 下载图片失败: {url}")
                    except Exception as e:
                        logger.warning(f"⚠️ 下载图片异常: {e}")
                else:
                    logger.warning(f"⚠️ 暂不支持的图片URL格式: {url[:30]}...")

    return text_content, images

def build_full_context_text(messages: List[Message]) -> str:
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

def create_chunk(id: str, created: int, model: str, delta: dict, finish_reason: str = None) -> str:
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
        print(f"DEBUG: Yielding role chunk: {chunk}")
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
                print(f"DEBUG: Yielding text chunk: {chunk}")
                if is_stream:
                    yield f"data: {chunk}\n\n"
    
    if is_stream:
        final_chunk = create_chunk(chat_id, created_time, model_name, {}, "stop")
        print(f"DEBUG: Yielding final text chunk: {final_chunk}")
        yield f"data: {final_chunk}\n\n"