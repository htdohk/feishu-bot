# 技术文档

## 项目概述

本项目是一个基于飞书开放平台的机器人应用，集成了大语言模型（LLM）和多种功能模块。它主要通过飞书API与用户进行交互，并利用LLM实现智能对话。

## 主要特性
- **飞书消息处理**：自动接收并处理来自飞书机器人的消息
- **意图识别**：使用语义意图分析识别用户问题类型
- **AI图像生成**：支持根据文本描述生成图片
- **知识库问答**：集成向量数据库实现智能问答功能
- **网络搜索能力**：可进行网络搜索并整合结果

## 技术架构

### 1. 核心模块

#### app/main.py
主要的主程序入口文件，负责应用的主要流程控制。

#### app/config.py
配置管理模块，用于读取环境变量和设置系统参数。

#### app/feishu_api.py
飞书API封装模块，处理与飞书服务器的通信交互。

#### app/llm.py
LLM模型调用接口，集成大语言模型功能。

#### app/image_gen.py
图片生成模块，基于文本描述生成图像。

#### app/web_search.py
网络搜索模块，支持通过AI工具进行网络信息检索。

#### app/personality.py
个性设置模块，管理机器人的人格特征和响应风格。

#### app/semantic_intent.py
语义意图识别模块，用于分析用户问题的类型并分配相应处理函数。

#### app/db.py
数据库操作模块，使用sqlite3作为存储后端。

#### app/utils.py
工具集模块，包含各种辅助函数。

#### app/message_heat.py
消息热度分析模块，用于分析和处理消息中的热点信息。

#### app/migrations.py
数据库迁移管理模块，处理数据结构的变化和升级。

### 2. 数据库设计

- 使用SQLite3作为本地数据库存储后端
- `db.py`文件负责所有数据库相关的操作
- 通过`app.db`的函数来实现对消息记录、用户信息等的操作

### 3. 飞书集成

- 项目使用飞书开放平台API与飞书进行通信
- 消息处理和响应都基于飞书机器人接口规范
- 自动处理认证回调以完成飞书应用授权

### 4. LLM服务

- 支持多种大语言模型的调用
- 集成模型配置并支持模型选择及参数调整
- 使用`app/llm.py`模块与LLM进行交互通信

## 开发环境要求

- Python 3.8+
- 必须安装依赖库 (requirements.txt)
- 飞书开发者账号和应用凭证（APP_ID、APP_SECRET）

## 环境配置

### .env.example 文件

项目使用.env文件来管理敏感的配置信息，例如飞书API密钥等。用户需要创建一个.env文件并填入相应的配置值。

```bash
# 飞书应用配置
LARK_APP_ID=your_app_id_here
LARK_APP_SECRET=your_app_secret_here
LARK_APP_VERIFICATION_TOKEN=your_verification_token_here

# LLM 模型配置 (如果使用本地模型)
LLM_MODEL_PATH=/path/to/llm/model

# 数据库配置
DATABASE_URL=sqlite:///app.db
```

### 配置说明

- `LARK_APP_ID`：飞书应用ID
- `LARK_APP_SECRET`：飞书应用密钥
- `LARK_APP_VERIFICATION_TOKEN`：飞书验证令牌用于API回调认证
- `LLM_MODEL_PATH`：本地大语言模型的路径，若不使用本地模型则可省略此配置

## 项目目录结构

```
.
├── .env.example              # 环境变量示例文件
├── .gitignore                # Git忽略规则
├── Dockerfile                # 容器化Docker构建文件
├── docker-compose.yml        # Docker Compose定义
├── LICENSE                   # 许可协议文件
├── README.md                 # 项目说明文档
├── requirements.txt          # Python依赖包列表
├── app/                      # 主要应用代码目录
│   ├── config.py             # 配置读取模块
│   ├── constants.py          # 常量定义模块
│   ├── db.py                 # 数据库操作模块
│   ├── feishu_api.py         # 飞书API封装
│   ├── image_gen.py          # 图像生成模块
│   ├── llm.py                # LLM模型调用接口
│   ├── main.py               # 主程序入口
│   ├── message_heat.py       # 消息热度分析模块
│   ├── migrations.py         # 数据库迁移管理
│   ├── personality.py        # 个性设置模块
│   ├── semantic_intent.py    # 意图识别模块
│   ├── utils.py              # 工具集模块
│   └── web_search.py         # 网络搜索模块
└── scripts/                  # 脚本目录
    ├── cron_redeploy.sh      # 定时重部署脚本
    └── README-cron.md        # Cron任务说明文档
```

## 部署与运行

### 本地开发环境设置步骤：
1. 克隆仓库并安装依赖:
   ```bash
   git clone https://github.com/htdohk/feishu-bot.git && cd feishu-bot
   pip install -r requirements.txt
   ```

2. 创建 `.env` 文件:
   - 复制示例配置文件: `cp .env.example .env`
   - 填入实际的飞书应用信息 (APP_ID, APP_SECRET等)

3. 启动服务:
   ```bash
   python app/main.py
   ```

### Docker部署方式：
1. 构建Docker镜像:
   ```bash
   docker build -t feishu-bot .
   ```

2. 运行容器:
   ```bash
   docker run --env-file .env feishu-bot
