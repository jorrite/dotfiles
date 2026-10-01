# Inside any herdr pane ($HERDR_ENV is set there automatically, including
# panes herdr's own daemon spawns for herdr-projects coordinators/worker
# threads), always run claude sandboxed via cs-launch instead of the real
# binary -- there is no unsandboxed escape hatch for `claude` inside herdr.
# Outside herdr, this passes straight through unchanged.
function claude
    if set -q HERDR_ENV
        cs-launch $argv
    else
        command claude $argv
    end
end
