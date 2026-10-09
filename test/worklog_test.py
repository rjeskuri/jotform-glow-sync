#!/usr/bin/env python3
"""
tools/worklog.py: hours from session transcripts on the zone timeline, the log, the invoice
(synthetic data).
"""
import datetime as dt
import json
import os
import re
import time
import unittest

# first: importing helpers.common puts the repository root and tools/ on sys.path
import helpers.common  # noqa: F401
import worklog


class WorkLog(unittest.TestCase):
    """tools/worklog.py: hours from session transcripts on the zone timeline, the log, the invoice
    (synthetic data)."""
    TZ = dt.timezone(dt.timedelta(hours=8))
    UTC = dt.timezone.utc

    def at(self, hhmm, day="2026-09-26", tz=None):
        return dt.datetime.fromisoformat(f"{day}T{hhmm}:00").replace(tzinfo=tz or self.TZ)

    def utc(self, text):
        return dt.datetime.fromisoformat(text).replace(tzinfo=self.UTC)

    def zones(self, *rows):
        """rows: (since 'yyyy-mm-ddThh:mm' UTC, zone text) -> the timeline read_zones returns."""
        return [(self.utc(s), worklog.parse_zone(z), z, "") for s, z in rows]

    def plus8(self):
        return self.zones(("2026-01-01T00:00", "+08:00"))

    def entry(self, kind, when_utc, content="x", **extra):
        e = {"type": kind, "timestamp": when_utc, "message": {"content": content}}
        e.update(extra)
        return e

    def test_ryans_messages_only(self):
        ryan = worklog.is_ryans_message
        self.assertTrue(ryan(self.entry("user", "t", [{"type": "text", "text": "Pick this back up"}])))
        self.assertTrue(ryan(self.entry("user", "t", "Go ahead")))
        self.assertFalse(ryan(self.entry("user", "t", [{"type": "tool_result", "content": "ok"}])))
        self.assertFalse(ryan(self.entry("user", "t", "<task-notification><task-id>x</task-id>")))
        self.assertFalse(ryan(self.entry("user", "t", [{"type": "text", "text": "Base dir"}], isMeta=True)))
        self.assertFalse(ryan(self.entry("user", "t", "This session is being continued", isCompactSummary=True)))
        self.assertFalse(ryan(self.entry("assistant", "t", [{"type": "text", "text": "Done."}])))

    def test_blocks_gaps_and_the_ryan_rule(self):
        at = self.at
        evts = [(at("09:00"), True), (at("09:20"), False), (at("09:45"), False),    # block 1: 45 min
                (at("11:00"), False), (at("11:20"), False),                        # agent alone: not billed
                (at("14:00"), True), (at("14:10"), False)]                         # block 3: 10 min
        blocks = worklog.day_blocks(evts, self.plus8())
        day = at("09:00").date()
        self.assertEqual(worklog.blocks_text(blocks[day]), "09:00-09:45, 14:00-14:10")
        self.assertEqual(worklog.zones_text(blocks[day]), "+08:00")
        self.assertEqual(worklog.day_hours(blocks[day]), 1.0)          # 55 min -> 1.00
        # stricter gap: 09:20 is 20 min on, so the 09:00 block is that message alone, and the
        # 09:20-09:45 stretch has no message of Ryan's: not billed
        self.assertEqual(worklog.day_blocks(evts, self.plus8(), gap_minutes=15)[day][0], (at("09:00"), at("09:00")))

    def test_concurrent_sessions_count_once_and_a_session_past_midnight_stays_on_its_first_day(self):
        at = self.at
        one = [(at("10:00"), True), (at("10:40"), False)]
        two = [(at("10:05"), True), (at("10:30"), False)]                   # a second open session
        blocks = worklog.day_blocks(sorted(one + two), self.plus8())
        self.assertEqual(worklog.day_hours(blocks[at("10:00").date()]), 0.75)   # 40 min, not 65
        late = [(at("23:50"), True), (at("00:20", "2026-09-27"), False), (at("01:05", "2026-09-27"), True)]
        days = worklog.day_blocks(late, self.plus8())
        self.assertEqual(sorted(d.isoformat() for d in days), ["2026-09-26", "2026-09-27"])
        self.assertEqual(worklog.blocks_text(days[at("23:50").date()]), "23:50-00:20")   # one block, its start day
        self.assertEqual(worklog.day_hours(days[at("23:50").date()]), 0.5)
        self.assertEqual(worklog.blocks_text(days[at("01:05", "2026-09-27").date()]), "01:05-01:05")

    def test_rounding(self):
        at = self.at
        self.assertEqual(worklog.day_hours([(at("09:00"), at("09:07"))]), 0.25)    # a day with work: at least 0.25
        self.assertEqual(worklog.day_hours([(at("09:00"), at("09:52"))]), 0.75)    # 52 -> 0.75
        self.assertEqual(worklog.day_hours([(at("09:00"), at("09:53"))]), 1.0)     # 53 -> 1.00 (half up)

    def transcript(self, folder, stamps):
        """A transcript file of (UTC stamp, Ryan's?) entries."""
        path = os.path.join(folder, "s.jsonl")
        with open(path, "w") as fh:
            for stamp, ryans in stamps:
                fh.write(json.dumps(self.entry("user" if ryans else "assistant", stamp, "Go")) + "\n")
            fh.write(json.dumps({"type": "summary"}) + "\n")
            fh.write("not json\n")
        return path

    def test_events_are_utc(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            evts = worklog.events([self.transcript(d, [("2026-09-26T01:00:00.000Z", True),
                                                       ("2026-09-26T01:30:00.000Z", False)])])
        self.assertEqual(len(evts), 2)
        self.assertTrue(evts[0][1] and not evts[1][1])
        self.assertEqual(evts[0][0], self.utc("2026-09-26T01:00"))
        self.assertEqual(evts[0][0].utcoffset(), dt.timedelta(0))

    def test_the_same_rows_under_any_process_time_zone(self):
        """The regression that billed September on the wrong days: the Mac's zone at run time must not matter."""
        import tempfile
        stamps = [("2026-09-02T20:45:00.000Z", True), ("2026-09-02T21:12:00.000Z", False),   # 22:45 at +02
                  ("2026-09-12T17:00:00.000Z", True), ("2026-09-12T17:25:00.000Z", False),   # 20:00 at +03
                  ("2026-09-12T17:50:00.000Z", False), ("2026-09-12T18:15:00.000Z", False),
                  ("2026-09-12T18:30:00.000Z", False)]
        zones = self.zones(("2026-08-28T00:00", "+02:00"), ("2026-09-03T00:00", "+03:00"),
                           ("2026-09-17T00:00", "+08:00"))
        saved = os.environ.get("TZ")
        results = []
        with tempfile.TemporaryDirectory() as d:
            path = self.transcript(d, stamps)
            try:
                for tz in ("UTC", "Asia/Tokyo", "Pacific/Pago_Pago"):
                    os.environ["TZ"] = tz
                    time.tzset()
                    days = worklog.day_blocks(worklog.events([path]), zones)
                    results.append({k.isoformat(): (worklog.day_hours(b), worklog.blocks_text(b)) for k, b in days.items()})
            finally:
                if saved is None:
                    os.environ.pop("TZ", None)
                else:
                    os.environ["TZ"] = saved
                time.tzset()
        self.assertEqual(results[0], {"2026-09-02": (0.5, "22:45-23:12"), "2026-09-12": (1.5, "20:00-21:30")})
        self.assertTrue(results[0] == results[1] == results[2])

    def test_zone_parsing_and_zone_at(self):
        self.assertEqual(worklog.parse_zone("+09:00").utcoffset(None), dt.timedelta(hours=9))
        self.assertEqual(worklog.parse_zone("-03:30").utcoffset(None), -dt.timedelta(hours=3, minutes=30))
        self.assertEqual(str(worklog.parse_zone("Asia/Tokyo")), "Asia/Tokyo")
        for bad in ("+15:00", "+09:60", "9", "", "Mars/Base", "+9:00"):
            with self.assertRaises(ValueError, msg=bad):
                worklog.parse_zone(bad)
        self.assertEqual(worklog.parse_instant("2026-09-29T12:37:00Z"), self.utc("2026-09-29T12:37"))
        with self.assertRaises(ValueError):
            worklog.parse_instant("2026-09-29T12:37:00")                       # no offset
        zones = self.zones(("2026-09-17T00:00", "+08:00"), ("2026-09-29T12:37", "Asia/Tokyo"))
        at = worklog.zone_at
        self.assertIsNone(at(zones, self.utc("2026-09-16T23:59")))              # before the timeline
        self.assertEqual(at(zones, self.utc("2026-09-29T12:36")), zones[0][1])
        self.assertEqual(at(zones, self.utc("2026-09-29T12:37")), zones[1][1])  # since <= t: the switch itself is new

    def test_an_iana_zone_follows_daylight_saving(self):
        zones = self.zones(("2026-10-01T00:00", "Europe/London"))
        evts = [(self.utc("2026-10-24T12:00"), True), (self.utc("2026-10-26T12:00"), True)]
        days = worklog.day_blocks(evts, zones)
        self.assertEqual(worklog.blocks_text(days[dt.date(2026, 10, 24)]), "13:00-13:00")   # BST
        self.assertEqual(worklog.blocks_text(days[dt.date(2026, 10, 26)]), "12:00-12:00")   # GMT
        self.assertEqual(worklog.zones_text(days[dt.date(2026, 10, 24)]), "+01:00")

    def test_a_block_across_a_zone_switch_and_a_travel_day(self):
        zones = self.zones(("2026-09-17T00:00", "+08:00"), ("2026-09-29T12:37", "Asia/Tokyo"))
        across = [(self.utc("2026-09-29T12:20"), True), (self.utc("2026-09-29T12:50"), False)]
        day = worklog.day_blocks(across, zones)[dt.date(2026, 9, 29)]
        self.assertEqual(worklog.blocks_text(day), "20:20-20:50")      # the end on the start's clock
        travel = [(self.utc("2026-09-29T03:00"), True), (self.utc("2026-09-29T14:00"), True)]
        day = worklog.day_blocks(travel, zones)[dt.date(2026, 9, 29)]
        self.assertEqual(worklog.zones_text(day), "+08:00/+09:00")
        self.assertEqual(worklog.blocks_text(day), "11:00-11:00 (+08:00), 23:00-23:00 (+09:00)")

    def test_blocks_before_the_timeline_are_left_out(self):
        zones = self.zones(("2026-09-01T00:00", "+02:00"))
        evts = [(self.utc("2026-08-20T10:00"), True), (self.utc("2026-09-01T10:00"), True)]
        self.assertEqual(sorted(worklog.day_blocks(evts, zones)), [dt.date(2026, 9, 1)])

    def test_read_zones_refuses_a_bad_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "tz.csv")
            for body, why in [("since,zone,evidence\n", "no rows"),
                              ("since,zone,evidence\n2026-09-02T00:00:00+00:00,+02:00,\n"
                               "2026-09-01T00:00:00+00:00,+03:00,\n", "time order"),
                              ("since,zone,evidence\n2026-09-01T00:00:00+00:00,Mars/Base,\n", "line 2"),
                              ("since,zone,evidence\n2026-09-01T00:00:00,+02:00,\n", "line 2")]:
                with open(path, "w") as fh:
                    fh.write(body)
                with self.assertRaises(ValueError, msg=why) as cm:
                    worklog.read_zones(path)
                self.assertIn(why, str(cm.exception))
            with open(path, "w") as fh:
                fh.write("since,zone,evidence\n2026-09-01T00:00:00Z,+02:00,commits\n"
                         "2026-09-29T12:37:00+00:00,Asia/Tokyo,clock\n")
            zones = worklog.read_zones(path)
            self.assertEqual([z[2] for z in zones], ["+02:00", "Asia/Tokyo"])
            with self.assertRaises(ValueError):
                worklog.read_zones(os.path.join(d, "missing.csv"))

    def test_the_mac_must_be_on_the_timelines_zone(self):
        from zoneinfo import ZoneInfo
        zones = self.zones(("2026-09-17T00:00", "+08:00"))
        now = self.utc("2026-09-30T02:00")
        evts = [(self.utc("2026-09-28T14:00"), True), (self.utc("2026-09-28T15:55"), False),
                (self.utc("2026-09-29T13:15"), True), (self.utc("2026-09-30T01:50"), True)]
        self.assertIsNone(worklog.mac_zone_problem(zones, dt.timezone(dt.timedelta(hours=8)), None, now, evts))
        tokyo = ZoneInfo("Asia/Tokyo")
        commits = [self.commit("2026-09-28T14:43", 8)]                          # the last one on the old clock
        msg = worklog.mac_zone_problem(zones, tokyo, "Asia/Tokyo", now, evts, commits=commits)
        self.assertIn("--zone Asia/Tokyo", msg)
        # no clock-change time: the middle of the first idle stretch of 6 h+ after that commit, to the
        # hour - not the later stretch after a session that was already on the new clock
        self.assertIn("--since 2026-09-29T02:00+00:00", msg)
        self.assertIn("abc1234", msg)
        # the clock-change time, when nobody was working near it
        msg = worklog.mac_zone_problem(zones, tokyo, "Asia/Tokyo", now, evts, changed=self.utc("2026-09-29T12:37"),
                                       commits=commits)
        self.assertIn("--since 2026-09-29T12:37+00:00", msg)
        # ...but not when it falls inside a session
        msg = worklog.mac_zone_problem(zones, tokyo, "Asia/Tokyo", now, evts, changed=self.utc("2026-09-29T13:20"),
                                       commits=commits)
        self.assertIn("--since 2026-09-29T02:00+00:00", msg)
        # the same offset under another name is no change
        zones = self.zones(("2026-09-29T12:37", "Asia/Tokyo"))
        self.assertIsNone(worklog.mac_zone_problem(zones, dt.timezone(dt.timedelta(hours=9)), None, now, evts))

    def commit(self, when, offset_hours, sha="abc1234", committer="Ryan"):
        return (self.utc(when), dt.timedelta(hours=offset_hours), sha, "A commit", committer)

    def test_commit_offsets_must_agree_with_the_timeline(self):
        zones = self.zones(("2026-09-03T00:00", "+03:00"), ("2026-09-17T00:00", "+08:00"))
        start = self.utc("2026-09-01T00:00")
        ok = [self.commit("2026-09-12T17:23", 3), self.commit("2026-09-20T05:52", 8)]
        self.assertEqual(worklog.commit_problems(ok, zones, start), [])
        missed_trip = ok + [self.commit("2026-09-24T06:00", 9, "def5678")]      # the timeline says +08
        bad = worklog.commit_problems(missed_trip, zones, start)
        self.assertEqual(len(bad), 1)
        self.assertTrue(bad[0].startswith("def5678") and "+09:00" in bad[0] and "+08:00" in bad[0])
        self.assertEqual(worklog.commit_problems(missed_trip, zones, start, ignore=["def5678"]), [])
        github = ok + [self.commit("2026-09-24T06:00", 0, "fff0000", committer="GitHub")]
        self.assertEqual(worklog.commit_problems(github, zones, start), [])
        old = [self.commit("2026-08-20T10:00", 5)]                               # before the window / timeline
        self.assertEqual(worklog.commit_problems(old, zones, start), [])

    def in_zones(self, fn, zones=("UTC", "Asia/Tokyo", "Pacific/Pago_Pago")):
        """fn() under each process TZ (restored afterwards) -> the list of results."""
        saved, out = os.environ.get("TZ"), []
        try:
            for tz in zones:
                os.environ["TZ"] = tz
                time.tzset()
                out.append(fn())
        finally:
            if saved is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = saved
            time.tzset()
        return out

    def test_commit_subjects_are_dated_by_the_timeline(self):
        zones = self.zones(("2026-09-03T00:00", "+03:00"), ("2026-09-17T00:00", "+08:00"))
        commits = [(self.utc("2026-09-12T17:23"), dt.timedelta(hours=3), "a", "Evening rollout", "Ryan"),
                   (self.utc("2026-09-12T22:30"), dt.timedelta(hours=3), "b", "After midnight", "Ryan"),
                   # recorded at +09 but the timeline says +08: the timeline wins (23:30 on 09-20, not 00:30 on 09-21)
                   (self.utc("2026-09-20T15:30"), dt.timedelta(hours=9), "c", "Late", "Ryan"),
                   (self.utc("2026-08-01T10:00"), dt.timedelta(hours=1), "d", "Before the timeline", "Ryan")]
        want = {"2026-09-12": ["Evening rollout"], "2026-09-13": ["After midnight"], "2026-09-20": ["Late"]}
        for got in self.in_zones(lambda: worklog.subjects_by_day(commits, zones)):
            self.assertEqual(got, want)

    def test_a_commit_goes_to_the_day_its_block_started(self):
        zones = self.zones(("2026-09-29T00:00", "+09:00"))
        evts = [(self.utc("2026-09-29T13:15"), True), (self.utc("2026-09-29T15:36"), False)]   # 22:15-00:36 JST
        for step in range(15, 141, 15):                                                         # one long session
            evts.append((self.utc("2026-09-29T13:15") + dt.timedelta(minutes=step), False))
        days = worklog.day_blocks(sorted(evts), zones)
        commit = (self.utc("2026-09-29T15:40"), dt.timedelta(hours=9), "e", "Past midnight", "Ryan")   # 00:40 on 09-30
        self.assertEqual(worklog.subjects_by_day([commit], zones, days), {"2026-09-29": ["Past midnight"]})
        self.assertEqual(worklog.subjects_by_day([commit], zones), {"2026-09-30": ["Past midnight"]})

    def test_events_stay_utc_under_any_process_time_zone(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = self.transcript(d, [("2026-09-26T01:00:00.000Z", True), ("2026-09-26T20:00:00.000Z", True)])
            runs = self.in_zones(lambda: worklog.events([path]))
            after, end = self.utc("2026-09-26T00:00"), self.utc("2026-09-27T12:00")
            picks = self.in_zones(lambda: worklog.suggest_since(worklog.events([path]), after, end))
        for evts in runs:
            self.assertTrue(all(t.utcoffset() == dt.timedelta(0) for t, _ in evts))
            self.assertIs(evts[0][0].tzinfo, dt.timezone.utc)
        self.assertTrue(picks[0] == picks[1] == picks[2])

    def test_system_zone_reads_etc_localtime_not_the_shell(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            link = os.path.join(d, "localtime")
            os.symlink("/var/db/timezone/zoneinfo/Europe/London", link)       # need not exist
            stamp = 1790000000
            os.utime(link, (stamp, stamp), follow_symlinks=False)
            plain = os.path.join(d, "plain")
            open(plain, "w").close()
            odd = os.path.join(d, "odd")
            os.symlink("/nowhere/Asia/Tokyo", odd)
            saved = worklog.LOCALTIME
            try:
                worklog.LOCALTIME = link
                tz, name, changed = self.in_zones(worklog.system_zone, ("Asia/Tokyo",))[0]
                self.assertEqual((str(tz), name), ("Europe/London", "Europe/London"))
                self.assertEqual(changed, dt.datetime.fromtimestamp(stamp, dt.timezone.utc))
                for fallback in (plain, odd):
                    worklog.LOCALTIME = fallback
                    _, name, changed = worklog.system_zone()
                    self.assertEqual((name, changed), (None, None))
            finally:
                worklog.LOCALTIME = saved

    def test_where_a_zone_change_may_be_recorded(self):
        from zoneinfo import ZoneInfo
        tokyo = ZoneInfo("Asia/Tokyo")
        zones = self.zones(("2026-09-17T00:00", "+08:00"))
        now = self.utc("2026-09-30T02:00")
        evts = [(self.utc("2026-09-28T15:55"), True), (self.utc("2026-09-29T13:15"), True)]
        commits = [self.commit("2026-09-28T14:43", 8), self.commit("2026-09-29T14:00", 9, "fff1111")]
        check = worklog.since_problems
        self.assertEqual(check(self.utc("2026-09-29T02:00"), tokyo, zones, evts, commits, now), [])
        old = check(self.utc("2026-09-28T12:00"), tokyo, zones, evts, commits, now)
        self.assertTrue(any("old clock" in p for p in old))                          # 14:43 was still +08
        new = check(self.utc("2026-09-29T14:30"), tokyo, zones, evts, commits, now)
        self.assertTrue(any("new clock" in p and "fff1111" in p for p in new))       # 14:00 was already +09
        # inside a session with no commits around it: refused
        quiet = [self.commit("2026-09-20T01:00", 8)]
        inside = check(self.utc("2026-09-29T13:30"), tokyo, zones, evts, quiet, now)
        self.assertTrue(any("inside a session" in p for p in inside))
        # ...but a clock change during a session, between its old- and new-clock commits, is fine
        busy = [(self.utc("2026-10-05T10:00"), True)] + [
            (self.utc("2026-10-05T10:00") + dt.timedelta(minutes=m), False) for m in range(10, 121, 10)]
        mid = [self.commit("2026-10-05T10:30", 8), self.commit("2026-10-05T11:30", 9, "fff2222")]
        self.assertEqual(check(self.utc("2026-10-05T11:00"), tokyo, zones, busy, mid, self.utc("2026-10-06T00:00")), [])
        self.assertTrue(any("future" in p for p in check(self.utc("2026-10-02T00:00"), tokyo, zones, evts, commits, now)))
        self.assertTrue(any("not after the last row" in p for p in
                            check(self.utc("2026-09-10T00:00"), tokyo, zones, evts, commits, now)))

    def test_the_suggested_switch_is_one_zone_accepts_and_update_then_passes(self):
        from zoneinfo import ZoneInfo
        tokyo = ZoneInfo("Asia/Tokyo")
        zones = self.zones(("2026-09-17T00:00", "+08:00"))
        u = self.utc

        def session(start, minutes, ryan=True):
            t0 = u(start)
            return [(t0, ryan)] + [(t0 + dt.timedelta(minutes=m), False) for m in range(10, minutes + 1, 10)]

        def accepted(evts, commits, now, changed=None):
            msg = worklog.mac_zone_problem(zones, tokyo, "Asia/Tokyo", now, evts, changed, commits=commits)
            m = re.search(r"--since (\S+)\+00:00", msg)
            self.assertIsNotNone(m, msg)
            since = u(m.group(1))
            self.assertEqual(worklog.since_problems(since, tokyo, zones, evts, commits, now), [], msg)
            timeline = zones + [(since, tokyo, "Asia/Tokyo", "")]
            self.assertEqual(worklog.commit_problems(commits, timeline, zones[0][0]), [])
            return since

        # the clock changed 5 min before an arrival session that commits on the new clock (a short hop)
        evts = session("2026-10-05T08:00", 120) + session("2026-10-05T15:00", 120)
        commits = [self.commit("2026-10-05T10:00", 8), self.commit("2026-10-05T16:30", 9, "fff3333")]
        since = accepted(evts, commits, u("2026-10-05T18:00"), changed=u("2026-10-05T14:55"))
        self.assertTrue(u("2026-10-05T10:00") < since < u("2026-10-05T15:00"))
        # the clock changed 10 min before a session; a session with no commits sat before the flight:
        # the switch is after that session, not the night before it
        evts = session("2026-10-05T08:00", 120) + session("2026-10-06T00:00", 115) + session("2026-10-06T16:10", 60)
        commits = [self.commit("2026-10-05T10:00", 8)]
        since = accepted(evts, commits, u("2026-10-06T17:30"), changed=u("2026-10-06T16:00"))
        self.assertEqual(since, u("2026-10-06T09:00"))
        # no clock-change time: the longest idle stretch, never "now"
        since = accepted(evts, commits, u("2026-10-06T17:30"))
        self.assertTrue(u("2026-10-06T01:55") < since < u("2026-10-06T16:10"))
        # the clock changed during a session with commits on both clocks: no idle moment, no command
        evts = session("2026-10-05T10:00", 120)
        commits = [self.commit("2026-10-05T10:30", 8), self.commit("2026-10-05T11:30", 9, "fff4444")]
        msg = worklog.mac_zone_problem(zones, tokyo, "Asia/Tokyo", u("2026-10-05T12:00"), evts, commits=commits)
        self.assertIn("pick one by hand", msg)
        self.assertNotRegex(msg, r"--since \d")

    def test_a_switch_date_means_midnight_on_the_new_clock(self):
        switch = worklog.parse_switch
        self.assertEqual(switch("2026-10-02", "Europe/London")[0], self.utc("2026-10-01T23:00"))   # BST
        self.assertEqual(switch("2026-10-02", "+09:00")[0], self.utc("2026-10-01T15:00"))
        self.assertEqual(switch("2026-10-02", "-03:00")[0], self.utc("2026-10-02T03:00"))
        self.assertEqual(switch("2026-10-02T12:37:00Z", "Asia/Tokyo")[0], self.utc("2026-10-02T12:37"))
        for bad in [("2026-10-02T12:37", "Asia/Tokyo"), ("2026-10-02", "Mars/Base"), ("", "+09:00")]:
            with self.assertRaises(ValueError, msg=bad):
                switch(*bad)
        plus8, tokyo = worklog.parse_zone("+08:00"), worklog.parse_zone("Asia/Tokyo")
        self.assertEqual(worklog.first_day(self.utc("2026-09-29T15:30"), plus8, tokyo), dt.date(2026, 9, 29))
        self.assertEqual(worklog.first_day(self.utc("2026-09-29T16:30"), plus8, tokyo), dt.date(2026, 9, 30))

    def test_append_zone_keeps_rows_apart(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "tz.csv")
            with open(path, "w") as fh:
                fh.write("since,zone,evidence\n2026-09-17T00:00:00+00:00,+08:00,commits")      # no final newline
            worklog.append_zone(self.utc("2026-09-29T12:37"), "Asia/Tokyo", "clock", path)
            zones = worklog.read_zones(path)
            self.assertEqual([z[2] for z in zones], ["+08:00", "Asia/Tokyo"])
            with open(path, "rb") as fh:
                self.assertNotIn(b"\r", fh.read())
            with open(path, "w") as fh:
                fh.write("since,zone,evidence\n2026-09-17T00:00:00+00:00,+08:00,commits2026-09-29T12:37:00+00:00,"
                         "Asia/Tokyo,clock\n")                                              # two rows run together
            with self.assertRaises(ValueError) as cm:
                worklog.read_zones(path)
            self.assertIn("more than 3 columns", str(cm.exception))

    def recount(self, rows, evts, today, since, **kw):
        return worklog.update_rows(rows, evts, [], self.plus8(), since, today, **kw)

    def test_update_refuses_or_drops_a_stale_row_only_as_asked(self):
        evts = [(self.at("09:00", "2026-09-26"), True), (self.at("09:30", "2026-09-26"), False)]
        rows = [{"date": "2026-09-25", "hours": "0.75", "blocks": "10:00-10:45", "description": "Moved", "source": "auto"},
                {"date": "2026-09-25", "hours": "1.00", "blocks": "", "description": "Call", "source": "manual"}]
        today, since = dt.date(2026, 9, 30), dt.date(2026, 9, 20)
        with self.assertRaises(SystemExit) as cm:
            self.recount(rows, evts, today, since)
        self.assertIn("--drop-stale", str(cm.exception.code))
        new, computed, dropped, kept, held = self.recount(rows, evts, today, since, drop_stale=True)
        self.assertEqual(dropped, ["2026-09-25"])
        self.assertEqual([(r["date"], r["source"]) for r in new], [("2026-09-25", "manual"), ("2026-09-26", "auto")])
        # 40 days on, the row may just have lost its transcripts: kept, whatever the flag
        old_evts = [(self.at("09:00", "2026-11-05"), True)]
        new, *_, kept, held = self.recount(rows, old_evts, dt.date(2026, 11, 5), since, drop_stale=True)
        self.assertEqual(kept, ["2026-09-25"])
        self.assertIn(("2026-09-25", "auto"), [(r["date"], r["source"]) for r in new])
        # another transcript folder never drops a row
        new, _, dropped, kept, _ = self.recount(rows, evts, today, since, drop_stale=True, custom_folder=True)
        self.assertEqual((dropped, kept), ([], ["2026-09-25"]))

    def test_update_refuses_work_before_the_timeline(self):
        zones = self.zones(("2026-09-26T00:00", "+08:00"))
        evts = [(self.utc("2026-09-25T20:00"), True)]                      # 2026-09-26 04:00 at +08
        with self.assertRaises(SystemExit) as cm:
            worklog.update_rows([], evts, [], zones, dt.date(2026, 9, 26), dt.date(2026, 9, 30))
        self.assertIn("predates", str(cm.exception.code))

    def test_an_old_or_partial_recount_never_lowers_a_logged_row(self):
        evts = [(self.at("09:00", "2026-09-01"), True), (self.at("09:30", "2026-09-01"), False)]
        rows = [{"date": "2026-09-01", "hours": "2.75", "blocks": "08:00-10:45", "description": "Kept", "source": "auto"}]
        since = dt.date(2026, 9, 1)
        # a month later a session of that day may have expired: the row stays, reported as held
        new, computed, _, _, held = self.recount(rows, evts, dt.date(2026, 10, 31), since)
        self.assertEqual((held, new[0]["hours"]), (["2026-09-01"], "2.75"))
        # another folder: held too
        new, _, _, _, held = self.recount(rows, evts, dt.date(2026, 9, 10), since, custom_folder=True)
        self.assertEqual((held, new[0]["hours"]), (["2026-09-01"], "2.75"))
        # a recent day recounts; --rewrite-old lets a deliberate correction of an old one through
        new, *_, held = self.recount(rows, evts, dt.date(2026, 9, 10), since)
        self.assertEqual((held, new[0]["hours"]), ([], "0.50"))
        new, *_, held = self.recount(rows, evts, dt.date(2026, 10, 31), since, rewrite_old=True)
        self.assertEqual((held, new[0]["hours"]), ([], "0.50"))

    def test_days_before_the_window_must_not_change_and_a_missed_day_is_found(self):
        rows = [{"date": "2026-10-01", "hours": "1.00", "blocks": "10:00-11:00", "source": "auto"},
                {"date": "2026-10-03", "hours": "1.00", "blocks": "10:00-11:00", "source": "auto"}]
        computed = {"2026-10-01": (1.0, "10:00-11:00", "+09:00"), "2026-10-03": (1.0, "10:00-11:00", "+09:00"),
                    "2026-10-04": (2.0, "10:00-12:00", "+09:00"), "2026-10-20": (1.0, "10:00-11:00", "+09:00")}
        today = dt.date(2026, 10, 20)
        # the default window reaches back to the last logged day when the log is behind
        self.assertEqual(worklog.default_since(rows, today), dt.date(2026, 10, 3))
        self.assertEqual(worklog.default_since(rows, dt.date(2026, 10, 10)), dt.date(2026, 9, 26))  # not behind
        self.assertEqual(worklog.default_since(rows, dt.date(2026, 11, 30)), dt.date(2026, 11, 1))  # never past 29 days
        self.assertIsNone(worklog.window_problems(rows, computed, dt.date(2026, 10, 3), today))
        # an explicit --since past a never-logged day refuses and names it
        msg = worklog.window_problems(rows, computed, dt.date(2026, 10, 6), today)
        self.assertIn("2026-10-04: no row -> 2.00 h", msg)
        self.assertIn("--since 2026-10-04", msg)
        # a logged day whose work vanished (recent) refuses; the log's own start and expired days do not
        self.assertIn("no work", worklog.window_problems(rows, {}, dt.date(2026, 10, 2), today))
        self.assertIsNone(worklog.window_problems(rows, {}, dt.date(2026, 10, 2), dt.date(2026, 12, 1)))
        self.assertIsNone(worklog.window_problems(rows, {"2026-09-30": (1.0, "x", "+09:00")}, dt.date(2026, 10, 1), today))
        self.assertIsNone(worklog.window_problems(rows, {}, dt.date(2026, 10, 2), today, earliest=dt.date(2026, 10, 2)))

    def test_stale_rows_go_only_when_recent_and_from_this_repos_transcripts(self):
        rows = [{"date": "2026-09-05", "hours": "0.75", "source": "auto"},
                {"date": "2026-09-05", "hours": "1.00", "source": "manual"},
                {"date": "2026-09-04", "hours": "0.75", "source": "auto"}]
        computed = {"2026-09-04": (0.75, "20:32-21:15", "+03:00")}
        since = dt.date(2026, 9, 1)
        self.assertEqual(worklog.stale_days(rows, computed, since, dt.date(2026, 9, 30), False), (["2026-09-05"], []))
        # a month later its transcripts may have expired: kept, never dropped
        self.assertEqual(worklog.stale_days(rows, computed, since, dt.date(2026, 10, 20), False), ([], ["2026-09-05"]))
        # another transcript folder never drops anything
        self.assertEqual(worklog.stale_days(rows, computed, since, dt.date(2026, 9, 30), True), ([], ["2026-09-05"]))

    def test_merge_keeps_manual_rows_and_written_descriptions(self):
        rows = [{"date": "2026-09-25", "hours": "2.00", "blocks": "x", "description": "Curated text", "source": "auto"},
                {"date": "2026-09-25", "hours": "1.00", "blocks": "", "description": "Call", "source": "manual"},
                {"date": "2026-09-05", "hours": "0.75", "blocks": "z", "description": "Moved", "source": "auto"},
                {"date": "2026-08-30", "hours": "3.00", "blocks": "y", "description": "Old", "source": "auto"}]
        computed = {"2026-09-25": (2.5, "09:00-11:30", "+08:00"), "2026-09-26": (1.0, "10:00-11:00", "+08:00")}
        subjects = {"2026-09-26": ["Second commit", "First commit"]}
        out = worklog.merge(rows, computed, subjects, drop=["2026-09-05"])
        by = {(r["date"], r["source"]): r for r in out}
        self.assertEqual(by[("2026-09-25", "auto")]["hours"], "2.50")
        self.assertEqual(by[("2026-09-25", "auto")]["zone"], "+08:00")
        self.assertEqual(by[("2026-09-25", "auto")]["description"], "Curated text")
        self.assertEqual(by[("2026-09-25", "manual")]["hours"], "1.00")
        self.assertEqual(by[("2026-09-26", "auto")]["description"], "First commit; Second commit")
        self.assertNotIn(("2026-09-05", "auto"), by)     # dropped as asked
        self.assertIn(("2026-08-30", "auto"), by)        # an expired day is never dropped
        self.assertEqual([r["date"] for r in out], sorted(r["date"] for r in out))

    def test_invoice_rows(self):
        rows = [{"date": "2026-09-25", "hours": "2.50", "description": "Fix", "source": "auto"},
                {"date": "2026-09-25", "hours": "1.00", "description": "Call", "source": "manual"},
                {"date": "2026-09-26", "hours": "1.25", "description": "", "source": "auto"},
                {"date": "2026-10-01", "hours": "4.00", "description": "Next month", "source": "auto"}]
        out = worklog.invoice_rows(rows, "2026-09", rate=60)
        self.assertEqual(out[0], ["Date", "Hours", "Description", "Amount"])
        self.assertEqual(out[1], ["2026-09-25", "3.50", "Fix / Call", "210.00"])
        self.assertEqual(out[-1], ["Total", "4.75", "", "285.00"])
        self.assertEqual(len(worklog.invoice_rows(rows, "2026-09")[0]), 3)   # no rate, no Amount

    def test_log_round_trip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "w", "log.csv")
            rows = [{"date": "2026-09-25", "hours": "1.00", "blocks": "09:00-10:00",
                     "description": 'Commas, "quotes"\nand a newline', "source": "auto", "zone": "+08:00"}]
            worklog.write_log(rows, path)
            self.assertEqual(worklog.read_log(path), rows)
            with open(path, "rb") as fh:
                self.assertNotIn(b"\r", fh.read())     # LF only: an update must not rewrite every line

    def test_transcripts_dir(self):
        repo = os.sep + os.path.join("srv", "jotform-glow-sync")          # built, not a literal path
        self.assertTrue(worklog.transcripts_dir(repo).endswith(
            os.path.join(".claude", "projects", "-srv-jotform-glow-sync")))


if __name__ == "__main__":
    unittest.main(verbosity=1)
