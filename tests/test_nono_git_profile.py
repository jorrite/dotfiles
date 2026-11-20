"""Tests for nono-git-profile and git-session-hook. Run from the repo root:

    PYTHONDONTWRITEBYTECODE=1 uv run --no-project python -m unittest discover -s tests -v

Nothing here touches the network, 1Password or the real nono profile directory.
"""

import importlib.machinery
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

# The generator is imported from the chezmoi source tree, where bytecode must not land.
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent
GENERATOR = ROOT / "dot_local" / "bin" / "executable_nono-git-profile"
HOOK = ROOT / "dot_config" / "nono" / "hooks" / "executable_git-session-hook"
BASE = ROOT / "dot_config" / "nono" / "profiles" / "agent-base.json"
HERDR = ROOT / "dot_config" / "nono" / "profiles" / "herdr.json"
CS_LAUNCH = ROOT / "dot_local" / "bin" / "executable_cs-launch"

_loader = importlib.machinery.SourceFileLoader("nono_git_profile", str(GENERATOR))
_spec = importlib.util.spec_from_loader("nono_git_profile", _loader)
ngp = importlib.util.module_from_spec(_spec)
sys.modules["nono_git_profile"] = ngp
_loader.exec_module(ngp)

HAVE_NONO = shutil.which("nono") is not None
HAVE_GIT = shutil.which("git") is not None


def short_tmp() -> Path:
    """A short temp dir: unix socket paths are limited to about 100 bytes on macOS."""
    return Path(tempfile.mkdtemp(dir="/private/tmp" if Path("/private/tmp").is_dir() else None))


def git(*args, cwd, env=None):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env={**os.environ, **(env or {})})


class ParseRemote(unittest.TestCase):
    def test_accepted_forms(self):
        cases = {
            "https://github.com/jorrite/mote.git": ("github.com", "jorrite/mote"),
            "https://github.com/jorrite/mote": ("github.com", "jorrite/mote"),
            "https://github.com/jorrite/mote/": ("github.com", "jorrite/mote"),
            "git@github.com:jorrite/mote.git": ("github.com", "jorrite/mote"),
            "ssh://git@github.com/jorrite/mote.git": ("github.com", "jorrite/mote"),
            "ssh://git@github.com:22/jorrite/mote.git": ("github.com", "jorrite/mote"),
            "https://user:secret@github.com/jorrite/mote.git": ("github.com", "jorrite/mote"),
            "https://GitHub.com/Jorrite/Mote.git": ("github.com", "Jorrite/Mote"),
            "https://gitlab.com/group/project.git": ("gitlab.com", "group/project"),
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(ngp.parse_remote(url), expected)

    def test_rejected_forms(self):
        for url in ["", "/Users/me/repo", "../relative", "file:///srv/repo.git", "https://github.com/jorrite",
                    "https://github.com/a/b/c", "https://github.com//repo"]:
            with self.subTest(url=url):
                self.assertIsNone(ngp.parse_remote(url))


@unittest.skipUnless(HAVE_GIT, "git not installed")
class OriginRemote(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.gitconfig = self.tmp / "gitconfig"
        self.gitconfig.write_text("")
        patcher = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(self.gitconfig), "GIT_CONFIG_SYSTEM": "/dev/null"})
        patcher.start()
        self.addCleanup(patcher.stop)
        git("init", "-q", cwd=self.repo)

    def test_reads_origin_and_ignores_other_remotes(self):
        git("remote", "add", "upstream", "git@github.com:cloudposse/atmos.git", cwd=self.repo)
        git("remote", "add", "origin", "https://github.com/jorrite/atmos.git", cwd=self.repo)
        self.assertEqual(ngp.origin_remote(str(self.repo)), ("github.com", "jorrite/atmos"))

    def test_applies_instead_of_rewrites(self):
        self.gitconfig.write_text('[url "git@github.com:"]\n\tinsteadOf = https://github.com/\n')
        git("remote", "add", "origin", "https://github.com/jorrite/mote.git", cwd=self.repo)
        self.assertEqual(ngp.origin_remote(str(self.repo)), ("github.com", "jorrite/mote"))

    def test_other_hosts_are_reported_as_such(self):
        git("remote", "add", "origin", "https://gitlab.com/group/project.git", cwd=self.repo)
        self.assertEqual(ngp.origin_remote(str(self.repo)), ("gitlab.com", "group/project"))

    def test_no_origin_and_not_a_repo(self):
        self.assertIsNone(ngp.origin_remote(str(self.repo)))
        self.assertIsNone(ngp.origin_remote(str(self.tmp)))


class EndpointRules(unittest.TestCase):
    def test_every_repo_is_readable_and_nothing_is_writable_by_default(self):
        rules = ngp.endpoint_rules(None)
        self.assertEqual(rules, [{"method": "GET", "path": "/*/*/info/refs"}, {"method": "POST", "path": "/*/*/git-upload-pack"}])
        self.assertFalse(any("receive-pack" in r["path"] for r in rules))

    def test_only_the_write_target_gets_receive_pack_in_both_url_forms(self):
        rules = ngp.endpoint_rules("jorrite/atmos")
        pushes = [r for r in rules if "receive-pack" in r["path"]]
        self.assertEqual(pushes, [
            {"method": "POST", "path": "/jorrite/atmos.git/git-receive-pack"},
            {"method": "POST", "path": "/jorrite/atmos/git-receive-pack"},
        ])

    def test_no_rule_lets_a_wildcard_push(self):
        for rule in ngp.endpoint_rules("jorrite/atmos"):
            if "receive-pack" in rule["path"]:
                self.assertNotIn("*", rule["path"])


