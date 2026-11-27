#!/usr/bin/env node
'use strict';
/**
 * Offline tests for ticket #237: the club folders already directly in each region folder of the
 * Shared Drive (named `<Club Name> <MM-DD-YYYY>` since 2026-10-30, the club alone before that, so
 * carrying no partner) are re-filed once under `<Region>/<Partner>/<YYYY-MM | undated>/`, the layout
 * #225 gives new photos. The partner comes from REFILE_LIST, a club -> partner list written once by
 * tools/refile_list.py (test/refile_list_test.py). drive-sync/*.gs are loaded together in a vm
 * sandbox as in test/drive_sync_layout_test.js (which, with test/drive_sync_test.js, stays as it is).
 *
 * Ryan's decisions (2026-11-23): partner source option A (the list; the mover reads no sheet, no new
 * scope); folders with no date go to `<Region>/<Partner>/undated/`; a club whose partner is not found
 * stays where it is and is listed in the dry run with the reason.
 *
 * The orchestrator's rulings, pinned here:
 *   G1  drive-sync/Refile.gs: planRefile_(regions, list) (pure), previewRefile (dry run), refileExisting.
 *         regions  {<Region>: {id, folders: [Folder]}}: each region folder's direct LIVE subfolders;
 *                  Folder = {id, name, files: <live files directly in it>, folders: [Folder]}, 3 levels deep
 *         list     REFILE_LIST rows [{region, partner, club}]
 *         returns  {refile: [{region, id, name, path: [<Partner>, <YYYY-MM | undated>], to: <region folder id>,
 *                             partnerId, monthId}], stays: [{region, id, name, code, why}]}; every region-root
 *                  folder in exactly one list
 *   G3  matching: each row offers its club and `<club> - <partner>`, compared whitespace-collapsed and
 *       lower-cased; the folder's own region's rows first, else every row; 1 partner found, 2+ ambiguous
 *       (why names them), 0 no-partner
 *   G4  names: a layout name (photoPath_) keeps its own path, no lookup; `<blank> | <club> | <MM-DD-YYYY>
 *       [| week]` -> club and date; `<club> <MM-DD-YYYY>` with a real date -> its month; date-shaped but
 *       not a real date -> bad-date; anything else -> the whole trimmed name is the club, `undated`
 *   G5  a root folder holding any live folder never moves (holds-folders); two or more photo folders of
 *       one exact name: all stay (duplicate-name)
 *   G6  a photo folder named exactly like a partner targeted in its region: it and that partner's entries
 *       there stay (partner-name); else root folders named P holding folders: 0 made, 1 reused, 2+
 *       partner-folders; inside, the month: 0 made, 1 reused, 2+ month-folders; the photo folder's exact
 *       name already in that month folder: exists
 *   G7  the real run moves each folder itself, one Drive.Files.update({}, id, null, {addParents: month,
 *       removeParents: region, supportsAllDrives: true}); partner/month folders by Drive.Files.create once
 *       per run; nothing renamed or trashed; re-checked just before (moved or trashed since the read:
 *       skipped), read back after (REFILE_FAILED); a re-run after a complete run moves nothing
 *   G8  logs: each region-root folder by name with its target path or its reason; never a file's name;
 *       previewRefile makes and moves nothing
 *   G9  REFILE_LIST missing or malformed: both entry points refuse before any Drive call
 *
 * The test-author's readings (reversible; the coder follows them):
 *   T1  A name is trimmed before it is parsed. `<club> <MM-DD-YYYY>`: the last whitespace-separated token is
 *       the date, the club the rest (G3 compares it collapsed and lower-cased). A blank-partner layout name's
 *       week is optional, as in photoPath_.
 *   T2  The photo folder named exactly like a partner targeted in its region stays with code `partner-name`
 *       itself; one named like a partner no entry of its region targets is looked up like any other name.
 *   T3  The exact-name rules (duplicate-name, the partner and month levels, exists) are case- and
 *       space-sensitive: `bright stars 10-02-2026` is not a duplicate of `Bright Stars 10-02-2026`, a
 *       root folder `fixture partner gamma` is not the partner folder of `Fixture Partner Gamma`.
 *   T4  partnerId and monthId are null (not absent) when the run must make that folder.
 *   T5  The dry run logs, for each region-root folder, a line with its trimmed name and either its target
 *       `<Region>/<Partner>/<YYYY-MM|undated>` or its stay `code`; an ambiguous line also names the partners.
 *   T6  REFILE_LIST reaches the sandbox as Ryan pastes it: a generated RefileList.gs
 *       (`const REFILE_LIST = [...]`) appended after drive-sync/*.gs. So Refile.gs neither declares it nor
 *       reads it at load.
 *   T7  G9's refusal is a thrown Error whose message names REFILE_LIST, with no DriveApp or Drive call
 *       before it. Malformed: not an array; a row that is not an object, or whose partner or club is not a
 *       non-empty string. (An empty array, and a row's region, are not pinned.)
 *   T8  The fake Drive changes a folder "after the read" at the first access to it by id (Files.get,
 *       Files.update, DriveApp.getFolderById / getFileById): the read lists folders, the re-check gets it
 *       by id. Such a folder is logged by name on a line matching /moved or trashed/i; the run does not
 *       end in an error for it.
 *   T9  A move Drive answers but the read-back does not show: a line with REFILE_FAILED and the folder's
 *       name; the other folders still move (whether the run then throws is not pinned).
 *   T10 The move's resource is `{}` (G7): no key at all, so nothing is renamed or trashed by it.
 *   T11 Ryan's requirement (2026-11-23, after his naming change and before his ` | ` fix the forms' Drive
 *       integration named folders with spaces only): `<Partner> <Club> <MM-DD-YYYY> [<Week>]`, the week blank
 *       on a special event. In any name without ` | ` the LAST date-shaped word is the date (this widens T1's
 *       "last token") and every word after it is dropped (the week; also e.g. Drive's ` (1)` on a
 *       `<club> <MM-DD-YYYY>` name, which then files to that date's month); the words before it are looked up
 *       as G3 says, each row also offering `<partner> <club>` and `<partner> <club> - <partner>`. So the partner
 *       before the club settles a club two partners share; a pair not on the list (another partner's club, a
 *       partner the list does not have) is no-partner, never filed by the club or the partner alone; a
 *       date-shaped word that is not a real date is bad-date, week or not.
 *
 * Ticket #262 (2026-11-24): the live dry run stopped in the first region, Drive refusing the batched listing (up to
 * REFILE_BATCH parents joined by `or`) with "The attempted action requires shared drive membership.": the account that
 * runs the mover reaches the region folders through folder sharing and is no member of the Shared Drive. Ryan: read
 * folder by folder, slower is fine, do not add the account to the drive. The test-author's readings for it:
 *   T12 Every Drive.Files.list the re-filing sends names exactly one folder: one `'<id>' in parents` term, ANDed with
 *       the rest (trashed, mimeType, name). Every scenario's fake Drive refuses, with the live error, a query naming
 *       two or more parents, and one naming none (a whole-drive listing needs the same membership: #183). corpora /
 *       driveId as listSharedDrive_ sends them (the fake does not tell them apart). The fake answers only the fields
 *       asked (`files(a, b)`; none given: kind, id, name, mimeType); a listing that returns files while asking for their
 *       `name` (or every field) asks Drive for a file's name (G8), and so does DriveApp File.getName.
 *   T13 The budget scenarios run on a fake clock: the sandbox's `Date` (Date.now(), new Date()) reads a clock that
 *       advances STEP ms at each Drive.Files or DriveApp call, 10 minutes between runs, and never otherwise.
 *       STEP = RUN_BUDGET_MS / 2 / 120: a run's read budget (`started + RUN_BUDGET_MS / 2`) holds about 120 Drive
 *       calls, the whole run about 240, and no run may pass Apps Script's 6 minutes. The re-filing reads time only
 *       from Date.now() / new Date(). There Files.list answers up to 25 items a page (pageSize honoured up to that);
 *       elsewhere two a page, as before.
 *   T14 What one execution learns is kept for the next in the Script Properties (PropertiesService.
 *       getScriptProperties(): getProperty, getProperties, getKeys, setProperty, setProperties(obj),
 *       deleteProperty), the one store the fake offers: no CacheService (it may drop an entry at any time, and a read
 *       that loses its progress never ends), no User or Document properties, nothing written to Drive. The fake keeps
 *       Apps Script's limits: a value over 9 KB (9216 bytes, UTF-8) throws `Argument too large: value`; a store whose
 *       keys and values together pass 500 KB (512000 bytes) throws `You have exceeded the property storage quota.`
 *       It refuses (throws) deleteAllProperties, setProperties(obj, true), and any change to or delete of a property
 *       set before the first run (SOURCE_FOLDER_*, TARGET_FOLDER_*). The big region's progress does not fit one value
 *       (300 folders with Drive-length ids).
 *   T15 A run that has not read a region in full logs, for it, a line holding `TIME_BUDGET` and the region's name
 *       (one line per region), and once it has listed the region folder itself, `<n> ... left to read`
 *       (/(\d+)[^\d\n]{0,40}left to read/), n > 0 the folders whose listing the region still needs; n falls from each
 *       run to the next within a cycle (T16). Such a run logs none of that region's plan (no line naming one of its
 *       folders with a target path or a stay code) and moves none of its folders. Other wording and a run estimate
 *       are free.
 *   T16 A cycle: the runs from one to the first that logs no TIME_BUDGET line (every configured region read in full
 *       and planned; with refileExisting its moves done). A region small enough is read and planned in one run, as
 *       before (the single-run scenarios). A region's plan is logged (T5's lines) in the run that completes its read,
 *       with the outcomes planRefile_ gives on the region as the Drive then is, read in one go: its folders as that
 *       run lists the region folder (one added, trashed or moved since an earlier run of the cycle counts as it now
 *       is), their contents as read during the cycle. A region read in full is not read again within its cycle (a
 *       region after it would wait forever). The run after a cycle's end starts a new one from the Drive as it then
 *       is, planning nothing from what an earlier cycle read; when a cycle ends, what the re-filing keeps in the
 *       Script Properties is under 2 KB (the config unchanged).
 *   T17 refileExisting moves a region's folders only from the plan of the region read in full: each move is one
 *       planRefile_ makes on the Drive as it is at the start of that run, none before the read is complete. The
 *       moves a run leaves are made by the next runs from that read, before the region is read again (each
 *       re-checked as G7 says); a run that leaves some logs a TIME_BUDGET line with `<n> ... left` (as the done
 *       line does). A partner or month folder the mover made since the read (a `<Partner>` in the region folder, a
 *       `<YYYY-MM>` in a partner folder) is used, never a second of its name made. A folder trashed, renamed or
 *       moved since its read is not moved by that read's plan; a renamed one is re-filed by its new name, and one
 *       that appears between runs is re-filed, by a later run of the cycle or by the next cycle.
 *       Bounds, with W = 2 x (folders directly in the big region folder) + (the folders in them) + its listing
 *       pages + 2, the Drive calls of one full read: a preview cycle within ceil(W / 60) + 2 runs; every folder of
 *       the first plan in its target within ceil(W / 60) + ceil(8 x <moves> / 240) + 2 runs; then a quiet cycle
 *       (no move, no TIME_BUDGET) within 2 x (ceil(W / 60) + 2) + 2 more.
 *
 * Every partner, club and file name is fictional (test/fixtures/make_fixture.py's word lists).
 */
const fs = require('fs');
const os = require('os');
const path = require('path');
const vm = require('vm');
const loadGs = require('./load_gs');
const { check, finish } = require('./helpers/js/check');

const DIR = path.join(__dirname, '..', 'drive-sync');
const GS = fs.existsSync(DIR) ? fs.readdirSync(DIR).filter(f => f.endsWith('.gs')).sort().map(f => path.join(DIR, f)) : [];
const FOLDER = 'application/vnd.google-apps.folder';
const MIN = 60 * 1000;
const PREFIX = 'Attendance photos - ';
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const show = (a, b) => 'got ' + JSON.stringify(a) + ' want ' + JSON.stringify(b);
const key = s => String(s).split(/\s+/).filter(Boolean).join(' ').toLowerCase();

const ALPHA = 'Fixture Partner Alpha', BETA = 'Fixture Partner Beta', GAMMA = 'Fixture Partner Gamma';
const DELTA = 'Fixture Partner Delta', ZETA = 'Fixture Partner Zeta';
const CODES = ['holds-folders', 'no-partner', 'ambiguous', 'bad-date', 'duplicate-name', 'partner-name', 'partner-folders',
               'month-folders', 'exists'];

// ---------------------------------------------------------------- loading: no Google service, no REFILE_LIST
console.log('drive-sync/Refile.gs — loads (#237, G1)');
const hasRefile = fs.existsSync(path.join(DIR, 'Refile.gs'));
check('drive-sync/Refile.gs exists', hasRefile, GS.map(f => path.basename(f)).join(', '));
const touched = [];
const trap = name => new Proxy({}, { get(_, k) { touched.push(name + '.' + String(k)); throw new Error(name + ' touched'); } });
const trapped = {};
for (const s of ['DriveApp', 'Drive', 'PropertiesService', 'ScriptApp', 'MailApp', 'GmailApp', 'UrlFetchApp', 'LockService',
                 'CacheService', 'SpreadsheetApp', 'Session', 'Utilities']) trapped[s] = trap(s);
let ctx = null, loadError = '';
try { ctx = loadGs.sandbox(GS, trapped); } catch (e) { loadError = e.message; }
check('drive-sync/*.gs, Refile.gs among them, load with no Google service touched and no REFILE_LIST defined (T6)',
      hasRefile && !!ctx && !loadError && !touched.length, loadError || touched.join(', ') || (hasRefile ? '' : 'no Refile.gs'));
const fn = name => (ctx && typeof ctx[name] === 'function' ? ctx[name] : null);
for (const name of ['planRefile_', 'previewRefile', 'refileExisting']) {
  check(name + ' is a top-level function', !!fn(name), ctx ? typeof ctx[name] : 'not loaded');
}
const planRefile = fn('planRefile_');
const revive = ctx ? vm.runInContext('(function (s) { return JSON.parse(s); })', ctx) : s => JSON.parse(s);

function planOf(regions, list) {
  if (!planRefile) return { plan: null, error: 'planRefile_ is not defined' };
  try {
    return { plan: planRefile(revive(JSON.stringify(regions)), revive(JSON.stringify(list))), error: '' };
  } catch (e) { return { plan: null, error: e && e.message || String(e) }; }
}

