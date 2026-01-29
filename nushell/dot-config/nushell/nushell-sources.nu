#!/usr/bin/env nu

def main [--verbose (-v)] {
    let file_configs = [
        "~/.config/nushell/work.nu"
        "~/.config/nushell/personal.nu"
        "~/.config/nushell/secrets.nu"
    ]

    let tools = [
        [name, command];
        [starship, {|| starship init nu }],
        [zoxide, {|| zoxide init nushell }],
        [mise, {|| ^mise activate nu }],
        [carapace, {|| carapace _carapace nushell }]
    ]

    def vprint [message] {
    if $verbose { print $"$message\n" }
    }

    vprint "Generating tool configs..."

    let tool_sources = $tools | each { |tool|
        let output_file = $nu.default-config-dir | path join $"($tool.name).nu"

        if (which $tool.name | is-not-empty) {
            do $tool.command | save -f $output_file
            vprint $"✓ Generated ($tool.name).nu"
            $"source ($output_file)"
        } else {
            "" | save -f $output_file
            vprint $"⊘ ($tool.name) not found - created empty ($tool.name).nu"
            $"source ($output_file)"
        }
    }

    vprint "Generating conditional includes..."

    let config_sources = $file_configs
        | each { |f| $f | path expand }
        | where { |f| $f | path exists }
        | each { |f|
            vprint $"✓ Found ($f)"
            $"source ($f)"
        }

    let all_sources = $tool_sources | append $config_sources | str join "\n"
    let includes_file = $nu.default-config-dir | path join auto-includes.nu
    $all_sources | save -f $includes_file
    vprint $"✓ Generated ($includes_file) with all includes"
}
