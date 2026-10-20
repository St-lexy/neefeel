import pytest
from neefeel.text_utils import extract_json, infer_status_and_risks, strip_think


def test_strip_think_variants():
    assert strip_think("<think>x</think>answer") == "answer"
    assert strip_think("hidden reasoning</think>answer") == "answer"  # opening tag dropped by provider
    assert strip_think("plain") == "plain"


def test_extract_json_handles_think_and_fences():
    assert extract_json('<think>{x}</think>\n```json\n{"a": 1}\n```') == {"a": 1}
    for bad in ("no json here", '{"a": "unterminated', "[1,2]"):
        with pytest.raises(Exception):
            extract_json(bad)


@pytest.mark.parametrize("text,expected", [
    ("Plan\n\nRisks:\n- API limits\n- Scope creep\n", ["API limits", "Scope creep"]),
    ("Plan\n\nRisks: None", []),
    ("**Risks:**\n- Heavy infra cost\n- GDPR\n", ["Heavy infra cost", "GDPR"]),   # was: junk '*' bullet
    ("## Risks\n- Heavy infra cost\n- GDPR\n", ["Heavy infra cost", "GDPR"]),     # was: lost entirely
    ("Risks:\n1. Heavy infra cost\n2. GDPR\n", ["Heavy infra cost", "GDPR"]),     # was: only the first
    ("Intro\nRisks:\n- A\n\n## Next steps\n- do x\n", ["A"]),
    ("Risks:\n- A\n- B\nSTATUS: blocked_on_hitl", ["A", "B"]),
])
def test_risk_parsing(text, expected):
    assert infer_status_and_risks(text)[1] == expected


def test_status_needs_explicit_line_not_prose():
    assert infer_status_and_risks("Fine.\nRisks: None\nSTATUS: blocked_on_hitl")[0] == "blocked_on_hitl"
    assert infer_status_and_risks("**STATUS: blocked_on_hitl**")[0] == "blocked_on_hitl"
    # These used to block the task:
    assert infer_status_and_risks("This requires founder approval before spend.\nRisks: None")[0] == "completed"
    assert infer_status_and_risks("It is not blocked_on_hitl and needs no approval.\nRisks: None")[0] == "completed"


def test_contradicts_phrase_captured_once():
    _, risks = infer_status_and_risks("Body contradicts Product's pricing: $9 vs $19\nRisks:\n- contradicts Product's pricing: tiers lose money")
    assert any("tiers lose money" in r for r in risks)
    assert sum("Product's pricing" in r for r in risks) == 2  # the bullet + the body mention, no duplicates of either