const has = (o, k) => !!o && Object.prototype.hasOwnProperty.call(o, k);
const field = (e, k) => (has(e, k) ? e[k] : '<missing>');
function lists(plan) {
  const L = k => (plan && Array.isArray(plan[k]) ? Array.from(plan[k]) : null);
  return { refile: L('refile'), stays: L('stays') };
}
/** A region-root folder's place in the plan: {kind: 'refile', ...} | {kind: 'stay', ...} | {kind: '<n> entries'}. */
function outcome(plan, id) {
  const { refile, stays } = lists(plan);
  if (!refile || !stays) return { kind: 'no refile/stays lists' };
  const r = refile.filter(e => e && e.id === id), s = stays.filter(e => e && e.id === id);
  if (r.length + s.length !== 1) return { kind: (r.length + s.length) + ' entries' };
  if (r.length) {
    const e = r[0];
    return { kind: 'refile', region: e.region, name: e.name, path: Array.isArray(e.path) ? Array.from(e.path) : e.path, to: e.to,
             partnerId: field(e, 'partnerId'), monthId: field(e, 'monthId') };
  }
  return { kind: 'stay', region: s[0].region, name: s[0].name, code: s[0].code, why: s[0].why };
}
function checkCovers(title, regions, plan) {
  const { refile, stays } = lists(plan);
  if (!refile || !stays) return check(title + ': the plan has refile and stays lists', false, JSON.stringify(plan));
  const got = refile.concat(stays).map(e => e && e.id).sort();
  const want = [].concat(...Object.values(regions).map(r => r.folders.map(f => f.id))).sort();
  check(title + ': every region-root folder in exactly one list, and nothing else', same(got, want), show(got, want));
  const bad = stays.filter(e => !e || CODES.indexOf(e.code) < 0 || typeof e.why !== 'string' || !e.why.trim());
  return check(title + ': every stay has a known code and a reason', !bad.length, JSON.stringify(bad.slice(0, 3)));
}

// ---------------------------------------------------------------- building planner inputs
const F = (id, name, folders, files) => ({ id, name, files: files === undefined ? (folders && folders.length ? 0 : 1 + id.length % 3) : files,
                                         folders: folders || [] });
const RID = region => 'tgt-' + region.replace(/\W/g, '').toLowerCase();
/** spec {<Region>: [[id, name, expect, folders?, files?]]}; expect [P, M, partnerId?, monthId?] or {code, names?}. */
function runScenario(title, spec, list) {
  const regions = {}, want = {};
  for (const region of Object.keys(spec)) {
    regions[region] = { id: RID(region), folders: [] };
    for (const [id, name, expect, folders, files] of spec[region]) {
      regions[region].folders.push(F(id, name, folders, files));
      want[id] = { region, name, expect };
    }
  }
  console.log('\n' + title);
  const got = planOf(regions, list);
  if (!check('planRefile_ returns a plan', !got.error && !!got.plan, got.error)) return;
  checkCovers(title.split(' — ')[1] || title, regions, got.plan);
  for (const id of Object.keys(want)) {
    const w = want[id], o = outcome(got.plan, id);
    let ok, label;
    if (Array.isArray(w.expect)) {
      const [P, M, pid, mid] = w.expect;
      const wantPid = pid === undefined ? null : pid, wantMid = mid === undefined ? null : mid;
      ok = o.kind === 'refile' && o.region === w.region && o.name === w.name && same(o.path, [P, M]) && o.to === RID(w.region) &&
        o.partnerId === wantPid && o.monthId === wantMid;
      label = w.region + ' ' + JSON.stringify(w.name) + ' -> ' + P + '/' + M +
        (wantPid || wantMid ? ' (reusing ' + [wantPid, wantMid].filter(Boolean).join(', ') + ')' : '');
    } else {
      ok = o.kind === 'stay' && o.region === w.region && o.name === w.name && o.code === w.expect.code &&
        (w.expect.names || []).every(n => typeof o.why === 'string' && o.why.includes(n));
      label = w.region + ' ' + JSON.stringify(w.name) + ' stays: ' + w.expect.code +
        (w.expect.names ? ' (why names ' + w.expect.names.join(', ') + ')' : '');
    }
    check(label, ok, JSON.stringify(o));
  }
}

const LIST = [
  { region: 'Africa', partner: ALPHA, club: 'Sunrise Club' },
  { region: 'Africa', partner: ALPHA, club: 'Bright Stars' },
  { region: 'Africa', partner: ALPHA, club: 'Harbor Club 1' },
  { region: 'Africa', partner: BETA, club: 'Golden Wings' },
  { region: 'Africa', partner: DELTA, club: 'Golden Wings' },
  { region: 'Africa', partner: BETA, club: 'Silver Flames' },
  { region: 'Africa', partner: BETA, club: 'Rising Stars - Juniors' },
  { region: 'Asia', partner: DELTA, club: 'Silver Flames' },
  { region: 'Asia', partner: GAMMA, club: 'River Roots' },
  { region: 'Asia', partner: BETA, club: 'Ocean Lights' },
  { region: 'Asia', partner: ALPHA, club: 'Morning Stars' },
  { region: 'Latin America', partner: ALPHA, club: 'Morning Stars' },
  { region: 'Latin America', partner: GAMMA, club: 'Golden Wings' },
  { region: '', partner: DELTA, club: 'Valley Roots' },
];

// ---------------------------------------------------------------- the ticket's tests: legacy names
runScenario('planRefile_ — legacy names: club and date, club only, a club whose partner is unknown (the ticket\'s tests)', {
  Africa: [
    ['a01', 'Sunrise Club 10-30-2026', [ALPHA, '2026-10']],
    ['a02', 'Sunrise Club 01-05-2027', [ALPHA, '2027-01']],
    ['a03', 'Bright Stars 12-31-2026', [ALPHA, '2026-12']],
    ['a04', 'Bright Stars 02-29-2028', [ALPHA, '2028-02']],
    ['a05', 'Harbor Club 1 11-30-2026', [ALPHA, '2026-11']],
    ['a06', 'Sunrise Club', [ALPHA, 'undated']],
    ['a07', 'Bright Stars', [ALPHA, 'undated']],
    ['a08', 'Harbor Club 1', [ALPHA, 'undated']],
    ['a09', 'Morning Voices 10-30-2026', { code: 'no-partner' }],
    ['a10', 'Morning Voices', { code: 'no-partner' }],
    ['a11', 'Sunrise Club Juniors 10-30-2026', { code: 'no-partner' }],
    ['a12', 'Sunrise 10-30-2026', { code: 'no-partner' }],
  ],
  Asia: [
    ['s01', 'River Roots 10-16-2026', [GAMMA, '2026-10']],
    ['s02', 'River Roots 09-03-2026', [GAMMA, '2026-09']],
    ['s03', 'Ocean Lights', [BETA, 'undated']],
    ['s04', 'Quiet Harbor', { code: 'no-partner' }],
  ],
}, LIST);

runScenario('planRefile_ — matching: case and spaces, `<club> - <partner>`, own region first, ambiguous (G3, T1)', {
  Africa: [
    ['b01', '  sunrise   CLUB  09-14-2026 ', [ALPHA, '2026-09']],
    ['b02', 'BRIGHT   stars', [ALPHA, 'undated']],
    ['b03', 'Golden Wings 10-30-2026', { code: 'ambiguous', names: [BETA, DELTA] }],
    ['b04', 'Golden Wings', { code: 'ambiguous', names: [BETA, DELTA] }],
    ['b05', 'Golden Wings - Fixture Partner Beta 10-30-2026', [BETA, '2026-10']],
    ['b06', 'golden wings  -  fixture partner DELTA', [DELTA, 'undated']],
    ['b07', 'Golden Wings - Fixture Partner Gamma 10-30-2026', [GAMMA, '2026-10']],   // no Africa row has it: every row
    ['b08', 'Silver Flames 11-20-2026', [BETA, '2026-11']],                           // Africa's row, not Asia's
    ['b09', 'Morning Stars 10-30-2026', [ALPHA, '2026-10']],                          // two rows elsewhere, one partner
    ['b10', 'Rising Stars - Juniors 10-30-2026', [BETA, '2026-10']],                  // never split on " - "
  ],
  Asia: [
    ['b11', 'Silver Flames', [DELTA, 'undated']],
    ['b12', 'Valley Roots 10-30-2026', [DELTA, '2026-10']],                           // a blank-region row: every row
    ['b13', 'Golden Wings 10-30-2026', { code: 'ambiguous', names: [BETA, DELTA, GAMMA] }],
    ['b14', 'Sunrise Club 10-30-2026', [ALPHA, '2026-10']],
  ],
  'Latin America': [
    ['b15', 'Golden Wings 11-02-2026', [GAMMA, '2026-11']],                           // its own region decides
    ['b16', 'Silver Flames 10-30-2026', { code: 'ambiguous', names: [BETA, DELTA] }], // none here, two elsewhere
    ['b17', 'Morning Stars', [ALPHA, 'undated']],
  ],
}, LIST);

runScenario('planRefile_ — layout names: a blank partner is looked up, a named partner kept with no lookup (G4)', {
  Africa: [
    ['c01', ' | Sunrise Club | 11-13-2026 | 2', [ALPHA, '2026-11']],
    ['c02', ' | Golden Wings - Fixture Partner Delta | 11-13-2026', [DELTA, '2026-11']],
    ['c03', '   | bright stars | 03-02-2027 |  ', [ALPHA, '2027-03']],
    ['c04', ' | Morning Voices | 10-30-2026 | 1', { code: 'no-partner' }],
    ['c05', ' | Golden Wings | 10-30-2026 | 3', { code: 'ambiguous', names: [BETA, DELTA] }],
    ['c06', 'Fixture Partner Zeta | Evening Lights | 10-30-2026 | 4', [ZETA, '2026-10']],
    ['c07', 'Fixture Partner Delta | Sunrise Club | 12-01-2026 | 7', [DELTA, '2026-12']],
    ['c08', 'Fixture Partner Alpha | Bright Stars | 10-30-2026', [ALPHA, '2026-10']],
  ],
}, LIST);

runScenario('planRefile_ — the integration\'s spaces-only names of 2026-11-23, `<Partner> <Club> <MM-DD-YYYY> [<Week>]` (T11)', {
  Africa: [
    ['h01', 'Fixture Partner Alpha Sunrise Club 11-23-2026 4', [ALPHA, '2026-11']],
    ['h02', 'Fixture Partner Alpha Bright Stars 11-23-2026', [ALPHA, '2026-11']],             // a special event: no week
    ['h03', 'Fixture Partner Alpha Sunrise Club 11-23-2026 ', [ALPHA, '2026-11']],            // the blank week's space
    ['h04', '  fixture partner ALPHA   harbor  club 1  12-01-2026   2 ', [ALPHA, '2026-12']], // case and spaces; a number in the club
    ['h05', 'Fixture Partner Beta Golden Wings - Fixture Partner Beta 11-23-2026 2', [BETA, '2026-11']],
    ['h06', 'Fixture Partner Delta Golden Wings 11-24-2026 1', [DELTA, '2026-11']],          // the club alone is ambiguous (b03)
    ['h07', 'Fixture Partner Beta Golden Wings 01-04-2027 12', [BETA, '2027-01']],
    ['h08', 'Fixture Partner Gamma Golden Wings 11-23-2026 3', [GAMMA, '2026-11']],          // no Africa row has it: every row
    ['h09', 'Fixture Partner Beta Sunrise Club 11-23-2026 4', { code: 'no-partner' }],       // Alpha's club: not on the list
    ['h10', 'Fixture Partner Zeta Sunrise Club 11-23-2026', { code: 'no-partner' }],          // a partner the list does not have
    ['h11', 'Fixture Partner Alpha Morning Voices 11-23-2026 4', { code: 'no-partner' }],
    ['h12', 'Fixture Partner Alpha Sunrise Club 02-30-2026 4', { code: 'bad-date' }],
    ['h13', 'Fixture Partner Alpha Bright Stars 13-01-2026', { code: 'bad-date' }],
    ['h14', 'Sunrise Club 10-30-2026 (1)', [ALPHA, '2026-10']],                               // text after a `<club> <date>`
    ['h15', 'Sunrise Club 11-23-2026 4', [ALPHA, '2026-11']],                                 // a blank partner: the club alone
  ],
  Asia: [
    ['h20', 'Fixture Partner Delta Silver Flames 11-23-2026 2', [DELTA, '2026-11']],
    ['h21', 'Fixture Partner Beta Silver Flames 11-23-2026 2', [BETA, '2026-11']],           // Asia's row is Delta's: every row
  ],
  'Latin America': [
    ['h30', 'Fixture Partner Alpha Morning Stars 11-30-2026', [ALPHA, '2026-11']],
    ['h31', 'Fixture Partner Gamma Morning Stars 11-30-2026 4', { code: 'no-partner' }],
  ],
}, LIST);

runScenario('planRefile_ — a date-shaped last token that is not a real date stays (G4: bad-date)', {
  Africa: [
    ['d01', 'Sunrise Club 02-30-2026', { code: 'bad-date' }],
    ['d02', 'Sunrise Club 13-40-2026', { code: 'bad-date' }],
    ['d03', 'Bright Stars 02-29-2027', { code: 'bad-date' }],
    ['d04', 'Bright Stars 04-31-2027', { code: 'bad-date' }],
    ['d05', 'Sunrise Club 00-10-2026', { code: 'bad-date' }],
    ['d06', 'Sunrise Club 10-00-2026', { code: 'bad-date' }],
    ['d07', 'Sunrise Club 10-31-2026', [ALPHA, '2026-10']],
    ['d08', 'Bright Stars 02-28-2027', [ALPHA, '2027-02']],
  ],
}, LIST);

// ---------------------------------------------------------------- G5 and G6: what holds a folder where it is
runScenario('planRefile_ — holds-folders; a partner and month folder reused; exists (G5, G6, T3, T4)', {
  Africa: [
    ['pb', BETA, { code: 'holds-folders' },
     [F('pb-09', '2026-09', [F('pb-09-x', 'Golden Wings - Fixture Partner Beta 09-25-2026')]), F('pb-un', 'undated')]],
    ['old', 'Old uploads', { code: 'holds-folders' }, [F('old-m', 'misc')]],
    ['sx', 'Sunrise Club 10-30-2026', { code: 'holds-folders' }, [F('sx-a', 'more photos')]],
    ['g1', 'Golden Wings - Fixture Partner Beta 10-30-2026', [BETA, '2026-10', 'pb', null]],
    ['g2', 'Golden Wings - Fixture Partner Beta 09-02-2026', [BETA, '2026-09', 'pb', 'pb-09']],
    ['g3', 'Golden Wings - Fixture Partner Beta', [BETA, 'undated', 'pb', 'pb-un']],
    ['g4', 'Golden Wings - Fixture Partner Beta 09-25-2026', { code: 'exists' }],
    ['g5', 'golden wings - fixture partner beta 09-25-2026', [BETA, '2026-09', 'pb', 'pb-09']],
    ['g6', 'Sunrise Club 11-06-2026', [ALPHA, '2026-11']],
  ],
  Asia: [
    ['apa', ALPHA, { code: 'holds-folders' }, [F('apa-11', '2026-11')]],
    ['ag6', 'Sunrise Club 11-06-2026', [ALPHA, '2026-11', 'apa', 'apa-11']],   // Asia's own Alpha folder; Africa's is made
  ],
}, LIST);

runScenario('planRefile_ — two or more photo folders of one exact name all stay (G5: duplicate-name, T3)', {
  Africa: [
    ['e1', 'Bright Stars 10-02-2026', { code: 'duplicate-name' }],
    ['e2', 'Bright Stars 10-02-2026', { code: 'duplicate-name' }],
    ['e3', 'bright stars 10-02-2026', [ALPHA, '2026-10']],
    ['e4', 'Bright Stars', [ALPHA, 'undated']],
    ['e5', 'Sunrise Club', { code: 'duplicate-name' }],
    ['e6', 'Sunrise Club', { code: 'duplicate-name' }],
    ['e7', 'Sunrise Club', { code: 'duplicate-name' }],
  ],
  Asia: [
    ['e8', 'Bright Stars 10-02-2026', [ALPHA, '2026-10']],   // one in this region folder
  ],
}, LIST);

