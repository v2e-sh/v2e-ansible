#!/usr/bin/env python3
"""model-router: right-size the Claude model tier per task.

Stdlib-only (mirrors the vault CLI convention) so it runs anywhere agent-run
does, with no pip install step. See SKILL.md for the policy this implements.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

TIER_ORDER = ["haiku", "sonnet", "opus"]
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
DEFAULT_LOG_PATH = Path.home() / ".local" / "state" / "model-router" / "decisions.jsonl"


def load_config(path: str | Path | None = None) -> dict:
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def check_hard_floor(task_text: str, config: dict) -> dict | None:
    for rule in config["hard_floor_rules"]:
        if re.search(rule["pattern"], task_text):
            return rule
    return None


def build_classifier_prompt(task_text: str) -> str:
    return (
        "Classify the complexity/risk of the following task into exactly one "
        "tier: HAIKU (mechanical, low-risk: typo fixes, renames, formatting, "
        "boilerplate, copy edits), SONNET (moderate: normal feature work, "
        "routine multi-file changes, ambiguous-but-not-risky work), or OPUS "
        "(complex or critical: tricky logic, wide blast radius, judgment-heavy "
        "or high-stakes work).\n"
        "If you are unsure between two adjacent tiers, choose the HIGHER "
        "tier.\n"
        "Respond with exactly one word: HAIKU, SONNET, or OPUS. No other "
        "text.\n\n"
        f"Task: {task_text}"
    )


def _call_claude_haiku(prompt: str, config: dict) -> str:
    model = config["tiers"]["haiku"]
    result = subprocess.run(
        ["claude", "-p", prompt, "--model", model],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return result.stdout


def triage(task_text: str, config: dict, classifier=None) -> tuple[str, str]:
    classifier = classifier or _call_claude_haiku
    prompt = build_classifier_prompt(task_text)
    try:
        raw = classifier(prompt, config).strip().upper()
    except Exception as exc:  # noqa: BLE001 - any classifier failure is a fallback signal
        return config["default_tier"], f"triage call failed ({exc}); defaulted to {config['default_tier']}"
    for tier in ("HAIKU", "SONNET", "OPUS"):
        if tier in raw:
            return tier.lower(), f"haiku triage classified {tier.lower()}"
    return config["default_tier"], f"triage returned unparseable '{raw[:60]}'; defaulted to {config['default_tier']}"


def clamp_tier(tier: str, escalate_by: int, max_escalations: int) -> tuple[str, int]:
    applied = max(0, min(escalate_by, max_escalations))
    idx = min(TIER_ORDER.index(tier) + applied, len(TIER_ORDER) - 1)
    return TIER_ORDER[idx], applied


def route(task_text: str, retry: int = 0, config: dict | None = None, classifier=None) -> dict:
    config = config or load_config()
    floor = check_hard_floor(task_text, config)
    max_esc = config.get("max_escalations", 2)

    if floor:
        base_tier = "opus"
        final_tier = "opus"
        reason = f"hard-floor: {floor['reason']} (rule={floor['id']})"
    else:
        base_tier, reason = triage(task_text, config, classifier)
        final_tier, applied = clamp_tier(base_tier, retry, max_esc)
        if applied:
            reason += f"; escalated +{applied} tier(s) after {retry} retr{'y' if retry == 1 else 'ies'}"
            if retry > max_esc:
                reason += f" (capped at max_escalations={max_esc})"

    return {
        "task": task_text[:200],
        "retry": retry,
        "hard_floor": floor["id"] if floor else None,
        "base_tier": base_tier,
        "tier": final_tier,
        "model": config["tiers"][final_tier],
        "reason": reason,
    }


def log_decision(decision: dict, log_path: str | Path) -> None:
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = dict(decision)
    entry["timestamp"] = dt.datetime.now(dt.timezone.utc).isoformat()
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="router.py")
    sub = parser.add_subparsers(dest="command", required=True)

    route_p = sub.add_parser("route", help="classify a task into a model tier")
    route_p.add_argument("task")
    route_p.add_argument("--retry", type=int, default=0)
    route_p.add_argument("--config", default=None)
    route_p.add_argument("--log", default=None)
    route_p.add_argument("--no-log", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "route":
        config = load_config(args.config)
        decision = route(args.task, retry=args.retry, config=config)
        if not args.no_log:
            log_path = args.log or os.environ.get("MODEL_ROUTER_LOG") or DEFAULT_LOG_PATH
            log_decision(decision, log_path)
        print(json.dumps(decision))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
