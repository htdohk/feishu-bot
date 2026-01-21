"""
语义意图识别模块
使用 LLM 理解用户真实意图，而不仅依赖关键词
"""
import logging
from typing import Dict, Optional
from .llm import call_llm

logger = logging.getLogger("feishu_bot.semantic_intent")


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
    
    try:
        response = await call_llm(user_prompt, system=system_prompt, temperature=0.1)
        
        # 尝试解析 JSON
        import json
        result = json.loads(response)
        
        logger.debug(f"detect_user_intent text='{text[:50]}' intent={result.get('intent')} confidence={result.get('confidence')}")
        return result
    except Exception as e:
        logger.warning(f"detect_user_intent parse error: {e}, response={response[:200] if 'response' in locals() else 'N/A'}")
        # 降级处理：返回默认结果
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
