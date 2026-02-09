"""
连接器模块 - 支持多种连接方式（Webhook、WebSocket）
替代 webhook.py，提供统一的事件接收、验证和路由接口
"""
import os
import json
import logging
from typing import Callable, Any
from collections import deque
from fastapi.responses import JSONResponse

logger = logging.getLogger("feishu_bot.connector")


class BaseConnector:
    """基础连接器类"""
    
    def verify_token(self, body: dict) -> bool:
        """验证请求 token"""
        verification_token = os.getenv("FEISHU_VERIFICATION_TOKEN", "")
        header = body.get("header", {})
        ok = (header.get("token") == verification_token) or (
            body.get("token") == verification_token
        )
        if not ok:
            logger.warning(
                "verify_token failed header=%s body_token=%s",
                header.get("token"),
                body.get("token"),
            )
        return ok
    
    def verify_url_challenge(self, body: dict) -> str:
        """验证 URL Challenge（仅 Webhook 需要）"""
        if body.get("type") == "url_verification" and "challenge" in body:
            logger.debug("verify_url_challenge hit")
            return body["challenge"]
        return None
    
    def parse_event(self, body: dict) -> tuple:
        """解析事件类型和事件数据"""
        if "header" in body and "event" in body:
            return body["header"].get("event_type", ""), body["event"]
        return body.get("type", ""), body.get("event", {})


class WebhookConnector(BaseConnector):
    """Webhook 连接器实现"""
    
    def __init__(self):
        # 事件去重：保存最近处理过的 event_id
        self.recent_event_ids: deque = deque(maxlen=5000)
        self.recent_event_set: set = set()
    
    def is_event_processed(self, event_id: str) -> bool:
        """
        检查事件是否已处理过
        返回 True 表示该 event_id 已处理，本次应直接忽略
        """
        if not event_id:
            return False
        if event_id in self.recent_event_set:
            logger.debug(f"skip duplicated event_id={event_id}")
            return True
        self.recent_event_ids.append(event_id)
        self.recent_event_set.add(event_id)
        # 当 deque 发生淘汰时，重建 set，避免无限增长
        if len(self.recent_event_ids) >= self.recent_event_ids.maxlen:
            logger.debug("recent_event_ids reached maxlen, rebuilding recent_event_set")
            self.recent_event_set.clear()
            self.recent_event_set.update(self.recent_event_ids)
        logger.debug(f"mark event_id={event_id} as processed")
        return False
    
    async def webhook_handler(
        self,
        body: dict,
        handle_message_fn: Callable,
        handle_event_fn: Callable
    ) -> dict:
        """
        处理 Webhook 请求的核心逻辑
        
        Args:
            body: 飞书服务器推送的请求体
            handle_message_fn: 消息处理函数
            handle_event_fn: 事件处理函数（非消息事件）
            
        Returns:
            JSON 响应
        """
        logger.debug(
            f"webhook_handler raw_body={json.dumps(body, ensure_ascii=False)[:500]}"
        )
        
        # 处理 URL Challenge 验证
        ch = self.verify_url_challenge(body)
        if ch:
            logger.info("received url_verification challenge")
            return {"challenge": ch}
        
        # 验证请求合法性
        if not self.verify_token(body):
            logger.warning("verify_token failed")
            raise Exception("Invalid token")
        
        # 解析事件类型和数据
        event_type, event = self.parse_event(body)
        event_id = (
            body.get("header", {}).get("event_id") or
            body.get("event_id") or
            ""
        )
        
        logger.debug(f"parsed event_type={event_type} event_id={event_id}")
        
        # 事件去重
        if self.is_event_processed(event_id):
            return {"code": 0}
        
        # 消息事件处理
        if event_type == "im.message.receive_v1":
            await handle_message_fn(event, event_id)
            return {"code": 0}
        
        # 新成员加入事件处理
        if event_type.startswith("im.chat.member") and (
            "add" in event_type or "user_added" in event_type
        ):
            chat_id = (
                event.get("chat_id") or
                event.get("chat", {}).get("chat_id") or
                ""
            )
            members = event.get("users") or event.get("members") or []
            if chat_id and members:
                name = members[0].get("name") or "新同学"
                logger.info(
                    f"new member event chat_id={chat_id} name={name} "
                    f"members_count={len(members)}"
                )
                # 路由到事件处理函数
                await handle_event_fn(
                    event_type="new_member",
                    chat_id=chat_id,
                    new_user_name=name
                )
            return {"code": 0}
        
        return {"code": 0}


class WebSocketConnector(BaseConnector):
    """
    WebSocket 连接器实现（未来扩展）
    """
    
    async def websocket_handler(
        self,
        websocket: Any,
        handle_message_fn: Callable,
        handle_event_fn: Callable
    ):
        """处理 WebSocket 连接"""
        # TODO: 实现 WebSocket 连接逻辑
        logger.info("WebSocket connector not yet implemented")
        pass


def create_connector(
    mode: str = "webhook",
    handle_message_fn: Callable = None,
    handle_event_fn: Callable = None
):
    """
    工厂函数，根据 env 配置选择连接方式
    
    Args:
        mode: 连接方式（webhook 或 websocket）
        handle_message_fn: 消息处理函数
        handle_event_fn: 事件处理函数
        
    Returns:
        连接器实例或处理函数
    """
    mode = os.getenv("FEISHU_CONNECTION_MODE", mode).lower()
    
    if mode == "websocket":
        logger.info("Using WebSocket connector")
        connector = WebSocketConnector()
        return connector.websocket_handler
    else:
        logger.info("Using Webhook connector (default)")
        connector = WebhookConnector()
        
        async def webhook_handler_wrapper(body: dict) -> dict:
            return await connector.webhook_handler(body, handle_message_fn, handle_event_fn)
        
        return webhook_handler_wrapper
