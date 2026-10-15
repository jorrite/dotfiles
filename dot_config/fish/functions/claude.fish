# Always run claude sandboxed via cs-launch -- inside a herdr pane
# (coordinator or worker thread) and from a plain interactive terminal
# alike. No unsandboxed `claude` at all; `claude-yolo` is the deliberate,
# clearly-named escape hatch for when that's actually wanted.
function claude
    cs-launch $argv
end
