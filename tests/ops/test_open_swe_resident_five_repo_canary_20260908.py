def test_resident_five_repository_mount_order() -> None:
    mounted_repository_ids = (
        "James3014/Nexus-new",
        "James3014/devspace",
        "James3014/nexus-core",
        "James3014/nexus-learning",
        "James3014/nexus-open-swe-runtime",
    )

    assert mounted_repository_ids == (
        "James3014/Nexus-new",
        "James3014/devspace",
        "James3014/nexus-core",
        "James3014/nexus-learning",
        "James3014/nexus-open-swe-runtime",
    )
