from neefeel.models import Department, StructuredTask, TaskResult


def mk(tid, dept=Department.PRODUCT, deps=(), title=None, instr="Write a spec for the product.", gate=False, **kw):
    return StructuredTask(task_id=tid, department=dept, title=title or tid, instruction=instr,
                          depends_on=list(deps), requires_human_confirmation=gate, **kw)


def ok(task, text=None, risks=None, status="completed"):
    return TaskResult(task_id=task.task_id, department=task.department, status=status,
                      output=text or f"out-{task.task_id}", risks=risks or [])
