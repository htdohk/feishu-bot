# 定时部署脚本说明

## 概述

`cron_redeploy.sh` 是一个智能化的 Docker 部署脚本，支持：
- ✅ 自动检测依赖变化
- ✅ 智能决定是否忽略缓存
- ✅ 自动清理旧镜像
- ✅ 完整的日志记录
- ✅ 支持手动和定时执行

## 🚀 核心特性

### 1. 智能缓存检测

脚本会自动检测以下文件的变化：
- `requirements.txt` - Python 依赖
- `Dockerfile` - Docker 构建配置

**检测逻辑**：
- 如果依赖或 Dockerfile 发生变化 → 使用 `--no-cache` 重新构建
- 如果没有变化 → 使用缓存快速构建
- 如果镜像不存在 → 从头构建

### 2. 自动清理

- 保留最近 3 个镜像版本
- 自动删除旧版本，节省磁盘空间

### 3. 完整日志

所有操作都会记录到日志文件：
- 默认位置：`/var/log/feishu-bot/cron_redeploy.log`
- 包含时间戳、操作详情、错误信息

## 📋 使用方法

### 手动执行

```bash
# 基本用法
bash scripts/cron_redeploy.sh

# 自定义项目路径
PROJECT_DIR=/path/to/project bash scripts/cron_redeploy.sh

# 自定义日志目录
LOG_DIR=/custom/log/path bash scripts/cron_redeploy.sh
```

### 定时执行（推荐）

#### 1. 添加到 crontab

```bash
# 编辑 crontab
crontab -e

# 添加以下行（每天凌晨 3 点执行）
0 3 * * * PROJECT_DIR=/opt/feishu-bot /opt/feishu-bot/scripts/cron_redeploy.sh

# 或者每周一凌晨 3 点执行
0 3 * * 1 PROJECT_DIR=/opt/feishu-bot /opt/feishu-bot/scripts/cron_redeploy.sh
```

#### 2. 使用 systemd timer（推荐）

创建 service 文件：`/etc/systemd/system/feishu-bot-redeploy.service`

```ini
[Unit]
Description=Feishu Bot Redeploy Service
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
Environment="PROJECT_DIR=/opt/feishu-bot"
Environment="LOG_DIR=/var/log/feishu-bot"
ExecStart=/opt/feishu-bot/scripts/cron_redeploy.sh
User=root
StandardOutput=journal
StandardError=journal
```

创建 timer 文件：`/etc/systemd/system/feishu-bot-redeploy.timer`

```ini
[Unit]
Description=Feishu Bot Redeploy Timer
Requires=feishu-bot-redeploy.service

[Timer]
# 每天凌晨 3 点执行
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

启用 timer：

```bash
# 重载 systemd
sudo systemctl daemon-reload

# 启用并启动 timer
sudo systemctl enable feishu-bot-redeploy.timer
sudo systemctl start feishu-bot-redeploy.timer

# 查看 timer 状态
sudo systemctl status feishu-bot-redeploy.timer

# 查看下次执行时间
sudo systemctl list-timers feishu-bot-redeploy.timer
```

## ⚙️ 环境变量配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PROJECT_DIR` | `/opt/feishu-bot` | 项目根目录 |
| `COMPOSE_FILE` | `docker-compose.yml` | Docker Compose 配置文件 |
| `SERVICE_NAME` | `feishu-bot` | 服务名称 |
| `LOG_DIR` | `/var/log/feishu-bot` | 日志目录 |
| `LOG_FILE` | `${LOG_DIR}/cron_redeploy.log` | 日志文件路径 |

## 📊 日志示例

```
[2026-01-20 03:00:01] === cron_redeploy start ===
[2026-01-20 03:00:01] PROJECT_DIR=/opt/feishu-bot SERVICE_NAME=feishu-bot COMPOSE_FILE=docker-compose.yml
[2026-01-20 03:00:01] Compose cmd: docker compose
[2026-01-20 03:00:02] Dependencies changed (requirements.txt)
[2026-01-20 03:00:02]   Previous: a1b2c3d4e5f6
[2026-01-20 03:00:02]   Current:  f6e5d4c3b2a1
[2026-01-20 03:00:02] Building image with --no-cache (dependencies or Dockerfile changed)...
[2026-01-20 03:05:30] Cache updated
[2026-01-20 03:05:31] Restart service...
[2026-01-20 03:05:35] Container status:
NAMES           STATUS                  PORTS
feishu-bot      Up 4 seconds           0.0.0.0:18080->8000/tcp
[2026-01-20 03:05:36] Cleaning up old images...
[2026-01-20 03:05:37] === cron_redeploy done ===
```

