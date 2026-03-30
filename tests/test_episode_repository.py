import json

from nexus.core.episode_repository import EpisodeRepository


def test_episode_repository_append_writes_jsonl(tmp_path):
    repo = EpisodeRepository(str(tmp_path))
    payload = {"task_id": "ep-1", "success": True}
    path = repo.append(payload)

    assert path.exists()
    line = path.read_text(encoding="utf-8").strip()
    assert json.loads(line)["task_id"] == "ep-1"
