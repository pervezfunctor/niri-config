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
