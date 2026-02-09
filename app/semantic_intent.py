"""
语义意图识别模块
使用 LLM 理解用户真实意图，而不仅依赖关键词
"""
import logging
import json
from typing import Dict, Optional
from .llm import call_llm
from .config import config

logger = logging.getLogger("feishu_bot.semantic_intent")


async def call_small_llm(prompt: str, system: str = "", temperature: float = 0.1) -> str:
    """
    调用小模型（用于快速意图分类）
    
    Args:
        prompt: 用户提示词
        system: 系统提示词
        temperature: 温度参数
        
    Returns:
        模型返回的文本
    """
    # 如果配置了独立的小模型，使用小模型；否则使用主LLM
    if config.SMALL_MODEL_BASE_URL and config.SMALL_MODEL_API_KEY and config.SMALL_MODEL:
        # 使用独立的小模型配置
        import httpx
        import asyncio
        
        url = config.SMALL_MODEL_BASE_URL.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.SMALL_MODEL_API_KEY}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": config.SMALL_MODEL,
            "messages": [
                {"role": "system", "content": system} if system else {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
        }
        
        try:
            async with httpx.AsyncClient(timeout=config.SMALL_MODEL_TIMEOUT) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code >= 300:
                    logger.warning(f"Small model API error: {resp.status_code}, falling back to main LLM")
                    return await call_llm(prompt, system=system, temperature=temperature)
                
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"Small model call failed: {e}, falling back to main LLM")
            return await call_llm(prompt, system=system, temperature=temperature)
    else:
        # 没有配置小模型，使用主LLM
        logger.debug("No small model configured, using main LLM for intent classification")
        return await call_llm(prompt, system=system, temperature=temperature)


async def classify_intent(text: str, has_images: bool = False) -> Dict:
    """
    使用小模型快速分类用户意图
    
    Args:
        text: 用户输入文本
        has_images: 是否包含图片
        
    Returns:
        {
            "task_type": "draw" | "chat" | "command" | "other",
            "confidence": 0.0-1.0,
            "is_image_modification": bool,  # if task_type == "draw"
            "needs_reference_image": bool,  # if task_type == "draw"
            "reason": "分类原因说明"
        }
    """
    if not text or not text.strip():
        return {
            "task_type": "other",
            "confidence": 0.0,
            "reason": "empty message"
        }
    
    system_prompt = """你是一个用户意图分类助手。分析用户的消息，快速判断用户的真实意图。

严格按照以下规则分类：
1. "draw" - 用户要求生成、绘制、修改图片
   - 文生图: 画xxxx、生成xxxx、设计xxxx等
   - 图生图: 改成xxxx风格、修改这个xxxx、重绘成xxxx等（即使没有明确说"生成图片"）
2. "command" - 用户发送命令（以/开头）或要求特定操作
3. "chat" - 日常闲聊或提问
4. "other" - 其他

返回 JSON 格式结果，包含：
- task_type: 上述分类之一
- confidence: 0.0-1.0 的置信度
- is_image_modification: 如果是draw，是否是图生图（True）还是文生图（False）
- needs_reference_image: 如果是draw且是图生图，是否需要参考图片
- reason: 简短的分类理由

仅返回 JSON，不要其他文字。"""
    
    user_prompt = f"""用户消息: "{text}"
是否包含图片: {has_images}

分类这条消息。"""
    
    response = None
    try:
        response = await call_small_llm(user_prompt, system=system_prompt, temperature=0.1)
        
        if not response or not response.strip():
            logger.warning(f"classify_intent received empty response for text='{text[:50]}'")
            return _get_default_classify_intent_result("other")
        
        # 尝试解析JSON
        result = json.loads(response)
        
        # 验证返回的结果结构
        if not isinstance(result, dict) or "task_type" not in result:
            logger.warning(f"classify_intent invalid result structure: {result}")
            return _get_default_classify_intent_result("other")
        
        # 确保task_type有效
        valid_types = ["draw", "chat", "command", "other"]
        if result.get("task_type") not in valid_types:
            logger.warning(f"classify_intent invalid task_type: {result.get('task_type')}")
            result["task_type"] = "other"
        
        logger.debug(f"classify_intent text='{text[:50]}' task_type={result.get('task_type')} confidence={result.get('confidence')}")
        return result
        
    except json.JSONDecodeError as e:
        # JSON 解析失败，尝试从响应中提取 JSON
        if response:
            extracted = _try_extract_json(response)
            if extracted:
                logger.debug(f"classify_intent extracted JSON from response for text='{text[:50]}'")
                return extracted
            logger.warning(f"classify_intent JSON parse error: {e}, response='{response[:300]}'")
        else:
            logger.warning(f"classify_intent JSON parse error: {e}, response is None or empty")
        return _get_default_classify_intent_result("other")
        
    except Exception as e:
        logger.error(f"classify_intent unexpected error: {e}, response='{response[:300] if response else 'N/A'}'")
        return _get_default_classify_intent_result("other")