runScenario('planRefile_ — a photo folder named like a partner the region targets holds it all (G6: partner-name, T2)', {
  Asia: [
    ['pn', BETA, { code: 'partner-name' }, [], 3],
    ['o1', 'Ocean Lights 10-30-2026', { code: 'partner-name' }],
    ['o2', 'Ocean Lights', { code: 'partner-name' }],
    ['r1', 'River Roots 10-30-2026', [GAMMA, '2026-10']],
    ['pd', DELTA, { code: 'no-partner' }, [], 2],   // no Asia entry targets Delta: a name like any other
  ],
  Africa: [
    ['ag', 'Golden Wings - Fixture Partner Beta 10-30-2026', [BETA, '2026-10']],   // the hold is Asia's only
  ],
}, LIST);

runScenario('planRefile_ — two partner folders of one name (G6: partner-folders, T3)', {
  Africa: [
    ['pa1', ALPHA, { code: 'holds-folders' }, [F('pa1-10', '2026-10')]],
    ['pa2', ALPHA, { code: 'holds-folders' }, [F('pa2-11', '2026-11')]],
    ['p1', 'Sunrise Club 10-30-2026', { code: 'partner-folders' }],
    ['p2', 'Bright Stars', { code: 'partner-folders' }],
    ['p3', 'Fixture Partner Alpha | Harbor Club 1 | 10-30-2026 | 2', { code: 'partner-folders' }],
    ['p4', 'Golden Wings - Fixture Partner Beta 10-30-2026', [BETA, '2026-10']],
  ],
  'Latin America': [
    ['lpa', 'fixture partner gamma', { code: 'holds-folders' }, [F('lpa-11', '2026-11')]],
    ['l1', 'Golden Wings 11-02-2026', [GAMMA, '2026-11']],   // not that folder: another name
  ],
}, LIST);

runScenario('planRefile_ — two month folders of one name; a month reused, one made; exists (G6: month-folders, exists)', {
  Africa: [
    ['pa', ALPHA, { code: 'holds-folders' },
     [F('m10a', '2026-10'), F('m10b', '2026-10'), F('mun', 'undated'), F('m11', '2026-11', [F('m11-x', 'Sunrise Club 11-06-2026')])]],
    ['m1', 'Sunrise Club 10-30-2026', { code: 'month-folders' }],
    ['m2', 'Bright Stars 10-09-2026', { code: 'month-folders' }],
    ['m3', 'Sunrise Club', [ALPHA, 'undated', 'pa', 'mun']],
    ['m4', 'Sunrise Club 12-04-2026', [ALPHA, '2026-12', 'pa', null]],
    ['m5', 'Sunrise Club 11-13-2026', [ALPHA, '2026-11', 'pa', 'm11']],
    ['m6', 'Sunrise Club 11-06-2026', { code: 'exists' }],
  ],
}, LIST);

// ---------------------------------------------------------------- a generated table against an independent oracle
const DIM = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
const isLeap = y => (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
const daysIn = (y, m) => (m === 2 && isLeap(y) ? 29 : DIM[m - 1]);
const p2 = x => String(x).padStart(2, '0');
const mdy = (y, m, d) => p2(m) + '-' + p2(d) + '-' + y;
function prng(seed) {   // mulberry32
  return function () {
    seed |= 0; seed = seed + 0x6D2B79F5 | 0;
    let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

console.log('\nplanRefile_ — generated regions against an independent oracle (G3-G6)');
{
  const PG = [ALPHA, BETA, 'Fixture Partner Gamma - North', DELTA];
  const REG = ['Africa', 'Asia', 'Latin America'];
  const CW = ['Bright', 'Golden', 'River', 'Morning', 'Silver'], CN = ['Stars', 'Wings', 'Roots', 'Lights'];
  const UNKNOWN = ['Hidden Valley', 'Quiet Harbor', 'Paper Lanterns', 'Ocean Voices Club'];
  const MONTHS = [[2026, 9], [2026, 10], [2026, 11], [2026, 12], [2027, 1]];
  const BAD = ['02-30-2026', '13-40-2026', '04-31-2027', '02-29-2027', '00-10-2026', '10-00-2026', '10-32-2026', '11-31-2026'];
  const tally = {};
  const bump = k => { tally[k] = (tally[k] || 0) + 1; };
  const failures = [];
  for (let seed = 1; seed <= 40; seed++) {
    const r = prng(2370 + seed);
    const pick = a => a[Math.floor(r() * a.length)];
    let n = 0;
    const id = p => p + seed + '-' + (++n);
    const list = [], seenRow = new Set();
    while (list.length < 12) {
      const row = { region: pick(REG.concat([''])), partner: pick(PG), club: pick(CW) + ' ' + pick(CN) };
      const k = row.region + '|' + key(row.partner) + '|' + key(row.club);
      if (!seenRow.has(k)) { seenRow.add(k); list.push(row); }
    }
    const mangle = s => {
      const roll = r();
      let t = roll < 0.25 ? s.toLowerCase() : roll < 0.4 ? s.toUpperCase() : s;
      if (r() < 0.3) t = t.replace(' ', '  ');
      return t;
    };
    const lookup = (region, clubText) => {   // G3 and T11, written from the rulings
      const k = key(clubText);
      const match = row => [row.club, row.club + ' - ' + row.partner].some(n => key(n) === k || key(row.partner + ' ' + n) === k);
      let hits = list.filter(x => x.region === region && match(x));
      if (!hits.length) hits = list.filter(match);
      const partners = [...new Set(hits.map(x => x.partner))];
      return partners.length === 1 ? { partner: partners[0] } : { code: partners.length ? 'ambiguous' : 'no-partner' };
    };
    const regions = {}, want = {};
    for (const region of REG) {
      const roots = [];
      // partner folders already there (and a stray folder holding folders)
      for (const P of PG.concat([ZETA])) {
        const roll = r();
        if (roll < 0.5) continue;
        for (let c = 0; c < (roll < 0.88 ? 1 : 2); c++) {
          const months = [];
          for (let i = 0; i < 1 + Math.floor(r() * 3); i++) {
            const [y, m] = pick(MONTHS);
            months.push(F(id('m'), r() < 0.2 ? 'undated' : y + '-' + p2(m), r() < 0.3 ? [F(id('x'), 'Some Club ' + mdy(y, m, 1))] : []));
          }
          if (r() < 0.12) months.push(F(id('m'), months[0].name));
          roots.push(F(id('p'), P, months));
        }
      }
      if (r() < 0.25) roots.push(F(id('j'), 'Archive ' + seed, [F(id('j'), 'misc')]));
      // photo folders, each with its name's meaning (never parsed back)
      const photos = [], used = new Set();
      while (photos.length < 10) {
        const [y, m] = pick(MONTHS);
        const date = mdy(y, m, 1 + Math.floor(r() * daysIn(y, m))), month = y + '-' + p2(m);
        const known = () => pick(list).club, any = () => (r() < 0.8 ? known() : pick(UNKNOWN));
        const kind = r();
        let name, meaning;
        if (kind < 0.25) { const c = mangle(any()); name = c + ' ' + date; meaning = { club: c, month }; }
        else if (kind < 0.4) { const c = mangle(any()); name = c; meaning = { club: c, month: 'undated' }; }
        else if (kind < 0.55) {
          const row = pick(list);
          const c = mangle(row.club + ' - ' + (r() < 0.8 ? row.partner : pick(PG)));
          const dated = r() < 0.6;
          name = dated ? c + ' ' + date : c;
          meaning = { club: c, month: dated ? month : 'undated' };
        } else if (kind < 0.68) {
          const c = mangle(any());
          const segs = [pick(['', ' ', '   ']), c, date];
          if (r() < 0.5) segs.push(String(1 + Math.floor(r() * 30)));
          name = segs.join(' | ');
          meaning = { club: c, month };
        } else if (kind < 0.82) {
          const P = pick(PG.concat([ZETA]));
          name = [P, mangle(any()), date, String(1 + Math.floor(r() * 30))].join(' | ');
          meaning = { path: [P, month] };
        } else { name = mangle(known()) + ' ' + pick(BAD); meaning = { code: 'bad-date' }; }
        if (used.has(name)) continue;
        used.add(name);
        photos.push({ folder: F(id('f'), name), meaning });
      }
      // T11: the integration's spaces-only names, `<Partner> <Club> <MM-DD-YYYY> [<Week>]`, after the others
      while (photos.length < 13) {
        const [y, m] = pick(MONTHS);
        const date = mdy(y, m, 1 + Math.floor(r() * daysIn(y, m))), month = y + '-' + p2(m);
        const row = pick(list);
        const P = r() < 0.6 ? row.partner : pick(PG.concat([ZETA]));
        const c = r() < 0.85 ? row.club + (r() < 0.2 ? ' - ' + row.partner : '') : pick(UNKNOWN);
        const text = mangle(P + ' ' + c), bad = r() < 0.15, wk = r();
        const name = text + ' ' + (bad ? pick(BAD) : date) + (wk < 0.6 ? ' ' + (1 + Math.floor(r() * 30)) : wk < 0.75 ? ' ' : '');
        if (used.has(name)) continue;
        used.add(name);
        photos.push({ folder: F(id('f'), name), meaning: bad ? { code: 'bad-date' } : { club: text, month }, spaces: true });
      }
      // the oracle: G4's meaning, G3's lookup, G6's levels
      const partnerFolders = P => roots.filter(x => x.folders.length && x.name === P);
      const decide = (ph) => {
        let target = ph.meaning.path || null;
        if (ph.meaning.code) return { code: ph.meaning.code, tag: 'bad-date' };
        if (!target) {
          const found = lookup(region, ph.meaning.club);
          if (found.code) return { code: found.code, tag: found.code };
          target = [found.partner, ph.meaning.month];
        }
        const pfs = partnerFolders(target[0]);
        if (pfs.length > 1) return { code: 'partner-folders', tag: 'partner-folders' };
        if (!pfs.length) return { path: target, partnerId: null, monthId: null, tag: ph.meaning.path ? 'layout, made' : 'made' };
        const ms = pfs[0].folders.filter(x => x.name === target[1]);
        if (ms.length > 1) return { code: 'month-folders', tag: 'month-folders' };
        if (!ms.length) return { path: target, partnerId: pfs[0].id, monthId: null, tag: 'partner reused' };
        if (ms[0].folders.some(x => x.name === ph.folder.name)) return { code: 'exists', tag: 'exists' };
        return { path: target, partnerId: pfs[0].id, monthId: ms[0].id, tag: 'partner and month reused', month: ms[0] };
      };
      for (const ph of photos) ph.out = decide(ph);
      // a same-name folder already in the month folder: exists
      for (const ph of photos) {
        if (ph.out.month && r() < 0.25) {
          ph.out.month.folders.push(F(id('e'), ph.folder.name));
          ph.out = { code: 'exists', tag: 'exists' };
        }
      }
      // a second photo folder of a name: both stay
      const clean = photos.filter(ph => ph.out.path);
      if (clean.length && r() < 0.4) {
        const dup = pick(clean);
        photos.push({ folder: F(id('f'), dup.folder.name), out: null });
        dup.out = { code: 'duplicate-name', tag: 'duplicate-name' };
        photos[photos.length - 1].out = { code: 'duplicate-name', tag: 'duplicate-name' };
      }
      for (const x of roots) want[x.id] = { region, kind: 'stay', code: 'holds-folders', tag: 'holds-folders' };
      for (const ph of photos) {
        roots.push(ph.folder);
        want[ph.folder.id] = ph.out.path ?
          { region, kind: 'refile', path: ph.out.path, partnerId: ph.out.partnerId, monthId: ph.out.monthId, tag: ph.out.tag } :
          { region, kind: 'stay', code: ph.out.code, tag: ph.out.tag };
        if (ph.spaces) bump('spaces ' + (ph.out.path ? 'refiled' : ph.out.code));
      }
      // the order Drive lists them in is no order: shuffle
      for (let i = roots.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [roots[i], roots[j]] = [roots[j], roots[i]]; }
      regions[region] = { id: RID(region), folders: roots };
    }
    for (const w of Object.values(want)) bump(w.tag);
    const got = planOf(regions, list);
    if (got.error || !got.plan) { failures.push('seed ' + seed + ': ' + (got.error || 'no plan')); continue; }
    for (const fid of Object.keys(want)) {
      const w = want[fid], o = outcome(got.plan, fid);
      const ok = w.kind === 'refile' ?
        o.kind === 'refile' && o.region === w.region && same(o.path, w.path) && o.to === RID(w.region) &&
          o.partnerId === w.partnerId && o.monthId === w.monthId :
        o.kind === 'stay' && o.region === w.region && o.code === w.code;
      if (!ok) failures.push('seed ' + seed + ' ' + fid + ': ' + JSON.stringify(o) + ' want ' + JSON.stringify(w));
    }
  }
  const need = ['made', 'layout, made', 'partner reused', 'partner and month reused', 'ambiguous', 'no-partner', 'bad-date',
                'holds-folders', 'duplicate-name', 'partner-folders', 'month-folders', 'exists',
                'spaces refiled', 'spaces no-partner', 'spaces bad-date'];
  check('40 generated runs, every outcome among them: each region-root folder re-filed or held as the oracle says',
        !failures.length && need.every(k => tally[k] > 3),
        failures.length + ' wrong; first: ' + failures.slice(0, 3).join(' ;; ') + '; outcomes ' + JSON.stringify(tally));
}

console.log('\nplanRefile_ — pure: no Google service, inputs unchanged');
{
  const regions = { Africa: { id: 'tgt-africa', folders: [
    F('pa', ALPHA, [F('pa-10', '2026-10', [F('pa-10-x', 'Bright Stars 10-02-2026')])]),
    F('f1', 'Sunrise Club 10-30-2026'), F('f2', 'Bright Stars'), F('f3', 'Golden Wings 10-30-2026'), F('f4', 'Morning Voices'),
    F('f5', 'Bright Stars 10-02-2026'), F('f6', 'Sunrise Club 02-30-2026')] } };
  const rj = JSON.stringify(regions), lj = JSON.stringify(LIST);
  const ri = revive(rj), li = revive(lj);
  touched.length = 0;
  let err = '', p = null;
  try { p = planRefile(ri, li); } catch (e) { err = e && e.message || String(e); }
  check('planning touches no Google service and leaves its inputs as they were',
        !err && !!p && !touched.length && JSON.stringify(ri) === rj && JSON.stringify(li) === lj,
        err || touched.join(', ') || 'inputs changed: ' + (JSON.stringify(ri) !== rj) + ', ' + (JSON.stringify(li) !== lj));
  let p2nd = null;
  try { p2nd = planRefile(revive(rj), revive(lj)); } catch (e) { err = e && e.message || String(e); }
  check('the same inputs give the same plan', !err && !!p && JSON.stringify(p) === JSON.stringify(p2nd), err);
}

// ---------------------------------------------------------------- the entry points on a fake Drive
/**
 * A fake Shared Drive (and the mover's My Drive source folders, which the re-filing never needs), adapted from
 * test/drive_sync_layout_test.js. DriveApp: getFolderById / getFileById; a Folder lists its folders and files
 * (Drive's trash included, isTrashed() true, as DriveApp does), getParents, getName, getId; createFolder, moveTo,
 * setTrashed and setName refuse. The advanced service (v3): Files.list answers `q` (`'<id>' in parents`, trashed,
 * mimeType, name; and / or / not, parentheses), two items a page, Shared Drive items only with supportsAllDrives
 * and includeItemsFromAllDrives; Files.get (parents, trashed, mimeType, driveId, name); Files.create makes a folder
 * under its one parent (supportsAllDrives); Files.update moves an item (addParents a live folder, removeParents
 * its current parent), a folder within the Shared Drive too, never a My Drive folder into it, and refuses any
 * resource key but `trashed`. Every DriveApp and Drive call is recorded (G9); `hooks` change an item at the
 * first access to it by id (T8); a `silent` id's move is answered but not done (T9). Unknown members throw.
 * #262: Files.list refuses a query naming other than one parent with the live error, and every query is recorded
 * with the run it came in (T12); list and get answer only the fields asked; the Script Properties keep Apps Script's
 * limits and the config (T14); with `clocked` the sandbox's Date is the fake clock and a page holds up to `pageCap`
 * items (T13).
 */
const MEMBERSHIP = 'API call to drive.files.list failed with error: The attempted action requires shared drive membership.';
const READ_CALLS = 120;   // T13: the Drive calls one run's read budget holds on the fake clock
const RUN_BUDGET = ctx ? vm.runInContext('typeof RUN_BUDGET_MS === "number" ? RUN_BUDGET_MS : 0', ctx) : 0;
const STEP = (RUN_BUDGET || 4.5 * MIN) / 2 / READ_CALLS;
const BIG_PAGE = 25;
const VALUE_MAX = 9 * 1024, STORE_MAX = 500 * 1024;
const DEFAULT_FIELDS = ['kind', 'id', 'name', 'mimeType'];
/** The fields a Files.list (`nested`: `files(...)`) or Files.get asks for: a Set, or null for every field. */
function fieldsAsked(fields, nested) {
  if (fields === undefined || fields === null || fields === '') return new Set(DEFAULT_FIELDS);
  const f = String(fields), split = t => t.split(',').map(s => s.trim()).filter(Boolean);
  if (!nested) return f.includes('*') ? null : new Set(split(f));
  const m = /files\(([^)]*)\)/.exec(f);
  if (m) return m[1].includes('*') ? null : new Set(split(m[1]));
  const slash = split(f).filter(s => s.startsWith('files/')).map(s => s.slice(6));
  if (slash.length) return slash.includes('*') ? null : new Set(slash);
  return /\bfiles\b|\*/.test(f) ? null : new Set();
}
const ROOT = 'drive-root-237';
const REGION_IDS = { Africa: 'tgt-africa', Asia: 'tgt-asia' };
const SOURCE_IDS = { Africa: 'src-africa', Asia: 'src-asia' };

/** The predicate of a Files.list `q`; its `parents` are the ids its `'<id>' in parents` terms name (T12). */
function parseDriveQuery(q) {
  const src = String(q), toks = [], parents = [];
  const re = /\s*(?:'((?:[^'\\]|\\.)*)'|(!=|=|\(|\))|([A-Za-z]+))/y;
  let i = 0;
  while (i < src.length && src.slice(i).trim()) {
    re.lastIndex = i;
    const m = re.exec(src);
    if (!m) throw new Error('fake Files.list: cannot read the query at "' + src.slice(i, i + 20) + '"');
    i = re.lastIndex;
    toks.push(m[1] !== undefined ? { str: m[1].replace(/\\(.)/g, '$1') } : m[2] ? { op: m[2] } : { word: m[3] });
  }
  let p = 0;
  const fail = what => { throw new Error('fake Files.list: unsupported query (' + what + '): ' + src); };
  const isWord = w => !!toks[p] && toks[p].word !== undefined && toks[p].word.toLowerCase() === w;
  const operator = () => { const t = toks[p++]; if (!t || (t.op !== '=' && t.op !== '!=')) fail('operator'); return t.op; };
  const clause = () => {
    const t = toks[p++];
    if (!t) fail('a term expected');
    if (t.str !== undefined) {
      if (!isWord('in')) fail('`in` expected');
      p++;
      if (!toks[p] || toks[p].word !== 'parents') fail('`parents` expected');
      p++;
      parents.push(t.str);
      return m => m.parent === t.str;
    }
    if (t.word === 'trashed') {
      const op = operator(), v = toks[p++];
      if (!v || (v.word !== 'true' && v.word !== 'false')) fail('trashed value');
      const want = v.word === 'true';
      return op === '=' ? m => m.trashed === want : m => m.trashed !== want;
    }
    if (t.word === 'mimeType' || t.word === 'name') {
      const op = operator(), v = toks[p++];
      if (!v || v.str === undefined) fail('a quoted value');
      const get = m => (t.word === 'name' ? m.name : (m.isFolder ? FOLDER : 'image/jpeg'));
      return op === '=' ? m => get(m) === v.str : m => get(m) !== v.str;
    }
    return fail('the term ' + JSON.stringify(t));
  };
  const unary = () => {
    if (isWord('not')) { p++; const u = unary(); return m => !u(m); }
    if (toks[p] && toks[p].op === '(') {
      p++;
      const e = orExpr();
      if (!toks[p] || toks[p].op !== ')') fail('`)`');
      p++;
      return e;
    }
    return clause();
  };
  const andExpr = () => { let a = unary(); while (isWord('and')) { p++; const l = a, r = unary(); a = m => l(m) && r(m); } return a; };
  function orExpr() { let a = andExpr(); while (isWord('or')) { p++; const l = a, r = andExpr(); a = m => l(m) || r(m); } return a; }
  const test = orExpr();
  if (p !== toks.length) fail('trailing terms');
  test.parents = parents;
  return test;
}

