import os
import json
import time
import logging
from typing import Any

import httpx
from fastapi import HTTPException
from fastapi.responses import JSONResponse

LARK_API_BASE = "https://open.feishu.cn/open-apis"
APP_ID = os.getenv("FEISHU_APP_ID", "")
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
VERIFICATION_TOKEN = os.getenv("FEISHU_VERIFICATION_TOKEN", "")
ENCRYPT_KEY = os.getenv("FEISHU_ENCRYPT_KEY", "")

TENANT_TOKEN_CACHE = {"token": "", "expire_at": 0.0}

logger = logging.getLogger("feishu_bot.feishu_api")


async def get_tenant_access_token() -> str:
    now = time.time()
    if TENANT_TOKEN_CACHE["token"] and now < TENANT_TOKEN_CACHE["expire_at"] - 60:
        return TENANT_TOKEN_CACHE["token"]
    url = f"{LARK_API_BASE}/auth/v3/tenant_access_token/internal"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            url, json={"app_id": APP_ID, "app_secret": APP_SECRET}
        )
        data = resp.json()
        if data.get("code", 0) != 0:
            logger.error(f"get_tenant_access_token failed: {data}")
            raise HTTPException(
                status_code=500, detail=f"get tenant_access_token failed: {data}"
            )
        token = data["tenant_access_token"]
        expire = data["expire"]
        TENANT_TOKEN_CACHE["token"] = token
        TENANT_TOKEN_CACHE["expire_at"] = now + expire
        logger.debug("get_tenant_access_token success, expire=%s", expire)
        return token



def extract_plain_text(message_event: dict):
    message = message_event.get("message", {})
    chat_id = message.get("chat_id", "")
    sender = message.get("sender", {}).get("sender_id", {})
    sender_id = sender.get("user_id") or sender.get("open_id") or ""
    content_raw = message.get("content", "{}")
    try:
        content = json.loads(content_raw)
    except Exception:
        content = {}
    text = content.get("text", "")
    return chat_id, sender_id, text


def extract_message_payload(message_event: dict) -> tuple[str, str, str, list[str], str]:
    """
    提取消息的核心信息：
    - chat_id, sender_id
    - text（尽可能抽取纯文本/富文本里的可读文字）
    - image_keys（image 或 post/img）
    - msg_type（text/image/post/...）
    """
    message = message_event.get("message", {}) or {}
    chat_id = message.get("chat_id", "")
    sender = message.get("sender", {}).get("sender_id", {}) or {}
    sender_id = sender.get("user_id") or sender.get("open_id") or ""

    msg_type = (
        message.get("message_type")
        or message.get("msg_type")
        or message.get("type")
        or ""
    )
    content_raw = message.get("content", "{}")
    try:
        content = json.loads(content_raw)
    except Exception:
        content = {}

    text = ""
    image_keys: list[str] = []

    if isinstance(content, dict):
        # text 消息
        if "text" in content and isinstance(content.get("text"), str):
            text = content.get("text") or ""
        # image 消息
        if "image_key" in content:
            img_key = content.get("image_key")
            if isinstance(img_key, str) and img_key.strip():
                image_keys.append(img_key.strip())
                logger.debug("extract_message_payload found image_key=%s", img_key)
            else:
                logger.warning(
                    "extract_message_payload invalid image_key type/value: %s", type(img_key)
                )

        # post 富文本：
        # 1）有语言包装：{"zh_cn": {"title": "...", "content": [...]}}
        # 2）无语言包装：{"title": "...", "content": [...]}
        def _parse_post_lang_obj(lang_obj: dict[str, Any]):
            nonlocal text, image_keys
            if not isinstance(lang_obj, dict):
                return
            title_inner = lang_obj.get("title") or ""
            if title_inner:
                text = (text + "\n" + title_inner).strip() if text else title_inner
            blocks = lang_obj.get("content") or []
            texts_local: list[str] = []
            try:
                for para in blocks:
                    if not isinstance(para, list):
                        continue
                    for el in para:
                        if not isinstance(el, dict):
                            continue
                        tag = el.get("tag")
                        if tag == "text" and isinstance(el.get("text"), str):
                            texts_local.append(el.get("text"))
                        elif tag == "img":
                            img_key_inner = el.get("image_key")
                            if isinstance(img_key_inner, str) and img_key_inner.strip():
                                image_keys.append(img_key_inner.strip())
                                logger.debug(
                                    "extract_message_payload found post img image_key=%s",
                                    img_key_inner,
                                )
                            else:
                                logger.warning(
                                    "extract_message_payload invalid post img image_key: %s",
                                    type(img_key_inner),
                                )
            except Exception:
                pass
            if texts_local:
                joined_inner = "".join(texts_local).strip()
                if joined_inner:
                    text = (text + "\n" + joined_inner).strip() if text else joined_inner

        if any(k in content for k in ("zh_cn", "en_us")):
            lang_obj = content.get("zh_cn") or content.get("en_us") or {}
            _parse_post_lang_obj(lang_obj)
        # 无语言包装的 post（你的日志里就是这种结构）
        elif "content" in content and isinstance(content.get("content"), list):
            _parse_post_lang_obj(content)

    # 兜底：如果 msg_type 空但抽到了 image_key，认为是 image
    if not msg_type and image_keys:
        msg_type = "image"

    logger.debug(
        "extract_message_payload result chat_id=%s msg_type=%s text_len=%s image_keys=%s",
        chat_id,
        msg_type,
        len(text),
        image_keys,
    )
    return chat_id, sender_id, text, image_keys, msg_type


