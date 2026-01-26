$env.EDITOR = ["code", "--wait"]
$env.VISUAL = ["code", "--wait"]

$env.VOLTA_HOME = ($env.HOME | path join .volta)
$env.PATH = ($env.PATH | prepend [$"($env.HOME)/.pixi/bin", $"($env.HOME)/bin", $"($env.HOME)/.local/bin", $"($env.HOME)/.opencode/bin", $"($env.VOLTA_HOME)/bin", /home/linuxbrew/.linuxbrew/bin])

const auto_includes = $nu.default-config-dir | path join auto-includes.nu
if not ($auto_includes | path exists) {
    ^$"($nu.default-config-dir | path join nushell-sources.nu)"
}