function fakeDrive(opts) {
  opts = opts || {};
  const pageCap = opts.pageCap || 2;
  const items = new Map(), logs = [], creates = [], updates = [], banned = [], calls = [];
  const queries = [], refused = [], nameAsks = [], state = { run: 0 };
  const hooks = new Map(), silent = new Set();
  const clock = { now: Date.UTC(2026, 10, 24, 9, 0, 0), step: opts.clocked ? STEP : 0 };
  const tick = () => { clock.now += clock.step; };
  const t0 = Date.now();
  let n = 0;
  const add = (parent, name, isFolder, o) => {
    o = o || {};
    const id = o.id || (isFolder ? 'folder-' : 'file-') + (++n);
    const p = parent ? items.get(parent) : null;
    items.set(id, { id, name, isFolder, parent, size: o.size || 0, trashed: !!o.trashed, explicitlyTrashed: !!o.trashed,
                    updatedAt: t0 - 600 * MIN, createdAt: t0 - 600 * MIN,
                    shared: o.shared !== undefined ? o.shared : !!(p && p.shared) });
    return id;
  };
  add(null, 'Photos Shared Drive', true, { id: ROOT, shared: true });
  for (const reg of Object.keys(REGION_IDS)) {
    add(ROOT, reg, true, { id: REGION_IDS[reg] });
    add(null, PREFIX + reg, true, { id: SOURCE_IDS[reg], shared: false });
  }
  const kids = id => [...items.values()].filter(m => m.parent === id);
  const INTRO = new Set(['toString', 'valueOf', 'toJSON', 'constructor', 'then', 'inspect']);
  const guard = (type, obj) => new Proxy(obj, {
    get(t, k) {
      if (typeof k !== 'string' || INTRO.has(k) || k in t) return t[k];
      return () => { banned.push(type + '.' + k); throw new Error('fake ' + type + ' has no ' + k); };
    },
  });
  const iter = list => { let i = 0; return guard('Iterator', { hasNext: () => i < list.length, next: () => list[i++] }); };
  const refuse = what => { banned.push(what); throw new Error('fake: ' + what + ' is not how the re-filing writes (G7)'); };
  const byId = id => {
    if (!hooks.has(id)) return;
    const h = hooks.get(id);
    hooks.delete(id);
    h();
  };
  const get = id => {
    if (!items.has(id)) throw new Error('File not found: ' + id + ' (fake)');
    return items.get(id);
  };
  const fileApi = id => {
    const m = () => items.get(id);
    return guard('File', {
      getId: () => id, getName: () => { nameAsks.push('File.getName'); return m().name; }, getSize: () => m().size,
      getMimeType: () => 'image/jpeg',
      getLastUpdated: () => new Date(m().updatedAt), getDateCreated: () => new Date(m().createdAt), isTrashed: () => m().trashed,
      getParents: () => iter(m().parent ? [folderApi(m().parent)] : []),
      moveTo: () => refuse('File.moveTo'), setTrashed: () => refuse('File.setTrashed'), setName: () => refuse('File.setName'),
    });
  };
  function folderApi(id) {
    const m = () => items.get(id);
    return guard('Folder', {
      getId: () => id, getName: () => m().name, isTrashed: () => m().trashed,
      getLastUpdated: () => new Date(m().updatedAt), getDateCreated: () => new Date(m().createdAt),
      getFolders: () => { tick(); return iter(kids(id).filter(k => k.isFolder).map(k => folderApi(k.id))); },
      getFoldersByName: nm => { tick(); return iter(kids(id).filter(k => k.isFolder && k.name === nm).map(k => folderApi(k.id))); },
      getFiles: () => { tick(); return iter(kids(id).filter(k => !k.isFolder).map(k => fileApi(k.id))); },
      getFilesByName: nm => { tick(); return iter(kids(id).filter(k => !k.isFolder && k.name === nm).map(k => fileApi(k.id))); },
      getParents: () => iter(m().parent ? [folderApi(m().parent)] : []),
      createFolder: nm => refuse('Folder.createFolder ' + nm), moveTo: () => refuse('Folder.moveTo'),
      setTrashed: () => refuse('Folder.setTrashed'), setName: () => refuse('Folder.setName'),
    });
  }
  const pick = (r, want) => {
    if (!want) return r;
    const o = {};
    for (const k of want) if (has(r, k)) o[k] = r[k];
    return o;
  };
  const rep = m => {
    const r = { kind: 'drive#file', id: m.id, name: m.name, mimeType: m.isFolder ? FOLDER : 'image/jpeg',
                parents: m.parent ? [m.parent] : [], trashed: m.trashed, explicitlyTrashed: m.explicitlyTrashed,
                modifiedTime: new Date(m.updatedAt).toISOString(), createdTime: new Date(m.createdAt).toISOString() };
    if (!m.isFolder) r.size = String(m.size);
    if (m.shared) r.driveId = ROOT;
    return r;
  };
  const Files = guard('Drive.Files', {
    list(args) {
      calls.push('Drive.Files.list');
      tick();
      if (!args || typeof args.q !== 'string') throw new Error('fake Files.list: q required');
      const test = parseDriveQuery(args.q);
      queries.push({ q: args.q, fields: args.fields, parents: test.parents.slice(), run: state.run, refused: test.parents.length !== 1 });
      if (test.parents.length !== 1) {   // T12: the live refusal; a whole-drive listing too (#183)
        refused.push(args.q);
        throw new Error(MEMBERSHIP);
      }
      const all = args.supportsAllDrives === true && args.includeItemsFromAllDrives === true;
      let pool = [...items.values()].filter(m => m.id !== ROOT && (all || !m.shared));
      if (args.corpora === 'drive') pool = pool.filter(m => m.shared && args.driveId === ROOT);
      const hits = pool.filter(test);
      const start = args.pageToken ? Number(args.pageToken) : 0;
      const size = Math.max(1, Math.min(pageCap, Number(args.pageSize) || 100));
      const page = hits.slice(start, start + size), want = fieldsAsked(args.fields, true);
      if ((want === null || want.has('name')) && page.some(m => !m.isFolder)) nameAsks.push(args.q);
      const out = { files: page.map(m => pick(rep(m), want)) };
      if (start + size < hits.length) out.nextPageToken = String(start + size);
      return out;
    },
    get(id, args) {
      calls.push('Drive.Files.get');
      tick();
      byId(id);
      const m = get(id);
      if (m.shared && !(args && args.supportsAllDrives === true)) throw new Error('File not found: ' + id + ' (fake: supportsAllDrives)');
      return pick(rep(m), fieldsAsked(args && args.fields, false));
    },
    create(resource, media, args) {
      calls.push('Drive.Files.create');
      tick();
      creates.push({ resource: JSON.parse(JSON.stringify(resource || {})), args: Object.assign({}, args || {}) });
      const parents = resource && resource.parents;
      if (!resource || resource.mimeType !== FOLDER || !Array.isArray(parents) || parents.length !== 1) {
        throw new Error('fake Files.create: a folder with one parent expected');
      }
      const parent = get(parents[0]);
      if (!parent.isFolder || parent.trashed) throw new Error('fake Files.create: parent not a live folder');
      if (parent.shared && !(args && args.supportsAllDrives === true)) throw new Error('File not found: ' + parent.id + ' (fake: supportsAllDrives)');
      return rep(items.get(add(parent.id, resource.name, true)));
    },
    update(resource, fileId, media, args) {
      calls.push('Drive.Files.update');
      tick();
      byId(fileId);
      resource = resource || {};
      args = args || {};
      updates.push({ resource: Object.assign({}, resource), fileId, args: Object.assign({}, args) });
      if (Object.keys(resource).some(k => k !== 'trashed')) refuse('Files.update with ' + Object.keys(resource).join(','));
      const m = get(fileId);
      if (args.addParents) {
        const dest = get(args.addParents);
        if ((m.shared || dest.shared) && args.supportsAllDrives !== true) throw new Error('File not found (fake: supportsAllDrives)');
        if (!dest.isFolder || dest.trashed) throw new Error('fake Files.update: addParents is not a live folder');
        if (m.isFolder && dest.shared && !m.shared) throw new Error('teamDrivesFolderMoveInNotSupported (fake)');
        if (args.removeParents !== m.parent) throw new Error('fake Files.update: removeParents is not the current parent');
        if (!silent.has(fileId)) {
          m.parent = dest.id;
          m.shared = dest.shared;
        }
      }
      if (resource.trashed === true || resource.trashed === false) {
        m.trashed = resource.trashed;
        m.explicitlyTrashed = resource.trashed;
      }
      return rep(m);
    },
  });
  const props = {};
  for (const reg of Object.keys(REGION_IDS)) {
    props['SOURCE_FOLDER_' + reg.toUpperCase()] = SOURCE_IDS[reg];
    props['TARGET_FOLDER_' + reg.toUpperCase()] = REGION_IDS[reg];
  }
  // T14: the Script Properties as Apps Script keeps them, the mover's config untouchable
  const config = Object.assign({}, props);
  const bytes = s => Buffer.byteLength(String(s), 'utf8');
  const sizeOf = (p, keys) => (keys || Object.keys(p)).reduce((n, k) => n + bytes(k) + bytes(p[k]), 0);
  const storeRefuse = what => {
    banned.push('Properties: ' + what);
    throw new Error('fake Properties: the re-filing may not ' + what + ' (T14: the mover\'s config stays)');
  };
  const putAll = obj => {
    const next = Object.assign({}, props);
    for (const k of Object.keys(obj)) {
      const key = String(k), value = String(obj[k]);
      if (has(config, key) && value !== config[key]) storeRefuse('change ' + key);
      if (bytes(value) > VALUE_MAX) throw new Error('Argument too large: value');
      next[key] = value;
    }
    if (sizeOf(next) > STORE_MAX) {
      throw new Error('You have exceeded the property storage quota. Please remove some properties and try again.');
    }
    for (const k of Object.keys(next)) props[k] = next[k];
  };
  const properties = guard('Properties', {
    getProperty: k => (has(props, String(k)) ? props[String(k)] : null),
    getProperties: () => Object.assign({}, props),
    getKeys: () => Object.keys(props),
    setProperty: (k, v) => { putAll({ [String(k)]: v }); return properties; },
    setProperties: (obj, deleteAllOthers) => {
      if (deleteAllOthers) storeRefuse('delete every other property (setProperties with deleteAllOthers)');
      putAll(obj || {});
      return properties;
    },
    deleteProperty: k => {
      if (has(config, String(k))) storeRefuse('delete ' + k);
      delete props[String(k)];
      return properties;
    },
    deleteAllProperties: () => storeRefuse('delete all properties'),
  });
  const say = (...a) => logs.push(a.map(String).join(' '));
  const globals = {
    console: { log: say, info: say, warn: say, error: say },
    DriveApp: guard('DriveApp', {
      getFolderById: id => {
        calls.push('DriveApp.getFolderById');
        tick();
        byId(id);
        if (!get(id).isFolder) throw new Error('not a folder (fake)');
        return folderApi(id);
      },
      getFileById: id => {
        calls.push('DriveApp.getFileById');
        tick();
        byId(id);
        if (get(id).isFolder) throw new Error('not a file (fake)');
        return fileApi(id);
      },
    }),
    Drive: guard('Drive', { Files }),
    PropertiesService: guard('PropertiesService', { getScriptProperties: () => properties }),
    LockService: guard('LockService', {
      getScriptLock: () => guard('Lock', { tryLock: () => true, waitLock: () => undefined, releaseLock: () => undefined, hasLock: () => true }),
    }),
    ScriptApp: guard('ScriptApp', { getProjectTriggers: () => [] }),
  };
  if (opts.clocked) {   // T13: the sandbox's Date reads the fake clock (a vm context's own `Date` shadows the builtin)
    const RealDate = Date;
    globals.Date = class extends RealDate {
      constructor(...a) { if (a.length) super(...a); else super(clock.now); }
      static now() { return clock.now; }
    };
  }
  /** The folder names from the region folder down to the item's parent (the Shared Drive's root left out). */
  const where = id => {
    const out = [];
    for (let at = get(id).parent; at && at !== ROOT; at = items.get(at).parent) out.unshift(items.get(at).name);
    return out;
  };
  /** The live folders at that chain of names below the Shared Drive's root (['Africa', partner, month]). */
  const foldersAt = names => {
    let level = [ROOT];
    for (const nm of names) level = [].concat(...level.map(i => kids(i).filter(k => k.isFolder && !k.trashed && k.name === nm).map(k => k.id)));
    return level;
  };
  return { add, items, logs, creates, updates, banned, calls, hooks, silent, globals, where, foldersAt, kids,
           queries, refused, nameAsks, state, clock, props,
           ownStoreBytes: () => sizeOf(props, Object.keys(props).filter(k => !has(config, k))),
           configIntact: () => Object.keys(config).every(k => props[k] === config[k]),
           snapshot: () => JSON.stringify([...items.values()].map(m => [m.id, m.name, m.parent, m.trashed, m.shared])) };
}