def _try_extract_json(text: str) -> Optional[Dict]:
    """
    尝试从文本中提取 JSON 对象
    支持多种格式：纯JSON、markdown代码块、带引号等
    """
    if not text:
        return None
    
    # 尝试找到 JSON 对象的开始和结束
    try:
        # 首先尝试去掉 markdown 代码块标记 (```json ... ```)
        text_clean = text
        if "```json" in text or "```" in text:
            # 移除 ```json 或 ``` 标记
            text_clean = text.replace("```json", "").replace("```", "").strip()
        
        # 查找 { 和 } 的匹配对
        start_idx = text_clean.find('{')
        if start_idx == -1:
            return None
        
        # 从 start_idx 开始，找到匹配的 }
        brace_count = 0
        end_idx = -1
        for i in range(start_idx, len(text_clean)):
            if text_clean[i] == '{':
                brace_count += 1
            elif text_clean[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i
                    break
        
        if end_idx == -1:
            return None
        
        json_str = text_clean[start_idx:end_idx + 1]
        result = json.loads(json_str)
        
        if isinstance(result, dict) and "task_type" in result:
            logger.debug(f"_try_extract_json successfully extracted from markdown/formatted text")
            return result
    except Exception as e:
        logger.debug(f"_try_extract_json failed: {e}")
    
    return None


def _get_default_classify_intent_result(task_type: str = "other") -> Dict:
    """
    返回默认的分类结果（for classify_intent）
    """
    return {
        "task_type": task_type,
        "confidence": 0.5,
        "is_image_modification": False,
        "needs_reference_image": False,
        "reason": "classification failed"
    }


async def detect_user_intent(text: str, context: str = "") -> Dict[str, any]:
    """
    使用 LLM 识别用户意图
    
    Args:
        text: 用户输入文本
        context: 群聊上下文（可选）
        
    Returns:
        {
            "intent": "draw" | "question" | "chat" | "command",
            "confidence": 0.0-1.0,
            "details": {
                "is_image_generation": bool,
                "is_image_modification": bool,
                "needs_reference_image": bool,
                "description": str
            }
        }
    """
    if not text or not text.strip():
        return {
            "intent": "chat",
            "confidence": 0.0,
            "details": {"description": "empty message"}
        }
    
    system_prompt = """你是一个意图识别助手。分析用户消息，判断用户的真实意图。

返回 JSON 格式的结果，包含：
- intent: "draw"(绘图/图生图) | "question"(提问) | "chat"(闲聊) | "command"(命令)
- confidence: 0.0-1.0 的置信度
- details: {
    "is_image_generation": 是否是文生图,
    "is_image_modification": 是否是图生图/修改图片,
    "needs_reference_image": 是否需要参考图片,
    "description": 简短描述用户需求
  }

判断规则：
1. 如果用户说"改成xxx风格"、"变成xxx"、"修改这个"等，即使没有明确说"生成图片"，也是图生图意图
2. 如果用户说"画xxx"、"生成xxx"、"设计xxx"等，是文生图意图
3. 如果用户提问或讨论，是 question 或 chat
4. 如果用户说"帮我总结"、"生成报告"等，是 command

只返回 JSON，不要其他文字。"""
    
    user_prompt = f"""分析这条消息的意图：
"{text}"

{f'群聊上下文：{context}' if context else ''}

返回 JSON 结果。"""
    
    response = None
    try:
        response = await call_llm(user_prompt, system=system_prompt, temperature=0.1)
        
        # 检查响应是否为空
        if not response or not response.strip():
            logger.warning(f"detect_user_intent received empty response for text='{text[:50]}'")
            return _get_default_intent_result()
        
        # 尝试解析 JSON
        import json
        result = json.loads(response)
        
        # 验证返回的结果结构
        if not isinstance(result, dict) or "intent" not in result:
            logger.warning(f"detect_user_intent invalid result structure: {result}")
            return _get_default_intent_result()
        
        logger.debug(f"detect_user_intent text='{text[:50]}' intent={result.get('intent')} confidence={result.get('confidence')}")
        return result
        
    except json.JSONDecodeError as e:
        # JSON 解析失败，尝试从响应中提取 JSON
        if response:
            extracted = _try_extract_json(response)
            if extracted:
                logger.debug(f"detect_user_intent extracted JSON from response for text='{text[:50]}'")
                return extracted
            logger.warning(f"detect_user_intent JSON parse error: {e}, response='{response[:300]}'")
        else:
            logger.warning(f"detect_user_intent JSON parse error: {e}, response is None or empty")
        return _get_default_intent_result()
        
    except Exception as e:
        logger.error(f"detect_user_intent unexpected error: {e}, response='{response[:300] if response else 'N/A'}'")
        return _get_default_intent_result()




def _get_default_intent_result() -> Dict[str, any]:
    """
    返回默认的意图识别结果
    """
    return {
        "intent": "chat",
        "confidence": 0.5,
        "details": {"description": "intent detection failed"}
    }


async def should_respond_to_message(
    text: str,
    context: str,
    is_mentioned: bool,
    is_in_conversation: bool,
    time_since_last_message: float,
    threshold: float = 0.65
) -> Dict[str, any]:
    """
    综合判断是否应该回复这条消息
    
    Args:
        text: 消息文本
        context: 群聊上下文
        is_mentioned: 是否被 @
        is_in_conversation: 是否在对话窗口内
        time_since_last_message: 距离上一条消息的秒数
        threshold: 主动回复阈值
        
    Returns:
        {
            "should_respond": bool,
            "reason": str,
            "score": 0.0-1.0
        }
    """
    # 被 @ 或在对话窗口内，直接回复
    if is_mentioned or is_in_conversation:
        return {
            "should_respond": True,
            "reason": "mentioned or in conversation",
            "score": 1.0
        }
    
    # 冷消息（距离上一条消息超过 5 分钟）且没有被 @，不主动回复
    if time_since_last_message > 300:  # 5 分钟
        return {
            "should_respond": False,
            "reason": "cold message (>5min since last)",
            "score": 0.0
        }
    
    # 检测意图
    intent_result = await detect_user_intent(text, context)
    intent = intent_result.get("intent", "chat")
    confidence = intent_result.get("confidence", 0.0)
    
    # 绘图请求总是回复
    if intent == "draw":
        return {
            "should_respond": True,
            "reason": "draw request detected",
            "score": 1.0
        }
    
    # 提问类消息，根据置信度和阈值判断
    if intent == "question":
        score = confidence
        should_respond = score >= threshold
        return {
            "should_respond": should_respond,
            "reason": f"question with confidence {confidence:.2f}",
            "score": score
        }
    
    # 闲聊消息，根据热度判断
    if intent == "chat":
        # 热消息（距离上一条消息 < 1 分钟）且置信度高，可以回复
        if time_since_last_message < 60 and confidence > 0.7:
            score = confidence * 0.8
            should_respond = score >= threshold
            return {
                "should_respond": should_respond,
                "reason": f"hot chat message, confidence {confidence:.2f}",
                "score": score
            }
        else:
            return {
                "should_respond": False,
                "reason": "cold or low-confidence chat",
                "score": 0.0
            }
    
    return {
        "should_respond": False,
        "reason": "unknown intent",
        "score": 0.0
    }
