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

def has_cmd [ app: string ] {
    (which $app | is-not-empty)
}

def uv-marimo-standalone [] {
    uvx --with pyzmq --from "marimo[sandbox]" marimo edit --sandbox
}

def uv-jupyter-standalone [] {
    uv tool run jupyter lab
}

source ($nu.default-config-dir | path join auto-includes.nu)
source ($nu.default-config-dir | path join aliases.nu)

def reinit [] {
    ^$"($nu.default-config-dir | path join nushell-sources.nu)"
}
