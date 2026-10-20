import json
import os
import sys
import time
from pathlib import Path
from typing import List, Literal
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

# Load environment
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)
load_dotenv()

API_KEY = os.environ.get("FIREWORKS_API_KEY") or os.environ.get("OPENAI_API_KEY")
BASE_URL = os.environ.get("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1")
MODEL = "accounts/fireworks/models/deepseek-v4-pro-0813"

# Pricing rates per 1M tokens (Fireworks standard tier for high-end reasoning models)
INPUT_COST_PER_M = 0.90   # $0.90 per 1M prompt tokens
OUTPUT_COST_PER_M = 0.90  # $0.90 per 1M completion tokens

if not API_KEY:
    print("Error: FIREWORKS_API_KEY not found in environment.")
    sys.exit(1)

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

# --- Strict Pydantic Schema for Structured Planning Output ---
class PlannedStep(BaseModel):
    step_id: str
    department: Literal["product", "design", "engineering", "growth", "legal", "finance", "people"]
    title: str
    rationale: str
    dependencies: List[str] = Field(default_factory=list)
    risk_assessment: str

class ArchitecturalPlan(BaseModel):
    summary: str
    critical_path: List[str]
    potential_bottlenecks: List[str]
    steps: List[PlannedStep]

SYSTEM_PROMPT = """You are the Senior Technical Strategist for Neefeel.
Deconstruct the founder's system proposal into an end-to-end multi-agent execution plan.
You must output strictly a single valid JSON object adhering to this schema:
{
  "summary": "High level strategy",
  "critical_path": ["step_id1", "step_id2"],
  "potential_bottlenecks": ["bottleneck 1"],
  "steps": [
    {
      "step_id": "P-1",
      "department": "product | design | engineering | growth | legal | finance | people",
      "title": "Short title",
      "rationale": "Reasoning for sequencing and department ownership",
      "dependencies": ["prior_step_id"],
      "risk_assessment": "Failure modes"
    }
  ]
}
Do not write markdown backticks (```json). Return pure JSON text only."""

PLANNING_PROMPT = """Create an end-to-end launch plan for migrating Neefeel from local memory to a multi-tenant Supabase pgvector store.
The plan must cover:
1. Database schema with RLS and 1536-dim vector indexing.
2. Async Python memory adapter integration.
3. Legal/Compliance verification for data residency and encryption in transit.
4. Unit economics of vector storage vs. query volume at 10,000 active founders.
Ensure dependency ordering reflects genuine blockers."""

print(f"Connecting to: {BASE_URL}")
print(f"Model: {MODEL}")
print("Executing structured planning call...\n" + "-" * 60)

t_start = time.perf_counter()
t_first_token = None
raw_chunks = []

stream = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": PLANNING_PROMPT},
    ],
    temperature=0.2,
    stream=True,
    stream_options={"include_usage": True},
)

usage_data = None

for chunk in stream:
    if chunk.choices and len(chunk.choices) > 0:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            if t_first_token is None:
                t_first_token = time.perf_counter()
            raw_chunks.append(delta)
            sys.stdout.write(delta)
            sys.stdout.flush()
    if hasattr(chunk, "usage") and chunk.usage:
        usage_data = chunk.usage

t_end = time.perf_counter()
full_raw_text = "".join(raw_chunks).strip()

print("\n" + "-" * 60)

# Telemetry calculations
ttft_ms = (t_first_token - t_start) * 1000 if t_first_token else 0.0
total_duration_s = t_end - t_start
generation_duration_s = (t_end - t_first_token) if t_first_token else total_duration_s

prompt_tokens = usage_data.prompt_tokens if usage_data else len(PLANNING_PROMPT.split()) * 2
completion_tokens = usage_data.completion_tokens if usage_data else len(raw_chunks)

throughput_tps = completion_tokens / generation_duration_s if generation_duration_s > 0 else 0.0

# Cost Calculation
prompt_cost = (prompt_tokens / 1_000_000) * INPUT_COST_PER_M
completion_cost = (completion_tokens / 1_000_000) * OUTPUT_COST_PER_M
total_cost = prompt_cost + completion_cost
cost_per_1k_tokens = (total_cost / ((prompt_tokens + completion_tokens) / 1000)) if (prompt_tokens + completion_tokens) > 0 else 0.0

# Schema Validation & Reasoning Quality Check
parsed_plan = None
schema_valid = False
validation_error = None

clean_json_str = full_raw_text
if clean_json_str.startswith("```json"):
    clean_json_str = clean_json_str[7:]
if clean_json_str.startswith("```"):
    clean_json_str = clean_json_str[3:]
if clean_json_str.endswith("```"):
    clean_json_str = clean_json_str[:-3]
clean_json_str = clean_json_str.strip()

try:
    data = json.loads(clean_json_str)
    parsed_plan = ArchitecturalPlan.model_validate(data)
    schema_valid = True
except (json.JSONDecodeError, ValidationError) as e:
    schema_valid = False
    validation_error = str(e)

# Generate Markdown Report
report_path = "PLANNING_REASONING_REPORT.md"
with open(report_path, "w", encoding="utf-8") as f:
    f.write(f"# DeepSeek-V4-Pro Planning & Reasoning Benchmark\n\n")
    f.write(f"### 1. Model & Endpoint Specs\n")
    f.write(f"- **Model:** `{MODEL}`\n")
    f.write(f"- **Inference Provider:** Fireworks AI\n")
    f.write(f"- **Temperature:** `0.2` (Low entropy for deterministic structure)\n\n")
    
    f.write(f"### 2. Performance & Cost Telemetry\n")
    f.write(f"| Metric | Value |\n")
    f.write(f"| :--- | :--- |\n")
    f.write(f"| **Time to First Token (TTFT)** | **{ttft_ms:.2f} ms** |\n")
    f.write(f"| **Generation Duration** | **{generation_duration_s:.2f} s** |\n")
    f.write(f"| **Total Latency** | **{total_duration_s:.2f} s** |\n")
    f.write(f"| **Throughput** | **{throughput_tps:.2f} tokens/s** |\n")
    f.write(f"| **Prompt Tokens** | {prompt_tokens} |\n")
    f.write(f"| **Completion Tokens** | {completion_tokens} |\n")
    f.write(f"| **Estimated Run Cost** | **${total_cost:.5f}** |\n")
    f.write(f"| **Blended Cost / 1k Tokens** | **${cost_per_1k_tokens:.5f}** |\n\n")

    f.write(f"### 3. Reliability & Schema Compliance\n")
    f.write(f"- **Structured JSON Parse:** {'✅ Passed' if schema_valid else '❌ Failed'}\n")
    if not schema_valid:
        f.write(f"- **Validation Error:** `{validation_error}`\n\n")
    else:
        f.write(f"- **Steps Planned:** {len(parsed_plan.steps)}\n")
        f.write(f"- **Critical Path Defined:** `{' -> '.join(parsed_plan.critical_path)}`\n")
        f.write(f"- **Bottlenecks Identified:** {len(parsed_plan.potential_bottlenecks)}\n\n")
        
        f.write(f"### 4. Reasoning Quality Breakdown\n")
        for step in parsed_plan.steps:
            deps = ", ".join(step.dependencies) if step.dependencies else "None"
            f.write(f"#### `{step.step_id}` — {step.title} ({step.department.upper()})\n")
            f.write(f"- **Rationale:** {step.rationale}\n")
            f.write(f"- **Depends On:** `{deps}`\n")
            f.write(f"- **Risk Assessment:** {step.risk_assessment}\n\n")

print(f"\nAudit and evaluation logged to {report_path}")