import os
import time
import logging
from typing import List, Dict

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, Float, Text
from sqlalchemy import select, update

DATABASE_URL = os.getenv("DATABASE_URL", "")

Base = declarative_base()
engine = None
Session = None

logger = logging.getLogger("feishu_bot.db")


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    text: Mapped[str] = mapped_column(Text())
    ts: Mapped[str] = mapped_column(String(32), index=True)


class Setting(Base):
    __tablename__ = "settings"
    chat_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    mode: Mapped[str] = mapped_column(String(16), default="normal")
    threshold: Mapped[float] = mapped_column(Float(), default=0.65)
    personality: Mapped[str] = mapped_column(String(32), default="chill", nullable=True)  # chill/professional/humorous
    language_style: Mapped[str] = mapped_column(String(32), default="casual", nullable=True)  # casual/formal/technical
    response_length: Mapped[str] = mapped_column(String(16), default="normal", nullable=True)  # brief/normal/detailed
    last_mention_time: Mapped[float] = mapped_column(Float(), default=0.0, nullable=True)  # 上一次 @bot 的时间戳


async def init_db():
    global engine, Session
    if not DATABASE_URL:
        logger.warning("DATABASE_URL not set, DB features disabled")
        return
    logger.info("init_db creating engine for DATABASE_URL=%s", DATABASE_URL)
    engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("init_db finished")


async def save_message_db(chat_id: str, user_id: str, text: str):
    if not DATABASE_URL:
        return
    from sqlalchemy.exc import SQLAlchemyError

    try:
        async with Session() as s:
            m = Message(
                chat_id=chat_id,
                user_id=user_id,
                text=text,
                ts=time.strftime("%m-%d %H:%M", time.localtime()),
            )
            s.add(m)
            await s.commit()
        logger.debug(
            "save_message_db chat_id=%s user_id=%s text_len=%s",
            chat_id,
            user_id,
            len(text),
        )
    except SQLAlchemyError as e:
        logger.error(f"[DB] save_message error: {e}")


async def get_recent_messages(chat_id: str, limit: int = 50) -> List[Dict]:
    if not DATABASE_URL:
        return []
    try:
        async with Session() as s:
            q = await s.execute(
                select(Message)
                .where(Message.chat_id == chat_id)
                .order_by(Message.id.desc())
                .limit(limit)
            )
            rows = list(reversed(q.scalars().all()))
            logger.debug(
                "get_recent_messages chat_id=%s limit=%s got=%s",
                chat_id,
                limit,
                len(rows),
            )
            return [{"ts": r.ts, "user_id": r.user_id, "text": r.text} for r in rows]
    except Exception as e:
        logger.error(f"[DB] get_recent_messages error: {e}")
        return []


async def get_or_create_settings(chat_id: str, default_threshold: float = 0.65) -> Dict:
    if not DATABASE_URL:
        return {"mode": "normal", "threshold": default_threshold}
    try:
        async with Session() as s:
            try:
                # 尝试查询所有列（包括新列）
                q = await s.execute(select(Setting).where(Setting.chat_id == chat_id))
                obj = q.scalar_one_or_none()
                if obj:
                    logger.debug(
                        "get_or_create_settings existing chat_id=%s mode=%s threshold=%s",
                        chat_id,
                        obj.mode,
                        obj.threshold,
                    )
                    return {"mode": obj.mode, "threshold": obj.threshold}
            except Exception as e:
                # 如果新列不存在，只查询旧列
                logger.debug(f"Full query failed, falling back to basic columns: {e}")
                await s.rollback()
                # 创建新会话重试
                async with Session() as s2:
                    q = await s2.execute(
                        select(Setting.chat_id, Setting.mode, Setting.threshold).where(Setting.chat_id == chat_id)
                    )
                    row = q.first()
                    if row:
                        return {"mode": row[1], "threshold": row[2]}
        
        # 如果不存在，创建新的
        async with Session() as s:
            obj = Setting(chat_id=chat_id, mode="normal", threshold=default_threshold)
            s.add(obj)
            await s.commit()
            logger.info(
                "get_or_create_settings created default chat_id=%s mode=%s threshold=%s",
                chat_id,
                obj.mode,
                obj.threshold,
            )
            return {"mode": obj.mode, "threshold": obj.threshold}
    except Exception as e:
        logger.error(f"[DB] get_or_create_settings error: {e}")
        return {"mode": "normal", "threshold": default_threshold}


async def update_settings_threshold(chat_id: str, value: float):
    if not DATABASE_URL:
        return
    try:
        async with Session() as s:
            try:
                q = await s.execute(select(Setting).where(Setting.chat_id == chat_id))
                obj = q.scalar_one_or_none()
                if obj:
                    obj.threshold = value
                    await s.commit()
                    logger.info("update_settings_threshold chat_id=%s value=%s", chat_id, value)
                    return
            except Exception as e:
                logger.debug(f"Query failed in update_settings_threshold: {e}")
                await s.rollback()
        
        # 如果查询失败或对象不存在，创建新会话重试
        async with Session() as s2:
            q = await s2.execute(select(Setting).where(Setting.chat_id == chat_id))
            obj = q.scalar_one_or_none()
            if obj:
                obj.threshold = value
            else:
                obj = Setting(chat_id=chat_id, threshold=value)
                s2.add(obj)
            await s2.commit()
            logger.info("update_settings_threshold chat_id=%s value=%s", chat_id, value)
    except Exception as e:
        logger.error(f"[DB] update_settings_threshold error: {e}")


