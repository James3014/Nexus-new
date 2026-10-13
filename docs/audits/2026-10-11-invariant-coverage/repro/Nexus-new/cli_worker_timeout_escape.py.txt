"""Repro: run_cli_worker enforces timeout by killpg(SIGKILL) on the worker's
process group and then calls process.communicate() with NO timeout. A worker
descendant that calls setsid() escapes the group, keeps the inherited stdout
pipe open, survives the kill, and blocks the controller well past
timeout_seconds (and keeps running after the receipt says TIMED_OUT/killed)."""
import sys, time, tempfile, warnings, os, subprocess
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/user/Nexus-new")
from nexus.executors.cli_worker import CliWorkerRequest, run_cli_worker
marker = tempfile.mktemp()
code = ("import os,time\n"
        "if os.fork()==0:\n"
        "    os.setsid(); time.sleep(6); open(%r,'w').write('survived'); os._exit(0)\n"
        "time.sleep(60)\n") % marker
t = time.monotonic()
res = run_cli_worker(CliWorkerRequest(executable=sys.executable, argv=("-c", code), cwd=tempfile.mkdtemp(), timeout_seconds=1.0))
el = time.monotonic() - t
print(f"timeout_seconds=1.0 status={res.status.value} process_group_killed={res.process_group_killed} actual_wall={el:.1f}s")
time.sleep(0.5)
print("escaped descendant completed its side effect after 'kill':", os.path.exists(marker))
