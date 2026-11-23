#!/usr/bin/env python3
"""
.claude/hooks/live_gate.sh (Bash), run as Claude Code runs it (the harness, the hooks and
settings it reads, and the osascript stub: test/helpers/hooks.py): how a live command is matched.

"Prompt, don't parse" (Ryan, 2026-10-14): the command is matched as text - as written and with
quote and backslash characters removed, in any case - never read as shell words. A gh api call is
live when the command holds a gh word, api, and actions/, dispatches or graphql anywhere, whatever
the method; every other gh api call is ungated.

The prompt itself: test/hooks_live_gate_prompt_test.py.
"""
import unittest

# first: importing helpers.common (through helpers.hooks) puts the repository root and tools/ on sys.path
from helpers.hooks import ASK_MODES, NO_PROMPT_MODES, HookFixture, needs_bash, nest


@needs_bash
class LiveGateMatching(HookFixture, unittest.TestCase):
    # gh api, "prompt, don't parse" (Ryan, 2026-10-14). The read/write reader of 9794ffe..a2cf749
    # is withdrawn: four reviews found it failing open on each gap between it and the shell. A
    # gh word - any case, a path ending /gh, =gh, split by quotes or a backslash - and api, and
    # actions/, dispatches or graphql anywhere in the command: live whatever the method, GETs too
    GH_API_LIVE = [
        # the method does not count: reads of the Actions API, of dispatches and graphql ask too
        "gh api repos/o/r/actions/variables",
        "gh api -X GET repos/o/r/actions/runs --jq '.total_count'",
        "gh api repos/o/r/actions/runs/1234/logs > run.zip",
        "gh api --paginate repos/o/r/actions/secrets",
        "gh api --method GET repos/o/r/actions/variables -f per_page=100",
        "gh api graphql -f query='query { viewer { login } }'",
        "gh api repos/o/r/dispatches",
        # ... and the writes
        "gh api -X PATCH repos/o/r/actions/variables/SF_SYNC -f value=apply",
        "gh api repos/o/r/actions/workflows/auto-sync.yml/dispatches -f ref=main -f 'inputs[apply]=true'",
        "gh api repos/o/r/dispatches -f event_type=roster-changed",
        "gh api graphql -F query=@m.graphql",
        "gh -R o/r api repos/o/r/actions/variables/X -X DELETE",
        "gh api -iXDELETE repos/o/r/actions/secrets/X",
        "gh api orgs/o/actions/variables -f name=SF_SYNC -f value=x",
        # shapes the reader did not see through (reviews of PR #41): a # it took for a comment,
        # a redirection between the path and the method, a substitution before or inside the
        # command, eval, a shell, gh found at run time, four shells deep
        "gh pr comment 41 --body \"$(printf \"Closes #36\")\" && gh api repos/o/r/actions/variables/X -X PATCH -f value=true",
        "echo `echo #`; gh api -X PATCH repos/o/r/actions/variables/X -f value=true",
        "echo ${x:- #}; gh api -X PATCH repos/o/r/actions/variables/X -f value=true",
        "cat <<'EOF'\ndon't\nEOF\necho ' # '; gh api -X PATCH repos/o/r/actions/variables/X -f value=true",
        "echo `echo #`; gh api graphql -F query=@m.graphql",
        "gh api repos/o/r/actions/variables/SF_SYNC >/dev/null -X PATCH -f value=apply",
        "gh api repos/o/r/actions/variables/SF_SYNC 2>&1 -X PATCH -f value=apply",
        "$(true)gh api -X PATCH repos/o/r/actions/variables/SF_SYNC -f value=apply",
        "gh $(true) api repos/o/r/actions/variables/SF_SYNC -X PATCH -f value=apply",
        "eval 'gh api -X PATCH repos/o/r/actions/variables/SF_SYNC -f value=apply'",
        "bash -c \"gh api repos/o/r/actions/secrets/X -X DELETE\"",
        "sh -c 'gh api repos/o/r/dispatches -f event_type=x'",
        "$(which gh) api repos/o/r/actions/variables/SF_SYNC -X PATCH -f value=apply",
        nest("gh api -X PATCH repos/o/r/actions/variables/SF_SYNC -f value=apply", 4),
        # the gh word and api spelt otherwise
        "/opt/homebrew/bin/gh api repos/o/r/actions/variables",
        "=gh api graphql -f query=x",
        "GH api repos/o/r/actions/variables",
        "Gh API repos/o/r/actions/runs",
        "g\"\"h api repos/o/r/dispatches -f event_type=x",
        "g\\h api repos/o/r/actions/variables",
        "'gh' api repos/o/r/actions/runs",
        "gh 'api' graphql -f query=x",
        "gh a\"\"pi repos/o/r/actions/variables",
        "gh ap\\i repos/o/r/actions/secrets",
    ]
    # every other gh api call is ungated, as on main (Ryan, 2026-10-14): the harness's resume
    # reads, and writes to issues, comments and labels - silent in every mode and from a subagent
    GH_API_UNGATED = [
        "gh api repos/o/r/issues -f title=x",
        "gh api repos/o/r/pulls/1/reviews",
        "gh api --paginate repos/o/r/pulls/1/reviews",
        "gh api repos/o/r/pulls/1/reviews/2/comments",
        "gh api repos/o/r/issues/1/comments -f body=x",
        "gh api -X DELETE repos/o/r/labels/x",
        "gh api user", "gh api -X GET search/issues -f q=x", "gh -R o/r api repos/o/r/pulls/1/reviews",
        "gh api repos/o/r/pulls/1  # check", "# -X DELETE later\ngh api repos/o/r/pulls/1",
        "bash -c \"gh api repos/o/r/pulls/1\"", "/opt/homebrew/bin/gh api repos/o/r/pulls/1/reviews",
        "g\"\"h api repos/o/r/pulls/1/reviews", "GH api repos/o/r/issues/1",
        "echo =gh", "gh pr view 1",
    ]
    # prose that mentions gh api - a commit message, a PR or issue body (a heredoc with an odd
    # apostrophe too), a question on the board - is text, not a command: silent in every mode,
    # headless and from a subagent included (review of 014d2ab: the reader refused these)
    PROSE = [
        "git commit -m \"every gh api command asks; Ryan's go\"",
        "gh pr create --title x --body-file - <<'EOF'\nThe gate no longer reads gh api commands; it's text now.\nEOF",
        "harness-board needs-input 37 --question \"Should a gh api read ask? The hook doesn't parse it.\"",
        "gh issue comment 36 --body-file - <<'EOF'\nIt's done.\nEOF",
        "gh pr create --title x --body \"$(cat <<'EOF'\nThe Ryan's note on gh api\nEOF\n)\"",
        "gh pr comment 41 --body \"gh api reads stay ungated; it's as on main\"",
    ]
    # prose that also names actions/, dispatches or graphql: an accepted over-ask (Ryan,
    # 2026-10-14) - silent or the prompt, never refused in the session
    PROSE_OVER_ASK = ["git commit -m \"live gate: gh api under actions/ asks; Ryan's go\"",
                      "gh pr comment 41 --body \"gh api graphql calls ask now; it's greedy\""]
    # the live families with a quoted or split word, or in capitals: matched as written and with
    # quote and backslash characters removed, in any case (Ryan, 2026-10-14)
    SPELT_OTHERWISE = [
        "gh 'workflow' run auto-sync.yml -f apply=true",
        "gh \"variable\" set SF_SYNC --body apply",
        "GH variable set X --body 1",
        "SF data delete record -s Contact -i 003000000000001",
        "gh secret \"set\" JOTFORM_API_KEY",
        "Gh Workflow Disable auto-sync.yml",
        "sf \"apex\" run -f merge.apex",
        "g\"\"h run rerun 1234",
        "gh var\\iable delete SF_SYNC",
        "npx clasp \"push\" -f",
        "SFDX force:source:deploy -p force-app",
        "Sf Project Deploy Start -d force-app",
        "python3 sync_attendance_form.py x --ap\"\"ply",
        "curl -X PUT https://API.JOTFORM.COM/form/1/properties -d @rules.json",
    ]
    # a backslash-newline (LF or CRLF) inside a word: the shell removes it and joins the word
    # (review of 253135b), so the text is matched with those joined - one or more per family
    CONTINUED_WORDS = [
        "python3 sync_attendance_form.py x --ap\\\nply",
        "python3 sync_attendance_form.py x --pr\\\r\nune",
        "gh vari\\\nable set X --body 1",
        "g\\\nh variable set SF_SYNC --body apply",
        "gh secret s\\\r\net JOTFORM_API_KEY",
        "gh workflow run auto-sync.yml -f ap\\\nply=true",
        "gh run re\\\nrun 1234",
        "gh api repos/o/r/acti\\\nons/variables/X -X PATCH",
        "gh api gra\\\r\nphql -f query=x",
        "sf apex r\\\nun -f merge.apex",
        "sf data del\\\nete record -s Contact -i 003000000000001",
        "npx clasp pu\\\nsh -f",
        "curl -X PUT https://api.jot\\\nform.com/form/1/properties -d @rules.json",
        "python3 tools/sf_dupes.py merge --reh\\\r\nearse",
    ]
    # gh's -R/--repo between a family's words (gh variable -R o/r set): the family still asks
    # (review of 253135b) ...
    FLAGS_BETWEEN = [
        "gh variable -R o/r set X --body 1",
        "gh secret -R o/r set X",
        "gh workflow -R o/r disable x.yml",
        "gh run -R o/r rerun 1",
        "gh variable --repo o/r delete SF_SYNC",
        "gh secret --repo=o/r remove X",
        "gh workflow --repo o/r enable auto-sync.yml",
        "gh workflow -R o/r run auto-sync.yml -f apply=true",
    ]
    # ... and the same commands with a verb that changes nothing stay silent
    FLAGS_BETWEEN_READS = ["gh variable list", "gh run list", "gh variable -R o/r list", "gh run -R o/r list",
                           "gh secret --repo o/r list", "gh workflow -R o/r view auto-sync.yml",
                           "gh workflow -R o/r run auto-sync.yml"]
    # the GitHub API by its URL (curl, a script): api.github.com with actions/, dispatches or
    # graphql is live whatever the method, as gh api is (review of 253135b)
    GITHUB_URL_LIVE = [
        "curl -sS https://api.github.com/repos/o/r/actions/variables/AUTO_SYNC_APPLY -X PATCH -d '{\"value\": \"true\"}'",
        "curl -X POST https://api.github.com/repos/o/r/actions/workflows/auto-sync.yml/dispatches -d @in.json",
        "curl -s https://api.github.com/repos/o/r/actions/secrets",
        "curl -X POST https://api.github.com/graphql -d @query.json",
        "curl -X PATCH https://API.GITHUB.COM/repos/o/r/actions/variables/SF_SYNC -d @v.json",
        "python3 -c \"import requests; requests.patch('https://api.github.com/repos/o/r/actions/variables/SF_SYNC')\"",
    ]
    GITHUB_URL_READS = ["curl https://api.github.com/repos/o/r/pulls/1",
                        "curl -s 'https://api.github.com/repos/o/r/issues?state=open'"]

    def test_a_gh_api_call_on_actions_dispatches_or_graphql_asks_whatever_the_method(self):
        # "prompt, don't parse" (Ryan, 2026-10-14): the greedy text rule, so no shell construct
        # hides the call and no GET passes; refused where no prompt can be shown, and from a subagent
        for mode in ASK_MODES:
            self.assert_asks(self.GH_API_LIVE, mode=mode)
        with self.subTest("one ASKED per call"):
            self.assertEqual(self.logged(), {"ASKED": len(self.GH_API_LIVE) * len(ASK_MODES)})
        for mode in NO_PROMPT_MODES + ["foo"]:
            self.assert_denies(self.GH_API_LIVE, mode=mode)
        self.assert_denies(self.GH_API_LIVE, agent=True, saying=("agent",))

    def test_every_other_gh_api_call_is_ungated(self):
        # as on main: an issue, a comment, a label, the harness's resume reads - no prompt, and no
        # refusal in a headless run or a subagent (a refusal there would stall the harness)
        for mode in ("default", "dontAsk", "bypassPermissions", "auto", None):
            self.assert_silent(self.GH_API_UNGATED, mode=mode)
        self.assert_silent(self.GH_API_UNGATED, agent=True)
        self.assertEqual(self.logged(), {})

    def test_prose_that_mentions_gh_api_passes_in_every_mode(self):
        for mode in ASK_MODES + NO_PROMPT_MODES + ["foo"]:
            self.assert_silent(self.PROSE, mode=mode)
        self.assert_silent(self.PROSE, agent=True)
        with self.subTest("nothing logged for the prose"):
            self.assertEqual(self.logged(), {})
        # with actions/, dispatches or graphql in it too: the prompt is an accepted over-ask
        for command, run in self.runs(self.PROSE_OVER_ASK):
            with self.subTest(command=command):
                self.assertIn(self.verdict(run), ("silent", "ask"), self.show(run))

    def test_the_live_families_match_with_quoted_words_and_in_any_case(self):
        self.assert_asks(self.SPELT_OTHERWISE)
        with self.subTest("one ASKED per command"):
            self.assertEqual(self.logged(), {"ASKED": len(self.SPELT_OTHERWISE)})
        self.assert_denies(self.SPELT_OTHERWISE, mode="dontAsk", saying=("interactive", "terminal"))
        self.assert_denies(self.SPELT_OTHERWISE, agent=True, saying=("agent",))

    def test_a_word_continued_on_the_next_line_is_one_word(self):
        for mode in ASK_MODES:
            self.assert_asks(self.CONTINUED_WORDS, mode=mode)
        with self.subTest("one ASKED per command"):
            self.assertEqual(self.logged(), {"ASKED": len(self.CONTINUED_WORDS) * len(ASK_MODES)})
        for mode in NO_PROMPT_MODES:
            self.assert_denies(self.CONTINUED_WORDS, mode=mode, saying=("interactive", "terminal"))
        self.assert_denies(self.CONTINUED_WORDS, agent=True, saying=("agent",))

    def test_a_repo_flag_between_the_family_words_does_not_hide_it(self):
        self.assert_asks(self.FLAGS_BETWEEN)
        with self.subTest("one ASKED per command"):
            self.assertEqual(self.logged(), {"ASKED": len(self.FLAGS_BETWEEN)})
        self.assert_denies(self.FLAGS_BETWEEN, mode="dontAsk", saying=("interactive", "terminal"))
        self.assert_denies(self.FLAGS_BETWEEN, agent=True, saying=("agent",))
        before = self.logged()
        for mode in ("default", "dontAsk", None):
            self.assert_silent(self.FLAGS_BETWEEN_READS, mode=mode)
        self.assert_silent(self.FLAGS_BETWEEN_READS, agent=True)
        with self.subTest("nothing logged for the reads"):
            self.assertEqual(self.logged(), before)

    def test_the_github_api_by_url_asks_on_its_live_paths(self):
        for mode in ASK_MODES:
            self.assert_asks(self.GITHUB_URL_LIVE, mode=mode)
        with self.subTest("one ASKED per command"):
            self.assertEqual(self.logged(), {"ASKED": len(self.GITHUB_URL_LIVE) * len(ASK_MODES)})
        self.assert_denies(self.GITHUB_URL_LIVE, mode="dontAsk", saying=("interactive", "terminal"))
        self.assert_denies(self.GITHUB_URL_LIVE, agent=True, saying=("agent",))
        before = self.logged()
        for mode in ("default", "dontAsk", None):
            self.assert_silent(self.GITHUB_URL_READS, mode=mode)
        self.assert_silent(self.GITHUB_URL_READS, agent=True)
        with self.subTest("nothing logged for the reads"):
            self.assertEqual(self.logged(), before)


if __name__ == "__main__":
    unittest.main(verbosity=1)
