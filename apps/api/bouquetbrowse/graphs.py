"""Two independently checkpointed workflows; domain services own all facts."""

from contextlib import contextmanager
from typing import Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .providers import CapabilityError

BEHAVIOR_VERSION = "threads-graphs-v5"


class GraphState(TypedDict, total=False):
    execution_id: str
    fingerprint: str
    frontier_id: str | None
    observation_id: str | None
    action_receipt_id: str | None
    capture_id: str | None
    offer_id: str | None
    review_id: str | None
    action_count: int
    planner_count: int
    needs_recheck: bool
    waiting_review: bool
    stop: bool


class GraphServices(Protocol):
    def stage(self, name: str, state: GraphState) -> GraphState: ...


def node(services, name):
    def execute(state):
        result = services.stage(name, state)
        if set(result) - set(GraphState.__annotations__):
            raise ValueError("Graph checkpoints may only contain compact continuation fields")
        for key, value in result.items():
            if isinstance(value, str) and len(value) > 160:
                raise ValueError("Long text does not belong in graph checkpoints")
            if not isinstance(value, (str, int, bool, type(None))):
                raise ValueError("Graph state must contain scalar identifiers and progress only")
            if key == "execution_id" and value != state["execution_id"]:
                raise ValueError("A node cannot reassign execution identity")
        return result

    return execute


def discovery_graph(services: GraphServices, checkpointer):
    builder = StateGraph(GraphState)
    stages = ["load_limits", "select_task", "observe", "plan", "execute", "persist", "segment", "dispatch"]
    for name in stages + ["finish"]:
        builder.add_node(name, node(services, name))
    builder.add_edge(START, "load_limits")
    builder.add_edge("load_limits", "select_task")
    builder.add_conditional_edges("select_task", lambda s: "finish" if s.get("stop") else "observe")
    for source, target in zip(stages[2:], stages[3:], strict=False):
        builder.add_conditional_edges(source, lambda s, next_node=target: "finish" if s.get("stop") else next_node)
    builder.add_conditional_edges("dispatch", lambda s: "finish" if s.get("stop") else "select_task")
    builder.add_edge("finish", END)
    return builder.compile(checkpointer=checkpointer)


def offer_graph(services: GraphServices, checkpointer):
    builder = StateGraph(GraphState)
    stages = ["load_evidence", "resolve", "prepare_media", "recognize", "validate", "route", "commit"]
    for name in stages + ["recheck"]:
        builder.add_node(name, node(services, name))

    def await_review(state):
        interrupt({"execution_id": state["execution_id"], "review_id": state.get("review_id")})
        # Resume input is a wake-up signal, not authorization to approve a claim.
        return node(services, "review_resolved")(state)

    builder.add_node("await_review", await_review)
    builder.add_edge(START, "load_evidence")
    for source, target in zip(stages[:3], stages[1:4], strict=True):
        builder.add_edge(source, target)
    builder.add_conditional_edges("recognize", lambda s: "recheck" if s.get("needs_recheck") else "validate")
    builder.add_edge("recheck", "validate")
    builder.add_edge("validate", "route")
    builder.add_conditional_edges("route", lambda s: "await_review" if s.get("waiting_review") else "commit")
    builder.add_edge("await_review", "validate")
    builder.add_edge("commit", END)
    return builder.compile(checkpointer=checkpointer)


@contextmanager
def postgres_checkpointer(database_url):
    import psycopg
    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    from psycopg.rows import dict_row
    from sqlalchemy.engine import make_url

    if not database_url.startswith("postgresql"):
        raise CapabilityError("Recurring graphs require PostgreSQL checkpoints.", "postgres_required")
    url = make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(
        url, autocommit=True, prepare_threshold=0, row_factory=dict_row, options="-c search_path=graph_checkpoints"
    ) as connection:
        if not connection.execute("SELECT to_regclass('graph_checkpoints.checkpoints') AS name").fetchone()["name"]:
            raise CapabilityError("Migration owner must initialize graph checkpoints first.", "checkpoints_not_ready")
        yield PostgresSaver(connection, serde=JsonPlusSerializer(pickle_fallback=False))


def invoke_graph(graph, execution_id, initial=None):
    from langsmith.run_helpers import tracing_context

    config = {"configurable": {"thread_id": execution_id}, "recursion_limit": 1300}
    with tracing_context(enabled=False):
        snapshot = graph.get_state(config)
        if snapshot.values and not snapshot.next and not snapshot.interrupts:
            return snapshot.values
        from langgraph.types import Command

        continuation = Command(resume=True) if snapshot.interrupts else None
        return graph.invoke(
            continuation if snapshot.values else initial or {"execution_id": execution_id}, config, durability="sync"
        )