class ForkParent(unittest.TestCase):
    def lookup(self, payload):
        return ngp.fork_parent("jorrite/atmos", runner=lambda cmd, timeout=None: payload)

    def test_a_fork_has_a_parent(self):
        self.assertEqual(self.lookup(json.dumps({"fork": True, "parent": {"full_name": "cloudposse/atmos"}})), "cloudposse/atmos")

    def test_no_parent_when_it_is_not_a_fork_or_the_lookup_failed(self):
        self.assertIsNone(self.lookup(json.dumps({"fork": False})))
        self.assertIsNone(self.lookup(None))
        self.assertIsNone(self.lookup("not json"))
        self.assertIsNone(self.lookup("[]"))

    def test_asks_gh_for_the_repo(self):
        seen = []
        ngp.fork_parent("jorrite/atmos", runner=lambda cmd, timeout=None: seen.append(cmd))
        self.assertEqual(seen, [["gh", "api", "repos/jorrite/atmos"]])


class PrTargets(unittest.TestCase):
    def targets(self, remotes, parent=None):
        calls = []

        def runner(cmd, timeout=None):
            calls.append(cmd[0])
            if cmd[0] == "git":
                return remotes.get(cmd[-1])
            return json.dumps({"parent": {"full_name": parent}} if parent else {"fork": False})

        return ngp.pr_targets("/repo", "jorrite/atmos", runner), calls

    def test_the_upstream_remote_wins_and_no_lookup_is_needed(self):
        found, calls = self.targets({"upstream": "git@github.com:cloudposse/atmos.git"}, parent="someone/else")
        self.assertEqual(found, ["cloudposse/atmos"])
        self.assertNotIn("gh", calls)

    def test_a_fork_falls_back_to_its_parent(self):
        self.assertEqual(self.targets({}, parent="cloudposse/atmos")[0], ["cloudposse/atmos"])

    def test_an_upstream_on_another_host_does_not_count(self):
        self.assertEqual(self.targets({"upstream": "https://gitlab.com/g/p.git"}, parent="cloudposse/atmos")[0], ["cloudposse/atmos"])

    def test_nothing_when_there_is_no_upstream_and_no_fork(self):
        self.assertEqual(self.targets({})[0], [])

    def test_origin_is_never_its_own_target(self):
        self.assertEqual(self.targets({"upstream": "https://github.com/Jorrite/Atmos.git"})[0], [])


class GhPolicy(unittest.TestCase):
    def test_reads_and_graphql_are_open_and_nothing_else_without_a_write_target(self):
        self.assertEqual(ngp.gh_endpoint_rules(None, []), [{"method": "GET", "path": "/**"}, {"method": "POST", "path": "/graphql"}])

    def test_rest_writes_only_on_the_write_target_and_a_pull_request_on_the_upstream(self):
        rules = ngp.gh_endpoint_rules("jorrite/atmos", ["cloudposse/atmos"])
        for method in ("POST", "PATCH", "PUT", "DELETE"):
            self.assertIn({"method": method, "path": "/repos/jorrite/atmos"}, rules)
            self.assertIn({"method": method, "path": "/repos/jorrite/atmos/**"}, rules)
        self.assertIn({"method": "POST", "path": "/repos/cloudposse/atmos/pulls"}, rules)
        self.assertFalse([r for r in rules if "cloudposse" in r["path"] and not r["path"].endswith("/pulls")])
        self.assertEqual([r for r in rules if r["method"] == "GET"], [{"method": "GET", "path": "/**"}])

    def test_without_a_write_target_gh_only_gets_read_subcommands(self):
        policy = ngp.gh_invocation_policy(write=False)
        self.assertEqual(policy["default"], "deny")
        allowed = [rule["argv"]["prefix"] for rule in policy["allow"]]
        for read in (["pr", "view"], ["issue", "list"], ["api"], ["search"]):
            self.assertIn(read, allowed)
        for write in (["pr", "create"], ["pr", "comment"], ["pr", "merge"], ["issue", "create"], ["repo", "delete"]):
            self.assertNotIn(write, allowed)
        self.assertIn({"contains": ["graphql"]}, [rule["argv"] for rule in policy["deny"]])

    def test_with_a_write_target_gh_is_open_except_for_a_few_subcommands(self):
        policy = ngp.gh_invocation_policy(write=True)
        self.assertEqual(policy["default"], "allow")
        denied = [rule["argv"]["prefix"] for rule in policy["deny"]]
        for args in (["auth", "token"], ["auth", "login"], ["extension"], ["alias"], ["repo", "delete"]):
            self.assertIn(args, denied)
        self.assertNotIn(["pr", "create"], denied)

    def test_the_command_chains_to_git_and_uses_the_phantom_credential(self):
        profile = ngp.build_profile("jorrite/atmos", ["agent-base"], {}, targets=["cloudposse/atmos"])
        gh = profile["command_policies"]["commands"]["gh"]
        self.assertEqual(gh["can_use"], ["git"])
        sandbox = gh["from"]["session"]["sandbox"]
        self.assertEqual(sandbox["credentials"][0]["name"], "gh-api")
        self.assertNotIn("GH_TOKEN", sandbox["environment"].get("set_vars", {}))  # nono supplies the placeholder
        self.assertIn("/repos/cloudposse/atmos/pulls", [r["path"] for r in sandbox["credentials"][0]["endpoint_policy"]["allow"]])

    def test_a_read_only_profile_has_the_read_only_gh(self):
        profile = ngp.build_profile(None, ["agent-base"], {})
        self.assertEqual(profile["command_policies"]["commands"]["gh"]["from"]["session"]["invocation_policy"]["default"], "deny")

    def test_gh_can_read_its_installed_extensions_in_both_modes(self):
        # Without this gh treats installed extensions as missing and offers to install them.
        for write_slug in ("jorrite/atmos", None):
            sandbox = ngp.build_profile(write_slug, ["agent-base"], {})["command_policies"]["commands"]["gh"]["from"]["session"]["sandbox"]
            self.assertIn("$HOME/.local/share/gh/extensions", sandbox["fs_read"])
            self.assertFalse([p for p in sandbox.get("fs_write", []) if "gh/extensions" in p])  # read, never write

    def test_extensions_stay_denied_without_a_write_target(self):
        # An extension talks GraphQL itself, which the endpoint policy cannot tell from a mutation.
        allowed = [rule["argv"]["prefix"] for rule in ngp.gh_invocation_policy(write=False)["allow"]]
        for name in ("stack", "actions-lock", "extension"):
            self.assertFalse([a for a in allowed if a[0] == name])


