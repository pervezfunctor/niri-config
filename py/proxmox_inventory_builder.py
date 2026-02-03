#!/usr/bin/env python3
"""Interactive helper that builds proxmox-hosts manifests from live inventory.

This script performs the following steps:
1. Prompts for (or updates) a host entry in py/proxmox-hosts.toml.
2. Uses the provided API token to discover VMs and containers on the host.
3. Walks through every guest, collecting SSH credentials and verifying access.
4. Installs the configured SSH public key on guests (when needed) using their password.
5. Persists everything back to the TOML manifest so proxmox_maintenance can consume it.

The workflow is intentionally verbose to keep operators informed about what is
happening (network calls, SSH checks, etc.).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import paramiko
import questionary
from questionary import Choice

from proxmox_config_wizard import (
    DefaultsForm,
    HostForm,
    ManifestError,
    ManifestState,
    WizardAbort,
    load_manifest_state,
    write_manifest,
)
from proxmox_maintenance import LXCContainer, ProxmoxAPIClient, ProxmoxAPIError, VirtualMachine, shlex_join
from remote_maintenance import CommandExecutionError, SSHSession

LOGGER = logging.getLogger(__name__)
DEFAULT_CONFIG_PATH = Path(__file__).with_name("proxmox-hosts.toml")
GUEST_INVENTORY_KEY = "guest_inventory"


@dataclass(slots=True)
class APICredentials:
    token_id: str
    token_secret: str


@dataclass(slots=True)
class GuestDiscovery:
    kind: Literal["vm", "ct"]
    identifier: str
    name: str
    status: str
    ip: str | None

    @property
    def label(self) -> str:
        prefix = "VM" if self.kind == "vm" else "CT"
        return f"{prefix} {self.name} ({self.identifier})"


@dataclass(slots=True)
class ManagedGuest:
    discovery: GuestDiscovery
    username: str
    password: str | None
    password_env: str | None
    managed: bool
    ssh_verified: bool
    ssh_key_path: str | None
    notes: str | None
    last_checked: str

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.discovery.kind,
            "id": self.discovery.identifier,
            "name": self.discovery.name,
            "status": self.discovery.status,
            "ip": self.discovery.ip,
            "user": self.username,
            "managed": self.managed,
            "ssh_verified": self.ssh_verified,
            "ssh_key_path": self.ssh_key_path,
            "last_checked": self.last_checked,
        }
        if self.password is not None:
            payload["password"] = self.password
        if self.password_env is not None:
            payload["password_env"] = self.password_env
        if self.notes:
            payload["notes"] = self.notes
        return payload


class InventoryError(RuntimeError):
    """Raised when the wizard cannot continue."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive Proxmox inventory configurator")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to proxmox-hosts.toml (default: %(default)s)",
    )
    parser.add_argument("--host", help="Pre-select an existing host entry by name")
    parser.add_argument("--skip-ssh-checks", action="store_true", help="Skip SSH connectivity tests")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging output")
    return parser.parse_args()


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")


def load_manifest(path: Path) -> ManifestState:
    if path.exists():
        return load_manifest_state(path)
    questionary.print(f"Creating new manifest at {path}", style="bold yellow")
    return ManifestState.empty()


def save_manifest(state: ManifestState, path: Path) -> None:
    write_manifest(state, path)
    questionary.print(f"Updated manifest written to {path}", style="bold green")


def _ask_required_text(message: str, *, default: str | None = None) -> str:
    while True:
        response = questionary.text(message, default=default or "").ask()
        if response is None:
            raise WizardAbort()
        trimmed = response.strip()
        if trimmed:
            return trimmed
        questionary.print("Value is required", style="bold red")


def _ask_optional_text(message: str, *, default: str | None = None) -> str | None:
    response = questionary.text(message, default=default or "").ask()
    if response is None:
        raise WizardAbort()
    trimmed = response.strip()
    return trimmed or default


def _ask_bool(message: str, *, default: bool = True) -> bool:
    response = questionary.confirm(message, default=default).ask()
    if response is None:
        raise WizardAbort()
    return bool(response)


def _ask_password(message: str) -> str:
    response = questionary.password(message).ask()
    if response is None:
        raise WizardAbort()
    return response.strip()


