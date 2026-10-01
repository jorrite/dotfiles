# Run Claude Code sandboxed via nono, scoped to the current repo (must be
# run inside a herdr pane)
abbr -a cs 'cs-launch'

# Shorthand for the herdr-projects CLI (already resolvable on PATH once the
# plugin is installed; --root defaults sensibly on its own). Only defined
# inside herdr panes ($HERDR_ENV, set by herdr itself -- see
# dot_config/fish/functions/claude.fish), not globally in every shell.
if set -q HERDR_ENV
    abbr -a hp herdr-projects
end
