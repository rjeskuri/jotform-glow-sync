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
 */
const ROOT = 'drive-root-237';
const REGION_IDS = { Africa: 'tgt-africa', Asia: 'tgt-asia' };
const SOURCE_IDS = { Africa: 'src-africa', Asia: 'src-asia' };

function parseDriveQuery(q) {
  const src = String(q), toks = [];
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
  return test;
}

function fakeDrive() {
  const items = new Map(), logs = [], creates = [], updates = [], banned = [], calls = [];
  const hooks = new Map(), silent = new Set();
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
      getId: () => id, getName: () => m().name, getSize: () => m().size, getMimeType: () => 'image/jpeg',
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
      getFolders: () => iter(kids(id).filter(k => k.isFolder).map(k => folderApi(k.id))),
      getFoldersByName: nm => iter(kids(id).filter(k => k.isFolder && k.name === nm).map(k => folderApi(k.id))),
      getFiles: () => iter(kids(id).filter(k => !k.isFolder).map(k => fileApi(k.id))),
      getFilesByName: nm => iter(kids(id).filter(k => !k.isFolder && k.name === nm).map(k => fileApi(k.id))),
      getParents: () => iter(m().parent ? [folderApi(m().parent)] : []),
      createFolder: nm => refuse('Folder.createFolder ' + nm), moveTo: () => refuse('Folder.moveTo'),
      setTrashed: () => refuse('Folder.setTrashed'), setName: () => refuse('Folder.setName'),
    });
  }
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
      if (!args || typeof args.q !== 'string') throw new Error('fake Files.list: q required');
      const test = parseDriveQuery(args.q);
      const all = args.supportsAllDrives === true && args.includeItemsFromAllDrives === true;
      let pool = [...items.values()].filter(m => m.id !== ROOT && (all || !m.shared));
      if (args.corpora === 'drive') pool = pool.filter(m => m.shared && args.driveId === ROOT);
      const hits = pool.filter(test);
      const start = args.pageToken ? Number(args.pageToken) : 0;
      const out = { files: hits.slice(start, start + 2).map(rep) };
      if (start + 2 < hits.length) out.nextPageToken = String(start + 2);
      return out;
    },
    get(id, args) {
      calls.push('Drive.Files.get');
      byId(id);
      const m = get(id);
      if (m.shared && !(args && args.supportsAllDrives === true)) throw new Error('File not found: ' + id + ' (fake: supportsAllDrives)');
      return rep(m);
    },
    create(resource, media, args) {
      calls.push('Drive.Files.create');
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
  const say = (...a) => logs.push(a.map(String).join(' '));
  const globals = {
    console: { log: say, info: say, warn: say, error: say },
    DriveApp: guard('DriveApp', {
      getFolderById: id => {
        calls.push('DriveApp.getFolderById');
        byId(id);
        if (!get(id).isFolder) throw new Error('not a folder (fake)');
        return folderApi(id);
      },
      getFileById: id => {
        calls.push('DriveApp.getFileById');
        byId(id);
        if (get(id).isFolder) throw new Error('not a file (fake)');
        return fileApi(id);
      },
    }),
    Drive: guard('Drive', { Files }),
    PropertiesService: guard('PropertiesService', {
      getScriptProperties: () => guard('Properties', { getProperty: k => (has(props, k) ? props[k] : null) }),
    }),
    LockService: guard('LockService', {
      getScriptLock: () => guard('Lock', { tryLock: () => true, waitLock: () => undefined, releaseLock: () => undefined, hasLock: () => true }),
    }),
    ScriptApp: guard('ScriptApp', { getProjectTriggers: () => [] }),
  };
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

fs.rmSync(TMP, { recursive: true, force: true });
finish();
