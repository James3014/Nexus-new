from nexus.services.local_heal.task_manifest import local_heal_20_task_manifest


def test_local_heal_20_manifest_has_fixed_midterm_shape():
    manifest = local_heal_20_task_manifest()

    assert len(manifest) == 20
    assert len({task.task_id for task in manifest}) == 20

    astropy_tasks = [task for task in manifest if task.family == "astropy"]
    concurrency_tasks = [task for task in manifest if task.family == "concurrency"]

    assert [task.swe_index for task in astropy_tasks] == list(range(10))
    assert all(task.kind == "swebench" for task in astropy_tasks)
    assert all(task.env_profile == "astropy-legacy" for task in astropy_tasks)

    assert [task.task_id for task in concurrency_tasks] == [
        "deepswe-task4",
        "deepswe-task5",
        "deepswe-task6",
        "deepswe-task7",
        "deepswe-task8",
        "deepswe-task9",
        "deepswe-task10",
        "django-31505",
        "asyncio-barrier",
        "free-threading-weakref",
    ]
    assert all(task.kind == "local_concurrency" for task in concurrency_tasks)
    assert all(task.env_profile == "python-default" for task in concurrency_tasks)
    assert all(task.local_path for task in concurrency_tasks)
