import html, re
from neefeel.dashboard.graph_render import graph_to_dot
from neefeel.dashboard.preview_embed import inline_preview_html, sandboxed_preview_html
from neefeel.orchestration.task_graph import TaskGraph
from helpers import mk


def test_preview_is_sandboxed_without_same_origin(tmp_path):
    (tmp_path / "index.html").write_text('<link rel="stylesheet" href="s.css"><script src="a.js"></script><b>"hi"</b>')
    (tmp_path / "s.css").write_text("b{}"); (tmp_path / "a.js").write_text("window.x=1")
    assert "<style>" in inline_preview_html(str(tmp_path))
    wrapped = sandboxed_preview_html(str(tmp_path))
    sandbox = re.search(r'sandbox="([^"]*)"', wrapped).group(1)
    assert "allow-scripts" in sandbox and "allow-same-origin" not in sandbox
    assert "window.x=1" in html.unescape(re.search(r'srcdoc="(.*)"></iframe>', wrapped, re.S).group(1))


def test_dot_labels_survive_hostile_titles():
    g = TaskGraph([mk("T1", title='Say "hi"\\n\nnow')])
    dot = graph_to_dot(g)
    assert '"hi"' not in dot.split("label=")[1].split(",")[0][1:-1] and dot.count("\n") == 6
