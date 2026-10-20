"""
Demo entry point for the full Neefeel platform (CLI).

Usage (from the directory that CONTAINS the `neefeel` package folder):
    cp neefeel/.env.example neefeel/.env     # then fill in a key
    python -m neefeel.main
"""

import asyncio
import os
import warnings

from dotenv import load_dotenv

load_dotenv()
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

from .cofounder import AICofounder

SAMPLE_PROMPT = (
    "Build a client portal for African design agencies with recurring Paystack retainers "
    "and a production Netlify deploy."
)


async def review_pending(cofounder: AICofounder) -> None:
    """Walks every task awaiting the founder: approve / reject / skip."""
    graph = cofounder._active_graph
    while graph is not None and graph.pending_hitl():
        progressed = False
        for task in list(graph.pending_hitl()):
            held = cofounder._active_engine.held_result(task.task_id)
            print(f"\n🛡️  {task.task_id} · {task.department.value} · {task.title} (risk: {task.risk_level.value})")
            if held is not None:
                print("   Draft awaiting your review:\n   " + held.output[:600].replace("\n", "\n   "))
                if held.risks:
                    print("   Risks:", "; ".join(held.risks))
            else:
                print("   Instruction:", task.instruction)
            choice = input("   [a]pprove / [r]eject / [s]kip: ").strip().lower()
            if choice == "a":
                await cofounder.approve(task.task_id)
                progressed = True
            elif choice == "r":
                await cofounder.reject(task.task_id, "Rejected by founder in CLI")
                progressed = True
        if not progressed:  # everything skipped
            break


async def main():
    model_name = os.environ.get("NEELFEEL_MODEL")  # falls back to the cofounder default
    cofounder = AICofounder(model=model_name, auto_open_preview=True)

    try:
        await cofounder.memory.seed_global_identity(
            company_name="Neefeel Venture Studio",
            mission="Rapidly prototype, design, and validate software products.",
            vision="Turn founder ideas into working software prototypes.",
            brand_assets=["Tone: Modern, direct, clean"],
        )

        print(f"🚀 Founder prompt: '{SAMPLE_PROMPT}'\n")

        print("⚙️  Decomposing objective into a task DAG...")
        plan = await cofounder.decompose(SAMPLE_PROMPT)
        print("=== Decomposition Plan ===")
        print(plan.model_dump_json(indent=2))

        print("\n⚙️  Dispatching tasks to the executive pod...")
        await cofounder.execute(plan)

        await review_pending(cofounder)

        print("\n=== Task Results ===")
        for r in cofounder.current_results():
            print(f"{r.task_id} [{r.department.value}] {r.status}: {r.output[:120]!r}")

        print("\n⚙️  Synthesizing final executive briefing...")
        briefing = await cofounder.synthesize(SAMPLE_PROMPT, plan)
        print("\n" + "=" * 70)
        print("📋 EXECUTIVE BRIEFING")
        print("=" * 70)
        print(briefing.model_dump_json(indent=2))
    finally:
        await cofounder.close()


if __name__ == "__main__":
    asyncio.run(main())
