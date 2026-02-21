# Niri Config

NixOS flake based configuration featuring the Niri Wayland compositor, Home Manager, and development tools.

## Features

- **Niri** - Modern Wayland tiling compositor
- **DankMaterialShell (DMS)** - shell layer providing Bar, Launcher, etc.
- **Home Manager** - kitty, Niri and shell configuration
- **Fish** - Excellent interactive shell
- **Nushell** - Modern shell scripting language
- **Kitty** - GPU-accelerated terminal emulator
- **Zed** - GPU-accelerated text editor
- **Shell tools** - eza, fzf, zoxide, direnv, tmux, and more
- **devenv** - Development environment without devcontainers
- **volta** - Node.js version manager

## Quick Start

### New Machine Setup

Use [nixos graphical iso](https://nixos.org/download/#nix-more) to install nixos. Use either gnome or nodesktop setup(advanced). Open terminal(tty or gnome terminal) and follow the instructions below:

```bash
curl -fsSL https://raw.githubusercontent.com/pervezfunctor/niri-config/main/setup.nu > setup.nu
nix run nixpkgs#nushell setup.nu
rm setup.nu
```

This will:
1. Clone the repository to `~/niri-config`
2. Generate `vars.nix` with your username, home directory, and hostname
3. Copy/Generate hardware and system configuration files from `/etc/nixos`
4. Add files to git
5. Prompt you to rebuild the system

### Manual Setup

```bash
git clone https://github.com/pervezfunctor/niri-config.git ~/niri-config.git
cd ~/niri-config
cp /etc/nixos/* .
```

Create and edit `vars.nix` in `~/niri-config` with your username, home directory, and hostname. It should look like this:

```nix
{
  username = "your_username";
  homeDirectory = "/home/your_username";
  hostname = "your_hostname"; # on a freshly installed nixos system, hostname is typically `nixos`
}
```

`vars.nix` is useful to keep nix evaluations pure.

Stage files to git, otherwise nix won't see them.

```bash
git add vars.nix hardware-configuration.nix configuration.nix
```

Rebuild the system

```bash
sudo nixos-rebuild switch --flake .#
```

### Using with Your Own Repository

After initial setup, you may want to use this configuration with your own GitHub repository:

```bash
# Remove the original git history
rm -rf .git

# Login to GitHub CLI
gh auth login

# Create a new public repository
gh repo create niri-config --public --source=. --push
```

If you decide to reinstall nixos on the same system, you can use your own repository:

```bash
sudo nixos-rebuild switch --flake github:your_username/niri-config
```

For installing on a different system, change references to current repository in `setup.nu` and follow the same instructions.

## Testing in a VM

Running in a vm could be painfully slow, use it only for testing before actually installing it your system.

```bash
cd ~/niri-config
nu vm.nu
nu vm.nu --clean  # Remove qcow2 image
```

## Project Structure

| File | Description |
|------|-------------|
| `flake.nix` | Main flake definition, inputs, and outputs |
| `vars.nix` | User configuration (username, home, hostname) - auto-generated |
| `configuration.nix` | System-level NixOS configuration |
| `home.nix` | User-level Home Manager configuration |
| `homeModule.nix` | Home Manager wrapper module |
| `niri.nix` | Niri window manager modules (system + home) |
| `config.kdl` | Niri compositor configuration |
| `core.nix` | Core system settings (Nix, fonts, shells, services) |
| `hardware-configuration.nix` | Hardware-specific configuration - auto-generated |
| `vm-config.nix` | VM configuration for testing |
| `kitty.conf` | Kitty terminal emulator configuration |
| `setup.nu` | Initial setup script (interactive) |
| `vm.nu` | VM testing script |


### Adding Packages

Edit `home.nix` for user packages or `core.nix` for system packages.

### Configuring Niri

Edit `config.kdl` to customize keybindings, layouts, and window behavior.

### Configuring Kitty

Edit `kitty.conf` to customize Kitty terminal emulator settings.
