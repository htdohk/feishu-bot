"""
工具函数模块
提取通用的辅助函数
"""
import logging
from typing import List, Tuple

from .config import config
from .feishu_api import get_message_image_bytes

logger = logging.getLogger("feishu_bot.utils")


async def fetch_message_images(
    message_id: str, 
    image_keys: List[str]
) -> Tuple[List[bytes], List[str]]:
    """
    从消息中获取图片数据
    
    Args:
        message_id: 消息ID
        image_keys: 图片key列表
        
    Returns:
        (图片字节列表, MIME类型列表)
    """
    images: List[bytes] = []
    mimes: List[str] = []
    
    if not image_keys or not message_id:
        return images, mimes
    
    # 限制图片数量
    max_images = min(len(image_keys), config.MAX_IMAGES_PER_MESSAGE)
    
    for image_key in image_keys[:max_images]:
        try:
            img_bytes, mime = await get_message_image_bytes(message_id, image_key)
            if img_bytes:
                images.append(img_bytes)
                mimes.append(mime or "image/jpeg")
        except Exception as e:
            logger.warning(
                f"fetch_message_images failed for image_key={image_key}: {e}"
            )
            continue
    
    logger.debug(
        f"fetch_message_images message_id={message_id} "
        f"requested={len(image_keys)} fetched={len(images)}"
    )
    
    return images, mimes
