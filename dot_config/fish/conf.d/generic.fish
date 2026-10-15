set -x PATH ~/.local/bin $PATH
set -x PROMPT_TOOLKIT_NO_CPR 1 # needed because Warp does not handle CPR well

# herdr-projects spawns claude as a raw child process (Rust's
# Command::new, no shell involved), using whatever PATH this pane's
# shell has at that moment. mise's dynamic fish activation keeps
# re-prepending each tool's own install dir ahead of ~/.local/bin on
# every prompt, which would otherwise make that spawn find the real
# claude binary instead of dot_local/bin/claude. Erasing mise's hooks
# and fixing PATH once keeps it stable -- scoped to herdr panes only,
# so normal interactive mise usage elsewhere is unaffected.
if set -q HERDR_ENV
    functions -e __mise_cd_hook __mise_env_eval_on_prompt __mise_env_eval_2 2>/dev/null
    set -x PATH ~/.local/bin $PATH
end