class BuildProfile(unittest.TestCase):
    launch = ngp.Launch(Path("/s/nono-git-profile/ab12cd34"))

    def sandbox(self, profile):
        return profile["command_policies"]["commands"]["git"]["sandbox"]

    def policy(self, profile):
        return self.sandbox(profile)["credentials"][0]["endpoint_policy"]

    def test_always_reads_through_the_proxy_with_default_deny(self):
        profile = ngp.build_profile(None, ["agent-base"], {})
        self.assertEqual(profile["network"]["tls_intercept"], {"ca_lifecycle": "session", "ca_validity": "30d"})
        self.assertEqual(self.sandbox(profile)["credentials"][0]["name"], "gh-git")
        self.assertEqual(self.policy(profile)["default"], "deny")
        self.assertEqual(self.policy(profile)["allow"], ngp.endpoint_rules(None))
        self.assertNotIn("session_hooks", profile)

    def test_name_is_a_stable_content_hash_without_a_launch(self):
        a = ngp.build_profile("o/r", ["agent-base"], {})
        b = ngp.build_profile("o/r", ["agent-base"], {})
        c = ngp.build_profile(None, ["agent-base"], {})
        self.assertEqual(a["meta"]["name"], b["meta"]["name"])
        self.assertNotEqual(a["meta"]["name"], c["meta"]["name"])

    def test_write_target_reaches_the_policy(self):
        allow = self.policy(ngp.build_profile("jorrite/mote", ["agent-base"], {}))["allow"]
        self.assertIn({"method": "POST", "path": "/jorrite/mote.git/git-receive-pack"}, allow)

    def test_launch_adds_hooks_socket_tmp_and_signing_config(self):
        env = {"GIT_AUTHOR_NAME": "A"}
        profile = ngp.build_profile("jorrite/mote", ["agent-base"], env, self.launch)
        self.assertEqual(profile["meta"]["name"], "git-ab12cd34")
        self.assertEqual(profile["session_hooks"]["before"]["script"], "/s/nono-git-profile/ab12cd34/before.sh")
        self.assertEqual(profile["session_hooks"]["after"]["script"], "/s/nono-git-profile/ab12cd34/after.sh")
        self.assertEqual(profile["filesystem"], {"allow": ["/s/nono-git-profile/ab12cd34/tmp"]})
        sandbox = self.sandbox(profile)
        self.assertEqual(sandbox["unix_socket_bind"], ["/s/nono-git-profile/ab12cd34/a"])
        self.assertEqual(sandbox["fs_write"], ["/s/nono-git-profile/ab12cd34"])
        self.assertEqual(sandbox["fs_read_file"], ["/usr/bin/ssh-keygen"])
        set_vars = sandbox["environment"]["set_vars"]
        self.assertEqual(set_vars["SSH_AUTH_SOCK"], "/s/nono-git-profile/ab12cd34/a")
        self.assertEqual(set_vars["TMPDIR"], "/s/nono-git-profile/ab12cd34/tmp")
        self.assertEqual(set_vars["GIT_AUTHOR_NAME"], "A")
        count = int(set_vars["GIT_CONFIG_COUNT"])
        config = {set_vars[f"GIT_CONFIG_KEY_{i}"]: set_vars[f"GIT_CONFIG_VALUE_{i}"] for i in range(count)}
        self.assertEqual(config["commit.gpgsign"], "true")
        self.assertEqual(config["gpg.format"], "ssh")
        self.assertEqual(config["user.signingkey"], "/s/nono-git-profile/ab12cd34/signing.pub")
        self.assertNotIn(f"GIT_CONFIG_KEY_{count}", set_vars)

    def test_a_launch_without_signing_still_has_hooks_and_a_temp_dir_but_no_agent(self):
        profile = ngp.build_profile("jorrite/mote", ["agent-base"], {}, ngp.Launch(self.launch.dir, sign=False))
        self.assertEqual(profile["meta"]["name"], "git-ab12cd34")
        self.assertEqual(profile["session_hooks"]["before"]["script"], "/s/nono-git-profile/ab12cd34/before.sh")
        self.assertEqual(profile["session_hooks"]["after"]["script"], "/s/nono-git-profile/ab12cd34/after.sh")
        self.assertEqual(profile["filesystem"], {"allow": ["/s/nono-git-profile/ab12cd34/tmp"]})
        sandbox = self.sandbox(profile)
        for key in ("unix_socket_bind", "fs_write", "fs_read_file", "environment"):
            self.assertNotIn(key, sandbox)  # no socket, no signing config, no TMPDIR for git

    def test_input_env_is_not_modified(self):
        env = {"GIT_AUTHOR_NAME": "A"}
        ngp.build_profile(None, ["agent-base"], env, self.launch)
        self.assertEqual(env, {"GIT_AUTHOR_NAME": "A"})


