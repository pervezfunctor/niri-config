#!/usr/bin/env python3
"""Interactive wizard for managing proxmox_batch manifests."""
from __future__ import annotations

import argparse
import contextlib
import copy
import logging
import os
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import questionary
import tomli_w

import proxmox_batch
from proxmox_batch import ManifestError

try:  # Python 3.11+ builtin
    import tomllib
except ModuleNotFoundError as exc:  # pragma: no cover - Python 3.12+ required elsewhere
    raise RuntimeError("Python 3.11+ is required") from exc

LOGGER = logging.getLogger(__name__)


def _str_list_factory() -> list[str]:
    return []


def _extras_factory() -> dict[str, Any]:
    return {}


@dataclass
class DefaultsForm:
    user: str = "root"
    guest_user: str = "root"
    identity_file: str | None = None
    guest_identity_file: str | None = None
    ssh_extra_args: list[str] = field(default_factory=_str_list_factory)
    guest_ssh_extra_args: list[str] = field(default_factory=_str_list_factory)
    api_node: str | None = None
    api_port: int = 8006
    api_insecure: bool = False
    max_parallel: int = 2
    dry_run: bool = False
    extras: dict[str, Any] = field(default_factory=_extras_factory)


@dataclass
class HostForm:
    name: str
    host: str
    api_token_env: str
    api_secret_env: str
    user: str | None = None
    identity_file: str | None = None
    ssh_extra_args: list[str] | None = None
    guest_user: str | None = None
    guest_identity_file: str | None = None
    guest_ssh_extra_args: list[str] | None = None
    api_node: str | None = None
    api_port: int | None = None
    api_insecure: bool | None = None
    max_parallel: int | None = None
    dry_run: bool | None = None
    extras: dict[str, Any] = field(default_factory=_extras_factory)


@dataclass
class ManifestState:
    defaults: DefaultsForm
    hosts: list[HostForm]
    top_level_extras: dict[str, Any] = field(default_factory=_extras_factory)

    @classmethod
    def empty(cls) -> ManifestState:
        return cls(defaults=DefaultsForm(), hosts=[], top_level_extras={})


class WizardAbort(RuntimeError):
    """Raised when the user aborts via Ctrl+C/ESC inside Questionary."""


def _to_mutable(value: Any) -> Any:
    if isinstance(value, dict):
        dict_value = cast(dict[str, Any], value)
        result: dict[str, Any] = {}
        for key, item in dict_value.items():
            result[key] = _to_mutable(item)
        return result
    if isinstance(value, list):
        return [_to_mutable(item) for item in cast(list[Any], value)]
    return value


def _pop_path(mapping: dict[str, Any], path: str) -> tuple[Any | None, bool]:
    segments = path.split(".")
    parents: list[tuple[dict[str, Any], str]] = []
    current = mapping
    for segment in segments[:-1]:
        next_value = current.get(segment)
        if not isinstance(next_value, dict):
            return None, False
        parents.append((current, segment))
        current = cast(dict[str, Any], next_value)
    last = segments[-1]
    if last not in current:
        return None, False
    result = current.pop(last)
    for parent, key in reversed(parents):
        child = parent.get(key)
        if isinstance(child, dict) and not child:
            parent.pop(key)
        else:
            break
    return result, True


def _set_path(mapping: dict[str, Any], path: str, value: Any) -> None:
    segments = path.split(".")
    current = mapping
    for segment in segments[:-1]:
        next_value = current.get(segment)
        if not isinstance(next_value, dict):
            next_value = {}
            current[segment] = next_value
        current = cast(dict[str, Any], next_value)
    current[segments[-1]] = value


def _expect_type(value: Any, label: str, validator: Callable[[Any], bool], type_name: str) -> Any:
    if validator(value):
        return value
    raise ManifestError(f"Expected {type_name} for '{label}', got {type(value).__name__}")


def _expect_str(value: Any, label: str) -> str:
    return _expect_type(value, label, lambda v: isinstance(v, str), "string")


def _expect_bool(value: Any, label: str) -> bool:
    return _expect_type(value, label, lambda v: isinstance(v, bool), "boolean")


def _expect_int(value: Any, label: str) -> int:
    return _expect_type(value, label, lambda v: isinstance(v, int), "integer")


def _expect_str_list(value: Any, label: str) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in cast(list[Any], value)]
    raise ManifestError(f"Expected string list for '{label}', got {type(value).__name__}")


