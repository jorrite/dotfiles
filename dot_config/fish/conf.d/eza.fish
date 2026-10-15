# Use eza as a drop-in ls replacement in interactive shells. Guarded so
# fish still starts cleanly before Homebrew has installed eza.
if status is-interactive; and type -q eza
    function ls --wraps eza --description 'eza instead of ls'
        eza --group-directories-first --icons=auto $argv
    end
    function ll --wraps eza --description 'eza long listing with git status'
        eza --long --header --git --group-directories-first --icons=auto $argv
    end
    function la --wraps eza --description 'eza long listing incl. hidden files'
        eza --long --header --git --all --group-directories-first --icons=auto $argv
    end
    function lt --wraps eza --description 'eza tree view'
        eza --tree --level=2 --group-directories-first --icons=auto $argv
    end
end
