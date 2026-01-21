"""
数据库迁移脚本
用于添加新的列到现有表
"""
import logging
from sqlalchemy import text
from .db import engine

logger = logging.getLogger("feishu_bot.migrations")


async def migrate_add_personality_columns():
    """
    添加个性化配置列到 settings 表
    """
    if not engine:
        logger.warning("Database engine not initialized, skipping migration")
        return
    
    async with engine.begin() as conn:
        try:
            # 逐个添加列，避免一次性添加失败
            columns_to_add = [
                ("personality", "VARCHAR(32) DEFAULT 'chill'"),
                ("language_style", "VARCHAR(32) DEFAULT 'casual'"),
                ("response_length", "VARCHAR(16) DEFAULT 'normal'"),
                ("last_mention_time", "FLOAT DEFAULT 0.0"),
            ]
            
            for col_name, col_def in columns_to_add:
                try:
                    # 使用 IF NOT EXISTS 语法（PostgreSQL 9.1+）
                    await conn.execute(
                        text(f"ALTER TABLE settings ADD COLUMN IF NOT EXISTS {col_name} {col_def}")
                    )
                    logger.info(f"Added column {col_name}")
                except Exception as e:
                    # 如果列已存在或其他错误，记录但继续
                    error_msg = str(e).lower()
                    if "already exists" in error_msg or "duplicate" in error_msg or "column" in error_msg:
                        logger.info(f"Column {col_name} already exists or migration skipped: {e}")
                    else:
                        logger.warning(f"Error adding column {col_name}: {e}")
            
            logger.info("Migration completed successfully")
            
        except Exception as e:
            logger.error(f"Migration error: {e}")
            # 不抛出异常，允许应用继续运行


async def run_migrations():
    """
    运行所有迁移
    """
    logger.info("Starting database migrations...")
    try:
        await migrate_add_personality_columns()
        logger.info("All migrations completed")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise
