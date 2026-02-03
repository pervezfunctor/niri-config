from __future__ import annotations

from remote_maintenance import build_upgrade_command, determine_package_manager


def test_determine_package_manager_includes_alpine() -> None:
    result = determine_package_manager({"ID": "alpine"})
    assert result == "apk"


def test_build_upgrade_command_for_apk_supports_sudo() -> None:
    command = build_upgrade_command("apk", use_sudo=True)
    assert command == "sudo apk update && sudo apk upgrade"
