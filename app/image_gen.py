"""
图片生成模块
支持文生图和图生图功能
"""
import logging
import base64
import re
from typing import Optional, Tuple, List
from io import BytesIO

import httpx

from .config import config
from .constants import (
    MSG_DRAW_NO_CONFIG,
    MSG_DRAW_ERROR,
    PROMPT_TEMPLATE_IMAGE_GEN,
    PROMPT_TEMPLATE_IMAGE_TO_IMAGE,
    IMAGE_SIZE_PRESETS,
)

logger = logging.getLogger("feishu_bot.image_gen")


def is_draw_request(text: str) -> bool:
    """
    判断文本是否包含绘图请求
    
    NOTE: 此函数已弃用，改用 semantic_intent.classify_intent() 进行 LLM-based 分析
    保留此函数仅作为备用，避免破坏兼容性
    
    Args:
        text: 用户输入文本
        
    Returns:
        是否为绘图请求（使用 LLM 分析的结果）
    """
    # 已移至 semantic_intent.classify_intent() 中进行 LLM 分析
    # 此函数不再使用
    logger.warning("is_draw_request() is deprecated, use semantic_intent.classify_intent() instead")
    return False


def has_reference_intent(text: str) -> bool:
    """
    判断是否有参考图片的意图
    
    Args:
        text: 用户输入文本
        
    Returns:
        是否有参考意图
    """
    if not text:
        return False
    
    # 注：此函数已不再使用，改用 semantic_intent.classify_intent() 进行LLM分析
    reference_keywords = [
        "参照", "参考", "基于", "根据", "仿照", "模仿", "类似",
        "像这样", "这种风格", "按照", "依据"
    ]
    return any(keyword in text for keyword in reference_keywords)


def parse_size_from_text(text: str, reference_size: Optional[Tuple[int, int]] = None) -> Tuple[int, int]:
    """
    从文本中解析图片尺寸
    
    Args:
        text: 用户输入文本
        reference_size: 参考图片尺寸 (width, height)
        
    Returns:
        (width, height) 元组
    """
    max_size = config.IMAGE_MAX_SIZE
    
    # 如果有参考图片，使用参考图片的比例
    if reference_size:
        ref_width, ref_height = reference_size
        # 保持比例，限制最大边
        if ref_width >= ref_height:
            width = max_size
            height = int(max_size * ref_height / ref_width)
        else:
            height = max_size
            width = int(max_size * ref_width / ref_height)
        return (width, height)
    
    # 检查预设尺寸关键词
    text_lower = text.lower()
    if "横" in text or "landscape" in text_lower or "宽" in text:
        return IMAGE_SIZE_PRESETS["landscape"]
    if "竖" in text or "portrait" in text_lower or "高" in text:
        return IMAGE_SIZE_PRESETS["portrait"]
    if "超宽" in text or "wide" in text_lower:
        return IMAGE_SIZE_PRESETS["wide"]
    if "超高" in text or "tall" in text_lower:
        return IMAGE_SIZE_PRESETS["tall"]
    
    # 尝试解析具体尺寸 (例如: "1024x768", "1024*768", "1024 x 768")
    size_pattern = r'(\d{3,4})\s*[x*×]\s*(\d{3,4})'
    match = re.search(size_pattern, text, re.IGNORECASE)
    if match:
        width = int(match.group(1))
        height = int(match.group(2))
        # 限制最大尺寸
        if width > max_size or height > max_size:
            scale = max_size / max(width, height)
            width = int(width * scale)
            height = int(height * scale)
        return (width, height)
    
    # 默认正方形
    return IMAGE_SIZE_PRESETS["square"]


def _image_to_base64(image_bytes: bytes) -> str:
    """
    将图片字节转换为 base64 字符串
    
    Args:
        image_bytes: 图片字节数据
        
    Returns:
        base64 编码的字符串
    """
    return base64.b64encode(image_bytes).decode('utf-8')


def _convert_size_to_aspect_ratio(width: int, height: int) -> str:
    """
    将像素尺寸转换为宽高比
    
    Args:
        width: 宽度
        height: 高度
        
    Returns:
        宽高比字符串，例如 "1:1", "2:3"
    """
    from math import gcd
    
    # 计算最大公约数
    divisor = gcd(width, height)
    w_ratio = width // divisor
    h_ratio = height // divisor
    
    # 限制在支持的比例内
    supported_ratios = {
        (1, 1): "1:1",
        (2, 3): "2:3",
        (3, 2): "3:2",
        (3, 4): "3:4",
        (4, 3): "4:3",
        (4, 5): "4:5",
        (5, 4): "5:4",
        (9, 16): "9:16",
        (16, 9): "16:9",
        (21, 9): "21:9",
    }
    
    ratio_key = (w_ratio, h_ratio)
    if ratio_key in supported_ratios:
        return supported_ratios[ratio_key]
    
    # 如果不在支持列表中，找最接近的
    target_ratio = w_ratio / h_ratio
    closest_key = None
    min_distance = float('inf')
    
    for key in supported_ratios.keys():
        supported_ratio = key[0] / key[1]
        distance = abs(target_ratio - supported_ratio)
        if distance < min_distance:
            min_distance = distance
            closest_key = key
    
    if closest_key:
        closest_ratio_str = supported_ratios[closest_key]
        logger.warning(f"Unsupported aspect ratio {w_ratio}:{h_ratio} ({target_ratio:.3f}), using closest {closest_ratio_str}")
        return closest_ratio_str
    
    # 备用方案（不应该到达这里）
    logger.warning(f"Failed to find closest ratio for {w_ratio}:{h_ratio}, using 1:1")
    return "1:1"


