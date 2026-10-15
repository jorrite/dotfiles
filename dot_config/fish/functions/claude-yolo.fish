# Deliberate, clearly-named escape hatch: runs the real, unsandboxed
# claude binary directly, bypassing cs-launch entirely. `claude` itself
# always sandboxes now, with no exception for a plain interactive
# terminal -- this exists for when that's a real, considered choice, not
# the default.
#
# Resolved via mise rather than a bare "claude" on PATH: that would just
# re-resolve back to this shell's own `claude` function and recurse.
function claude-yolo
    command (mise which claude) $argv
end