def _ask_list(message: str, *, default_values: Iterable[str] | None = None) -> list[str]:
    default_text = ", ".join(default_values or [])
    response = questionary.text(f"{message} (comma separated)", default=default_text).ask()
    if response is None:
        raise WizardAbort()
    return [item.strip() for item in response.split(",") if item.strip()]


def _slugify_env(name: str) -> str:
    tokens = [token for token in name.replace("-", "_").replace(" ", "_").split("_") if token]
    upper = "_".join(tokens).upper() or "PROXMOX"
    return upper


def select_host(state: ManifestState, requested: str | None) -> tuple[HostForm, bool]:
    if requested:
        for host in state.hosts:
            if host.name == requested:
                return host, False
        questionary.print(f"Host '{requested}' not found, creating a new entry.", style="bold yellow")
    if not state.hosts:
        questionary.print("Manifest has no hosts yet. Let's add one.", style="bold yellow")
        return create_host_form(state.defaults), True
    choices = [Choice(title=f"Update {host.name}", value=host) for host in state.hosts]
    choices.append(Choice(title="Add a new host", value="__new__"))
    response = questionary.select("Select a host entry", choices=choices).ask()
    if response is None:
        raise WizardAbort()
    if response == "__new__":
        new_host = create_host_form(state.defaults)
        state.hosts.append(new_host)
        return new_host, True
    return response, False


def create_host_form(defaults: DefaultsForm) -> HostForm:
    name = _ask_required_text("Host entry name (used as manifest identifier)")
    host = _ask_required_text("Proxmox hostname or IP")
    slug = _slugify_env(name)
    token_env = _ask_required_text(
        "Environment variable for API token ID",
        default=f"{slug}_TOKEN",
    )
    secret_env = _ask_required_text(
        "Environment variable for API token secret",
        default=f"{slug}_SECRET",
    )
    user = _ask_optional_text("Proxmox SSH user", default=defaults.user)
    identity = _ask_optional_text(
        "SSH identity file for host (leave blank to inherit)",
        default=defaults.identity_file,
    )
    guest_user = _ask_optional_text("Default guest SSH user", default=defaults.guest_user)
    guest_identity = _ask_optional_text(
        "Guest SSH identity file (used for VMs/CTs)",
        default=defaults.guest_identity_file,
    )
    ssh_args = _ask_list("Additional ssh args for host connection", default_values=defaults.ssh_extra_args)
    guest_ssh_args = _ask_list(
        "Additional ssh args for guest connections",
        default_values=defaults.guest_ssh_extra_args,
    )
    api_node = _ask_optional_text("Preferred Proxmox node (leave blank for auto)", default=defaults.api_node)
    api_port_str = _ask_optional_text("API port", default=str(defaults.api_port)) or str(defaults.api_port)
    api_port = int(api_port_str)
    api_insecure = _ask_bool("Disable API TLS verification?", default=defaults.api_insecure)
    dry_run = _ask_bool("Enable dry-run for this host by default?", default=defaults.dry_run)
    max_parallel_str = _ask_optional_text("Max parallel guest actions", default=str(defaults.max_parallel))
    max_parallel = int(max_parallel_str) if max_parallel_str else defaults.max_parallel
    host_form = HostForm(
        name=name,
        host=host,
        api_token_env=token_env,
        api_secret_env=secret_env,
        user=user,
        identity_file=identity,
        ssh_extra_args=ssh_args or None,
        guest_user=guest_user,
        guest_identity_file=guest_identity,
        guest_ssh_extra_args=guest_ssh_args or None,
        api_node=api_node,
        api_port=api_port,
        api_insecure=api_insecure,
        max_parallel=max_parallel,
        dry_run=dry_run,
    )
    return host_form


def prompt_api_credentials(host: HostForm) -> APICredentials:
    suggested_id = os.getenv(host.api_token_env, "")
    token_id = _ask_required_text(
        f"API token ID for {host.name} (env {host.api_token_env})",
        default=suggested_id or None,
    )
    token_secret = _ask_password(
        f"API token secret for {host.name} (env {host.api_secret_env})",
    )
    return APICredentials(token_id=token_id, token_secret=token_secret)


