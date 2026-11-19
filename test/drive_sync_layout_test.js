#!/usr/bin/env node
'use strict';
/**
 * Offline tests for ticket #225: the photo mover files a submission subfolder under
 * `<Region>/<Partner>/<YYYY-MM>/` on the Shared Drive when its name carries the partner and the
 * session date (Ryan's option A, 2026-11-18). drive-sync/*.gs are loaded together in a vm sandbox
 * as in test/drive_sync_test.js (whose tests stay as they are: R3).
 *
 * The orchestrator's rulings, pinned here:
 *
 *   R1  The Jotform subfolder name (set by hand in each form's Drive integration, Ryan's step):
 *         `<Partner> | <Club Name> | <MM-DD-YYYY> | <Week>`
 *       separator " | " (club names may contain " - ", never "|"). The date is question 17 as Jotform
 *       writes it, mm-dd-yyyy (e.g. 10-30-2026). The week (question 100) is opaque text, blank or
 *       absent for a special event: `P | C | 10-30-2026 | ` (with or without trailing spaces) or
 *       `P | C | 10-30-2026`. Each segment's surrounding whitespace is trimmed for parsing.
 *   R2  Such a subfolder is filed at `<Region folder>/<Partner>/<YYYY-MM>/<its name unchanged>`, the
 *       month from the session date. Its own name is never changed.
 *   R3  Anything else stays exactly as today, directly in the region folder: a legacy name
 *       (`<Club> <MM-DD-YYYY>`, or the club alone), a blank Partner segment, a date that is not a
 *       real calendar date (13-40-2026, 02-30-2026), a wrong number of segments.
 *   R4  photoPath_(name) -> [partner, 'YYYY-MM'] for a layout name, [] otherwise (pure).
 *       planMoves_: each moves / merges / waiting / refused entry of a layout name carries
 *       `path: [<Partner>, <YYYY-MM>]`; one filed at the region root `path: []` (absent is read as
 *       [] here). targetFolders[region].subfolders entries gain `path` (the folder's place below the
 *       region folder; absent means []). Same-name matching (merge, refused, one per name per run)
 *       is by name AND path: a same-name folder at another path does not count. `to` stays the
 *       region folder's id.
 *   R5  The mover: moveSettledPhotos puts a layout subfolder's files in a folder of its name inside
 *       <Partner>/<YYYY-MM> under the region folder, making the partner and month folders when
 *       missing (Drive.Files.create with supportsAllDrives) and reusing one of that name when it
 *       exists; two folders of the partner's (or the month's) name at that level: refused and logged,
 *       nothing moved for that subfolder. previewMoves makes nothing and logs the target path.
 *       Retention (#185) still finds photos at the deeper level.
 *
 * The test-author's readings (reversible; the coder follows them):
 *
 *   T1  `P | C | 10-30-2026 |` (a blank week whose trailing space is gone) is a layout name too.
 *   T2  The dry run's line for a layout subfolder holds its name and `<Partner>/<YYYY-MM>`.
 *   T3  A partner or month folder in Drive's trash does not count: neither reused nor a duplicate.
 *   T4  A refusal's log line matches /refus/i and names the partner.
 *   T5  Dates in any other form (2026-10-30, 10/30/2026, 10-30-26) are R3's "anything else".
 *   T6  On the Shared Drive no folder is made by DriveApp's createFolder, and no Files.update carries
 *       a name (nothing is renamed).
 *
 * Every partner, club and file name is fictional (test/fixtures/make_fixture.py's word lists).
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const loadGs = require('./load_gs');
const { check, finish } = require('./helpers/js/check');

const DIR = path.join(__dirname, '..', 'drive-sync');
const GS = fs.existsSync(DIR) ? fs.readdirSync(DIR).filter(f => f.endsWith('.gs')).sort().map(f => path.join(DIR, f)) : [];
const MIN = 60 * 1000;
const DAY = 24 * 60 * MIN;
const OLD = 600;   // minutes: settled under the mover's 10-minute settle time
const PREFIX = 'Attendance photos - ';
const FOLDER = 'application/vnd.google-apps.folder';
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const show = (a, b) => 'got ' + JSON.stringify(a) + ' want ' + JSON.stringify(b);

// ---------------------------------------------------------------- loading: the pure functions, no Google service
const touched = [];
const trap = name => new Proxy({}, { get(_, k) { touched.push(name + '.' + String(k)); throw new Error(name + ' touched'); } });
const trapped = {};
for (const s of ['DriveApp', 'Drive', 'PropertiesService', 'ScriptApp', 'MailApp', 'GmailApp', 'UrlFetchApp', 'LockService',
                 'CacheService', 'SpreadsheetApp', 'Session']) trapped[s] = trap(s);
let ctx = null, loadError = '';
try { ctx = loadGs.sandbox(GS, trapped); } catch (e) { loadError = e.message; }
console.log('drive-sync/ — loads (#225)');
check('drive-sync/*.gs load with no Google service touched', !!ctx && !loadError && !touched.length, loadError || touched.join(', '));
const fn = name => (ctx && typeof ctx[name] === 'function' ? ctx[name] : null);
const photoPath = fn('photoPath_'), planMoves = fn('planMoves_'), planTrash = fn('planTrash_');
check('photoPath_ is a top-level function (R4)', !!photoPath, ctx ? typeof ctx.photoPath_ : 'not loaded');
const revive = ctx ? vm.runInContext(
  '(function (s) { return JSON.parse(s, function (k, v) { return k === "updated" || k === "created" ? new Date(v) : v; }); })', ctx)
  : s => JSON.parse(s);
const CtxDate = ctx ? vm.runInContext('Date', ctx) : Date;

function pathOf(name) {
  if (!photoPath) return { got: null, error: 'photoPath_ is not defined' };
  try {
    const got = photoPath(name);
    return { got: Array.isArray(got) ? Array.from(got) : got, error: '' };
  } catch (e) { return { got: null, error: e && e.message || String(e) }; }
}
function plan(sources, targets, nowMs) {
  if (!planMoves) return { plan: null, error: 'planMoves_ is not defined' };
  try {
    return { plan: planMoves(revive(JSON.stringify(sources)), revive(JSON.stringify(targets)), new CtxDate(nowMs), 10), error: '' };
  } catch (e) { return { plan: null, error: e && e.message || String(e) }; }
}

// ---------------------------------------------------------------- independent oracle for a name's place
const PARTNERS = ['Fixture Partner Alpha', 'Fixture Partner Beta', 'Fixture Partner Gamma - North', 'Fixture Partner Delta'];
const WORDS = ['Bright', 'Rising', 'Golden', 'Silver', 'Morning', 'Evening', 'River', 'Ocean'];
const NOUNS = ['Stars', 'Lights', 'Flames', 'Voices', 'Wings', 'Roots'];
const DIM = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
const isLeap = y => (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
const daysIn = (y, m) => (m === 2 && isLeap(y) ? 29 : DIM[m - 1]);
const p2 = x => String(x).padStart(2, '0');
const mdy = (y, m, d) => p2(m) + '-' + p2(d) + '-' + y;
const month = (y, m) => y + '-' + p2(m);
const BAD_DATES = ['13-40-2026', '02-30-2026', '04-31-2027', '02-29-2027', '00-10-2026', '10-00-2026', '10-32-2026',
                   '2026-10-30', '10/30/2026', '10-30-26', ''];

function prng(seed) {   // mulberry32
  return function () {
    seed |= 0; seed = seed + 0x6D2B79F5 | 0;
    let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

/** A random subfolder name and where R1-R3 put it, built from its parts (never parsed back). */
function randomName(r) {
  const pick = a => a[Math.floor(r() * a.length)];
  const pad = s => ' '.repeat(Math.floor(r() * 2)) + s + ' '.repeat(Math.floor(r() * 2));
  const club = pick(WORDS) + ' ' + pick(NOUNS) + (r() < 0.2 ? ' - ' + pick(PARTNERS) : '');
  const partner = pick(PARTNERS);
  const y = 2026 + Math.floor(r() * 3), m = 1 + Math.floor(r() * 12);
  const d = r() < 0.15 ? daysIn(y, m) : 1 + Math.floor(r() * daysIn(y, m));
  const date = mdy(y, m, d);
  const roll = r();
  if (roll < 0.55) {   // a layout name
    const w = Math.floor(r() * 6);
    const segs = [partner, club, date];
    if (w === 0) segs.push(String(1 + Math.floor(r() * 40)));
    else if (w === 1) segs.push('Week ' + (1 + Math.floor(r() * 40)));
    else if (w === 2) segs.push('W-12 / Term 2');
    else if (w === 3) segs.push('');
    else if (w === 4) segs.push('   ');
    let name = segs.map(pad).join(' | ');
    if (w >= 3 && r() < 0.5) name = name.replace(/\s+$/, '');   // T1
    return { kind: 'layout', name, path: [partner, month(y, m)] };
  }
  if (roll < 0.72) {
    const legacy = [club + ' ' + date, club, club + ' ' + mdy(y, m, d)];
    return { kind: 'legacy', name: pick(legacy), path: [] };
  }
  if (roll < 0.8) return { kind: 'no partner', name: [pick(['', ' ', '   ']), club, date, '3'].join(' | '), path: [] };
  if (roll < 0.9) return { kind: 'bad date', name: [partner, club, pick(BAD_DATES), '2'].join(' | '), path: [] };
  const wrong = [[partner, club], [partner, date], [partner, club, date, '4', 'extra'], [club, date]];
  return { kind: 'segments', name: pick(wrong).join(' | '), path: [] };
}

