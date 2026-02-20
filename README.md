# Niri Config

NixOS flake configuration featuring the Niri Wayland compositor, Home Manager, and a curated development environment.

## Features

- **Niri** - Modern Wayland tiling compositor
- **DankMaterialShell (DMS)** - Material Design-inspired shell layer
- **Home Manager** - Declarative user environment management
- **Nushell** - Modern shell with powerful data manipulation
- **Kitty** - GPU-accelerated terminal emulator
- **Editor** - Zed 
- **Development tools** - eza, fzf, zoxide, direnv, tmux, and more

## Quick Start

### New Machine Setup

```bash
# Clone, configure, and rebuild in one command
curl -sL https://raw.githubusercontent.com/pervezfunctor/niri-config/main/setup.nu | nu
```

This will:
1. Clone the repository to `~/niri-config`
2. Generate `vars.nix` with your username, home directory, and hostname
3. Copy/Generate hardware and system configuration files
4. Add files to git
5. Prompt you to rebuild the system

### Manual Setup

```bash
git clone https://github.com/pervezfunctor/niri-config.git ~/niri-config
cd ~/niri-config
nu setup.nu
sudo nixos-rebuild switch --flake .#
```

## Testing in a VM

```bash
cd ~/niri-config
nu run-vm.nu
nu run-vm.nu --clean  # Remove qcow2 image
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
| `run-vm.nu` | VM testing script |


### Adding Packages

Edit `home.nix` for user packages or `core.nix` for system packages.

### Configuring Niri

Edit `config.kdl` to customize keybindings, layouts, and window behavior.

### Configuring Kitty

Edit `kitty.conf` to customize Kitty terminal emulator settings.
