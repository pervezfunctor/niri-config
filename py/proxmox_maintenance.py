#!/usr/bin/env python3
"""Proxmox fleet maintenance helper."""
from __future__ import annotations

import argparse
import asyncio
import logging
import shlex
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from remote_maintenance import (
    CommandExecutionError,
    GuestSSHOptions,
    SSHSession,
    attempt_guest_upgrade,
    build_upgrade_command,
    determine_package_manager,
    parse_os_release,
)

logger = logging.getLogger(__name__)

@dataclass
class VirtualMachine:
    vmid: str
    name: str
    status: str

    @property
    def is_running(self) -> bool:
        return self.status.lower() == "running"


@dataclass
class LXCContainer:
    ctid: str
    name: str
    status: str

    @property
    def is_running(self) -> bool:
        return self.status.lower() == "running"


def shlex_join(parts: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


class Reconciler(Protocol):
    async def reconcile(self) -> None:
        ...


class NodeRecord(BaseModel):
    node: str

    model_config = ConfigDict(extra="ignore")


class VMRecord(BaseModel):
    vmid: int
    name: str | None = None
    status: str | None = None

    model_config = ConfigDict(extra="ignore")


class ContainerRecord(BaseModel):
    vmid: int
    name: str | None = None
    status: str | None = None

    model_config = ConfigDict(extra="ignore")


class GuestInterfaceAddress(BaseModel):
    ip_address: str = Field(alias="ip-address")
    ip_address_type: str = Field(alias="ip-address-type")

    model_config = ConfigDict(populate_by_name=True)


def _empty_address_list() -> list[GuestInterfaceAddress]:
    return []


class GuestInterface(BaseModel):
    name: str | None = None
    ip_addresses: list[GuestInterfaceAddress] = Field(
        default_factory=_empty_address_list,
        alias="ip-addresses",
    )

    model_config = ConfigDict(populate_by_name=True)


VM_LIST_ADAPTER = TypeAdapter(list[VMRecord])
CONTAINER_LIST_ADAPTER = TypeAdapter(list[ContainerRecord])
INTERFACE_LIST_ADAPTER = TypeAdapter(list[GuestInterface])
NODE_LIST_ADAPTER = TypeAdapter(list[NodeRecord])


class ProxmoxAPIError(RuntimeError):
    """Raised when the Proxmox HTTP API call fails."""


class ProxmoxAPIClient:
    """Minimal Proxmox API helper that uses HTTP requests for inventory data."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        token_id: str,
        token_secret: str,
        node: str | None,
        verify_ssl: bool,
        timeout: float = 30.0,
    ) -> None:
        if not token_id or not token_secret:
            raise ProxmoxAPIError("API token id/secret are required")
        base_url = f"https://{host}:{port}/api2/json"
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"PVEAPIToken={token_id}={token_secret}"},
            timeout=timeout,
            verify=verify_ssl,
        )
        self._node = node

    async def __aenter__(self) -> ProxmoxAPIClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._client.aclose()

    async def list_vms(self) -> list[VirtualMachine]:
        node = await self._ensure_node()
        payload = await self._request("GET", f"/nodes/{node}/qemu")
        try:
            records = VM_LIST_ADAPTER.validate_python(payload.get("data", []))
        except ValidationError as exc:
            raise ProxmoxAPIError(f"Invalid VM payload: {exc}") from exc
        return [
            VirtualMachine(
                vmid=str(record.vmid),
                name=record.name or str(record.vmid),
                status=(record.status or "unknown"),
            )
            for record in records
        ]

    async def list_containers(self) -> list[LXCContainer]:
        node = await self._ensure_node()
        payload = await self._request("GET", f"/nodes/{node}/lxc")
        try:
            records = CONTAINER_LIST_ADAPTER.validate_python(payload.get("data", []))
        except ValidationError as exc:
            raise ProxmoxAPIError(f"Invalid container payload: {exc}") from exc
        return [
            LXCContainer(
                ctid=str(record.vmid),
                name=record.name or str(record.vmid),
                status=(record.status or "unknown"),
            )
            for record in records
        ]

    async def fetch_vm_interfaces(self, vmid: str) -> list[GuestInterface]:
        node = await self._ensure_node()
        payload = await self._request(
            "POST", f"/nodes/{node}/qemu/{vmid}/agent/network-get-interfaces"
        )
        try:
            return INTERFACE_LIST_ADAPTER.validate_python(payload.get("data", []))
        except ValidationError as exc:
            raise ProxmoxAPIError(f"Invalid interface payload: {exc}") from exc

    async def _request(self, method: str, path: str) -> Mapping[str, Any]:
        try:
            response = await self._client.request(method, path)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProxmoxAPIError(f"HTTP error calling Proxmox API: {exc}") from exc
        try:
            return response.json()
        except ValueError as exc:
            raise ProxmoxAPIError("Invalid JSON response from Proxmox API") from exc

    async def _ensure_node(self) -> str:
        if self._node:
            return self._node
        payload = await self._request("GET", "/nodes")
        try:
            nodes = NODE_LIST_ADAPTER.validate_python(payload.get("data", []))
        except ValidationError as exc:
            raise ProxmoxAPIError(f"Invalid nodes payload: {exc}") from exc
        if not nodes:
            raise ProxmoxAPIError("Proxmox API returned no nodes; specify --api-node")
        self._node = nodes[0].node
        return self._node


class VirtualMachineAgent:
    def __init__(
        self,
        vm: VirtualMachine,
        proxmox_session: SSHSession,
        api_client: ProxmoxAPIClient,
        guest_options: GuestSSHOptions,
    ) -> None:
        self.vm = vm
        self.proxmox_session = proxmox_session
        self.api_client = api_client
        self.guest_options = guest_options

    async def reconcile(self) -> None:
        logger.info("Processing VM %s (%s)", self.vm.name, self.vm.vmid)
        was_running = self.vm.is_running
        if self.vm.is_running:
            await self.stop_vm()
        await self.backup_vm()
        await self.start_vm()
        ip_address = await self.fetch_ip()
        if ip_address:
            await attempt_guest_upgrade(
                ip_address=ip_address,
                default_user=self.guest_options.user,
                options=self.guest_options,
                dry_run=self.proxmox_session.dry_run,
                identifier=f"vm-{self.vm.vmid}",
            )
        else:
            logger.warning("Unable to determine IP for VM %s", self.vm.vmid)
        if not was_running:
            await self.stop_vm()

    async def stop_vm(self) -> None:
        logger.info("Stopping VM %s", self.vm.vmid)
        cmd = shlex_join(["qm", "shutdown", self.vm.vmid, "--timeout", "120"])
        await self.proxmox_session.run(cmd, capture_output=False, mutable=True)
        self.vm.status = "stopped"

    async def backup_vm(self) -> None:
        logger.info("Backing up VM %s", self.vm.vmid)
        cmd = shlex_join(["vzdump", self.vm.vmid, "--mode", "snapshot", "--compress", "zstd"])
        await self.proxmox_session.run(cmd, capture_output=False, mutable=True)

    async def start_vm(self) -> None:
        logger.info("Starting VM %s", self.vm.vmid)
        cmd = shlex_join(["qm", "start", self.vm.vmid])
        await self.proxmox_session.run(cmd, capture_output=False, mutable=True)
        self.vm.status = "running"

    async def fetch_ip(self) -> str | None:
        try:
            interfaces = await self.api_client.fetch_vm_interfaces(self.vm.vmid)
        except ProxmoxAPIError as exc:
            logger.error("Unable to fetch IP for VM %s: %s", self.vm.vmid, exc)
            return None
        for iface in interfaces:
            for address in iface.ip_addresses:
                if address.ip_address_type.lower() == "ipv4":
                    return address.ip_address
        return None


class ContainerAgent:
    def __init__(
        self,
        container: LXCContainer,
        proxmox_session: SSHSession,
        guest_options: GuestSSHOptions,
    ) -> None:
        self.container = container
        self.proxmox_session = proxmox_session
        self.guest_options = guest_options

    async def reconcile(self) -> None:
        logger.info("Processing CT %s (%s)", self.container.name, self.container.ctid)
        was_running = self.container.is_running
        if self.container.is_running:
            await self.stop()
        await self.backup()
        await self.start()
        ip_address = await self.fetch_ip()
        if ip_address:
            await attempt_guest_upgrade(
                ip_address=ip_address,
                default_user=self.guest_options.user,
                options=self.guest_options,
                dry_run=self.proxmox_session.dry_run,
                identifier=f"ct-{self.container.ctid}",
            )
        else:
            logger.warning("Unable to determine IP for CT %s", self.container.ctid)
        if not was_running:
            await self.stop()

    async def stop(self) -> None:
        cmd = shlex_join(["pct", "shutdown", self.container.ctid, "--timeout", "120"])
        await self.proxmox_session.run(cmd, capture_output=False, mutable=True)
        self.container.status = "stopped"

    async def backup(self) -> None:
        cmd = shlex_join(["vzdump", self.container.ctid, "--mode", "snapshot", "--compress", "zstd"])
        await self.proxmox_session.run(cmd, capture_output=False, mutable=True)

    async def start(self) -> None:
        cmd = shlex_join(["pct", "start", self.container.ctid])
        await self.proxmox_session.run(cmd, capture_output=False, mutable=True)
        self.container.status = "running"

    async def fetch_ip(self) -> str | None:
        cmd = shlex_join(["pct", "exec", self.container.ctid, "--", "hostname", "-I"])
        try:
            result = await self.proxmox_session.run(cmd, capture_output=True, mutable=False)
        except CommandExecutionError as exc:
            logger.error("Unable to fetch container IP: %s", exc)
            return None
        for token in result.stdout.split():
            if is_ipv4_address(token):
                return token
        return None


def is_ipv4_address(value: str) -> bool:
    parts = value.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(part) <= 255 for part in parts)
    except ValueError:
        return False


class ProxmoxAgent:
    def __init__(
        self,
        proxmox_session: SSHSession,
        api_client: ProxmoxAPIClient,
        guest_options: GuestSSHOptions,
        max_parallel: int,
    ) -> None:
        self.proxmox_session = proxmox_session
        self.api_client = api_client
        self.guest_options = guest_options
        self.max_parallel = max(1, max_parallel)

    async def run(self) -> None:
        try:
            vms = await self.api_client.list_vms()
        except ProxmoxAPIError as exc:
            logger.error("Cannot list VMs via API: %s", exc)
            vms = []
        await self._run_with_limit(
            [
                VirtualMachineAgent(vm, self.proxmox_session, self.api_client, self.guest_options)
                for vm in vms
            ]
        )
        try:
            containers = await self.api_client.list_containers()
        except ProxmoxAPIError as exc:
            logger.error("Cannot list containers via API: %s", exc)
            containers = []
        await self._run_with_limit(
            [ContainerAgent(ct, self.proxmox_session, self.guest_options) for ct in containers]
        )
        await self.upgrade_proxmox_host()

    async def _run_with_limit(self, agents: Sequence[Reconciler]) -> None:
        if not agents:
            return
        semaphore = asyncio.Semaphore(self.max_parallel)

        async def worker(agent: Reconciler) -> None:
            async with semaphore:
                await agent.reconcile()

        await asyncio.gather(*(worker(agent) for agent in agents))

    async def upgrade_proxmox_host(self) -> None:
        logger.info("Upgrading Proxmox host")
        try:
            release_content = await self.proxmox_session.run(
                "cat /etc/os-release", capture_output=True, mutable=False
            )
        except CommandExecutionError as exc:
            logger.error("Unable to read Proxmox OS release: %s", exc)
            return
        os_release = parse_os_release(release_content.stdout)
        package_manager = determine_package_manager(os_release)
        if not package_manager:
            logger.error("Unsupported Proxmox host OS")
            return
        command = build_upgrade_command(package_manager, use_sudo=False)
        try:
            await self.proxmox_session.run(command, capture_output=False, mutable=True)
        except CommandExecutionError as exc:
            logger.error("Host upgrade failed: %s", exc)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Proxmox guest lifecycle maintenance")
    parser.add_argument("host", help="Proxmox host IPv4/IPv6 or DNS")
    parser.add_argument("--user", default="root", help="Proxmox SSH user (default: root)")
    parser.add_argument("--identity-file", dest="identity_file", help="SSH identity for Proxmox host")
    parser.add_argument("--guest-user", dest="guest_user", default="root", help="Guest SSH user")
    parser.add_argument(
        "--guest-identity-file", dest="guest_identity_file", help="Identity file for guest SSH"
    )
    parser.add_argument(
        "--guest-ssh-extra-arg",
        dest="guest_ssh_extra_args",
        action="append",
        default=[],
        help="Additional ssh arguments for guest connections",
    )
    parser.add_argument(
        "--ssh-extra-arg",
        dest="ssh_extra_args",
        action="append",
        default=[],
        help="Additional ssh arguments for Proxmox host connection",
    )
    parser.add_argument("--api-token-id", required=True, help="Proxmox API token id (user@realm!token)")
    parser.add_argument("--api-token-secret", required=True, help="Proxmox API token secret")
    parser.add_argument("--api-node", help="Proxmox node name (defaults to first available)")
    parser.add_argument("--api-port", type=int, default=8006, help="Proxmox API port (default: 8006)")
    parser.add_argument(
        "--api-insecure",
        action="store_true",
        help="Disable TLS verification for the API (not recommended)",
    )
    parser.add_argument(
        "--max-parallel", type=int, default=2, help="Maximum concurrent guest operations (default: 2)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Log actions without changing state")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser


def ensure_valid_host_argument(parser: argparse.ArgumentParser, host: str) -> None:
    trimmed = (host or "").strip()
    if not trimmed:
        parser.error("Host/IP address is required (example: proxmox.example.com)")
    if trimmed.startswith("-"):
        parser.error(
            "Host parameter appears missing. Provide the Proxmox host before options, e.g. "
            "`proxmox_maintenance.py proxmox.example --dry-run`. "
            "To show help, run without the extra `--` (example: `proxmox_maintenance.py --help`)."
        )


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")


async def async_main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    ensure_valid_host_argument(parser, args.host)
    configure_logging(args.verbose)
    host_session = SSHSession(
        host=args.host,
        user=args.user,
        dry_run=args.dry_run,
        identity_file=args.identity_file,
        extra_args=tuple(args.ssh_extra_args),
        description="proxmox",
    )
    guest_options = GuestSSHOptions(
        user=args.guest_user,
        identity_file=args.guest_identity_file,
        extra_args=tuple(args.guest_ssh_extra_args),
    )
    async with ProxmoxAPIClient(
        host=args.host,
        port=args.api_port,
        token_id=args.api_token_id,
        token_secret=args.api_token_secret,
        node=args.api_node,
        verify_ssl=not args.api_insecure,
    ) as api_client:
        agent = ProxmoxAgent(host_session, api_client, guest_options, max_parallel=args.max_parallel)
        await agent.run()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    sys.exit(main())
