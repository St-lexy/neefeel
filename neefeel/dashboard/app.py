"""
Founder Web Dashboard — Streamlit.
Conversational co-founder loop + 7-seat executive pod.

Run from the directory that CONTAINS the `neefeel` package folder:
    streamlit run neefeel/dashboard/app.py
"""

from __future__ import annotations

import asyncio
import inspect
import os
import sys
import threading
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

PROJECT_PARENT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(PROJECT_PARENT))

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")
load_dotenv()

from neefeel.cofounder import AICofounder
from neefeel.dashboard.graph_render import graph_to_dot
from neefeel.dashboard.preview_embed import sandboxed_preview_html
from neefeel.models import Department

st.set_page_config(page_title="Neefeel — AI Co-founder", layout="wide")

# Streamlit replaced use_container_width=True with width="stretch"; support both.
STRETCH = (
    {"width": "stretch"} if "width" in inspect.signature(st.button).parameters
    else {"use_container_width": True}
)


def show_html(markup: str, height: int) -> None:
    """Render trusted wrapper markup (st.components.v1.html is being removed)."""
    if hasattr(st, "iframe"):
        st.iframe(markup, height=height)
    else:
        st.components.v1.html(markup, height=height + 20, scrolling=True)


@st.cache_resource
def _background_loop() -> asyncio.AbstractEventLoop:
    """ONE long-lived event loop for the whole app. The async HTTP client inside
    the model client binds to the loop it first runs on; creating a new loop per
    call (asyncio.run) breaks it on the second call with 'Event loop is closed'."""
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True, name="neefeel-loop").start()
    return loop


def run_async(coro):
    return asyncio.run_coroutine_threadsafe(coro, _background_loop()).result()


# ---- Sidebar ------------------------------------------------------------------------------
st.sidebar.header("Model Connection")
default_api_key = os.environ.get("FIREWORKS_API_KEY") or st.secrets.get("FIREWORKS_API_KEY", "")
default_base_url = os.environ.get("FIREWORKS_BASE_URL") or st.secrets.get("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1")
default_model = os.environ.get("NEELFEEL_MODEL") or st.secrets.get("NEELFEEL_MODEL", "accounts/fireworks/models/deepseek-v4p1-flash-1017")

model_name = st.sidebar.text_input("Model", value=default_model, key="cfg_model")
base_url = st.sidebar.text_input("Base URL", value=default_base_url, key="cfg_base_url")
api_key = st.sidebar.text_input("API Key", value=default_api_key, type="password", key="cfg_api_key")
auto_mobilize = st.sidebar.checkbox(
    "Auto-mobilize the pod when the co-founder says it's ready",
    value=True,
    help="Each run makes several model calls and generates a prototype. Turn off to confirm first.",
)

# ---- (Re)initialise the co-founder when the connection settings change --------------------
needs_init = (
    "cofounder" not in st.session_state
    or st.session_state.get("_last_model") != model_name
    or st.session_state.get("_last_base_url") != base_url
    or st.session_state.get("_last_api_key") != api_key
)

if needs_init:
    if "cofounder" in st.session_state:
        try:
            run_async(st.session_state.cofounder.close())
        except Exception:
            pass

    cofounder_instance = AICofounder(
        model=model_name, base_url=base_url or None, api_key=api_key or None,
        auto_open_preview=False,  # the dashboard embeds the preview itself
    )
    run_async(
        cofounder_instance.memory.seed_global_identity(
            company_name="Neefeel Venture Studio",
            mission="Empower solo founders to ship high-confidence MVPs with autonomous executive oversight.",
            vision="A trusted AI leadership team that protects unit economics and manages risk.",
            brand_assets=["Tone: Strategic, pragmatic, sharp, direct"],
        )
    )
    st.session_state.cofounder = cofounder_instance
    st.session_state._last_model = model_name
    st.session_state._last_base_url = base_url
    st.session_state._last_api_key = api_key
    for key, default in (("chat_messages", []), ("plan", None), ("briefing", None),
                         ("brief", ""), ("pending_brief", "")):
        st.session_state[key] = default

cofounder: AICofounder = st.session_state.cofounder

