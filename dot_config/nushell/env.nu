$env.EDITOR = "micro"
$env.VISUAL = ["flatpak", "run", "com.visualstudio.code", "--wait"]
$env.PATH = ($env.PATH | prepend [$"($env.HOME)/bin", $"($env.HOME)/.local/bin"])

if ("~/.local/bin/mise" | path expand | path exists) {
    let mise_path = ($nu.default-config-dir | path join mise.nu)
    mise activate nu | save --force $mise_path
}

starship init nu | save -f ($nu.default-config-dir | path join starship.nu)
zoxide init nushell | save -f ($nu.default-config-dir | path join zoxide.nu)
