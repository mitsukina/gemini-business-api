import uuid
import time
import base64
from typing import List, Optional

from fastapi import HTTPException

from config import logger, http_client, IMAGE_SAVE_DIR, BASE_URL
from auth import Account
from utils import get_common_headers
from models import ChatImage

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

    logger.info(f"上传图片 [{mime_type}] 到 Session...")
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

async def save_generated_image(account: Account, session_name: str, file_id: str, file_name: Optional[str], mime_type: str, chat_id: str, image_index: int = 1) -> ChatImage:
    """下载并保存生成的图片，返回本地URL"""
    session_id = session_name.split("/")[-1]
    image_data = await download_file(account, session_id, file_id)
    if not image_data:
        raise HTTPException(500, "Failed to download image")
    
    # 解码base64
    try:
        image_bytes = base64.b64decode(image_data)
    except Exception:
        image_bytes = image_data  # 假设已经是bytes
    
    # 保存到本地
    ext = mime_type.split('/')[-1] if '/' in mime_type else "png"
    filename = f"{chat_id}_{image_index}.{ext}"
    file_path = IMAGE_SAVE_DIR / filename
    with open(file_path, "wb") as f:
        f.write(image_bytes)
    
    # 返回本地URL
    url = f"{BASE_URL}/images/{filename}"
    return ChatImage(
        url=url,
        filename=filename,
        mime_type=mime_type,
        size=len(image_bytes),
        chat_id=chat_id,
        image_index=image_index
    )