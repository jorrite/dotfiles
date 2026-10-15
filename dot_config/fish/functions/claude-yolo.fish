# Escape hatch: runs the real, unsandboxed claude binary directly.
# Resolved via mise, not a bare "claude", to avoid recursing into this
# shell's own `claude` function.
function claude-yolo
    set -l claude_bin (mise which claude)
    command $claude_bin $argv
end