if st.sidebar.button("Reset Session / Reload Pod", **STRETCH, key="btn_reset_session"):
    cofounder.reset_session()  # clears the co-founder's own state, not just the UI's
    st.session_state.update(chat_messages=[], plan=None, briefing=None, brief="", pending_brief="")
    st.rerun()


def mobilize(brief: str) -> None:
    """Decompose the brief and run the pod. `brief` is the co-founder's
    self-contained directive, not the founder's last (possibly one-word) message."""
    with st.spinner("Decomposing directive into task DAG..."):
        plan = run_async(cofounder.decompose(brief))
    with st.spinner("Dispatching across executive departments..."):
        run_async(cofounder.execute(plan))
    st.session_state.plan = plan
    st.session_state.brief = brief
    st.session_state.briefing = None
    st.session_state.pending_brief = ""
    st.rerun()


st.title("Neefeel — AI Co-founder Workspace")

# ---- Dialogue -------------------------------------------------------------------------------
chat_container = st.container()
with chat_container:
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if msg.get("missing"):
                st.warning("⚠️ **Missing Context Identified:**\n" + "\n".join(f"- {m}" for m in msg["missing"]))
            if msg.get("recalled"):
                st.caption("🧠 **Recalled from History:** " + ", ".join(msg["recalled"]))

if user_input := st.chat_input("Discuss strategy, specify features, or instruct the pod..."):
    st.session_state.chat_messages.append({"role": "user", "content": user_input})
    with chat_container:
        with st.chat_message("user"):
            st.write(user_input)
        with st.chat_message("assistant"):
            with st.spinner("Analyzing intent and recalling context..."):
                dialogue = run_async(cofounder.chat(user_input))
            st.write(dialogue.reply)
            if dialogue.missing_information:
                st.warning("⚠️ **Missing Context Identified:**\n" + "\n".join(f"- {m}" for m in dialogue.missing_information))
            if dialogue.recalled_facts:
                st.caption("🧠 **Recalled from History:** " + ", ".join(dialogue.recalled_facts))

    st.session_state.chat_messages.append({
        "role": "assistant", "content": dialogue.reply,
        "missing": dialogue.missing_information, "recalled": dialogue.recalled_facts,
    })

    if dialogue.intent == "ready_for_execution":
        brief = dialogue.execution_brief.strip() or user_input
        if auto_mobilize:
            st.info("🚀 Strategy aligned. Mobilizing the executive pod...")
            mobilize(brief)
        else:
            st.session_state.pending_brief = brief
            st.rerun()

if st.session_state.pending_brief:
    st.info("The co-founder considers this ready for execution.")
    with st.expander("Execution brief", expanded=False):
        st.write(st.session_state.pending_brief)
    if st.button("🚀 Mobilize the pod", type="primary", key="btn_mobilize"):
        mobilize(st.session_state.pending_brief)

