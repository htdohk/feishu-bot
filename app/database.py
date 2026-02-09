"""
数据库管理模块
合并了 db.py 和 migrations.py 的功能
"""
import os
import time
import logging
from typing import List, Dict

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, Float, Text, text
from sqlalchemy import select, update

DATABASE_URL = os.getenv("DATABASE_URL", "")

Base = declarative_base()
engine = None
Session = None

logger = logging.getLogger("feishu_bot.database")


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
    personality: Mapped[str] = mapped_column(String(32), default="chill", nullable=True)
    language_style: Mapped[str] = mapped_column(String(32), default="casual", nullable=True)
    response_length: Mapped[str] = mapped_column(String(16), default="normal", nullable=True)
    last_mention_time: Mapped[float] = mapped_column(Float(), default=0.0, nullable=True)


async def init_db():
    """初始化数据库"""
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


async def run_migrations():
    """运行数据库迁移"""
    if not engine:
        logger.warning("Database engine not initialized, skipping migration")
        return
    
    try:
        async with engine.begin() as conn:
            # 添加新的列（如果还不存在）
            columns_to_add = [
                ("personality", "VARCHAR(32) DEFAULT 'chill'"),
                ("language_style", "VARCHAR(32) DEFAULT 'casual'"),
                ("response_length", "VARCHAR(16) DEFAULT 'normal'"),
                ("last_mention_time", "FLOAT DEFAULT 0.0"),
            ]
            
            for col_name, col_def in columns_to_add:
                try:
                    await conn.execute(
                        text(f"ALTER TABLE settings ADD COLUMN IF NOT EXISTS {col_name} {col_def}")
                    )
                    logger.info(f"Added column {col_name}")
                except Exception as e:
                    error_msg = str(e).lower()
                    if "already exists" in error_msg or "duplicate" in error_msg or "column" in error_msg:
                        logger.info(f"Column {col_name} already exists, skipping")
                    else:
                        logger.warning(f"Error adding column {col_name}: {e}")
        
        logger.info("Migration completed successfully")
    except Exception as e:
        logger.error(f"Migration error: {e}")


async def save_message_db(chat_id: str, user_id: str, text: str):
    """保存消息到数据库"""
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
    """获取最近的消息"""
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
    """获取或创建群聊设置"""
    if not DATABASE_URL:
        return {"mode": "normal", "threshold": default_threshold}
    try:
        async with Session() as s:
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
    """更新阈值设置"""
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
    """更新模式设置"""
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
    """获取所有群聊ID"""
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
                logger.debug(f"Query failed: {e}")
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
                logger.debug(f"Query failed: {e}")
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
                logger.debug(f"Query failed: {e}")
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
                logger.debug(f"Query failed: {e}")
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
