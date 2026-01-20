import os
import json
import time
import asyncio
import logging
from typing import Deque, Dict, List, Optional, Tuple
from collections import defaultdict, deque

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .llm import call_llm, call_llm_with_images
from .feishu_api import (
    send_text_to_chat,
    upload_image,
    send_image_to_chat,
    verify_url_challenge,
    verify_token,
    parse_event,
    extract_message_payload,
    mentioned_bot,
    get_message_text_by_id,
    get_message_image_bytes,
)
from .image_gen import (
    is_draw_request,
    has_reference_intent,
    generate_image,
)
from .constants import (
    MSG_DRAWING,
    MSG_DRAW_SUCCESS,
)
from .db import (
    init_db,
    save_message_db,
    get_recent_messages,
    get_or_create_settings,
    update_settings_threshold,
    update_settings_mode,
    list_chat_ids,
)
from .semantic_intent import (
    detect_user_intent,
    should_respond_to_message,
)
from .message_heat import (
    calculate_message_heat,
    should_respond_based_on_heat,
)
from .personality import (
    get_personality_config,
)
from .web_search import (
    fetch_webpage_content,
    search_with_searxng,
    extract_urls_from_text,
    process_urls_in_context,
    should_use_web_search,
)
from .migrations import run_migrations


# -----------------------
# 日志配置（通过环境变量 LOG_LEVEL 控制级别）
# -----------------------
LOG_LEVEL_NAME = os.getenv("LOG_LEVEL", "INFO").upper()
_LEVEL_MAP = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}
logging.basicConfig(
    level=_LEVEL_MAP.get(LOG_LEVEL_NAME, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("feishu_bot.main")


BOT_NAME = os.getenv("BOT_NAME", "群助手")
BOT_USER_ID = os.getenv("BOT_USER_ID", "")
ENGAGE_DEFAULT = 0.65
CONVERSATION_TTL_SECONDS = int(os.getenv("CONVERSATION_TTL_SECONDS", "600"))  # 群聊“默认仍在对话”窗口

# 内存回退（DB 异常时仍可运行）
chat_logs: Dict[str, Deque[dict]] = defaultdict(lambda: deque(maxlen=2000))

# 群聊会话粘性：最近一次@机器人（或机器人回复）后，在一段时间内无需再@也会继续回复
conversation_active_until: Dict[str, float] = defaultdict(float)

# 简单事件去重（防止飞书重试导致重复回复）
recent_event_ids: Deque[str] = deque(maxlen=5000)
recent_event_set: set = set()


def is_event_processed(event_id: str) -> bool:
    """
    返回 True 表示该 event_id 已处理过，本次应直接忽略。
    为简单起见使用进程内去重，如有多实例部署可改为 Redis/DB。
    """
    if not event_id:
        return False
    if event_id in recent_event_set:
        logger.debug(f"skip duplicated event_id={event_id}")
        return True
    recent_event_ids.append(event_id)
    recent_event_set.add(event_id)
    # 当 deque 发生淘汰时，重建 set，避免无限增长
    if len(recent_event_ids) >= recent_event_ids.maxlen:
        logger.debug("recent_event_ids reached maxlen, rebuilding recent_event_set")
        recent_event_set.clear()
        recent_event_set.update(recent_event_ids)
    logger.debug(f"mark event_id={event_id} as processed")
    return False

app = FastAPI()
scheduler = AsyncIOScheduler()

def basic_engage_score(text: str) -> float:
    lowers = text.lower()
    score = 0.0
    keywords = ["怎么", "如何", "为啥", "为什么", "怎么办", "谁知道", "有链接吗", "总结", "结论", "进展", "?", "？"]
    for kw in keywords:
        if kw in text or kw in lowers:
            score += 0.2
    if "?" in text or "？" in text:
        score += 0.2
    final = min(score, 1.0)
    logger.debug(f"basic_engage_score text='{text[:50]}' score={final}")
    return final

def build_context_summary(messages: List[dict], limit: int = 15) -> str:
    tail = messages[-limit:]
    lines = []
    for m in tail:
        who = (m.get("user_id","") or "")[-6:]
        lines.append(f"{m.get('ts','')}-{who}: {m.get('text','')}")
    return "\n".join(lines)

def mark_conversation_active(chat_id: str):
    if not chat_id:
        return
    conversation_active_until[chat_id] = time.time() + CONVERSATION_TTL_SECONDS

def is_conversation_active(chat_id: str) -> bool:
    if not chat_id:
        return False
    return time.time() <= (conversation_active_until.get(chat_id, 0.0) or 0.0)

def mentions_someone_else(message_event: dict) -> bool:
    """
    如果本条消息@了别人但没@机器人，则视为“明显不是对机器人说”，避免误插话。
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

async def answer_when_mentioned(
    chat_id: str,
    question: str,
    context: str,
    images: Optional[List[bytes]] = None,
    image_mimes: Optional[List[str]] = None,
):
    system = (
        "你是群聊助手，说话像人类、直接、不啰嗦。"
        "输出要求：1) 先给结论/建议；2) 最多5条要点，每条不超20字；"
        "3) 不要自夸/推销/寒暄，不要'如果你需要我还能...'；"
        "4) 有图片就结合图片和文字给出具体改进。"
    )
    
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
            logger.info(f"Semantic intent detected need for web search: {question[:80]}")
            search_results, error = await search_with_searxng(question, num_results=3)
            if search_results:
                web_context = f"\n\n【搜索结果】\n{search_results}"
            elif error:
                logger.warning(f"Web search failed: {error}")
    
    # 构建最终提示词
    prompt = f"群上下文：\n{context}"
    if web_context:
        prompt += web_context
    prompt += f"\n\n用户问题：{question}\n请用简短要点直接回答。"
    
    logger.debug(f"answer_when_mentioned chat_id={chat_id} question='{question[:80]}' web_context_len={len(web_context)}")
    if images:
        reply = await call_llm_with_images(
            prompt, images=images, image_mimes=image_mimes, system=system, temperature=0.2
        )
    else:
        reply = await call_llm(prompt, system, temperature=0.2)
    await send_text_to_chat(chat_id, reply)
    # 机器人回复也延长对话窗口
    mark_conversation_active(chat_id)

async def maybe_proactive_engage(chat_id: str, text: str, ctx: str, threshold: float):
    score = basic_engage_score(text)
    if score >= threshold:
        logger.debug(
            f"maybe_proactive_engage triggered chat_id={chat_id} "
            f"score={score} threshold={threshold}"
        )
        prompt = (
            f"群上下文：\n{ctx}\n\n有人说：{text}\n"
            f"请用口语化、极简要点回应："
            f"1) 最多3条，每条不超20字；"
            f"2) 不要客套/自夸/推销；"
            f"3) 只说核心见解或下一步建议。"
        )
        reply = await call_llm(prompt, temperature=0.3)
        await send_text_to_chat(chat_id, reply)
    else:
        logger.debug(
            f"maybe_proactive_engage skipped chat_id={chat_id} "
            f"score={score} threshold={threshold}"
        )

async def summarize_chat(chat_id: str, period: str = "weekly"):
    msgs = await get_recent_messages(chat_id, limit=400)
    if not msgs and chat_id in chat_logs:
        msgs = list(chat_logs[chat_id])
    if not msgs:
        logger.info(f"summarize_chat chat_id={chat_id} period={period} no messages")
        await send_text_to_chat(chat_id, f"最近没有足够的消息用于{period}总结。")
        return
    system = "你是擅长做会议/群聊总结的助理。"
    prompt = (
        f"请对以下群聊做{period}总结：\n"
        f"- 输出：主题Top N、关键结论/决定、待办与负责人、参考链接/原话片段、活跃度与情绪（可选）。\n"
        f"- 语气客观，条理清晰。\n\n"
        f"片段：\n{build_context_summary(msgs, limit=120)}"
    )
    logger.info(f"summarize_chat chat_id={chat_id} period={period} start LLM")
    report = await call_llm(prompt, system, temperature=0.3)
    await send_text_to_chat(chat_id, f"{period}总结：\n{report}")

async def welcome_new_user(chat_id: str, new_user_name: str):
    msgs = await get_recent_messages(chat_id, limit=80)
    if not msgs and chat_id in chat_logs:
        msgs = list(chat_logs[chat_id])[-80:]
    ctx = build_context_summary(msgs, limit=40)
    prompt = (f"为新成员写一段40~80字的欢迎语，并附上过去两周群里讨论的主题关键词与一个开场建议。\n上下文示例：\n{ctx}")
    logger.info(f"welcome_new_user chat_id={chat_id} name={new_user_name}")
    text = await call_llm(prompt, temperature=0.5)
    await send_text_to_chat(chat_id, f"欢迎 {new_user_name} 加入！\n{text}\n可使用 /help 查看指令。")


async def build_question_with_quote(event: dict, original_text: str) -> str:
    """
    如果当前消息是"回复/引用"另一条消息，则把被引用原文显式拼进问题里，
    让 LLM 更清楚"这条消息"指的是哪一句。
    """
    try:
        msg = event.get("message", {}) or {}
        parent_id = msg.get("parent_id") or msg.get("root_id") or ""
        if not parent_id:
            return original_text
        quoted = await get_message_text_by_id(parent_id)
        if not quoted:
            return original_text
        # 在问题前面加一行注释，保持原问题内容不变
        return f"（当前这条消息是对下面这句话的回复/引用：{quoted}）\n{original_text}"
    except Exception as e:
        logger.warning(f"build_question_with_quote error: {e}")
        return original_text


async def handle_draw_request(
    chat_id: str,
    text: str,
    user_images: Optional[List[bytes]] = None
):
    """
    处理绘图请求
    
    Args:
        chat_id: 群聊ID
        text: 用户文本
        user_images: 用户上传的图片（用作参考图）
    """
    logger.info(f"handle_draw_request chat_id={chat_id} text='{text[:80]}' has_ref_image={bool(user_images)}")
    
    # 发送"正在绘制"提示
    await send_text_to_chat(chat_id, MSG_DRAWING)
    
    # 判断是否有参考图片意图
    # 如果用户上传了图片，默认作为参考图片使用（除非明确说不用）
    reference_image = None
    if user_images:
        # 检查是否有明确的"不用参考"意图
        no_ref_keywords = ["不用参考", "不参考", "忽略图片", "不基于", "独立创作"]
        has_no_ref_intent = any(kw in text for kw in no_ref_keywords)
        
        if not has_no_ref_intent:
            # 默认使用上传的图片作为参考
            reference_image = user_images[0]
            logger.info(f"Using reference image, size={len(reference_image)} bytes")
        else:
            logger.info(f"User explicitly requested not to use reference image")
    
    # 生成图片
    image_bytes, error = await generate_image(
        prompt=text,
        reference_image=reference_image
    )
    
    if error:
        # 生成失败，发送错误消息
        await send_text_to_chat(chat_id, error)
        return
    
    if not image_bytes:
        await send_text_to_chat(chat_id, "图片生成失败，请稍后重试")
        return
    
    # 上传图片到飞书
    image_key, upload_error = await upload_image(image_bytes)
    if upload_error:
        await send_text_to_chat(chat_id, f"图片上传失败: {upload_error}")
        return
    
    # 发送图片
    await send_image_to_chat(chat_id, image_key, MSG_DRAW_SUCCESS)
    logger.info(f"Draw request completed successfully for chat_id={chat_id}")


async def run_with_thinking(chat_id: str, main_coro, delay: float = 5.0, enable_thinking: bool = True):
    """
    若主任务在 delay 内未完成,先发一句"让我想想..."缓解等待；主任务完成后正常回复。
    enable_thinking: 是否启用"让我想想"提示，仅在多模态消息时启用
    """
    done = asyncio.Event()

    async def thinking():
        try:
            await asyncio.wait_for(done.wait(), timeout=delay)
        except asyncio.TimeoutError:
            if enable_thinking:
                await send_text_to_chat(chat_id, "让我想想……")
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

@app.on_event("startup")
async def on_startup():
    logger.info("FastAPI startup: init_db & scheduler")
    await init_db()
    # 运行数据库迁移
    try:
        await run_migrations()
    except Exception as e:
        logger.warning(f"Database migration failed (may be expected if columns already exist): {e}")
    # 定时任务：周报（每周一 09:00）与月报（每月1日 09:00）
    scheduler.add_job(
        func=lambda: app.router.lifespan_context,  # 占位，防报错
        trigger=CronTrigger(day_of_week="mon", hour=9, minute=0),
        id="noop", replace_existing=True
    )
    scheduler.add_job(
        func=lambda: None,
        trigger=CronTrigger(day="1", hour=9, minute=0),
        id="noop2", replace_existing=True
    )
    # 真正任务
    scheduler.add_job(func=run_periodic_summary_weekly, trigger=CronTrigger(day_of_week="mon", hour=9, minute=0), id="weekly_summary", replace_existing=True)
    scheduler.add_job(func=run_periodic_summary_monthly, trigger=CronTrigger(day="1", hour=9, minute=0), id="monthly_summary", replace_existing=True)
    scheduler.start()

async def run_periodic_summary_weekly():
    logger.info("run_periodic_summary_weekly started")
    for chat_id in await list_chat_ids():
        try:
            await summarize_chat(chat_id, "weekly")
        except Exception as e:
            logger.error(f"[weekly] summary for {chat_id} failed: {e}")

async def run_periodic_summary_monthly():
    logger.info("run_periodic_summary_monthly started")
    for chat_id in await list_chat_ids():
        try:
            await summarize_chat(chat_id, "monthly")
        except Exception as e:
            logger.error(f"[monthly] summary for {chat_id} failed: {e}")


async def handle_message_event(event: dict, event_id: str):
    """
    将耗时处理（拉图、调用 LLM）放到后台，避免 webhook 超时被飞书重试。
    """
    try:
        chat_id, user_id, text, image_keys, msg_type = extract_message_payload(event)
        message_obj = (event.get("message", {}) or {})
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

        # 忽略机器人自身或非用户（系统/应用）发送的消息，防止自我触发导致“自己跟自己聊天”
        sender = event.get("sender", {}) or {}
        sender_type = sender.get("sender_type") or sender.get("type") or ""
        if sender_type and sender_type != "user":
            logger.debug(
                f"ignore message from non-user sender_type={sender_type} user_id={user_id}"
            )
            return
        if BOT_USER_ID and user_id == BOT_USER_ID:
            logger.debug(f"ignore message from bot itself BOT_USER_ID={BOT_USER_ID}")
            return
        # DEBUG: mention 结构
        try:
            msg = event.get("message", {})
            logger.debug(
                "mentions=%s keys=%s ids=%s",
                json.dumps(msg.get("mentions", []), ensure_ascii=False),
                [m.get("key") for m in (msg.get("mentions") or [])],
                json.dumps(
                    [m.get("id") for m in (msg.get("mentions") or [])],
                    ensure_ascii=False,
                ),
            )
        except Exception as e:
            logger.warning(f"[DEBUG] mention debug error: {e}")

        if not chat_id or (not (text or "").strip() and not image_keys):
            logger.debug("message missing chat_id or content(text/image), ignore")
            return

        # 存DB（若DB异常会在内部降级为不阻塞）
        text_for_store = (text or "").strip()
        if image_keys:
            # DB 里保留一个可读的占位，避免“纯图片”在上下文里丢失
            suffix = f"[图片x{len(image_keys)}]"
            text_for_store = f"{text_for_store} {suffix}".strip() if text_for_store else suffix
        await save_message_db(chat_id, user_id, text_for_store)

        # 内存也存一份，保障上下文
        ts = time.strftime("%m-%d %H:%M", time.localtime())
        if chat_id not in chat_logs:
            chat_logs[chat_id] = deque(maxlen=2000)
        chat_logs[chat_id].append({"ts": ts, "user_id": user_id, "text": text_for_store})
        logger.debug(
            f"append chat_logs chat_id={chat_id} "
            f"len={len(chat_logs[chat_id])} ts={ts}"
        )

        # 命令
        if text.startswith("/"):
            parts = text.strip().split()
            cmd = parts[0].lower()
            args = parts[1:]
            if cmd == "/help":
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
                return
            if cmd == "/summary":
                period = (args[0].lower() if args else "weekly")
                if period not in ("weekly","monthly"):
                    period = "weekly"
                logger.info(f"/summary {period} in chat_id={chat_id}")
                await summarize_chat(chat_id, period)
                return
            if cmd == "/settings" and len(args) >= 2:
                key, val = args[0].lower(), args[1].lower()
                if key == "threshold":
                    try:
                        t = float(val); t = max(0.0, min(1.0, t))
                        await update_settings_threshold(chat_id, t)
                        logger.info(f"/settings threshold chat_id={chat_id} t={t}")
                        await send_text_to_chat(chat_id, f"已将主动发言阈值设置为 {t}")
                    except:
                        logger.warning(
                            f"/settings threshold parse error chat_id={chat_id} val={val}"
                        )
                        await send_text_to_chat(chat_id, "阈值需为0~1数字，例如 /settings threshold 0.65")
                elif key == "mode" and val in ("quiet","normal","active"):
                    await update_settings_mode(chat_id, val)
                    logger.info(f"/settings mode chat_id={chat_id} mode={val}")
                    await send_text_to_chat(chat_id, f"已切换模式为 {val}")
                else:
                    logger.warning(
                        f"/settings unknown key or value chat_id={chat_id} "
                        f"key={key} val={val}"
                    )
                    await send_text_to_chat(chat_id, "未识别的设置项。")
                return
            if cmd == "/optout":
                logger.info(f"/optout in chat_id={chat_id} user_id={user_id}")
                await send_text_to_chat(chat_id, "已记录；后续公共总结将不展示你的个人条目。")
                return
            if cmd == "/reset":
                logger.info(f"/reset in chat_id={chat_id}")
                # 清空群聊的会话记录
                if chat_id in chat_logs:
                    chat_logs[chat_id].clear()
                if chat_id in conversation_active_until:
                    del conversation_active_until[chat_id]
                # 重置数据库中的设置为默认值
                await update_settings_threshold(chat_id, ENGAGE_DEFAULT)
                await update_settings_mode(chat_id, "normal")
                await send_text_to_chat(chat_id, "已重置 Bot 状态：\n- 清空会话记录\n- 重置主动发言阈值为 0.65\n- 重置发言模式为 normal\n- 忘记所有之前的对话上下文")
                return

        # 群聊：被@则直接回答，并进入“无需再@也继续回复”的窗口
        if mentioned_bot(event):
            logger.info(
                f"mentioned_bot=True chat_id={chat_id} user_id={user_id} text='{text[:80]}'"
            )
            mark_conversation_active(chat_id)
            # 取最近上下文
            msgs = await get_recent_messages(chat_id, limit=20)
            if not msgs and chat_id in chat_logs:
                msgs = list(chat_logs[chat_id])[-20:]
            ctx = build_context_summary(msgs, limit=20)
            question = await build_question_with_quote(event, text_for_store)
            images: List[bytes] = []
            mimes: List[str] = []
            if image_keys and message_id:
                for k in image_keys[:4]:
                    b, mime = await get_message_image_bytes(message_id, k)
                    if b:
                        images.append(b)
                        mimes.append(mime or "image/jpeg")
            
            # 检查是否为绘图请求
            if is_draw_request(text):
                await handle_draw_request(chat_id, text, user_images=images or None)
                mark_conversation_active(chat_id)
                return
            
            # 仅在有图片时才启用"让我想想"提示
            await run_with_thinking(
                chat_id,
                answer_when_mentioned(
                    chat_id, question, ctx, images=images or None, image_mimes=mimes or None
                ),
                enable_thinking=bool(images),
            )
            return

        # 群聊“对话粘性”：在活跃窗口内且没有@别人时，也当成在对机器人说
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
            # 特殊：像人类一样“拉上拉链”
            if should_zip_reply(text):
                await send_text_to_chat(chat_id, "🤐")
                mark_conversation_active(chat_id)
                return

            msgs = await get_recent_messages(chat_id, limit=20)
            if not msgs and chat_id in chat_logs:
                msgs = list(chat_logs[chat_id])[-20:]
            ctx = build_context_summary(msgs, limit=20)
            question = await build_question_with_quote(event, text_for_store)
            images: List[bytes] = []
            mimes: List[str] = []
            if image_keys and message_id:
                for k in image_keys[:4]:
                    b, mime = await get_message_image_bytes(message_id, k)
                    if b:
                        images.append(b)
                        mimes.append(mime or "image/jpeg")
            
            # 检查是否为绘图请求
            if is_draw_request(text):
                await handle_draw_request(chat_id, text, user_images=images or None)
                mark_conversation_active(chat_id)
                return
            
            # 仅在有图片时才启用"让我想想"提示
            await run_with_thinking(
                chat_id,
                answer_when_mentioned(
                    chat_id, question, ctx, images=images or None, image_mimes=mimes or None
                ),
                enable_thinking=bool(images),
            )
            return

        # 主动模式
        settings = await get_or_create_settings(chat_id, default_threshold=ENGAGE_DEFAULT)
        if settings["mode"] != "quiet":
            thr = settings["threshold"]
             # 记录当前模式与阈值
            logger.debug(
                f"proactive mode chat_id={chat_id} mode={settings['mode']} "
                f"threshold={thr}"
            )
            msgs = await get_recent_messages(chat_id, limit=12)
            if not msgs and chat_id in chat_logs:
                msgs = list(chat_logs[chat_id])[-12:]
            ctx = build_context_summary(msgs, limit=12)
            await maybe_proactive_engage(chat_id, text, ctx, thr)
        else:
            logger.debug(f"mode=quiet, skip proactive chat_id={chat_id}")
    except Exception as e:
        logger.error(f"handle_message_event error event_id={event_id}: {e}")


@app.post("/feishu/events")
async def feishu_events(request: Request):
    body = await request.json()
    logger.debug(f"/feishu/events raw_body={json.dumps(body, ensure_ascii=False)[:500]}")
    ch = verify_url_challenge(body)
    if ch:
        logger.info("received url_verification challenge")
        return JSONResponse({"challenge": ch})

    if not verify_token(body):
        logger.warning("verify_token failed")
        raise HTTPException(status_code=403, detail="invalid token")

    event_type, event = parse_event(body)
    event_id = body.get("header", {}).get("event_id") or body.get("event_id") or ""

    # 飞书会在超时/失败时重试推送，同一 event_id 不应重复处理
    if is_event_processed(event_id):
        return JSONResponse({"code": 0})

    logger.debug(f"parsed event_type={event_type} event_id={event_id}")

    # 消息事件
    if event_type == "im.message.receive_v1":
        asyncio.create_task(handle_message_event(event, event_id))
        # 立即返回，避免飞书重试
        return JSONResponse({"code": 0})

    # 新成员加入
    if event_type.startswith("im.chat.member") and "add" in event_type or "user_added" in event_type:
        chat_id = (event.get("chat_id") or event.get("chat", {}).get("chat_id") or "")
        members = event.get("users") or event.get("members") or []
        if chat_id and members:
            name = members[0].get("name") or "新同学"
            logger.info(
                f"new member event chat_id={chat_id} name={name} "
                f"members_count={len(members)}"
            )
            await welcome_new_user(chat_id, name)
        return JSONResponse({"code": 0})

    return JSONResponse({"code": 0})
