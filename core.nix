{ pkgs, vars, ... }:
{
  services.displayManager.plasma-login-manager.enable = true;
  hardware.enableRedistributableFirmware = true;
  nixpkgs.config.allowUnfree = true;

  services.xserver.enable = true;
  services.xserver.xkb.options = "caps:ctrl_modifier";

  environment.sessionVariables = {
    XCURSOR_SIZE = "32";
    XCURSOR_THEME = "Bibata-Modern-Ice";
    ELECTRON_OZONE_PLATFORM_HINT = "auto";
    QT_QPA_PLATFORM = "wayland";
    QT_QPA_PLATFORMTHEME = "gtk3";
    QT_QPA_PLATFORMTHEME_QT6 = "gtk3";
  };

  security.rtkit.enable = true;
  security.polkit.enable = true;
  # security.pam.services.gdm.enableGnomeKeyring = true;
  security.pam.services.login.enableGnomeKeyring = true;

  services.dbus.enable = true;
  services.gnome.gnome-keyring.enable = true;

  services.udisks2.enable = true;
  services.gvfs.enable = true;
  services.tumbler.enable = true;
  programs.thunar.enable = true;
  programs.xfconf.enable = true;

  xdg.portal = {
    enable = true;
    wlr.enable = true;
    extraPortals = [
      pkgs.xdg-desktop-portal-gtk
      pkgs.xdg-desktop-portal-gnome
    ];
    config = {
      common = {
        default = [ "gnome" ];
      };
    };
  };

  services.pipewire = {
    enable = true;
    alsa.enable = true;
    pulse.enable = true;
    jack.enable = false;
    wireplumber.enable = true;
  };

  nix = {
    settings = {
      experimental-features = [
        "nix-command"
        "flakes"
      ];
      auto-optimise-store = true;
    };
    gc = {
      automatic = true;
      dates = "daily";
      options = "--delete-older-than 7d";
      persistent = true;
    };
  };

  programs.nix-ld.enable = true;
  services.flatpak.enable = true;
  programs.appimage = {
    enable = true;
    binfmt = true;
  };

  fonts = {
    fontconfig.enable = true;
    packages = with pkgs; [
      fira-code
      font-awesome
      inter
      inter-nerdfont
      nerd-fonts.jetbrains-mono
      nerd-fonts.monaspace
      noto-fonts
      noto-fonts-color-emoji
    ];
  };

  users.extraGroups.video.members = [ vars.username ];

  users.defaultUserShell = pkgs.fish;
  programs.bash.enable = true;
  programs.neovim.enable = true;
  programs.fish = {
    enable = true;
    shellInit = ''
      set -gx PATH "$HOME/.local/bin" "$PATH"
    '';
    shellAliases = {
      gst = "git status";
      gcm = "git commit -m";
      gp = "git push";
      gfm = "git pull";
      gia = "git add .";
      gcb = "git checkout -b";
      nrs = "sudo nixos-rebuild switch --flake .#";
    };
  };

  programs.starship = {
    enable = true;
    interactiveOnly = true;
    transientPrompt.enable = true;
  };

  services.passSecretService.enable = true;

  environment.systemPackages = with pkgs; [
    adwaita-fonts
    adwaita-icon-theme
    cliphist
    cmake
    curl
    dbus
    dnsmasq
    gcc
    gcr
    git
    gnumake
    libsecret
    udiskie
    udisks2
    unzip
    wget
    wl-clipboard
  ];
}
