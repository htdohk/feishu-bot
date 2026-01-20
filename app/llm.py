import logging
import base64
from typing import List, Optional

import httpx

from .config import config
from .constants import (
    HTTP_TIMEOUT_LLM,
    PLACEHOLDER_RESPONSE,
    PLACEHOLDER_RESPONSE_MULTIMODAL,
    LLM_ERROR_PARSE,
    LLM_ERROR_HTTP,
    LLM_ERROR_FORMAT,
)

logger = logging.getLogger("feishu_bot.llm")


async def call_llm(prompt: str, system: str = "", temperature: float = 0.2) -> str:
    if not (config.LLM_BASE_URL and config.LLM_API_KEY and config.LLM_MODEL):
        logger.warning(
            "LLM config missing, return placeholder. "
            "LLM_BASE_URL=%s LLM_MODEL=%s",
            config.LLM_BASE_URL,
            config.LLM_MODEL,
        )
        return PLACEHOLDER_RESPONSE.format(prompt=prompt[:200])
    
    url = config.LLM_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.LLM_MODEL,
        "temperature": temperature,
        "messages": [],
    }
    if system:
        payload["messages"].append({"role": "system", "content": system})
    payload["messages"].append({"role": "user", "content": prompt})

    logger.debug(
        "call_llm url=%s model=%s temp=%s prompt_len=%s",
        url,
        config.LLM_MODEL,
        temperature,
        len(prompt),
    )
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_LLM) as client:
        resp = await client.post(url, headers=headers, json=payload)
        try:
            data = resp.json()
        except Exception:
            logger.error("call_llm parse json error resp_text=%s", resp.text[:200])
            return LLM_ERROR_PARSE.format(text=resp.text[:200])
        if resp.status_code >= 300:
            logger.error("call_llm http error status=%s body=%s", resp.status_code, data)
            return LLM_ERROR_HTTP.format(data=data)
        try:
            content = data["choices"][0]["message"]["content"]
            logger.debug("call_llm success, content_len=%s", len(content))
            return content
        except Exception:
            logger.error("call_llm response format error data=%s", data)
            return LLM_ERROR_FORMAT.format(data=data)


def _image_data_url(image_bytes: bytes, mime: str) -> str:
    """
    将图片二进制转成 data URL，便于发给多模态模型（无需公网可访问 URL）。
    """
    if not image_bytes:
        return ""
    m = mime or "image/jpeg"
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{m};base64,{b64}"


async def call_llm_with_images(
    prompt: str,
    images: List[bytes],
    image_mimes: Optional[List[str]] = None,
    system: str = "",
    temperature: float = 0.2,
) -> str:
    """
    多模态：同时发送文字 + 多张图片给支持 vision 的模型。
    按 OpenAI Chat Completions 兼容格式组织 messages。
    """
    if not (config.LLM_BASE_URL and config.LLM_API_KEY and config.LLM_MODEL):
        logger.warning(
            "LLM config missing, return placeholder. "
            "LLM_BASE_URL=%s LLM_MODEL=%s",
            config.LLM_BASE_URL,
            config.LLM_MODEL,
        )
        return PLACEHOLDER_RESPONSE_MULTIMODAL.format(
            prompt=prompt[:200], count=len(images)
        )

    url = config.LLM_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    content_blocks = [{"type": "text", "text": prompt}]
    mimes = image_mimes or []
    for idx, img in enumerate(images):
        mime = mimes[idx] if idx < len(mimes) else "image/jpeg"
        data_url = _image_data_url(img, mime)
        if not data_url:
            continue
        content_blocks.append({"type": "image_url", "image_url": {"url": data_url}})

    payload = {
        "model": config.LLM_MODEL,
        "temperature": temperature,
        "messages": [],
    }
    if system:
        payload["messages"].append({"role": "system", "content": system})
    payload["messages"].append({"role": "user", "content": content_blocks})

    logger.debug(
        "call_llm_with_images url=%s model=%s temp=%s prompt_len=%s images=%s",
        url,
        config.LLM_MODEL,
        temperature,
        len(prompt),
        len(images),
    )
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_LLM) as client:
        resp = await client.post(url, headers=headers, json=payload)
        try:
            data = resp.json()
        except Exception:
            logger.error(
                "call_llm_with_images parse json error resp_text=%s", resp.text[:200]
            )
            return LLM_ERROR_PARSE.format(text=resp.text[:200])
        if resp.status_code >= 300:
            logger.error(
                "call_llm_with_images http error status=%s body=%s",
                resp.status_code,
                data,
            )
            return LLM_ERROR_HTTP.format(data=data)
        try:
            content = data["choices"][0]["message"]["content"]
            logger.debug("call_llm_with_images success, content_len=%s", len(content))
            return content
        except Exception:
            logger.error("call_llm_with_images response format error data=%s", data)
            return LLM_ERROR_FORMAT.format(data=data)