async def generate_image(
    prompt: str,
    reference_image: Optional[bytes] = None,
    size: Optional[Tuple[int, int]] = None
) -> Tuple[Optional[bytes], Optional[str]]:
    """
    生成图片（使用 chat.completions 接口）
    
    Args:
        prompt: 绘图提示词
        reference_image: 参考图片字节数据（可选）
        size: 图片尺寸 (width, height)，如果为 None 则自动判断
        
    Returns:
        (图片字节数据, 错误信息) 元组，成功时错误信息为 None
    """
    # 检查配置
    if not (config.IMAGE_MODEL_BASE_URL and config.IMAGE_MODEL_API_KEY):
        logger.warning("Image generation not configured")
        return None, MSG_DRAW_NO_CONFIG
    
    # 清理提示词（去掉@提及和多余空格）
    clean_prompt = prompt.strip()
    # 移除 @mention 前缀
    if clean_prompt.startswith("@"):
        parts = clean_prompt.split(maxsplit=1)
        clean_prompt = parts[1] if len(parts) > 1 else clean_prompt
    clean_prompt = clean_prompt.strip()
    
    # 确定尺寸
    if size is None:
        if reference_image:
            # 尝试从参考图片获取尺寸
            try:
                from PIL import Image
                img = Image.open(BytesIO(reference_image))
                ref_width, ref_height = img.size
                logger.info(f"Reference image size: {ref_width}x{ref_height}")
                # 使用参考图片的比例
                size = parse_size_from_text(clean_prompt, reference_size=(ref_width, ref_height))
            except Exception as e:
                logger.warning(f"Failed to get reference image size: {e}, using default square")
                size = IMAGE_SIZE_PRESETS["square"]
        else:
            size = parse_size_from_text(clean_prompt)
    
    width, height = size
    aspect_ratio = _convert_size_to_aspect_ratio(width, height)
    
    logger.info(f"Generating image: prompt='{clean_prompt[:50]}...' size={width}x{height} ratio={aspect_ratio} has_ref={reference_image is not None}")
    
    try:
        # 使用 chat.completions 接口（兼容 aihubmix）
        url = config.IMAGE_MODEL_BASE_URL.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.IMAGE_MODEL_API_KEY}",
            "Content-Type": "application/json",
        }
        
        # 根据是否有参考图片选择不同的提示词模板
        if reference_image:
            full_prompt = PROMPT_TEMPLATE_IMAGE_TO_IMAGE.format(prompt=clean_prompt)
        else:
            full_prompt = PROMPT_TEMPLATE_IMAGE_GEN.format(prompt=clean_prompt)
        
        # 构建消息内容 - 图片应该放在文本之前
        user_content = []
        
        # 如果有参考图片，先添加图片
        if reference_image:
            ref_b64 = _image_to_base64(reference_image)
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{ref_b64}"}
            })
            logger.debug(f"Added reference image to request, size={len(reference_image)} bytes")
        
        # 然后添加文本
        user_content.append({"type": "text", "text": full_prompt})
        
        payload = {
            "model": config.IMAGE_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": f"aspect_ratio={aspect_ratio}"
                },
                {
                    "role": "user",
                    "content": user_content
                }
            ],
            "modalities": ["text", "image"]
        }
        
        logger.debug(f"Image generation request: model={config.IMAGE_MODEL} aspect_ratio={aspect_ratio} content_items={len(user_content)}")
        if reference_image:
            logger.debug(f"Request includes reference image, prompt='{clean_prompt[:100]}'")
        
        async with httpx.AsyncClient(timeout=config.IMAGE_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, json=payload)
            
            if resp.status_code >= 300:
                error_msg = f"HTTP {resp.status_code}"
                try:
                    error_data = resp.json()
                    error_msg = error_data.get("error", {}).get("message", error_msg)
                except Exception:
                    error_msg = resp.text[:200]
                
                logger.error(f"Image generation failed: {error_msg}")
                return None, MSG_DRAW_ERROR.format(error=error_msg)
            
            data = resp.json()
            
            # 解析响应 - 从 multi_mod_content 中提取图片
            try:
                choices = data.get("choices", [])
                if not choices:
                    error_msg = "No choices in response"
                    logger.error(f"Image generation failed: {error_msg}")
                    return None, MSG_DRAW_ERROR.format(error=error_msg)
                
                message = choices[0].get("message", {})
                multi_mod_content = message.get("multi_mod_content", [])
                
                if not multi_mod_content:
                    error_msg = "No multi_mod_content in response"
                    logger.error(f"Image generation failed: {error_msg}")
                    return None, MSG_DRAW_ERROR.format(error=error_msg)
                
                # 查找图片数据
                for part in multi_mod_content:
                    if "inline_data" in part:
                        image_data = part["inline_data"].get("data", "")
                        if image_data:
                            image_bytes = base64.b64decode(image_data)
                            logger.info(f"Image generated successfully, size={len(image_bytes)} bytes")
                            return image_bytes, None
                
                error_msg = "No image data found in response"
                logger.error(f"Image generation failed: {error_msg}")
                return None, MSG_DRAW_ERROR.format(error=error_msg)
                
            except Exception as e:
                error_msg = f"Failed to parse response: {str(e)}"
                logger.error(f"Image generation parse error: {error_msg}, data={data}")
                return None, MSG_DRAW_ERROR.format(error=error_msg)
            
    except httpx.TimeoutException:
        error_msg = "请求超时，请稍后重试"
        logger.error(f"Image generation timeout")
        return None, MSG_DRAW_ERROR.format(error=error_msg)
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Image generation error: {e}", exc_info=True)
        return None, MSG_DRAW_ERROR.format(error=error_msg)
