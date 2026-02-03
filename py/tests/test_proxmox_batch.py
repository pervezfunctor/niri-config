from __future__ import annotations

from pathlib import Path

import pytest
from _pytest.monkeypatch import MonkeyPatch

import proxmox_batch


def _make_host(**overrides: object) -> proxmox_batch.HostConfig:
    base: dict[str, object] = {
        "name": "prod-a",
        "host": "proxmox-a.example.com",
        "user": "root",
        "identity_file": None,
        "ssh_extra_args": (),
        "guest_user": "root",
        "guest_identity_file": None,
        "guest_ssh_extra_args": (),
        "api_node": None,
        "api_port": 8006,
        "api_insecure": False,
        "api_token_env": "TOKEN_ID",
        "api_secret_env": "TOKEN_SECRET",
        "max_parallel": 2,
        "dry_run": False,
    }
    base.update(overrides)
    return proxmox_batch.HostConfig(**base)  # type: ignore[arg-type]


def test_load_manifest_merges_defaults(tmp_path: Path) -> None:
    manifest = tmp_path / "hosts.toml"
    manifest.write_text(
        """
        [defaults]
        user = "root"
        identity_file = "~/.ssh/proxmox"
        ssh.extra_args = ["-J", "bastion"]
        guest.user = "root"
        guest.identity_file = "~/.ssh/guest-default"
        api.node = "pve"
        dry_run = false

        [[hosts]]
        name = "prod-a"
        host = "proxmox-a.example.com"
        api.token_env = "TOKEN_A"
        api.secret_env = "SECRET_A"

        [[hosts]]
        host = "proxmox-b.example.com"
        user = "admin"
        guest.user = "ops"
        ssh.extra_args = ["-o", "ProxyJump=jumper"]
        api.token_env = "TOKEN_B"
        api.secret_env = "SECRET_B"
        dry_run = true
        """
    )

    defaults, hosts = proxmox_batch.load_manifest(manifest)

    assert defaults.user == "root"
    assert defaults.api_node == "pve"
    assert len(hosts) == 2

    host_a, host_b = hosts
    assert host_a.name == "prod-a"
    assert host_a.user == "root"
    assert host_a.identity_file == str(Path("~/.ssh/proxmox").expanduser())
    assert host_a.guest_identity_file == str(Path("~/.ssh/guest-default").expanduser())

    assert host_b.name == "proxmox-b.example.com"
    assert host_b.user == "admin"
    assert host_b.guest_user == "ops"
    assert host_b.ssh_extra_args == ("-o", "ProxyJump=jumper")
    assert host_b.dry_run is True


def test_missing_token_env_raises() -> None:
    host = _make_host(name="missing-token", api_token_env="TOKEN_ENV", api_secret_env="SECRET_ENV")
    with pytest.raises(proxmox_batch.CredentialError) as excinfo:
        proxmox_batch.resolve_api_credentials(host)
    assert "TOKEN_ENV" in str(excinfo.value)


def test_host_filtering() -> None:
    host_a = _make_host(name="a", host="a.local")
    host_b = _make_host(name="b", host="b.local")
    selected = proxmox_batch.select_hosts([host_a, host_b], ["b"])
    assert selected == [host_b]
    with pytest.raises(ValueError):
        proxmox_batch.select_hosts([host_a, host_b], ["unknown"])


def test_build_args_matches_manifest(monkeypatch: MonkeyPatch) -> None:
    host = _make_host(
        identity_file="~/.ssh/proxmox",
        ssh_extra_args=("-J bastion",),
        guest_identity_file="~/.ssh/guest",
        guest_ssh_extra_args=("-o StrictHostKeyChecking=no",),
        api_node="pve-a",
        api_insecure=True,
        max_parallel=4,
    )
    host.identity_file = str(Path(host.identity_file).expanduser())  # type: ignore[arg-type]
    host.guest_identity_file = str(Path(host.guest_identity_file).expanduser())  # type: ignore[arg-type]

    argv = proxmox_batch.build_host_argv(
        host,
        token="token-value",
        secret="secret-value",
        verbose=True,
        force_dry_run=True,
    )

    assert argv[0] == host.host
    assert "--identity-file" in argv and host.identity_file in argv
    assert argv.count("--ssh-extra-arg") == 1
    assert "--api-node" in argv
    assert "--api-insecure" in argv
    assert "--dry-run" in argv
    assert "--verbose" in argv


@pytest.mark.asyncio
async def test_async_main_handles_mixed_results(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    host_success = _make_host(name="success")
    host_failure = _make_host(name="failure")

    async def fake_run_host(
        host: proxmox_batch.HostConfig,
        *,
        force_dry_run: bool,
        verbose: bool,
    ) -> tuple[bool, str | None]:
        return (host.name == "success", None if host.name == "success" else "boom")

    monkeypatch.setattr(proxmox_batch, "run_host", fake_run_host)
    def fake_load_manifest(_path: Path) -> tuple[proxmox_batch.BatchDefaults, list[proxmox_batch.HostConfig]]:
        return proxmox_batch.BatchDefaults(), [host_success, host_failure]

    monkeypatch.setattr(proxmox_batch, "load_manifest", fake_load_manifest)

    exit_code = await proxmox_batch.async_main(["--config", str(tmp_path / "dummy.toml")])
    assert exit_code == 3


@pytest.mark.asyncio
async def test_async_main_returns_two_on_credential_failures(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    host = _make_host(name="needs-creds")

    async def fake_run_host(
        host: proxmox_batch.HostConfig,
        *,
        force_dry_run: bool,
        verbose: bool,
    ) -> tuple[bool, str | None]:
        raise proxmox_batch.CredentialError(host.name, "TOKEN_ID")

    monkeypatch.setattr(proxmox_batch, "run_host", fake_run_host)
    def fake_load_manifest(_path: Path) -> tuple[proxmox_batch.BatchDefaults, list[proxmox_batch.HostConfig]]:
        return proxmox_batch.BatchDefaults(), [host]

    monkeypatch.setattr(proxmox_batch, "load_manifest", fake_load_manifest)

    exit_code = await proxmox_batch.async_main(["--config", str(tmp_path / "dummy.toml")])
    assert exit_code == 2
