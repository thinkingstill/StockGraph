"""图后端配置与「一键切换」。

优先级：环境变量 > config/graph_backend.json > 默认 sqlite。

一键切换的语义是：改一个地方，全链路生效。因此所有图读写都必须经过
`create_graph_store()`，不允许业务代码直接 new 具体后端。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from stockgraph.core.paths import GRAPH_BACKEND_CONFIG_PATH, ensure_runtime_dirs

SUPPORTED_BACKENDS = ("sqlite", "falkordb")
BACKEND_ENV = "STOCKGRAPH_GRAPH_BACKEND"

DEFAULT_CONFIG: dict[str, Any] = {
    "backend": "sqlite",
    "falkordb": {
        "host": "127.0.0.1",
        "port": 6379,
        "graph_name": "stockgraph",
        "username": "",
        "password": "",
        "timeout": 5,
    },
    "fallback_to_sqlite": True,
}


@dataclass(slots=True)
class GraphSettings:
    backend: str = "sqlite"
    falkordb: dict[str, Any] = field(default_factory=dict)
    fallback_to_sqlite: bool = True
    source: str = "default"

    def as_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "falkordb": self.falkordb,
            "fallback_to_sqlite": self.fallback_to_sqlite,
            "source": self.source,
        }


def config_path() -> Path:
    return Path(os.environ.get("STOCKGRAPH_GRAPH_CONFIG", GRAPH_BACKEND_CONFIG_PATH))


def load_config() -> dict[str, Any]:
    path = config_path()
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        if isinstance(payload, dict):
            if payload.get("backend"):
                config["backend"] = str(payload["backend"]).lower()
            if isinstance(payload.get("falkordb"), dict):
                config["falkordb"].update(payload["falkordb"])
            if "fallback_to_sqlite" in payload:
                config["fallback_to_sqlite"] = bool(payload["fallback_to_sqlite"])
    return config


def save_config(config: dict[str, Any]) -> Path:
    ensure_runtime_dirs()
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def resolve_settings() -> GraphSettings:
    config = load_config()
    backend = str(config.get("backend", "sqlite")).lower()
    source = "config" if config_path().exists() else "default"

    env_backend = os.environ.get(BACKEND_ENV, "").strip().lower()
    if env_backend:
        backend = env_backend
        source = "env"

    falkordb = dict(config.get("falkordb") or {})
    falkordb["host"] = os.environ.get("STOCKGRAPH_FALKORDB_HOST", falkordb.get("host", "127.0.0.1"))
    falkordb["port"] = int(os.environ.get("STOCKGRAPH_FALKORDB_PORT", falkordb.get("port", 6379)))
    falkordb["graph_name"] = os.environ.get(
        "STOCKGRAPH_FALKORDB_GRAPH", falkordb.get("graph_name", "stockgraph")
    )
    falkordb["username"] = os.environ.get("STOCKGRAPH_FALKORDB_USERNAME", falkordb.get("username", ""))
    falkordb["password"] = os.environ.get("STOCKGRAPH_FALKORDB_PASSWORD", falkordb.get("password", ""))
    falkordb["timeout"] = float(os.environ.get("STOCKGRAPH_FALKORDB_TIMEOUT", falkordb.get("timeout", 5)))

    fallback = config.get("fallback_to_sqlite", True)
    if os.environ.get("STOCKGRAPH_GRAPH_FALLBACK") is not None:
        fallback = os.environ["STOCKGRAPH_GRAPH_FALLBACK"] not in {"0", "false", "False", ""}

    return GraphSettings(
        backend=backend,
        falkordb=falkordb,
        fallback_to_sqlite=bool(fallback),
        source=source,
    )


def switch_backend(
    backend: str,
    *,
    host: str | None = None,
    port: int | None = None,
    graph_name: str | None = None,
    password: str | None = None,
    fallback_to_sqlite: bool | None = None,
) -> dict[str, Any]:
    """把默认后端写进配置文件，返回新的配置。

    只负责落盘，不做连通性校验；校验由 CLI 的 `switch` 命令完成，
    这样即使 FalkorDB 暂时不可用也能先把配置改过去（配合 fallback）。
    """
    normalized = (backend or "").strip().lower()
    if normalized not in SUPPORTED_BACKENDS:
        raise ValueError(f"不支持的后端: {backend}，可选值: {', '.join(SUPPORTED_BACKENDS)}")

    config = load_config()
    config["backend"] = normalized
    if host:
        config["falkordb"]["host"] = host
    if port:
        config["falkordb"]["port"] = int(port)
    if graph_name:
        config["falkordb"]["graph_name"] = graph_name
    if password is not None:
        config["falkordb"]["password"] = password
    if fallback_to_sqlite is not None:
        config["fallback_to_sqlite"] = bool(fallback_to_sqlite)

    save_config(config)
    return config
