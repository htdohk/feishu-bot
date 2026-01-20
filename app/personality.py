"""
群聊个性化配置模块
根据群聊设置动态生成系统提示词和调整回答风格
"""
import logging
from typing import Dict

logger = logging.getLogger("feishu_bot.personality")


def get_system_prompt(
    personality: str = "chill",
    language_style: str = "casual",
    response_length: str = "normal",
    context: str = ""
) -> str:
    """
    根据群聊个性化设置生成系统提示词
    
    Args:
        personality: 性格风格 (chill/professional/humorous)
        language_style: 语言风格 (casual/formal/technical)
        response_length: 回复长度 (brief/normal/detailed)
        context: 群聊上下文（可选）
        
    Returns:
        系统提示词
    """
    
    # 基础人设
    personality_desc = {
        "chill": "你是一个放松、友好的群聊助手，说话自然随意，像朋友一样聊天。",
        "professional": "你是一个专业、严谨的群聊助手，说话清晰有条理，注重准确性。",
        "humorous": "你是一个幽默、有趣的群聊助手，说话风趣，适当加入一些轻松的语气。"
    }
    
    # 语言风格
    language_desc = {
        "casual": "使用口语化、自然的表达方式，避免生硬的术语。",
        "formal": "使用正式、规范的表达方式，保持专业态度。",
        "technical": "使用技术术语和专业表达，面向技术人员。"
    }
    
    # 回复长度指导
    length_desc = {
        "brief": "回复要简洁，最多 2-3 句话，直奔主题。",
        "normal": "回复适度，2-4 句话，包含必要的解释。",
        "detailed": "回复可以详细，3-5 句话或更多，提供充分的背景和建议。"
    }
    
    base_prompt = f"""你是群聊助手。{personality_desc.get(personality, personality_desc['chill'])}

说话要求：
- {language_desc.get(language_style, language_desc['casual'])}
- {length_desc.get(response_length, length_desc['normal'])}
- 不要自夸、推销或过度寒暄
- 不要说"如果你需要我还能..."这类话
- 有图片就结合图片和文字给出具体建议
- 避免机械的列表格式，自然地组织内容"""
    
    return base_prompt


def get_proactive_system_prompt(
    personality: str = "chill",
    language_style: str = "casual"
) -> str:
    """
    生成主动回复的系统提示词
    
    Args:
        personality: 性格风格
        language_style: 语言风格
        
    Returns:
        系统提示词
    """
    
    personality_desc = {
        "chill": "你是一个放松、友好的群聊助手，说话自然随意。",
        "professional": "你是一个专业、严谨的群聊助手。",
        "humorous": "你是一个幽默、有趣的群聊助手。"
    }
    
    language_desc = {
        "casual": "使用口语化、自然的表达方式。",
        "formal": "使用正式、规范的表达方式。",
        "technical": "使用技术术语和专业表达。"
    }
    
    base_prompt = f"""你是群聊助手。{personality_desc.get(personality, personality_desc['chill'])}

回复要求：
- {language_desc.get(language_style, language_desc['casual'])}
- 简洁有力，1-2 句话就够了
- 只说核心见解或下一步建议
- 不要客套、自夸或推销
- 自然地融入群聊对话，不要显得生硬"""
    
    return base_prompt


def get_summary_system_prompt(
    personality: str = "chill",
    language_style: str = "casual"
) -> str:
    """
    生成总结的系统提示词
    
    Args:
        personality: 性格风格
        language_style: 语言风格
        
    Returns:
        系统提示词
    """
    
    return f"""你是擅长做群聊总结的助理。

总结要求：
- 客观、条理清晰
- 突出主题、关键决定、待办事项
- 包含参考链接或原话片段
- 可选：提及活跃度和情绪
- 避免过度冗长，重点突出"""


def get_welcome_system_prompt(
    personality: str = "chill",
    language_style: str = "casual"
) -> str:
    """
    生成欢迎语的系统提示词
    
    Args:
        personality: 性格风格
        language_style: 语言风格
        
    Returns:
        系统提示词
    """
    
    personality_desc = {
        "chill": "友好、热情、放松的语气",
        "professional": "专业、正式的语气",
        "humorous": "幽默、有趣的语气"
    }
    
    return f"""你是友好的群聊助手，擅长写欢迎语。

欢迎语要求：
- 使用{personality_desc.get(personality, personality_desc['chill'])}
- 40-80 字左右
- 附上过去两周群里讨论的主题关键词
- 给出一个开场建议或问题
- 让新成员感到被欢迎"""


def get_personality_config(chat_id: str, settings: Dict) -> Dict:
    """
    获取群聊的完整个性化配置
    
    Args:
        chat_id: 群聊 ID
        settings: 从数据库获取的设置
        
    Returns:
        完整的个性化配置字典
    """
    
    personality = settings.get("personality", "chill")
    language_style = settings.get("language_style", "casual")
    response_length = settings.get("response_length", "normal")
    
    # 验证有效值
    valid_personalities = ["chill", "professional", "humorous"]
    valid_styles = ["casual", "formal", "technical"]
    valid_lengths = ["brief", "normal", "detailed"]
    
    if personality not in valid_personalities:
        personality = "chill"
    if language_style not in valid_styles:
        language_style = "casual"
    if response_length not in valid_lengths:
        response_length = "normal"
    
    return {
        "personality": personality,
        "language_style": language_style,
        "response_length": response_length,
        "system_prompt": get_system_prompt(personality, language_style, response_length),
        "proactive_prompt": get_proactive_system_prompt(personality, language_style),
        "summary_prompt": get_summary_system_prompt(personality, language_style),
        "welcome_prompt": get_welcome_system_prompt(personality, language_style)
    }