def mentioned_bot(message_event: dict) -> bool:
    """
    Try multiple strategies to detect bot mention:
    1) mentions[].id.app_id == FEISHU_APP_ID (best if present)
    2) mentions[].name matches BOT_NAME (fallback)
    3) text contains @BOT_NAME (last resort)
    """
    bot_app_id = os.getenv("FEISHU_APP_ID", "")
    bot_name = os.getenv("BOT_NAME", "群助手")

    message = message_event.get("message", {})
    mentions = message.get("mentions") or []

    for m in mentions:
        idinfo = m.get("id") or {}
        if idinfo.get("app_id") and idinfo.get("app_id") == bot_app_id:
            logger.debug("mentioned_bot by app_id")
            return True

    for m in mentions:
        name = (m.get("name") or "").strip()
        if name and name == bot_name:
            logger.debug("mentioned_bot by name=%s", bot_name)
            return True

    # last resort: text contains @BOT_NAME
    content_raw = message.get("content", "{}")
    try:
        content = json.loads(content_raw)
    except Exception:
        content = {}
    text = content.get("text", "")
    if f"@{bot_name}" in text:
        logger.debug("mentioned_bot by text contains @%s", bot_name)
        return True
    return False


async def send_text_to_chat(chat_id: str, text: str):
    token = await get_tenant_access_token()
    url = f"{LARK_API_BASE}/im/v1/messages?receive_id_type=chat_id"
    payload = {
        "receive_id": chat_id,
        "msg_type": "text",
        "content": json.dumps({"text": text}, ensure_ascii=False),
    }
    headers = {"Authorization": f"Bearer {token}"}
    logger.debug(
        "send_text_to_chat chat_id=%s text='%s...'",
        chat_id,
        text[:80],
    )
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, headers=headers, json=payload)
        data = r.json()
        if data.get("code") != 0:
            logger.error("[send_text_to_chat] error: %s", data)


async def upload_image(image_bytes: bytes) -> tuple[str, str]:
    """
    上传图片到飞书，获取 image_key
    
    Args:
        image_bytes: 图片字节数据
        
    Returns:
        (image_key, error_message) 元组，成功时 error_message 为空字符串
    """
    token = await get_tenant_access_token()
    url = f"{LARK_API_BASE}/im/v1/images"
    headers = {"Authorization": f"Bearer {token}"}
    
    # 构建 multipart/form-data 请求
    files = {
        "image": ("image.png", image_bytes, "image/png"),
    }
    data = {
        "image_type": "message",  # 消息图片
    }
    
    logger.debug(f"upload_image size={len(image_bytes)} bytes")
    
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, headers=headers, files=files, data=data)
        try:
            resp_data = r.json()
        except Exception:
            error_msg = f"Failed to parse response: {r.text[:200]}"
            logger.error(f"upload_image error: {error_msg}")
            return "", error_msg
        
        if r.status_code >= 300 or resp_data.get("code") != 0:
            error_msg = resp_data.get("msg", f"HTTP {r.status_code}")
            logger.error(f"upload_image failed: {error_msg}, response={resp_data}")
            return "", error_msg
        
        image_key = resp_data.get("data", {}).get("image_key", "")
        if not image_key:
            error_msg = "No image_key in response"
            logger.error(f"upload_image error: {error_msg}")
            return "", error_msg
        
        logger.info(f"upload_image success, image_key={image_key}")
        return image_key, ""


async def send_image_via_base64(chat_id: str, image_bytes: bytes, caption: str = ""):
    """
    通过 Base64 编码直接发送图片消息（富文本格式）
    
    Args:
        chat_id: 群聊ID
        image_bytes: 图片字节数据
        caption: 图片说明文字（可选）
    """
    import base64
    
    if not image_bytes:
        logger.error("send_image_via_base64: empty image_bytes")
        return
    
    token = await get_tenant_access_token()
    url = f"{LARK_API_BASE}/im/v1/messages?receive_id_type=chat_id"
    
    try:
        # Base64 编码图片
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # 构建富文本消息（post 格式）
        # 飞书支持在 post 消息中内嵌 Base64 图片
        post_content = {
            "zh_cn": {
                "title": caption or "生成的图片",
                "content": [
                    [
                        {
                            "tag": "img",
                            "image_key": "",  # 使用 base64 时可以为空
                            "extra": {
                                "image_type": "png",
                                "original_url": f"data:image/png;base64,{image_base64}"
                            }
                        }
                    ]
                ]
            }
        }
        
        payload = {
            "receive_id": chat_id,
            "msg_type": "post",
            "content": json.dumps({"post": post_content}, ensure_ascii=False),
        }
        
        headers = {"Authorization": f"Bearer {token}"}
        logger.debug(f"send_image_via_base64 chat_id={chat_id} image_size={len(image_bytes)} bytes")
        
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, headers=headers, json=payload)
            data = r.json()
            if data.get("code") != 0:
                logger.error(f"send_image_via_base64 error: {data}")
                return
            
            logger.info(f"send_image_via_base64 success chat_id={chat_id}")
            
    except Exception as e:
        logger.error(f"send_image_via_base64 exception: {e}", exc_info=True)