const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'refile-237-'));
let tmpN = 0;
const listSource = rows => 'const REFILE_LIST = [\n' + rows.map(x => '  ' + JSON.stringify(x)).join(',\n') + '\n];\n';

/** The entry point run in a new sandbox (one execution): drive-sync/*.gs, then RefileList.gs holding `src` (T6). */
function runEntry(env, entry, src) {
  let threw = '';
  const before = env.logs.length;
  const files = GS.slice();
  if (src !== null) {
    const f = path.join(TMP, 'RefileList' + (++tmpN) + '.gs');
    fs.writeFileSync(f, src);
    files.push(f);
  }
  try {
    const c = loadGs.sandbox(files, env.globals);
    vm.runInContext(entry + '();', c, { timeout: 20000 });
  } catch (e) { threw = String(e && e.message || e); }
  return { threw, text: env.logs.slice(before).join('\n') };
}

const E2E_LIST = [
  { region: 'Africa', partner: ALPHA, club: 'Sunrise Club' },
  { region: 'Africa', partner: ALPHA, club: 'Bright Stars' },
  { region: 'Africa', partner: BETA, club: 'Golden Wings' },
  { region: 'Africa', partner: DELTA, club: 'Golden Wings' },
  { region: 'Asia', partner: BETA, club: 'Ocean Lights' },
  { region: 'Asia', partner: GAMMA, club: 'River Roots' },
];
// [id, region, name, photos, expect]: expect [Partner, Month] (re-filed) or {code, names?} (stays)
const E2E = [
  ['A1', 'Africa', 'Sunrise Club 10-30-2026', ['IMG_5001.jpg', 'Nimbleford portrait.jpg'], [ALPHA, '2026-10']],
  ['A2', 'Africa', 'Sunrise Club 11-06-2026', ['IMG_5003.jpg'], [ALPHA, '2026-11']],
  ['A3', 'Africa', 'Bright Stars', ['IMG_5004.jpg'], [ALPHA, 'undated']],
  ['A4', 'Africa', 'bright  stars 10-02-2026', ['IMG_5005.jpg'], [ALPHA, '2026-10']],
  ['A5', 'Africa', 'Golden Wings 10-30-2026', ['IMG_5006.jpg'], { code: 'ambiguous', names: [BETA, DELTA] }],
  ['A6', 'Africa', 'Golden Wings - Fixture Partner Beta 10-30-2026', ['IMG_5007.jpg'], [BETA, '2026-10']],
  ['A7', 'Africa', 'Morning Voices 10-30-2026', ['IMG_5008.jpg'], { code: 'no-partner' }],
  ['A8', 'Africa', 'Sunrise Club 02-30-2026', ['IMG_5009.jpg'], { code: 'bad-date' }],
  ['A9', 'Africa', 'Fixture Partner Zeta | Evening Lights | 10-30-2026 | 4', ['IMG_5010.jpg'], [ZETA, '2026-10']],
  ['A10', 'Africa', ' | Sunrise Club | 11-13-2026 | 2', ['IMG_5011.jpg'], [ALPHA, '2026-11']],
  ['A11', 'Africa', 'Bright Stars 10-09-2026', ['IMG_5012.jpg'], { code: 'duplicate-name' }],
  ['A12', 'Africa', 'Bright Stars 10-09-2026', ['IMG_5013.jpg', 'IMG_5014.jpg'], { code: 'duplicate-name' }],
  ['A13', 'Africa', 'Fixture Partner Alpha Sunrise Club 11-23-2026 4', ['IMG_5022.jpg'], [ALPHA, '2026-11']],   // T11
  ['A14', 'Africa', 'Fixture Partner Beta Sunrise Club 11-23-2026', ['IMG_5023.jpg'], { code: 'no-partner' }],  // T11
  ['S1', 'Asia', 'River Roots 10-16-2026', ['IMG_5015.jpg'], { code: 'exists' }],
  ['S2', 'Asia', 'River Roots 10-23-2026', ['IMG_5016.jpg', 'IMG_5017.jpg'], [GAMMA, '2026-10']],
  ['S3', 'Asia', 'Ocean Lights', ['IMG_5018.jpg'], [BETA, 'undated']],
  ['S4', 'Asia', 'Golden Wings 10-30-2026', ['IMG_5019.jpg'], { code: 'ambiguous', names: [BETA, DELTA] }],
  ['X', 'Asia', 'River Roots 10-02-2026', ['IMG_5020.jpg'], [GAMMA, '2026-10']],   // trashed after the read
  ['Y', 'Asia', 'River Roots 10-09-2026', ['IMG_5021.jpg'], [GAMMA, '2026-10']],   // moved after the read
];
// folders that hold folders (G5), and folders in the trash (never read, never touched)
const E2E_HOLD = [['PB', 'Africa', BETA], ['OLD', 'Africa', 'Old uploads'], ['PG', 'Asia', GAMMA]];
function seedE2E(env) {
  let k = 0;
  for (const [id, region, name, photos] of E2E) {
    env.add(REGION_IDS[region], name, true, { id });
    for (const p of photos) env.add(id, p, false, { size: 1000 + (++k) });
  }
  env.add(REGION_IDS.Africa, BETA, true, { id: 'PB' });
  env.add('PB', '2026-09', true, { id: 'PB09' });
  env.add('PB09', 'Golden Wings - Fixture Partner Beta 09-25-2026', true, { id: 'PB09X' });
  env.add('PB09X', 'IMG_5100.jpg', false, { size: 77 });
  env.add(REGION_IDS.Africa, 'Old uploads', true, { id: 'OLD' });
  env.add('OLD', 'misc', true, { id: 'OLDM' });
  env.add('OLDM', 'IMG_5101.jpg', false, { size: 78 });
  env.add(REGION_IDS.Africa, ALPHA, true, { id: 'DEAD', trashed: true });
  env.add('DEAD', '2026-10', true, { id: 'DEAD10', trashed: true });
  env.add(REGION_IDS.Africa, 'Sunrise Club 10-16-2026', true, { id: 'TR', trashed: true });
  env.add('TR', 'IMG_5102.jpg', false, { size: 79, trashed: true });
  env.add(REGION_IDS.Asia, GAMMA, true, { id: 'PG' });
  env.add('PG', '2026-10', true, { id: 'PG10' });
  env.add('PG10', 'River Roots 10-16-2026', true, { id: 'PG10X' });
  env.add('PG10X', 'IMG_5103.jpg', false, { size: 80 });
}
const MOVED = E2E.filter(x => Array.isArray(x[4]) && x[0] !== 'X' && x[0] !== 'Y');
const target = x => [x[1]].concat(x[4]);
const noFileNames = text => !/IMG_\d+/.test(text) && !/Nimbleford/.test(text);
const driveCalls = env => env.calls.filter(c => /^Drive/.test(c));

/** T12 and G8 on what the runs asked Drive: each listing names one parent, none refused, no file's name asked. */
function checkQueries(what, env, ran) {
  const many = env.queries.filter(x => x.parents.length > 1), none = env.queries.filter(x => !x.parents.length);
  check(what + ': no Drive query names more than one parent (T12: ' + env.queries.length + ' listing(s))',
        ran && env.queries.length > 0 && !many.length,
        many.length ? many.length + ', e.g. ' + many[0].q.slice(0, 160) : ran ? '' : 'it did not run');
  check(what + ': every listing names exactly one folder (none a whole-drive query), and Drive refused none',
        ran && !none.length && !env.refused.length,
        (none.length ? 'no parent: ' + none[0].q.slice(0, 120) + '; ' : '') + env.refused.length + ' refused' +
        (env.refused.length ? ' (' + MEMBERSHIP + ')' : ''));
  check(what + ': Drive was never asked for a file\'s name (G8)', ran && !env.nameAsks.length,
        env.nameAsks.length ? env.nameAsks.length + ', e.g. ' + env.nameAsks[0].slice(0, 120) : '');
}

console.log('\npreviewRefile — the dry run: plans and logs every folder, makes and moves nothing (G8, T5)');
{
  const env = fakeDrive();
  seedE2E(env);
  const before = env.snapshot();
  const r = runEntry(env, 'previewRefile', listSource(E2E_LIST));
  check('the dry run ends without an error', !r.threw, r.threw);
  const ran = !r.threw && !!r.text.trim();
  check('it ran, and made, moved, renamed or trashed nothing: no Files.create, no Files.update, the Drive as it was',
        ran && !env.creates.length && !env.updates.length && !env.banned.length && env.snapshot() === before,
        (ran ? '' : 'it did not run; ') + env.creates.length + ' create(s), ' + env.updates.length + ' update(s); ' + env.banned.join(', '));
  const lines = r.text.split('\n');
  for (const [, region, name, , expect] of E2E) {
    const nm = name.trim();
    if (Array.isArray(expect)) {
      const to = region + '/' + expect.join('/');
      check('a line names ' + JSON.stringify(nm) + ' and its target ' + to, lines.some(l => l.includes(nm) && l.includes(to)),
            lines.filter(l => l.includes(nm)).join(' || ') || 'no line names it');
    } else {
      const words = [expect.code].concat(expect.names || []);
      check('a line names ' + JSON.stringify(nm) + ' and why it stays: ' + words.join(', '),
            lines.some(l => l.includes(nm) && words.every(w => l.includes(w))),
            lines.filter(l => l.includes(nm)).join(' || ') || 'no line names it');
    }
  }
  for (const [, , name] of E2E_HOLD) {
    check('a line names ' + JSON.stringify(name) + ' and why it stays: holds-folders',
          lines.some(l => l.includes(name) && l.includes('holds-folders')), lines.filter(l => l.includes(name)).join(' || ') || 'none');
  }
  check('the log (not empty) names no photo', ran && noFileNames(r.text), ran ? (r.text.match(/IMG_\d+|Nimbleford/) || [''])[0] : 'it did not run');
  checkQueries('the dry run', env, ran);
}

