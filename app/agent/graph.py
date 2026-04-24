from langgraph.graph import StateGraph, END
from typing import Any
from app.agent.nodes import retrieve_patterns, review_code


def build_graph():
    graph = StateGraph(dict)
    graph.add_node("retrieve_patterns", retrieve_patterns)
    graph.add_node("review_code", review_code)
    graph.set_entry_point("retrieve_patterns")
    graph.add_edge("retrieve_patterns", "review_code")
    graph.add_edge("review_code", END)
    return graph.compile()


agent = build_graph()
