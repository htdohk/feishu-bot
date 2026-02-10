"""
飞书 AI 聊天机器人
集成大语言模型（LLM）和多种功能模块的智能对话机器人
"""

__version__ = "1.0.0"
__author__ = "feishu-bot team"

# 导出主要组件
from .main import app
from .config import config

__all__ = ["app", "config"]