async def update_settings_mode(chat_id: str, mode: str):
    if not DATABASE_URL:
        return
    try:
        async with Session() as s:
            try:
                q = await s.execute(select(Setting).where(Setting.chat_id == chat_id))
                obj = q.scalar_one_or_none()
                if obj:
                    obj.mode = mode
                    await s.commit()
                    logger.info("update_settings_mode chat_id=%s mode=%s", chat_id, mode)
                    return
            except Exception as e:
                logger.debug(f"Query failed in update_settings_mode: {e}")
                await s.rollback()
        
        # 如果查询失败或对象不存在，创建新会话重试
        async with Session() as s2:
            q = await s2.execute(select(Setting).where(Setting.chat_id == chat_id))
            obj = q.scalar_one_or_none()
            if obj:
                obj.mode = mode
            else:
                obj = Setting(chat_id=chat_id, mode=mode)
                s2.add(obj)
            await s2.commit()
            logger.info("update_settings_mode chat_id=%s mode=%s", chat_id, mode)
    except Exception as e:
        logger.error(f"[DB] update_settings_mode error: {e}")


async def list_chat_ids() -> List[str]:
    if not DATABASE_URL:
        return []
    try:
        async with Session() as s:
            q = await s.execute(select(Setting.chat_id))
            rows = [row[0] for row in q.all()]
            logger.debug("list_chat_ids count=%s", len(rows))
            return rows
    except Exception as e:
        logger.error(f"[DB] list_chat_ids error: {e}")
        return []


async def update_settings_personality(chat_id: str, personality: str):
    """更新群聊性格设置"""
    if not DATABASE_URL:
        return
    try:
        async with Session() as s:
            try:
                q = await s.execute(select(Setting).where(Setting.chat_id == chat_id))
                obj = q.scalar_one_or_none()
                if obj:
                    obj.personality = personality
                    await s.commit()
                    logger.info("update_settings_personality chat_id=%s personality=%s", chat_id, personality)
                    return
            except Exception as e:
                logger.debug(f"Query failed in update_settings_personality: {e}")
                await s.rollback()
        
        async with Session() as s2:
            q = await s2.execute(select(Setting).where(Setting.chat_id == chat_id))
            obj = q.scalar_one_or_none()
            if obj:
                obj.personality = personality
            else:
                obj = Setting(chat_id=chat_id, personality=personality)
                s2.add(obj)
            await s2.commit()
            logger.info("update_settings_personality chat_id=%s personality=%s", chat_id, personality)
    except Exception as e:
        logger.error(f"[DB] update_settings_personality error: {e}")


async def update_settings_language_style(chat_id: str, language_style: str):
    """更新群聊语言风格设置"""
    if not DATABASE_URL:
        return
    try:
        async with Session() as s:
            try:
                q = await s.execute(select(Setting).where(Setting.chat_id == chat_id))
                obj = q.scalar_one_or_none()
                if obj:
                    obj.language_style = language_style
                    await s.commit()
                    logger.info("update_settings_language_style chat_id=%s style=%s", chat_id, language_style)
                    return
            except Exception as e:
                logger.debug(f"Query failed in update_settings_language_style: {e}")
                await s.rollback()
        
        async with Session() as s2:
            q = await s2.execute(select(Setting).where(Setting.chat_id == chat_id))
            obj = q.scalar_one_or_none()
            if obj:
                obj.language_style = language_style
            else:
                obj = Setting(chat_id=chat_id, language_style=language_style)
                s2.add(obj)
            await s2.commit()
            logger.info("update_settings_language_style chat_id=%s style=%s", chat_id, language_style)
    except Exception as e:
        logger.error(f"[DB] update_settings_language_style error: {e}")


async def update_settings_response_length(chat_id: str, response_length: str):
    """更新群聊回复长度设置"""
    if not DATABASE_URL:
        return
    try:
        async with Session() as s:
            try:
                q = await s.execute(select(Setting).where(Setting.chat_id == chat_id))
                obj = q.scalar_one_or_none()
                if obj:
                    obj.response_length = response_length
                    await s.commit()
                    logger.info("update_settings_response_length chat_id=%s length=%s", chat_id, response_length)
                    return
            except Exception as e:
                logger.debug(f"Query failed in update_settings_response_length: {e}")
                await s.rollback()
        
        async with Session() as s2:
            q = await s2.execute(select(Setting).where(Setting.chat_id == chat_id))
            obj = q.scalar_one_or_none()
            if obj:
                obj.response_length = response_length
            else:
                obj = Setting(chat_id=chat_id, response_length=response_length)
                s2.add(obj)
            await s2.commit()
            logger.info("update_settings_response_length chat_id=%s length=%s", chat_id, response_length)
    except Exception as e:
        logger.error(f"[DB] update_settings_response_length error: {e}")


async def update_last_mention_time(chat_id: str, timestamp: float):
    """更新上一次 @bot 的时间戳"""
    if not DATABASE_URL:
        return
    try:
        async with Session() as s:
            try:
                q = await s.execute(select(Setting).where(Setting.chat_id == chat_id))
                obj = q.scalar_one_or_none()
                if obj:
                    obj.last_mention_time = timestamp
                    await s.commit()
                    logger.debug("update_last_mention_time chat_id=%s timestamp=%s", chat_id, timestamp)
                    return
            except Exception as e:
                logger.debug(f"Query failed in update_last_mention_time: {e}")
                await s.rollback()
        
        async with Session() as s2:
            q = await s2.execute(select(Setting).where(Setting.chat_id == chat_id))
            obj = q.scalar_one_or_none()
            if obj:
                obj.last_mention_time = timestamp
            else:
                obj = Setting(chat_id=chat_id, last_mention_time=timestamp)
                s2.add(obj)
            await s2.commit()
            logger.debug("update_last_mention_time chat_id=%s timestamp=%s", chat_id, timestamp)
    except Exception as e:
        logger.error(f"[DB] update_last_mention_time error: {e}")
