#!/usr/bin/env python3
import argparse
import os
import pty
import re
import select
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib import request as urllib_request


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GATEWAY_URL = os.getenv("NEXUS_PILOT_GATEWAY_URL", "http://100.82.155.88:5005")
FRIEND_BIN = Path("/Users/jameschen/.local/bin/nexus-pilot-friend")
PILOT_BIN = Path("/Users/jameschen/.local/bin/nexus-pilot")
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "ops" / "install_nexus_pilot_friend.sh"
DEFAULT_VENV = Path("/Users/jameschen/.nexus-pilot/venv")
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
PROMPT = "NEXUS >"
API_PROMPT = "API Key:"
ACHERON_PROMPT = """🌀 試煉代號：Acheron Paradox —「跨維度記憶扭曲測試」
一、試煉主題
在一個包含 500+ 模組／32萬行跨語言代碼 的虛擬工程中，隱藏一個導致「幽影洩漏 (Spectral Leak)」的現象：
一個 Rust 宏展開導致生成的型別在 Python 側 PyO3 包裝中出現不一致的生命周期表徵，表面上合法編譯，但在特定呼叫序列下會觸發跨語言 AST 鏡像錯誤，變數名稱在 AST 同步樹中被覆寫為幽靈引用。
二、考題任務
1. 檢測階段：
   * 在 10 萬個 AST 節點內即時定位導致幽影洩漏的型別起源。
   * 需要同時追蹤 Rust 宏展開後的 TokenStream 與其 Python 對應的 AST 映射節點。
   * 限時 2 毫秒。
2. 推理階段：
   * 找出該錯誤為何能通過靜態檢查與單元測試。
   * 模擬 unsafe 指標在 RefCell 邊界的隱性越界行為，確保 Reflex Layer 成功檢測並復原此狀態。
3. 修復階段：
   * 動態修改 AST 樹，不重編譯整體，修補生命周期標註與 PyO3 橋接層生成規則，使其在僅修改 4 個 token 的情況下回到穩定狀態。
   * 驗證其後續 memory trace 零洩漏。
三、技術壓測重點
* 跨語言同步：考驗 Nexus-v17 在共享 Rust-Python 記憶體圖譜下能否即時維持一致性。
* 宏展開深潛解析：要求 Rust AST 解構器穿透 macro_rules! 與 proc-macro 階層，全速反推來源位置。
* 選擇性樹修改：測試看見即修改模式在百萬節點規模下之障斷與修復延遲。
* TDD 防爆牆壓力測試：所有自動修補須即刻通過 codex-test scanner 的防護監測。
四、補充場景
/project/
 ├── core/
 │    ├── quantum.rs
 │    ├── memory.rs
 │    └── mirror.py
 ├── util/
 │    ├── entropy.rs
 │    └── bridge.rs
 └── test/test_reflection.py
要求 Nexus 在毫秒級找出 mirror.py 中 RefObject 字段對應的 Rust 型別在宏展開後出錯行，並修復鏈結。"""


def clean_terminal_text(text: str) -> str:
    text = ANSI_RE.sub("", text)
    text = text.replace("\r", "")
    text = text.replace("\x1b", "")
    return text


def mask_secret(text: str, secret: str) -> str:
    if not secret:
        return text
    return text.replace(secret, f"{secret[:4]}***")


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


