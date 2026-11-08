#!/usr/bin/env bash
# 一键拉起本地 FalkorDB（可选图后端），供 StockGraph 的 falkordb backend 使用。
#
#   ./scripts/falkordb_up.sh            # 启动（默认端口 6379，首次会自动 pull 镜像）
#   ./scripts/falkordb_up.sh stop       # 停止并删除容器
#   ./scripts/falkordb_up.sh status     # 看容器与连通性
#
# 不想用 Docker 也可以直接跑二进制：
#   docker run -d -p 6379:6379 -p 3000:3000 falkordb/falkordb:latest
set -euo pipefail

CONTAINER="${FALKORDB_CONTAINER:-stockgraph-falkordb}"
PORT="${FALKORDB_PORT:-6379}"
UI_PORT="${FALKORDB_UI_PORT:-3000}"
VOLUME="${FALKORDB_VOLUME:-stockgraph-falkordb-data}"
ACTION="${1:-up}"

need_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "未检测到 docker。请先安装 Docker，或改用二进制方式启动 FalkorDB。" >&2
    echo "参考: https://docs.falkordb.com/getting-started/installation.html" >&2
    exit 1
  fi
}

case "$ACTION" in
  up|start)
    need_docker
    if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
      docker start "$CONTAINER" >/dev/null
      echo "已启动已有容器 $CONTAINER"
    else
      docker run -d \
        --name "$CONTAINER" \
        --restart unless-stopped \
        -p "${PORT}:6379" \
        -p "${UI_PORT}:3000" \
        -v "${VOLUME}:/var/lib/falkordb/data" \
        falkordb/falkordb:latest >/dev/null
      echo "已创建容器 $CONTAINER（Redis 端口 ${PORT}，Web UI 端口 ${UI_PORT}）"
    fi
    echo "等待 Redis 就绪..."
    for _ in $(seq 1 30); do
      if docker exec "$CONTAINER" redis-cli ping >/dev/null 2>&1; then
        echo "FalkorDB 就绪: redis://127.0.0.1:${PORT}"
        echo "下一步: python scripts/graph_backend.py switch falkordb --migrate"
        exit 0
      fi
      sleep 1
    done
    echo "FalkorDB 未在 30 秒内就绪，请检查: docker logs $CONTAINER" >&2
    exit 1
    ;;
  stop|down)
    need_docker
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    echo "已停止并删除容器 $CONTAINER"
    ;;
  status)
    need_docker
    docker ps -a --filter "name=^/${CONTAINER}$" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
    docker exec "$CONTAINER" redis-cli ping 2>/dev/null || echo "容器未运行"
    ;;
  *)
    echo "用法: $0 [up|stop|status]" >&2
    exit 2
    ;;
esac
