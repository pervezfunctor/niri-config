"""Reusable SSH helpers for maintaining remote Linux guests."""
from __future__ import annotations

import asyncio
import logging
import sys
from asyncio.subprocess import PIPE
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

logger = logging.getLogger(__name__)


DEFAULT_SSH_OPTIONS: tuple[str, ...] = (
    "-o",
    "BatchMode=yes",
    "-o",
    "StrictHostKeyChecking=no",
    "-o",
    "UserKnownHostsFile=/dev/null",
    "-o",
    "ConnectTimeout=15",
)


class CommandExecutionError(RuntimeError):
    """Raised when an SSH command fails."""


@dataclass
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


@dataclass
class GuestSSHOptions:
    user: str
    identity_file: str | None
    extra_args: tuple[str, ...]


class SSHSession:
    """Executes commands over SSH with optional dry-run semantics."""

    def __init__(
        self,
        host: str,
        user: str,
        *,
        dry_run: bool,
        identity_file: str | None = None,
        extra_args: Sequence[str] | None = None,
        description: str = "remote",
    ) -> None:
        self.host = host
        self.user = user
        self.dry_run = dry_run
        self.identity_file = identity_file
        self.description = description
        self.extra_args = tuple(extra_args or ())

    async def run(
        self,
        remote_cmd: str,
        *,
        capture_output: bool,
        check: bool = True,
        mutable: bool = False,
        timeout_seconds: float | None = None,
    ) -> CommandResult:
        ssh_command = ["ssh", *DEFAULT_SSH_OPTIONS]
        if self.identity_file:
            ssh_command.extend(["-i", self.identity_file])
        ssh_command.extend(self.extra_args)
        ssh_command.append(f"{self.user}@{self.host}")
        ssh_command.append(remote_cmd)
        if self.dry_run and mutable:
            logger.info("[dry-run] %s -> %s", self.description, remote_cmd)
            return CommandResult(stdout="", stderr="", returncode=0)
        logger.debug("%s$ %s", self.description, remote_cmd)
        stdout_pipe = PIPE if capture_output else None
        process = await asyncio.create_subprocess_exec(
            *ssh_command,
            stdout=stdout_pipe,
            stderr=PIPE,
        )
        try:
            if timeout_seconds is not None:
                async with asyncio.timeout(timeout_seconds):
                    stdout_bytes, stderr_bytes = await process.communicate()
            else:
                stdout_bytes, stderr_bytes = await process.communicate()
        except TimeoutError as exc:  # pragma: no cover - rare path
            process.kill()
            await process.wait()
            raise CommandExecutionError(
                f"Command timed out on {self.description}: {remote_cmd}"
            ) from exc
        stdout_text = stdout_bytes.decode() if stdout_bytes else ""
        stderr_text = stderr_bytes.decode() if stderr_bytes else ""
        return_code = process.returncode if process.returncode is not None else -1
        if check and return_code != 0:
            raise CommandExecutionError(
                f"Command failed ({return_code}) on {self.description}: {remote_cmd}\n"
                f"{stderr_text.strip()}"
            )
        return CommandResult(stdout=stdout_text, stderr=stderr_text, returncode=return_code)


async def attempt_guest_upgrade(
    *,
    ip_address: str,
    default_user: str,
    options: GuestSSHOptions,
    dry_run: bool,
    identifier: str,
) -> None:
    """Run a best-effort OS upgrade on a remote guest."""

    session = SSHSession(
        host=ip_address,
        user=default_user,
        dry_run=dry_run,
        identity_file=options.identity_file,
        extra_args=options.extra_args,
        description=identifier,
    )
    success = await upgrade_guest_operating_system(session)
    if success:
        return
    alternate_user = prompt_for_alternate_username(ip_address, default_user)
    if not alternate_user:
        return
    retry_session = SSHSession(
        host=ip_address,
        user=alternate_user,
        dry_run=dry_run,
        identity_file=options.identity_file,
        extra_args=options.extra_args,
        description=f"{identifier}-retry",
    )
    await upgrade_guest_operating_system(retry_session)


async def upgrade_guest_operating_system(session: SSHSession) -> bool:
    try:
        release_content = await session.run("cat /etc/os-release", capture_output=True, mutable=False)
    except CommandExecutionError as exc:
        logger.error("Unable to read /etc/os-release on %s: %s", session.description, exc)
        return False
    os_release = parse_os_release(release_content.stdout)
    package_manager = determine_package_manager(os_release)
    if not package_manager:
        logger.warning("Unsupported OS for %s", session.description)
        return False
    command = build_upgrade_command(package_manager, session.user != "root")
    try:
        await session.run(command, capture_output=False, mutable=True)
    except CommandExecutionError as exc:
        logger.error("Upgrade failed on %s: %s", session.description, exc)
        return False
    return True


def prompt_for_alternate_username(target: str, previous_user: str) -> str | None:
    if not sys.stdin.isatty():
        logger.warning("Cannot prompt for alternate username for %s; non-interactive session", target)
        return None
    prompt = (
        f"SSH to {target} failed for user '{previous_user}'. "
        "Enter alternate username (leave blank to skip): "
    )
    try:
        new_user = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return None
    return new_user or None


def parse_os_release(content: str) -> Mapping[str, str]:
    data: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        data[key] = value
    return data


def determine_package_manager(os_release: Mapping[str, str]) -> str | None:
    os_id = os_release.get("ID", "").lower()
    like_tokens = os_release.get("ID_LIKE", "").lower().split()
    candidates = {os_id, *like_tokens}
    if any(token in {"alpine"} for token in candidates):
        return "apk"
    if any(token in {"debian", "ubuntu"} for token in candidates):
        return "apt"
    if any(token in {"fedora", "rhel", "centos"} for token in candidates):
        return "dnf"
    if "arch" in candidates:
        return "pacman"
    if any(token in {"suse", "opensuse", "sles"} for token in candidates):
        return "zypper"
    return None


def build_upgrade_command(package_manager: str, use_sudo: bool) -> str:
    prefix = "sudo " if use_sudo else ""
    if package_manager == "apt":
        return f"{prefix}apt update && {prefix}apt full-upgrade -y && {prefix}apt autoremove -y"
    if package_manager == "dnf":
        return f"{prefix}dnf upgrade --refresh -y"
    if package_manager == "apk":
        return f"{prefix}apk update && {prefix}apk upgrade"
    if package_manager == "pacman":
        return f"{prefix}pacman -Syu --noconfirm"
    if package_manager == "zypper":
        return f"{prefix}zypper refresh && {prefix}zypper update -y"
    raise ValueError(f"Unsupported package manager: {package_manager}")


__all__ = [
    "DEFAULT_SSH_OPTIONS",
    "CommandExecutionError",
    "CommandResult",
    "GuestSSHOptions",
    "SSHSession",
    "attempt_guest_upgrade",
    "build_upgrade_command",
    "determine_package_manager",
    "parse_os_release",
    "prompt_for_alternate_username",
    "upgrade_guest_operating_system",
]
