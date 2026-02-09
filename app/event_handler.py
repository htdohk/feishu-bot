"""
事件处理模块 - 统一处理所有非消息事件
包括：新成员欢迎、命令处理（/help、/summary、/settings 等）、对话管理
"""
import time
import logging
from typing import List, Dict, Callable, Optional
from collections import defaultdict

from .database import (
    get_recent_messages,
    update_settings_threshold,
    update_settings_mode,
    list_chat_ids,
)
from .llm import call_llm
from .feishu_api import send_text_to_chat
from .constants import (
    MSG_NO_MESSAGES_FOR_SUMMARY,
    SYSTEM_PROMPT_SUMMARY,
    SYSTEM_PROMPT_WELCOME,
    PROMPT_TEMPLATE_SUMMARY,
    PROMPT_TEMPLATE_WELCOME,
    MSG_WELCOME_PREFIX,
    MSG_WELCOME_SUFFIX,
    TEMPERATURE_SUMMARY,
    TEMPERATURE_WELCOME,
)

logger = logging.getLogger("feishu_bot.event_handler")

# 全局状态管理
conversation_active_until: Dict[str, float] = defaultdict(float)
CONVERSATION_TTL_SECONDS = 600  # 10 分钟对话窗口


def mark_conversation_active(chat_id: str):
    """标记群聊进入活跃对话状态"""
    if not chat_id:
        return
    conversation_active_until[chat_id] = time.time() + CONVERSATION_TTL_SECONDS
    logger.debug(f"marked conversation active for chat_id={chat_id}")


def is_conversation_active(chat_id: str) -> bool:
    """检查群聊是否仍在活跃对话窗口内"""
    if not chat_id:
        return False
    is_active = time.time() <= (conversation_active_until.get(chat_id, 0.0) or 0.0)
    logger.debug(f"is_conversation_active chat_id={chat_id} result={is_active}")
    return is_active


def build_context_summary(messages: List[dict], limit: int = 15) -> str:
    """构建消息上下文摘要"""
    if not messages:
        return ""
    tail = messages[-limit:]
    lines = []
    for m in tail:
        who = (m.get("user_id", "") or "")[-6:]
        lines.append(f"{m.get('ts', '')}-{who}: {m.get('text', '')}")
    return "\n".join(lines)


async def welcome_new_user(chat_id: str, new_user_name: str):
    """
    欢迎新成员加入群聊
    
    Args:
        chat_id: 群聊ID
        new_user_name: 新成员名字
    """
    logger.info(f"welcome_new_user chat_id={chat_id} name={new_user_name}")
    
    try:
        # 获取群聊最近的消息作为上下文
        msgs = await get_recent_messages(chat_id, limit=80)
        ctx = build_context_summary(msgs, limit=40)
        
        # 生成欢迎语
        prompt = PROMPT_TEMPLATE_WELCOME.format(context=ctx)
        text = await call_llm(
            prompt,
            SYSTEM_PROMPT_WELCOME,
            temperature=TEMPERATURE_WELCOME
        )
        
        # 发送欢迎消息
        welcome_msg = f"{MSG_WELCOME_PREFIX.format(name=new_user_name)}{text}{MSG_WELCOME_SUFFIX}"
        await send_text_to_chat(chat_id, welcome_msg)
        
        logger.info(f"welcome_new_user completed for chat_id={chat_id}")
    except Exception as e:
        logger.error(f"welcome_new_user error: {e}")


async def summarize_chat(chat_id: str, period: str = "weekly"):
    """
    生成群聊总结（周报或月报）
    
    Args:
        chat_id: 群聊ID
        period: 总结周期（weekly 或 monthly）
    """
    logger.info(f"summarize_chat chat_id={chat_id} period={period}")
    
    try:
        # 获取最近的消息
        msgs = await get_recent_messages(chat_id, limit=400)
        
        if not msgs:
            logger.info(f"summarize_chat chat_id={chat_id} period={period} no messages")
            await send_text_to_chat(
                chat_id,
                MSG_NO_MESSAGES_FOR_SUMMARY.format(period=period)
            )
            return
        
        # 生成总结
        system = SYSTEM_PROMPT_SUMMARY
        prompt = PROMPT_TEMPLATE_SUMMARY.format(
            period=period,
            messages=build_context_summary(msgs, limit=120)
        )
        
        logger.info(f"summarize_chat chat_id={chat_id} period={period} start LLM")
        report = await call_llm(prompt, system, temperature=TEMPERATURE_SUMMARY)
        
        # 发送总结
        await send_text_to_chat(chat_id, f"{period}总结：\n{report}")
        
        logger.info(f"summarize_chat completed for chat_id={chat_id} period={period}")
    except Exception as e:
        logger.error(f"summarize_chat error: {e}")


