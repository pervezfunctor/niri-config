from __future__ import annotations

from dataclasses import dataclass
from unittest import mock

import pytest
from _pytest.monkeypatch import MonkeyPatch

from proxmox_maintenance import SSHSession, build_arg_parser, ensure_valid_host_argument


@pytest.mark.asyncio
async def test_mutable_command_skipped_during_dry_run() -> None:
    session = SSHSession(host="192.0.2.10", user="root", dry_run=True, description="test")
    result = await session.run("echo 'hello'", capture_output=False, mutable=True)
    assert result.returncode == 0
    assert result.stdout == ""


@dataclass
class _FakeProcess:
    returncode: int = 0
    _communicate_called: bool = False

    async def communicate(self) -> tuple[bytes, bytes]:
        self._communicate_called = True
        return b"{}", b""

    @property
    def was_awaited(self) -> bool:
        return self._communicate_called


@pytest.mark.asyncio
async def test_read_command_runs_even_in_dry_run(monkeypatch: MonkeyPatch) -> None:
    session = SSHSession(host="192.0.2.10", user="root", dry_run=True, description="test")
    fake_process = _FakeProcess()

    async def fake_create_subprocess_exec(*_args: object, **_kwargs: object) -> _FakeProcess:
        return fake_process

    monkeypatch.setattr("proxmox_maintenance.asyncio.create_subprocess_exec", fake_create_subprocess_exec)
    result = await session.run("whoami", capture_output=True, mutable=False)
    assert result.stdout == "{}"
    assert result.returncode == 0
    assert fake_process.was_awaited


def test_flag_like_host_triggers_friendly_error(monkeypatch: MonkeyPatch) -> None:
    parser = build_arg_parser()
    mock_error = mock.Mock(side_effect=SystemExit(2))
    monkeypatch.setattr(parser, "error", mock_error)
    with pytest.raises(SystemExit):
        ensure_valid_host_argument(parser, "--help")
    mock_error.assert_called_once()


def test_valid_host_passes_validation() -> None:
    parser = build_arg_parser()
    ensure_valid_host_argument(parser, "proxmox.local")
