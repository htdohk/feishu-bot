# 开发指南

## 环境准备

### 依赖安装
```bash
# 安装Python依赖包
pip install -r requirements.txt

# 或者使用pipenv (如果项目支持)
pipenv install
```

### 飞书应用配置
1. 访问飞书开放平台开发者后台
2. 创建新的应用并获取APP_ID和APP_SECRET
3. 在飞书机器人设置中启用相关事件订阅
4. 获取Verification Token用于API回调认证

## 项目结构说明

### 核心模块详解

#### app/main.py
这是程序的入口文件，负责初始化整个系统：
- 加载环境变量配置
- 初始化数据库连接
- 启动飞书消息监听服务
- 注册事件处理回调函数

```python
# 主要功能示例
app = FastAPI()
# 应用启动时初始化各模块
# 监听飞书机器人事件
```

#### app/config.py
配置管理模块负责读取和解析环境变量：
- 从.env文件中读取飞书应用信息
- 设置默认参数值
- 提供统一的配置访问接口

```python
# 配置示例
LARK_APP_ID = os.getenv('LARK_APP_ID', 'default_app_id')
LARK_APP_SECRET = os.getenv('LARK_APP_SECRET', 'default_secret')
```

#### app/feishu_api.py
飞书API封装模块：
- 封装与飞书服务器的HTTP通信
- 实现消息发送和接收处理逻辑
- 处理认证回调以完成应用授权

#### app/llm.py
LLM模型调用接口：
- 集成多种大语言模型（如OpenAI、本地模型）
- 提供统一的prompt处理和响应生成方法
- 支持模型参数配置和切换

#### app/image_gen.py
图像生成模块：
- 实现基于文本描述的图片生成功能
- 配置图像生成API调用细节
- 处理图像生成结果并返回给用户

#### app/web_search.py
网络搜索模块：
- 封装网页搜索功能（如Google、Bing）
- 通过AI工具实现信息检索和整合
- 提供可配置的搜索引擎接口

### 数据库设计

数据库使用SQLite3，主要包含以下表结构：
```sql
# 消息记录表
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    message_type TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

# 用户信息表
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 部署配置

#### Docker部署说明
Dockerfile和docker-compose.yml文件用于容器化部署：
- 容器镜像基于Python 3.8-alpine
- 自动复制环境变量并安装依赖
- 启动命令为：`python app/main.py`

```yaml
# docker-compose.yml 示例配置
version: '3'
services:
  feishu-bot:
    build: .
    env_file:
      - .env
    ports:
      - "8000:8000"
```

#### 环境变量设置

.env文件中需要包含以下关键配置：
```bash
# 飞书应用信息
LARK_APP_ID=your_app_id_here
LARK_APP_SECRET=your_app_secret_here
LARK_APP_VERIFICATION_TOKEN=your_verification_token_here

# LLM模型配置（如使用本地模型）
LLM_MODEL_PATH=/path/to/llm/model

# 数据库路径
DATABASE_URL=sqlite:///app.db
```

## 开发流程

### 1. 功能开发规范

所有功能模块应遵循以下开发原则：
- 模块化设计，便于维护和扩展
- 统一的错误处理机制
- 明确的输入输出接口定义
- 完善的日志记录和调试信息

### 2. 添加新功能模块

#### 步骤1：创建模块文件
```bash
# 创建新的模块文件
touch app/new_feature.py
```

#### 步骤2：添加模块到main.py注册中
在app/main.py中适当位置添加导入：
```python
from app.new_feature import NewFeatureHandler  # 导入新功能处理器

# 在初始化函数中注册新功能
def register_handlers():
    # ... 其他handler的注册
    app.add_event_handler("new_feature", NewFeatureHandler())
```

#### 步骤3：实现处理逻辑
在模块文件中实现具体的业务逻辑和事件响应。

### 3. 调试与测试

使用以下命令运行调试模式：
```bash
# 启动开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 或者直接运行Python脚本（需要确保环境变量已设置）
python app/main.py
```

## 编码规范

### 命名约定
- Python文件使用snake_case命名格式
- 类名使用PascalCase格式
- 函数和变量使用snake_case格式
- 常量使用UPPER_CASE格式

### 代码风格要求
- 遵循PEP8编码规范
- 所有函数需添加docstring说明
- 使用类型注解提升可读性
- 合理的模块内聚，避免功能耦合过紧

## 开发工具推荐

### IDE配置建议
- 推荐使用Visual Studio Code
- 安装Python扩展包以获得更好的支持
- 配置代码格式化工具如black和flake8

### 依赖管理
```bash
# 使用pipenv进行依赖管理（如果可用）
pipenv install --dev

# 或者使用requirements.txt直接安装
pip install -r requirements.txt
```

## 测试指南

### 单元测试方法
- 所有模块应包含单元测试用例
- 重点关注关键业务逻辑的覆盖度
- 使用pytest框架进行测试管理

### 系统集成测试
- 需要对飞书API通信部分进行模拟测试
- 数据库操作需进行数据一致性验证
- LLM调用需要检查输入输出的一致性

## 性能优化建议

### 缓存机制
- 对于重复查询结果使用内存缓存
- 图片生成等耗时操作可添加异步处理
- 飞书API响应的缓存策略设计

### 错误处理与日志记录
- 添加完善的异常捕获和错误恢复机制
- 使用logging模块记录关键信息以便调试
- 对于重要操作增加重试机制以确保可靠性

## 项目维护

### 数据库迁移管理
当需要修改数据库结构时：
1. 在`app/migrations.py`中创建新的迁移脚本
2. 根据数据表变化调整相应的迁移逻辑
3. 使用`alembic`或手动方式完成数据迁移升级

### 版本更新策略
- 遵循语义化版本控制规范（SemVer）
- 所有代码变更需记录在CHANGELOG.md中
- 更新requirements.txt中的依赖版本以确保兼容性

## 常见问题处理

### 1. 环境变量配置错误
检查.env文件是否包含所有必要字段，确认是否存在拼写错误。

### 2. 飞书API调用失败
验证APP_ID和APP_SECRET是否正确设置，确认飞书应用权限配置完整。

### 3. 数据库连接异常
检查数据库路径配置，确保数据库文件存在且具有正确的访问权限。

### 4. LLM模型加载失败
确认模型路径是否正确，并确保所依赖的模型文件已下载并解压到指定位置。
