"""Phase 1 linear pipeline: Thalamus → Hippocampus → Prefrontal → Broca.

Each region node is wrapped with audit instrumentation so completion of a
region emits a ``pipeline.region_complete`` event. See ponder.audit.
"""

from langgraph.graph import StateGraph, START, END

from ponder.audit import audit_wrap
from ponder.blackboard import BlackboardState
from ponder.regions.thalamus import thalamus_node
from ponder.regions.hippocampus import hippocampus_node
from ponder.regions.prefrontal import prefrontal_node
from ponder.regions.broca import broca_node


def build_pipeline():
    graph = StateGraph(BlackboardState)

    graph.add_node("thalamus", audit_wrap(thalamus_node, "thalamus"))
    graph.add_node("hippocampus", audit_wrap(hippocampus_node, "hippocampus"))
    graph.add_node("prefrontal", audit_wrap(prefrontal_node, "prefrontal"))
    graph.add_node("broca", audit_wrap(broca_node, "broca"))

    graph.add_edge(START, "thalamus")
    graph.add_edge("thalamus", "hippocampus")
    graph.add_edge("hippocampus", "prefrontal")
    graph.add_edge("prefrontal", "broca")
    graph.add_edge("broca", END)

    return graph.compile()
