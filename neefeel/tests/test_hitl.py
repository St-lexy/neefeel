import pytest
from neefeel.models import Department as D
from neefeel.orchestration.task_graph import TaskGraph
from neefeel.safety.hitl import HITLGate, keyword_flags_hitl
from helpers import mk


@pytest.mark.parametrize("text", [
    "Write the PRD: user can sign up and sign in with email",
    "Define MVP scope for recurring Paystack retainers",
    "Draft the go-to-market launch sequence and channel plan",
    "Design the payment screen and checkout flow wireframes",
    "Produce database schema for invoices and billing",
    "Define the persona: a busy engineer who wants to pay less",
    "Model pricing tiers and cost per charge",
    "Draft a paid campaign plan with ad spend assumptions",
    "Architecture for a production-ready system on Netlify",
])
def test_drafting_and_planning_are_not_gated(text):
    assert not keyword_flags_hitl(text)


@pytest.mark.parametrize("text", [
    "Deploy the app to production on Netlify",
    "Publish the site to production",
    "Run paid ads on Instagram with a $500 budget",
    "Send an email to customers announcing the launch",
    "Charge customers their monthly retainer",
    "Sign the contractor agreement with the vendor",
    "Delete the production database records",
    "Write the plan, then actually deploy it live",
])
def test_real_actions_are_gated(text):
    assert keyword_flags_hitl(text)


def test_apply_policy_and_respects_decomposer_flag():
    g = TaskGraph([mk("T1", D.LEGAL, instr="Draft ToS"), mk("T2", gate=True), mk("T3", instr="Write the PRD"),
                   mk("T4", D.ENGINEERING, instr="Deploy to production on Vercel")])
    gate = HITLGate(); gate.apply(g)
    assert [t.requires_human_confirmation for t in g.tasks] == [True, True, False, True]
    assert gate.should_gate_now(g.get("T1")); gate.approve("T1"); assert not gate.should_gate_now(g.get("T1"))