def expand_optional_path(value: str | None) -> str | None:
    if not value:
        return None
    return str(Path(value).expanduser())


async def discover_inventory(
    host: HostForm,
    defaults: DefaultsForm,
    creds: APICredentials,
) -> tuple[list[GuestDiscovery], SSHSession | None]:
    host_user = (host.user or defaults.user).strip()
    ssh_identity = expand_optional_path(host.identity_file or defaults.identity_file)
    ssh_extra_args = tuple(host.ssh_extra_args or defaults.ssh_extra_args)
    host_session: SSHSession | None = None
    if host_user and host.host:
        host_session = SSHSession(
            host=host.host,
            user=host_user,
            dry_run=False,
            identity_file=ssh_identity,
            extra_args=ssh_extra_args,
            description=f"proxmox-{host.name}",
        )
    guests: list[GuestDiscovery] = []
    try:
        async with ProxmoxAPIClient(
            host=host.host,
            port=host.api_port or defaults.api_port,
            token_id=creds.token_id,
            token_secret=creds.token_secret,
            node=host.api_node or defaults.api_node,
            verify_ssl=not (host.api_insecure if host.api_insecure is not None else defaults.api_insecure),
        ) as api_client:
            vms = await api_client.list_vms()
            vm_guests = await _discover_vms(api_client, vms)
            guests.extend(vm_guests)
            containers = await api_client.list_containers()
            ct_guests = await _discover_containers(containers, host_session)
            guests.extend(ct_guests)
    except ProxmoxAPIError as exc:
        raise InventoryError(f"Failed to query Proxmox API: {exc}") from exc
    return guests, host_session


async def _discover_vms(api_client: ProxmoxAPIClient, vms: list[VirtualMachine]) -> list[GuestDiscovery]:
    discoveries: list[GuestDiscovery] = []
    for vm in vms:
        ip = None
        try:
            interfaces = await api_client.fetch_vm_interfaces(vm.vmid)
            for interface in interfaces:
                for address in interface.ip_addresses:
                    if address.ip_address_type.lower() == "ipv4":
                        ip = address.ip_address
                        break
                if ip:
                    break
        except ProxmoxAPIError as exc:
            LOGGER.warning("Unable to fetch IP for VM %s: %s", vm.vmid, exc)
        discoveries.append(
            GuestDiscovery(kind="vm", identifier=vm.vmid, name=vm.name, status=vm.status, ip=ip)
        )
    return discoveries


async def _discover_containers(
    containers: list[LXCContainer],
    host_session: SSHSession | None,
) -> list[GuestDiscovery]:
    discoveries: list[GuestDiscovery] = []
    for ct in containers:
        ip = None
        if host_session is not None:
            cmd = shlex_join(["pct", "exec", ct.ctid, "--", "hostname", "-I"])
            try:
                result = await host_session.run(cmd, capture_output=True, mutable=False)
                ip = _extract_ipv4(result.stdout)
            except CommandExecutionError as exc:
                LOGGER.warning("Unable to fetch IP for CT %s: %s", ct.ctid, exc)
        discoveries.append(
            GuestDiscovery(kind="ct", identifier=ct.ctid, name=ct.name, status=ct.status, ip=ip)
        )
    return discoveries


def _extract_ipv4(output: str) -> str | None:
    for token in output.split():
        parts = token.split(".")
        if len(parts) != 4:
            continue
        try:
            if all(0 <= int(part) <= 255 for part in parts):
                return token
        except ValueError:
            continue
    return None


def prompt_public_key_path(host: HostForm, defaults: DefaultsForm) -> Path:
    candidate = host.guest_identity_file or defaults.guest_identity_file
    derived_pub = None
    if candidate:
        private_path = Path(candidate).expanduser()
        if private_path.suffix:
            pub_path = private_path.with_suffix(private_path.suffix + ".pub")
        else:
            pub_path = private_path.with_name(private_path.name + ".pub")
        if pub_path.exists():
            derived_pub = str(pub_path)
    prompt_default = derived_pub or str(Path.home() / ".ssh" / "id_rsa.pub")
    while True:
        response = questionary.text("SSH public key to install on guests", default=prompt_default).ask()
        if response is None:
            raise WizardAbort()
        resolved = Path(response).expanduser()
        if resolved.exists():
            return resolved
        questionary.print(f"File {resolved} does not exist", style="bold red")