async def send_image_to_chat(chat_id: str, image_key: str, caption: str = ""):
    """
    发送图片消息到群聊
    
    Args:
        chat_id: 群聊ID
        image_key: 图片key（通过 upload_image 获取）
        caption: 图片说明文字（可选）
    """
    token = await get_tenant_access_token()
    url = f"{LARK_API_BASE}/im/v1/messages?receive_id_type=chat_id"
    
    payload = {
        "receive_id": chat_id,
        "msg_type": "image",
        "content": json.dumps({"image_key": image_key}, ensure_ascii=False),
    }
    
    headers = {"Authorization": f"Bearer {token}"}
    logger.debug(f"send_image_to_chat chat_id={chat_id} image_key={image_key}")
    
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, headers=headers, json=payload)
        data = r.json()
        if data.get("code") != 0:
            logger.error(f"[send_image_to_chat] error: {data}")
            return
        
        # 如果有说明文字，再发送一条文本消息
        if caption:
            await send_text_to_chat(chat_id, caption)


async def get_message_text_by_id(message_id: str) -> str:
    """
    根据 message_id 调用飞书接口获取消息文本，用于还原“回复/引用”的原文。
    需要在飞书开发者后台为应用开启读取消息的权限（例如 im:message）。
    """
    if not message_id:
        return ""
    token = await get_tenant_access_token()
    url = f"{LARK_API_BASE}/im/v1/messages/{message_id}"
    headers = {"Authorization": f"Bearer {token}"}
    logger.debug("get_message_text_by_id message_id=%s", message_id)
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=headers)
        try:
            data = r.json()
        except Exception:
            logger.error(
                "get_message_text_by_id parse json error status=%s text=%s",
                r.status_code,
                r.text[:200],
            )
            return ""
    if r.status_code >= 300 or data.get("code") not in (0, None):
        logger.error("get_message_text_by_id http/error status=%s body=%s", r.status_code, data)
        return ""

    msg = (data.get("data") or {}).get("message") or {}
    content_raw = msg.get("content", "{}")
    try:
        content = json.loads(content_raw)
    except Exception:
        content = {}
    text = content.get("text") or ""
    logger.debug(
        "get_message_text_by_id success message_id=%s text_len=%s",
        message_id,
        len(text),
    )
    return text


async def get_message_image_bytes(message_id: str, image_key: str) -> tuple[bytes, str]:
    """
    按“获取消息中的资源文件”规范，通过 message_id + image_key 拉取消息里的图片。
    接口：GET /open-apis/im/v1/messages/:message_id/resources/:file_key?type=image
    注意：需要应用具备 im:message / im:message:readonly / im:message.history:readonly 等权限。
    返回：(bytes, mime)
    """
    if not message_id or not isinstance(message_id, str):
        logger.warning("get_message_image_bytes invalid message_id: %s", message_id)
        return b"", ""
    if not image_key or not isinstance(image_key, str):
        logger.warning("get_message_image_bytes invalid image_key: %s", image_key)
        return b"", ""
    message_id = message_id.strip()
    image_key = image_key.strip()
    if not message_id or not image_key:
        logger.warning(
            "get_message_image_bytes empty ids after strip message_id=%s image_key=%s",
            message_id,
            image_key,
        )
        return b"", ""

    token = await get_tenant_access_token()
    # 文档：https://open.feishu.cn/open-apis/im/v1/messages/:message_id/resources/:file_key?type=image
    url = f"{LARK_API_BASE}/im/v1/messages/{message_id}/resources/{image_key}?type=image"
    headers = {"Authorization": f"Bearer {token}"}
    logger.debug(
        "get_message_image_bytes message_id=%s image_key=%s url=%s",
        message_id,
        image_key,
        url,
    )
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, headers=headers)
        if r.status_code >= 300:
            # 尝试解析错误信息
            try:
                data = r.json()
            except Exception:
                data = r.text[:200]
            logger.error(
                "get_message_image_bytes http error status=%s message_id=%s image_key=%s body=%s",
                r.status_code,
                message_id,
                image_key,
                data,
            )
            return b"", ""
        mime = (r.headers.get("content-type") or "").split(";")[0].strip()
        logger.debug(
            "get_message_image_bytes success message_id=%s image_key=%s mime=%s size=%s",
            message_id,
            image_key,
            mime,
            len(r.content),
        )
        return r.content, mime
