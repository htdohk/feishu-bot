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


@app.on_event("shutdown")
async def on_shutdown():
    """应用关闭事件"""
    logger.info("FastAPI shutdown: cleanup resources")

    # 关闭 HTTP 客户端
    try:
        from .llm import close_http_client
        await close_http_client()
    except Exception as e:
        logger.warning(f"Failed to close HTTP client: {e}")


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
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse request body: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    try:
        result = await _webhook_handler(body)
        return JSONResponse(result)
    except ValueError as e:
        # 验证错误（如 token 验证失败）
        logger.warning(f"Validation error: {e}")
        raise HTTPException(status_code=403, detail="Validation failed")
    except Exception as e:
        # 其他未预期的错误
        logger.error(f"Unexpected error in webhook_handler: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
