#!/usr/bin/env nu

const REPO_URL = "https://github.com/pervezfunctor/niri-config.git"
let DOT_DIR = $"($env.HOME)/.niri-config"

def prompt_yn [message: string] {
  let response = (input $"($message) [y/N]: " | str trim | str downcase)
  $response == "y" or $response == "yes"
}

def main [] {
  if ($DOT_DIR | path exists) {
    print "Repository already exists."
  } else {
    print $"Cloning repository to ($DOT_DIR)..."
    ^nix run nixpkgs#git -- clone $REPO_URL $DOT_DIR
  }

  if not ($DOT_DIR | path join "vars.nix" | path exists) {
    let username = (whoami | str trim)
    let homeDirectory = ($env.HOME | str trim)
    let host = (hostname | str trim)

    print "Generating vars.nix..."
    let vars_content = $"{\n  username = \"($username)\";\n  homeDirectory = \"($homeDirectory)\";\n  hostname = \"($host)\";\n}"
    $vars_content | save -f $"($DOT_DIR)/vars.nix"
  }

  if not ($DOT_DIR | path join "configuration.nix" | path exists) {
    print "Copying NixOS configuration..."
    for file in (glob /etc/nixos/*) {
      cp $file $DOT_DIR
    }
  }

  if ($DOT_DIR | path join ".git" | path exists) {
    print "Staging changes..."
    ^git -C $DOT_DIR add .
  }

  print "Rebuilding NixOS..."
  if (prompt_yn "Do you want to rebuild NixOS now?") {
    ^sudo nixos-rebuild switch --flake $"($DOT_DIR)#"
  } else {
    print "Rebuild NixOS with 'nixos-rebuild switch --flake ($DOT_DIR)#' when you're ready."
  }

  print "Setup complete!"
}
