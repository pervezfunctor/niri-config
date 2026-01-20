$env.config = {
    show_banner: false
}

def jupyter-lab [] {
    let jupyter_dir = ($nu.home-dir | path join jupyter-lab)

    if not ($jupyter_dir | path exists) {
        error make {
            msg: "Directory does not exist"
            label: {
                text: $jupyter_dir
                span: (metadata $jupyter_dir).span
            }
        }
    }

    let jupyter = ($jupyter_dir | path join .venv | path join bin | path join jupyter)
    if not ($jupyter | path exists) {
        error make { msg: "Virtual environment not found" }
    }

    ^$jupyter lab
}

def 'has_cmd' [ app: string ] {
  (which $app | is-not-empty)
}

if ("~/.cargo/env.nu" | path expand | path exists) {
    source ~/.cargo/env.nu
}

if ("~/.config/nushell/mise.nu" | path expand | path exists) {
    use ~/.config/nushell/mise.nu
}

source ~/.config/nushell/starship.nu
source ~/.config/nushell/zoxide.nu
