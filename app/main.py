"""
主应用入口 - 大幅精简版本
负责：FastAPI 初始化、数据库初始化、路由设置
业务逻辑全部委托给 connector、event_handler、message_handler
"""
import os
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from .database import init_db, run_migrations
from .connector import create_connector
from .message_handler import handle_message
from .event_handler import handle_event

# 日志配置
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

# FastAPI 应用
app = FastAPI()


@app.on_event("startup")
async def on_startup():
    """应用启动事件"""
    logger.info("FastAPI startup: init_db & migrations")
    
    # 初始化数据库
    await init_db()
    
    # 运行数据库迁移
    try:
        await run_migrations()
    except Exception as e:
        logger.warning(
            f"Database migration failed (may be expected if columns already exist): {e}"
        )


# 创建 webhook 处理器
_webhook_handler = create_connector(
    mode="webhook",
    handle_message_fn=handle_message,
    handle_event_fn=handle_event,
)


async def _handle_message_with_dedup(event: dict, event_id: str):
    """
    消息处理（带事件去重）
    """
    # 事件去重在 connector 中处理
    await handle_message(event, event_id)


@app.post("/feishu/events")
async def feishu_events(request: Request):
    """
    飞书 Webhook 事件接收入口
    """
    body = await request.json()
    try:
        result = await _webhook_handler(body)
        return JSONResponse(result)
    except Exception as e:
        logger.error(f"webhook_handler error: {e}")
        raise HTTPException(status_code=403, detail="invalid token")
