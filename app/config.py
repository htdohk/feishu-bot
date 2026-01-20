"""
配置管理模块
统一管理所有环境变量和配置项
"""
import os
from typing import Optional


class Config:
    """应用配置类"""
    
    # 飞书配置
    FEISHU_APP_ID: str = os.getenv("FEISHU_APP_ID", "")
    FEISHU_APP_SECRET: str = os.getenv("FEISHU_APP_SECRET", "")
    FEISHU_VERIFICATION_TOKEN: str = os.getenv("FEISHU_VERIFICATION_TOKEN", "")
    FEISHU_ENCRYPT_KEY: str = os.getenv("FEISHU_ENCRYPT_KEY", "")
    FEISHU_API_BASE: str = "https://open.feishu.cn/open-apis"
    
    # 机器人配置
    BOT_NAME: str = os.getenv("BOT_NAME", "群助手")
    BOT_USER_ID: str = os.getenv("BOT_USER_ID", "")
    
    # 数据库配置
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    
    # LLM 配置
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "60"))
    
    # 绘图模型配置
    IMAGE_MODEL_BASE_URL: str = os.getenv("IMAGE_MODEL_BASE_URL", "")
    IMAGE_MODEL_API_KEY: str = os.getenv("IMAGE_MODEL_API_KEY", "")
    IMAGE_MODEL: str = os.getenv("IMAGE_MODEL", "gemini-3-pro-image-preview")
    IMAGE_MAX_SIZE: int = int(os.getenv("IMAGE_MAX_SIZE", "1024"))
    IMAGE_TIMEOUT: int = int(os.getenv("IMAGE_TIMEOUT", "120"))
    
    # 日志配置
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # 业务配置
    CONVERSATION_TTL_SECONDS: int = int(os.getenv("CONVERSATION_TTL_SECONDS", "600"))
    ENGAGE_DEFAULT_THRESHOLD: float = 0.65
    THINKING_MESSAGE_DELAY: float = 5.0
    
    # 内存限制
    CHAT_LOGS_MAXLEN: int = 2000
    RECENT_EVENTS_MAXLEN: int = 5000
    
    # 消息处理配置
    MAX_CONTEXT_MESSAGES: int = 20
    MAX_SUMMARY_MESSAGES: int = 400
    MAX_IMAGES_PER_MESSAGE: int = 4
    
    # 联网搜索配置
    SEARXNG_URL: str = os.getenv("SEARXNG_URL", "")
    SEARXNG_TIMEOUT: int = int(os.getenv("SEARXNG_TIMEOUT", "10"))
    
    @classmethod
    def validate(cls) -> list[str]:
        """
        验证必需的配置项
        返回缺失的配置项列表
        """
        missing = []
        
        # 检查必需的飞书配置
        if not cls.FEISHU_APP_ID:
            missing.append("FEISHU_APP_ID")
        if not cls.FEISHU_APP_SECRET:
            missing.append("FEISHU_APP_SECRET")
        if not cls.FEISHU_VERIFICATION_TOKEN:
            missing.append("FEISHU_VERIFICATION_TOKEN")
        
        # LLM 配置是可选的（可以降级运行）
        # DATABASE_URL 也是可选的（可以使用内存模式）
        
        return missing
    
    @classmethod
    def is_valid(cls) -> bool:
        """检查配置是否有效"""
        return len(cls.validate()) == 0
    
    @classmethod
    def get_log_level_int(cls) -> int:
        """获取日志级别的整数值"""
        import logging
        level_map = {
            "CRITICAL": logging.CRITICAL,
            "ERROR": logging.ERROR,
            "WARNING": logging.WARNING,
            "INFO": logging.INFO,
            "DEBUG": logging.DEBUG,
        }
        return level_map.get(cls.LOG_LEVEL, logging.INFO)


# 创建全局配置实例
config = Config()
