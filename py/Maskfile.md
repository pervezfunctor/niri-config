# Maskfile

## lint
Run Ruff lint checks.
```sh
uv run --extra dev ruff check
```

## lint:fix
Run Ruff lint checks and attempt to fix any issues.
```sh
uv run --extra dev ruff check --fix
```

## format
Format code using Ruff's formatter.
```sh
uv run --extra dev ruff format
```

## test
Execute unit tests for the Proxmox helpers.
```sh
uv run --extra dev pytest
```

## typecheck
Run Pyright in strict mode.
```sh
uv run --extra dev pyright
```

## proxmox:dry-run
Example dry-run against a Proxmox host (override arguments as needed).
```sh
uv run proxmox_maintenance.py "$@" --dry-run
```

## proxmox:run
Run the maintenance script with custom arguments passed through.
```sh
uv run proxmox_maintenance.py "$@"
```

## proxmox:batch
Run maintenance across every host defined in the manifest (override args as needed).
```sh
uv run proxmox_batch.py "$@"
```

## proxmox:config
Launch the interactive manifest wizard to add or edit host entries.
```sh
uv run proxmox_config_wizard.py "$@"
```

## proxmox:inventory
Discover guests on a host, verify SSH, and update the manifest with credentials.
```sh
uv run proxmox_inventory_builder.py "$@"
```
