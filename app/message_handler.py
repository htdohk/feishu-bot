"""
消息处理模块 - 专注于消息分析、意图识别和内容生成
重构版本：消除重复代码，使用 state_manager 管理状态
"""
import asyncio
import logging
from typing import Optional

from .config import config
from .database import (
    save_message_db,
    get_recent_messages,
    get_or_create_settings,
)
from .feishu_api import (
    extract_message_payload,
    mentioned_bot,
    get_message_text_by_id,
    get_message_image_bytes,
    send_text_to_chat,
)
from .image_gen import handle_draw_request
from .llm import call_llm, call_llm_with_images
from .semantic_intent import classify_intent
from .web_search import (
    extract_urls_from_text,
    process_urls_in_context,
    should_use_web_search,
)
from .state_manager import (
    mark_conversation_active,
    is_conversation_active,
    add_chat_log,
    get_chat_logs,
    build_context_summary,
)
from .constants import (
    MSG_THINKING,
    SYSTEM_PROMPT_CHAT_ASSISTANT,
    SYSTEM_PROMPT_PROACTIVE,
    PROMPT_TEMPLATE_CHAT,
    PROMPT_TEMPLATE_PROACTIVE,
    TEMPERATURE_CHAT,
    TEMPERATURE_PROACTIVE,
)

logger = logging.getLogger("feishu_bot.message_handler")


def basic_engage_score(text: str) -> float:
    """
    基础参与度评分
    根据关键词判断用户是否需要回复
    """
    lowers = text.lower()
    score = 0.0
    keywords = [
        "怎么",
        "如何",
        "为啥",
        "为什么",
        "怎么办",
        "谁知道",
        "有链接吗",
        "总结",
        "结论",
        "进展",
        "?",
        "？",
    ]
    for kw in keywords:
        if kw in text or kw in lowers:
            score += 0.2
    if "?" in text or "？" in text:
        score += 0.2
    final = min(score, 1.0)
    logger.debug(f"basic_engage_score text='{text[:50]}' score={final}")
    return final


def mentions_someone_else(message_event: dict) -> bool:
    """
    如果本条消息@了别人但没@机器人，则视为"明显不是对机器人说"
    """
    try:
        msg = message_event.get("message", {}) or {}
        mentions = msg.get("mentions") or []
        if not mentions:
            return False
        # mentions 存在，但没@机器人
        return not mentioned_bot(message_event)
    except Exception:
        return False


def should_zip_reply(text: str) -> bool:
    """检查是否应该"拉上拉链"（不说话）"""
    t = (text or "").strip()
    if not t:
        return False
    keywords = [
        "啥都不用做",
        "你呆着就好",
        "别说话",
        "闭嘴",
        "安静点",
        "不用回",
        "不用回复",
        "不需要你",
    ]
    return any(k in t for k in keywords)


async def build_question_with_quote(event: dict, original_text: str) -> str:
    """
    如果当前消息是回复/引用另一条消息，则把被引用原文显式拼进问题里
    """
    try:
        msg = event.get("message", {}) or {}
        parent_id = msg.get("parent_id") or msg.get("root_id") or ""
        if not parent_id:
            return original_text
        quoted = await get_message_text_by_id(parent_id)
        if not quoted:
            return original_text
        return f"（当前这条消息是对下面这句话的回复/引用：{quoted}）\n{original_text}"
    except Exception as e:
        logger.warning(f"build_question_with_quote error: {e}")
        return original_text




async def run_with_thinking(
    chat_id: str,
    main_coro,
    delay: float = 5.0,
    enable_thinking: bool = True
):
    """
    若主任务在 delay 内未完成，先发一句"让我想想..."缓解等待
    """
    done = asyncio.Event()

    async def thinking():
        try:
            await asyncio.wait_for(done.wait(), timeout=delay)
        except asyncio.TimeoutError:
            if enable_thinking:
                await send_text_to_chat(chat_id, MSG_THINKING)
        except Exception as e:
            logger.debug(f"thinking helper error: {e}")

    thinking_task = asyncio.create_task(thinking())
    try:
        result = await main_coro
        return result
    finally:
        done.set()
        try:
            thinking_task.cancel()
        except Exception:
            pass


