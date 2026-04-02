from typing import Any, Dict, List, Optional, Tuple
import json
import subprocess


class SimpleHttpResponse:
    def __init__(self, status_code: int, text: str, headers: dict):
        self.status_code = status_code
        self.text = text
        self.headers = headers

    def json(self):
        return json.loads(self.text)


def curl_request(
    url: str,
    *,
    method: str = "GET",
    json_payload: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: float = 8.0,
) -> SimpleHttpResponse:
    marker_status = "__NEXUS_STATUS__:"
    marker_type = "__NEXUS_TYPE__:"
    cmd = [
        "curl",
        "-sS",
        "-X",
        method,
        "--max-time",
        str(max(1, int(timeout))),
    ]
    for key, value in (headers or {}).items():
        cmd.extend(["-H", f"{key}: {value}"])
    if json_payload is not None:
        cmd.extend(["--data-binary", json.dumps(json_payload, ensure_ascii=False)])
    cmd.extend(
        [
            "-w",
            f"\n{marker_status}%{{http_code}}\n{marker_type}%{{content_type}}",
            url,
        ]
    )
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"curl failed with code {proc.returncode}")

    text = proc.stdout
    status_idx = text.rfind(marker_status)
    type_idx = text.rfind(marker_type)
    if status_idx == -1 or type_idx == -1 or type_idx < status_idx:
        raise RuntimeError(f"Unable to parse curl response metadata: {text[-500:]}")

    body = text[:status_idx].rstrip("\n")
    status_line = text[status_idx + len(marker_status):type_idx].strip()
    content_type = text[type_idx + len(marker_type):].strip()
    try:
        status_code = int(status_line)
    except ValueError as exc:
        raise RuntimeError(f"Invalid curl status line: {status_line!r}") from exc

    return SimpleHttpResponse(
        status_code=status_code,
        text=body,
        headers={"content-type": content_type},
    )
