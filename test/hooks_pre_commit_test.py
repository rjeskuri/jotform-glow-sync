#!/usr/bin/env python3
"""
.githooks/pre-commit, in a scratch repository: the lines a commit adds are scanned for secrets, and
ruff checks every added, changed or renamed .py file as staged. (The Claude Code guardrail hooks:
test/hooks_test.py and test/hooks_*_test.py.)
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

# first: importing helpers.common puts the repository root and tools/ on sys.path
from helpers.common import REPO
from helpers.hooks import BASH

RUFF = shutil.which("ruff") or (os.path.join(REPO, ".venv", "bin", "ruff")
                                if os.access(os.path.join(REPO, ".venv", "bin", "ruff"), os.X_OK) else None)


@unittest.skipUnless(shutil.which("git") and RUFF and os.access(BASH, os.X_OK), "needs git, ruff and /bin/bash")
class PreCommit(unittest.TestCase):
    """.githooks/pre-commit run on a scratch repository's staged changes (it is installed per clone
    by `make hooks`; here it is called directly, as git would)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = self.tmp.name
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env["PATH"] = os.pathsep.join([os.path.dirname(RUFF), os.path.dirname(sys.executable),
                                            self.env.get("PATH", "")])
        os.makedirs(os.path.join(self.repo, "scripts"))
        shutil.copy(os.path.join(REPO, "scripts", "check_secrets.py"), os.path.join(self.repo, "scripts"))
        shutil.copy(os.path.join(REPO, "ruff.toml"), self.repo)
        self.write("tools/club.py", "def club(name):\n    return name.strip()\n")
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", "start")

    def git(self, *args):
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.org",
                        "-c", "core.hooksPath=/dev/null", *args], cwd=self.repo, env=self.env, check=True,
                       capture_output=True)

    def write(self, rel, text):
        os.makedirs(os.path.dirname(os.path.join(self.repo, rel)) or self.repo, exist_ok=True)
        with open(os.path.join(self.repo, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def hook(self):
        done = subprocess.run([os.path.join(REPO, ".githooks", "pre-commit")], cwd=self.repo, env=self.env,
                              capture_output=True, text=True, timeout=60)
        return done.returncode, done.stdout + done.stderr

    def test_a_renamed_and_edited_py_file_is_linted(self):
        # review of 2026-10-09: --diff-filter=AM dropped a renamed file (status R)
        self.git("mv", "tools/club.py", "tools/clubs.py")
        self.assertEqual(self.hook()[0], 0)                               # a plain rename
        self.write("tools/clubs.py", "import os\n\n\ndef club(name):\n    return name.strip()\n")
        self.git("add", "tools/clubs.py")
        code, out = self.hook()
        self.assertEqual(code, 1, out)
        self.assertIn("F401", out)

    def test_added_lines_are_scanned_and_lint_errors_refused(self):
        self.write("notes.md", "a clean line\n")
        self.git("add", "notes.md")
        self.assertEqual(self.hook()[0], 0)
        self.write("tools/new.py", "import sys\n")
        self.git("add", "tools/new.py")
        self.assertEqual(self.hook()[0], 1)
        self.git("rm", "-q", "--cached", "tools/new.py")
        fake = "ab" * 16                                                  # a 32-hex token, built here
        self.write("cfg.txt", f"token = {fake}\n")
        self.git("add", "cfg.txt")
        code, out = self.hook()
        self.assertEqual(code, 1, out)
        self.assertIn("32-hex token", out)
        self.git("commit", "-q", "--no-verify", "-m", "slipped in")
        self.git("rm", "-q", "cfg.txt")
        self.assertEqual(self.hook()[0], 0)                              # removing it is fine

    def test_a_column_0_decorator_is_not_read_as_an_e_mail_address(self):
        # review of 2026-10-09: the diff's "+" marker went into the scan, and with it a decorator at
        # column 0 matched the e-mail rule (whose local part takes "+"), refusing a clean commit
        self.write("tools/cached.py", "\n".join(["import functools", "", "",
                                                 "@functools.lru_cache(maxsize=64)",
                                                 "def club(name):", "    return name.strip()", ""]))
        self.git("add", "tools/cached.py")
        code, out = self.hook()
        self.assertEqual(code, 0, out)
        address = "mentor" + "@" + "school.test"                         # built here, as above
        self.write("notes.md", f"{address}\n")                           # still caught at column 0
        self.git("add", "notes.md")
        code, out = self.hook()
        self.assertEqual(code, 1, out)
        self.assertIn("e-mail address", out)


if __name__ == "__main__":
    unittest.main(verbosity=1)
