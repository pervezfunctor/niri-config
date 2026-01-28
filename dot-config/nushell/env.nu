$env.EDITOR = ["code", "--wait"]
$env.VISUAL = ["code", "--wait"]

$env.PNPM_HOME = $"($env.HOME)/.local/share/pnpm"
$env.VOLTA_HOME = ($env.HOME | path join .volta)
$env.PATH = ($env.PATH | prepend [$"($env.HOME)/.pixi/bin", $"($env.HOME)/bin", $"($env.HOME)/.local/bin", $"($env.VOLTA_HOME)/bin", $"($env.PNPM_HOME)", /home/linuxbrew/.linuxbrew/bin])

$env.CARAPACE_BRIDGES = 'zsh,fish,bash,inshellisense' # optional

const auto_includes = $nu.default-config-dir | path join auto-includes.nu
if not ($auto_includes | path exists) {
    ^$"($nu.default-config-dir | path join nushell-sources.nu)"
}
