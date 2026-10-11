import uuid

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph

from app.config import DATABASE_URL
from app.graph.nodes import literature_node
from app.graph.state import AgentState


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("literature_node", literature_node)
    graph.add_edge(START, "literature_node")
    graph.add_edge("literature_node", END)
    return graph


def start_research(query: str) -> dict:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is missing")
    initial: AgentState = {
        "query": query,
        "literature_context": [],
        "hypotheses": [],
        "approval_status": "",
    }
    thread_id = str(uuid.uuid4())
    with PostgresSaver.from_conn_string(DATABASE_URL) as checkpointer:
        checkpointer.setup()
        compiled = build_graph().compile(checkpointer=checkpointer)
        state = compiled.invoke(
            initial,
            config={"configurable": {"thread_id": thread_id}},
        )
    return {"thread_id": thread_id, "state": state}