class DefaultBases(unittest.TestCase):
    def extends(self, *args, herdr=False):
        env = {"HC_TERMINAL_ID": "t7"} if herdr else {}
        with mock.patch.dict(os.environ, env):
            if not herdr:
                os.environ.pop("HC_TERMINAL_ID", None)
            with tempfile.TemporaryFile("w+") as out:
                with mock.patch("sys.stdout", out):
                    self.assertEqual(ngp.main(["--json", "--no-sign", "--cwd", "/nonexistent", *args]), 0)
                out.seek(0)
                return json.loads(out.read())["extends"]

    def test_uses_nonos_claude_profile_by_default(self):
        self.assertEqual(self.extends(), ["agent-base", "nolabs-ai/claude"])

    def test_hc_access_only_inside_herdr(self):
        self.assertEqual(self.extends(herdr=True), ["agent-base", "herdr", "nolabs-ai/claude"])
        self.assertNotIn("herdr", self.extends(herdr=False))

    def test_base_replaces_the_default_even_inside_herdr(self):
        self.assertEqual(self.extends("--base", "agent-base", herdr=True), ["agent-base"])


class LaunchDir(unittest.TestCase):
    def setUp(self):
        self.state = short_tmp() / "nono-git-profile"
        self.addCleanup(shutil.rmtree, self.state.parent, ignore_errors=True)

    def test_socket_path_that_is_too_long_is_refused(self):
        with self.assertRaises(SystemExit):
            ngp.Launch.new(Path("/" + "x" * 120))

    def test_create_makes_private_dirs_and_stubs_that_call_the_hook(self):
        launch = ngp.Launch.new(self.state, "ab12cd34")
        launch.create(Path("/hooks/git session hook"))
        self.assertEqual(oct(launch.dir.stat().st_mode & 0o777), "0o700")
        self.assertTrue(launch.tmp.is_dir())
        self.assertEqual(launch.before.read_text(), f"#!/bin/sh\nexec '/hooks/git session hook' before {launch.dir}\n")
        self.assertEqual(launch.after.read_text(), f"#!/bin/sh\nexec '/hooks/git session hook' after {launch.dir}\n")
        self.assertTrue(os.access(launch.before, os.X_OK) and os.access(launch.after, os.X_OK))

    def test_a_launch_without_signing_tells_the_before_hook_so(self):
        launch = ngp.Launch.new(self.state, "ab12cd34", sign=False)
        launch.create(Path("/h"))
        self.assertTrue(launch.tmp.is_dir())
        self.assertEqual(launch.before.read_text(), f"#!/bin/sh\nexec /h before {launch.dir} nosign\n")
        self.assertEqual(launch.after.read_text(), f"#!/bin/sh\nexec /h after {launch.dir}\n")

    def make(self, name, owner=None, age=0, sign=True, agent=None):
        launch = ngp.Launch.new(self.state, name, sign=sign)
        launch.create(Path("/h"))
        if owner is not None:
            (launch.dir / "owner").write_text(f"{owner}\n")
        if agent is not None:
            (launch.dir / "pid").write_text(f"{agent}\n")
        old = time.time() - age
        os.utime(launch.dir, (old, old))
        return launch.dir

    def test_sweep_keeps_live_sessions_and_fresh_launches_and_removes_dead_ones(self):
        dead = subprocess.Popen(["true"])
        dead.wait()
        live = self.make("11111111", owner=os.getpid())
        fresh = self.make("22222222")
        gone = self.make("33333333", owner=dead.pid)
        orphan = self.make("44444444", age=ngp.ORPHAN_AFTER + 60)
        unrelated = self.state / "not-a-launch"
        unrelated.mkdir()
        ngp.sweep(self.state)
        self.assertTrue(live.exists() and fresh.exists() and unrelated.exists())
        self.assertFalse(gone.exists() or orphan.exists())

    def test_sweep_keeps_sessions_the_older_hook_started_which_only_recorded_the_agent(self):
        # Applying this version must not delete the directory of a session that is still running
        # from before it: the older before hook wrote `pid` (the agent) and no `owner`.
        dead = subprocess.Popen(["true"])
        dead.wait()
        old = ngp.ORPHAN_AFTER * 24
        running = self.make("66666666", agent=os.getpid(), age=old)
        gone = self.make("77777777", agent=dead.pid, age=old)
        ngp.sweep(self.state)
        self.assertTrue(running.exists())
        self.assertFalse(gone.exists())

    def test_sweep_goes_by_nono_when_both_are_recorded_even_if_the_agent_lingers(self):
        dead = subprocess.Popen(["true"])
        dead.wait()
        lingering = self.make("88888888", owner=dead.pid, agent=os.getpid(), age=ngp.ORPHAN_AFTER * 2)
        ngp.sweep(self.state)
        self.assertFalse(lingering.exists())

    def test_sweep_keeps_a_long_running_session_that_has_no_signing_agent(self):
        # Liveness is nono's pid, not the agent's: a session without an agent has to survive
        # past ORPHAN_AFTER, or the next launch would delete its temp dir while it runs.
        old = ngp.ORPHAN_AFTER * 24
        running = self.make("55555555", owner=os.getpid(), age=old, sign=False)
        ngp.sweep(self.state)
        self.assertTrue(running.exists())
        (running / "owner").write_text("999999999\n")  # nono is gone, no after hook ran
        ngp.sweep(self.state)
        self.assertFalse(running.exists())

    def test_sweep_without_a_state_dir_is_fine(self):
        ngp.sweep(self.state / "missing")