// ---------------------------------------------------------------- photoPath_: a table, then the named cases
console.log('\nphotoPath_ — partner and month from the name (R1, R3, R4)');
{
  const NAMED = [
    ['Fixture Partner Alpha | Bright Stars | 10-30-2026 | 4', ['Fixture Partner Alpha', '2026-10']],
    ['Fixture Partner Beta | Golden Wings | 01-05-2027 | Week 12', ['Fixture Partner Beta', '2027-01']],
    ['Fixture Partner Delta | River Roots | 12-31-2026 | 9', ['Fixture Partner Delta', '2026-12']],
    ['Fixture Partner Alpha | Bright Stars - Fixture Partner Beta | 11-02-2026 | 5', ['Fixture Partner Alpha', '2026-11']],
    ['Fixture Partner Gamma - North | Ocean Lights | 03-09-2028 | W-12 / Term 2', ['Fixture Partner Gamma - North', '2028-03']],
    ['  Fixture Partner Alpha   |  Silver Voices  |  10-30-2026  |  2  ', ['Fixture Partner Alpha', '2026-10']],
    ['Fixture Partner Alpha | Bright Stars | 02-29-2028 | 1', ['Fixture Partner Alpha', '2028-02']],
    // a special event: no week
    ['Fixture Partner Beta | Morning Flames | 10-30-2026 | ', ['Fixture Partner Beta', '2026-10']],
    ['Fixture Partner Beta | Morning Flames | 10-30-2026 |    ', ['Fixture Partner Beta', '2026-10']],
    ['Fixture Partner Beta | Morning Flames | 10-30-2026 |', ['Fixture Partner Beta', '2026-10']],   // T1
    ['Fixture Partner Beta | Morning Flames | 09-01-2026', ['Fixture Partner Beta', '2026-09']],
    // R3: missing partner, not a calendar date, wrong segments, legacy names
    [' | Morning Flames | 10-30-2026 | 3', []],
    ['   | Morning Flames | 10-30-2026 | ', []],
    ['Fixture Partner Alpha | Bright Stars | 13-40-2026 | 4', []],
    ['Fixture Partner Alpha | Bright Stars | 02-30-2026 | 4', []],
    ['Fixture Partner Alpha | Bright Stars | 02-29-2027 | 4', []],
    ['Fixture Partner Alpha | Bright Stars | 2026-10-30 | 4', []],   // T5
    ['Fixture Partner Alpha | Bright Stars | 10/30/2026 | 4', []],   // T5
    ['Fixture Partner Alpha | Bright Stars |  | 4', []],
    ['Fixture Partner Alpha | Bright Stars', []],
    ['Fixture Partner Alpha | 10-30-2026', []],
    ['Fixture Partner Alpha | Bright Stars | 10-30-2026 | 4 | extra', []],
    ['Bright Stars 10-30-2026', []],
    ['Bright Stars - Fixture Partner Beta 10-30-2026', []],
    ['Bright Stars', []],
    ['', []],
  ];
  for (const [name, want] of NAMED) {
    const r = pathOf(name);
    check('photoPath_(' + JSON.stringify(name) + ')', !r.error && same(r.got, want), r.error || show(r.got, want));
  }
  // a generated table: every partner, month and year, each kind of name
  const r = prng(225);
  const seen = {};
  let bad = [];
  for (let i = 0; i < 600; i++) {
    const n = randomName(r);
    seen[n.kind] = (seen[n.kind] || 0) + 1;
    const got = pathOf(n.name);
    if (got.error || !same(got.got, n.path)) bad.push(JSON.stringify(n.name) + ': ' + (got.error || show(got.got, n.path)));
  }
  check('600 generated names: each gives the partner and month it was built from, or []', !bad.length,
        bad.length + ' wrong; first: ' + bad.slice(0, 3).join(' ;; '));
  check('the generated names cover every kind', ['layout', 'legacy', 'no partner', 'bad date', 'segments'].every(k => seen[k] > 10),
        JSON.stringify(seen));
}

