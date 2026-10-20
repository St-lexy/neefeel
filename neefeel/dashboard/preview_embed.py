"""
Inlines a generated project's linked CSS/JS directly into its HTML, so the
dashboard can embed the prototype in an iframe-like component without
needing a local file server (browsers block relative-path fetches from a
raw file:// or srcdoc context).

Kept dependency-free from Streamlit on purpose, so it can be unit tested
without a running dashboard.
"""

from __future__ import annotations

import html as _html
import re
from pathlib import Path

_LINK_STYLESHEET_RE = re.compile(
    r'<link[^>]+rel=["\']stylesheet["\'][^>]+href=["\']([^"\']+)["\'][^>]*>', re.IGNORECASE
)
_SCRIPT_SRC_RE = re.compile(
    r'<script[^>]+src=["\']([^"\']+)["\'][^>]*>\s*</script>', re.IGNORECASE
)


def inline_preview_html(project_dir: str, index_filename: str = "index.html") -> str:
    """Reads index.html from `project_dir` and inlines any local
    stylesheet/script references it finds, returning one self-contained
    HTML string. Missing referenced files are left as-is (external CDN
    links, for instance, are untouched since they resolve fine on their own)."""
    project_path = Path(project_dir)
    index_path = project_path / index_filename
    html = index_path.read_text(encoding="utf-8")

    def _inline_css(match: "re.Match") -> str:
        href = match.group(1)
        css_path = project_path / href
        if css_path.exists():
            return f"<style>\n{css_path.read_text(encoding='utf-8')}\n</style>"
        return match.group(0)

    def _inline_js(match: "re.Match") -> str:
        src = match.group(1)
        js_path = project_path / src
        if js_path.exists():
            return f"<script>\n{js_path.read_text(encoding='utf-8')}\n</script>"
        return match.group(0)

    html = _LINK_STYLESHEET_RE.sub(_inline_css, html)
    html = _SCRIPT_SRC_RE.sub(_inline_js, html)
    return html


# Inside an opaque-origin sandbox `localStorage` throws, and generated prototypes are
# told to persist with it, so provide an in-memory stand-in when the real one is blocked.
_STORAGE_SHIM = (
    "<script>try{window.localStorage.getItem('_')}catch(e){var m={};"
    "Object.defineProperty(window,'localStorage',{value:{getItem:function(k){return k in m?m[k]:null},"
    "setItem:function(k,v){m[k]=String(v)},removeItem:function(k){delete m[k]},clear:function(){m={}},"
    "key:function(i){return Object.keys(m)[i]||null},get length(){return Object.keys(m).length}}})}</script>"
)


def sandboxed_preview_html(project_dir: str, height: int = 600, index_filename: str = "index.html") -> str:
    """Wraps the inlined prototype in an iframe WITHOUT `allow-same-origin`.

    The prototype is model-written code. Embedded directly it would run with
    the dashboard's own origin (it could read or drive the Streamlit page). In
    this sandbox its scripts, forms and modals work, but it gets an opaque
    origin and cannot reach the parent page."""
    inner = inline_preview_html(project_dir, index_filename)
    inner = _STORAGE_SHIM + inner
    return (
        f'<iframe sandbox="allow-scripts allow-forms allow-modals allow-popups" '
        f'style="width:100%;height:{int(height)}px;border:1px solid #334155;border-radius:8px;background:white" '
        f'srcdoc="{_html.escape(inner, quote=True)}"></iframe>'
    )