console.log('\nrefileExisting — the real run: each folder moved whole by one update, partner and month folders made once (G7)');
{
  const env = fakeDrive();
  seedE2E(env);
  const photoParents = new Map([...env.items.values()].filter(m => !m.isFolder).map(m => [m.id, m.parent]));
  const trashedBefore = new Map([...env.items.values()].map(m => [m.id, m.trashed]));
  const names = new Map([...env.items.values()].map(m => [m.id, m.name]));
  env.hooks.set('X', () => {
    const m = env.items.get('X');
    m.trashed = true;
    m.explicitlyTrashed = true;
    for (const kid of env.kids('X')) kid.trashed = true;
  });
  env.hooks.set('Y', () => { env.items.get('Y').parent = 'PG'; });
  const r = runEntry(env, 'refileExisting', listSource(E2E_LIST));
  check('the real run ends without an error (a folder skipped as moved or trashed is no failure: T8)', !r.threw, r.threw);
  const ran = !r.threw && env.updates.length > 0, notRun = 'the run moved nothing' + (r.threw ? ': ' + r.threw : '');
  for (const x of MOVED) {
    const [id, , name] = x;
    const m = env.items.get(id);
    check('"' + name.trim() + '" is now in ' + target(x).join(' / ') + ', its id and name kept',
          same(env.where(id), target(x)) && m.name === name && m.isFolder && !m.trashed, JSON.stringify(env.where(id)));
  }
  const stayed = E2E.filter(x => !Array.isArray(x[4])).map(x => [x[0], x[1], x[2]]).concat(E2E_HOLD);
  check('every folder that stays is still directly in its region folder, as it was',
        ran && stayed.every(([id, region, name]) => same(env.where(id), [region]) && env.items.get(id).name === name),
        ran ? stayed.filter(([id, region]) => !same(env.where(id), [region])).map(([id]) => id + ' in ' + JSON.stringify(env.where(id))).join(', ')
          : notRun);
  check('the existing partner and month folders are reused: Asia\'s Gamma/2026-10, Africa\'s Beta',
        env.items.get('S2').parent === 'PG10' && env.items.get(env.items.get('A6').parent).parent === 'PB',
        env.items.get('S2').parent + ', ' + env.items.get(env.items.get('A6').parent).parent);
  const CHAINS = [['Africa', ALPHA], ['Africa', ALPHA, '2026-10'], ['Africa', ALPHA, '2026-11'], ['Africa', ALPHA, 'undated'],
                  ['Africa', BETA], ['Africa', BETA, '2026-10'], ['Africa', BETA, '2026-09'], ['Africa', ZETA], ['Africa', ZETA, '2026-10'],
                  ['Asia', GAMMA], ['Asia', GAMMA, '2026-10'], ['Asia', BETA], ['Asia', BETA, 'undated']];
  const counts = CHAINS.map(c => c.join('/') + ': ' + env.foldersAt(c).length);
  check('each partner and month folder exists once, a partner folder in the trash not reused',
        CHAINS.every(c => env.foldersAt(c).length === 1) && env.kids('DEAD').length === 1, counts.join('; '));
  check('9 folders made (Africa: Alpha, its 2026-10, 2026-11, undated; Beta/2026-10; Zeta, its 2026-10. Asia: Beta, its undated), ' +
        'each by Drive.Files.create with supportsAllDrives',
        env.creates.length === 9 && env.creates.every(c => c.args.supportsAllDrives === true && c.resource.mimeType === FOLDER),
        env.creates.map(c => c.resource.name).join(', '));
  const movedIds = MOVED.map(x => x[0]).sort();
  const byFolder = env.updates.map(u => u.fileId).sort();
  check('one Drive.Files.update per moved folder and no other: ' + movedIds.join(', '), same(byFolder, movedIds), show(byFolder, movedIds));
  const wrong = env.updates.filter(u => {
    const x = MOVED.find(e => e[0] === u.fileId);
    return !x || Object.keys(u.resource).length || u.args.supportsAllDrives !== true || u.args.removeParents !== REGION_IDS[x[1]] ||
      u.args.addParents !== env.items.get(u.fileId).parent;
  });
  check('each update: resource {}, addParents its month folder, removeParents its region folder, supportsAllDrives (T10)',
        ran && !wrong.length, ran ? JSON.stringify(wrong.slice(0, 2)) : notRun);
  const movedPhotos = [...photoParents].filter(([id, parent]) => env.items.get(id).parent !== parent);
  check('no photo moved by itself: each still in its own folder',
        ran && !movedPhotos.length && !env.updates.some(u => !env.items.get(u.fileId).isFolder), ran ? movedPhotos.map(([id]) => id).join(', ') : notRun);
  const renamed = [...names].filter(([id, nm]) => env.items.get(id).name !== nm);
  const trashedNow = [...trashedBefore].filter(([id, t]) => env.items.get(id).trashed !== t && id !== 'X' && env.items.get(id).parent !== 'X');
  check('nothing renamed, nothing trashed or untrashed, no refused call', ran && !renamed.length && !trashedNow.length && !env.banned.length,
        ran ? JSON.stringify({ renamed, trashedNow, banned: env.banned }) : notRun);
  check('a folder trashed since the read is skipped: still in the trash, still in the region folder',
        env.items.get('X').trashed && same(env.where('X'), ['Asia']) && !env.updates.some(u => u.fileId === 'X'), JSON.stringify(env.where('X')));
  check('a folder moved since the read is skipped: still where it was moved to',
        same(env.where('Y'), ['Asia', GAMMA]) && !env.updates.some(u => u.fileId === 'Y'), JSON.stringify(env.where('Y')));
  const lines = r.text.split('\n');
  for (const [id, nm] of [['X', 'River Roots 10-02-2026'], ['Y', 'River Roots 10-09-2026']]) {
    check('the log says ' + id + ' "' + nm + '" was moved or trashed since the read (T8)',
          lines.some(l => l.includes(nm) && /moved or trashed/i.test(l)), lines.filter(l => l.includes(nm)).join(' || ') || 'none');
  }
  check('the folders in the trash are left alone', ran && env.items.get('TR').trashed && env.items.get('DEAD').trashed &&
        same(env.where('TR'), ['Africa']) && same(env.where('DEAD'), ['Africa']), JSON.stringify([env.where('TR'), env.where('DEAD')]));
  check('the log names no photo', ran && noFileNames(r.text), ran ? (r.text.match(/IMG_\d+|Nimbleford/) || [''])[0] : notRun);
  checkQueries('the real run', env, ran);

  // a re-run after a complete run: nothing left to do
  const made = env.creates.length, moved = env.updates.length, snap = env.snapshot();
  const r2 = runEntry(env, 'refileExisting', listSource(E2E_LIST));
  check('a re-run moves nothing and makes nothing; the Drive as it was', ran && !r2.threw && env.creates.length === made &&
        env.updates.length === moved && env.snapshot() === snap,
        r2.threw || (env.creates.length - made) + ' made, ' + (env.updates.length - moved) + ' moved');
}

console.log('\nrefileExisting — a move Drive does not confirm on read-back is REFILE_FAILED; the rest goes on (G7, T9)');
{
  const env = fakeDrive();
  env.add(REGION_IDS.Africa, 'Sunrise Club 10-30-2026', true, { id: 'F1' });
  env.add('F1', 'IMG_6001.jpg', false, { size: 1 });
  env.add(REGION_IDS.Africa, 'Bright Stars', true, { id: 'F2' });
  env.add('F2', 'IMG_6002.jpg', false, { size: 2 });
  env.silent.add('F1');
  const r = runEntry(env, 'refileExisting', listSource(E2E_LIST));
  check('a REFILE_FAILED line names the folder',
        r.text.split('\n').some(l => l.includes('REFILE_FAILED') && l.includes('Sunrise Club 10-30-2026')), r.text.split('\n').slice(-6).join(' || '));
  check('the other folder still moves', same(env.where('F2'), ['Africa', ALPHA, 'undated']), JSON.stringify(env.where('F2')));
  check('the log names no photo', env.updates.length > 0 && noFileNames(r.text),
        env.updates.length ? (r.text.match(/IMG_\d+/) || [''])[0] : 'the run moved nothing' + (r.threw ? ': ' + r.threw : ''));
}

console.log('\npreviewRefile / refileExisting — REFILE_LIST missing or malformed: refused before any Drive call (G9, T7)');
{
  const ROW = { region: 'Africa', partner: ALPHA, club: 'Sunrise Club' };
  const BAD_LISTS = [
    ['missing (no RefileList.gs)', null],
    ['an object, not an array', 'const REFILE_LIST = ' + JSON.stringify(ROW) + ';\n'],
    ['a string', 'const REFILE_LIST = "Sunrise Club";\n'],
    ['null', 'const REFILE_LIST = null;\n'],
    ['a row with a blank partner', listSource([ROW, { region: 'Africa', partner: '', club: 'Bright Stars' }])],
    ['a row without a partner', listSource([ROW, { region: 'Africa', club: 'Bright Stars' }])],
    ['a row with a blank club', listSource([ROW, { region: 'Africa', partner: ALPHA, club: '' }])],
    ['a row whose club is a number', listSource([ROW, { region: 'Africa', partner: ALPHA, club: 42 }])],
    ['a row that is a string', listSource([ROW, 'Bright Stars'])],
    ['a row that is null', listSource([ROW, null])],
  ];
  for (const entry of ['previewRefile', 'refileExisting']) {
    for (const [label, src] of BAD_LISTS) {
      const env = fakeDrive();
      seedE2E(env);
      const before = env.snapshot();
      const r = runEntry(env, entry, src);
      check(entry + ', REFILE_LIST ' + label + ': throws naming REFILE_LIST, no Drive call, nothing changed',
            !!r.threw && /REFILE_LIST/.test(r.threw) && !driveCalls(env).length && env.snapshot() === before,
            (r.threw || 'no error') + '; Drive calls: ' + driveCalls(env).slice(0, 4).join(', '));
    }
  }
}

// ---------------------------------------------------------------- #262: a region bigger than one run's read budget
const ETA = 'Fixture Partner Eta', THETA = 'Fixture Partner Theta';
const CLUB_WORDS = ['Bright', 'Rising', 'Golden', 'Silver', 'Morning', 'Evening', 'Northern', 'Southern', 'River', 'Mountain',
                    'Ocean', 'Valley'];   // make_fixture.py's RANDOM_CLUB_WORDS and _NOUNS
const CLUB_NOUNS = ['Stars', 'Lights', 'Flames', 'Voices', 'Wings', 'Roots'];
const BIG_PARTNERS = [ALPHA, BETA, GAMMA, DELTA, ETA, THETA];
/** The big region's clubs [{club, partners}]: none, off the list (no-partner); two, ambiguous. */
const BIG_CLUBS = [];
CLUB_WORDS.forEach((w, a) => CLUB_NOUNS.forEach((nn, b) => {
  const i = a * CLUB_NOUNS.length + b, p = (a * 5 + b) % 6;
  BIG_CLUBS.push({ club: w + ' ' + nn,
                   partners: i % 17 === 5 ? [] : i % 13 === 7 ? [BIG_PARTNERS[p], BIG_PARTNERS[(p + 1) % 6]] : [BIG_PARTNERS[p]] });
}));
const BIG_LIST = [].concat(...BIG_CLUBS.map(c => c.partners.map(p => ({ region: 'Africa', partner: p, club: c.club })))).concat([
  { region: 'Asia', partner: GAMMA, club: 'Rising Harbor Club' }, { region: 'Asia', partner: BETA, club: 'Mountain Path Club' },
  { region: 'Asia', partner: DELTA, club: 'Southern Bridge Club' }]);
const onlyPartner = P => BIG_CLUBS.filter(c => c.partners.length === 1 && c.partners[0] === P).map(c => c.club);
const BIG_MONTHS = [[2026, 9], [2026, 10], [2026, 11], [2026, 12], [2027, 1]];
const BIG_BAD = ['02-30-2026', '13-40-2026', '04-31-2027', '02-29-2027', '10-32-2026', '11-31-2026'];
const BIG_ROOTS = 300;
const ALNUM = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
let bigImg = 7000;

/**
 * The big Africa region folder (BIG_ROOTS folders directly in it, Drive-length ids, listed in no order) and a small Asia
 * one. Each folder G5/G6 hold is there (an empty folder named like a partner, a partner folder with a folder already in
 * its month, two partner folders of a name, two month folders of a name, a folder of files named like a partner, three
 * pairs of one name), with an anchor: the outcome the rulings give it, independent of the planner. The rest are photo
 * folders in every name shape G4 and T11 read. Returns {africa: [{id, name, expect}], asia, R, L2, old}.
 */
function seedBig(env) {
  const r = prng(26200);
  const pick = a => a[Math.floor(r() * a.length)];
  const ids = new Set();
  const nid = () => {
    let id;
    do { id = '1' + Array.from({ length: 32 }, () => ALNUM[Math.floor(r() * ALNUM.length)]).join(''); } while (ids.has(id));
    ids.add(id);
    return id;
  };
  const date = () => { const [y, m] = pick(BIG_MONTHS); return mdy(y, m, 1 + Math.floor(r() * daysIn(y, m))); };
  const known = BIG_CLUBS.filter(c => c.partners.length === 1), amb = BIG_CLUBS.filter(c => c.partners.length > 1);
  const off = BIG_CLUBS.filter(c => !c.partners.length).map(c => c.club).concat(['Hidden Valley', 'Quiet Harbor', 'Paper Lanterns']);
  const roots = [], used = new Set();
  const push = (name, files, sub, expect) => { roots.push({ name, files, sub: sub || [], expect }); used.add(name); };
  const fresh = make => { for (;;) { const n = make(); if (!used.has(n)) return n; } };
  const exClub = onlyPartner(BETA)[0], exName = exClub + ' 11-12-2026';
  push(ALPHA, 0, [], { code: 'holds-folders' });   // empty, named like a partner the region targets: that partner's folder
  push(exName, 2, [], { code: 'exists' });
  push(BETA, 0, [['2026-09', [BETA + ' | ' + exClub + ' | 09-25-2026 | 3']], ['2026-10', []], ['undated', []], ['2026-11', [exName]]],
       { code: 'holds-folders' });
  push(GAMMA, 0, [['2026-10', []]], { code: 'holds-folders' });
  push(GAMMA, 0, [['2026-11', []]], { code: 'holds-folders' });
  push(DELTA, 0, [['2026-11', []], ['2026-11', []], ['2026-10', []], ['2026-12', []]], { code: 'holds-folders' });
  push(THETA, 2, [], { code: 'partner-name' });
  push('Old uploads', 0, [['misc', []]], { code: 'holds-folders' });
  push(onlyPartner(GAMMA)[0] + ' 10-14-2026', 1, [], { code: 'partner-folders' });
  push(onlyPartner(DELTA)[0] + ' 11-05-2026', 1, [], { code: 'month-folders' });
  push(onlyPartner(DELTA)[0] + ' 10-05-2026', 1, [], { path: [DELTA, '2026-10'], reuse: 'both' });
  push(onlyPartner(THETA)[0] + ' 10-21-2026', 1, [], { code: 'partner-name' });
  push(onlyPartner(ALPHA)[0] + ' 12-02-2026', 1, [], { path: [ALPHA, '2026-12'], reuse: 'partner' });
  push(onlyPartner(ETA)[0] + ' 09-16-2026', 1, [], { path: [ETA, '2026-09'], reuse: 'none' });
  push(onlyPartner(BETA)[1] + ' 10-07-2026', 1, [], { path: [BETA, '2026-10'], reuse: 'both' });
  push(amb[0].club + ' 10-28-2026', 1, [], { code: 'ambiguous' });
  push('Quiet Harbor 10-28-2026', 1, [], { code: 'no-partner' });
  push(onlyPartner(ALPHA)[1] + ' 02-30-2026', 1, [], { code: 'bad-date' });
  for (let k = 0; k < 3; k++) {
    const nm = fresh(() => pick(known).club + ' ' + date());
    push(nm, 1, [], { code: 'duplicate-name' });
    push(nm, 2, [], { code: 'duplicate-name' });
  }
  while (roots.length < BIG_ROOTS) {
    const kind = r(), wk = String(1 + Math.floor(r() * 30));
    push(fresh(() => {
      if (kind < 0.55) return pick(known).club + ' ' + date();
      if (kind < 0.63) return pick(known).club;
      if (kind < 0.68) return pick([ALPHA, BETA, DELTA, ETA, ZETA]) + ' | ' + pick(known).club + ' | ' + date() + ' | ' + wk;
      if (kind < 0.73) return ' | ' + pick(known).club + ' | ' + date() + ' | ' + wk;
      if (kind < 0.80) {
        const c = pick(known);
        return (r() < 0.8 ? c.partners[0] : pick(BIG_PARTNERS)) + ' ' + c.club + ' ' + date() + (r() < 0.7 ? ' ' + wk : '');
      }
      if (kind < 0.84) return pick(known).club + ' ' + pick(BIG_BAD);
      if (kind < 0.92) return pick(off) + ' ' + date();
      return pick(amb).club + ' ' + date();
    }), 1 + Math.floor(r() * 3));
  }
  for (let i = roots.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [roots[i], roots[j]] = [roots[j], roots[i]]; }
  let L2 = 0, old = null;
  const photo = parent => env.add(parent, 'IMG_' + (++bigImg) + '.jpg', false, { size: 1000 + bigImg });
  for (const x of roots) {
    x.id = nid();
    env.add(REGION_IDS.Africa, x.name, true, { id: x.id });
    if (x.name === 'Old uploads') old = x.id;
    for (let k = 0; k < x.files; k++) photo(x.id);
    for (const [sname, kids] of x.sub) {
      const sid = nid();
      L2++;
      env.add(x.id, sname, true, { id: sid });
      if (sname === 'misc') photo(sid);
      for (const k of kids) { const kid = nid(); env.add(sid, k, true, { id: kid }); photo(kid); }
    }
  }
  const pg = nid(), pg10 = nid();
  env.add(REGION_IDS.Asia, GAMMA, true, { id: pg });
  env.add(pg, '2026-10', true, { id: pg10 });
  const asia = [{ id: pg, name: GAMMA, expect: { code: 'holds-folders' } },
                { name: 'Rising Harbor Club 10-23-2026', expect: { path: [GAMMA, '2026-10'], reuse: 'both' } },
                { name: 'Mountain Path Club', expect: { path: [BETA, 'undated'], reuse: 'none' } },
                { name: 'Southern Bridge Club 11-20-2026', expect: { path: [DELTA, '2026-11'], reuse: 'none' } },
                { name: 'Northern Harbor Club 10-30-2026', expect: { code: 'no-partner' } }];
  for (const x of asia.slice(1)) {
    x.id = nid();
    env.add(REGION_IDS.Asia, x.name, true, { id: x.id });
    photo(x.id);
  }
  return { africa: roots, asia, R: roots.length, L2, old };
}

