"""
Renders a TaskGraph as Graphviz DOT for the dashboard's Visual DAG Canvas —
node color encodes execution state, edges encode `depends_on`.
"""

from __future__ import annotations

from ..models import TaskStatus
from ..orchestration.task_graph import TaskGraph

STATUS_COLORS = {
    TaskStatus.PENDING: "#9CA3AF",
    TaskStatus.IN_PROGRESS: "#3B82F6",
    TaskStatus.COMPLETED: "#22C55E",
    TaskStatus.BLOCKED_ON_DEPENDENCY: "#F59E0B",
    TaskStatus.BLOCKED_ON_HITL: "#EF4444",
    TaskStatus.FAILED: "#7F1D1D",
}


def _escape(text: str) -> str:
    """Makes model-written titles safe inside a DOT double-quoted label."""
    return text.replace("\\", "/").replace('"', "'").replace("\n", " ").replace("\r", " ")


def graph_to_dot(graph: TaskGraph) -> str:
    lines = [
        "digraph TaskGraph {",
        '  rankdir="LR";',
        '  bgcolor="transparent";',
        '  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11];',
        '  edge [color="#6B7280"];',
    ]
    for task in graph.tasks:
        color = STATUS_COLORS.get(task.status, "#9CA3AF")
        label = f"{_escape(task.title)}\\n[{task.department.value}]\\n{task.status.value}"
        lines.append(f'  "{task.task_id}" [label="{label}", fillcolor="{color}", fontcolor="white"];')
    for task in graph.tasks:
        for dep in task.depends_on:
            lines.append(f'  "{dep}" -> "{task.task_id}";')
    lines.append("}")
    return "\n".join(lines)
