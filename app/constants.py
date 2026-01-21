"""
常量定义模块
集中管理所有魔法数字和硬编码字符串
"""

# 系统提示词
SYSTEM_PROMPT_CHAT_ASSISTANT = (
    "你叫托兰，是群聊助手，同时也是群里的一员，说话要有人味。不要自夸/推销/寒暄，说话言简意赅不要啰嗦，不要装腔作势。平铺直叙的输出，而不是markdown格式。"
)

SYSTEM_PROMPT_PROACTIVE = (
    "你叫托兰，是群聊助手，同时也是群里的一员，说话要有人味。不要自夸/推销/寒暄，说话言简意赅不要啰嗦，不要装腔作势。平铺直叙的输出，而不是markdown格式。"
)

SYSTEM_PROMPT_SUMMARY = "你叫托兰，是擅长做会议/群聊总结的助理，同时也是群里的一员，说话要有人味。不要自夸/推销/寒暄，说话言简意赅不要啰嗦，不要装腔作势。"

SYSTEM_PROMPT_WELCOME = "你叫托兰，是友好的群聊助手，擅长写欢迎语，同时也是群里的一员，说话要有人味。不要自夸/推销/寒暄，说话言简意赅不要啰嗦，不要装腔作势。"

# 提示词模板
PROMPT_TEMPLATE_CHAT = "群上下文：\n{context}\n\n用户问题：{question}\n请用简短要点直接回答。"

PROMPT_TEMPLATE_PROACTIVE = (
    "群上下文：\n{context}\n\n有人说：{text}\n"
    "请做出回应，说话像人类、直接、不啰嗦。不要自夸/推销/寒暄。"
)

PROMPT_TEMPLATE_SUMMARY = (
    "请对以下群聊做{period}总结：\n"
    "- 输出：主题Top N、关键结论/决定、待办与负责人。\n"
    "- 语气客观，条理清晰。\n\n"
    "片段：\n{messages}"
)

PROMPT_TEMPLATE_WELCOME = (
    "为新成员写一段20~40字的欢迎语。\n"
    "上下文示例：\n{context}"
)

# 命令帮助文本
HELP_TEXT = """可用命令：
/summary weekly|monthly - 生成群总结
/settings threshold <0~1> - 调整主动发言阈值
/settings mode quiet|normal|active - 调整发言模式
/optout - 个人选择不纳入公开个人总结
"""

# 响应消息
MSG_THINKING = "让我想想……"
MSG_ZIP_REPLY = "🤐"
MSG_THRESHOLD_SET = "已将主动发言阈值设置为 {threshold}"
MSG_THRESHOLD_ERROR = "阈值需为0~1数字，例如 /settings threshold 0.65"
MSG_MODE_SET = "已切换模式为 {mode}"
MSG_SETTINGS_UNKNOWN = "未识别的设置项。"
MSG_OPTOUT_CONFIRMED = "已记录；后续公共总结将不展示你的个人条目。"
MSG_NO_MESSAGES_FOR_SUMMARY = "最近没有足够的消息用于{period}总结。"
MSG_WELCOME_PREFIX = "欢迎 {name} 加入！\n"
MSG_WELCOME_SUFFIX = "\n可使用 /help 查看指令。"

# 主动发言触发关键词
ENGAGE_KEYWORDS = [
    "怎么", "如何", "为啥", "为什么", "怎么办", 
    "谁知道", "有链接吗", "总结", "结论", "进展", "?", "？"
]

# 闭嘴关键词（用户要求机器人不要回复）
ZIP_KEYWORDS = [
    "啥都不用做", "你呆着就好", "别说话", "闭嘴", 
    "安静点", "不用回", "不用回复", "不需要你"
]

# 命令列表
CMD_HELP = "/help"
CMD_SUMMARY = "/summary"
CMD_SETTINGS = "/settings"
CMD_OPTOUT = "/optout"

# 设置项
SETTING_THRESHOLD = "threshold"
SETTING_MODE = "mode"

# 模式
MODE_QUIET = "quiet"
MODE_NORMAL = "normal"
MODE_ACTIVE = "active"
VALID_MODES = [MODE_QUIET, MODE_NORMAL, MODE_ACTIVE]

# 总结周期
PERIOD_WEEKLY = "weekly"
PERIOD_MONTHLY = "monthly"
VALID_PERIODS = [PERIOD_WEEKLY, PERIOD_MONTHLY]

# 事件类型
EVENT_TYPE_MESSAGE = "im.message.receive_v1"
EVENT_TYPE_URL_VERIFICATION = "url_verification"

# 消息类型
MSG_TYPE_TEXT = "text"
MSG_TYPE_IMAGE = "image"
MSG_TYPE_POST = "post"

# 聊天类型
CHAT_TYPE_GROUP = "group"
CHAT_TYPE_P2P = "p2p"

# 发送者类型
SENDER_TYPE_USER = "user"
SENDER_TYPE_APP = "app"
SENDER_TYPE_SYSTEM = "system"

# 时间格式
TIME_FORMAT_MESSAGE = "%m-%d %H:%M"

# LLM 温度参数
TEMPERATURE_CHAT = 0.2
TEMPERATURE_PROACTIVE = 0.3
TEMPERATURE_SUMMARY = 0.3
TEMPERATURE_WELCOME = 0.5

# HTTP 超时
HTTP_TIMEOUT_DEFAULT = 10
HTTP_TIMEOUT_LLM = 60
HTTP_TIMEOUT_IMAGE = 20

# 占位符响应
PLACEHOLDER_RESPONSE = "[占位回复] {prompt}..."
PLACEHOLDER_RESPONSE_MULTIMODAL = "[占位回复-多模态] {prompt}... (images={count})"
LLM_ERROR_PARSE = "[LLM错误] 无法解析响应: {text}"
LLM_ERROR_HTTP = "[LLM错误] {data}"
LLM_ERROR_FORMAT = "[LLM错误] 响应格式异常: {data}"

# 绘图相关
DRAW_KEYWORDS = [
    "画", "绘制", "生成", "生成图片", "生成一张", "画一张", "画个", "画出",
    "帮我画", "给我画", "创作", "设计", "改成", "修改", "变成", "转换",
    "draw", "generate", "generate image", "create image", "make image"
]

DRAW_REFERENCE_KEYWORDS = [
    "参照", "参考", "基于", "根据", "仿照", "模仿", "类似",
    "像这样", "这种风格", "按照", "依据"
]

MSG_DRAWING = "正在绘制中，请稍候..."
MSG_DRAW_SUCCESS = "图片已生成！"
MSG_DRAW_ERROR = "绘图失败: {error}"
MSG_DRAW_NO_CONFIG = "绘图功能未配置，请联系管理员设置 IMAGE_MODEL 相关配置"

# 绘图提示词模板
PROMPT_TEMPLATE_IMAGE_GEN = """根据用户需求生成图片。

用户需求: {prompt}

请生成符合要求的图片。"""

PROMPT_TEMPLATE_IMAGE_TO_IMAGE = """根据参考图片和用户需求生成新图片。

参考图片已提供。
用户需求: {prompt}

请基于参考图片生成符合要求的新图片。"""

# 图片尺寸预设
IMAGE_SIZE_PRESETS = {
    "square": (1024, 1024),
    "landscape": (1024, 768),
    "portrait": (768, 1024),
    "wide": (1024, 576),
    "tall": (576, 1024),
}