async def handle_help_command(chat_id: str):
    """处理 /help 命令"""
    help_text = (
        "可用命令：\n"
        "/summary weekly|monthly - 生成群总结\n"
        "/settings threshold <0~1> - 调整主动发言阈值（0=总是回复，1=从不回复）\n"
        "/settings mode quiet|normal|active - 调整发言模式\n"
        "  - quiet: 仅在被@时回复\n"
        "  - normal: 默认模式，根据阈值自动回复\n"
        "  - active: 更积极地自动回复\n"
        "/optout - 个人选择不纳入公开个人总结\n"
        "/reset - 重置 Bot 状态（清空会话、重置设置）\n"
        "\n💡 提示：如不想自动回复，使用 /settings mode quiet"
    )
    logger.info(f"/help in chat_id={chat_id}")
    await send_text_to_chat(chat_id, help_text)


async def handle_summary_command(chat_id: str, period: str = "weekly"):
    """处理 /summary 命令"""
    if period not in ("weekly", "monthly"):
        period = "weekly"
    logger.info(f"/summary {period} in chat_id={chat_id}")
    await summarize_chat(chat_id, period)


async def handle_settings_command(chat_id: str, key: str, val: str):
    """处理 /settings 命令"""
    key = key.lower()
    val = val.lower()
    
    if key == "threshold":
        try:
            t = float(val)
            t = max(0.0, min(1.0, t))
            await update_settings_threshold(chat_id, t)
            logger.info(f"/settings threshold chat_id={chat_id} t={t}")
            await send_text_to_chat(chat_id, f"已将主动发言阈值设置为 {t}")
        except ValueError:
            logger.warning(
                f"/settings threshold parse error chat_id={chat_id} val={val}"
            )
            await send_text_to_chat(
                chat_id,
                "阈值需为0~1数字，例如 /settings threshold 0.65"
            )
    elif key == "mode" and val in ("quiet", "normal", "active"):
        await update_settings_mode(chat_id, val)
        logger.info(f"/settings mode chat_id={chat_id} mode={val}")
        await send_text_to_chat(chat_id, f"已切换模式为 {val}")
    else:
        logger.warning(
            f"/settings unknown key or value chat_id={chat_id} "
            f"key={key} val={val}"
        )
        await send_text_to_chat(chat_id, "未识别的设置项。")


async def handle_optout_command(chat_id: str, user_id: str):
    """处理 /optout 命令"""
    logger.info(f"/optout in chat_id={chat_id} user_id={user_id}")
    await send_text_to_chat(
        chat_id,
        "已记录；后续公共总结将不展示你的个人条目。"
    )


async def handle_reset_command(chat_id: str):
    """处理 /reset 命令"""
    logger.info(f"/reset in chat_id={chat_id}")
    
    # 清空群聊的会话记录
    if chat_id in conversation_active_until:
        del conversation_active_until[chat_id]
    
    # 重置数据库中的设置为默认值
    await update_settings_threshold(chat_id, 0.65)
    await update_settings_mode(chat_id, "normal")
    
    await send_text_to_chat(
        chat_id,
        "已重置 Bot 状态：\n"
        "- 清空会话记录\n"
        "- 重置主动发言阈值为 0.65\n"
        "- 重置发言模式为 normal\n"
        "- 忘记所有之前的对话上下文"
    )


async def handle_event(
    event_type: str,
    chat_id: str,
    **kwargs
) -> bool:
    """
    统一的事件处理入口
    
    Args:
        event_type: 事件类型（new_member、command等）
        chat_id: 群聊ID
        **kwargs: 其他事件参数
        
    Returns:
        是否处理成功
    """
    try:
        if event_type == "new_member":
            # 新成员加入事件
            new_user_name = kwargs.get("new_user_name", "新同学")
            await welcome_new_user(chat_id, new_user_name)
            return True
        
        elif event_type == "command":
            # 命令事件
            command = kwargs.get("command", "")
            args = kwargs.get("args", [])
            
            if command == "help":
                await handle_help_command(chat_id)
            elif command == "summary":
                period = args[0] if args else "weekly"
                await handle_summary_command(chat_id, period)
            elif command == "settings":
                if len(args) >= 2:
                    key, val = args[0], args[1]
                    await handle_settings_command(chat_id, key, val)
            elif command == "optout":
                user_id = kwargs.get("user_id", "")
                await handle_optout_command(chat_id, user_id)
            elif command == "reset":
                await handle_reset_command(chat_id)
            
            return True
        
        logger.warning(f"Unknown event_type: {event_type}")
        return False
        
    except Exception as e:
        logger.error(f"handle_event error event_type={event_type}: {e}")
        return False


async def run_periodic_summaries():
    """
    运行周期性总结（可用于定时任务）
    注：当前架构改为用户主动触发命令，此函数作为备选方案保留
    """
    logger.info("run_periodic_summaries started")
    chat_ids = await list_chat_ids()
    for chat_id in chat_ids:
        try:
            await summarize_chat(chat_id, "weekly")
        except Exception as e:
            logger.error(f"periodic summary for {chat_id} failed: {e}")