def _extract(mapping: dict[str, Any], *paths: str) -> tuple[Any | None, bool, str | None]:
    for path in paths:
        value, found = _pop_path(mapping, path)
        if found:
            return value, True, path
    return None, False, None


def _load_defaults(defaults_raw: dict[str, Any]) -> DefaultsForm:
    working = cast(dict[str, Any], _to_mutable(defaults_raw))
    user_value, found, _ = _extract(working, "user")
    user = _expect_str(user_value, "defaults.user") if found else "root"

    guest_user_value, found, _ = _extract(working, "guest_user", "guest.user")
    guest_user = _expect_str(guest_user_value, "defaults.guest_user") if found else "root"

    identity_value, found, _ = _extract(working, "identity_file", "ssh.identity_file")
    identity_file = _expect_str(identity_value, "defaults.identity_file") if found else None

    guest_identity_value, found, _ = _extract(
        working,
        "guest_identity_file",
        "guest.identity_file",
    )
    guest_identity_file = (
        _expect_str(guest_identity_value, "defaults.guest_identity_file") if found else None
    )

    ssh_extra_value, found, _ = _extract(working, "ssh_extra_args", "ssh.extra_args")
    ssh_extra_args = _expect_str_list(ssh_extra_value, "defaults.ssh_extra_args") if found else []

    guest_ssh_value, found, _ = _extract(
        working,
        "guest_ssh_extra_args",
        "guest.ssh_extra_args",
        "guest.ssh.extra_args",
    )
    guest_ssh_extra_args = (
        _expect_str_list(guest_ssh_value, "defaults.guest_ssh_extra_args") if found else []
    )

    api_node_value, found, _ = _extract(working, "api_node", "api.node")
    api_node = _expect_str(api_node_value, "defaults.api_node") if found else None

    api_port_value, found, _ = _extract(working, "api_port", "api.port")
    api_port = _expect_int(api_port_value, "defaults.api_port") if found else 8006

    api_insecure_value, found, _ = _extract(working, "api_insecure", "api.insecure")
    api_insecure = _expect_bool(api_insecure_value, "defaults.api_insecure") if found else False

    max_parallel_value, found, _ = _extract(working, "max_parallel")
    max_parallel = _expect_int(max_parallel_value, "defaults.max_parallel") if found else 2

    dry_run_value, found, _ = _extract(working, "dry_run")
    dry_run = _expect_bool(dry_run_value, "defaults.dry_run") if found else False

    return DefaultsForm(
        user=user,
        guest_user=guest_user,
        identity_file=identity_file,
        guest_identity_file=guest_identity_file,
        ssh_extra_args=ssh_extra_args,
        guest_ssh_extra_args=guest_ssh_extra_args,
        api_node=api_node,
        api_port=api_port,
        api_insecure=api_insecure,
        max_parallel=max_parallel,
        dry_run=dry_run,
        extras=working,
    )


def _load_host(entry_raw: dict[str, Any]) -> HostForm:
    working = cast(dict[str, Any], _to_mutable(entry_raw))

    name_value, found, _ = _extract(working, "name")
    name = _expect_str(name_value, "hosts.name") if found else None

    host_value, host_found, _ = _extract(working, "host")
    if not host_found:
        raise ManifestError("Each host requires a 'host' value")
    host = _expect_str(host_value, "hosts.host")

    if name is None:
        name = host

    token_value, token_found, _ = _extract(working, "api.token_env", "api_token_env")
    if not token_found:
        raise ManifestError(f"Host '{name}' must define api.token_env")
    api_token_env = _expect_str(token_value, "hosts.api.token_env")

    secret_value, secret_found, _ = _extract(working, "api.secret_env", "api_secret_env")
    if not secret_found:
        raise ManifestError(f"Host '{name}' must define api.secret_env")
    api_secret_env = _expect_str(secret_value, "hosts.api.secret_env")

    def _optional_str(*paths: str) -> str | None:
        value, found, _ = _extract(working, *paths)
        return _expect_str(value, paths[0]) if found else None

    def _optional_int(*paths: str) -> int | None:
        value, found, _ = _extract(working, *paths)
        return _expect_int(value, paths[0]) if found else None

    def _optional_bool(*paths: str) -> bool | None:
        value, found, _ = _extract(working, *paths)
        return _expect_bool(value, paths[0]) if found else None

    def _optional_list(*paths: str) -> list[str] | None:
        value, found, _ = _extract(working, *paths)
        return _expect_str_list(value, paths[0]) if found else None

    return HostForm(
        name=name,
        host=host,
        api_token_env=api_token_env,
        api_secret_env=api_secret_env,
        user=_optional_str("user", "ssh.user"),
        identity_file=_optional_str("identity_file", "ssh.identity_file"),
        ssh_extra_args=_optional_list("ssh_extra_args", "ssh.extra_args"),
        guest_user=_optional_str("guest_user", "guest.user"),
        guest_identity_file=_optional_str(
            "guest_identity_file",
            "guest.identity_file",
        ),
        guest_ssh_extra_args=_optional_list(
            "guest_ssh_extra_args",
            "guest.ssh_extra_args",
            "guest.ssh.extra_args",
        ),
        api_node=_optional_str("api_node", "api.node"),
        api_port=_optional_int("api_port", "api.port"),
        api_insecure=_optional_bool("api_insecure", "api.insecure"),
        max_parallel=_optional_int("max_parallel"),
        dry_run=_optional_bool("dry_run"),
        extras=working,
    )