class PTYSession:
    def __init__(self, cmd: list[str], env: dict[str, str], cwd: str):
        pid, master_fd = pty.fork()
        if pid == 0:  # pragma: no cover - child process
            os.chdir(cwd)
            os.execvpe(cmd[0], cmd, env)
        self.pid = pid
        self.master_fd = master_fd
        self._returncode = None
        self._raw = bytearray()

    def close(self) -> int:
        try:
            os.close(self.master_fd)
        except OSError:
            pass
        return self.poll(wait=True)

    def terminate(self) -> None:
        if self.poll() is None:
            os.kill(self.pid, signal.SIGTERM)
            deadline = time.time() + 3
            while time.time() < deadline:
                if self.poll() is not None:
                    return
                time.sleep(0.1)
            os.kill(self.pid, signal.SIGKILL)
            self.poll(wait=True)

    def poll(self, wait: bool = False):
        if self._returncode is not None:
            return self._returncode
        flags = 0 if wait else os.WNOHANG
        pid, status = os.waitpid(self.pid, flags)
        if pid == 0:
            return None
        self._returncode = os.waitstatus_to_exitcode(status)
        return self._returncode

    def send_text(self, text: str) -> None:
        os.write(self.master_fd, text.encode("utf-8"))

    def send_bytes(self, data: bytes) -> None:
        os.write(self.master_fd, data)

    def snapshot(self) -> str:
        return clean_terminal_text(self._raw.decode("utf-8", errors="ignore"))

    def mark(self) -> int:
        return len(self._raw)

    def segment_from(self, mark: int) -> str:
        return clean_terminal_text(self._raw[mark:].decode("utf-8", errors="ignore"))

    def wait_for(self, needle: str, timeout: float = 20.0) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if needle in self.snapshot():
                return self.snapshot()
            ready, _, _ = select.select([self.master_fd], [], [], 0.2)
            if not ready:
                continue
            chunk = os.read(self.master_fd, 65536)
            if not chunk:
                break
            self._raw.extend(chunk)
        raise TimeoutError(f"Timed out waiting for {needle!r}. Transcript tail:\n{self.snapshot()[-2000:]}")

    def wait_for_after(self, mark: int, needle: str, timeout: float = 20.0) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            segment = self.segment_from(mark)
            if needle in segment:
                return segment
            ready, _, _ = select.select([self.master_fd], [], [], 0.2)
            if not ready:
                continue
            chunk = os.read(self.master_fd, 65536)
            if not chunk:
                break
            self._raw.extend(chunk)
        raise TimeoutError(f"Timed out waiting for {needle!r} after mark. Transcript tail:\n{self.snapshot()[-2000:]}")

    def drain_available(self) -> None:
        while True:
            ready, _, _ = select.select([self.master_fd], [], [], 0)
            if not ready:
                return
            try:
                chunk = os.read(self.master_fd, 65536)
            except OSError:
                return
            if not chunk:
                return
            self._raw.extend(chunk)


def record(results: list[CheckResult], name: str, fn: Callable[[], str]) -> None:
    print(f"[RUN] {name}", flush=True)
    try:
        detail = fn()
        results.append(CheckResult(name=name, ok=True, detail=detail))
        print(f"[PASS] {name} - {detail}", flush=True)
    except Exception as exc:  # pragma: no cover - smoke harness
        results.append(CheckResult(name=name, ok=False, detail=str(exc)))
        print(f"[FAIL] {name} - {exc}", flush=True)
        raise


