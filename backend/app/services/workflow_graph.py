from __future__ import annotations

from app.models.schemas import WorkflowGraph


class InvalidWorkflowGraph(ValueError):
    pass


def validate_graph(graph: WorkflowGraph) -> None:
    node_ids = [node.id for node in graph.nodes]
    if len(node_ids) != len(set(node_ids)):
        raise InvalidWorkflowGraph("Workflow node IDs must be unique")
    known = set(node_ids)
    for edge in graph.edges:
        if edge.source not in known or edge.target not in known:
            raise InvalidWorkflowGraph(f"Connection {edge.id} points to a missing node")
        if edge.source == edge.target:
            raise InvalidWorkflowGraph(f"Connection {edge.id} cannot connect a node to itself")

    adjacency: dict[str, list[str]] = {node_id: [] for node_id in known}
    for edge in graph.edges:
        adjacency[edge.source].append(edge.target)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise InvalidWorkflowGraph("Workflow connections must not contain a cycle")
        if node_id in visited:
            return
        visiting.add(node_id)
        for neighbor in adjacency[node_id]:
            visit(neighbor)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in known:
        visit(node_id)

