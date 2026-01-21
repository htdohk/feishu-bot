# 飞书智能群聊机器人 🤖

一个基于 FastAPI 和 LLM 的智能飞书群聊助手，支持多模态消息处理、智能回复、定时总结等功能。

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## ✨ 核心特性

### 🎯 智能对话
- **@机器人回复**: 在群聊中@机器人即可获得智能回复
- **对话粘性**: 一次@后，在一段时间内无需再@即可继续对话
- **多模态支持**: 支持文字+图片的混合消息处理
- **上下文理解**: 自动获取群聊历史上下文，提供更准确的回复

### 🚀 主动参与
- **智能插话**: 根据关键词和问题特征主动参与讨论
- **可调节阈值**: 支持调整机器人的主动发言频率
- **三种模式**: quiet（安静）、normal（正常）、active（活跃）

### 📊 定时总结
- **周报**: 每周一自动生成群聊周报
- **月报**: 每月1日自动生成群聊月报
- **手动触发**: 支持通过命令随时生成总结

### 🎨 人性化交互
- **思考提示**: 处理图片等耗时操作时会说"让我想想……"
- **智能闭嘴**: 识别"别说话"等指令，适时保持安静
- **新人欢迎**: 自动欢迎新成员并介绍群聊主题

## 🏗️ 技术架构

```
飞书机器人
├── FastAPI          # Web 框架
├── SQLAlchemy       # ORM 框架
├── PostgreSQL       # 数据库
├── LLM API          # 大语言模型（支持 OpenAI 兼容接口）
└── Docker           # 容器化部署
```

### 项目结构

```
feishu-bot/
├── app/
│   ├── main.py           # 主应用入口和业务逻辑
│   ├── config.py         # 配置管理
│   ├── constants.py      # 常量定义
│   ├── db.py             # 数据库模型和操作
│   ├── feishu_api.py     # 飞书 API 封装
│   ├── llm.py            # LLM 调用封装
│   └── utils.py          # 工具函数
├── scripts/
│   ├── cron_redeploy.sh  # 定时重启脚本
│   └── README-cron.md    # 定时任务说明
├── .env.example          # 环境变量示例
├── docker-compose.yml    # Docker Compose 配置
├── Dockerfile            # Docker 镜像配置
├── requirements.txt      # Python 依赖
└── README.md             # 项目说明
```

## 🚀 快速开始

### 前置要求

- Python 3.11+
- PostgreSQL 数据库
- 飞书开放平台应用
- LLM API（支持 OpenAI 兼容接口）

### 1. 创建飞书应用

1. 访问 [飞书开放平台](https://open.feishu.cn/)
2. 创建企业自建应用
3. 获取以下信息：
   - App ID
   - App Secret
   - Verification Token
4. 配置应用权限：
   - `im:message` - 获取与发送单聊、群组消息
   - `im:message:readonly` - 读取消息
   - `im:chat` - 获取群组信息
5. 配置事件订阅：
   - 订阅 `im.message.receive_v1` 事件
   - 设置请求地址：`https://your-domain.com/feishu/events`

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入实际配置：

```bash
# 飞书应用配置
FEISHU_APP_ID=your_app_id
FEISHU_APP_SECRET=your_app_secret
FEISHU_VERIFICATION_TOKEN=your_verification_token
FEISHU_ENCRYPT_KEY=

# 机器人配置
BOT_NAME=AI助手
BOT_USER_ID=your_bot_user_id

# 数据库配置
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname

# LLM 配置
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=your_api_key
LLM_MODEL=gpt-4o-mini

# 其他配置
TZ=Asia/Shanghai
LOG_LEVEL=INFO
CONVERSATION_TTL_SECONDS=600
```

### 3. 使用 Docker 部署（推荐）

```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 4. 本地开发部署

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. 配置飞书回调地址

将飞书应用的事件订阅地址设置为：
```
https://your-domain.com/feishu/events
```

## 📖 使用指南

### 基本命令

在群聊中发送以下命令：

```
/help                          # 查看帮助信息
/summary weekly                # 生成周报
/summary monthly               # 生成月报
/settings threshold 0.7        # 设置主动发言阈值（0-1）
/settings mode quiet           # 设置为安静模式
/settings mode normal          # 设置为正常模式
/settings mode active          # 设置为活跃模式
/optout                        # 退出个人总结统计
```

### 使用场景

#### 场景1：技术讨论
```
用户A: @AI助手 这个 bug 怎么解决？
机器人: 1. 检查日志文件
       2. 确认配置是否正确
       3. 尝试重启服务
       
用户B: 重启后还是不行
机器人: 可以尝试：
       1. 清除缓存
       2. 检查数据库连接
```

#### 场景2：图片分析
```
用户: @AI助手 [上传截图] 这个界面有什么问题？
机器人: 让我想想……
       根据截图分析：
       1. 按钮对齐有问题
       2. 颜色对比度不够
       3. 建议调整布局
```

#### 场景3：主动参与
```
用户A: 有人知道怎么部署吗？
机器人: 可以参考以下步骤：
       1. 准备 Docker 环境
       2. 配置环境变量
       3. 运行 docker-compose up
```

## ⚙️ 配置说明

### 主动发言阈值

阈值范围：0.0 - 1.0
- **0.0-0.3**: 几乎不主动发言
- **0.4-0.6**: 适度参与（推荐）
- **0.7-1.0**: 积极参与

### 发言模式

- **quiet**: 只在被@时回复，不主动发言
- **normal**: 正常模式，根据阈值决定是否主动发言
- **active**: 活跃模式，更容易被触发

### 对话粘性

默认600秒（10分钟）。在此时间内，用户无需再次@机器人即可继续对话。

## 🔧 高级配置

### 自定义提示词

编辑 `app/constants.py` 中的系统提示词：

```python
SYSTEM_PROMPT_CHAT_ASSISTANT = (
    "你是群聊助手，说话像人类、直接、不啰嗦。"
    # 自定义你的提示词...
)
```

### 调整消息上下文

在 `app/config.py` 中修改：

```python
MAX_CONTEXT_MESSAGES = 20      # 每次获取的上下文消息数
MAX_SUMMARY_MESSAGES = 400     # 总结时获取的消息数
MAX_IMAGES_PER_MESSAGE = 4     # 每条消息最多处理的图片数
```

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件


## ⚠️ 免责声明

本项目仅供学习和研究使用。使用本项目时，请遵守相关法律法规和飞书开放平台的使用条款。对于使用本项目造成的任何直接或间接损失，开发者不承担任何责任。

---

**如果这个项目对你有帮助，请给个 ⭐️ Star 支持一下！**
