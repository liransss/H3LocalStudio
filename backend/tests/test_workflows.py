import pytest

from app.models.schemas import WorkflowEdge, WorkflowGraph, WorkflowNode
from app.services.workflow_graph import InvalidWorkflowGraph, validate_graph


def node(node_id: str) -> WorkflowNode:
    return WorkflowNode(id=node_id, type="prompt", position={"x": 0, "y": 0})


def test_workflow_serialization_and_validation():
    graph = WorkflowGraph(
        nodes=[node("prompt"), node("h3"), node("preview")],
        edges=[
            WorkflowEdge(id="a", source="prompt", target="h3"),
            WorkflowEdge(id="b", source="h3", target="preview"),
        ],
    )
    validate_graph(graph)
    assert WorkflowGraph.model_validate_json(graph.model_dump_json()) == graph


def test_missing_node_and_cycle_are_rejected():
    missing = WorkflowGraph(nodes=[node("a")], edges=[WorkflowEdge(id="x", source="a", target="b")])
    with pytest.raises(InvalidWorkflowGraph):
        validate_graph(missing)

    cycle = WorkflowGraph(
        nodes=[node("a"), node("b")],
        edges=[WorkflowEdge(id="x", source="a", target="b"), WorkflowEdge(id="y", source="b", target="a")],
    )
    with pytest.raises(InvalidWorkflowGraph):
        validate_graph(cycle)