def read_public_key_text(path: Path) -> str:
    data = path.read_text(encoding="utf-8").strip()
    if not data:
        raise InventoryError(f"Public key file {path} is empty")
    return data


def load_existing_guest_map(host: HostForm) -> dict[tuple[str, str], dict[str, Any]]:
    extras_raw = host.extras.get(GUEST_INVENTORY_KEY)
    if not isinstance(extras_raw, dict):
        return {}
    extras = cast(dict[str, object], extras_raw)
    entries_obj: list[Any] | None = None
    if "entries" in extras:
        candidate: object = extras["entries"]
        if isinstance(candidate, list):
            entries_obj = cast(list[Any], candidate)
    if entries_obj is None:
        return {}
    entries_list: list[dict[str, Any]] = []
    for raw_item in entries_obj:
        if isinstance(raw_item, dict):
            entries_list.append(cast(dict[str, Any], raw_item))
    mapping: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in entries_list:
        kind_obj = entry.get("kind")
        id_obj = entry.get("id")
        if not isinstance(kind_obj, str) or not isinstance(id_obj, str):
            continue
        mapping[(kind_obj, id_obj)] = entry
    return mapping


async def verify_guest_ssh(
    guest: GuestDiscovery,
    username: str,
    identity_file: str | None,
    extra_args: Iterable[str],
) -> bool:
    if not guest.ip:
        LOGGER.warning("Skipping SSH check for %s: missing IP", guest.label)
        return False
    if not identity_file:
        LOGGER.warning("Skipping SSH check for %s: no guest identity file configured", guest.label)
        return False
    session = SSHSession(
        host=guest.ip,
        user=username,
        dry_run=False,
        identity_file=identity_file,
        extra_args=tuple(extra_args),
        description=guest.label,
    )
    try:
        await session.run("true", capture_output=False, mutable=False, timeout_seconds=15)
    except CommandExecutionError as exc:
        LOGGER.info("SSH to %s failed: %s", guest.label, exc)
        return False
    return True


def install_public_key(
    guest: GuestDiscovery,
    username: str,
    password: str,
    public_key: str,
) -> bool:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=guest.ip or guest.name,
            username=username,
            password=password,
            look_for_keys=False,
            allow_agent=False,
            timeout=25,
        )
        sftp = client.open_sftp()
        try:
            _ensure_remote_dir(sftp, ".ssh", mode=0o700)
            auth_path = ".ssh/authorized_keys"
            _ensure_remote_file(sftp, auth_path, mode=0o600)
            with sftp.open(auth_path, "r") as handle:
                existing = handle.read().decode()
            if public_key not in existing:
                with sftp.open(auth_path, "a") as handle:
                    handle.write((public_key + "\n").encode())
        finally:
            sftp.close()
    except Exception as exc:  # pragma: no cover - depends on remote state
        LOGGER.error("Failed to install key on %s: %s", guest.label, exc)
        return False
    finally:
        client.close()
    return True


def _ensure_remote_dir(sftp: paramiko.SFTPClient, path: str, *, mode: int) -> None:
    try:
        sftp.stat(path)
    except OSError:
        sftp.mkdir(path, mode=mode)
    sftp.chmod(path, mode)


def _ensure_remote_file(sftp: paramiko.SFTPClient, path: str, *, mode: int) -> None:
    try:
        sftp.stat(path)
    except OSError:
        with sftp.open(path, "w") as handle:
            handle.write(b"")
    sftp.chmod(path, mode)