async def handle_user_question(
    chat_id: str,
    question: str,
    event: dict,
    message_id: str,
    image_keys: Optional[list[str]] = None,
    enable_thinking: bool = True
) -> None:
    """
    统一处理用户提问（被@或对话窗口内）

    Args:
        chat_id: 群聊ID
        question: 用户问题
        event: 消息事件
        message_id: 消息ID
        image_keys: 图片键列表
        enable_thinking: 是否启用"思考中"提示
    """
    # 获取上下文
    msgs = await get_recent_messages(chat_id, limit=config.MAX_CONTEXT_MESSAGES)
    if not msgs:
        msgs = get_chat_logs(chat_id, limit=config.MAX_CONTEXT_MESSAGES)
    context = build_context_summary(msgs, limit=config.MAX_CONTEXT_MESSAGES)

    # 处理引用/回复
    question_with_quote = await build_question_with_quote(event, question)

    # 获取图片
    images: list[bytes] = []
    mimes: list[str] = []
    if image_keys and message_id:
        for k in image_keys[:config.MAX_IMAGES_PER_MESSAGE]:
            b, mime = await get_message_image_bytes(message_id, k)
            if b:
                images.append(b)
                mimes.append(mime or "image/jpeg")

    # 检查是否为绘图请求（使用LLM进行意图分类）
    intent_result = await classify_intent(question, has_images=bool(images))
    if intent_result.get("task_type") == "draw":
        await handle_draw_request(chat_id, question, user_images=images or None)
        mark_conversation_active(chat_id)
        logger.info(f"Draw request handled: chat_id={chat_id} confidence={intent_result.get('confidence')}")
        return

    # 回答问题（可能带图片）
    await run_with_thinking(
        chat_id,
        _answer_with_context(
            chat_id,
            question_with_quote,
            context,
            images=images or None,
            image_mimes=mimes or None
        ),
        enable_thinking=enable_thinking and bool(images),
    )
    mark_conversation_active(chat_id)


async def _answer_with_context(
    chat_id: str,
    question: str,
    context: str,
    images: Optional[list[bytes]] = None,
    image_mimes: Optional[list[str]] = None,
):
    """
    基于上下文回答用户问题（内部辅助函数）

    Args:
        chat_id: 群聊ID
        question: 用户问题
        context: 群聊上下文
        images: 图片列表
        image_mimes: 图片MIME类型列表
    """
    system = SYSTEM_PROMPT_CHAT_ASSISTANT

    # 检查是否需要联网搜索或获取网页内容
    web_context = ""

    # 1. 检查问题中是否有 URL
    urls = extract_urls_from_text(question)
    if urls:
        logger.info(f"Found URLs in question: {urls}")
        url_contents = await process_urls_in_context(question, max_urls=2)
        if url_contents:
            web_context = "\n\n【网页内容】\n"
            for url, content in url_contents.items():
                web_context += f"来自 {url}:\n{content[:1000]}\n\n"

    # 2. 使用语义识别判断是否需要搜索实时信息
    if not web_context:
        needs_search = await should_use_web_search(question, context)
        if needs_search:
            logger.info(f"Web search needed: {question[:80]}")
            # 使用 web_search（如果需要）

    # 构建最终提示词
    prompt = PROMPT_TEMPLATE_CHAT.format(context=context, question=question)
    if web_context:
        prompt = (
            f"群上下文：\n{context}{web_context}\n\n"
            f"用户问题：{question}\n请用简短要点直接回答。"
        )

    logger.debug(
        f"_answer_with_context chat_id={chat_id} question='{question[:80]}' "
        f"web_context_len={len(web_context)}"
    )

    # 调用 LLM
    if images:
        reply = await call_llm_with_images(
            prompt,
            images=images,
            image_mimes=image_mimes,
            system=system,
            temperature=TEMPERATURE_CHAT,
        )
    else:
        reply = await call_llm(prompt, system, temperature=TEMPERATURE_CHAT)

    await send_text_to_chat(chat_id, reply)


async def maybe_proactive_engage(chat_id: str, text: str, ctx: str, threshold: float):
    """主动模式：根据参与度评分决策是否回复"""
    score = basic_engage_score(text)
    if score >= threshold:
        logger.debug(
            f"maybe_proactive_engage triggered chat_id={chat_id} "
            f"score={score} threshold={threshold}"
        )
        prompt = PROMPT_TEMPLATE_PROACTIVE.format(context=ctx, text=text)
        reply = await call_llm(
            prompt,
            SYSTEM_PROMPT_PROACTIVE,
            temperature=TEMPERATURE_PROACTIVE
        )
        await send_text_to_chat(chat_id, reply)
    else:
        logger.debug(
            f"maybe_proactive_engage skipped chat_id={chat_id} "
            f"score={score} threshold={threshold}"
        )


