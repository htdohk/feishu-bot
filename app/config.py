"""
配置管理模块
统一管理所有环境变量和配置项
"""
import logging
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """应用配置类 - 使用 Pydantic Settings 进行配置管理和验证"""

    # Pydantic Settings 配置
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=True,
        extra='ignore'
    )

    # 飞书配置
    FEISHU_APP_ID: str = Field(default="", description="飞书应用 ID")
    FEISHU_APP_SECRET: str = Field(default="", description="飞书应用密钥")
    FEISHU_VERIFICATION_TOKEN: str = Field(default="", description="飞书验证令牌")
    FEISHU_ENCRYPT_KEY: str = Field(default="", description="飞书加密密钥")
    FEISHU_API_BASE: str = Field(default="https://open.feishu.cn/open-apis", description="飞书 API 基础 URL")

    # 机器人配置
    BOT_NAME: str = Field(default="群助手", description="机器人名称")

    # 数据库配置
    DATABASE_URL: str = Field(default="", description="数据库连接 URL")

    # LLM 配置
    LLM_BASE_URL: str = Field(default="", description="LLM API 基础 URL")
    LLM_API_KEY: str = Field(default="", description="LLM API 密钥")
    LLM_MODEL: str = Field(default="gpt-4o-mini", description="LLM 模型名称")
    LLM_TIMEOUT: int = Field(default=60, ge=10, le=300, description="LLM 请求超时（秒）")

    # 小模型配置（用于快速意图分类）
    SMALL_MODEL_BASE_URL: str = Field(default="", description="小模型 API 基础 URL")
    SMALL_MODEL_API_KEY: str = Field(default="", description="小模型 API 密钥")
    SMALL_MODEL: str = Field(default="", description="小模型名称")
    SMALL_MODEL_TIMEOUT: int = Field(default=30, ge=5, le=120, description="小模型请求超时（秒）")

    # 绘图模型配置
    IMAGE_MODEL_BASE_URL: str = Field(default="", description="图像模型 API 基础 URL")
    IMAGE_MODEL_API_KEY: str = Field(default="", description="图像模型 API 密钥")
    IMAGE_MODEL: str = Field(default="gemini-3-pro-image-preview", description="图像模型名称")
    IMAGE_MAX_SIZE: int = Field(default=1024, ge=256, le=4096, description="图片最大尺寸")
    IMAGE_TIMEOUT: int = Field(default=120, ge=30, le=600, description="图像生成超时（秒）")

    # 日志配置
    LOG_LEVEL: str = Field(default="INFO", description="日志级别")

    # 业务配置
    CONVERSATION_TTL_SECONDS: int = Field(default=600, ge=60, le=7200, description="对话窗口有效期（秒）")
    ENGAGE_DEFAULT_THRESHOLD: float = Field(default=0.65, ge=0.0, le=1.0, description="主动发言默认阈值")
    THINKING_MESSAGE_DELAY: float = Field(default=5.0, ge=1.0, le=30.0, description="思考提示延迟（秒）")

    # 内存限制
    CHAT_LOGS_MAXLEN: int = Field(default=2000, ge=100, le=10000, description="聊天日志最大长度")
    RECENT_EVENTS_MAXLEN: int = Field(default=5000, ge=100, le=20000, description="最近事件最大长度")

    # 消息处理配置
    MAX_CONTEXT_MESSAGES: int = Field(default=20, ge=5, le=100, description="最大上下文消息数")
    MAX_SUMMARY_MESSAGES: int = Field(default=400, ge=50, le=1000, description="最大总结消息数")
    MAX_IMAGES_PER_MESSAGE: int = Field(default=4, ge=1, le=10, description="每条消息最大图片数")

    # 联网搜索配置
    SEARXNG_URL: str = Field(default="", description="SearXNG 搜索引擎 URL")
    SEARXNG_TIMEOUT: int = Field(default=10, ge=5, le=60, description="搜索超时（秒）")

    @field_validator('LOG_LEVEL')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """验证日志级别"""
        valid_levels = ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f'LOG_LEVEL must be one of {valid_levels}')
        return v_upper

    def validate_required(self) -> list[str]:
        """
        验证必需的配置项
        返回缺失的配置项列表
        """
        missing = []

        # 检查必需的飞书配置
        if not self.FEISHU_APP_ID:
            missing.append("FEISHU_APP_ID")
        if not self.FEISHU_APP_SECRET:
            missing.append("FEISHU_APP_SECRET")
        if not self.FEISHU_VERIFICATION_TOKEN:
            missing.append("FEISHU_VERIFICATION_TOKEN")

        # LLM 配置是可选的（可以降级运行）
        # DATABASE_URL 也是可选的（可以使用内存模式）

        return missing

    def is_valid(self) -> bool:
        """检查配置是否有效"""
        return len(self.validate_required()) == 0

    def get_log_level_int(self) -> int:
        """获取日志级别的整数值"""
        level_map = {
            "CRITICAL": logging.CRITICAL,
            "ERROR": logging.ERROR,
            "WARNING": logging.WARNING,
            "INFO": logging.INFO,
            "DEBUG": logging.DEBUG,
        }
        return level_map.get(self.LOG_LEVEL, logging.INFO)


# 创建全局配置实例
config = Config()