// ---------------------------------------------------------------- planMoves_: a generated table against an oracle
console.log('\nplanMoves_ — generated layouts against an independent oracle (R4: name AND path)');
const NOW = Date.UTC(2026, 10, 19, 12, 0, 0);
const pathKey = e => JSON.stringify(e && e.path === undefined ? [] : e && Array.from(e.path || ['<not an array>']));
const ids = xs => (xs || []).map(f => (f && typeof f === 'object' ? f.id : f)).sort().join(',');
function norm(p) {
  const L = k => (p && Array.isArray(p[k]) ? p[k] : []);
  return {
    moves: L('moves').map(m => [m.region, m.id, m.name, m.to, ids(m.files), pathKey(m)].join('|')).sort(),
    merges: L('merges').map(m => [m.region, m.id, m.name, m.into, ids(m.files), ids(m.kept), pathKey(m)].join('|')).sort(),
    waiting: L('waiting').map(m => [m.region, m.id, m.name, pathKey(m)].join('|')).sort(),
    refused: L('refused').map(m => [m.region, m.id, m.name, pathKey(m)].join('|')).sort(),
  };
}
{
  const REG = ['Africa', 'Asia', 'Latin America'];
  const tally = {};
  const bump = k => { tally[k] = (tally[k] || 0) + 1; };
  const failures = [];
  for (let seed = 1; seed <= 40; seed++) {
    const r = prng(1000 + seed);
    const pick = a => a[Math.floor(r() * a.length)];
    const sources = [], targets = {}, want = { moves: [], merges: [], waiting: [], refused: [] };
    let n = 0;
    const id = p => p + seed + '-' + (++n);
    for (const region of REG) {
      const tgt = { id: 'tgt-' + seed + '-' + region.replace(/\W/g, ''), subfolders: [] };
      targets[region] = tgt;
      const src = { id: id('src'), name: PREFIX + region, subfolders: [] };
      sources.push(src);
      const used = new Set();
      for (let i = 0; i < 8; i++) {
        let nm;
        do { nm = randomName(r); } while (used.has(nm.name));
        used.add(nm.name);
        const files = [];
        const fresh = r() < 0.12;
        for (let j = 0; j < 1 + Math.floor(r() * 3); j++) {
          files.push({ id: id('f'), name: 'IMG_' + (100 + j) + '.jpg', size: 1000 + Math.floor(r() * 9000),
                       updated: NOW - (fresh && j === 0 ? 2 : OLD) * MIN });
        }
        const sub = { id: id('sub'), name: nm.name, updated: NOW - OLD * MIN, folders: [], trashed: false, files };
        src.subfolders.push(sub);
        // where same-name folders already are on the Shared Drive
        const other = () => {
          if (!nm.path.length) return [pick(PARTNERS), '2026-10'];
          const k = Math.floor(r() * 3);
          if (k === 0) return [];
          if (k === 1) return [PARTNERS.filter(x => x !== nm.path[0])[0], nm.path[1]];
          return [nm.path[0], nm.path[1] === '2026-10' ? '2026-11' : '2026-10'];
        };
        const at = p => {
          const t = { id: id('tsub'), name: nm.name, files: [] };
          if (p.length || r() < 0.5) t.path = p;
          for (const f of files) if (r() < 0.4) t.files.push({ id: id('t'), name: f.name, size: f.size });
          if (r() < 0.3) t.files.push({ id: id('t'), name: 'IMG_900.jpg', size: 77 });
          tgt.subfolders.push(t);
          return t;
        };
        const sit = pick(['none', 'none', 'here', 'here', 'elsewhere', 'twice here', 'here and elsewhere', 'twice elsewhere']);
        const here = [];
        if (sit === 'here' || sit === 'here and elsewhere') here.push(at(nm.path));
        if (sit === 'twice here') here.push(at(nm.path), at(nm.path));
        if (sit === 'elsewhere' || sit === 'here and elsewhere') at(other());
        if (sit === 'twice elsewhere') { at(other()); at(other()); }
        const pk = JSON.stringify(nm.path);
        const layoutKind = nm.path.length ? 'layout' : 'root';
        if (fresh) {
          want.waiting.push([region, sub.id, sub.name, pk].join('|'));
          bump(layoutKind + ' waiting');
          continue;
        }
        if (here.length > 1) {
          want.refused.push([region, sub.id, sub.name, pk].join('|'));
          bump(layoutKind + ' refused');
        } else if (here.length === 1) {
          const dup = f => here[0].files.some(t => t.name === f.name && t.size === f.size);
          want.merges.push([region, sub.id, sub.name, here[0].id, ids(files.filter(f => !dup(f))), ids(files.filter(dup)), pk].join('|'));
          bump(layoutKind + ' merge');
        } else {
          want.moves.push([region, sub.id, sub.name, tgt.id, ids(files), pk].join('|'));
          bump(layoutKind + ' move' + (sit === 'none' ? '' : ' past a same-name folder elsewhere'));
        }
      }
    }
    const got = plan(sources, targets, NOW);
    if (got.error) { failures.push('seed ' + seed + ': ' + got.error); continue; }
    const g = norm(got.plan);
    for (const k of Object.keys(want)) {
      want[k].sort();
      if (!same(g[k], want[k])) {
        const missing = want[k].filter(x => !g[k].includes(x)), extra = g[k].filter(x => !want[k].includes(x));
        failures.push('seed ' + seed + ' ' + k + ': missing ' + JSON.stringify(missing.slice(0, 2)) + ' extra ' +
                      JSON.stringify(extra.slice(0, 2)));
      }
    }
  }
  check('40 generated runs: moves, merges, waiting and refused match the oracle, path included', !failures.length,
        failures.length + ' wrong; first: ' + failures.slice(0, 2).join(' ;; '));
  const need = ['layout move', 'layout merge', 'layout refused', 'layout waiting', 'layout move past a same-name folder elsewhere',
                'root move', 'root merge', 'root refused', 'root waiting', 'root move past a same-name folder elsewhere'];
  check('the table covers each outcome for layout and root names', need.every(k => tally[k] > 3), JSON.stringify(tally));
}

