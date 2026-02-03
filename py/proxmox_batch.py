#!/usr/bin/env python3
"""Batch runner for Proxmox maintenance tasks.

Exit codes:
  0 - every host succeeded
  2 - missing credentials (environment variables)
  3 - one or more hosts failed during maintenance
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeGuard, cast

try:  # Python 3.11 fallbacks (not expected, but keeps lint happy)
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError as exc:  # pragma: no cover - only for <3.11
    raise RuntimeError("Python 3.11+ is required for tomllib") from exc

from proxmox_maintenance import (
    async_main as proxmox_async_main,
    configure_logging as configure_proxmox_logging,
)

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).with_name("proxmox-hosts.toml")


class ManifestError(RuntimeError):
    """Raised when the TOML manifest is invalid."""


class CredentialError(RuntimeError):
    """Raised when required secrets are missing from the environment."""

    def __init__(self, host_name: str, env_var: str) -> None:
        message = f"Host '{host_name}' requires environment variable '{env_var}'"
        super().__init__(message)
        self.host_name = host_name
        self.env_var = env_var


@dataclass(slots=True)
class BatchDefaults:
    user: str = "root"
    guest_user: str = "root"
    identity_file: str | None = None
    guest_identity_file: str | None = None
    ssh_extra_args: tuple[str, ...] = ()
    guest_ssh_extra_args: tuple[str, ...] = ()
    api_node: str | None = None
    api_port: int = 8006
    api_insecure: bool = False
    max_parallel: int = 2
    dry_run: bool = False


@dataclass(slots=True)
class HostConfig:
    name: str
    host: str
    user: str
    identity_file: str | None
    ssh_extra_args: tuple[str, ...]
    guest_user: str
    guest_identity_file: str | None
    guest_ssh_extra_args: tuple[str, ...]
    api_node: str | None
    api_port: int
    api_insecure: bool
    api_token_env: str
    api_secret_env: str
    max_parallel: int
    dry_run: bool


@dataclass(slots=True)
class HostResult:
    name: str
    success: bool
    duration: float
    message: str | None = None


def _is_str_mapping(value: Any) -> TypeGuard[Mapping[str, Any]]:
    return isinstance(value, Mapping)


def _lookup(mapping: Mapping[str, Any], dotted_path: str) -> Any | None:
    current: Any = mapping
    for segment in dotted_path.split("."):
        if not _is_str_mapping(current):
            return None
        next_value = current.get(segment)
        if next_value is None:
            return None
        current = next_value
    return current


def _first_value(mapping: Mapping[str, Any], paths: Iterable[str]) -> Any | None:
    for path in paths:
        value = _lookup(mapping, path)
        if value is not None:
            return value
    return None


def _expect_str(value: object, label: str) -> str:
    if isinstance(value, str):
        return value
    raise ManifestError(f"Expected string for '{label}', got {type(value).__name__}")


def _expect_bool(value: object, label: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ManifestError(f"Expected boolean for '{label}', got {type(value).__name__}")


def _expect_int(value: object, label: str) -> int:
    if isinstance(value, int):
        return value
    raise ManifestError(f"Expected integer for '{label}', got {type(value).__name__}")


def _is_nonstring_sequence(value: object) -> TypeGuard[Sequence[object]]:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _expect_str_list(value: object, label: str) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if _is_nonstring_sequence(value):
        return tuple(str(item) for item in value)
    raise ManifestError(f"Expected string list for '{label}', got {type(value).__name__}")


def _expand_path(value: str | None) -> str | None:
    if value is None:
        return None
    return str(Path(value).expanduser())


def _get_str(mapping: Mapping[str, Any], *paths: str) -> str | None:
    raw = _first_value(mapping, paths)
    if raw is None:
        return None
    return _expect_str(raw, paths[0])


def _get_bool(mapping: Mapping[str, Any], *paths: str) -> bool | None:
    raw = _first_value(mapping, paths)
    if raw is None:
        return None
    return _expect_bool(raw, paths[0])


def _get_int(mapping: Mapping[str, Any], *paths: str) -> int | None:
    raw = _first_value(mapping, paths)
    if raw is None:
        return None
    return _expect_int(raw, paths[0])


def _get_str_list(mapping: Mapping[str, Any], *paths: str) -> tuple[str, ...] | None:
    raw = _first_value(mapping, paths)
    if raw is None:
        return None
    return _expect_str_list(raw, paths[0])


def load_manifest(path: Path) -> tuple[BatchDefaults, list[HostConfig]]:
    try:
        with path.open("rb") as handle:
            data: dict[str, Any] = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ManifestError(f"Manifest file '{path}' was not found") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"Manifest file '{path}' is invalid: {exc}") from exc

    defaults_data = data.get("defaults", {})
    if defaults_data and not isinstance(defaults_data, Mapping):
        raise ManifestError("[defaults] must be a table")

    defaults_mapping: Mapping[str, Any] = (
        cast(Mapping[str, Any], defaults_data) if isinstance(defaults_data, Mapping) else {}
    )
    defaults = BatchDefaults(
        user=_get_str(defaults_mapping, "user") or "root",
        guest_user=_get_str(defaults_mapping, "guest_user", "guest.user") or "root",
        identity_file=_expand_path(
            _get_str(defaults_mapping, "identity_file", "ssh.identity_file")
        ),
        guest_identity_file=_expand_path(
            _get_str(defaults_mapping, "guest_identity_file", "guest.identity_file")
        ),
        ssh_extra_args=_get_str_list(defaults_mapping, "ssh_extra_args", "ssh.extra_args") or (),
        guest_ssh_extra_args=_get_str_list(
            defaults_mapping,
            "guest_ssh_extra_args",
            "guest.ssh_extra_args",
            "guest.ssh.extra_args",
        )
        or (),
        api_node=_get_str(defaults_mapping, "api_node", "api.node"),
        api_port=_get_int(defaults_mapping, "api_port", "api.port") or 8006,
        api_insecure=_get_bool(defaults_mapping, "api_insecure", "api.insecure") or False,
        max_parallel=_get_int(defaults_mapping, "max_parallel") or 2,
        dry_run=_get_bool(defaults_mapping, "dry_run") or False,
    )

    hosts_data_raw_obj = data.get("hosts")
    if not isinstance(hosts_data_raw_obj, list) or not hosts_data_raw_obj:
        raise ManifestError("Manifest must include a non-empty [[hosts]] list")

    hosts_data: list[Any] = cast(list[Any], hosts_data_raw_obj)
    host_entries: list[Mapping[str, Any]] = []
    for entry in hosts_data:
        if not isinstance(entry, Mapping):
            raise ManifestError("Each [[hosts]] entry must be a table")
        host_entries.append(cast(Mapping[str, Any], entry))

    host_configs: list[HostConfig] = []
    seen_names: set[str] = set()
    for entry_mapping in host_entries:
        host_value = _get_str(entry_mapping, "host")
        if not host_value:
            raise ManifestError("Each host requires a 'host' value")
        name_value = _get_str(entry_mapping, "name") or host_value
        if name_value in seen_names:
            raise ManifestError(f"Duplicate host name '{name_value}' detected")
        seen_names.add(name_value)

        user = _get_str(entry_mapping, "user", "ssh.user") or defaults.user
        guest_user = _get_str(entry_mapping, "guest_user", "guest.user") or defaults.guest_user
        identity = (
            _expand_path(_get_str(entry_mapping, "identity_file", "ssh.identity_file"))
            or defaults.identity_file
        )
        guest_identity = (
            _expand_path(_get_str(entry_mapping, "guest_identity_file", "guest.identity_file"))
            or defaults.guest_identity_file
        )
        ssh_extra = (
            _get_str_list(entry_mapping, "ssh_extra_args", "ssh.extra_args")
            or defaults.ssh_extra_args
        )
        guest_ssh_extra = _get_str_list(
            entry_mapping,
            "guest_ssh_extra_args",
            "guest.ssh_extra_args",
            "guest.ssh.extra_args",
        ) or defaults.guest_ssh_extra_args
        api_node = _get_str(entry_mapping, "api_node", "api.node") or defaults.api_node
        api_port = _get_int(entry_mapping, "api_port", "api.port") or defaults.api_port
        api_insecure = _get_bool(entry_mapping, "api_insecure", "api.insecure")
        if api_insecure is None:
            api_insecure = defaults.api_insecure
        max_parallel = _get_int(entry_mapping, "max_parallel") or defaults.max_parallel
        dry_run = _get_bool(entry_mapping, "dry_run")
        if dry_run is None:
            dry_run = defaults.dry_run

        token_env = _get_str(entry_mapping, "api.token_env", "api_token_env")
        secret_env = _get_str(entry_mapping, "api.secret_env", "api_secret_env")
        if not token_env or not secret_env:
            raise ManifestError(f"Host '{name_value}' must define api.token_env and api.secret_env")

        host_configs.append(
            HostConfig(
                name=name_value,
                host=host_value,
                user=user,
                identity_file=identity,
                ssh_extra_args=ssh_extra,
                guest_user=guest_user,
                guest_identity_file=guest_identity,
                guest_ssh_extra_args=guest_ssh_extra,
                api_node=api_node,
                api_port=api_port,
                api_insecure=api_insecure,
                api_token_env=token_env,
                api_secret_env=secret_env,
                max_parallel=max_parallel,
                dry_run=dry_run,
            )
        )
    return defaults, host_configs


def select_hosts(hosts: Sequence[HostConfig], requested: Sequence[str]) -> list[HostConfig]:
    if not requested:
        return list(hosts)
    name_index = {host.name: host for host in hosts}
    missing = [name for name in requested if name not in name_index]
    if missing:
        raise ValueError(f"Unknown host(s): {', '.join(missing)}")
    return [name_index[name] for name in requested]


def resolve_api_credentials(host: HostConfig) -> tuple[str, str]:
    token = os.environ.get(host.api_token_env)
    if not token:
        raise CredentialError(host.name, host.api_token_env)
    secret = os.environ.get(host.api_secret_env)
    if not secret:
        raise CredentialError(host.name, host.api_secret_env)
    return token, secret


def build_host_argv(
    host: HostConfig,
    token: str,
    secret: str,
    *,
    verbose: bool,
    force_dry_run: bool,
) -> list[str]:
    argv: list[str] = [host.host]
    argv.extend(["--user", host.user])
    if host.identity_file:
        argv.extend(["--identity-file", host.identity_file])
    for extra in host.ssh_extra_args:
        argv.extend(["--ssh-extra-arg", extra])
    argv.extend(["--api-token-id", token])
    argv.extend(["--api-token-secret", secret])
    if host.api_node:
        argv.extend(["--api-node", host.api_node])
    argv.extend(["--api-port", str(host.api_port)])
    if host.api_insecure:
        argv.append("--api-insecure")
    argv.extend(["--guest-user", host.guest_user])
    if host.guest_identity_file:
        argv.extend(["--guest-identity-file", host.guest_identity_file])
    for extra in host.guest_ssh_extra_args:
        argv.extend(["--guest-ssh-extra-arg", extra])
    argv.extend(["--max-parallel", str(host.max_parallel)])
    dry_run_enabled = force_dry_run or host.dry_run
    if dry_run_enabled:
        argv.append("--dry-run")
    if verbose:
        argv.append("--verbose")
    return argv


async def run_host(
    host: HostConfig,
    *,
    force_dry_run: bool,
    verbose: bool,
) -> tuple[bool, str | None]:
    token, secret = resolve_api_credentials(host)
    argv = build_host_argv(host, token, secret, verbose=verbose, force_dry_run=force_dry_run)
    logger.info("Starting maintenance for %s (%s)", host.name, host.host)
    return_code = await proxmox_async_main(argv)
    if return_code == 0:
        return True, None
    return False, f"proxmox_maintenance exited with status {return_code}"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch runner for Proxmox maintenance")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to proxmox hosts manifest (default: %(default)s)",
    )
    parser.add_argument(
        "--host",
        dest="hosts",
        action="append",
        default=[],
        help="Limit execution to the specified host name (repeatable)",
    )
    parser.add_argument(
        "--dry-run",
        dest="force_dry_run",
        action="store_true",
        help="Force dry-run across every host regardless of manifest",
    )
    parser.add_argument(
        "--max-hosts",
        type=int,
        help="Process at most N hosts from the filtered list",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging for batch and host runs",
    )
    return parser


def _resolve_config_path(value: str) -> Path:
    return Path(value).expanduser()


async def async_main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.max_hosts is not None and args.max_hosts <= 0:
        parser.error("--max-hosts must be a positive integer")

    configure_proxmox_logging(args.verbose)
    config_path = _resolve_config_path(args.config)
    try:
        _, hosts = load_manifest(config_path)
    except ManifestError as exc:
        logger.error("%s", exc)
        return 1

    try:
        selected_hosts = select_hosts(hosts, args.hosts)
    except ValueError as exc:
        parser.error(str(exc))

    if args.max_hosts is not None:
        selected_hosts = selected_hosts[: args.max_hosts]

    if not selected_hosts:
        logger.warning("No hosts selected; exiting without work")
        return 0

    results: list[HostResult] = []
    credential_issue = False
    runtime_failure = False

    for host in selected_hosts:
        start = time.monotonic()
        try:
            success, message = await run_host(
                host,
                force_dry_run=args.force_dry_run,
                verbose=args.verbose,
            )
        except CredentialError as exc:
            credential_issue = True
            success = False
            message = str(exc)
            logger.error("%s", message)
        except Exception as exc:  # pragma: no cover - defensive
            runtime_failure = True
            success = False
            message = f"Unexpected failure for {host.name}: {exc}"
            logger.exception("Unexpected failure for %s", host.name)
        duration = time.monotonic() - start
        results.append(HostResult(name=host.name, success=success, duration=duration, message=message))
        if success:
            logger.info("Host %s completed successfully in %.1fs", host.name, duration)
        else:
            logger.error("Host %s failed in %.1fs (%s)", host.name, duration, message or "no details")

    if credential_issue:
        return 2
    if runtime_failure or any(not result.success for result in results):
        return 3
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    sys.exit(main())
