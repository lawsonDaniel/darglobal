"""Live answer evaluation (uses your OpenRouter quota: about 2-4 requests per question).

    python -m eval.run_qa                      # runs the agent in-process (needs OPENROUTER_API_KEY)
    python -m eval.run_qa --url https://...    # asks a deployed server through /api/chat

Each case in eval/qa_cases.jsonl lists strings the answer must include (all, or any), strings it must not
include, and whether it may contain unverified figures or non-official phone numbers.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from pathlib import Path

import httpx

from app import agent, guards

CASES = Path(__file__).with_name("qa_cases.jsonl")


def judge(case: dict, reply: str, checks: dict) -> list[str]:
    problems = []
    low = reply.lower()
    for s in case.get("include", []):
        if s.lower() not in low:
            problems.append(f"missing '{s}'")
    if case.get("include_any") and not any(s.lower() in low for s in case["include_any"]):
        problems.append(f"missing any of {case['include_any']}")
    for s in case.get("exclude", []):
        if s.lower() in low:
            problems.append(f"should not contain '{s}'")
    if case.get("no_unverified") and checks.get("figures_unverified"):
        problems.append(f"unverified figures {checks['figures_unverified']}")
    if case.get("exclude_phones"):
        allowed = guards.allowed_phone_digits()
        for m in guards.PHONE_RE.finditer(reply):
            if re.sub(r"\D", "", m.group(0)).removeprefix("00") not in allowed:
                problems.append(f"non-official phone {m.group(0)}")
    return problems


async def ask_local(q: str) -> tuple[str, dict, str]:
    res = await agent.answer([{"role": "user", "content": q}])
    return res.reply, res.checks, res.mode


async def ask_remote(url: str, q: str) -> tuple[str, dict, str]:
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(url.rstrip("/") + "/api/chat", json={"message": q})
        j = r.json()
        if r.status_code != 200:
            return f"[HTTP {r.status_code}] {j.get('error')}", {}, "error"
        return j["reply"], j.get("checks", {}), j.get("mode", "?")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--pause", type=float, default=3.0, help="seconds between questions (free-tier rate limits)")
    args = ap.parse_args()
    cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()]
    passed, rows = 0, []
    for i, case in enumerate(cases, 1):
        t0 = time.time()
        try:
            reply, checks, mode = await (ask_remote(args.url, case["q"]) if args.url else ask_local(case["q"]))
        except Exception as e:  # count failures, keep going
            reply, checks, mode = f"[error] {type(e).__name__}: {e}", {}, "error"
        problems = judge(case, reply, checks) if mode != "error" else ["request failed"]
        passed += not problems
        rows.append({"q": case["q"], "ok": not problems, "problems": problems, "mode": mode,
                     "seconds": round(time.time() - t0, 1), "reply": reply[:400]})
        print(f"[{i}/{len(cases)}] {'PASS' if not problems else 'FAIL'} {case['q'][:60]} {problems or ''}")
        await asyncio.sleep(args.pause)
    print(f"\n{passed}/{len(cases)} passed")
    Path("eval/qa_report.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
