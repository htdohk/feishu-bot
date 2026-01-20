#!/usr/bin/env bash
set -euo pipefail

# 用途：
# - 手动执行：一键重新构建并重启 feishu-bot（docker compose）
# - cron 执行：同样可用（无交互、带日志）
# - 智能检测：自动判断是否需要忽略缓存重新构建
#
# 服务器项目路径（你服务器上是 /opt/feishu-bot）
PROJECT_DIR="${PROJECT_DIR:-/opt/feishu-bot}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
SERVICE_NAME="${SERVICE_NAME:-feishu-bot}"

# 日志位置（建议宿主机持久化目录）
LOG_DIR="${LOG_DIR:-/var/log/feishu-bot}"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/cron_redeploy.log}"

# 缓存检测文件
CACHE_DIR="${LOG_DIR}/.cache"
mkdir -p "${CACHE_DIR}"
DEPS_CACHE="${CACHE_DIR}/requirements.txt.md5"
DOCKERFILE_CACHE="${CACHE_DIR}/Dockerfile.md5"

ts() { date "+%Y-%m-%d %H:%M:%S"; }
log() { echo "[$(ts)] $*" | tee -a "${LOG_FILE}"; }

# 计算文件 MD5
get_md5() {
    local file="$1"
    if [[ ! -f "$file" ]]; then
        echo "missing"
        return
    fi
    
    # 兼容 macOS 和 Linux
    if command -v md5sum >/dev/null 2>&1; then
        md5sum "$file" | awk '{print $1}'
    elif command -v md5 >/dev/null 2>&1; then
        md5 -q "$file"
    else
        echo "unknown"
    fi
}

# 检查是否需要忽略缓存
should_ignore_cache() {
    local force_rebuild=false
    
    # 检查 requirements.txt 是否变化
    local current_deps_md5=$(get_md5 "${PROJECT_DIR}/requirements.txt")
    local cached_deps_md5=""
    if [[ -f "${DEPS_CACHE}" ]]; then
        cached_deps_md5=$(cat "${DEPS_CACHE}")
    fi
    
    if [[ "$current_deps_md5" != "$cached_deps_md5" ]]; then
        log "Dependencies changed (requirements.txt)"
        log "  Previous: ${cached_deps_md5:-none}"
        log "  Current:  ${current_deps_md5}"
        force_rebuild=true
    fi
    
    # 检查 Dockerfile 是否变化
    local current_dockerfile_md5=$(get_md5 "${PROJECT_DIR}/Dockerfile")
    local cached_dockerfile_md5=""
    if [[ -f "${DOCKERFILE_CACHE}" ]]; then
        cached_dockerfile_md5=$(cat "${DOCKERFILE_CACHE}")
    fi
    
    if [[ "$current_dockerfile_md5" != "$cached_dockerfile_md5" ]]; then
        log "Dockerfile changed"
        log "  Previous: ${cached_dockerfile_md5:-none}"
        log "  Current:  ${current_dockerfile_md5}"
        force_rebuild=true
    fi
    
    # 检查是否存在构建缓存
    local image_exists=false
    if docker images "${SERVICE_NAME}" --format "{{.Repository}}" | grep -q "${SERVICE_NAME}"; then
        image_exists=true
    fi
    
    if [[ "$image_exists" == "false" ]]; then
        log "No existing image found, will build from scratch"
        force_rebuild=true
    fi
    
    if [[ "$force_rebuild" == "true" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

# 更新缓存文件
update_cache() {
    get_md5 "${PROJECT_DIR}/requirements.txt" > "${DEPS_CACHE}"
    get_md5 "${PROJECT_DIR}/Dockerfile" > "${DOCKERFILE_CACHE}"
    log "Cache updated"
}

log "=== cron_redeploy start ==="
log "PROJECT_DIR=${PROJECT_DIR} SERVICE_NAME=${SERVICE_NAME} COMPOSE_FILE=${COMPOSE_FILE}"

if [[ ! -d "${PROJECT_DIR}" ]]; then
  log "ERROR: PROJECT_DIR not found: ${PROJECT_DIR}"
  exit 1
fi

cd "${PROJECT_DIR}"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  log "ERROR: compose file not found: ${PROJECT_DIR}/${COMPOSE_FILE}"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  log "ERROR: docker not found in PATH"
  exit 1
fi

# 兼容 docker compose v2（优先）和 docker-compose v1
if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  log "ERROR: neither 'docker compose' nor 'docker-compose' found"
  exit 1
fi

log "Compose cmd: ${COMPOSE}"

# 检查是否需要忽略缓存
IGNORE_CACHE=$(should_ignore_cache)

if [[ "$IGNORE_CACHE" == "true" ]]; then
    log "Building image with --no-cache (dependencies or Dockerfile changed)..."
    ${COMPOSE} -f "${COMPOSE_FILE}" build --pull --no-cache "${SERVICE_NAME}" 2>&1 | tee -a "${LOG_FILE}"
    update_cache
else
    log "Building image with cache (no critical changes detected)..."
    ${COMPOSE} -f "${COMPOSE_FILE}" build --pull "${SERVICE_NAME}" 2>&1 | tee -a "${LOG_FILE}"
fi

log "Restart service..."
${COMPOSE} -f "${COMPOSE_FILE}" up -d --remove-orphans "${SERVICE_NAME}" 2>&1 | tee -a "${LOG_FILE}"

log "Container status:"
docker ps --filter "name=${SERVICE_NAME}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>&1 | tee -a "${LOG_FILE}"

# 清理旧镜像（可选，保留最近3个版本）
log "Cleaning up old images..."
docker images "${SERVICE_NAME}" --format "{{.ID}}" | tail -n +4 | xargs -r docker rmi 2>&1 | tee -a "${LOG_FILE}" || true

log "=== cron_redeploy done ==="