def load_manifest_state(path: Path) -> ManifestState:
    with path.open("rb") as handle:
        raw_data: Any = tomllib.load(handle)

    if raw_data is None:
        raw_mapping: dict[str, Any] = {}
    elif isinstance(raw_data, dict):
        raw_mapping = cast(dict[str, Any], raw_data)
    else:
        raise ManifestError("Manifest root must be a table")

    defaults_section = raw_mapping.get("defaults")
    if defaults_section is None:
        defaults_raw: dict[str, Any] = {}
    elif isinstance(defaults_section, dict):
        defaults_raw = cast(dict[str, Any], defaults_section)
    else:
        raise ManifestError("[defaults] must be a table")
    defaults = _load_defaults(defaults_raw)

    hosts_entries: list[HostForm] = []
    hosts_section = raw_mapping.get("hosts")
    if hosts_section is None:
        hosts_entries = []
    elif isinstance(hosts_section, list):
        host_entries_raw = cast(list[Any], hosts_section)
        for entry in host_entries_raw:
            if not isinstance(entry, dict):
                raise ManifestError("Each [[hosts]] entry must be a table")
            host_entry = cast(dict[str, Any], entry)
            hosts_entries.append(_load_host(host_entry))
    else:
        raise ManifestError("[[hosts]] must be an array of tables")

    top_level_extras: dict[str, Any] = {
        key: _to_mutable(value)
        for key, value in raw_mapping.items()
        if key not in {"defaults", "hosts"}
    }

    return ManifestState(defaults=defaults, hosts=hosts_entries, top_level_extras=top_level_extras)


def manifest_state_to_dict(state: ManifestState) -> dict[str, Any]:
    data = copy.deepcopy(state.top_level_extras)
    data["defaults"] = _defaults_to_dict(state.defaults)
    data["hosts"] = [_host_to_dict(host) for host in state.hosts]
    return data


def _ensure_proxmox_compat(payload: str) -> None:
    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as handle:
        handle.write(payload)
        temp_path = Path(handle.name)
    try:
        proxmox_batch.load_manifest(temp_path)
    finally:
        with contextlib.suppress(FileNotFoundError):  # pragma: no cover - best effort cleanup
            temp_path.unlink()


def _defaults_to_dict(defaults: DefaultsForm) -> dict[str, Any]:
    mapping = copy.deepcopy(defaults.extras)

    def _set_optional(path: str, value: Any | None) -> None:
        if value is None:
            _pop_path(mapping, path)
        else:
            _set_path(mapping, path, value)

    _set_path(mapping, "user", defaults.user)
    _set_path(mapping, "guest_user", defaults.guest_user)
    _set_optional("identity_file", defaults.identity_file)
    _set_optional("guest_identity_file", defaults.guest_identity_file)
    _set_path(mapping, "ssh_extra_args", list(defaults.ssh_extra_args))
    _set_path(mapping, "guest_ssh_extra_args", list(defaults.guest_ssh_extra_args))
    _set_optional("api_node", defaults.api_node)
    _set_path(mapping, "api_port", defaults.api_port)
    _set_path(mapping, "api_insecure", defaults.api_insecure)
    _set_path(mapping, "max_parallel", defaults.max_parallel)
    _set_path(mapping, "dry_run", defaults.dry_run)
    return mapping


