from dataclasses import dataclass, field


@dataclass(slots=True)
class GraphNode:
    node_id: str
    node_type: str
    node_key: str
    node_name: str
    attributes: dict = field(default_factory=dict)


@dataclass(slots=True)
class GraphEdge:
    source_node_id: str
    target_node_id: str
    edge_type: str
    weight: float
    trade_date: str = ""
    attributes: dict = field(default_factory=dict)


@dataclass(slots=True)
class Community:
    community_id: str
    member_node_ids: list[str] = field(default_factory=list)
    score: float = 0.0
    label: str = ""


@dataclass(slots=True)
class Subgraph:
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class GraphSnapshot:
    snapshot_date: str
    snapshot_type: str
    version: str = "v1"
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    communities: list[Community] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
