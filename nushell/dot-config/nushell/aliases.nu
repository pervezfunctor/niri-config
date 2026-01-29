alias c = code
alias g = git
alias h = btm
alias i = pikman install
def u [] {
    pikman update
    pikman upgrade
}
alias p = pikman
alias pi = pixi global install
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

alias stls = sudo systemctl status
alias stle = sudo systemctl enable --now
alias stld = sudo systemctl disable
alias stlp = sudo systemctl stop
alias stlr = sudo systemctl restart
alias stlg = sudo systemctl list-units
alias stlf = sudo systemctl list-units --all --state=failed

alias utle = systemctl --user enable --now
alias utld = systemctl --user disable
alias utlp = systemctl --user stop
alias utlr = systemctl --user restart
alias utlg = systemctl --user list-units
alias utlf = systemctl --user list-units --all --state=failed
alias uv-jupyter-standalone = uv tool run jupyter lab
alias uv-marimo-standalone = uvx marimo edit --sandbox