@unittest.skipUnless(Path("/bin/bash").exists(), "bash not installed")
class CsLaunch(unittest.TestCase):
    """cs-launch only glues nono-git-profile to nono run, so both are stubs that record their argv."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        stubs = {
            "nono-git-profile": ("gen.args", "GEN_EXIT", "echo /fake/profile.json"),
            "nono": ("nono.args", "NONO_EXIT", ""),
        }
        for name, (record, exit_var, extra) in stubs.items():
            lines = ["#!/bin/sh", 'for a in "$@"; do printf "%s\\n" "$a"; done > "$REC/' + record + '"']
            if extra:
                lines.append(extra)
            lines.append('exit "${' + exit_var + ':-0}"')
            stub = self.tmp / name
            stub.write_text("\n".join(lines) + "\n")
            stub.chmod(0o755)

    def run_cs(self, *args, **env):
        full = {"PATH": f"{self.tmp}:/usr/bin:/bin", "REC": str(self.tmp), **env}
        return subprocess.run(["/bin/bash", str(CS_LAUNCH), *args], env=full, capture_output=True, text=True)

    def recorded(self, name):
        path = self.tmp / name
        return path.read_text().splitlines() if path.exists() else None

    def test_defaults_to_claude_with_a_strict_sandbox(self):
        self.assertEqual(self.run_cs().returncode, 0)
        self.assertEqual(self.recorded("gen.args"), [])
        self.assertEqual(
            self.recorded("nono.args"),
            ["run", "--strict-broker-path", "--profile", "/fake/profile.json", "--allow-cwd", "--", "claude"],
        )

    def test_options_before_the_double_dash_go_to_the_profile_generator(self):
        self.assertEqual(self.run_cs("--push", "--base", "agent-base").returncode, 0)
        self.assertEqual(self.recorded("gen.args"), ["--push", "--base", "agent-base"])
        self.assertEqual(self.recorded("nono.args")[-1], "claude")

    def test_a_command_after_the_double_dash_replaces_claude_and_keeps_its_arguments(self):
        self.assertEqual(self.run_cs("--no-sign", "--", "bash", "-c", "echo hi there").returncode, 0)
        self.assertEqual(self.recorded("gen.args"), ["--no-sign"])
        self.assertEqual(self.recorded("nono.args")[-4:], ["--", "bash", "-c", "echo hi there"])

    def test_what_is_not_a_wrapper_option_goes_to_claude(self):
        self.assertEqual(self.run_cs("--push", "--resume").returncode, 0)
        self.assertEqual(self.recorded("gen.args"), ["--push"])
        self.assertEqual(self.recorded("nono.args")[-2:], ["claude", "--resume"])

    def test_claude_options_with_values_and_a_prompt_keep_their_words(self):
        self.assertEqual(self.run_cs("--no-sign", "-r", "abc", "--model", "opus", "fix the tests").returncode, 0)
        self.assertEqual(self.recorded("gen.args"), ["--no-sign"])
        self.assertEqual(self.recorded("nono.args")[-6:], ["claude", "-r", "abc", "--model", "opus", "fix the tests"])

    def test_wrapper_options_with_values_still_reach_the_generator_next_to_claude_options(self):
        self.assertEqual(self.run_cs("--resume", "--cwd", "/some dir", "--base=agent-base", "--continue").returncode, 0)
        self.assertEqual(self.recorded("gen.args"), ["--cwd", "/some dir", "--base=agent-base"])
        self.assertEqual(self.recorded("nono.args")[-3:], ["claude", "--resume", "--continue"])

    def test_arguments_after_the_double_dash_belong_to_that_command_even_when_they_look_like_wrapper_ones(self):
        self.assertEqual(self.run_cs("--push", "--", "codex", "--resume", "--push").returncode, 0)
        self.assertEqual(self.recorded("gen.args"), ["--push"])
        self.assertEqual(self.recorded("nono.args")[-4:], ["--", "codex", "--resume", "--push"])

    def test_an_empty_double_dash_still_means_claude(self):
        self.assertEqual(self.run_cs("--push", "--").returncode, 0)
        self.assertEqual(self.recorded("nono.args")[-1], "claude")

    def test_an_unknown_option_before_an_explicit_command_is_refused_and_nothing_starts(self):
        done = self.run_cs("--resume", "--", "codex")
        self.assertEqual(done.returncode, 2)
        self.assertIn("--resume", done.stderr)
        self.assertIsNone(self.recorded("gen.args"))
        self.assertIsNone(self.recorded("nono.args"))

    def test_a_wrapper_option_without_its_value_is_refused(self):
        done = self.run_cs("--push", "--base")
        self.assertEqual(done.returncode, 2)
        self.assertIsNone(self.recorded("nono.args"))

    def test_nothing_starts_when_the_profile_cannot_be_generated(self):
        done = self.run_cs(GEN_EXIT="3")
        self.assertEqual(done.returncode, 3)
        self.assertIsNone(self.recorded("nono.args"))

    def test_the_exit_code_of_the_agent_is_returned(self):
        self.assertEqual(self.run_cs(NONO_EXIT="7").returncode, 7)


@unittest.skipUnless(shutil.which("ssh-agent") and shutil.which("ssh-keygen"), "openssh not installed")
class HookScript(unittest.TestCase):
    def setUp(self):
        self.tmp = short_tmp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.key = self.tmp / "key"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(self.key)], check=True)
        self.dir = self.tmp / "nono-git-profile" / "ab12cd34"
        (self.dir / "tmp").mkdir(parents=True)
        self.env_file = self.tmp / "env"
        self.env = {**os.environ, "NONO_SIGNING_KEY_CMD": f"cat {self.key}", "NONO_ENV_FILE": str(self.env_file), "NONO_WATCH_INTERVAL": "1"}
        self.addCleanup(self.kill_agent)

    def kill_agent(self):
        pid_file = self.dir / "pid"
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text()), signal.SIGTERM)
            except (OSError, ValueError):
                pass

    def hook(self, mode, directory=None, *extra, **env):
        return subprocess.run([str(HOOK), mode, str(directory or self.dir), *extra], env={**self.env, **env}, capture_output=True, text=True)

    def test_before_loads_only_the_key_and_after_cleans_everything_up(self):
        done = self.hook("before")
        self.assertEqual(done.returncode, 0, done.stderr)
        agent = {**os.environ, "SSH_AUTH_SOCK": str(self.dir / "a")}
        listing = subprocess.run(["ssh-add", "-l"], env=agent, capture_output=True, text=True).stdout.splitlines()
        self.assertEqual(len(listing), 1)
        self.assertIn("ED25519", listing[0])
        self.assertTrue((self.dir / "signing.pub").read_text().startswith("ssh-ed25519 "))
        # Claude's own tree (scratchpad, task output) goes into the launch dir along with TMPDIR.
        self.assertEqual(self.env_file.read_text(), f"TMPDIR={self.dir}/tmp\nCLAUDE_CODE_TMPDIR={self.dir}/tmp\n")
        self.assertFalse(any(p.name == "key" or p.read_text(errors="ignore").startswith("-----BEGIN") for p in self.dir.rglob("*") if p.is_file()))
        self.assertEqual(int((self.dir / "owner").read_text()), os.getpid())  # the hook's parent stands in for nono
        pid = int(( self.dir / "pid").read_text())
        os.kill(pid, 0)  # agent is running

        self.assertEqual(self.hook("after").returncode, 0)
        self.assertFalse(self.dir.exists())
        with self.assertRaises(ProcessLookupError):
            for _ in range(20):
                os.kill(pid, 0)
                time.sleep(0.1)
            os.kill(pid, 0)

    def test_before_without_signing_sets_up_the_temp_dir_and_starts_no_agent_and_asks_for_no_key(self):
        asked = self.tmp / "asked"
        done = self.hook("before", None, "nosign", NONO_SIGNING_KEY_CMD=f"touch {asked}; cat {self.key}")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.env_file.read_text(), f"TMPDIR={self.dir}/tmp\nCLAUDE_CODE_TMPDIR={self.dir}/tmp\n")
        self.assertEqual(int((self.dir / "owner").read_text()), os.getpid())
        self.assertFalse(asked.exists(), "the key was read although nothing is signed")
        for name in ("a", "pid", "signing.pub"):
            self.assertFalse((self.dir / name).exists(), name)
        self.assertEqual(self.hook("after").returncode, 0)
        self.assertFalse(self.dir.exists())

    def test_a_failed_key_load_still_leaves_the_directory_to_be_cleaned_up(self):
        # before fails, nono carries on (hooks fail open): the session must still have its
        # temp dir, and the watcher must still be there to remove it.
        done = self.hook("before", None, NONO_SIGNING_KEY_CMD="false")
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(self.env_file.read_text(), f"TMPDIR={self.dir}/tmp\nCLAUDE_CODE_TMPDIR={self.dir}/tmp\n")
        self.assertTrue((self.dir / "owner").exists())
        self.kill_agent()
        self.hook("after")

    def test_refuses_directories_that_are_not_launch_dirs(self):
        for bad in [self.tmp / "nono-git-profile" / "not-a-launch-id", self.tmp / "elsewhere" / "ab12cd34", self.tmp]:
            bad.mkdir(parents=True, exist_ok=True)
            with self.subTest(bad=str(bad)):
                done = self.hook("after", bad)
                self.assertEqual(done.returncode, 1)
                self.assertTrue(bad.exists())

    def test_after_is_idempotent(self):
        shutil.rmtree(self.dir)
        self.assertEqual(self.hook("after").returncode, 0)

    def test_before_needs_the_launch_dir_to_exist(self):
        shutil.rmtree(self.dir)
        self.assertEqual(self.hook("before").returncode, 1)

    def test_watcher_cleans_up_when_nono_is_killed_without_running_after(self):
        # The parent of the hook stands in for nono. herdr ends a worker by killing it.
        nono = subprocess.Popen(["sh", "-c", f'"{HOOK}" before "{self.dir}"; exec sleep 120'], env=self.env)
        self.addCleanup(lambda: nono.poll() is None and nono.kill())
        for _ in range(100):
            if (self.dir / "signing.pub").exists():
                break
            time.sleep(0.1)
        self.assertTrue((self.dir / "signing.pub").exists(), "before never finished")
        agent = int((self.dir / "pid").read_text())
        nono.kill()
        nono.wait()
        for _ in range(150):
            if not self.dir.exists():
                break
            time.sleep(0.1)
        self.assertFalse(self.dir.exists(), "the watcher did not remove the launch dir")
        for _ in range(50):
            try:
                os.kill(agent, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        with self.assertRaises(ProcessLookupError):
            os.kill(agent, 0)

    def test_watcher_cleans_up_a_session_without_signing_too(self):
        nono = subprocess.Popen(["sh", "-c", f'"{HOOK}" before "{self.dir}" nosign; exec sleep 120'], env=self.env)
        self.addCleanup(lambda: nono.poll() is None and nono.kill())
        for _ in range(100):
            if (self.dir / "owner").exists():
                break
            time.sleep(0.1)
        self.assertTrue((self.dir / "owner").exists(), "before never finished")
        self.assertTrue(self.dir.exists())
        time.sleep(2)  # a few polls: the directory stays for as long as nono runs
        self.assertTrue(self.dir.exists())
        nono.kill()
        nono.wait()
        for _ in range(150):
            if not self.dir.exists():
                break
            time.sleep(0.1)
        self.assertFalse(self.dir.exists(), "the watcher did not remove the launch dir")

    def test_unknown_mode_fails(self):
        self.assertEqual(self.hook("bogus").returncode, 1)


@unittest.skipUnless(HAVE_NONO and HAVE_GIT, "nono and git are needed")
class AgainstNono(unittest.TestCase):
    """The generated profile has to pass nono's own validation, with the real base profile."""

    def setUp(self):
        self.tmp = short_tmp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.xdg = self.tmp / "xdg"
        (self.xdg / "nono" / "profiles").mkdir(parents=True)
        (self.xdg / "nono" / "hooks").mkdir(parents=True)
        shutil.copy(BASE, self.xdg / "nono" / "profiles" / "agent-base.json")
        shutil.copy(HOOK, self.xdg / "nono" / "hooks" / "git-session-hook")
        self.state = self.tmp / "state" / "nono-git-profile"
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        gitconfig = self.tmp / "gitconfig"
        gitconfig.write_text("[user]\n\tname = Test User\n\temail = test@example.invalid\n")
        patcher = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.xdg), "GIT_CONFIG_GLOBAL": str(gitconfig), "GIT_CONFIG_SYSTEM": "/dev/null"})
        patcher.start()
        self.addCleanup(patcher.stop)
        git("init", "-q", cwd=self.repo)
        git("remote", "add", "origin", "https://github.com/jorrite/atmos.git", cwd=self.repo)

    def generate(self, *extra, cwd=None):
        with tempfile.TemporaryFile("w+") as out:
            with mock.patch("sys.stdout", out):
                code = ngp.main(["--cwd", str(cwd or self.repo), "--state-dir", str(self.state), *([] if "--base" in extra else ["--base", "agent-base"]), *extra])
            out.seek(0)
            return code, out.read().strip()

    def test_static_profiles_are_valid(self):
        for profile in (BASE, HERDR):
            done = subprocess.run(["nono", "profile", "validate", str(profile)], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, f"{profile.name}: {done.stdout}{done.stderr}")

    def test_signing_launch_is_valid_and_its_stubs_clean_up(self):
        code, printed = self.generate("--push")
        self.assertEqual(code, 0)
        profile = json.loads(Path(printed).read_text())
        launch = Path(printed).parent
        self.assertEqual(profile["meta"]["name"], f"git-{launch.name}")
        paths = {g["path"] for g in profile["command_policies"]["commands"]["git"]["sandbox"]["credentials"][0]["endpoint_policy"]["allow"]}
        self.assertIn("/jorrite/atmos.git/git-receive-pack", paths)  # origin may push
        self.assertIn("/*/*/git-upload-pack", paths)  # every repo may be read
        self.assertEqual(sorted(p for p in paths if "receive-pack" in p), ["/jorrite/atmos.git/git-receive-pack", "/jorrite/atmos/git-receive-pack"])
        self.assertEqual(profile["command_policies"]["commands"]["git"]["sandbox"]["environment"]["set_vars"]["GIT_AUTHOR_EMAIL"], "test@example.invalid")
        done = subprocess.run([str(launch / "after.sh")], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse(launch.exists())

    def test_no_sign_launch_is_valid_read_only_has_hooks_but_no_agent_and_its_stubs_clean_up(self):
        code, printed = self.generate("--no-sign")
        self.assertEqual(code, 0)
        profile = json.loads(Path(printed).read_text())
        launch = Path(printed).parent
        self.assertEqual(launch.parent, self.state)
        self.assertEqual(profile["meta"]["name"], f"git-{launch.name}")
        self.assertIn("session_hooks", profile)
        self.assertNotIn("receive-pack", printed + json.dumps(profile))
        self.assertNotIn("unix_socket_bind", profile["command_policies"]["commands"]["git"]["sandbox"])
        self.assertIn("nosign", (launch / "before.sh").read_text())
        done = subprocess.run([str(launch / "after.sh")], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse(launch.exists())

    def session(self, *flags, script):
        """Run `script` in a real nono session and return its launch dir and the result."""
        work = self.tmp / "work"
        work.mkdir(exist_ok=True)
        code, printed = self.generate(*flags, cwd=work)
        self.assertEqual(code, 0)
        done = subprocess.run(["nono", "run", "-s", "--profile", printed, "--allow-cwd", "--", "sh", "-c", script], cwd=work, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        return Path(printed).parent, done

    def test_a_session_without_signing_gets_its_own_temp_dir_that_is_gone_once_nono_exits(self):
        launch, done = self.session("--no-sign", script='echo "$TMPDIR"; echo "$CLAUDE_CODE_TMPDIR"; touch "$TMPDIR/scratch" && echo wrote')
        tmpdir, claude_tmp, wrote = done.stdout.split()
        self.assertEqual(os.path.realpath(tmpdir), os.path.realpath(launch / "tmp"))
        self.assertEqual(os.path.realpath(claude_tmp), os.path.realpath(launch / "tmp"))
        self.assertEqual(wrote, "wrote")
        self.assertFalse(launch.exists(), "the after hook did not remove the launch dir")

    @unittest.skipUnless(shutil.which("ssh-agent") and shutil.which("ssh-keygen"), "openssh not installed")
    def test_a_signing_session_gets_the_same_temp_dir_and_loses_its_agent_with_it(self):
        key = self.tmp / "key"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
        with mock.patch.dict(os.environ, {"NONO_SIGNING_KEY_CMD": f"cat {key}"}):
            launch, done = self.session(script='echo "$TMPDIR"; echo "$CLAUDE_CODE_TMPDIR"')
        for value in done.stdout.split():
            self.assertEqual(os.path.realpath(value), os.path.realpath(launch / "tmp"))
        self.assertFalse(launch.exists())
        agents = subprocess.run(["pgrep", "-f", f"{launch}/a"], capture_output=True, text=True)
        self.assertEqual(agents.returncode, 1, "the signing agent is still running")

    def test_rm_cp_mv_work_inside_the_working_directory_only(self):
        work, outside = self.tmp / "work", self.tmp / "outside"
        work.mkdir()
        outside.mkdir()
        (work / "a.txt").write_text("a")
        (outside / "o.txt").write_text("o")
        code, printed = self.generate("--no-sign", cwd=work)
        self.assertEqual(code, 0)
        script = "cp a.txt b.txt && mv b.txt c.txt && rm c.txt; rm ../outside/o.txt; mv a.txt ../outside/a.txt; chmod 000 a.txt; true"
        subprocess.run(["nono", "run", "--profile", printed, "--allow-cwd", "--", "sh", "-c", script], cwd=work, capture_output=True, text=True)
        self.assertTrue((work / "a.txt").exists())  # not moved out
        self.assertFalse((work / "b.txt").exists() or (work / "c.txt").exists())  # copied, moved and removed inside
        self.assertTrue((outside / "o.txt").exists())  # not removed
        self.assertFalse((outside / "a.txt").exists())  # nothing moved in
        self.assertTrue((work / "a.txt").stat().st_mode & 0o400)  # chmod is still denied
        self.assertFalse(Path(printed).parent.exists())  # and nono's after hook removed the launch dir

    def test_missing_hook_is_an_error_in_every_mode(self):
        (self.xdg / "nono" / "hooks" / "git-session-hook").unlink()
        for flags in ((), ("--no-sign",)):
            with self.subTest(flags=flags):
                code, _ = self.generate(*flags)
                self.assertEqual(code, 1)

    def test_repo_without_origin_can_still_read_but_not_push(self):
        git("remote", "remove", "origin", cwd=self.repo)
        code, printed = self.generate("--no-sign", "--push")
        self.assertEqual(code, 0)
        text = Path(printed).read_text()
        self.assertIn("/*/*/info/refs", text)
        self.assertNotIn("receive-pack", text)

    def test_origin_on_another_host_cannot_push(self):
        git("remote", "set-url", "origin", "https://gitlab.com/group/project.git", cwd=self.repo)
        code, printed = self.generate("--no-sign", "--push")
        self.assertEqual(code, 0)
        self.assertNotIn("receive-pack", Path(printed).read_text())


if __name__ == "__main__":
    unittest.main()