def run_pytest() -> str:
    proc = subprocess.run(
        ["uv", "run", "pytest", str(REPO_ROOT / "tests" / "pilot_cli"), "-q"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or "passed" not in proc.stdout:
        raise RuntimeError(proc.stdout + "\n" + proc.stderr)
    summary_line = next((line.strip() for line in proc.stdout.splitlines() if " passed" in line), "pilot_cli pytest suite passed")
    return f"pilot_cli pytest suite passed ({summary_line})"


def check_install_script_syntax() -> str:
    proc = subprocess.run(
        ["bash", "-n", str(INSTALL_SCRIPT)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout + "\n" + proc.stderr)
    return "install script syntax ok"


def check_wrapper_target(wrapper: Path, expected_fragment: str) -> str:
    text = wrapper.read_text(encoding="utf-8")
    if expected_fragment not in text:
        raise RuntimeError(text)
    return f"{wrapper.name} points to {expected_fragment}"


def check_prompt_toolkit_in_venv() -> str:
    proc = subprocess.run(
        [
            str(DEFAULT_VENV / "bin" / "python"),
            "-c",
            "import prompt_toolkit; print(prompt_toolkit.__version__)",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout + "\n" + proc.stderr)
    return f"prompt_toolkit available in venv ({proc.stdout.strip()})"


def run_gateway_health(gateway_url: str) -> str:
    with urllib_request.urlopen(f"{gateway_url}/status", timeout=5.0) as response:
        body = response.read().decode("utf-8", errors="ignore")
    if "ok" not in body.lower() and "status" not in body.lower():
        raise RuntimeError(body)
    return f"gateway reachable at {gateway_url}/status"


def _friend_env(gateway_url: str) -> dict[str, str]:
    env = os.environ.copy()
    env["NEXUS_PILOT_GATEWAY_URL"] = gateway_url
    env["NEXUS_PILOT_PROVIDER"] = "Gemini"
    env["NEXUS_PILOT_MODEL"] = "gemini-2.5-flash"
    env["TERM"] = "xterm-256color"
    return env


def start_friend_session(api_key: str, tenant: str, gateway_url: str) -> PTYSession:
    session = PTYSession([str(FRIEND_BIN), tenant], env=_friend_env(gateway_url), cwd=str(REPO_ROOT))
    session.wait_for(API_PROMPT, timeout=10.0)
    session.send_text(api_key + "\r")
    text = session.wait_for(PROMPT, timeout=20.0)
    if "Provider: Gemini" not in text or f"Tenant: {tenant}" not in text:
        raise RuntimeError(text[-2000:])
    return session


def _assert_structured_answer(segment: str) -> None:
    required = ["結論：", "根因：", "為何會漏過：", "修補策略："]
    if "Initial diagnosis" in segment:
        raise RuntimeError(segment[-4000:])
    if any(label not in segment for label in required):
        raise RuntimeError(segment[-4000:])


def _send_bracketed_paste(
    session: PTYSession,
    prompt_text: str,
    chunk_size: int = 4096,
    pause: float = 0.005,
) -> None:
    payload = b"\x1b[200~" + prompt_text.encode("utf-8") + b"\x1b[201~\r"
    sent = 0
    os.set_blocking(session.master_fd, False)
    try:
        while sent < len(payload):
            try:
                written = os.write(session.master_fd, payload[sent : sent + chunk_size])
                sent += written
            except BlockingIOError:
                written = 0
            session.drain_available()
            if sent < len(payload):
                time.sleep(pause)
    finally:
        os.set_blocking(session.master_fd, True)
    session.drain_available()


def _ask_acheron_bracketed(session: PTYSession, prompt_text: str) -> str:
    mark = session.mark()
    _send_bracketed_paste(session, prompt_text)
    segment = session.wait_for_after(mark, PROMPT, timeout=40.0)
    _assert_structured_answer(segment)
    return segment


def _ask_acheron_bracketed_chunks(session: PTYSession, prompt_text: str, chunk_size: int) -> str:
    mark = session.mark()
    _send_bracketed_paste(session, prompt_text, chunk_size=chunk_size, pause=0.005)
    segment = session.wait_for_after(mark, PROMPT, timeout=40.0)
    _assert_structured_answer(segment)
    return segment


def _ask_acheron_after_escape_clear(session: PTYSession, prompt_text: str) -> str:
    session.send_text("garbage_to_clear")
    time.sleep(0.3)
    session.send_bytes(b"\x1b")
    time.sleep(0.3)
    return _ask_acheron_bracketed(session, prompt_text)


def _normalize_crlf(text: str) -> str:
    return text.replace("\n", "\r\n")


def _with_extra_blank_line(text: str) -> str:
    return text.replace("3. 修復階段：", "\n3. 修復階段：", 1)


def _run_session_method(
    api_key: str,
    tenant: str,
    gateway_url: str,
    method_name: str,
    runner: Callable[[PTYSession], str],
    transcripts: list[str],
) -> CheckResult:
    session = start_friend_session(api_key, tenant, gateway_url)
    try:
        detail = runner(session)
        result = CheckResult(method_name, True, detail)
    finally:
        transcripts.append(f"## {method_name}\n\n{mask_secret(session.snapshot(), api_key)}\n")
        if session.poll() is None:
            session.terminate()
    return result


def _build_local_repo_fixture() -> tuple[str, str]:
    root = Path(tempfile.mkdtemp(prefix="nexus-pilot-smoke-"))
    work_dir = root / "repo-work"
    origin_dir = root / "repo-origin.git"
    work_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(work_dir), check=True, capture_output=True, text=True)
    (work_dir / "app.py").write_text('print("hi")\n', encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=str(work_dir), check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "user.name=Smoke", "-c", "user.email=smoke@example.com", "commit", "-m", "init"],
        cwd=str(work_dir),
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(["git", "clone", "--bare", str(work_dir), str(origin_dir)], check=True, capture_output=True, text=True)
    return str(work_dir), str(origin_dir)


def check_prompt_toolkit_paste(prompt_text: str, chunk_size: int = 4096) -> str:
    helper = r"""
import sys
import threading
import time
from prompt_toolkit import PromptSession
from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.output import DummyOutput

text = open(sys.argv[1], "r", encoding="utf-8").read()
chunk_size = int(sys.argv[2])
bindings = KeyBindings()

@bindings.add("escape")
def _clear(event):
    event.app.current_buffer.reset()

with create_pipe_input() as pipe:
    session = PromptSession(
        multiline=False,
        key_bindings=bindings,
        wrap_lines=True,
        input=pipe,
        output=DummyOutput(),
    )
    result = {}
    def worker():
        result["value"] = session.prompt("NEXUS > ")
    thread = threading.Thread(target=worker)
    thread.start()
    time.sleep(0.1)
    pipe.send_text("\x1b[200~")
    for idx in range(0, len(text), chunk_size):
        pipe.send_text(text[idx: idx + chunk_size])
    pipe.send_text("\x1b[201~")
    pipe.send_text("\r")
    thread.join(timeout=5)
    if result.get("value") != text:
        raise SystemExit(f"mismatch:{result.get('value')!r}")
print("OK")
"""
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tmp:
        tmp.write(prompt_text)
        tmp_path = tmp.name
    try:
        proc = subprocess.run(
            [
                str(DEFAULT_VENV / "bin" / "python"),
                "-c",
                helper,
                tmp_path,
                str(chunk_size),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    if proc.returncode != 0 or "OK" not in proc.stdout:
        raise RuntimeError(proc.stdout + "\n" + proc.stderr)
    return f"prompt_toolkit accepted {len(prompt_text)} chars with chunk_size={chunk_size}"


def _assert_gemini_answer(answer: str) -> None:
    required = ["結論：", "根因：", "為何會漏過：", "修補策略："]
    if any(label not in answer for label in required):
        raise RuntimeError(answer[-4000:])


def check_gemini_acheron(api_key: str, prompt_text: str, model: str = "gemini-2.5-flash") -> str:
    sys.path.insert(0, str(REPO_ROOT))
    from nexus.pilot_cli.gemini_client import chat_via_gemini_api
    from nexus.pilot_cli.session import PilotSession

    session = PilotSession(
        tenant_id="pilot_a",
        provider="Gemini",
        model=model,
        api_key=api_key,
    )
    answer = chat_via_gemini_api(session, prompt_text)
    _assert_gemini_answer(answer)
    return "Gemini returned structured 4-section Acheron answer"


def run_friend_checks(api_key: str, tenant: str, gateway_url: str, report_dir: Path) -> list[CheckResult]:
    checks: list[CheckResult] = []
    transcripts: list[str] = []
    local_workspace, repo_origin = _build_local_repo_fixture()
    clone_target = str(Path(tempfile.mkdtemp(prefix="nexus-pilot-clone-target-")) / "repo-clone")
    methods: list[tuple[str, Callable[[], str]]] = [
        ("acheron_method_01_prompt_toolkit_exact", lambda: check_prompt_toolkit_paste(ACHERON_PROMPT)),
        ("acheron_method_02_prompt_toolkit_crlf", lambda: check_prompt_toolkit_paste(_normalize_crlf(ACHERON_PROMPT))),
        ("acheron_method_03_prompt_toolkit_extra_blank_line", lambda: check_prompt_toolkit_paste(_with_extra_blank_line(ACHERON_PROMPT))),
        ("acheron_method_04_prompt_toolkit_256_chunks", lambda: check_prompt_toolkit_paste(ACHERON_PROMPT, chunk_size=256)),
        ("acheron_method_05_prompt_toolkit_17_chunks", lambda: check_prompt_toolkit_paste(ACHERON_PROMPT, chunk_size=17)),
        ("acheron_method_06_gemini_exact", lambda: check_gemini_acheron(api_key, ACHERON_PROMPT)),
        ("acheron_method_07_gemini_crlf", lambda: check_gemini_acheron(api_key, _normalize_crlf(ACHERON_PROMPT))),
        ("acheron_method_08_gemini_extra_blank_line", lambda: check_gemini_acheron(api_key, _with_extra_blank_line(ACHERON_PROMPT))),
        ("acheron_method_09_gemini_prefixed_context", lambda: check_gemini_acheron(api_key, "請先做快速壓縮分析，再回答：\n" + ACHERON_PROMPT)),
        ("acheron_method_10_gemini_repeat_same_prompt", lambda: (check_gemini_acheron(api_key, ACHERON_PROMPT), check_gemini_acheron(api_key, ACHERON_PROMPT), "Gemini answered the same Acheron prompt twice")[-1]),
    ]

    def run_with_mark(session: PTYSession, command: str, timeout: float = 20.0, idle: float = 1.0) -> str:
        mark = session.mark()
        session.send_text(command)
        deadline = time.time() + timeout
        last_activity = time.time()
        saw_output = False
        while time.time() < deadline:
            ready, _, _ = select.select([session.master_fd], [], [], 0.2)
            if ready:
                try:
                    chunk = os.read(session.master_fd, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                session._raw.extend(chunk)
                last_activity = time.time()
                saw_output = True
                continue
            if saw_output and time.time() - last_activity >= idle:
                return session.segment_from(mark)
        segment = session.segment_from(mark)
        if segment:
            return segment
        raise TimeoutError(f"Timed out waiting for command output: {command!r}")

    def run_until_contains(session: PTYSession, command: str, needle: str, timeout: float = 30.0) -> str:
        mark = session.mark()
        session.send_text(command)
        segment = session.wait_for_after(mark, needle, timeout=timeout)
        time.sleep(0.5)
        session.drain_available()
        return session.segment_from(mark)

    for name, runner in methods:
        record(checks, name, runner)

    def live_startup(session: PTYSession) -> str:
        snapshot = session.snapshot()
        if "Nexus Singularity" not in snapshot or "Mode: FAST" not in snapshot:
            raise RuntimeError(snapshot[-2000:])
        return "friend CLI session started cleanly"

    def live_status_mask(session: PTYSession) -> str:
        segment = run_until_contains(session, "/status\r", "API Key:", timeout=10.0)
        if "API Key: AIza***" not in segment:
            raise RuntimeError(segment[-2000:])
        return "status output masks API key"

    def live_govern(session: PTYSession) -> str:
        segment = run_until_contains(session, "幫我修這個 bug\r", "Governance task detected.", timeout=20.0)
        if "Governance task detected." not in segment:
            raise RuntimeError(segment[-2000:])
        govern_segment = run_until_contains(session, "/govern\r", "Battle Mode engaged.", timeout=20.0)
        if "Battle Mode engaged." not in govern_segment or "Task:" not in govern_segment:
            raise RuntimeError(govern_segment[-2000:])
        return "govern command produced battle task"

    def live_mount_local(session: PTYSession) -> str:
        segment = run_until_contains(session, f"/mount {local_workspace}\r", "Mounted workspace:", timeout=10.0)
        if f"Mounted workspace: {local_workspace}" not in segment:
            raise RuntimeError(segment[-2000:])
        return "local workspace mounted"

    def live_clone_local(session: PTYSession) -> str:
        segment = run_until_contains(session, f"/clone {repo_origin} {clone_target}\r", "Mounted workspace:", timeout=30.0)
        if "Cloned repo to" not in segment or "Mounted workspace:" not in segment:
            raise RuntimeError(segment[-3000:])
        return "local repo origin cloned and mounted"

    def live_mount_repo_warn(session: PTYSession) -> str:
        segment = run_until_contains(
            session,
            "/mount https://github.com/example/project.git\r",
            "GitHub URL detected. Use /clone <repo-url> to fetch it locally first.",
            timeout=10.0,
        )
        if "GitHub URL detected. Use /clone <repo-url> to fetch it locally first." not in segment:
            raise RuntimeError(segment[-2000:])
        return "repo URL mount warns to use /clone"

    def live_reset(session: PTYSession) -> str:
        run_until_contains(session, f"/mount {local_workspace}\r", "Mounted workspace:", timeout=10.0)
        run_until_contains(session, "幫我修這個 bug\r", "Governance task detected.", timeout=20.0)
        run_until_contains(session, "/govern\r", "Battle Mode engaged.", timeout=20.0)
        reset_segment = run_until_contains(session, "/reset\r", "Context reset.", timeout=10.0)
        if "Context reset." not in reset_segment:
            raise RuntimeError(reset_segment[-2000:])
        status_segment = run_until_contains(session, "/status\r", "API Key:", timeout=10.0)
        if "Workspace: (not set)" not in status_segment or "Mode: FAST" not in status_segment or "Active Task: (none)" not in status_segment:
            raise RuntimeError(status_segment[-2000:])
        return "reset clears workspace and battle task state"

    live_methods: list[tuple[str, str, Callable[[PTYSession], str]]] = [
        ("pilot_a_startup", "pilot_a", live_startup),
        ("pilot_a_status_masks_api_key", "pilot_a", live_status_mask),
        ("pilot_a_govern_task", "pilot_a", live_govern),
        ("pilot_a_mount_local_workspace", "pilot_a", live_mount_local),
        ("pilot_a_clone_local_repo_origin", "pilot_a", live_clone_local),
        ("pilot_a_mount_repo_url_warns_use_clone", "pilot_a", live_mount_repo_warn),
        ("pilot_a_reset_clears_context", "pilot_a", live_reset),
        ("pilot_b_startup", "pilot_b", live_startup),
        ("pilot_b_status_masks_api_key", "pilot_b", live_status_mask),
        ("pilot_b_govern_task", "pilot_b", live_govern),
    ]

    for name, live_tenant, runner in live_methods:
        print(f"[RUN] {name}", flush=True)
        result = _run_session_method(api_key, live_tenant, gateway_url, name, runner, transcripts)
        checks.append(result)
        print(f"[PASS] {name} - {result.detail}", flush=True)

    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "pilot_cli_20_checks_transcript.txt").write_text(
        "\n".join(transcripts),
        encoding="utf-8",
    )
    return checks


def write_report(report_path: Path, results: list[CheckResult]) -> None:
    lines = ["# Nexus Pilot CLI 20-Check Report", ""]
    for index, result in enumerate(results, start=1):
        status = "PASS" if result.ok else "FAIL"
        lines.append(f"{index}. [{status}] {result.name}")
        lines.append(f"   - {result.detail}")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--tenant", default="pilot_a")
    parser.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL)
    parser.add_argument(
        "--report",
        default=str(REPO_ROOT / "logs" / "pilot" / "pilot_cli_20_checks_report.md"),
    )
    args = parser.parse_args()

    results: list[CheckResult] = []
    report_path = Path(args.report)
    report_dir = report_path.parent

    record(results, "install-script-syntax", check_install_script_syntax)
    record(results, "friend-wrapper-target", lambda: check_wrapper_target(FRIEND_BIN, str(DEFAULT_VENV / "bin" / "nexus-pilot-friend")))
    record(results, "pilot-wrapper-target", lambda: check_wrapper_target(PILOT_BIN, str(DEFAULT_VENV / "bin" / "nexus-pilot")))
    record(results, "prompt-toolkit-in-venv", check_prompt_toolkit_in_venv)
    record(results, "pytest-suite", run_pytest)
    record(results, "gateway-health", lambda: run_gateway_health(args.gateway_url))
    results.extend(run_friend_checks(args.api_key, args.tenant, args.gateway_url, report_dir))

    if len(results) != 26:
        raise RuntimeError(f"expected 26 checks, got {len(results)}")

    write_report(report_path, results)
    print(f"Wrote smoke report to {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
