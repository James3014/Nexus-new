from pathlib import Path
#!/usr/bin/env python3
import argparse
import json
import os
import sys
import tempfile


def load_handoff(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_gemini_prompt(payload):
    next_action = payload.get("next_action") or "gemini_repair"
    summary = payload.get("summary") or ""
    reasons = payload.get("escalation_reasons") or []
    brief = payload.get("action_brief") or {}
    title = brief.get("title") or "Nexus Next Action"
    instructions = brief.get("instructions") or ""
    context = brief.get("context") or {}

    lines = [
        "[NEXUS HANDOFF]",
        f"Action: {next_action}",
        f"Title: {title}",
    ]

    if summary:
        lines.append(f"Summary: {summary}")
    if reasons:
        lines.append("Reasons: " + ", ".join(reasons))
    if instructions:
        lines.append("")
        lines.append("Instructions:")
        lines.append(instructions)
    if context:
        lines.append("")
        lines.append("Context:")
        for key, value in context.items():
            if value:
                lines.append(f"- {key}: {value}")

    lines.append("")
    lines.append(
        "Deliverable: Return only concrete file edits and the minimal validation commands."
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Convert codex_loop next-action JSON into a Gemini-ready prompt."
    )
    parser.add_argument(
        "--input",
        default=os.getenv("NEXUS_HANDOFF_FILE", os.path.join(tempfile.gettempdir(), "codex_next_action.json")),
        help="Path to codex next action JSON sidecar.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output file path. If omitted, print to stdout.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(
            f"ERROR: handoff file not found: {input_path}. Run codex-loop first to generate {os.getenv('NEXUS_HANDOFF_FILE', os.path.join(tempfile.gettempdir(), 'codex_next_action.json'))}.",
            file=sys.stderr,
        )
        return 2

    payload = load_handoff(args.input)
    prompt = build_gemini_prompt(payload)

    if args.output:
        Path(args.output).write_text(prompt, encoding="utf-8")
    else:
        print(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
