import pytest
from neefeel.models import Department as D, TaskStatus as S
from neefeel.orchestration.task_graph import CyclicDependencyError, TaskGraph
from helpers import mk


def test_validation():
    with pytest.raises(CyclicDependencyError):
        TaskGraph([mk("A", deps=["B"]), mk("B", deps=["A"])])
    with pytest.raises(CyclicDependencyError):
        TaskGraph([mk("A", deps=["A"])])
    with pytest.raises(ValueError, match="unknown"):
        TaskGraph([mk("A", deps=["Z"])])
    with pytest.raises(ValueError, match="Duplicate"):  # used to silently merge
        TaskGraph([mk("A"), mk("A", D.DESIGN)])


def test_blocked_dependents_resume_after_dependency_completes():
    g = TaskGraph([mk("A"), mk("B", deps=["A"]), mk("C", deps=["B"])])
    g.set_status("A", S.BLOCKED_ON_HITL)
    assert g.ready_batch() == []
    assert g.get("B").status == S.BLOCKED_ON_DEPENDENCY
    assert g.get("C").status == S.BLOCKED_ON_DEPENDENCY      # transitive
    g.set_status("A", S.COMPLETED)
    assert [t.task_id for t in g.ready_batch()] == ["B"]     # used to stay blocked forever
    assert g.get("C").status == S.PENDING


def test_failed_dependency_blocks_dependents():
    g = TaskGraph([mk("A"), mk("B", deps=["A"])])
    g.set_status("A", S.FAILED)
    g.ready_batch()
    assert g.get("B").status == S.BLOCKED_ON_DEPENDENCY
