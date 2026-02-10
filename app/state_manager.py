"""
状态管理模块
集中管理所有全局状态，避免循环导入问题

注意：此模块使用内存存储，仅适用于单实例部署。
如需多实例部署，请使用 Redis 等分布式存储替代。
"""
import time
import logging
from collections import defaultdict, deque
from typing import Optional

from .config import config

logger = logging.getLogger("feishu_bot.state_manager")

# 对话活跃状态管理
# key: chat_id, value: 活跃截止时间戳
conversation_active_until: dict[str, float] = defaultdict(float)

# 聊天日志缓存
# key: chat_id, value: deque of message dicts
chat_logs: dict[str, deque] = defaultdict(
    lambda: deque(maxlen=config.CHAT_LOGS_MAXLEN)
)


def mark_conversation_active(chat_id: str, ttl_seconds: Optional[int] = None) -> None:
    """
    标记群聊进入活跃对话状态

    Args:
        chat_id: 群聊ID
        ttl_seconds: 活跃窗口时长（秒），默认使用配置值
    """
    if not chat_id:
        return

    if ttl_seconds is None:
        ttl_seconds = config.CONVERSATION_TTL_SECONDS

    conversation_active_until[chat_id] = time.time() + ttl_seconds
    logger.debug(f"marked conversation active for chat_id={chat_id}, ttl={ttl_seconds}s")


def is_conversation_active(chat_id: str) -> bool:
    """
    检查群聊是否仍在活跃对话窗口内

    Args:
        chat_id: 群聊ID

    Returns:
        是否活跃
    """
    if not chat_id:
        return False

    is_active = time.time() <= conversation_active_until.get(chat_id, 0.0)
    logger.debug(f"is_conversation_active chat_id={chat_id} result={is_active}")
    return is_active


def clear_conversation(chat_id: str) -> None:
    """
    清除群聊的对话状态

    Args:
        chat_id: 群聊ID
    """
    if chat_id in conversation_active_until:
        del conversation_active_until[chat_id]
        logger.debug(f"cleared conversation state for chat_id={chat_id}")


def add_chat_log(chat_id: str, user_id: str, text: str, ts: Optional[str] = None) -> None:
    """
    添加聊天日志到内存缓存

    Args:
        chat_id: 群聊ID
        user_id: 用户ID
        text: 消息文本
        ts: 时间戳字符串，如果为 None 则自动生成
    """
    if not chat_id:
        return

    if ts is None:
        ts = time.strftime("%m-%d %H:%M", time.localtime())

    if chat_id not in chat_logs:
        chat_logs[chat_id] = deque(maxlen=config.CHAT_LOGS_MAXLEN)

    chat_logs[chat_id].append({
        "ts": ts,
        "user_id": user_id,
        "text": text
    })

    logger.debug(
        f"added chat log: chat_id={chat_id} user_id={user_id} "
        f"log_count={len(chat_logs[chat_id])} ts={ts}"
    )


def get_chat_logs(chat_id: str, limit: Optional[int] = None) -> list[dict]:
    """
    获取群聊的聊天日志

    Args:
        chat_id: 群聊ID
        limit: 返回最近的 N 条记录，None 表示返回全部

    Returns:
        消息列表
    """
    if chat_id not in chat_logs:
        return []

    logs = list(chat_logs[chat_id])
    if limit is not None and limit > 0:
        logs = logs[-limit:]

    logger.debug(f"get_chat_logs chat_id={chat_id} limit={limit} returned={len(logs)}")
    return logs


def clear_chat_logs(chat_id: str) -> None:
    """
    清除群聊的聊天日志

    Args:
        chat_id: 群聊ID
    """
    if chat_id in chat_logs:
        del chat_logs[chat_id]
        logger.debug(f"cleared chat logs for chat_id={chat_id}")


def build_context_summary(messages: list[dict], limit: int = 15) -> str:
    """
    构建消息上下文摘要

    Args:
        messages: 消息列表，每条消息包含 ts, user_id, text
        limit: 使用最近的 N 条消息

    Returns:
        格式化的上下文字符串
    """
    if not messages:
        return ""

    tail = messages[-limit:] if len(messages) > limit else messages
    lines = []
    for m in tail:
        who = (m.get("user_id", "") or "")[-6:]
        lines.append(f"{m.get('ts', '')}-{who}: {m.get('text', '')}")

    return "\n".join(lines)


def get_stats() -> dict:
    """
    获取状态管理器的统计信息

    Returns:
        统计信息字典
    """
    active_conversations = sum(
        1 for expire_time in conversation_active_until.values()
        if time.time() <= expire_time
    )

    total_logs = sum(len(logs) for logs in chat_logs.values())

    return {
        "active_conversations": active_conversations,
        "total_conversations": len(conversation_active_until),
        "chat_groups": len(chat_logs),
        "total_logs": total_logs,
    }