/** A folder of photos `name` directly in the region folder (a person's, or one the run before did not see). */
function addRoot(env, region, name) {
  const id = env.add(REGION_IDS[region], name, true);
  env.add(id, 'IMG_' + (++bigImg) + '.jpg', false, { size: 11 });
  return id;
}
/** What the mover does between runs: `<Region>/<Partner>/<YYYY-MM>/<sub>/` made where missing, a photo in it. */
function moverFiles(env, region, partner, month, sub) {
  let at = REGION_IDS[region];
  for (const nm of [partner, month]) {
    const have = env.kids(at).filter(k => k.isFolder && !k.trashed && k.name === nm);
    at = have.length ? have[0].id : env.add(at, nm, true);
  }
  const s = env.add(at, sub, true);
  env.add(s, 'IMG_' + (++bigImg) + '.jpg', false, { size: 12 });
}
/** A `<club> <MM-DD-YYYY>` name in that month no folder directly in the region folder has. */
function freshRoot(env, region, club, y, m) {
  const taken = new Set(env.kids(REGION_IDS[region]).map(k => k.name));
  for (let d = 15; d <= daysIn(y, m); d++) if (!taken.has(club + ' ' + mdy(y, m, d))) return club + ' ' + mdy(y, m, d);
  throw new Error('freshRoot: no free day');
}

/** The tree planRefile_ takes for a region folder, read from the fake in one go (what readRefileRegion_ would give). */
function treeOf(env, regionId) {
  const live = id => env.kids(id).filter(k => !k.trashed), dirs = id => live(id).filter(k => k.isFolder);
  return { id: regionId, folders: dirs(regionId).map(a => ({
    id: a.id, name: a.name, files: live(a.id).filter(k => !k.isFolder).length,
    folders: dirs(a.id).map(b => ({ id: b.id, name: b.name, files: null,
                                    folders: dirs(b.id).map(c => ({ id: c.id, name: c.name, files: null, folders: [] })) })) })) };
}
/** planRefile_ on the Drive as it now is, read in one go (the planner tests above pin it): {by: id -> entry, refile}. */
function oracle(env) {
  const regions = {};
  for (const reg of Object.keys(REGION_IDS)) regions[reg] = treeOf(env, REGION_IDS[reg]);
  const got = planOf(regions, BIG_LIST), by = new Map();
  const { refile, stays } = lists(got.plan);
  for (const e of refile || []) by.set(e.id, { kind: 'refile', region: e.region, id: e.id, name: e.name, path: Array.from(e.path),
                                               partnerId: e.partnerId, monthId: e.monthId });
  for (const s of stays || []) by.set(s.id, { kind: 'stay', region: s.region, id: s.id, name: s.name, code: s.code });
  return { error: got.error, by, refile: [...by.values()].filter(e => e.kind === 'refile'),
           stays: [...by.values()].filter(e => e.kind === 'stay') };
}
function anchorMisses(o, roots) {
  return roots.filter(x => x.expect).map(x => {
    const e = o.by.get(x.id), w = x.expect;
    const ok = !!e && (w.code ? e.kind === 'stay' && e.code === w.code :
      e.kind === 'refile' && same(e.path, w.path) &&
      (w.reuse === 'both' ? !!e.partnerId && !!e.monthId : w.reuse === 'partner' ? !!e.partnerId && e.monthId === null :
        e.partnerId === null && e.monthId === null));
    return ok ? null : JSON.stringify(x.name) + ': ' + JSON.stringify(e ? e.code || [e.path, e.partnerId, e.monthId] : 'none') +
      ' want ' + JSON.stringify(w);
  }).filter(Boolean);
}

const LEFT_TO_READ = /(\d+)[^\d\n]{0,40}left to read/i;
const LEFT_ANY = /(\d+)[^\d\n]{0,40}\bleft\b/i;
const budgetLines = (lines, region) => lines.filter(l => /TIME_BUDGET/.test(l) && (!region || l.includes(region)));
/** T15: the n of the run's `TIME_BUDGET ... <region> ... <n> ... left to read` line, null when it has none. */
function readLeft(lines, region) {
  const l = budgetLines(lines, region).find(x => LEFT_TO_READ.test(x));
  return l ? Number(LEFT_TO_READ.exec(l)[1]) : null;
}
/** One execution of `entry` on BIG_LIST: its log lines, what it made and moved, the parents it listed, its time. */
function bigRun(env, entry) {
  env.state.run++;
  const c0 = env.creates.length, u0 = env.updates.length, q0 = env.queries.length, t0 = env.clock.now, s0 = env.snapshot();
  const r = runEntry(env, entry, listSource(BIG_LIST));
  const run = { n: env.state.run, threw: r.threw, text: r.text, lines: r.text.split('\n'), creates: env.creates.slice(c0),
                updates: env.updates.slice(u0),
                listed: new Set([].concat(...env.queries.slice(q0).filter(x => !x.refused).map(x => x.parents))),
                took: env.clock.now - t0, changed: env.snapshot() !== s0 };
  run.left = readLeft(run.lines, 'Africa');
  run.budget = budgetLines(run.lines).length > 0;
  env.clock.now += 10 * MIN;   // the trigger's interval: the mover may run in between
  return run;
}
const africaMoves = run => run.updates.filter(u => u.args && u.args.removeParents === REGION_IDS.Africa);
const liveRoots = (env, region) => env.kids(REGION_IDS[region]).filter(k => k.isFolder && !k.trashed);
const rootNames = env => [].concat(...Object.keys(REGION_IDS).map(reg => liveRoots(env, reg).map(k => k.name.trim())));
/** The lines that name `name`, less those naming a longer root name that holds it (`River Roots` in `River Roots 10-02-2026`). */
function linesNaming(lines, name, names) {
  const longer = names.filter(n => n !== name && n.includes(name));
  return lines.filter(l => !/TIME_BUDGET/.test(l) && l.includes(name) && !longer.some(n => l.includes(n)));
}
/** T5 / T16: the region-root folders of `regions` that no line names with the target (and no stay code) or stay code `o` gives. */
function planMisses(lines, env, o, regions) {
  const names = rootNames(env), bad = [];
  for (const region of regions) {
    for (const k of liveRoots(env, region)) {
      const nm = k.name.trim(), e = o.by.get(k.id);
      if (!e) { bad.push(JSON.stringify(nm) + ': not in the planner\'s plan'); continue; }
      const want = e.kind === 'refile' ? region + '/' + e.path.join('/') : e.code;
      const ls = linesNaming(lines, nm, names);
      const ok = e.kind === 'refile' ? ls.some(l => l.includes(want) && !CODES.some(c => l.includes(c))) : ls.some(l => l.includes(want));
      if (!ok) bad.push(JSON.stringify(nm) + ' -> ' + want + ' :: ' + (ls[0] || 'no line names it').trim());
    }
  }
  return bad;
}
/** T15: the region's folders (named in no other region) a run's lines name with a target path or a stay code. */
function planLeaks(lines, env, region) {
  const names = rootNames(env);
  const elsewhere = new Set([].concat(...Object.keys(REGION_IDS).filter(x => x !== region).map(x => liveRoots(env, x).map(k => k.name.trim()))));
  return liveRoots(env, region).map(k => k.name.trim()).filter(nm => !elsewhere.has(nm) &&
    linesNaming(lines, nm, names).some(l => l.includes(region + '/') || CODES.some(c => l.includes(c))));
}
function bounds(big, moves) {
  const W = 2 * big.R + big.L2 + Math.ceil(big.R / BIG_PAGE) + 2, per = Math.ceil(W / (READ_CALLS / 2));
  return { W, cycle: per + 2, phase1: per + Math.ceil(8 * (moves || 0) / (2 * READ_CALLS)) + 2, quiet: 2 * (per + 2) + 2 };
}
const dated = name => /\b\d{2}-\d{2}-\d{4}$/.test(name.trim());
const showRuns = runs => runs.map(x => 'run ' + x.n + ': ' + (x.threw ? 'threw ' + x.threw.slice(0, 120) :
  (x.left === null ? '' : x.left + ' left to read; ') + africaMoves(x).length + ' moved' + (x.budget ? '; TIME_BUDGET' : ''))).join(' | ');

console.log('\npreviewRefile — a region bigger than one run\'s read budget: read over several runs, then planned in full (#262: T12-T16)');
{
  const env = fakeDrive({ clocked: true, pageCap: BIG_PAGE });
  const big = seedBig(env);
  const o0 = oracle(env);
  const b = bounds(big);
  check('the fixture: the planner, on the big region read in one go, gives every anchor the outcome the rulings give it',
        !o0.error && !anchorMisses(o0, big.africa.concat(big.asia)).length,
        o0.error || anchorMisses(o0, big.africa.concat(big.asia)).slice(0, 4).join(' ;; '));
  const codes = new Set(o0.stays.filter(s => s.region === 'Africa').map(s => s.code));
  check('the fixture: ' + big.R + ' folders directly in Africa (' + o0.refile.length + ' to re-file, every stay code among the ' +
        'rest), ' + big.L2 + ' in those: more than one run reads with ' + READ_CALLS + ' Drive calls; a cycle within ' + b.cycle + ' runs',
        big.R + big.L2 + 1 > READ_CALLS && CODES.every(c => codes.has(c)) && o0.refile.length > 100,
        CODES.filter(c => !codes.has(c)).join(', '));
  const runs = [];
  let added = null;
  for (let i = 0; i < b.cycle; i++) {
    const run = bigRun(env, 'previewRefile');
    runs.push(run);
    if (run.n === 1) added = addRoot(env, 'Africa', freshRoot(env, 'Africa', onlyPartner(ALPHA)[2], 2026, 12));
    if (run.threw || !run.budget) break;
  }
  const ran = runs.every(x => !x.threw), last = runs[runs.length - 1];
  check('no run of the cycle ends in an error', ran, showRuns(runs));
  check('the first run reads part of Africa: a TIME_BUDGET line names it with the folders left to read (T15)',
        runs[0].left > 0 && budgetLines(runs[0].lines, 'Africa').length > 0, budgetLines(runs[0].lines).join(' || ') || runs[0].threw);
  check('repeated runs finish the cycle within ' + b.cycle + ' runs: the last logs no TIME_BUDGET line (T16)',
        ran && !last.budget, showRuns(runs));
  const partial = runs.filter(x => x.left !== null);
  check('until the run that completes Africa\'s read each run says how many folders are left, a number that falls every run (T15)',
        ran && partial.length > 0 && partial.every((x, i) => x === runs[i] && x.left > 0 && (!i || x.left < partial[i - 1].left)),
        partial.map(x => x.left).join(' > '));
  const leaks = partial.map(x => planLeaks(x.lines, env, 'Africa')).filter(l => l.length);
  check('a run that has not read Africa in full logs none of its plan (T15)', ran && !leaks.length,
        leaks.length ? leaks[0].slice(0, 3).join(', ') : '');
  check('a run that does not plan Asia names it in a TIME_BUDGET line (T15)',
        ran && runs.every(x => x.lines.some(l => l.includes('Asia/')) || budgetLines(x.lines, 'Asia').length > 0),
        runs.filter(x => !x.lines.some(l => l.includes('Asia/')) && !budgetLines(x.lines, 'Asia').length).map(x => 'run ' + x.n).join(', '));
  const oEnd = oracle(env), all = [].concat(...runs.map(x => x.lines));
  const misses = planMisses(all, env, oEnd, ['Africa', 'Asia']);
  check('the cycle logs every folder of both regions with the planner\'s outcome on the Drive read in one go: ' +
        oEnd.refile.length + ' re-filed (same target), ' + oEnd.stays.length + ' stay (same code) (T16; DoD: outcomes unchanged)',
        ran && !last.budget && !misses.length, misses.length + ' missed; ' + misses.slice(0, 4).join(' ;; '));
  const addedName = added && env.items.get(added).name;
  check('a folder that appeared after the first run is in the plan: ' + JSON.stringify(addedName) + ' -> Africa/' + ALPHA + '/2026-12',
        !!added && linesNaming(all, addedName, rootNames(env)).some(l => l.includes('Africa/' + ALPHA + '/2026-12')), '');
  check('no run made, moved, renamed or trashed anything (G8)',
        ran && !env.creates.length && !env.updates.length && !env.banned.length && !runs.some(x => x.changed),
        env.creates.length + ' create(s), ' + env.updates.length + ' update(s); ' + env.banned.join(', '));
  checkQueries('the preview cycle', env, ran && runs.length > 1);
  check('the logs name no photo; no run passes Apps Script\'s 6 minutes on the fake clock (T13)',
        ran && runs.every(x => noFileNames(x.text) && x.took <= 6 * MIN), runs.map(x => Math.round(x.took / 1000) + 's').join(', '));
  check('when the cycle ends the re-filing keeps under 2 KB in the Script Properties, the config unchanged (T14, T16)',
        ran && !last.budget && env.configIntact() && env.ownStoreBytes() < 2048, env.ownStoreBytes() + ' bytes kept');

  // after the cycle: one folder renamed, one trashed, one added; the next cycle reads the Drive as it now is (T16)
  const oneName = e => liveRoots(env, 'Africa').filter(k => k.name === e.name).length === 1;
  const picks = oEnd.refile.filter(e => e.region === 'Africa' && e.id !== added && dated(e.name) && oneName(e) && e.path[0] !== BETA);
  const ren = picks[0], gone = picks[1];
  const oldName = ren.name, newName = freshRoot(env, 'Africa', onlyPartner(BETA)[2], 2027, 1);
  env.items.get(ren.id).name = newName;
  env.items.get(gone.id).trashed = true;
  for (const k of env.kids(gone.id)) k.trashed = true;
  const added2 = addRoot(env, 'Africa', freshRoot(env, 'Africa', onlyPartner(ETA)[1], 2026, 12));
  const runs2 = [];
  for (let i = 0; i < b.cycle; i++) {
    const run = bigRun(env, 'previewRefile');
    runs2.push(run);
    if (run.threw || !run.budget) break;
  }
  const ran2 = runs2.every(x => !x.threw), last2 = runs2[runs2.length - 1], all2 = [].concat(...runs2.map(x => x.lines));
  check('the run after a complete cycle reads Africa again (nothing planned from the last cycle\'s read): TIME_BUDGET, n left (T16)',
        ran2 && runs2[0].left > 0, showRuns(runs2.slice(0, 2)));
  const misses2 = planMisses(all2, env, oracle(env), ['Africa', 'Asia']);
  check('the next cycle finishes within ' + b.cycle + ' runs and plans the Drive as it now is: the renamed folder by its new ' +
        'name, the added one, every other as the planner says (T16)',
        ran2 && !last2.budget && !misses2.length, (last2.budget ? 'not finished; ' : '') + misses2.slice(0, 4).join(' ;; '));
  const names2 = rootNames(env).concat([oldName, gone.name]);
  check('the next cycle names neither the renamed folder\'s old name nor the trashed folder',
        ran2 && !linesNaming(all2, oldName, names2).length && !linesNaming(all2, gone.name, names2).length,
        linesNaming(all2, oldName, names2).concat(linesNaming(all2, gone.name, names2)).slice(0, 2).join(' || '));
  check('the next cycle plans the folder added after the last: ' + JSON.stringify(env.items.get(added2).name),
        linesNaming(all2, env.items.get(added2).name, rootNames(env)).some(l => l.includes('Africa/' + ETA + '/2026-12')), '');
  check('and again keeps under 2 KB when it ends, makes and moves nothing',
        ran2 && env.configIntact() && env.ownStoreBytes() < 2048 && !env.creates.length && !env.updates.length,
        env.ownStoreBytes() + ' bytes kept');
}

