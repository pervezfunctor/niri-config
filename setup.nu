#!/usr/bin/env nu

const REPO_URL = "https://github.com/pervezfunctor/niri-config.git"

def main [] {
  let repo_dir = $"($env.HOME)/niri-config"

  print $"Cloning repository to ($repo_dir)..."
  ^nix run nixpkgs#git -- clone $REPO_URL $repo_dir

  let username = (whoami | str trim)
  let homeDirectory = ($env.HOME | str trim)
  let hostname = (hostname | str trim)

  print "Generating vars.nix..."
  $"
{
  username = \"($username)\";
  homeDirectory = \"($homeDirectory)\";
  hostname = \"($hostname)\";
}
" | save $"($repo_dir)/vars.nix"

  print "Generating NixOS configuration..."
  ^nixos-generate-config --dir $repo_dir

  print "Adding files to git..."
  ^git -C $repo_dir add vars.nix hardware-configuration.nix configuration.nix

  print "Rebuilding NixOS..."
  ^sudo nixos-rebuild switch --flake $"($repo_dir)#nixos"
}