// ---------------------------------------------------------------- planMoves_: the named cases
console.log('\nplanMoves_ — the partner and month segments, a missing partner, a special event (the ticket\'s tests)');
const file = (id, name, size, ageMin) => ({ id, name, size, updated: NOW - (ageMin === undefined ? OLD : ageMin) * MIN });
const sub = (id, name, files, extra) => Object.assign({ id, name, updated: NOW - OLD * MIN, folders: [], trashed: false, files }, extra || {});
const src = (region, subs) => ({ id: 'src-' + region.replace(/\W/g, '').toLowerCase(), name: PREFIX + region, subfolders: subs });
const TGT = 'tgt-africa';
const tgtAfrica = subs => ({ Africa: { id: TGT, subfolders: subs || [] } });
{
  const CASES = [
    ['Fixture Partner Alpha | Bright Stars | 10-30-2026 | 4', ['Fixture Partner Alpha', '2026-10']],
    ['Fixture Partner Alpha | Bright Stars | 11-02-2026 | 4', ['Fixture Partner Alpha', '2026-11']],
    ['Fixture Partner Alpha | Bright Stars | 11-02-2027 | 4', ['Fixture Partner Alpha', '2027-11']],
    ['Fixture Partner Beta | Bright Stars | 10-30-2026 | 4', ['Fixture Partner Beta', '2026-10']],
    ['Fixture Partner Beta | Golden Wings | 10-30-2026 | ', ['Fixture Partner Beta', '2026-10']],   // special event
    ['Fixture Partner Beta | Golden Wings | 10-31-2026', ['Fixture Partner Beta', '2026-10']],      // special event
    [' | Golden Wings | 10-30-2026 | 4', []],                                                       // missing partner
    ['Fixture Partner Beta | Golden Wings | 13-40-2026 | 4', []],
    ['Fixture Partner Beta | Golden Wings', []],
    ['Golden Wings 10-30-2026', []],
    ['Golden Wings', []],
  ];
  const subs = CASES.map(([name], i) => sub('s' + i, name, [file('f' + i, 'IMG_' + i + '.jpg', 100 + i)]));
  const got = plan([src('Africa', subs)], tgtAfrica([]), NOW);
  const moves = got.plan && Array.isArray(got.plan.moves) ? got.plan.moves : [];
  CASES.forEach(([name, want], i) => {
    const m = moves.filter(x => x.id === 's' + i);
    const ok = m.length === 1 && m[0].to === TGT && same(JSON.parse(pathKey(m[0])), want) && m[0].name === name;
    check('a move of ' + JSON.stringify(name) + ': to the region folder, path ' + JSON.stringify(want), !got.error && ok,
          got.error || (m.length ? 'to ' + m[0].to + ' path ' + pathKey(m[0]) : 'no move'));
  });
}

console.log('\nplanMoves_ — a merge into an existing nested folder; a same-name folder at another path does not count');
{
  const NAME = 'Fixture Partner Alpha | Bright Stars | 10-30-2026 | 4';
  const PATH = ['Fixture Partner Alpha', '2026-10'];
  const files = () => [file('a', 'IMG_1.jpg', 100), file('b', 'IMG_2.jpg', 200)];
  const run = targets => plan([src('Africa', [sub('s1', NAME, files())])], tgtAfrica(targets), NOW);
  const expectOne = (label, targets, want) => {
    const got = run(targets);
    const g = norm(got.plan);
    check(label, !got.error && same(g, want), got.error || show(g, want));
  };
  const empty = { moves: [], merges: [], waiting: [], refused: [] };
  const pk = JSON.stringify(PATH);
  expectOne('the name once at its path: merged into that folder, the same-name-and-size photo kept',
            [{ id: 'n1', name: NAME, path: PATH, files: [{ id: 't1', name: 'IMG_1.jpg', size: 100 }] }],
            Object.assign({}, empty, { merges: ['Africa|s1|' + NAME + '|n1|b|a|' + pk] }));
  expectOne('the name only at the region root (filed before #225): a new folder at its path, not a merge',
            [{ id: 'r1', name: NAME, files: [{ id: 't1', name: 'IMG_1.jpg', size: 100 }] }],
            Object.assign({}, empty, { moves: ['Africa|s1|' + NAME + '|' + TGT + '|a,b|' + pk] }));
  expectOne('the name under another partner and under another month: a move to its own path',
            [{ id: 'x1', name: NAME, path: ['Fixture Partner Beta', '2026-10'], files: [] },
             { id: 'x2', name: NAME, path: ['Fixture Partner Alpha', '2026-11'], files: [] }],
            Object.assign({}, empty, { moves: ['Africa|s1|' + NAME + '|' + TGT + '|a,b|' + pk] }));
  expectOne('the name twice at its path: refused, with its path',
            [{ id: 'n1', name: NAME, path: PATH, files: [] }, { id: 'n2', name: NAME, path: PATH.slice(), files: [] }],
            Object.assign({}, empty, { refused: ['Africa|s1|' + NAME + '|' + pk] }));
  expectOne('the name once at its path and once at the root: merged into the one at its path, not refused',
            [{ id: 'r1', name: NAME, path: [], files: [] }, { id: 'n1', name: NAME, path: PATH, files: [] }],
            Object.assign({}, empty, { merges: ['Africa|s1|' + NAME + '|n1|a,b||' + pk] }));
  {
    const got = plan([src('Africa', [sub('s1', NAME, [file('a', 'IMG_1.jpg', 100, 2)])])], tgtAfrica([]), NOW);
    const g = norm(got.plan);
    check('a layout subfolder still uploading waits, with its path', !got.error && same(g.waiting, ['Africa|s1|' + NAME + '|' + pk]),
          got.error || JSON.stringify(g));
  }
  {
    // one per name per run: a live subfolder and one in the trash of the same layout name
    const got = plan([src('Africa', [sub('s1', NAME, [file('a', 'IMG_1.jpg', 100)]),
                                     sub('s2', NAME, [file('c', 'IMG_3.jpg', 300)], { trashed: true })])], tgtAfrica([]), NOW);
    const g = norm(got.plan);
    const ok = g.moves.length === 1 && g.waiting.length === 1 && g.moves[0].endsWith('|' + pk) && g.waiting[0].endsWith('|' + pk);
    check('one per name per run: of two same-name subfolders one moves to its path, the other waits', !got.error && ok,
          got.error || JSON.stringify(g));
  }
}