## 🔍 工作原理

### 缓存检测流程

```
┌─────────────────────────────────────┐
│  开始部署                            │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  计算 requirements.txt MD5          │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  与缓存的 MD5 比较                   │
└──────────────┬──────────────────────┘
               │
       ┌───────┴───────┐
       │               │
    变化了          没变化
       │               │
       ▼               ▼
┌──────────┐    ┌──────────┐
│ 计算      │    │ 计算      │
│Dockerfile │    │Dockerfile │
│ MD5      │    │ MD5      │
└─────┬────┘    └─────┬────┘
      │               │
      ▼               ▼
┌──────────┐    ┌──────────┐
│ 比较      │    │ 比较      │
│ MD5      │    │ MD5      │
└─────┬────┘    └─────┬────┘
      │               │
  ┌───┴───┐       ┌───┴───┐
  │       │       │       │
变化了  没变化  变化了  没变化
  │       │       │       │
  ▼       │       ▼       │
┌─────────┴───────────────┴─────┐
│ 使用 --no-cache 构建           │
└────────────┬───────────────────┘
             │
             ▼
      ┌──────────────┐
      │ 更新缓存文件  │
      └──────┬───────┘
             │
             ▼
      ┌──────────────┐
      │ 重启服务      │
      └──────┬───────┘
             │
             ▼
      ┌──────────────┐
      │ 清理旧镜像    │
      └──────────────┘
```

## 🛠️ 故障排查

### 问题1：脚本执行失败

**检查**：
```bash
# 查看日志
tail -f /var/log/feishu-bot/cron_redeploy.log

# 检查脚本权限
ls -l scripts/cron_redeploy.sh

# 添加执行权限
chmod +x scripts/cron_redeploy.sh
```

### 问题2：缓存检测不工作

**检查**：
```bash
# 查看缓存文件
ls -la /var/log/feishu-bot/.cache/

# 手动删除缓存（强制重新构建）
rm -rf /var/log/feishu-bot/.cache/
```

### 问题3：定时任务不执行

**crontab 检查**：
```bash
# 查看 cron 日志
sudo tail -f /var/log/cron

# 确认 crontab 配置
crontab -l
```

**systemd timer 检查**：
```bash
# 查看 timer 状态
sudo systemctl status feishu-bot-redeploy.timer

# 查看服务日志
sudo journalctl -u feishu-bot-redeploy.service -f

# 手动触发一次
sudo systemctl start feishu-bot-redeploy.service
```

## 💡 最佳实践

### 1. 定时执行建议

- **开发环境**：不建议使用定时任务
- **测试环境**：每天一次（凌晨执行）
- **生产环境**：每周一次或按需手动执行

### 2. 日志管理

```bash
# 定期清理旧日志（保留最近 30 天）
find /var/log/feishu-bot -name "*.log" -mtime +30 -delete

# 或使用 logrotate
cat > /etc/logrotate.d/feishu-bot << 'EOF'
/var/log/feishu-bot/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
}
EOF
```

### 3. 监控告警

```bash
# 检查最近一次部署是否成功
if tail -1 /var/log/feishu-bot/cron_redeploy.log | grep -q "done"; then
    echo "Last deployment: SUCCESS"
else
    echo "Last deployment: FAILED"
    # 发送告警通知
fi
```

## 🔐 安全建议

1. **权限控制**
   ```bash
   # 脚本只允许 root 执行
   sudo chown root:root scripts/cron_redeploy.sh
   sudo chmod 700 scripts/cron_redeploy.sh
   ```

2. **日志保护**
   ```bash
   # 日志目录权限
   sudo chmod 750 /var/log/feishu-bot
   ```

3. **定期审计**
   - 定期检查部署日志
   - 监控异常构建行为
   - 及时更新依赖版本

## 📚 相关文档

- [Docker Compose 文档](https://docs.docker.com/compose/)
- [Cron 表达式](https://crontab.guru/)
- [Systemd Timer](https://www.freedesktop.org/software/systemd/man/systemd.timer.html)
