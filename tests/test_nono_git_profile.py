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

    def test_input_env_is_not_modified(self):
        env = {"GIT_AUTHOR_NAME": "A"}
        ngp.build_profile(None, ["agent-base"], env, self.launch)
        self.assertEqual(env, {"GIT_AUTHOR_NAME": "A"})


class DefaultBases(unittest.TestCase):
    def extends(self, *args):
        with tempfile.TemporaryFile("w+") as out:
            with mock.patch("sys.stdout", out):
                self.assertEqual(ngp.main(["--json", "--no-sign", "--cwd", "/nonexistent", *args]), 0)
            out.seek(0)
            return json.loads(out.read())["extends"]

    def test_uses_nonos_claude_profile_by_default(self):
        self.assertEqual(self.extends(), ["agent-base", "nolabs-ai/claude"])

    def test_base_replaces_the_default(self):
        self.assertEqual(self.extends("--base", "agent-base"), ["agent-base"])


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

    def make(self, name, pid=None, age=0):
        launch = ngp.Launch.new(self.state, name)
        launch.create(Path("/h"))
        if pid is not None:
            (launch.dir / "pid").write_text(f"{pid}\n")
        old = time.time() - age
        os.utime(launch.dir, (old, old))
        return launch.dir

    def test_sweep_keeps_live_sessions_and_fresh_launches_and_removes_dead_ones(self):
        dead = subprocess.Popen(["true"])
        dead.wait()
        live = self.make("11111111", pid=os.getpid())
        fresh = self.make("22222222")
        gone = self.make("33333333", pid=dead.pid)
        orphan = self.make("44444444", age=ngp.ORPHAN_AFTER + 60)
        unrelated = self.state / "profiles"
        unrelated.mkdir()
        ngp.sweep(self.state)
        self.assertTrue(live.exists() and fresh.exists() and unrelated.exists())
        self.assertFalse(gone.exists() or orphan.exists())

    def test_sweep_without_a_state_dir_is_fine(self):
        ngp.sweep(self.state / "missing")


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
        self.env = {**os.environ, "NONO_SIGNING_KEY_CMD": f"cat {self.key}", "NONO_ENV_FILE": str(self.env_file)}
        self.addCleanup(self.kill_agent)

    def kill_agent(self):
        pid_file = self.dir / "pid"
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text()), signal.SIGTERM)
            except (OSError, ValueError):
                pass

    def hook(self, mode, directory=None):
        return subprocess.run([str(HOOK), mode, str(directory or self.dir)], env=self.env, capture_output=True, text=True)

    def test_before_loads_only_the_key_and_after_cleans_everything_up(self):
        done = self.hook("before")
        self.assertEqual(done.returncode, 0, done.stderr)
        agent = {**os.environ, "SSH_AUTH_SOCK": str(self.dir / "a")}
        listing = subprocess.run(["ssh-add", "-l"], env=agent, capture_output=True, text=True).stdout.splitlines()
        self.assertEqual(len(listing), 1)
        self.assertIn("ED25519", listing[0])
        self.assertTrue((self.dir / "signing.pub").read_text().startswith("ssh-ed25519 "))
        self.assertEqual(self.env_file.read_text(), f"TMPDIR={self.dir}/tmp\n")
        self.assertFalse(any(p.name == "key" or p.read_text(errors="ignore").startswith("-----BEGIN") for p in self.dir.rglob("*") if p.is_file()))
        pid = int(( self.dir / "pid").read_text())
        os.kill(pid, 0)  # agent is running

        self.assertEqual(self.hook("after").returncode, 0)
        self.assertFalse(self.dir.exists())
        with self.assertRaises(ProcessLookupError):
            for _ in range(20):
                os.kill(pid, 0)
                time.sleep(0.1)
            os.kill(pid, 0)

    def test_refuses_directories_that_are_not_launch_dirs(self):
        for bad in [self.tmp / "nono-git-profile" / "not-a-launch-id", self.tmp / "elsewhere" / "ab12cd34", self.tmp]:
            bad.mkdir(parents=True, exist_ok=True)
            with self.subTest(bad=str(bad)):
                done = self.hook("after", bad)
                self.assertEqual(done.returncode, 1)
                self.assertTrue(bad.exists())

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

    def generate(self, *extra):
        with tempfile.TemporaryFile("w+") as out:
            with mock.patch("sys.stdout", out):
                code = ngp.main(["--cwd", str(self.repo), "--state-dir", str(self.state), *([] if "--base" in extra else ["--base", "agent-base"]), *extra])
            out.seek(0)
            return code, out.read().strip()

    def test_base_profile_is_valid(self):
        done = subprocess.run(["nono", "profile", "validate", str(BASE)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

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

    def test_no_sign_profile_is_valid_read_only_and_has_no_launch_dir(self):
        code, printed = self.generate("--no-sign")
        self.assertEqual(code, 0)
        profile = json.loads(Path(printed).read_text())
        self.assertNotIn("session_hooks", profile)
        self.assertNotIn("receive-pack", printed + json.dumps(profile))
        self.assertEqual(Path(printed).parent, self.state / "profiles")

    def test_missing_hook_is_an_error(self):
        (self.xdg / "nono" / "hooks" / "git-session-hook").unlink()
        code, _ = self.generate()
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