console.log('\nplanMoves_ — legacy names stay at the region root (R3)');
{
  const LEG = 'Evening Lights 10-29-2026';
  const files = [file('a', 'IMG_1.jpg', 100)];
  const empty = { moves: [], merges: [], waiting: [], refused: [] };
  const cases = [
    ['no same-name folder: a move to the root', [], { moves: ['Africa|s1|' + LEG + '|' + TGT + '|a|[]'] }],
    ['the name at the root without `path`: a merge, as today', [{ id: 'r1', name: LEG, files: [] }],
     { merges: ['Africa|s1|' + LEG + '|r1|a||[]'] }],
    ['the name only under a partner/month folder: does not count, a move to the root',
     [{ id: 'z1', name: LEG, path: ['Fixture Partner Alpha', '2026-10'], files: [] }],
     { moves: ['Africa|s1|' + LEG + '|' + TGT + '|a|[]'] }],
    ['once at the root (path []) and once nested: merged into the root one',
     [{ id: 'z1', name: LEG, path: ['Fixture Partner Alpha', '2026-10'], files: [] }, { id: 'r1', name: LEG, path: [], files: [] }],
     { merges: ['Africa|s1|' + LEG + '|r1|a||[]'] }],
    ['twice at the root: refused, as today', [{ id: 'r1', name: LEG, files: [] }, { id: 'r2', name: LEG, path: [], files: [] }],
     { refused: ['Africa|s1|' + LEG + '|[]'] }],
  ];
  for (const [label, targets, want] of cases) {
    const got = plan([src('Africa', [sub('s1', LEG, files)])], tgtAfrica(targets), NOW);
    const w = Object.assign({}, empty, want);
    check(label, !got.error && same(norm(got.plan), w), got.error || show(norm(got.plan), w));
  }
}

console.log('\nplanMoves_ — pure: no Google service, inputs unchanged');
{
  const NAME = 'Fixture Partner Alpha | Bright Stars | 10-30-2026 | 4';
  const s = [src('Africa', [sub('s1', NAME, [file('a', 'IMG_1.jpg', 100)])])];
  const t = tgtAfrica([{ id: 'n1', name: NAME, path: ['Fixture Partner Alpha', '2026-10'], files: [] }]);
  const sj = JSON.stringify(s), tj = JSON.stringify(t);
  const si = revive(sj), ti = revive(tj);
  touched.length = 0;
  let err = '', p = null;
  try { p = planMoves(si, ti, new CtxDate(NOW), 10); } catch (e) { err = e.message; }
  check('planning a layout name touches no Google service and leaves its inputs as they were',
        !err && !touched.length && JSON.stringify(si) === JSON.stringify(revive(sj)) && JSON.stringify(ti) === JSON.stringify(revive(tj)) &&
        norm(p).merges.length === 1, err || touched.join(', ') || JSON.stringify(norm(p)));
}

// ---------------------------------------------------------------- retention at the deeper level (guard: #185 walks any depth)
console.log('\nplanTrash_ — photos under Region/Partner/Month/Subfolder (R5; #185 already walks any depth)');
{
  const now = Date.UTC(2027, 3, 1, 0, 0, 0);
  const at = days => now - days * DAY;
  const SUBN = 'Fixture Partner Alpha | Bright Stars | 10-30-2026 | 4';
  const base = (partnerAge, withYoungSibling) => {
    const folders = [{ id: 'R', name: 'Africa', parent: 'root', created: at(400), complete: true },
                     { id: 'P', name: 'Fixture Partner Alpha', parent: 'R', created: at(partnerAge), complete: true },
                     { id: 'M', name: '2026-10', parent: 'P', created: at(150), complete: true },
                     { id: 'S', name: SUBN, parent: 'M', created: at(140), complete: true }];
    const files = [{ id: 'f1', parent: 'S', created: at(130) }, { id: 'f2', parent: 'S', created: at(120) }];
    if (withYoungSibling) {
      folders.push({ id: 'S2', name: 'Fixture Partner Alpha | Golden Wings | 10-02-2026 | 1', parent: 'M', created: at(140), complete: true });
      files.push({ id: 'f3', parent: 'S2', created: at(5) });
    }
    return { regions: { Africa: 'R' }, rootId: 'root', folders, files };
  };
  const run = d => {
    if (!planTrash) return { error: 'planTrash_ is not defined' };
    try {
      const out = planTrash(revive(JSON.stringify(d)), new CtxDate(now), 90, 100);
      return { files: Array.from(out.files).map(f => f.id + '@' + f.top), folders: Array.from(out.folders).map(f => f.id), error: '' };
    } catch (e) { return { error: e.message }; }
  };
  const cases = [
    ['all old, all emptied: the photos (top: the partner folder), then subfolder, month and partner folders, deepest first',
     base(200, false), { files: ['f1@P', 'f2@P'], folders: ['S', 'M', 'P'] }],
    ['a young photo in a sibling subfolder: only the emptied subfolder goes; month and partner folders stay',
     base(200, true), { files: ['f1@P', 'f2@P'], folders: ['S'] }],
    ['a partner folder made recently (made for a new month, say): emptied but young, it stays',
     base(30, false), { files: ['f1@P', 'f2@P'], folders: ['S', 'M'] }],
  ];
  for (const [label, d, want] of cases) {
    const got = run(d);
    check(label, !got.error && same(got.files, want.files) && same(got.folders, want.folders),
          got.error || show({ files: got.files, folders: got.folders }, want));
  }
}

// ---------------------------------------------------------------- the mover on a fake Drive (R5)
/**
 * A fake My Drive and Shared Drive. DriveApp: getFolderById / getFileById; a Folder lists its folders and files
 * (getFolders, getFoldersByName, getFiles, getFilesByName; Drive's trash included, isTrashed() true, as DriveApp
 * does), getParents, getName, getId, getLastUpdated, isTrashed; createFolder, moveTo and setTrashed refuse (T6,
 * #132). The advanced service (v3): Files.list answers `q` (`'<id>' in parents`, trashed, mimeType, name; and / or /
 * not, parentheses), two items a page, Shared Drive items only with supportsAllDrives and includeItemsFromAllDrives;
 * Files.get (a Shared Drive item only with supportsAllDrives); Files.create makes a folder under its one parent (on
 * the Shared Drive only with supportsAllDrives); Files.update moves a file (addParents an existing folder,
 * removeParents its current parent, supportsAllDrives), never a folder into the Shared Drive
 * (teamDrivesFolderMoveInNotSupported), and trashes or untrashes. Unknown members throw.
 */
