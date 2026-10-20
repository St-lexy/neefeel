"""Prompts, models and parsers must agree. These tests fail when one side drifts."""
import json, re
from neefeel import cofounder as cf
from neefeel.executives.finance import FinanceExecutive
from neefeel.executives.legal import LegalExecutive
from neefeel.executives.people import PeopleExecutive
from neefeel.executives.engineering import EngineeringExecutive
from neefeel.models import (CofounderDialogueResponse, DecompositionPlan, Department, ExecutiveBriefing,
                            RiskLevel, StructuredTask)
from neefeel.safety.conflict import CONFLICT_SYSTEM_PROMPT, FEASIBILITY_RISK_KEYWORDS, ConflictResolver
from neefeel.models import TaskResult
from neefeel.text_utils import OUTPUT_FORMAT_INSTRUCTIONS, infer_status_and_risks


def schema_keys(prompt):
    block = prompt[prompt.index("{"): prompt.rindex("}") + 1]
    return set(re.findall(r'"(\w+)"\s*:', block))


def test_dialogue_prompt_matches_model():
    assert schema_keys(cf.DIALOGUE_SYSTEM_PROMPT) == set(CofounderDialogueResponse.model_fields)


def test_decomposition_prompt_matches_models():
    keys = schema_keys(cf.DECOMPOSITION_SYSTEM_PROMPT)
    task_fields = set(StructuredTask.model_fields) - {"status"}           # status is engine-owned
    assert keys == set(DecompositionPlan.model_fields) | task_fields


def test_decomposition_prompt_lists_exactly_the_departments_and_risk_levels():
    p = cf.DECOMPOSITION_SYSTEM_PROMPT
    line = re.search(r'"department": "([^"]+)"', p).group(1)
    assert {d.strip() for d in line.split("|")} == {d.value for d in Department}
    rl = re.search(r'"risk_level": "([^"]+)"', p).group(1)
    assert {x.strip() for x in rl.split("|")} == {r.value for r in RiskLevel}


def test_synthesis_prompt_keys_are_briefing_fields():
    assert schema_keys(cf.SYNTHESIS_SYSTEM_PROMPT) <= set(ExecutiveBriefing.model_fields)
    assert "deliverables" not in schema_keys(cf.SYNTHESIS_SYSTEM_PROMPT)  # code owns deliverables


def test_conflict_prompt_keys_are_the_ones_the_resolver_reads():
    assert schema_keys(CONFLICT_SYSTEM_PROMPT) == {"description", "recommended_resolution", "alternatives"}


def test_sample_json_in_prompts_round_trips_through_models():
    plan = {"founder_prompt": "x", "summary": "s", "tasks": [
        {"task_id": "T1", "department": "product", "title": "t", "instruction": "i", "depends_on": [],
         "requires_human_confirmation": False, "risk_level": "low", "should_build": False}]}
    DecompositionPlan.model_validate(json.loads(json.dumps(plan)))
    CofounderDialogueResponse.model_validate({"intent": "ready_for_execution", "reply": "r", "execution_brief": "b"})


def test_format_footer_and_executive_phrases_are_what_the_parsers_detect():
    assert "STATUS: blocked_on_hitl" in OUTPUT_FORMAT_INSTRUCTIONS and "Risks:" in OUTPUT_FORMAT_INSTRUCTIONS
    for exe, phrase in ((FinanceExecutive, "contradicts Product's pricing:"),
                        (PeopleExecutive, "contradicts Finance's runway:"),
                        (EngineeringExecutive, "contradicts Product's scope:")):
        assert phrase in exe.system_prompt, exe
        _, risks = infer_status_and_risks(f"Analysis.\n\nRisks:\n- {phrase} reason\n")
        flagged = ConflictResolver._find_conflict_flags(
            {"T": TaskResult(task_id="T", department=Department.FINANCE, status="completed", output="o", risks=risks)})
        assert flagged, phrase
    assert "STATUS: blocked_on_hitl" in LegalExecutive.system_prompt


def test_prompts_do_not_promise_features_that_do_not_exist():
    assert "7-seat" not in cf.DIALOGUE_SYSTEM_PROMPT
    from neefeel.executives.product import ProductExecutive
    assert "feasibility check" not in ProductExecutive.system_prompt      # review is now real (Engineering), wording fixed
