"""Preheat the local models the Workforce policy currently admits.

No model tag is hard-coded: the compact-diagnosis model is the worker
nexus-runtime admits for that role (``resolve_default_model``).  When the
policy admits nothing the script reports MODEL_DEFAULT_NOT_ADMITTED and does
not touch Ollama for that role.
"""

import json
import os
import urllib.request

from nexus_runtime.planning.services.model_default_resolution import (
    ModelDefaultNotAdmittedError,
    resolve_default_model,
)

OLLAMA_ENDPOINT = os.getenv("NEXUS_OLLAMA_ENDPOINT", "http://localhost:11434").rstrip("/")
PREHEAT_ROLES = ("compact_diagnosis",)
STATIC_MODELS = ("qwen2.5-coder:7b", "qwen2.5-coder:14b")


def admitted_models() -> list[str]:
    models: list[str] = []
    for role in PREHEAT_ROLES:
        try:
            models.append(resolve_default_model(role))
        except ModelDefaultNotAdmittedError as exc:
            print(f"Skipping role {role}: {exc}")
    return models + [m for m in STATIC_MODELS if m not in models]


def main() -> None:
    for m in admitted_models():
        print(f"Preheating {m}...")
        try:
            req = urllib.request.Request(
                f"{OLLAMA_ENDPOINT}/api/generate",
                data=json.dumps({
                    "model": m,
                    "prompt": "",
                    "stream": False,
                    "keep_alive": "30m",
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=180):
                print(f"Successfully preheated {m}")
        except Exception as e:  # noqa: BLE001 - operator script, report and continue
            print(f"Failed to preheat {m}: {e}")


if __name__ == "__main__":
    main()
