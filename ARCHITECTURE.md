# Sandboxing architecture: herdr, cs, and nono

This repo wires together three independent tools so that every `claude`
invocation inside a [herdr](https://github.com/eliasstravik/herdr) pane runs
inside a [nono](https://github.com/nolabs-ai/nono) sandbox, scoped to
whatever repo it's running in. No piece knows about the others' internals —
they compose through a small set of env vars, a fish function, and a
generated JSON profile.

## The three pieces

- **herdr** — a terminal pane/session manager. It sets `$HERDR_ENV` in every
  pane it spawns, including panes its `herdr-projects` plugin creates for
  project coordinators and worker threads. `dot_config/herdr/config.toml`
  pins `default_shell = "fish"` for all panes so the fish interception below
  always applies, even to daemon-spawned panes (herdr types commands into a
  pane's real interactive shell rather than spawning them server-side).
- **nono** — the actual OS-level sandbox. It runs a target binary under a
  named profile (`~/.config/nono/profiles/*.json`) that declares filesystem
  grants, network policy, and per-command policies for child processes it
  mediates (git, gh, ssh, ...).
- **cs** (`cs-launch`) — "claude sandbox": the glue script that generates a
  profile for the current repo and launches the real `claude` binary under
  `nono run` with it.

## Control flow: launching `claude` inside a herdr pane

1. **`dot_config/fish/functions/claude.fish`** shadows `claude`. If
   `$HERDR_ENV` is set (true in any herdr-managed pane), it calls
   `cs-launch` instead of the real binary. Outside herdr it passes through
   unchanged — there is no unsandboxed path for `claude` inside herdr.
2. **`cs-launch`** (`dot_local/bin/executable_cs-launch`):
   - sources `agent-sandbox-ssh-setup`, which pulls a dedicated git/ssh
     signing key out of 1Password into a PID-suffixed file under
     `~/.cache/agent-sandbox-ssh-keys/` and registers a `trap` to delete it
     on exit (sourced rather than exec'd so the trap lives in `cs-launch`'s
     own shell and actually fires);
   - runs `agent-sandbox-profile` to (re)generate a nono profile scoped to
     the current repo and capture its name;
   - resolves the real `claude` binary via `mise which claude` rather than a
     bare `claude` on `$PATH`, so it can't resolve back to the fish function
     and recurse;
   - exports `HERDR_AGENT=claude` when inside a herdr pane — nono's startup
     banner sits in front of claude's own output, which breaks herdr's
     screen-pattern agent detection, so this tells herdr directly what's
     running instead;
   - runs (not execs, so its own `trap` still fires on exit)
     `nono run --profile nolabs-ai/claude --extends <generated-profile> -- <real claude>`.
3. **`agent-sandbox-profile`** (`dot_local/bin/executable_agent-sandbox-profile`)
   generates the per-repo profile that `cs-launch` extends:
   - identifies the current repo by `git rev-parse --show-toplevel`, and
     parses the `origin`/`upstream` remotes (GitHub only) to scope `ssh`'s
     allowed `git-upload-pack`/`git-receive-pack` argv and `gh`'s allowed
     REST paths to exactly those repos. No repo discovered → read-only
     everywhere, push denied at the git layer;
   - names the profile deterministically from a hash of the repo's toplevel
     path, so every subdirectory of the same repo maps to (and overwrites)
     the same file — there's nothing to clean up between sessions;
   - detects whether it's running as a herdr-projects coordinator (a
     `PROJECT.md` in cwd) and, if so, additionally grants herdr's control
     socket, read access to the project's own repos, and the herdr
     worktrees directory, so the coordinator can run git preflight checks
     against those repos and manage worker threads;
   - declares `command_policies` for `git`, `gh`, `ssh`, `ssh-keygen`, and
     the `agent-sandbox-ssh-askpass` helper, wiring git to sign commits with
     the dedicated key (via `ssh-keygen` as `gpg.ssh.program`) and to push
     only through the scoped `ssh` argv policy, and `gh` to call the GitHub
     API through a proxied `github-pat` credential (from 1Password) instead
     of an env var the sandboxed process could read directly;
   - `extends: "agent-sandbox-base"`
     (`dot_config/nono/profiles/agent-sandbox-base.json`), which only adds
     agent-agnostic toolchain grants (mise, go) on top of nono's built-in
     `default` profile — it has no `command_policies` of its own and isn't
     meant to run standalone.
4. **nono** composes `nolabs-ai/claude` (the baseline claude sandbox) with
   the generated profile (which itself extends `agent-sandbox-base`), then
   runs the real `claude` binary inside it. From here, every `git`, `gh`,
   `ssh`, and `ssh-keygen` invocation claude makes is intercepted and
   re-mediated against the policies above rather than running unconstrained.

## Coordinators, worker threads, and the herdr socket

`herdr-projects` coordinators and the worker threads they spawn are just
more panes under herdr, so they go through the exact same
fish-function → `cs-launch` → `nono run` path. Every session (not only
coordinators) is granted the herdr control socket
(`~/.config/herdr/herdr.sock`) and read access to
`~/.herdr-projects/.progress`, since `herdr-projects report` needs to call
back over that socket to identify which pane it's running in — env vars
alone aren't enough, and worker threads can themselves spawn sub-threads.
Coordinators additionally get the broader repo/worktree grants described
above, since they operate on project repos directly rather than through a
single sandboxed cwd.

## Secrets

The dedicated signing/transport ssh key and its passphrase, and the
`github-pat` used by `gh`, all come from 1Password (`op://...` references)
and are materialized fresh per invocation — never an ambient `ssh-agent`,
never checked into the repo. The key file and its passphrase env var are
scoped only to the `ssh`/`ssh-keygen` command edges that need them; `gh`
never sees the PAT directly, only a proxied credential injected by nono.
