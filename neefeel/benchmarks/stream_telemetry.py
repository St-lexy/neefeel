import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Load .env from project root
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)
load_dotenv()

API_KEY = os.environ.get("FIREWORKS_API_KEY")
BASE_URL = os.environ.get("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1")
MODEL = os.environ.get("NEELFEEL_MODEL", "accounts/fireworks/models/deepseek-v4-flash")

if not API_KEY:
    print("Error: No API key found. Set FIREWORKS_API_KEY in your .env.")
    sys.exit(1)

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

system_prompt = (
    "You are the AI Co-founder of Neefeel. Respond as a sharp, operational venture partner. "
    "Structure your response strictly into three concise sections: "
    "1. Immediate Core Risks (Product & Compliance) "
    "2. Financial Model Breakdown (Unit Economics & Fee Impact) "
    "3. First Go/No-Go Milestone (48-Hour Actionable Test). "
    "Be direct, numeric where possible, and avoid fluff."
)

user_prompt = (
    "We are launching an automated multi-currency cross-border payout engine for remote African engineers. "
    "We plan to absorb fluctuating FX spreads by charging a flat 1.2% transaction fee, route funds through local payment switches, "
    "and offer instant settlement before domestic bank clearing completes."
)

print(f"Connecting to: {BASE_URL}")
print(f"Model: {MODEL}\n")
print("-" * 50)

# Timing telemetry
t_start = time.perf_counter()
t_first_token = None
chunk_count = 0
full_text = []

stream = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
    temperature=0.7,
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
            chunk_count += 1
            full_text.append(delta)
            sys.stdout.write(delta)
            sys.stdout.flush()
    if hasattr(chunk, "usage") and chunk.usage:
        usage_data = chunk.usage

t_end = time.perf_counter()

print("\n" + "-" * 50)

# Telemetry calculations
ttft_ms = (t_first_token - t_start) * 1000 if t_first_token else 0.0
total_duration_s = t_end - t_start
generation_duration_s = (t_end - t_first_token) if t_first_token else total_duration_s

completion_tokens = usage_data.completion_tokens if usage_data else chunk_count
prompt_tokens = usage_data.prompt_tokens if usage_data else len(user_prompt.split())

throughput_tps = completion_tokens / generation_duration_s if generation_duration_s > 0 else 0.0
time_per_1k_tokens_s = (1000.0 / throughput_tps) if throughput_tps > 0 else 0.0

report_markdown = f"""# Fireworks AI Streaming Telemetry Report

### Run Configuration
- **Model:** `{MODEL}`
- **Provider:** Fireworks AI (`{BASE_URL}`)
- **Stream Status:** Successful

### Latency & Throughput Metrics
| Metric | Value |
| :--- | :--- |
| **Time to First Token (TTFT)** | **{ttft_ms:.2f} ms** |
| **Prompt Tokens** | {prompt_tokens} |
| **Completion Tokens** | {completion_tokens} |
| **Total Duration** | {total_duration_s:.2f} s |
| **Generation Duration** | {generation_duration_s:.2f} s |
| **Generation Throughput** | **{throughput_tps:.2f} tokens/s** |
| **Latency per 1k Tokens** | **{time_per_1k_tokens_s:.2f} s** |

### Output Sample
> {"".join(full_text)[:280]}...
"""

# Save report
with open("FIREWORKS_STREAM_REPORT.md", "w", encoding="utf-8") as f:
    f.write(report_markdown)

print(f"\nReport written to FIREWORKS_STREAM_REPORT.md")