const ROOT = 'drive-root-225';
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
  const items = new Map(), logs = [], creates = [], updates = [], banned = [];
  const t0 = Date.now();
  let n = 0;
  const add = (parent, name, isFolder, o) => {
    o = o || {};
    const id = o.id || (isFolder ? 'folder-' : 'file-') + (++n);
    const p = parent ? items.get(parent) : null;
    const age = o.ageMin === undefined ? OLD : o.ageMin;
    items.set(id, { id, name, isFolder, parent, size: o.size || 0, trashed: !!o.trashed, explicitlyTrashed: !!o.trashed,
                    updatedAt: t0 - age * MIN, createdAt: t0 - age * MIN,
                    shared: o.shared !== undefined ? o.shared : !!(p && p.shared) });
    return id;
  };
  add(null, 'Photos Shared Drive', true, { id: ROOT, shared: true });
  for (const reg of Object.keys(REGION_IDS)) {
    add(ROOT, reg, true, { id: REGION_IDS[reg], ageMin: 400 * 24 * 60 });
    add(null, PREFIX + reg, true, { id: SOURCE_IDS[reg], shared: false });
  }
  const kids = id => [...items.values()].filter(m => m.parent === id);
  const INTRO = new Set(['toString', 'valueOf', 'toJSON', 'constructor', 'then', 'inspect']);
  const guard = (type, obj) => new Proxy(obj, {
    get(t, k) {
      if (typeof k !== 'string' || INTRO.has(k) || k in t) return t[k];
      return () => { throw new Error('fake ' + type + ' has no ' + k); };
    },
  });
  const iter = list => { let i = 0; return guard('Iterator', { hasNext: () => i < list.length, next: () => list[i++] }); };
  const refuse = what => { banned.push(what); throw new Error('fake: ' + what + ' is not how the mover writes (R5, #132)'); };
  const fileApi = id => {
    const m = () => items.get(id);
    return guard('File', {
      getId: () => id, getName: () => m().name, getSize: () => m().size, getMimeType: () => 'image/jpeg',
      getLastUpdated: () => new Date(m().updatedAt), getDateCreated: () => new Date(m().createdAt), isTrashed: () => m().trashed,
      getParents: () => iter(m().parent ? [folderApi(m().parent)] : []),
      moveTo: () => refuse('File.moveTo'), setTrashed: () => refuse('File.setTrashed'),
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
      setTrashed: () => refuse('Folder.setTrashed'),
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
  const get = id => {
    if (!items.has(id)) throw new Error('File not found: ' + id + ' (fake)');
    return items.get(id);
  };
  const trashAll = (m, v) => {
    m.trashed = v;
    m.explicitlyTrashed = v;
    for (const k of kids(m.id)) { k.trashed = v; k.explicitlyTrashed = false; if (k.isFolder) for (const kk of kids(k.id)) kk.trashed = v; }
  };
  const Files = guard('Drive.Files', {
    list(args) {
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
      const m = get(id);
      if (m.shared && !(args && args.supportsAllDrives === true)) throw new Error('File not found: ' + id + ' (fake: supportsAllDrives)');
      return rep(m);
    },
    create(resource, media, args) {
      creates.push({ resource: JSON.parse(JSON.stringify(resource || {})), args: Object.assign({}, args || {}) });
      const parents = resource && resource.parents;
      if (!resource || resource.mimeType !== FOLDER || !Array.isArray(parents) || parents.length !== 1) {
        throw new Error('fake Files.create: a folder with one parent expected');
      }
      const parent = get(parents[0]);
      if (!parent.isFolder || parent.trashed) throw new Error('fake Files.create: parent not a live folder');
      if (parent.shared && !(args && args.supportsAllDrives === true)) throw new Error('File not found: ' + parent.id + ' (fake: supportsAllDrives)');
      const id = add(parent.id, resource.name, true, { ageMin: 0 });
      return rep(items.get(id));
    },
    update(resource, fileId, media, args) {
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
        const from = m.parent;
        m.parent = dest.id;
        m.shared = dest.shared;
        items.get(from).updatedAt = Date.now();
        dest.updatedAt = Date.now();
      }
      if (resource.trashed === false) trashAll(m, false);
      if (resource.trashed === true) trashAll(m, true);
      return rep(m);
    },
  });
  const props = {};
  for (const reg of Object.keys(REGION_IDS)) {
    const key = reg.toUpperCase();
    props['SOURCE_FOLDER_' + key] = SOURCE_IDS[reg];
    props['TARGET_FOLDER_' + key] = REGION_IDS[reg];
  }
  const say = (...a) => logs.push(a.map(String).join(' '));
  const globals = {
    console: { log: say, info: say, warn: say, error: say },
    DriveApp: guard('DriveApp', {
      getFolderById: id => { const m = get(id); if (!m.isFolder) throw new Error('not a folder (fake)'); return folderApi(id); },
      getFileById: id => { const m = get(id); if (m.isFolder) throw new Error('not a file (fake)'); return fileApi(id); },
    }),
    Drive: guard('Drive', { Files }),
    PropertiesService: guard('PropertiesService', {
      getScriptProperties: () => guard('Properties', { getProperty: k => (Object.prototype.hasOwnProperty.call(props, k) ? props[k] : null) }),
    }),
    LockService: guard('LockService', {
      getScriptLock: () => guard('Lock', { tryLock: () => true, waitLock: () => undefined, releaseLock: () => undefined, hasLock: () => true }),
    }),
    ScriptApp: guard('ScriptApp', { getProjectTriggers: () => [] }),
  };
  /** The folder names from the region (or source) folder down to the item's parent; the Shared Drive's root left out. */
  const where = id => {
    const out = [];
    for (let at = get(id).parent; at && at !== ROOT; at = items.get(at).parent) out.unshift(items.get(at).name);
    return out;
  };
  const fileNamed = nm => [...items.values()].filter(m => !m.isFolder && m.name === nm);
  /** The live folders at that chain of names below the Shared Drive's root (['Africa', partner, month]). */
  const foldersAt = names => {
    let level = [ROOT];
    for (const nm of names) level = [].concat(...level.map(id => kids(id).filter(k => k.isFolder && !k.trashed && k.name === nm).map(k => k.id)));
    return level;
  };
  return { add, items, logs, creates, updates, banned, globals, where, fileNamed, foldersAt, kids,
           snapshot: () => JSON.stringify([...items.values()].map(m => [m.id, m.name, m.parent, m.trashed, m.shared])) };
}

function runMover(env, entry) {
  let threw = '';
  const before = env.logs.length;
  try {
    const c = loadGs.sandbox(GS, env.globals);
    vm.runInContext(entry + '();', c, { timeout: 20000 });
  } catch (e) { threw = String(e && e.message || e); }
  return { threw, text: env.logs.slice(before).join('\n') };
}

const A1 = 'Fixture Partner Alpha | Bright Stars | 10-30-2026 | 4';
const A2 = 'Fixture Partner Alpha | Golden Wings | 10-02-2026 | 1';
const A3 = 'Fixture Partner Alpha | Silver Roots | 11-02-2026 | ';     // special event, blank week
const B1 = 'Fixture Partner Beta | Morning Voices | 01-15-2027';        // special event, no week segment
const LEGACY = 'Evening Lights 10-29-2026';
const NOPARTNER = ' | Rising Flames | 10-30-2026 | 2';
const BADDATE = 'Fixture Partner Gamma - North | River Stars | 13-40-2026 | 3';
const ASIA1 = 'Fixture Partner Alpha | Ocean Lights | 10-30-2026 | 5';
// [region, subfolder name, its photos, where they must end up (below the Shared Drive's root)]
const LAYOUT_A = [
  ['Africa', A1, ['IMG_1001.jpg', 'IMG_1002.jpg'], ['Africa', 'Fixture Partner Alpha', '2026-10', A1]],
  ['Africa', A2, ['IMG_1003.jpg'], ['Africa', 'Fixture Partner Alpha', '2026-10', A2]],
  ['Africa', A3, ['IMG_1004.jpg'], ['Africa', 'Fixture Partner Alpha', '2026-11', A3]],
  ['Africa', B1, ['IMG_1005.jpg', 'IMG_1006.jpg'], ['Africa', 'Fixture Partner Beta', '2027-01', B1]],
  ['Africa', LEGACY, ['IMG_1007.jpg'], ['Africa', LEGACY]],
  ['Africa', NOPARTNER, ['IMG_1008.jpg'], ['Africa', NOPARTNER]],
  ['Africa', BADDATE, ['IMG_1009.jpg'], ['Africa', BADDATE]],
  ['Asia', ASIA1, ['IMG_1010.jpg'], ['Asia', 'Fixture Partner Alpha', '2026-10', ASIA1]],
];
function seed(env, rows) {
  let k = 0;
  for (const [region, name, photos] of rows) {
    const s = env.add(SOURCE_IDS[region], name, true);
    for (const p of photos) env.add(s, p, false, { size: 1000 + (++k) });
  }
}
const writesOk = env => env.creates.every(c => c.args.supportsAllDrives === true && c.resource.mimeType === FOLDER) && !env.banned.length;

console.log('\nmoveSettledPhotos — files land in <Region>/<Partner>/<YYYY-MM>/<name>, folders made once (R5)');
{
  const env = fakeDrive();
  seed(env, LAYOUT_A);
  const r = runMover(env, 'moveSettledPhotos');
  check('the real run ends without an error', !r.threw, r.threw);
  for (const [region, name, photos, want] of LAYOUT_A) {
    const got = photos.map(p => env.fileNamed(p).map(m => env.where(m.id)));
    check(region + ' ' + JSON.stringify(name) + ': its photos in ' + want.join(' / '),
          got.every(g => g.length === 1 && same(g[0], want)), JSON.stringify(got));
  }
  const counts = {
    'Africa/Fixture Partner Alpha': env.foldersAt(['Africa', 'Fixture Partner Alpha']).length,
    'Africa/Fixture Partner Alpha/2026-10': env.foldersAt(['Africa', 'Fixture Partner Alpha', '2026-10']).length,
    'Africa/Fixture Partner Alpha/2026-11': env.foldersAt(['Africa', 'Fixture Partner Alpha', '2026-11']).length,
    'Africa/Fixture Partner Beta/2027-01': env.foldersAt(['Africa', 'Fixture Partner Beta', '2027-01']).length,
    'Asia/Fixture Partner Alpha/2026-10': env.foldersAt(['Asia', 'Fixture Partner Alpha', '2026-10']).length,
  };
  check('each partner and month folder made once, in its own region (two subfolders share Alpha/2026-10)',
        Object.values(counts).every(v => v === 1), JSON.stringify(counts));
  // 8 subfolders + Africa: Alpha, 2026-10, 2026-11, Beta, 2027-01 + Asia: Alpha, 2026-10
  check('15 folders made in all, each by Drive.Files.create with supportsAllDrives; nothing by DriveApp, nothing renamed (T6)',
        env.creates.length === 15 && writesOk(env), env.creates.length + ' made; ' + env.banned.join(', '));
  check('the log names no photo', !/IMG_\d+/.test(r.text), (r.text.match(/IMG_\d+/) || [''])[0]);

  // the next run (a new execution): a new subfolder of the same partner and month finds those folders on the Drive
  const A4 = 'Fixture Partner Alpha | Rising Stars | 10-15-2026 | 2';
  seed(env, [['Africa', A4, ['IMG_1011.jpg']]]);
  const made = env.creates.length;
  const r2 = runMover(env, 'moveSettledPhotos');
  const got = env.fileNamed('IMG_1011.jpg').map(m => env.where(m.id));
  check('the next run files a new subfolder under the partner and month folders already there',
        !r2.threw && got.length === 1 && same(got[0], ['Africa', 'Fixture Partner Alpha', '2026-10', A4]) &&
        env.foldersAt(['Africa', 'Fixture Partner Alpha']).length === 1 &&
        env.foldersAt(['Africa', 'Fixture Partner Alpha', '2026-10']).length === 1 && env.creates.length === made + 1,
        r2.threw || JSON.stringify(got) + ', ' + (env.creates.length - made) + ' made');
}

console.log('\nmoveSettledPhotos — reuses partner and month folders, merges into a nested folder (R4, R5, T3)');
{
  const env = fakeDrive();
  const P1 = env.add(REGION_IDS.Africa, 'Fixture Partner Alpha', true);
  const M1 = env.add(P1, '2026-10', true);
  const N1 = env.add(M1, A1, true);
  env.add(N1, 'IMG_2001.jpg', false, { size: 2048 });
  const P2 = env.add(REGION_IDS.Africa, 'Fixture Partner Beta', true);
  const R1 = env.add(REGION_IDS.Africa, A2, true);   // a layout name filed at the root before #225
  env.add(R1, 'IMG_2100.jpg', false, { size: 500 });
  const DEAD = env.add(REGION_IDS.Africa, 'Fixture Partner Delta', true, { trashed: true });
  const P4 = env.add(REGION_IDS.Africa, 'Fixture Partner Delta', true);
  const D1 = 'Fixture Partner Delta | Valley Wings | 10-30-2026 | 2';
  const B2 = 'Fixture Partner Beta | Bright Roots | 12-05-2026 | 9';
  const s1 = env.add(SOURCE_IDS.Africa, A1, true);
  env.add(s1, 'IMG_2001.jpg', false, { size: 2048 });   // same name and size as the one there: kept
  env.add(s1, 'IMG_2002.jpg', false, { size: 2049 });
  const s2 = env.add(SOURCE_IDS.Africa, A2, true);
  env.add(s2, 'IMG_2101.jpg', false, { size: 501 });
  seed(env, [['Africa', B2, ['IMG_2201.jpg']], ['Africa', D1, ['IMG_2301.jpg']]]);
  const r = runMover(env, 'moveSettledPhotos');
  check('the real run ends without an error', !r.threw, r.threw);
  const loc = nm => env.fileNamed(nm).map(m => env.where(m.id));
  check('merge: the new photo joins the existing Alpha/2026-10 folder of its name; no second folder of that name',
        same(loc('IMG_2002.jpg'), [['Africa', 'Fixture Partner Alpha', '2026-10', A1]]) &&
        env.kids(M1).filter(k => k.isFolder && k.name === A1).length === 1, JSON.stringify(loc('IMG_2002.jpg')));
  check('merge: the photo already there (same name and size) stays in My Drive',
        same(loc('IMG_2001.jpg').sort(), [['Africa', 'Fixture Partner Alpha', '2026-10', A1], [PREFIX + 'Africa', A1]].sort()),
        JSON.stringify(loc('IMG_2001.jpg')));
  check('the same name at the region root does not count: a new folder under Alpha/2026-10; the root one untouched',
        same(loc('IMG_2101.jpg'), [['Africa', 'Fixture Partner Alpha', '2026-10', A2]]) &&
        same(env.kids(R1).map(k => k.name), ['IMG_2100.jpg']), JSON.stringify(loc('IMG_2101.jpg')));
  check('an existing partner folder is reused, its month folder made in it',
        same(loc('IMG_2201.jpg'), [['Africa', 'Fixture Partner Beta', '2026-12', B2]]) &&
        env.foldersAt(['Africa', 'Fixture Partner Beta']).length === 1 && env.kids(P2).length === 1, JSON.stringify(loc('IMG_2201.jpg')));
  check('a partner folder in the trash neither counts nor is used: the live one is (T3)',
        same(loc('IMG_2301.jpg'), [['Africa', 'Fixture Partner Delta', '2026-10', D1]]) && env.kids(DEAD).length === 0 &&
        env.kids(P4).length === 1, JSON.stringify(loc('IMG_2301.jpg')));
  const made = env.creates.map(c => c.resource.name).sort();
  const want = [A2, B2, D1, '2026-10', '2026-12'].sort();
  check('only the missing folders are made: ' + want.length, same(made, want) && writesOk(env), show(made, want));
}

console.log('\nmoveSettledPhotos — two partner (or month) folders of one name: refused, logged, nothing moved (R5, T4)');
{
  const env = fakeDrive();
  env.add(REGION_IDS.Africa, 'Fixture Partner Gamma - North', true);
  env.add(REGION_IDS.Africa, 'Fixture Partner Gamma - North', true);
  const PA = env.add(REGION_IDS.Africa, 'Fixture Partner Alpha', true);
  env.add(PA, '2026-10', true);
  env.add(PA, '2026-10', true);
  const G1 = 'Fixture Partner Gamma - North | Mountain Stars | 10-30-2026 | 1';
  const B3 = 'Fixture Partner Beta | Golden Lights | 10-30-2026 | 2';
  seed(env, [['Africa', G1, ['IMG_3001.jpg']], ['Africa', A1, ['IMG_3002.jpg']], ['Africa', B3, ['IMG_3003.jpg']]]);
  const r = runMover(env, 'moveSettledPhotos');
  const loc = nm => env.fileNamed(nm).map(m => env.where(m.id));
  check('two partner folders of its name: the photo stays in My Drive, no folder made for it',
        same(loc('IMG_3001.jpg'), [[PREFIX + 'Africa', G1]]) && !env.creates.some(c => c.resource.name === G1),
        JSON.stringify(loc('IMG_3001.jpg')));
  check('two month folders of its name under its partner: the photo stays in My Drive, no folder made for it',
        same(loc('IMG_3002.jpg'), [[PREFIX + 'Africa', A1]]) && !env.creates.some(c => c.resource.name === A1),
        JSON.stringify(loc('IMG_3002.jpg')));
  const lines = r.text.split('\n').filter(l => /refus/i.test(l));
  check('each refusal is logged, naming the partner',
        lines.some(l => l.includes('Fixture Partner Gamma - North')) && lines.some(l => l.includes('Fixture Partner Alpha')),
        JSON.stringify(lines));
  check('the rest of the run goes on: another partner\'s subfolder is filed',
        same(loc('IMG_3003.jpg'), [['Africa', 'Fixture Partner Beta', '2026-10', B3]]) && writesOk(env),
        JSON.stringify(loc('IMG_3003.jpg')) + ' ' + env.banned.join(', '));
}

console.log('\npreviewMoves — makes nothing, logs the target path (R5, T2)');
{
  const env = fakeDrive();
  seed(env, LAYOUT_A);
  const before = env.snapshot();
  const r = runMover(env, 'previewMoves');
  check('the dry run ends without an error', !r.threw, r.threw);
  check('nothing made, moved or trashed: no Files.create, no Files.update, the Drive as it was',
        !env.creates.length && !env.updates.length && !env.banned.length && env.snapshot() === before,
        env.creates.length + ' create(s), ' + env.updates.length + ' update(s) ' + env.banned.join(', '));
  const lines = r.text.split('\n');
  for (const [, name, , want] of LAYOUT_A.filter(x => x[3].length === 4)) {
    const tail = want[1] + '/' + want[2];
    check('a line names ' + JSON.stringify(name) + ' and its target ' + tail, lines.some(l => l.includes(name) && l.includes(tail)),
          lines.filter(l => l.includes(name)).join(' || ') || 'no line names it');
  }
}

finish();