def parse_command(text: str) -> Optional[tuple]:
    """
    解析命令
    返回：(command, args) 或 None
    """
    if not text.startswith("/"):
        return None
    
    parts = text.strip().split()
    cmd = parts[0][1:].lower()  # 移除 / 并转小写
    args = parts[1:]
    
    return (cmd, args)


async def handle_message(event: dict, event_id: str):
    """
    消息处理的主入口
    
    Args:
        event: 飞书消息事件
        event_id: 事件ID（用于去重）
    """
    import time
    
    try:
        # 提取消息信息
        chat_id, user_id, text, image_keys, msg_type = extract_message_payload(event)
        message_obj = event.get("message", {}) or {}
        chat_type = message_obj.get("chat_type") or ""
        message_id = message_obj.get("message_id") or ""
        
        logger.debug(
            f"im.message.receive_v1 chat_id={chat_id} user_id={user_id} "
            f"text='{text[:200]}'"
        )
        logger.debug(
            "message meta chat_id=%s msg_type=%s images=%s",
            chat_id,
            msg_type,
            len(image_keys or []),
        )
        
        # 忽略非用户发送的消息
        sender = event.get("sender", {}) or {}
        sender_type = sender.get("sender_type") or sender.get("type") or ""
        if sender_type and sender_type != "user":
            logger.debug(
                f"ignore message from non-user sender_type={sender_type} user_id={user_id}"
            )
            return
        
        # 检查消息内容
        if not chat_id or (not (text or "").strip() and not image_keys):
            logger.debug("message missing chat_id or content, ignore")
            return
        
        # 保存到数据库和内存
        text_for_store = (text or "").strip()
        if image_keys:
            suffix = f"[图片x{len(image_keys)}]"
            text_for_store = (
                f"{text_for_store} {suffix}".strip()
                if text_for_store
                else suffix
            )
        
        await save_message_db(chat_id, user_id, text_for_store)

        # 添加到内存日志
        add_chat_log(chat_id, user_id, text_for_store)
        
        # 检查是否为命令
        cmd_result = parse_command(text)
        if cmd_result:
            cmd, args = cmd_result
            logger.info(f"Command detected: {cmd} args={args}")

            # 交由 event_handler 处理
            from .event_handler import handle_event
            await handle_event(
                event_type="command",
                chat_id=chat_id,
                command=cmd,
                args=args,
                user_id=user_id,
            )
            return

        # 被@情况
        if mentioned_bot(event):
            logger.info(
                f"mentioned_bot=True chat_id={chat_id} user_id={user_id} "
                f"text='{text[:80]}'"
            )
            await handle_user_question(
                chat_id=chat_id,
                question=text_for_store,
                event=event,
                message_id=message_id,
                image_keys=image_keys,
                enable_thinking=True
            )
            return
        
        # 对话粘性：在活跃窗口内且没有@别人时
        in_sticky_conversation = (
            chat_type == "group"
            and is_conversation_active(chat_id)
            and not mentions_someone_else(event)
        )

        if in_sticky_conversation:
            logger.info(
                "sticky_conversation=True chat_id=%s user_id=%s text='%s'",
                chat_id,
                user_id,
                text[:80],
            )

            if should_zip_reply(text):
                await send_text_to_chat(chat_id, "🤐")
                mark_conversation_active(chat_id)
                return

            # 使用统一的处理逻辑
            await handle_user_question(
                chat_id=chat_id,
                question=text_for_store,
                event=event,
                message_id=message_id,
                image_keys=image_keys,
                enable_thinking=True
            )
            return
        
        # 主动模式
        settings = await get_or_create_settings(chat_id, default_threshold=config.ENGAGE_DEFAULT_THRESHOLD)
        if settings["mode"] != "quiet":
            thr = settings["threshold"]
            logger.debug(
                f"proactive mode chat_id={chat_id} mode={settings['mode']} "
                f"threshold={thr}"
            )
            msgs = await get_recent_messages(chat_id, limit=12)
            if not msgs:
                msgs = get_chat_logs(chat_id, limit=12)
            ctx = build_context_summary(msgs, limit=12)
            await maybe_proactive_engage(chat_id, text, ctx, thr)
        else:
            logger.debug(f"mode=quiet, skip proactive chat_id={chat_id}")
            
    except Exception as e:
        logger.error(f"handle_message error event_id={event_id}: {e}")
