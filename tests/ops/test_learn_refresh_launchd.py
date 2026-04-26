from scripts.ops import learn_refresh_launchd as launchd


def test_build_plist_payload_contains_schedule_and_program_args():
    payload = launchd.build_plist_payload(
        label="com.nexus.learn-refresh.test",
        interval_sec=1800,
        uv_bin="/usr/local/bin/uv",
        topic="openharness",
        benchmark_manifest="docs/research/learn_benchmark_manifest_template.json",
        due_within_days=1,
        pass_threshold=0.7,
        question_count=6,
    )
    assert payload["Label"] == "com.nexus.learn-refresh.test"
    assert payload["StartInterval"] == 1800
    assert payload["WorkingDirectory"].endswith("/nexus")
    assert launchd.REPO_ROOT.exists()
    args = payload["ProgramArguments"]
    assert args[0] == "/usr/local/bin/uv"
    assert "learn_refresh_daemon.py" in " ".join(args)
    assert "--once" in args
    assert "--topic" in args


def test_to_plist_xml_has_required_keys():
    payload = launchd.build_plist_payload(
        label="com.nexus.learn-refresh.test",
        interval_sec=3600,
        uv_bin="uv",
        topic="",
        benchmark_manifest="",
        due_within_days=0,
        pass_threshold=0.6,
        question_count=5,
    )
    xml = launchd._to_plist_xml(payload)
    assert "<key>Label</key>" in xml
    assert "<key>ProgramArguments</key>" in xml
    assert "<key>StartInterval</key>" in xml
