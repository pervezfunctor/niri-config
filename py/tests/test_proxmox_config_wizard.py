import tomllib
from pathlib import Path

import pytest

from proxmox_config_wizard import (
    DefaultsForm,
    HostForm,
    ManifestError,
    ManifestState,
    load_manifest_state,
    validate_state,
    write_manifest,
)

SAMPLE_MANIFEST = """
title = "primary cluster"

[defaults]
user = "root"
guest_user = "admin"
identity_file = "~/.ssh/proxmox"
ssh_extra_args = ["-J", "bastion"]
[defaults.custom]
notes = "keep me"

[[hosts]]
name = "alpha"
host = "alpha.example.com"
api.token_env = "PROXMOX_ALPHA_TOKEN"
api.secret_env = "PROXMOX_ALPHA_SECRET"
ssh_extra_args = ["-o", "StrictHostKeyChecking=no"]
metadata = { role = "db" }

[[hosts]]
host = "beta.example.com"
api.token_env = "PROXMOX_BETA_TOKEN"
api.secret_env = "PROXMOX_BETA_SECRET"
"""


def _write_sample(path: Path) -> Path:
    path.write_text(SAMPLE_MANIFEST, encoding="utf-8")
    return path


def test_load_manifest_state_preserves_extras(tmp_path: Path) -> None:
    manifest_path = _write_sample(tmp_path / "proxmox-hosts.toml")
    state = load_manifest_state(manifest_path)

    assert state.top_level_extras["title"] == "primary cluster"
    assert state.defaults.user == "root"
    assert state.defaults.extras["custom"]["notes"] == "keep me"
    assert state.defaults.ssh_extra_args == ["-J", "bastion"]

    assert len(state.hosts) == 2
    alpha = state.hosts[0]
    assert alpha.name == "alpha"
    assert alpha.ssh_extra_args == ["-o", "StrictHostKeyChecking=no"]
    assert alpha.extras["metadata"]["role"] == "db"

    beta = state.hosts[1]
    assert beta.name == "beta.example.com"
    assert beta.api_token_env == "PROXMOX_BETA_TOKEN"


def test_write_manifest_round_trip(tmp_path: Path) -> None:
    manifest_path = _write_sample(tmp_path / "proxmox-hosts.toml")
    state = load_manifest_state(manifest_path)

    state.defaults.user = "admin"
    state.defaults.api_node = "pve-alpha"
    state.hosts[0].api_port = 9000
    state.hosts[0].api_insecure = True

    output_path = tmp_path / "out.toml"
    write_manifest(state, output_path)

    data = tomllib.loads(output_path.read_text(encoding="utf-8"))
    assert data["title"] == "primary cluster"
    assert data["defaults"]["user"] == "admin"
    assert data["defaults"]["api_node"] == "pve-alpha"
    assert len(data["hosts"]) == 2
    assert data["hosts"][0]["api_port"] == 9000
    assert data["hosts"][0]["api_insecure"] is True
    assert data["hosts"][0]["metadata"]["role"] == "db"


def test_validate_state_rejects_duplicate_names() -> None:
    defaults = DefaultsForm()
    host_a = HostForm(
        name="alpha",
        host="alpha.example.com",
        api_token_env="TOKEN_A",
        api_secret_env="SECRET_A",
    )
    host_b = HostForm(
        name="alpha",
        host="alpha2.example.com",
        api_token_env="TOKEN_B",
        api_secret_env="SECRET_B",
    )
    state = ManifestState(defaults=defaults, hosts=[host_a, host_b])

    with pytest.raises(ManifestError):
        validate_state(state)