def _host_to_dict(host: HostForm) -> dict[str, Any]:
    mapping = copy.deepcopy(host.extras)

    def _set_optional(path: str, value: Any | None) -> None:
        if value is None:
            _pop_path(mapping, path)
        else:
            _set_path(mapping, path, value)

    _set_path(mapping, "name", host.name)
    _set_path(mapping, "host", host.host)
    _set_path(mapping, "api.token_env", host.api_token_env)
    _set_path(mapping, "api.secret_env", host.api_secret_env)
    _set_optional("user", host.user)
    _set_optional("identity_file", host.identity_file)
    _set_optional("ssh_extra_args", None if host.ssh_extra_args is None else list(host.ssh_extra_args))
    _set_optional("guest_user", host.guest_user)
    _set_optional("guest_identity_file", host.guest_identity_file)
    _set_optional(
        "guest_ssh_extra_args",
        None if host.guest_ssh_extra_args is None else list(host.guest_ssh_extra_args),
    )
    _set_optional("api_node", host.api_node)
    _set_optional("api_port", host.api_port)
    _set_optional("api_insecure", host.api_insecure)
    _set_optional("max_parallel", host.max_parallel)
    _set_optional("dry_run", host.dry_run)
    return mapping


def write_manifest(state: ManifestState, path: Path) -> None:
    validate_state(state)
    data = manifest_state_to_dict(state)
    payload = tomli_w.dumps(data)
    _ensure_proxmox_compat(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as handle:
        handle.write(payload)
        temp_name = Path(handle.name)
    os.replace(temp_name, path)
    LOGGER.info("Saved manifest to %s", path)


def validate_state(state: ManifestState) -> None:
    if state.defaults.max_parallel <= 0:
        raise ManifestError("defaults.max_parallel must be greater than zero")
    if state.defaults.api_port <= 0:
        raise ManifestError("defaults.api_port must be greater than zero")

    names: set[str] = set()
    if not state.hosts:
        raise ManifestError("Manifest must include at least one host")

    for host in state.hosts:
        if not host.name:
            raise ManifestError("Host entries require a name")
        if host.name in names:
            raise ManifestError(f"Duplicate host name '{host.name}' detected")
        names.add(host.name)
        if not host.host:
            raise ManifestError(f"Host '{host.name}' is missing a host value")
        if not host.api_token_env:
            raise ManifestError(f"Host '{host.name}' must define api.token_env")
        if not host.api_secret_env:
            raise ManifestError(f"Host '{host.name}' must define api.secret_env")
        if host.api_port is not None and host.api_port <= 0:
            raise ManifestError(f"Host '{host.name}' api_port must be greater than zero")
        if host.max_parallel is not None and host.max_parallel <= 0:
            raise ManifestError(f"Host '{host.name}' max_parallel must be greater than zero")


def _format_list(values: list[str]) -> str:
    return ", ".join(values)


def _parse_list(answer: str) -> list[str]:
    return [item.strip() for item in answer.split(",") if item.strip()]


def _ask_text(message: str, *, default: str = "", required: bool = False) -> str:
    while True:
        response = questionary.text(message, default=default).ask()
        if response is None:
            raise WizardAbort()
        result = response.strip()
        if result:
            return result
        if default and not required:
            return default
        if required:
            questionary.print("Value is required.", style="bold red")
            continue
        return ""


def _ask_optional_text(
    message: str,
    *,
    default: str | None = None,
    inherit_word: str | None = None,
    clear_word: str | None = None,
) -> str | None:
    prompt_default = default or ""
    while True:
        response = questionary.text(message, default=prompt_default).ask()
        if response is None:
            raise WizardAbort()
        result = response.strip()
        lowered = result.lower()
        if inherit_word and lowered == inherit_word:
            return None
        if clear_word and lowered == clear_word:
            return None
        if not result:
            return default
        return result


def _ask_list(
    message: str,
    *,
    current: list[str] | None,
    allow_inherit: bool,
    inherit_word: str = "inherit",
) -> list[str] | None:
    default = _format_list(current) if current else ""
    prompt = f"{message} (comma separated; enter 'none' for an empty list)"
    if allow_inherit:
        prompt = f"{prompt}; enter '{inherit_word}' to inherit"
    while True:
        response = questionary.text(prompt, default=default).ask()
        if response is None:
            raise WizardAbort()
        result = response.strip()
        lowered = result.lower()
        if allow_inherit and lowered == inherit_word:
            return None
        if lowered == "none":
            return []
        if not result:
            return current
        return _parse_list(result)


def _ask_int(message: str, *, default: int | None, required: bool, allow_inherit: bool = False) -> int | None:
    default_text = str(default) if default is not None else ""
    hint: list[str] = []
    if allow_inherit:
        hint.append("enter 'inherit' to remove override")
    prompt = message if not hint else f"{message} ({'; '.join(hint)})"
    while True:
        response = questionary.text(prompt, default=default_text).ask()
        if response is None:
            raise WizardAbort()
        result = response.strip()
        lowered = result.lower()
        if allow_inherit and lowered == "inherit":
            return None
        if not result:
            if default is not None and not required:
                return default
            if required:
                questionary.print("Value is required.", style="bold red")
                continue
            return None
        try:
            value = int(result)
        except ValueError:
            questionary.print("Please enter a valid integer.", style="bold red")
            continue
        if value <= 0 and required:
            questionary.print("Value must be greater than zero.", style="bold red")
            continue
        return value


def _ask_bool(message: str, *, default: bool) -> bool:
    response = questionary.confirm(message, default=default).ask()
    if response is None:
        raise WizardAbort()
    return bool(response)


def _ask_optional_bool(message: str, *, current: bool | None) -> bool | None:
    hint = "leave blank to inherit" if current is None else "enter 'inherit' to clear"
    prompt = f"{message} ({hint})"
    while True:
        response = questionary.text(prompt, default="" if current is None else str(current)).ask()
        if response is None:
            raise WizardAbort()
        result = response.strip().lower()
        if not result:
            return current
        if result == "inherit":
            return None
        if result in {"true", "t", "yes", "y"}:
            return True
        if result in {"false", "f", "no", "n"}:
            return False
        questionary.print("Enter true/false or 'inherit'.", style="bold red")


def _format_host_label(host: HostForm) -> str:
    return f"{host.name} ({host.host})"


def _clone_host(host: HostForm) -> HostForm:
    return HostForm(
        name=host.name,
        host=host.host,
        api_token_env=host.api_token_env,
        api_secret_env=host.api_secret_env,
        user=host.user,
        identity_file=host.identity_file,
        ssh_extra_args=None if host.ssh_extra_args is None else list(host.ssh_extra_args),
        guest_user=host.guest_user,
        guest_identity_file=host.guest_identity_file,
        guest_ssh_extra_args=
            None if host.guest_ssh_extra_args is None else list(host.guest_ssh_extra_args),
        api_node=host.api_node,
        api_port=host.api_port,
        api_insecure=host.api_insecure,
        max_parallel=host.max_parallel,
        dry_run=host.dry_run,
        extras=copy.deepcopy(host.extras),
    )


class ManifestWizard:
    def __init__(self, path: Path, state: ManifestState | None = None) -> None:
        self.path = path
        self.state = state or ManifestState.empty()
        self.dirty = False

    def load(self) -> None:
        if not self.path.exists():
            confirm = questionary.confirm(
                f"Manifest '{self.path}' not found. Create a new manifest?",
                default=True,
            ).ask()
            if confirm is None:
                raise WizardAbort()
            if not confirm:
                raise WizardAbort()
            self.state = ManifestState.empty()
            self.dirty = True
            return
        self.state = load_manifest_state(self.path)

    def run(self) -> None:
        self.load()
        while True:
            choice = questionary.select(
                "Select an action",
                choices=[
                    questionary.Choice("Edit defaults", "defaults"),
                    questionary.Choice("Manage hosts", "hosts"),
                    questionary.Choice("Save and exit", "save"),
                    questionary.Choice("Exit without saving", "exit"),
                ],
            ).ask()
            if choice is None:
                raise WizardAbort()
            if choice == "defaults":
                if self.edit_defaults():
                    self.dirty = True
            elif choice == "hosts":
                if self.manage_hosts():
                    self.dirty = True
            elif choice == "save":
                self.save()
                return
            elif choice == "exit":
                if self.dirty:
                    confirm = questionary.confirm(
                        "Discard unsaved changes?", default=False
                    ).ask()
                    if not confirm:
                        continue
                return

    def save(self) -> None:
        write_manifest(self.state, self.path)
        self.dirty = False

    def edit_defaults(self) -> bool:
        defaults = self.state.defaults
        try:
            defaults.user = _ask_text("SSH user", default=defaults.user, required=True)
            defaults.guest_user = _ask_text(
                "Guest SSH user",
                default=defaults.guest_user,
                required=True,
            )
            defaults.identity_file = _ask_optional_text(
                "Identity file (enter 'none' to clear)",
                default=defaults.identity_file,
                clear_word="none",
            )
            defaults.guest_identity_file = _ask_optional_text(
                "Guest identity file (enter 'none' to clear)",
                default=defaults.guest_identity_file,
                clear_word="none",
            )
            ssh_list = _ask_list(
                "SSH extra args",
                current=defaults.ssh_extra_args,
                allow_inherit=False,
            )
            defaults.ssh_extra_args = ssh_list if ssh_list is not None else []
            guest_ssh_list = _ask_list(
                "Guest SSH extra args",
                current=defaults.guest_ssh_extra_args,
                allow_inherit=False,
            )
            defaults.guest_ssh_extra_args = guest_ssh_list if guest_ssh_list is not None else []
            defaults.api_node = _ask_optional_text(
                "API node (enter 'none' to clear)",
                default=defaults.api_node,
                clear_word="none",
            )
            api_port_value = _ask_int(
                "API port",
                default=defaults.api_port,
                required=True,
            )
            defaults.api_port = cast(int, api_port_value)
            defaults.api_insecure = _ask_bool(
                "Allow insecure API connections?",
                default=defaults.api_insecure,
            )
            max_parallel_value = _ask_int(
                "Max parallel hosts",
                default=defaults.max_parallel,
                required=True,
            )
            defaults.max_parallel = cast(int, max_parallel_value)
            defaults.dry_run = _ask_bool(
                "Enable dry-run by default?",
                default=defaults.dry_run,
            )
        except WizardAbort:
            return False
        return True

    def manage_hosts(self) -> bool:
        dirty = False
        while True:
            choice = questionary.select(
                "Host manager",
                choices=[
                    questionary.Choice("Add host", "add"),
                    questionary.Choice("Edit host", "edit"),
                    questionary.Choice("Duplicate host", "duplicate"),
                    questionary.Choice("Delete host", "delete"),
                    questionary.Choice("Back", "back"),
                ],
            ).ask()
            if choice is None:
                raise WizardAbort()
            if choice == "add":
                dirty |= self.add_host()
            elif choice == "edit":
                dirty |= self.edit_host()
            elif choice == "duplicate":
                dirty |= self.duplicate_host()
            elif choice == "delete":
                dirty |= self.delete_host()
            elif choice == "back":
                return dirty

    def _select_host_index(self, prompt: str) -> int | None:
        if not self.state.hosts:
            questionary.print("No hosts defined yet.", style="bold yellow")
            return None
        choice = questionary.select(
            prompt,
            choices=[
                questionary.Choice(_format_host_label(host), idx)
                for idx, host in enumerate(self.state.hosts)
            ],
        ).ask()
        if choice is None:
            raise WizardAbort()
        return int(choice)

    def add_host(self) -> bool:
        host = HostForm(
            name="",
            host="",
            api_token_env="",
            api_secret_env="",
            extras={},
        )
        return self._edit_host_form(host, is_new=True)

    def edit_host(self) -> bool:
        index = self._select_host_index("Select a host to edit")
        if index is None:
            return False
        host = _clone_host(self.state.hosts[index])
        if self._edit_host_form(host, is_new=False):
            self.state.hosts[index] = host
            return True
        return False

    def duplicate_host(self) -> bool:
        index = self._select_host_index("Select a host to duplicate")
        if index is None:
            return False
        host = _clone_host(self.state.hosts[index])
        host.name = f"{host.name}-copy"
        if self._edit_host_form(host, is_new=True):
            self.state.hosts.append(host)
            return True
        return False

    def delete_host(self) -> bool:
        index = self._select_host_index("Select a host to delete")
        if index is None:
            return False
        host = self.state.hosts[index]
        confirm = questionary.confirm(
            f"Delete host '{host.name}'?", default=False
        ).ask()
        if confirm:
            self.state.hosts.pop(index)
            return True
        return False

    def _edit_host_form(self, host: HostForm, *, is_new: bool) -> bool:
        defaults = self.state.defaults
        try:
            host.name = self._ask_unique_name(host.name, current=host.name)
            host.host = _ask_text("Host address", default=host.host, required=True)
            host.user = self._ask_inheritable_text(
                "SSH user",
                current=host.user,
                inherit_value=defaults.user,
            )
            host.identity_file = self._ask_inheritable_text(
                "Identity file",
                current=host.identity_file,
                inherit_value=defaults.identity_file,
            )
            host.ssh_extra_args = self._ask_inheritable_list(
                "SSH extra args",
                current=host.ssh_extra_args,
                inherit_from=defaults.ssh_extra_args,
            )
            host.guest_user = self._ask_inheritable_text(
                "Guest user",
                current=host.guest_user,
                inherit_value=defaults.guest_user,
            )
            host.guest_identity_file = self._ask_inheritable_text(
                "Guest identity file",
                current=host.guest_identity_file,
                inherit_value=defaults.guest_identity_file,
            )
            host.guest_ssh_extra_args = self._ask_inheritable_list(
                "Guest SSH extra args",
                current=host.guest_ssh_extra_args,
                inherit_from=defaults.guest_ssh_extra_args,
            )
            host.api_node = self._ask_inheritable_text(
                "API node",
                current=host.api_node,
                inherit_value=defaults.api_node,
            )
            host.api_port = self._ask_inheritable_int(
                "API port",
                current=host.api_port,
                inherit_value=defaults.api_port,
            )
            host.api_insecure = self._ask_inheritable_bool(
                "Allow insecure API",
                current=host.api_insecure,
                inherit_value=defaults.api_insecure,
            )
            host.max_parallel = self._ask_inheritable_int(
                "Max parallel hosts",
                current=host.max_parallel,
                inherit_value=defaults.max_parallel,
            )
            host.dry_run = self._ask_inheritable_bool(
                "Force dry-run",
                current=host.dry_run,
                inherit_value=defaults.dry_run,
            )
            host.api_token_env = _ask_text(
                "API token env var",
                default=host.api_token_env,
                required=True,
            )
            host.api_secret_env = _ask_text(
                "API secret env var",
                default=host.api_secret_env,
                required=True,
            )
        except WizardAbort:
            return False

        if is_new:
            self.state.hosts.append(host)
        return True

    def _ask_unique_name(self, proposed: str, *, current: str | None) -> str:
        while True:
            value = _ask_text("Host name", default=proposed, required=True)
            if value == current:
                return value
            if any(existing.name == value for existing in self.state.hosts):
                questionary.print("Host name already exists.", style="bold red")
                continue
            return value

    def _ask_inheritable_text(
        self,
        label: str,
        *,
        current: str | None,
        inherit_value: str | None,
    ) -> str | None:
        inherit_word = "inherit"
        if inherit_value is None:
            hint = f"type '{inherit_word}' to inherit defaults"
        else:
            hint = f"type '{inherit_word}' to inherit {inherit_value!r}"
        prompt = f"{label} ({hint}; leave blank to keep current)"
        return _ask_optional_text(
            prompt,
            default=current or None,
            inherit_word=inherit_word,
        )

    def _ask_inheritable_list(
        self,
        label: str,
        *,
        current: list[str] | None,
        inherit_from: list[str],
    ) -> list[str] | None:
        inherit_word = "inherit"
        prompt = f"{label} (inherit -> {inherit_from!r})"
        return _ask_list(
            prompt,
            current=current,
            allow_inherit=True,
            inherit_word=inherit_word,
        )

    def _ask_inheritable_int(
        self,
        label: str,
        *,
        current: int | None,
        inherit_value: int,
    ) -> int | None:
        prompt = f"{label} (inherit -> {inherit_value})"
        return _ask_int(prompt, default=current, required=False, allow_inherit=True)

    def _ask_inheritable_bool(
        self,
        label: str,
        *,
        current: bool | None,
        inherit_value: bool,
    ) -> bool | None:
        hint = f"inherit -> {inherit_value}"
        return _ask_optional_bool(f"{label} ({hint})", current=current)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive editor for proxmox-hosts.toml")
    parser.add_argument(
        "--config",
        type=Path,
        default=proxmox_batch.DEFAULT_CONFIG_PATH,
        help="Path to the manifest file",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    wizard = ManifestWizard(args.config)
    try:
        wizard.run()
    except WizardAbort:
        questionary.print("Aborted.", style="bold red")
        return 1
    except ManifestError as exc:
        LOGGER.error("Manifest error: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