console.log('\nrefileExisting — the big region re-filed over repeated runs; what the mover adds between runs used, not doubled (#262: T15-T17)');
{
  const env = fakeDrive({ clocked: true, pageCap: BIG_PAGE });
  const big = seedBig(env);
  const o0 = oracle(env);
  const b = bounds(big, o0.refile.length);
  const runs = [], wrong = [], monthsAdded = [];
  const hand = { trash: null, rename: null, moved: null, newName: '', new1: null, new2: null };
  const isHand = id => id === hand.trash || id === hand.rename || id === hand.moved;
  const inPlace = e => same(env.where(e.id), [e.region].concat(e.path));
  const nameOf = id => (env.items.get(id) || {}).name;
  let firstMove = 0;
  /** T17: a move must be one planRefile_ makes on the Drive as it was when the run started. */
  const movesOff = (run, oStart) => run.updates.filter(u => u.args && u.args.removeParents).map(u => {
    const e = oStart.by.get(u.fileId);
    if (!e || e.kind !== 'refile') {
      return 'run ' + run.n + ' moved ' + JSON.stringify(nameOf(u.fileId)) + ', which the plan of the Drive then ' +
        (e ? 'holds (' + e.code + ')' : 'does not have');
    }
    return inPlace(e) ? null : 'run ' + run.n + ' moved ' + JSON.stringify(e.name) + ' to ' + env.where(u.fileId).join('/') + ', not ' +
      [e.region].concat(e.path).join('/');
  }).filter(Boolean);
  const between = run => {
    if (run.n === 1) {   // a folder the first run read trashed, one renamed, one moved by hand (T17)
      const once = e => liveRoots(env, 'Africa').filter(k => k.name === e.name).length === 1;
      const read1 = o0.refile.filter(e => e.region === 'Africa' && run.listed.has(e.id) && dated(e.name) && once(e) && e.path[0] !== BETA);
      const any = o0.refile.filter(e => e.region === 'Africa' && dated(e.name) && once(e) && e.path[0] !== BETA);
      const three = read1.length >= 3 ? read1 : any;
      [hand.trash, hand.rename, hand.moved] = three.slice(0, 3).map(e => e.id);
      hand.readFirst = read1.length >= 3;
      env.items.get(hand.trash).trashed = true;
      for (const k of env.kids(hand.trash)) k.trashed = true;
      hand.newName = freshRoot(env, 'Africa', onlyPartner(BETA)[2], 2027, 1);
      env.items.get(hand.rename).name = hand.newName;
      env.items.get(hand.moved).parent = big.old;
    }
    if (run.n === 2) {   // the mover files a submission of a partner with no folder yet; a person adds a folder
      moverFiles(env, 'Africa', ETA, '2026-11', ETA + ' | Hidden Valley | 11-24-2026 | 4');   // an off-list club: no name clash
      hand.new1 = addRoot(env, 'Africa', freshRoot(env, 'Africa', onlyPartner(ALPHA)[2], 2026, 12));
    }
    if (!firstMove && africaMoves(run).length) {   // a folder added once the moves have begun
      firstMove = run.n;
      hand.new2 = addRoot(env, 'Africa', freshRoot(env, 'Africa', onlyPartner(ALPHA)[3], 2027, 1));
    }
    if (monthsAdded.length < 4) {   // the mover makes a month folder a planned folder waits for, its partner folder read before
      const want = o0.refile.filter(e => e.region === 'Africa' && !isHand(e.id) && !inPlace(e) && e.path[1] !== 'undated' &&
        env.foldersAt(['Africa', e.path[0]]).length === 1 && !env.foldersAt(['Africa'].concat(e.path)).length);
      const staleOf = e => runs.some(x => x.listed.has(env.foldersAt(['Africa', e.path[0]])[0]));
      const e = want.filter(staleOf)[0] || want[0];
      if (e) {
        monthsAdded.push({ path: e.path, stale: staleOf(e) });
        moverFiles(env, 'Africa', e.path[0], e.path[1], e.path[0] + ' | Hidden Valley | ' + e.path[1].slice(5) + '-20-' +
                   e.path[1].slice(0, 4) + ' | 2');
      }
    }
  };
  const step = () => {
    const oStart = oracle(env);
    const run = bigRun(env, 'refileExisting');
    runs.push(run);
    wrong.push(...movesOff(run, oStart));
    run.movesLeft = run.left === null && o0.refile.some(e => e.region === 'Africa' && !isHand(e.id) && !inPlace(e));
    between(run);
    return run;
  };
  const firstPlan = () => o0.refile.filter(e => !isHand(e.id));
  let phase1 = 0, quiet = 0;
  for (let i = 0; i < b.phase1 && !phase1; i++) {
    const run = step();
    if (run.threw) break;
    if (firstPlan().every(inPlace)) phase1 = run.n;
  }
  for (let i = 0; phase1 && i < b.quiet && !quiet; i++) {
    const run = step();
    if (run.threw) break;
    if (!run.budget && !run.updates.length && !run.creates.length) quiet = run.n;
  }
  const ran = runs.length > 0 && runs.every(x => !x.threw && !/REFILE_FAILED/.test(x.text));
  check('no run ends in an error or logs REFILE_FAILED', ran, showRuns(runs.filter(x => x.threw || /REFILE_FAILED/.test(x.text)).slice(0, 3)) ||
        showRuns(runs.slice(0, 3)));
  check('the first run reads part of Africa (TIME_BUDGET, n left to read) and moves none of its folders (T15, T17)',
        runs[0].left > 0 && !africaMoves(runs[0]).length, showRuns(runs.slice(0, 1)));
  const k1 = runs.findIndex(x => x.left === null);
  check('no Africa folder moves before the run that completes its read; until then n falls every run (T15, T17)',
        k1 > 0 && runs.slice(0, k1).every((x, i) => !africaMoves(x).length && x.left > 0 && (!i || x.left < runs[i - 1].left)),
        showRuns(runs.slice(0, k1 < 0 ? runs.length : k1 + 1)));
  check('every folder of the first plan (' + firstPlan().length + ') is in its target within ' + b.phase1 + ' runs: the moves a run ' +
        'leaves are made by the next runs, without the region read again first (T17)',
        ran && phase1 > 0, (phase1 ? 'run ' + phase1 : firstPlan().filter(e => !inPlace(e)).length + ' not in place') + '; ' + showRuns(runs));
  const leaving = runs.filter(x => k1 >= 0 && x.n >= runs[k1].n && phase1 && x.n < phase1);
  const says = x => x.budget && (!x.movesLeft || budgetLines(x.lines).some(l => LEFT_ANY.test(l)));
  check('each run that leaves work for the next logs TIME_BUDGET; one that leaves moves says how many are left (T17)',
        ran && phase1 > 0 && leaving.every(says), leaving.filter(x => !says(x)).map(x => 'run ' + x.n).join(', '));
  check('every move is one planRefile_ makes on the Drive as it was at the start of that run: none from a part of a region (T17)',
        ran && !wrong.length && env.updates.length > 0, wrong.slice(0, 3).join(' ;; '));
  check('then a quiet run (no TIME_BUDGET, nothing moved or made) within ' + b.quiet + ' more runs', ran && quiet > 0,
        quiet ? 'run ' + quiet : showRuns(runs.slice(-4)));
  const off = firstPlan().filter(e => !inPlace(e) || nameOf(e.id) !== e.name || env.items.get(e.id).trashed);
  check('the first plan\'s folders are each in <Region>/<Partner>/<Month>, id and name kept', ran && !off.length,
        off.slice(0, 3).map(e => JSON.stringify(e.name) + ' in ' + env.where(e.id).join('/')).join(', '));
  const moved = o0.stays.filter(s => !same(env.where(s.id), [s.region]) || nameOf(s.id) !== s.name);
  check('every folder the first plan holds is still directly in its region folder, as it was', ran && !moved.length,
        moved.slice(0, 3).map(s => JSON.stringify(s.name) + ' in ' + env.where(s.id).join('/')).join(', '));
  check('three folders the first run had read were changed by hand before the second (the fixture: T17\'s case)', !!hand.readFirst, '');
  const touched = id => env.updates.some(u => u.fileId === id);
  check('the folder trashed since its read: never moved, still in the trash, in the region folder', ran && quiet > 0 &&
        env.items.get(hand.trash).trashed && same(env.where(hand.trash), ['Africa']) && !touched(hand.trash), env.where(hand.trash).join('/'));
  check('the folder moved by hand since its read: still where it was put', ran && quiet > 0 &&
        same(env.where(hand.moved), ['Africa', 'Old uploads']) && !touched(hand.moved), env.where(hand.moved).join('/'));
  check('the folder renamed since its read: re-filed by its new name ' + JSON.stringify(hand.newName) + ' to Africa/' + BETA + '/2027-01',
        same(env.where(hand.rename), ['Africa', BETA, '2027-01']) && nameOf(hand.rename) === hand.newName, env.where(hand.rename).join('/'));
  check('folders that appeared between runs are re-filed: Africa/' + ALPHA + '/2026-12 and /2027-01',
        !!hand.new1 && !!hand.new2 && same(env.where(hand.new1), ['Africa', ALPHA, '2026-12']) &&
        same(env.where(hand.new2), ['Africa', ALPHA, '2027-01']),
        JSON.stringify([hand.new1 && env.where(hand.new1), hand.new2 && env.where(hand.new2)]));
  const chains = new Set();
  for (const e of firstPlan()) { chains.add(JSON.stringify([e.region, e.path[0]])); chains.add(JSON.stringify([e.region].concat(e.path))); }
  for (const c of [['Africa', ETA], ['Africa', ETA, '2026-11'], ['Africa', BETA, '2027-01'], ['Africa', ALPHA, '2027-01']]) {
    chains.add(JSON.stringify(c));
  }
  const doubled = [...chains].map(c => JSON.parse(c)).filter(c => env.foldersAt(c).length !== 1);
  check('each partner and month folder is there once (' + chains.size + '): the mover\'s partner folder for ' + ETA +
        ' and its month folders used, never a second made (T17)', ran && !doubled.length,
        doubled.slice(0, 4).map(c => c.join('/') + ': ' + env.foldersAt(c).length).join('; '));
  const stale = monthsAdded.filter(x => x.stale);
  check('the month folders the mover made between runs (' + monthsAdded.length + ', ' + stale.length + ' after the re-filing had read ' +
        'their partner folder) are used: each there once, holding the folders planned for it',
        monthsAdded.length >= 3 && stale.length > 0 && monthsAdded.every(x => env.foldersAt(['Africa'].concat(x.path)).length === 1),
        monthsAdded.map(x => x.path.join('/') + (x.stale ? ' (stale)' : '') + ': ' + env.foldersAt(['Africa'].concat(x.path)).length).join('; '));
  const madeTwice = env.creates.map(c => JSON.stringify([c.resource.parents, c.resource.name]))
    .filter((k, i, a) => a.indexOf(k) !== i);
  check('no partner or month folder made twice in all the runs', ran && !madeTwice.length, madeTwice.slice(0, 3).join(', '));
  const badUpdate = env.updates.filter(u => Object.keys(u.resource).length || u.args.supportsAllDrives !== true ||
    (u.args.removeParents !== REGION_IDS.Africa && u.args.removeParents !== REGION_IDS.Asia));
  check('each move: resource {}, removeParents its region folder, supportsAllDrives (G7, T10)', ran && !badUpdate.length,
        JSON.stringify(badUpdate.slice(0, 2)));
  checkQueries('the real runs', env, ran);
  check('the logs name no photo; no run passes Apps Script\'s 6 minutes on the fake clock (T13)',
        ran && runs.every(x => noFileNames(x.text) && x.took <= 6 * MIN), runs.map(x => Math.round(x.took / 1000) + 's').join(', '));
  check('the quiet run leaves under 2 KB in the Script Properties, the config unchanged, no refused call (T14, T16)',
        ran && quiet > 0 && env.configIntact() && env.ownStoreBytes() < 2048 && !env.banned.length,
        env.ownStoreBytes() + ' bytes kept; ' + env.banned.join(', '));

  // a new cycle after the quiet run: nothing left to move
  const made = env.creates.length, movedN = env.updates.length, snap = env.snapshot(), more = [];
  for (let i = 0; quiet && i < b.cycle; i++) {
    const run = bigRun(env, 'refileExisting');
    more.push(run);
    if (run.threw || !run.budget) break;
  }
  check('a new cycle after it ends within ' + b.cycle + ' runs, moving and making nothing; the Drive as it was',
        quiet > 0 && more.length > 0 && more.every(x => !x.threw) && !more[more.length - 1].budget && env.creates.length === made &&
        env.updates.length === movedN && env.snapshot() === snap, showRuns(more));
}

fs.rmSync(TMP, { recursive: true, force: true });
finish();
