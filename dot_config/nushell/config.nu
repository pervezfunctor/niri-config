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

if ($nu.default-config-dir | path join .cargo | path join env.nu | path exists) {
    source ($nu.home-dir | path join .cargo | path join env.nu)
}

if ($nu.default-config-dir | path join mise.nu | path exists) {
    use ($nu.default-config-dir | path join mise.nu)
}

if ($nu.default-config-dir | path join starship.nu | path exists) {
    source ($nu.default-config-dir | path join starship.nu)
}

if ($nu.default-config-dir | path join zoxide.nu | path exists) {
    source ($nu.default-config-dir | path join zoxide.nu)
}

def has_cmd [ app: string ] {
    (which $app | is-not-empty)
}
