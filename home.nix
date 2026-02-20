{
  inputs,
  vars,
  pkgs,
  ...
}:
{
  home.username = vars.username;
  home.homeDirectory = vars.homeDirectory;
  home.stateVersion = "26.05";

  imports = [ inputs.dms.homeModules.dank-material-shell ];

  programs.dank-material-shell = {
    enable = true;
    systemd = {
      enable = false;
      restartIfChanged = true;
    };
  };

  home.pointerCursor = {
    package = pkgs.bibata-cursors;
    name = "Bibata-Modern-Ice";
    size = 24;
  };

  home.packages = with pkgs; [
    bat
    bottom
    devbox
    devenv
    fd
    gdu
    gh
    jq
    imagemagick
    kitty
    lazygit
    luarocks
    mermaid-cli
    nil
    nixd
    nixfmt
    nufmt
    nushell
    ripgrep
    tealdeer
    tmux
    trash-cli
    tree
    tree-sitter
    zed-editor
  ];

  programs = {
    home-manager.enable = true;

    librewolf.enable = true;
    nushell = {
      enable = true;
      plugins = [ pkgs.nushellPlugins.formats ];
      settings = {
        show_banner = false;
      };
    };

    eza = {
      enable = true;
      enableFishIntegration = true;
      enableNushellIntegration = true;
    };

    starship = {
      enable = true;
      enableFishIntegration = true;
      enableZshIntegration = true;
      enableNushellIntegration = true;
    };

    carapace = {
      enable = true;
      enableFishIntegration = true;
      enableNushellIntegration = true;
    };

    fzf = {
      enable = true;
      enableFishIntegration = true;
    };

    zoxide = {
      enable = true;
      enableFishIntegration = true;
      enableNushellIntegration = true;
    };

    direnv = {
      enable = true;
      nix-direnv.enable = true;
      enableFishIntegration = true;
      enableNushellIntegration = true;
    };
  };

  home.file = {
    ".config/kitty/kitty.conf" = {
      source = ./kitty.conf;
      force = true;
    };
  };
}