# ---- Execution view -------------------------------------------------------------------------
plan = st.session_state.plan
if plan is not None and cofounder._active_graph is not None:
    graph = cofounder._active_graph
    engine = cofounder._active_engine

    st.subheader("Task DAG Execution")
    st.graphviz_chart(graph_to_dot(graph), **STRETCH)

    pending_tasks = graph.pending_hitl()
    if pending_tasks:
        st.subheader("⚠️ Awaiting Founder Authorization")
        st.info(f"{len(pending_tasks)} task(s) need your decision before dependent work can proceed.")

        if len(pending_tasks) > 1:
            if st.button(f"✅ Approve All ({len(pending_tasks)} Tasks)", type="primary",
                         **STRETCH, key="btn_approve_all_tasks"):
                with st.spinner("Authorizing all tasks and resuming pipeline..."):
                    run_async(cofounder.approve_all([t.task_id for t in pending_tasks]))
                st.rerun()

        for task in pending_tasks:
            held = engine.held_result(task.task_id)
            with st.expander(f"{task.title} · {task.department.value} · risk: {task.risk_level.value}", expanded=True):
                if held is not None:
                    st.caption("The executive finished this draft and flagged it for your review. "
                               "Approving accepts it as-is (no re-run); modifying re-runs it.")
                    st.write(held.output)
                    if held.risks:
                        st.warning("Risks Flagged: " + "; ".join(held.risks))
                else:
                    st.caption("Held BEFORE execution. Approving lets the task run."
                               + (" The prototype preview appears only after this task runs." if task.should_build else ""))
                st.write(f"**Instruction:** {task.instruction}")

                approve_col, reject_col = st.columns(2)
                if approve_col.button("✅ Approve", key=f"btn_approve_{task.task_id}", **STRETCH):
                    with st.spinner(f"Resuming '{task.title}'..."):
                        run_async(cofounder.approve(task.task_id))
                    st.rerun()
                if reject_col.button("❌ Reject", key=f"btn_reject_{task.task_id}", **STRETCH):
                    run_async(cofounder.reject(task.task_id, "Rejected by founder"))
                    st.rerun()

                new_instruction = st.text_area("Modify instruction and resubmit", value=task.instruction,
                                               key=f"txt_modify_{task.task_id}")
                if st.button("✏️ Modify & Resubmit", key=f"btn_modify_{task.task_id}", **STRETCH):
                    with st.spinner(f"Resubmitting '{task.title}'..."):
                        run_async(cofounder.modify_and_resume(task.task_id, new_instruction))
                    st.rerun()

    results = cofounder.current_results()

    st.subheader("Executive Pod Deliverables")
    all_departments = list(Department)
    for tab, dept in zip(st.tabs([d.value.capitalize() for d in all_departments]), all_departments):
        with tab:
            dept_results = [r for r in results if r.department == dept]
            if not dept_results:
                st.caption("No deliverables submitted for this department.")
            for r in dept_results:
                with st.expander(f"{r.task_id} — {r.status.upper()}", expanded=True):
                    st.write(r.output)
                    if r.risks:
                        st.warning("Risks Flagged: " + "; ".join(r.risks))
                    if r.artifacts:
                        st.caption("Generated files: " + ", ".join(r.artifacts))

    # Live prototype preview — only from this run's results (never a stale folder).
    preview_project_dir = None
    for r in results:
        preview = (r.data or {}).get("preview")
        if preview and preview.get("project_dir") and os.path.exists(preview["project_dir"]):
            preview_project_dir = preview["project_dir"]

    # Always say what happened to the prototype, so a missing preview is never a mystery.
    build_tasks = [t for t in graph.tasks if t.department == Department.ENGINEERING and t.should_build]
    for bt in build_tasks:
        br = engine.results.get(bt.task_id)
        if br is not None and br.data.get("build_error"):
            st.error(f"Prototype build for '{bt.title}' failed: {br.data['build_error']}")
            if st.button("🔁 Retry prototype build", key=f"btn_rebuild_{bt.task_id}"):
                with st.spinner("Rebuilding the prototype..."):
                    run_async(cofounder.rebuild_prototype(bt.task_id))
                st.rerun()
        elif br is None or (br.status in ("blocked_on_hitl", "failed") and not (br.data or {}).get("preview")):
            st.info(f"Prototype for '{bt.title}' is not built yet (status: {bt.status.value}).")
    if not build_tasks:
        st.caption("This plan has no engineering build task, so there is no prototype to preview.")

    if preview_project_dir:
        st.subheader("Interactive Prototype Preview")
        try:
            show_html(sandboxed_preview_html(preview_project_dir, 600), 620)
        except Exception as e:
            st.caption(f"Could not render preview: {e}")

    # Executive briefing
    st.subheader("Synthesized Executive Briefing")
    if pending_tasks:
        st.caption("Resolve pending approvals above before generating the final briefing.")
    else:
        if st.button("Generate Executive Briefing", type="primary", key="btn_gen_briefing_main"):
            with st.spinner("Synthesizing status across all departments..."):
                st.session_state.briefing = run_async(
                    cofounder.synthesize(st.session_state.brief or plan.founder_prompt, plan)
                )
            st.rerun()

        briefing = st.session_state.briefing
        if briefing is not None:
            st.markdown(briefing.strategy_summary)
            for heading, items in (("Risks", briefing.risks), ("Conflicts", briefing.conflicts),
                                   ("Next actions", briefing.next_actions)):
                if items:
                    st.markdown(f"**{heading}**\n" + "\n".join(f"- {i}" for i in items))
            if briefing.deliverables:
                with st.expander(f"📦 Deliverables ({len(briefing.deliverables)})", expanded=False):
                    for d in briefing.deliverables:
                        st.markdown(f"- {d}")
