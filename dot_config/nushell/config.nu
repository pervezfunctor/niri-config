$env.config = {
    show_banner: false
}

def jupyter-lab [] {
    let jupyter_dir = ($nu.home-path | path join jupyter-lab)

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

if (($nu.home-path | path join .cargo/env.nu) | path exists) {
    source $"($nu.home-path)/.cargo/env.nu"
}

if (($nu.default-config-dir | path join mise.nu) | path exists) {
    use ($nu.default-config-dir | path join mise.nu)
}


source ($nu.default-config-dir | path join starship.nu)
source ($nu.default-config-dir | path join zoxide.nu)

alias c = flatpak run com.visualstudio.code
alias code = flatpak run com.visualstudio.code
alias g = git
alias h = btm
alias i = pickman install
alias p = pickman
alias t = tmux
alias v = nvim
alias s = rg
alias f = fd-find

alias gs = git stash -u 
alias gp = git push
alias gb = git branch
alias gbc = git checkout -b
alias gsl = git stash list
alias gst = git status 
alias gsu = git status -u 
alias gcan = git commit --amend --no-edit 
alias gsa = git stash apply
alias gfm = git pull
alias gcm = git commit --message
alias gia = git add
alias gco = git checkout
