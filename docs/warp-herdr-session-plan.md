# Plan: a Warp window dedicated to launching herdr

Goal: a separate Warp window (not a tab mixed in with regular shell/editor
windows) that, as soon as it opens, is already running `herdr` — no typing
`herdr` and waiting every time.

## Current state

Nothing in this repo manages Warp's window/tab/session behavior today.
Searched for "warp" and for launch-configuration-shaped YAML; only these
unrelated references exist:

- `dot_aerospace.toml` routes Warp windows to AeroSpace workspace 3 by
  `app-id = 'dev.warp.Warp-Stable'` — a window-manager rule, not a Warp-side
  config.
- `dot_config/fish/conf.d/generic.fish` sets `PROMPT_TOOLKIT_NO_CPR` because
  Warp mishandles cursor-position reports — a fish-side workaround.
- `.chezmoidata/packages.yaml` lists `warp` as an installed cask.

There is no `dot_warp/`, no `dot_config/warp-terminal/`, and neither
`~/.warp/launch_configurations/` nor `~/.config/warp-terminal/` exists yet on
this machine. This would all be new.

## How Warp supports this

Warp's relevant feature is **launch configurations**: a YAML file describing
one or more windows, each with tabs, each tab with a `layout` (cwd, optional
split panes) and startup `commands`. Confirmed against current Warp docs:

- Stored at `~/.warp/launch_configurations/<name>.yaml` on macOS.
- Minimal shape:

  ```yaml
  ---
  name: Herdr
  windows:
    - tabs:
        - title: Herdr
          color: blue
          layout:
            cwd: /Users/jelfferich
            commands:
              - exec: herdr
  ```
- `cwd` must be an absolute path (`~` does not expand).
- Commands under `layout.commands` run in sequence, chained with `&&`; since
  `herdr` takes over the terminal (it's a persistent TUI session, not a
  one-shot command), it should be the *last* (here, only) command in the tab.
- A launch configuration is opened via the Command Palette ("Launch
  Configuration"), via right-click on the tab `+` button, or — the useful
  part — via a **keybinding**: every loaded launch configuration registers an
  editable action `launch_config:open:<name>` with no default key, bindable
  in `~/.config/warp-terminal/keybindings.yaml` (macOS, non-portable install)
  exactly like a built-in action.

That keybinding is what turns this into a "dedicated window": bind a chord to
`launch_config:open:Herdr` and it opens a new window already running herdr,
the same way `prefix+a` already opens the herdr-projects popup from
`dot_config/herdr/config.toml`.

## Should it be chezmoi-managed?

Yes, for the same reason `dot_config/herdr/config.toml` and
`dot_config/private_karabiner/private_karabiner.json` are: it's config that
should survive a reinstall/new machine, and the home-directory path inside
`cwd` needs templating rather than a hardcoded `/Users/jelfferich`.

Proposed new files (not yet created — see "Not implemented" below):

- `dot_warp/launch_configurations/herdr.yaml.tmpl` → `~/.warp/launch_configurations/herdr.yaml`
  ```yaml
  ---
  name: Herdr
  windows:
    - tabs:
        - title: Herdr
          color: blue
          layout:
            cwd: {{ .chezmoi.homeDir }}
            commands:
              - exec: herdr
  ```
- `dot_config/warp-terminal/keybindings.yaml` → `~/.config/warp-terminal/keybindings.yaml`
  ```yaml
  keybindings:
    - key: <pick a chord>
      command: launch_config:open:Herdr
  ```
  (Exact top-level key/shape should be checked against a real exported
  `keybindings.yaml` from Settings → Keyboard Shortcuts before committing —
  not verified against a live Warp install in this investigation, only
  against docs/search results.)

`*.md` is chezmoi-ignored in this repo but YAML is not, so both would apply
normally via `chezmoi apply`.

## Open questions

1. **Same herdr session, or an isolated one?** Plain `herdr` attaches to "the
   persistent session" — the same shared session every other `herdr`-running
   pane/window on this machine attaches to (confirmed via `herdr --help`).
   So a window dedicated to launching herdr, using bare `herdr`, would show
   the *same* workspaces/tabs as any other window already attached, not a
   separate one. If the intent is instead a visually/logically separate
   herdr workspace (e.g. a "scratch" area), use herdr's own
   `--session <name>` flag instead: `exec: herdr --session scratch`. This is
   the main thing to decide before implementing — it changes the one line
   that matters in the launch configuration.
2. **One dedicated window vs. a tab inside the main window?** The brief asks
   for a window, which is also what makes the `launch_config:open:<name>`
   keybinding useful standalone (it opens into a new window unless a
   single-window config is set as default, in which case `Cmd+Enter` also
   opens it). A tab-only version is a strict subset (drop the `windows:`
   nesting to a single tab) if a window turns out to be overkill.
3. **What key to bind?** The user already uses Hyper+H (`ctrl+alt+cmd+shift+h`,
   via Karabiner) as herdr's own in-session prefix
   (`dot_config/herdr/config.toml`). Binding `launch_config:open:Herdr` to a
   *different* chord (e.g. Hyper+Shift+H, or a plain Warp global hotkey) avoids
   clashing with that prefix, which is only meaningful once already inside a
   herdr pane.
4. Two other threads are concurrently touching this repo (ARCHITECTURE.md +
   comment pruning; an `hp` fish alias scoped to herdr panes). Neither
   overlaps with Warp launch configurations or keybindings, so no coordination
   needed there.

## Not implemented

This thread produced the plan only, per the task's primary deliverable. The
two YAML files above are sketches, not committed files — in particular, the
`keybindings.yaml` shape and the session-isolation decision (open question 1)
should be settled first, since both change the file contents rather than
being refinements on top.
