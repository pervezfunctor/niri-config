# Linux Setup for developers on PikaOS/Fedora/Ubuntu

`dotfiles` from this repository can be used to setup development workstation using `niri` as your window manager.


## Operating Systems Supported

### PikaOS Niri Edition

I currently use this setup on [PikaOS](https://wiki.pika-os.com/en/home). PikaOS is based on Debian. I replace `pikabar` and related utilities with [dms](https://danklinux.com/).

If you have never used PikaOS before, I would recommend you to spend a few days with the default `niri` setup before switching to this.

Note that system package manager(`apt`) is painfully slow compared to `dnf` or `pacman` and setup will take a long time.

### Fedora OS

Setup script can optionally install `niri` and `dms` on Fedora. This is the secondary OS I use fairly regularly. You could install Fedora using any of it's official variants, something like sway should work fine too. I use `Fedora Everything` to install basic system software and use script from this repository to setup niri.

### Ubuntu Questing(25.04)

I don't use Ubuntu. Even though I believe this should work fine, this setup might not work currently. I would recommend you to either use Fedora or PikaOS.

### NixOS

If you are using NixOS, use my [nixos-config](https://github.com/pervezfunctor/nix-config) repository.


## Setup

Use the following script and select what you need. You MUST select at least system packages and dotfiles on the first run. You could run this script multiple times to select different options.

```bash
bash -c "$(curl -sSL https://raw.githubusercontent.com/pervezfunctor/linux-config/refs/heads/master/bin/bootstrap)" -- all
```

If you need docker run the following script to install docker inside a VM and use `devpod` for development.

```bash
~/.local/share/linux-config/bin/docker-vm
```

If you wish to install additional packages, first see if you operating system package manager has it. For eg.

```bash
# On PikaOS
pikman install <package>

# On Fedora
sudo dnf install <package>

# On Debian/Ubuntu
sudo apt install <package>
```

If the package is not available in your operating system package manager, you could try installing it with `pixi` or `brew`. For eg.

```bash
# With pixi
pixi global install <package>

# With brew
brew install <package>
```

For development environment consider mise, it's simple and efficient. You could also use nix.

For desktop apps, try flatpak first. If `Bazaar` is installed you could use it to install apps. Or

```bash
flatpak install --user flathub <package>
```

You can also install `nix` with above script, and use `home-manager` to manage your system. You need to modify nix files to add/remove packages.

## Logs

Every invocation of the bootstrap script records a timestamped log file under `~/.linux-config-logs`. Set `LINUX_CONFIG_LOG_DIR=/path/to/logs` if you want to capture runs elsewhere (useful in disposable environments or CI). Once the repository is cloned you can inspect or prune logs with the helper script:

```bash
~/.local/share/linux-config/bin/logs show           # view the most recent log
~/.local/share/linux-config/bin/logs show --select  # pick a specific timestamp interactively
~/.local/share/linux-config/bin/logs clean          # keep only the latest log
```

Pass `--dir /alternate/path` (before the `show`/`clean` command) or export `LINUX_CONFIG_LOG_DIR` to inspect archives that live outside the default location.

## Proxmox Maintenance Helpers

`py/proxmox_maintenance.py` handles lifecycle tasks (backup, shutdown, upgrade, restart) for a single Proxmox node. The new batch wrapper `py/proxmox_batch.py` coordinates multiple hosts defined in `py/proxmox-hosts.toml`.

### Manifest format

The manifest lives alongside the scripts so it can be versioned:

```toml
[defaults]
user = "root"
guest.user = "root"
identity_file = "~/.ssh/proxmox"
guest.identity_file = "~/.ssh/guest"
ssh.extra_args = ["-J", "bastion"]
guest.ssh.extra_args = ["-o", "StrictHostKeyChecking=no"]
max_parallel = 2
dry_run = false

[[hosts]]
name = "prod-a"
host = "proxmox-a.example.com"
api.node = "pve-a"
api.token_env = "PROXMOX_A_TOKEN"
api.secret_env = "PROXMOX_A_SECRET"

[[hosts]]
name = "prod-b"
host = "proxmox-b.example.com"
ssh.identity_file = "~/.ssh/proxmox-b"
guest.user = "admin"
api.token_env = "PROXMOX_B_TOKEN"
api.secret_env = "PROXMOX_B_SECRET"
dry_run = true
```

Each host entry must define the environment variables that hold its API token ID and secret. Export them (for example via `direnv`, a `.envrc`, or CI secrets) before running the batch tool.

### Usage

Run everything:

```bash
uv run proxmox_batch.py --dry-run
```

Only specific hosts:

```bash
uv run proxmox_batch.py --host prod-a --host prod-b
```

The batch process stops if the manifest is invalid, reports credential issues (missing env vars) with exit code `2`, and returns `3` if any host run fails. Use `Maskfile` shortcuts such as `mask proxmox:batch -- --host prod-a` for convenience.

### Interactive manifest editor

Launch an interactive Questionary wizard to add hosts, tweak defaults, or clean up existing manifests without hand-editing TOML:

```bash
uv run proxmox_config_wizard.py --config py/proxmox-hosts.toml
```

The wizard preserves unknown keys and validates the file with `proxmox_batch.py` before saving. `mask proxmox:config` opens the same workflow.

### Guest inventory builder

When you want to inspect a Proxmox host, discover its VMs/containers, and capture per-guest SSH credentials (including optional password env vars) run:

```bash
uv run proxmox_inventory_builder.py --config py/proxmox-hosts.toml
```

The script:

- Asks for the Proxmox API host/SSH details (or lets you add a new manifest entry on the fly).
- Connects to the API to list VMs and LXCs, grabbing IPs via QEMU guest agent or `pct exec`.
- Prompts for each guest's SSH username/password handling, verifies SSH using your configured key, and can install the key if only a password is available.
- Writes all captured metadata back under the corresponding `[[hosts]]` entry in `py/proxmox-hosts.toml`, preserving the format expected by `proxmox_maintenance`.
