"""
消息热度计算模块
根据时间、上下文等因素判断消息是否值得主动回复
"""
import logging
import time
from typing import Dict, List

logger = logging.getLogger("feishu_bot.message_heat")


def calculate_message_heat(
    current_message_time: float,
    last_bot_mention_time: float,
    recent_messages: List[Dict],
    time_since_last_message: float,
    is_after_mention: bool = False
) -> Dict[str, any]:
    """
    计算消息热度，综合考虑多个因素
    
    Args:
        current_message_time: 当前消息的时间戳
        last_bot_mention_time: 上一次 @bot 的时间戳
        recent_messages: 最近的消息列表
        time_since_last_message: 距离上一条消息的秒数
        is_after_mention: 当前消息是否紧跟在 @bot 之后
        
    Returns:
        {
            "heat_score": 0.0-1.0,
            "factors": {
                "recency": 0.0-1.0,
                "mention_proximity": 0.0-1.0,
                "message_density": 0.0-1.0,
                "after_mention": bool
            },
            "is_hot": bool,
            "reason": str
        }
    """
    factors = {
        "recency": 0.0,
        "mention_proximity": 0.0,
        "message_density": 0.0,
        "after_mention": is_after_mention
    }
    
    # 1. 新近性因素：距离上一条消息的时间
    # < 30秒：1.0，30-60秒：0.8，60-300秒：0.5，> 300秒：0.0
    if time_since_last_message < 30:
        factors["recency"] = 1.0
    elif time_since_last_message < 60:
        factors["recency"] = 0.8
    elif time_since_last_message < 300:  # 5分钟
        factors["recency"] = 0.5
    else:
        factors["recency"] = 0.0
    
    # 2. @提及接近度：距离上一次 @bot 的时间
    # < 2分钟：1.0，2-5分钟：0.7，5-10分钟：0.4，> 10分钟：0.0
    time_since_mention = current_message_time - last_bot_mention_time
    if time_since_mention < 120:  # 2分钟
        factors["mention_proximity"] = 1.0
    elif time_since_mention < 300:  # 5分钟
        factors["mention_proximity"] = 0.7
    elif time_since_mention < 600:  # 10分钟
        factors["mention_proximity"] = 0.4
    else:
        factors["mention_proximity"] = 0.0
    
    # 3. 消息密度：最近 5 条消息的平均间隔
    # 间隔 < 30秒：1.0，30-60秒：0.8，60-120秒：0.6，> 120秒：0.3
    if len(recent_messages) >= 2:
        intervals = []
        for i in range(1, min(5, len(recent_messages))):
            try:
                # 假设消息有 'ts' 字段（时间戳字符串）
                # 这里简化处理，实际需要解析时间戳
                intervals.append(1)  # 占位
            except:
                pass
        
        if intervals:
            avg_interval = sum(intervals) / len(intervals)
            if avg_interval < 30:
                factors["message_density"] = 1.0
            elif avg_interval < 60:
                factors["message_density"] = 0.8
            elif avg_interval < 120:
                factors["message_density"] = 0.6
            else:
                factors["message_density"] = 0.3
        else:
            factors["message_density"] = 0.5
    else:
        factors["message_density"] = 0.5
    
    # 4. 如果紧跟在 @bot 之后，热度加成
    after_mention_bonus = 0.3 if is_after_mention else 0.0
    
    # 综合热度分数（加权平均）
    # 新近性 40%，@提及接近度 30%，消息密度 20%，@之后加成 10%
    heat_score = (
        factors["recency"] * 0.4 +
        factors["mention_proximity"] * 0.3 +
        factors["message_density"] * 0.2 +
        after_mention_bonus
    )
    
    # 规范化到 0-1
    heat_score = min(1.0, max(0.0, heat_score))
    
    # 判断是否为"热消息"
    is_hot = heat_score >= 0.5
    
    # 生成原因说明
    if is_after_mention:
        reason = "紧跟在 @bot 之后"
    elif factors["recency"] >= 0.8:
        reason = "消息很新（< 60秒）"
    elif factors["mention_proximity"] >= 0.7:
        reason = "在 @bot 后的短时间内"
    elif factors["message_density"] >= 0.8:
        reason = "群聊消息密集"
    elif heat_score >= 0.5:
        reason = "综合热度较高"
    else:
        reason = "消息冷度较高"
    
    logger.debug(
        f"calculate_message_heat heat_score={heat_score:.2f} "
        f"recency={factors['recency']:.2f} mention_proximity={factors['mention_proximity']:.2f} "
        f"density={factors['message_density']:.2f} after_mention={is_after_mention}"
    )
    
    return {
        "heat_score": heat_score,
        "factors": factors,
        "is_hot": is_hot,
        "reason": reason
    }


def should_respond_based_on_heat(
    heat_score: float,
    threshold: float = 0.65,
    is_mentioned: bool = False,
    is_in_conversation: bool = False
) -> bool:
    """
    根据热度分数判断是否应该回复
    
    Args:
        heat_score: 消息热度分数
        threshold: 回复阈值
        is_mentioned: 是否被 @
        is_in_conversation: 是否在对话窗口内
        
    Returns:
        是否应该回复
    """
    # 被 @ 或在对话窗口内，直接回复
    if is_mentioned or is_in_conversation:
        return True
    
    # 根据热度分数和阈值判断
    return heat_score >= threshold