def configure_guests(
    host: HostForm,
    defaults: DefaultsForm,
    discoveries: list[GuestDiscovery],
    public_key_path: Path,
    skip_ssh_checks: bool,
) -> list[ManagedGuest]:
    guest_identity = expand_optional_path(host.guest_identity_file or defaults.guest_identity_file)
    guest_extra_args = tuple(host.guest_ssh_extra_args or defaults.guest_ssh_extra_args)
    public_key_text = read_public_key_text(public_key_path)
    existing_map = load_existing_guest_map(host)
    entries: list[ManagedGuest] = []
    for guest in discoveries:
        existing = existing_map.get((guest.kind, guest.identifier), {})
        manage = bool(existing.get("managed", True))
        manage = _ask_bool(f"Manage {guest.label}?", default=manage)
        username = _ask_required_text(
            f"SSH username for {guest.label}",
            default=existing.get("user") or host.guest_user or defaults.guest_user,
        )
        password_strategy = questionary.select(
            f"How should the password for {guest.label} be stored?",
            choices=[
                Choice("Environment variable reference (recommended)", value="env"),
                Choice("Inline plaintext (discouraged)", value="inline"),
                Choice("Do not store password", value="skip"),
            ],
            default="env"
            if existing.get("password_env")
            else ("inline" if existing.get("password") else "skip"),
        ).ask()
        if password_strategy is None:
            raise WizardAbort()
        password: str | None = None
        password_env: str | None = None
        if password_strategy == "env":
            default_env = existing.get("password_env") or f"{_slugify_env(host.name)}_{guest.identifier}_PASS"
            password_env = _ask_required_text(
                f"Env var for {guest.label} password",
                default=default_env,
            )
            password = os.getenv(password_env) or ""
            if not password:
                provided = _ask_password(
                    f"Enter current password for {guest.label} (used only for SSH key install)",
                )
                password = provided or None
        elif password_strategy == "inline":
            password = _ask_password(f"Password for {guest.label}")
        else:
            password = None
        notes = _ask_optional_text("Notes for this guest (optional)", default=existing.get("notes"))
        ssh_verified = False
        ensure_ssh = not skip_ssh_checks and _ask_bool(
            f"Attempt SSH login for {guest.label} now?", default=True
        )
        if ensure_ssh:
            ssh_verified = asyncio.run(verify_guest_ssh(guest, username, guest_identity, guest_extra_args))
            if not ssh_verified and password:
                install = _ask_bool(
                    f"SSH check failed for {guest.label}. Install {public_key_path} using the password?",
                    default=True,
                )
                if install:
                    if not guest.ip:
                        questionary.print("Cannot install key without IP address", style="bold red")
                    else:
                        success = install_public_key(guest, username, password, public_key_text)
                        if success:
                            ssh_verified = asyncio.run(
                                verify_guest_ssh(guest, username, guest_identity, guest_extra_args)
                            )
        entry = ManagedGuest(
            discovery=guest,
            username=username,
            password=password if password_strategy == "inline" else None,
            password_env=password_env,
            managed=manage,
            ssh_verified=ssh_verified,
            ssh_key_path=str(public_key_path),
            notes=notes,
            last_checked=datetime.now(UTC).isoformat(),
        )
        entries.append(entry)
    return entries


def update_host_inventory(host: HostForm, entries: list[ManagedGuest], public_key_path: Path) -> None:
    host.extras[GUEST_INVENTORY_KEY] = {
        "version": 1,
        "ssh_public_key": str(public_key_path),
        "updated_at": datetime.now(UTC).isoformat(),
        "entries": [entry.to_dict() for entry in entries],
    }


def main() -> int:
    args = parse_args()
    configure_logging(args.verbose)
    manifest_path = Path(args.config).expanduser()
    try:
        state = load_manifest(manifest_path)
        host, created = select_host(state, args.host)
        if created and host not in state.hosts:
            state.hosts.append(host)
        creds = prompt_api_credentials(host)
        discoveries, _ = asyncio.run(discover_inventory(host, state.defaults, creds))
        if not discoveries:
            questionary.print("No guests discovered on this host.", style="bold yellow")
        public_key_path = prompt_public_key_path(host, state.defaults)
        entries = configure_guests(
            host,
            state.defaults,
            discoveries,
            public_key_path,
            args.skip_ssh_checks,
        )
        update_host_inventory(host, entries, public_key_path)
        save_manifest(state, manifest_path)
        questionary.print(
            f"Configured {len(entries)} guests for host {host.name}", style="bold green"
        )
        return 0
    except WizardAbort:
        questionary.print("Aborted by user", style="bold yellow")
        return 1
    except (ManifestError, InventoryError) as exc:
        questionary.print(f"Error: {exc}", style="bold red")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
