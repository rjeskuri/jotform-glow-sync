#!/usr/bin/env node
'use strict';
/**
 * Offline tests for drive-sync/ (ticket #89): the standalone Apps Script project that moves
 * Jotform's photo subfolders from Ryan's My Drive (`Attendance photos - <Region>`) into the
 * matching region folder on the company Shared Drive. The PURE planning function is tested in
 * depth; the entry points are run once against fake Drive services (no Google API) to prove
 * what they may call; the real Drive is exercised by the dry run on Ryan's account (RUNBOOK).
 *
 * The contract (drive-sync/*.gs, loaded together in a vm sandbox like appsscript/):
 *
 *   planMoves_(sourceFolders, targetFolders, now, settleMinutes)
 *     -> {moves, merges, waiting, unknown, refused}
 *
 *   sourceFolders  [{id, name, subfolders: [{id, name, files: [{id, name, size, updated: Date}]}]}]
 *                  the folders of Ryan's My Drive; only `Attendance photos - <Region>` counts,
 *                  with the prefix exactly so (case and spacing included)
 *   targetFolders  {<Region>: {id, subfolders: [{id, name, files: [{id, name, size}]}]}}
 *                  the Shared Drive's region folders (ids from Script Properties), by region
 *   now            a Date;  settleMinutes  a number
 *
 *   moves    [{region, id, name, to, files}]  a subfolder (id) whose name is not yet in the region
 *            folder (to): `files` are ALL its files (each entry a file id, or the file object with
 *            its id). The mover makes a folder of that name in `to` and moves them into it (#132:
 *            Drive cannot move a My Drive folder into a Shared Drive; the emptied subfolder stays)
 *   merges   [{region, id, name, into, files, kept}]
 *            a subfolder whose name already exists ONCE in the region folder (into = that
 *            folder's id): `files` are the source files to move into it, `kept` the source
 *            files left where they are because a file of the same name AND the same size is
 *            already there (each entry a file id, or the file object with its id)
 *   waiting  [{region, id, name}]          its newest file changed less than settleMinutes ago;
 *            or another settled subfolder of the SAME name in the same region is moved or
 *            merged this run (one per name per run: never two same-name folders created)
 *   refused  [{region, id, name}]          settled, but the region folder holds two or more
 *            subfolders of that name: the mover does not pick one
 *   unknown  [{id, name}]                  an `Attendance photos - …` folder whose region is not
 *            exactly one of Africa, Asia, Latin America, U.S, Template, or has no target
 *            (an own key of targetFolders): left alone, reported
 *
 * A subfolder with no files is never moved or merged. Any other folder is in no list. The
 * planner touches no Google service and does not change its inputs (the dry run's plan).
 *
 * The entry points (top-level functions whose names do not end in `_`) are run with fake
 * DriveApp / Drive / ScriptApp / PropertiesService / LockService objects: with fictional ids
 * in Script Properties they may call only the methods in ALLOW below (reading, the trigger
 * builder, and on the apply path the advanced Drive service's Files.create / Files.update with
 * supportsAllDrives: true - never DriveApp's moveTo, which Drive refuses into a Shared Drive
 * (#132); never sharing, links, copies, trash or mail); with no Script Properties at all they
 * make no *ById call and change nothing.
 *
 * Every club name is fictional (test/fixtures/make_fixture.py's word lists).
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { execFileSync } = require('child_process');
const loadGs = require('./load_gs');
const { check, finish } = require('./helpers/js/check');

const REPO = path.join(__dirname, '..');
const DIR = path.join(REPO, 'drive-sync');
const MIN = 60 * 1000;
const REGIONS = ['Africa', 'Asia', 'Latin America', 'U.S', 'Template'];
const PREFIX = 'Attendance photos - ';
const DRIVE_SCOPE = 'https://www.googleapis.com/auth/drive';
const TRIGGER_SCOPE = 'https://www.googleapis.com/auth/script.scriptapp';

const exists = fs.existsSync(DIR) && fs.statSync(DIR).isDirectory();
const GS = exists ? fs.readdirSync(DIR).filter(f => f.endsWith('.gs')).sort().map(f => path.join(DIR, f)) : [];
const GS_SRC = GS.map(f => fs.readFileSync(f, 'utf8')).join('\n');

// Google services: touching any of them from the planner (or at load time) is a side effect
const touched = [];
const trap = name => new Proxy({}, {
  get(_, k) { touched.push(name + '.' + String(k)); throw new Error(name + ' touched by the planner'); },
});
const SERVICES = ['DriveApp', 'Drive', 'PropertiesService', 'ScriptApp', 'MailApp', 'GmailApp',
                  'UrlFetchApp', 'LockService', 'CacheService', 'SpreadsheetApp', 'Session'];
const trapped = {};
for (const s of SERVICES) trapped[s] = trap(s);

console.log('drive-sync/ — the project loads, and defines the planner');
let ctx = null, loadError = '';
try {
  if (GS.length) ctx = loadGs.sandbox(GS, trapped);
} catch (e) { loadError = e.message; }
check('drive-sync/ exists with .gs files', GS.length > 0,
      exists ? GS.map(f => path.basename(f)).join(', ') : 'no drive-sync/ directory');
check('the .gs files load together with no Google service touched at load time',
      !!ctx && !loadError && !touched.length, loadError || touched.join(', '));
const planMoves = ctx && typeof ctx.planMoves_ === 'function' ? ctx.planMoves_ : null;
check('planMoves_ is a top-level function', !!planMoves, ctx ? typeof ctx.planMoves_ : 'not loaded');

// inputs are built in the sandbox's realm (its Date), as Apps Script would hand them over
const revive = ctx ? vm.runInContext(
  '(function (s) { return JSON.parse(s, function (k, v) { return k === "updated" ? new Date(v) : v; }); })', ctx)
  : null;
const CtxDate = ctx ? vm.runInContext('Date', ctx) : Date;

/** planMoves_ on plain inputs (times as ms); null and a message when it throws. */
function plan(sources, targets, nowMs, settle) {
  if (!planMoves) return { plan: null, error: 'planMoves_ is not defined' };
  try {
    return { plan: planMoves(revive(JSON.stringify(sources)), revive(JSON.stringify(targets)),
                             new CtxDate(nowMs), settle), error: '' };
  } catch (e) { return { plan: null, error: e && e.message || String(e) }; }
}

const fid = f => (f && typeof f === 'object' ? f.id : f);
const list = (p, k) => (p && Array.isArray(p[k]) ? p[k] : []);
/** The plan as sorted strings, so order does not matter. */
function norm(p) {
  return {
    moves: list(p, 'moves').map(m => [m.region, m.id, m.name, m.to, (m.files || []).map(fid).sort().join(',')].join('|')).sort(),
    merges: list(p, 'merges').map(m => [m.region, m.id, m.name, m.into,
                                        (m.files || []).map(fid).sort().join(','),
                                        (m.kept || []).map(fid).sort().join(',')].join('|')).sort(),
    waiting: list(p, 'waiting').map(w => [w.region, w.id, w.name].join('|')).sort(),
    refused: list(p, 'refused').map(w => [w.region, w.id, w.name].join('|')).sort(),
    unknown: list(p, 'unknown').map(u => u.id).sort(),
  };
}
const KEYS = ['moves', 'merges', 'waiting', 'refused', 'unknown'];
const ids = p => new Set([].concat(...KEYS.map(k => list(p, k))).map(e => e && e.id));
const acted = p => list(p, 'moves').concat(list(p, 'merges'));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const show = (a, b) => 'got ' + JSON.stringify(a) + ' want ' + JSON.stringify(b);
const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);

// ---------------------------------------------------------------- broad: a generated table
console.log('\nplanMoves_ — generated My Drive / Shared Drive layouts against an independent oracle');

function prng(seed) {   // mulberry32
  return function () {
    seed |= 0; seed = seed + 0x6D2B79F5 | 0;
    let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}
const WORDS = ['Bright', 'Rising', 'Golden', 'Silver', 'Morning', 'Evening'];
const NOUNS = ['Stars', 'Lights', 'Flames', 'Voices', 'Wings', 'Roots'];
const OLD = 600;   // minutes: settled under any settle time used here

function layout(seed, nowMs, settle) {
  const r = prng(seed);
  const pick = a => a[Math.floor(r() * a.length)];
  const slug = s => s.toLowerCase().replace(/[^a-z]+/g, '');
  const sources = [], targets = {};
  let n = 0;
  const id = p => p + seed + '-' + (++n);
  for (const region of REGIONS) {
    const hasTarget = r() < 0.75;
    const tgt = { id: 'tgt-' + seed + '-' + slug(region), subfolders: [] };
    if (hasTarget) targets[region] = tgt;
    const src = { id: id('src'), name: PREFIX + region, subfolders: [] };
    const used = new Set();
    const count = 3 + Math.floor(r() * 5);
    for (let i = 0; i < count; i++) {
      let name;
      do { name = pick(WORDS) + ' ' + pick(NOUNS) + ' 2026-10-' + String(1 + Math.floor(r() * 28)).padStart(2, '0'); }
      while (used.has(name));
      used.add(name);
      const files = [];
      const nf = r() < 0.15 ? 0 : 1 + Math.floor(r() * 4);
      for (let j = 0; j < nf; j++) {
        // ages straddle the settle time: 0 .. settle*4 minutes, to the second
        const ageMs = Math.round(r() * settle * 4 * 60) * 1000;
        files.push({ id: id('f'), name: 'IMG_' + (100 + j) + '.jpg', size: 10000 + Math.floor(r() * 90000),
                     updated: nowMs - ageMs });
      }
      src.subfolders.push({ id: id('sub'), name, files });
      if (r() < 0.45) {   // a resubmission: the same subfolder name is already on the Shared Drive
        const tfiles = [];
        for (const f of files) {
          const roll = r();
          if (roll < 0.35) tfiles.push({ id: id('t'), name: f.name, size: f.size });            // identical
          else if (roll < 0.6) tfiles.push({ id: id('t'), name: f.name, size: f.size + 1 + Math.floor(r() * 500) });
          else if (roll < 0.85) tfiles.push({ id: id('t'), name: 'IMG_8' + j3(r) + '.jpg', size: f.size });   // same size, other name
        }
        tfiles.push({ id: id('t'), name: 'IMG_9' + Math.floor(r() * 10) + '.jpg', size: 5000 });
        tgt.subfolders.push({ id: id('tsub'), name, files: tfiles });
        if (r() < 0.2) tgt.subfolders.push({ id: id('tsub'), name, files: [] });   // the name twice there
      }
    }
    // a Shared Drive subfolder with no counterpart in My Drive
    tgt.subfolders.push({ id: id('tsub'), name: 'Golden Roots 2026-09-30', files: [{ id: id('t'), name: 'IMG_100.jpg', size: 1 }] });
    sources.push(src);
  }
  // targets for regions that are not regions
  if (r() < 0.6) targets.Europe = { id: 'tgt-' + seed + '-europe', subfolders: [] };
  if (r() < 0.6) targets['U.S '] = { id: 'tgt-' + seed + '-us-space', subfolders: [] };
  // unknown regions, and folders that are none of the mover's business
  for (const name of [PREFIX + 'Europe', PREFIX + 'U.S ', PREFIX + 'constructor', PREFIX + 'toString',
                      PREFIX + '__proto__', PREFIX + 'africa',
                      'Attendance photos', 'Receipts - Africa', 'Old ' + PREFIX + 'Asia',
                      'attendance photos - Africa', 'Attendance Photos - Asia', 'Attendance  photos - Africa',
                      'Attendance photos  - Asia', 'Attendance photos -Africa']) {
    sources.push({ id: id('src'), name, subfolders: [
      { id: id('sub'), name: 'Silver Wings 2026-10-02', files: [{ id: id('f'), name: 'IMG_100.jpg', size: 2000, updated: nowMs - OLD * MIN }] },
    ] });
  }
  return { sources, targets };
}
function j3(r) { return String(Math.floor(r() * 1000)).padStart(3, '0'); }

/** What the plan must be, worked out from the rules alone. */
function oracle(sources, targets, nowMs, settle) {
  const out = { moves: [], merges: [], waiting: [], refused: [], unknown: [] }, empty = [], ignored = [];
  for (const s of sources) {
    if (!s.name.startsWith(PREFIX)) { ignored.push(s.id); s.subfolders.forEach(x => ignored.push(x.id)); continue; }
    const region = s.name.slice(PREFIX.length);
    const tgt = REGIONS.includes(region) && own(targets, region) ? targets[region] : undefined;
    if (!tgt) { out.unknown.push(s.id); s.subfolders.forEach(x => ignored.push(x.id)); continue; }
    for (const sf of s.subfolders) {
      const key = [region, sf.id, sf.name];
      if (!sf.files.length) { empty.push(sf.id); continue; }
      const newest = Math.max(...sf.files.map(f => f.updated));
      if (nowMs - newest < settle * MIN) { out.waiting.push(key.join('|')); continue; }
      const there = tgt.subfolders.filter(t => t.name === sf.name);
      if (there.length > 1) { out.refused.push(key.join('|')); continue; }
      if (!there.length) { out.moves.push(key.concat(tgt.id, sf.files.map(f => f.id).sort().join(',')).join('|')); continue; }
      const dup = f => there[0].files.some(t => t.name === f.name && t.size === f.size);
      out.merges.push(key.concat(there[0].id, sf.files.filter(f => !dup(f)).map(f => f.id).sort().join(','),
                                 sf.files.filter(dup).map(f => f.id).sort().join(',')).join('|'));
    }
  }
  for (const k of Object.keys(out)) out[k].sort();
  return { want: out, empty, ignored };
}

const NOWS = [Date.UTC(2027, 2, 5, 8, 0, 0), Date.UTC(2025, 11, 31, 23, 30, 0), Date.UTC(2026, 9, 21, 14, 7, 30)];
const SETTLES = [10, 15, 3];
const seen = { moves: 0, merges: 0, waiting: 0, refused: 0, unknown: 0, kept: 0, sameSizeMoved: 0, empty: 0, multiFileMoves: 0 };
let runs = 0;
for (let seed = 1; seed <= 8; seed++) {
  for (let k = 0; k < NOWS.length; k++) {
    const nowMs = NOWS[k], settle = SETTLES[(seed + k) % SETTLES.length];
    const { sources, targets } = layout(seed, nowMs, settle);
    const { want, empty, ignored } = oracle(sources, targets, nowMs, settle);
    for (const key of KEYS) seen[key] += want[key].length;
    seen.kept += want.merges.filter(m => m.split('|')[5]).length;
    seen.multiFileMoves += want.moves.filter(m => m.split('|')[4].includes(',')).length;   // a move of 2+ files
    seen.empty += empty.length;
    // a moved file that has a same-size, other-name file in the target folder
    for (const s of sources) for (const sf of s.subfolders) {
      const region = s.name.slice(PREFIX.length);
      const t = own(targets, region) && REGIONS.includes(region) ? targets[region].subfolders.filter(x => x.name === sf.name) : [];
      if (t.length === 1 && want.merges.some(m => m.split('|')[1] === sf.id)) {
        seen.sameSizeMoved += sf.files.filter(f => t[0].files.some(x => x.size === f.size && x.name !== f.name) &&
                                                   !t[0].files.some(x => x.size === f.size && x.name === f.name)).length;
      }
    }
    const { plan: p, error } = plan(sources, targets, nowMs, settle);
    runs++;
    const got = norm(p);
    got.waiting = got.waiting.filter(w => !empty.includes(w.split('|')[1]));   // an empty one may wait
    const label = 'seed ' + seed + ', now ' + new Date(nowMs).toISOString() + ', settle ' + settle + 'm';
    check(label + ': moves (each with all its files), merges, waiting, refused and unknown are the rules\' answer',
          !error && same(got, want), error || (same(got, want) ? '' : show(got, want)));
    const all = ids(p);
    const wrong = empty.filter(x => acted(p).some(e => e.id === x)).concat(ignored.filter(x => all.has(x)));
    check(label + ': no empty subfolder moved; nothing outside a known region\'s folder planned',
          !error && !wrong.length, error || wrong.join(', '));
  }
}
check('the table covers every outcome (' + runs + ' layouts)',
      Object.values(seen).every(v => v > 0), JSON.stringify(seen));

// ---------------------------------------------------------------- specific cases
const NOW = Date.UTC(2027, 0, 12, 9, 0, 0);
const file = (id, name, size, ageMin) => ({ id, name, size, updated: NOW - ageMin * MIN });
const target = (region, subfolders) => ({ [region]: { id: 'tgt-' + region.toLowerCase().replace(/[^a-z]+/g, ''), subfolders: subfolders || [] } });

console.log('\nplanMoves_ — the settle time');
{
  const sources = [{ id: 'src-af', name: 'Attendance photos - Africa', subfolders: [
    { id: 'a', name: 'Bright Stars 2026-10-14', files: [file('a1', 'IMG_100.jpg', 2100, 10 - 1 / 60)] },   // 9m59s
    { id: 'b', name: 'Rising Lights 2026-10-14', files: [file('b1', 'IMG_100.jpg', 2200, 10)] },           // exactly 10m
    { id: 'c', name: 'Golden Flames 2026-10-13', files: [file('c1', 'IMG_100.jpg', 2300, 25)] },
    { id: 'd', name: 'Silver Voices 2026-10-13', files: [file('d1', 'IMG_100.jpg', 2400, 300), file('d2', 'IMG_101.jpg', 2500, 2)] },
  ] }];
  const nm = Object.fromEntries(sources[0].subfolders.map(s => [s.id, s.name]));
  const tg = target('Africa');
  const r10 = plan(sources, tg, NOW, 10);
  const n10 = norm(r10.plan);
  check('settle 10: 9m59s waits, exactly 10m moves, 25m moves (with their names)',
        same(n10.waiting, ['Africa|a|' + nm.a, 'Africa|d|' + nm.d]) &&
        same(n10.moves, ['Africa|b|' + nm.b + '|tgt-africa|b1', 'Africa|c|' + nm.c + '|tgt-africa|c1']),
        r10.error || JSON.stringify(n10));
  check('the NEWEST file decides: a 5-hour-old photo beside a 2-minute-old one waits',
        n10.waiting.includes('Africa|d|' + nm.d) && !acted(r10.plan).some(m => m.id === 'd'), r10.error || JSON.stringify(n10));
  const r30 = plan(sources, tg, NOW, 30);
  check('settle 30: the 25-minute-old subfolder waits too',
        same(norm(r30.plan).waiting.map(w => w.split('|')[1]), ['a', 'b', 'c', 'd']), r30.error || JSON.stringify(norm(r30.plan)));
  const r0 = plan(sources, tg, NOW + 60 * MIN, 10);
  check('an hour later, everything moves (age is counted from `now`, not the clock)',
        norm(r0.plan).moves.length === 4 && !norm(r0.plan).waiting.length, r0.error || JSON.stringify(norm(r0.plan)));
}

console.log('\nplanMoves_ — region from the folder name');
{
  const sources = REGIONS.map((reg, i) => ({ id: 'src-' + i, name: PREFIX + reg, subfolders: [
    { id: 'sub-' + i, name: WORDS[i] + ' ' + NOUNS[i] + ' 2026-10-0' + (i + 1), files: [file('f-' + i, 'IMG_100.jpg', 3000 + i, 60)] },
  ] }));
  const targets = Object.assign({}, ...REGIONS.map(reg => target(reg)));
  const r = plan(sources, targets, NOW, 10);
  const want = REGIONS.map((reg, i) => [reg, 'sub-' + i, sources[i].subfolders[0].name, targets[reg].id, 'f-' + i].join('|')).sort();
  check('Africa, Asia, Latin America, U.S, Template: each subfolder to its own region\'s folder',
        same(norm(r.plan).moves, want), r.error || show(norm(r.plan).moves, want));
  // the regions swapped round: the answer follows the names, not the order
  const reg2 = i => REGIONS[(i + 2) % REGIONS.length];
  const swapped = sources.map((s, i) => Object.assign({}, s, { name: PREFIX + reg2(i) }));
  const r2 = plan(swapped, targets, NOW, 10);
  const want2 = REGIONS.map((_, i) => [reg2(i), 'sub-' + i, sources[i].subfolders[0].name, targets[reg2(i)].id, 'f-' + i].join('|')).sort();
  check('folders renamed to other regions: the targets follow the names', same(norm(r2.plan).moves, want2),
        r2.error || show(norm(r2.plan).moves, want2));
  // targets keyed by things that are not regions, and region names that are object built-ins
  const odd = ['Europe', 'U.S ', ' Asia', 'asia', 'constructor', 'toString', '__proto__', 'hasOwnProperty', 'valueOf']
    .map((reg, i) => ({ id: 'odd-' + i, name: PREFIX + reg, subfolders: [
      { id: 'odd-sub-' + i, name: 'Evening Stars 2026-10-0' + (i + 1), files: [file('odd-f-' + i, 'IMG_100.jpg', 4000 + i, 90)] }] }));
  const oddTargets = Object.assign(target('Asia'), { Europe: { id: 'tgt-europe', subfolders: [] },
                                                     'U.S ': { id: 'tgt-us-space', subfolders: [] },
                                                     asia: { id: 'tgt-asia-lower', subfolders: [] } });
  const r3 = plan(odd, oddTargets, NOW, 10);
  check('`Europe`, `U.S ` (trailing space), ` Asia`, `asia` and constructor/toString/__proto__…: all unknown, nothing moved, no crash',
        !r3.error && same(norm(r3.plan).unknown, odd.map(s => s.id).sort()) &&
        !acted(r3.plan).length && !list(r3.plan, 'waiting').length && !list(r3.plan, 'refused').length,
        r3.error || JSON.stringify(norm(r3.plan)));
}

console.log('\nplanMoves_ — a resubmission is merged file by file, never overwritten');
{
  const name = 'Morning Wings 2026-10-15';
  const sources = [{ id: 'src-as', name: 'Attendance photos - Asia', subfolders: [
    { id: 'resub', name, files: [file('s-same', 'IMG_100.jpg', 48211, 40), file('s-bigger', 'IMG_101.jpg', 51007, 40),
                                 file('s-new', 'IMG_102.jpg', 39990, 40)] },
    { id: 'fresh', name: 'Evening Roots 2026-10-15', files: [file('s-fr', 'IMG_100.jpg', 48211, 40)] },
  ] }];
  const targets = { Asia: { id: 'tgt-asia', subfolders: [
    { id: 'existing', name, files: [{ id: 't-same', name: 'IMG_100.jpg', size: 48211 }, { id: 't-smaller', name: 'IMG_101.jpg', size: 50007 },
                                    { id: 't-samesize', name: 'IMG_200.jpg', size: 39990 }, { id: 't-alsosize', name: 'IMG_201.jpg', size: 51007 }] },
  ] }, Africa: { id: 'tgt-africa', subfolders: [{ id: 'af-same-name', name: 'Evening Roots 2026-10-15', files: [] }] } };
  const r = plan(sources, targets, NOW, 10);
  const m = list(r.plan, 'merges').find(x => x.id === 'resub');
  check('the same subfolder name on the Shared Drive: a merge into that folder, not a move',
        !!m && m.into === 'existing' && m.region === 'Asia' && m.name === name && !list(r.plan, 'moves').some(x => x.id === 'resub'),
        r.error || JSON.stringify(r.plan));
  check('same name and size: kept (reported), not moved', !!m && same((m.kept || []).map(fid), ['s-same']) &&
        !(m.files || []).map(fid).includes('s-same'), JSON.stringify(m));
  check('same name with another size, and same size with another name: both moved in beside what is there',
        !!m && same((m.files || []).map(fid).sort(), ['s-bigger', 's-new']), JSON.stringify(m));
  const planned = JSON.stringify(r.plan || {});
  check('the Shared Drive\'s own files appear nowhere in the plan (nothing there is replaced)',
        !!r.plan && !/t-same|t-smaller|t-samesize|t-alsosize/.test(planned), planned);
  check('a name that exists only in ANOTHER region\'s folder is a plain move',
        same(norm(r.plan).moves, ['Asia|fresh|Evening Roots 2026-10-15|tgt-asia|s-fr']), r.error || JSON.stringify(norm(r.plan)));
  const early = plan(sources, targets, NOW - 35 * MIN, 10);
  check('a resubmission still uploading waits (named); it is not merged half-way',
        norm(early.plan).waiting.includes('Asia|resub|' + name) && !list(early.plan, 'merges').length,
        early.error || JSON.stringify(norm(early.plan)));
}

console.log('\nplanMoves_ — the same name twice');
{
  const name = 'Bright Stars 2026-10-14';
  const two = order => [{ id: 'src-af', name: 'Attendance photos - Africa', subfolders: order.map(x => (
    { id: x, name, files: [file(x + '-f', 'IMG_100.jpg', x === 'dupA' ? 1111 : 2222, 120)] })) }];
  for (const order of [['dupA', 'dupB'], ['dupB', 'dupA']]) {
    const r = plan(two(order), target('Africa'), NOW, 10);
    const mv = list(r.plan, 'moves'), wt = norm(r.plan).waiting;
    check('two settled same-name subfolders in My Drive (' + order.join(', ') + '), none on the Shared Drive: ' +
          'one moves, the other waits (never two same-name folders there)',
          mv.length === 1 && order.includes(mv[0].id) && same(wt, ['Africa|' + order.find(x => x !== mv[0].id) + '|' + name]) &&
          !list(r.plan, 'merges').length, r.error || JSON.stringify(norm(r.plan)));
    const tg = target('Africa', [{ id: 'there', name, files: [] }]);
    const r2 = plan(two(order), tg, NOW, 10);
    const mg = list(r2.plan, 'merges');
    check('…and with the name already there: one merges into it, the other waits',
          mg.length === 1 && mg[0].into === 'there' && order.includes(mg[0].id) && !list(r2.plan, 'moves').length &&
          same(norm(r2.plan).waiting, ['Africa|' + order.find(x => x !== mg[0].id) + '|' + name]),
          r2.error || JSON.stringify(norm(r2.plan)));
  }
  const sources = [{ id: 'src-as', name: 'Attendance photos - Asia', subfolders: [
    { id: 'tw', name: 'Golden Flames 2026-10-13', files: [file('tw-f', 'IMG_100.jpg', 3333, 120)] },
    { id: 'ok', name: 'Silver Roots 2026-10-13', files: [file('ok-f', 'IMG_100.jpg', 3434, 120)] }] }];
  const tg = target('Asia', [{ id: 'g1', name: 'Golden Flames 2026-10-13', files: [] },
                             { id: 'g2', name: 'Golden Flames 2026-10-13', files: [{ id: 'g2-f', name: 'IMG_100.jpg', size: 3333 }] }]);
  const r = plan(sources, tg, NOW, 10);
  check('two same-name subfolders already on the Shared Drive: refused and reported, neither picked',
        same(norm(r.plan).refused, ['Asia|tw|Golden Flames 2026-10-13']) && !acted(r.plan).some(e => e.id === 'tw') &&
        !list(r.plan, 'waiting').some(e => e.id === 'tw') && same(norm(r.plan).moves, ['Asia|ok|Silver Roots 2026-10-13|tgt-asia|ok-f']),
        r.error || JSON.stringify(norm(r.plan)));
}

console.log('\nplanMoves_ — unknown regions, empty subfolders, other folders');
{
  const sub = (id, ageMin) => ({ id, name: 'Golden Stars 2026-10-09', files: [file(id + '-f', 'IMG_100.jpg', 1234, ageMin)] });
  const sources = [
    { id: 'src-eu', name: 'Attendance photos - Europe', subfolders: [sub('eu-1', 90)] },
    { id: 'src-us', name: 'Attendance photos - U.S', subfolders: [sub('us-1', 90)] },
    { id: 'src-af', name: 'Attendance photos - Africa', subfolders: [
      { id: 'af-empty', name: 'Rising Roots 2026-10-09', files: [] }, sub('af-1', 90)] },
    { id: 'src-x1', name: 'Attendance photos', subfolders: [sub('x1-1', 90)] },
    { id: 'src-x2', name: 'Receipts - Africa', subfolders: [sub('x2-1', 90)] },
    { id: 'src-x3', name: 'Old Attendance photos - Asia', subfolders: [sub('x3-1', 90)] },
    { id: 'src-x4', name: 'Holiday pictures', subfolders: [] },
    { id: 'src-x5', name: 'attendance photos - Africa', subfolders: [sub('x5-1', 90)] },
    { id: 'src-x6', name: 'Attendance Photos - Africa', subfolders: [sub('x6-1', 90)] },
    { id: 'src-x7', name: 'Attendance  photos - Africa', subfolders: [sub('x7-1', 90)] },
    { id: 'src-x8', name: 'Attendance photos  - Africa', subfolders: [sub('x8-1', 90)] },
    { id: 'src-x9', name: 'Attendance photos -Africa', subfolders: [sub('x9-1', 90)] },
  ];
  const targets = Object.assign(target('Africa'), target('Asia'));
  const r = plan(sources, targets, NOW, 10);
  const n = norm(r.plan);
  check('a region with no target (U.S here) and a region that does not exist (Europe): reported, left alone',
        same(n.unknown, ['src-eu', 'src-us']) && !ids(r.plan).has('eu-1') && !ids(r.plan).has('us-1'),
        r.error || JSON.stringify(n));
  check('an empty subfolder is neither moved nor merged; its settled neighbour moves',
        !acted(r.plan).some(e => e.id === 'af-empty') &&
        same(n.moves, ['Africa|af-1|Golden Stars 2026-10-09|tgt-africa|af-1-f']), r.error || JSON.stringify(n));
  const outside = ['src-x1', 'x1-1', 'src-x2', 'x2-1', 'src-x3', 'x3-1', 'src-x4', 'src-x5', 'x5-1', 'src-x6', 'x6-1',
                   'src-x7', 'x7-1', 'src-x8', 'x8-1', 'src-x9', 'x9-1'].filter(x => ids(r.plan).has(x));
  check('folders not named exactly `Attendance photos - …` (other case, doubled or missing space) are in no list',
        !!r.plan && !outside.length, r.error || outside.join(', '));
  const withUs = plan(sources, Object.assign({}, targets, target('U.S')), NOW, 10);
  check('…and once U.S has a target, its subfolder moves there', norm(withUs.plan).moves.includes('U.S|us-1|Golden Stars 2026-10-09|tgt-us|us-1-f') &&
        same(norm(withUs.plan).unknown, ['src-eu']), withUs.error || JSON.stringify(norm(withUs.plan)));
}

console.log('\nplanMoves_ — a move carries every file of its subfolder (#132: the mover moves them one by one)');
{
  const name = 'Golden Voices 2026-10-16';
  const sources = [
    { id: 'src-la', name: 'Attendance photos - Latin America', subfolders: [
      { id: 'three', name, files: [file('v1', 'IMG_100.jpg', 7001, 400), file('v2', 'IMG_101.jpg', 7002, 30), file('v3', 'IMG_102.jpg', 7001, 11)] },
      { id: 'one', name: 'Silver Flames 2026-10-16', files: [file('w1', 'IMG_100.jpg', 7001, 60)] },
      { id: 'young', name: 'Rising Wings 2026-10-16', files: [file('y1', 'IMG_100.jpg', 8000, 400), file('y2', 'IMG_101.jpg', 8001, 4)] },
    ] },
    { id: 'src-as', name: 'Attendance photos - Asia', subfolders: [
      { id: 'elsewhere', name, files: [file('e1', 'IMG_100.jpg', 7001, 60), file('e2', 'IMG_101.jpg', 7002, 60)] } ] },
  ];
  // Asia's Shared Drive folder already holds this name with files identical to Latin America's `three`:
  // another region, so `three` is still a plain move of everything (a move keeps nothing)
  const targets = Object.assign(target('Latin America'), target('Asia', [
    { id: 'as-there', name, files: [{ id: 't-e1', name: 'IMG_100.jpg', size: 7001 }, { id: 't-e2', name: 'IMG_101.jpg', size: 7002 },
                                    { id: 't-x', name: 'IMG_102.jpg', size: 7001 }] }]));
  const r = plan(sources, targets, NOW, 10);
  const byId = Object.fromEntries(list(r.plan, 'moves').map(m => [m.id, m]));
  const filesOf = m => (m && m.files ? m.files.map(fid).sort() : null);
  check('a three-file subfolder moves with all three ids (whatever their ages); a one-file one with its one',
        same(filesOf(byId.three), ['v1', 'v2', 'v3']) && same(filesOf(byId.one), ['w1']) && same(Object.keys(byId).sort(), ['one', 'three']),
        r.error || JSON.stringify(list(r.plan, 'moves')));
  check('…identical files under the same name in ANOTHER region\'s folder change nothing: nothing kept, every file in the move',
        !!byId.three && !(byId.three.kept || []).length && same(filesOf(byId.three), ['v1', 'v2', 'v3']) &&
        !!list(r.plan, 'merges').find(m => m.id === 'elsewhere' && !(m.files || []).length),
        r.error || JSON.stringify(norm(r.plan)));
  const all = [].concat(...list(r.plan, 'moves').map(m => (m.files || []).map(fid)));
  check('…no file of another subfolder or of the Shared Drive is in any move\'s files',
        !!r.plan && !all.some(x => ['y1', 'y2', 'e1', 'e2', 't-e1', 't-e2', 't-x'].includes(x)), all.join(','));
  const r3 = plan(sources, targets, NOW, 3);
  const young = list(r3.plan, 'moves').find(m => m.id === 'young');
  check('settle 3: the two-file subfolder that waited now moves, with both its files',
        same(filesOf(young), ['y1', 'y2']) && list(r3.plan, 'moves').length === 3, r3.error || JSON.stringify(norm(r3.plan)));
}

console.log('\nplanMoves_ — a merge that moves nothing does not claim the name');
{
  const name = 'Golden Flames 2026-10-13';
  const sub = (id, fname, size) => ({ id, name, files: [file(id + '-f', fname, size, 120)] });
  const tg = target('Africa', [{ id: 'there', name, files: [{ id: 't-1', name: 'IMG_100.jpg', size: 1000 }] }]);
  for (const order of [['allKept', 'newOne'], ['newOne', 'allKept']]) {
    const subs = { allKept: sub('allKept', 'IMG_100.jpg', 1000), newOne: sub('newOne', 'IMG_101.jpg', 2000) };
    const r = plan([{ id: 'src-af', name: 'Attendance photos - Africa', subfolders: order.map(k => subs[k]) }], tg, NOW, 10);
    const byId = Object.fromEntries(list(r.plan, 'merges').map(m => [m.id, m]));
    check('same name twice in My Drive, one copy entirely on the Shared Drive already (' + order.join(', ') + '): ' +
          'the other copy still merges this run',
          !!byId.newOne && byId.newOne.into === 'there' && same((byId.newOne.files || []).map(fid), ['newOne-f']),
          r.error || JSON.stringify(norm(r.plan)));
    check('…and the all-kept copy is a merge of nothing (kept), never `waiting`',
          !!byId.allKept && !(byId.allKept.files || []).length && same((byId.allKept.kept || []).map(fid), ['allKept-f']) &&
          !list(r.plan, 'waiting').length, r.error || JSON.stringify(norm(r.plan)));
  }
}

console.log('\nplanMoves_ — run after run, the plan carried out each time, everything settles');
{
  // the plan applied to the model, as the mover applies it to Drive (#132): a move makes a folder of
  // that name on the Shared Drive and moves the plan's files into it; the emptied subfolder stays
  const apply = (sources, targets, p) => {
    for (const s of sources) {
      const region = s.name.slice(PREFIX.length);
      for (const m of list(p, 'moves').filter(x => x.region === region)) {
        const from = s.subfolders.find(x => x.id === m.id);
        if (!from) continue;
        const made = { id: 'made-' + m.id, name: m.name, files: [] };
        for (const f of (m.files || []).map(fid)) {
          const i = from.files.findIndex(x => x.id === f);
          if (i >= 0) made.files.push(from.files.splice(i, 1)[0]);
        }
        targets[region].subfolders.push(made);
      }
      for (const m of list(p, 'merges').filter(x => x.region === region)) {
        const from = s.subfolders.find(x => x.id === m.id), into = targets[region].subfolders.find(x => x.id === m.into);
        for (const f of (m.files || []).map(fid)) {
          const i = from ? from.files.findIndex(x => x.id === f) : -1;
          if (i >= 0 && into) into.files.push(from.files.splice(i, 1)[0]);
        }
      }
    }
  };
  const settled = p => !!p && !list(p, 'moves').length && !list(p, 'merges').some(m => (m.files || []).length) &&
                       !list(p, 'waiting').length;
  for (let seed = 1; seed <= 6; seed++) {
    const r = prng(100 + seed);
    let n = 0;
    const id = p => p + seed + '-' + (++n);
    const names = ['Bright Stars 2026-10-14', 'Rising Lights 2026-10-14', 'Golden Flames 2026-10-13'];
    const targets = { Africa: { id: 'tgt-af-' + seed, subfolders: [] }, Asia: { id: 'tgt-as-' + seed, subfolders: [] } };
    const sources = ['Africa', 'Asia'].map(region => ({ id: id('src'), name: PREFIX + region, subfolders: [] }));
    for (const s of sources) {
      const region = s.name.slice(PREFIX.length);
      for (const nm of names) {
        if (r() < 0.5) {   // already on the Shared Drive once
          targets[region].subfolders.push({ id: id('tsub'), name: nm, files: [100, 101].filter(() => r() < 0.6)
            .map(k => ({ id: id('t'), name: 'IMG_' + k + '.jpg', size: k * 10 })) });
        }
        const copies = 1 + Math.floor(r() * 3);   // the same subfolder name up to three times in My Drive
        for (let c = 0; c < copies; c++) {
          s.subfolders.push({ id: id('sub'), name: nm, files: [100, 101, 102].filter(() => r() < 0.6)
            .map(k => ({ id: id('f'), name: 'IMG_' + k + '.jpg', size: r() < 0.7 ? k * 10 : k * 10 + 1, updated: NOW - OLD * MIN })) });
        }
      }
    }
    let last = null, runsUsed = 0, error = '', twice = [];
    for (let run = 0; run < 10; run++) {
      const got = plan(sources, targets, NOW + run * MIN, 10);
      if (got.error) { error = got.error; break; }
      runsUsed = run + 1;
      last = got.plan;
      if (settled(last)) break;
      apply(sources, targets, last);
      for (const [region, t] of Object.entries(targets)) {
        const count = {};
        for (const x of t.subfolders) count[x.name] = (count[x.name] || 0) + 1;
        twice = twice.concat(Object.keys(count).filter(k => count[k] > 1).map(k => region + ': ' + k));
      }
    }
    check('seed ' + seed + ': same-name copies settle run by run (' + runsUsed + ' of at most 10): nothing left waiting or to move',
          !error && settled(last), error || JSON.stringify(norm(last)));
    check('seed ' + seed + ': no run made a second same-name folder on the Shared Drive', !error && !twice.length, error || twice.join(', '));
  }
}

console.log('\nplanMoves_ — the dry run: a plan and no side effects');
{
  const { sources, targets } = layout(42, NOW, 10);
  const srcJson = JSON.stringify(sources), tgtJson = JSON.stringify(targets);
  const s = revive ? revive(srcJson) : null, t = revive ? revive(tgtJson) : null;
  touched.length = 0;
  let p1 = null, p2 = null, err = '';
  try {
    if (!planMoves) throw new Error('planMoves_ is not defined');
    p1 = planMoves(s, t, new CtxDate(NOW), 10);
    p2 = planMoves(s, t, new CtxDate(NOW), 10);
  } catch (e) { err = e.message; }
  check('no Google service is touched (DriveApp, Drive, PropertiesService, ScriptApp, MailApp …)',
        !err && !touched.length, err || touched.join(', '));
  check('the inputs are unchanged after planning (Dates included)',
        !err && JSON.stringify(s) === JSON.stringify(revive(srcJson)) && JSON.stringify(t) === JSON.stringify(revive(tgtJson)), err);
  check('the same inputs give the same plan', !err && same(norm(p1), norm(p2)) && norm(p1).moves.length > 0, err);
  const stray = ctx ? loadGs.strayGlobals(ctx) : ['not loaded'];
  check('no implicit globals made by the planner', !stray.length, stray.join(', '));
}

// ---------------------------------------------------------------- the entry points, run on fakes
console.log('\ndrive-sync/ — the entry points, run against fake Drive services');

// what each fake may be asked for; anything else is recorded as a violation
const ALLOW = {
  DriveApp: ['getFolders', 'getFoldersByName', 'getFolderById', 'getFileById', 'getRootFolder', 'searchFolders',
             'searchFiles', 'getFiles', 'getFilesByName'],
  Folder: ['getId', 'getName', 'getFolders', 'getFiles', 'getFoldersByName', 'getFilesByName', 'createFolder', 'moveTo',
           'addFile', 'removeFile', 'addFolder', 'removeFolder', 'getLastUpdated', 'getDateCreated', 'getParents',
           'isTrashed', 'searchFolders', 'searchFiles'],
  File: ['getId', 'getName', 'getSize', 'getLastUpdated', 'getDateCreated', 'getMimeType', 'moveTo', 'getParents', 'isTrashed'],
  Iterator: ['hasNext', 'next', 'getContinuationToken'],
  Drive: ['Files', 'Drives'],
  'Drive.Files': ['list', 'get', 'update', 'create'],
  'Drive.Drives': ['get', 'list'],
  ScriptApp: ['newTrigger', 'getProjectTriggers', 'deleteTrigger'],
  TriggerBuilder: ['timeBased', 'everyMinutes', 'everyHours', 'create', 'after', 'at', 'inTimezone', 'nearMinute', 'atHour'],
  Trigger: ['getHandlerFunction', 'getUniqueId', 'getEventType', 'getTriggerSource'],
  PropertiesService: ['getScriptProperties'],
  Properties: ['getProperty', 'getProperties', 'getKeys', 'setProperty', 'setProperties', 'deleteProperty'],
  LockService: ['getScriptLock'],
  Lock: ['tryLock', 'waitLock', 'releaseLock', 'hasLock'],
  Utilities: ['formatDate', 'sleep'],
  Logger: ['log'],
  Session: ['getScriptTimeZone'],
  MailApp: [], GmailApp: [], UrlFetchApp: [], SpreadsheetApp: [], CacheService: [], DocumentApp: [], FormApp: [],
};
const INTROSPECTION = new Set(['toString', 'valueOf', 'toJSON', 'constructor', 'then', 'inspect']);
const BY_ID = c => /ById$/.test(c) || ['Drive.Files.get', 'Drive.Files.update', 'Drive.Drives.get'].includes(c);
const WRITES = c => /\.(moveTo|createFolder|addFile|removeFile|addFolder|removeFolder)$/.test(c) ||
                    c === 'Drive.Files.update' || c === 'Drive.Files.create';

// Script Properties: SOURCE_FOLDER_<KEY> and TARGET_FOLDER_<KEY> per region (drive-sync/README.md)
const PROP_KEYS = { Africa: 'AFRICA', Asia: 'ASIA', 'Latin America': 'LATIN_AMERICA', 'U.S': 'US', Template: 'TEMPLATE' };
// the fake My Drive: Africa has a settled, a still-uploading and a resubmitted subfolder; Asia one settled one
const FAKE_SOURCES = {
  Africa: [['Bright Stars 2026-10-14', [['IMG_4471.jpg', 2048, OLD], ['IMG_4472.jpg', 4096, OLD]]],
           ['Rising Lights 2026-10-15', [['IMG_4480.jpg', 1500, 1]]],
           ['Golden Flames 2026-10-13', [['IMG_5501.jpg', 3000, OLD], ['IMG_5502.jpg', 3100, OLD]]]],
  Asia: [['Morning Wings 2026-10-13', [['IMG_6001.jpg', 5000, OLD]]]],
  'Latin America': [], 'U.S': [], Template: [],
};
// the fake Shared Drive: Africa already holds the resubmission's name, with one of its two photos
const FAKE_TARGETS = { Africa: [['Golden Flames 2026-10-13', [['IMG_5501.jpg', 3000]]]], Asia: [], 'Latin America': [], 'U.S': [], Template: [] };
const SOURCE_SUBS = Object.values(FAKE_SOURCES).reduce((a, s) => a + s.length, 0);
const FILE_STEMS = ['IMG_4471', 'IMG_4472', 'IMG_4480', 'IMG_5501', 'IMG_5502', 'IMG_6001', 'IMG_9000', 'receipt'];
// the real run (#132): a folder of each moved subfolder's name made ONCE in its region folder, each of its
// files moved into it; the merge's new photo into the folder already there (no folder made for a merge)
const EXPECTED_CREATED = ['T:Africa/Bright Stars 2026-10-14', 'T:Asia/Morning Wings 2026-10-13'].sort();
const EXPECTED_MOVES = ['S:Africa/Bright Stars 2026-10-14/IMG_4471.jpg -> T:Africa/Bright Stars 2026-10-14',
                        'S:Africa/Bright Stars 2026-10-14/IMG_4472.jpg -> T:Africa/Bright Stars 2026-10-14',
                        'S:Asia/Morning Wings 2026-10-13/IMG_6001.jpg -> T:Asia/Morning Wings 2026-10-13',
                        'S:Africa/Golden Flames 2026-10-13/IMG_5502.jpg -> T:Africa/Golden Flames 2026-10-13'].sort();
const inSub = (m, region, name) => m.startsWith('S:' + region + '/' + name + '/');

/**
 * Fake Google services recording every member asked for ('Type.member'), the file moves made
 * ('<file label> -> <folder label>'), the folders created ('<parent label>/<name>'), every
 * advanced Drive call (ops: op, the clock when it came, its optional args), the log and the
 * source subfolders read. The fake Drive behaves as the live one did on 2026-10-23 (#132):
 * DriveApp's Folder.moveTo / File.moveTo INTO a Shared Drive (T:*) folder throws; the advanced
 * service's Files.update moves a file only with supportsAllDrives true, addParents an existing
 * folder and removeParents the file's current parent, and never moves a folder
 * (teamDrivesFolderMoveInNotSupported); Files.create makes a real folder under its one parent,
 * found by name afterwards like any other. mode: 'ids' (every SOURCE_/TARGET_FOLDER_<KEY> set,
 * and any other property a fictional id) | 'empty' (no Script Properties). opt: failMoveOf (a
 * subfolder name whose files' moves throw), failCreateOf (a folder name whose Files.create
 * throws), moveAdvanceMin / readAdvanceMin (the clock jumps on each file moved / on each source
 * subfolder's files read), targetName / sourceName ({region: folder name}).
 */
function fakeEnv(mode, opt) {
  opt = opt || {};
  const calls = [], moved = [], attempted = [], created = [], ops = [], logs = [], read = new Set();
  const clock = { t: Date.now() };
  const t0 = clock.t;
  let D = Date, n = 0;
  const meta = new WeakMap(), byId = {};
  const wrap = (type, obj) => new Proxy(obj, {
    get(t, k) {
      if (typeof k !== 'string' || INTROSPECTION.has(k)) return t[k];
      calls.push(type + '.' + k);
      return k in t ? t[k] : function () { return undefined; };
    },
  });
  const iter = items => { let i = 0; return wrap('Iterator', { hasNext: () => i < items.length, next: () => items[i++],
                                                              getContinuationToken: () => null }); };
  const label = x => (meta.get(x) || { label: '?' }).label;
  const onSharedDrive = x => label(x).startsWith('T:');
  // DriveApp's moveTo: into a Shared Drive folder it fails as the live one did (#132)
  const moveTo = (self, dest) => {
    attempted.push(label(self));
    if (onSharedDrive(dest)) throw new Error('cannot use this operation on a shared drive item (fake)');
    moved.push(label(self) + ' -> ' + label(dest));
    return self;
  };
  const mkFile = (where, name, size, ageMin) => {
    const id = 'fake-file-' + (++n);
    const self = wrap('File', {
      getId: () => id, getName: () => name, getSize: () => size, getMimeType: () => 'image/jpeg',
      getLastUpdated: () => new D(t0 - ageMin * MIN), getDateCreated: () => new D(t0 - ageMin * MIN),
      moveTo: dest => moveTo(self, dest), getParents: () => iter([]), isTrashed: () => false,
    });
    meta.set(self, { id, name, label: where + '/' + name, parent: null, isFolder: false });
    byId[id] = self;
    return self;
  };
  const mkFolder = (lbl, name, kids, files, isSourceSub) => {
    const id = 'fake-folder-' + (++n);
    const self = wrap('Folder', {
      getId: () => id, getName: () => name, getFolders: () => iter(kids),
      getFiles: () => {
        if (isSourceSub) { read.add(lbl); if (opt.readAdvanceMin) clock.t += opt.readAdvanceMin * MIN; }
        return iter(files);
      },
      getFoldersByName: x => iter(kids.filter(k => meta.get(k).name === x)),
      getFilesByName: x => iter(files.filter(f => meta.get(f).name === x)),
      createFolder: x => {
        const made = mkFolder(lbl + '/' + x, x, [], [], false);
        kids.push(made);
        meta.get(made).parent = id;
        created.push(lbl + '/' + x);
        return made;
      },
      moveTo: dest => moveTo(self, dest),
      addFile: () => self, removeFile: () => self, addFolder: () => self, removeFolder: () => self,
      getLastUpdated: () => new D(t0 - OLD * MIN), getDateCreated: () => new D(t0 - OLD * MIN),
      getParents: () => iter([]), isTrashed: () => false, searchFolders: () => iter(kids), searchFiles: () => iter(files),
    });
    meta.set(self, { id, name, label: lbl, kids, files, parent: null, isFolder: true });
    for (const k of kids) meta.get(k).parent = id;
    for (const f of files) meta.get(f).parent = id;
    byId[id] = self;
    return self;
  };
  // the advanced Drive service, v3: Drive.Files.create(resource, mediaData, optionalArgs) and
  // Drive.Files.update(resource, fileId, mediaData, optionalArgs), as strict as Drive is
  const FOLDER_MIME = 'application/vnd.google-apps.folder';
  const allDrives = (op, args) => {
    if (!args || args.supportsAllDrives !== true) throw new Error(op + ': File not found (fake: supportsAllDrives is not true)');
  };
  const filesCreate = (resource, media, args) => {
    ops.push({ op: 'create', t: clock.t, args: Object.assign({}, args) });
    allDrives('Files.create', args);
    const r = resource || {};
    const parent = Array.isArray(r.parents) && r.parents.length === 1 ? byId[r.parents[0]] : null;
    if (!parent || !meta.get(parent).isFolder) throw new Error('Files.create: parents must be one existing folder id (fake)');
    if (r.mimeType !== FOLDER_MIME) throw new Error('Files.create: only a folder is created here, not ' + r.mimeType + ' (fake)');
    if (typeof r.name !== 'string' || !r.name) throw new Error('Files.create: a name is required (fake)');
    if (opt.failCreateOf && r.name === opt.failCreateOf) throw new Error('Drive said no (fake)');
    const made = mkFolder(label(parent) + '/' + r.name, r.name, [], [], false);
    meta.get(parent).kids.push(made);
    meta.get(made).parent = meta.get(parent).id;
    created.push(label(parent) + '/' + r.name);
    return { id: meta.get(made).id, name: r.name, mimeType: FOLDER_MIME, parents: [meta.get(parent).id] };
  };
  const filesUpdate = (resource, fileId, media, args) => {
    ops.push({ op: 'update', t: clock.t, args: Object.assign({}, args) });
    allDrives('Files.update', args);
    const item = byId[fileId];
    if (!item) throw new Error('Files.update: File not found: ' + String(fileId) + ' (fake)');
    const m = meta.get(item);
    attempted.push(m.label);
    const r = resource || {};
    if ('trashed' in r) calls.push('Drive.Files.update{trashed}');   // a trash by another door: a violation
    if ('parents' in r || 'trashed' in r) {
      throw new Error('Files.update: the parents field is not directly writable; nothing is trashed here (fake)');
    }
    if (m.isFolder) throw new Error('Files.update: teamDrivesFolderMoveInNotSupported: Moving folders into shared drives is not supported (fake)');
    const dest = args.addParents ? byId[args.addParents] : null;
    if (!dest || !meta.get(dest).isFolder) throw new Error('Files.update: addParents is not one existing folder id (fake)');
    if (args.removeParents !== m.parent) throw new Error('Files.update: removeParents is not the file\'s parent (fake)');
    const from = meta.get(byId[m.parent]);
    if (opt.failMoveOf && from.name === opt.failMoveOf) throw new Error('Drive said no (fake)');
    from.files.splice(from.files.indexOf(item), 1);
    meta.get(dest).files.push(item);
    m.parent = meta.get(dest).id;
    moved.push(m.label + ' -> ' + label(dest));
    if (opt.moveAdvanceMin) clock.t += opt.moveAdvanceMin * MIN;
    return { id: fileId, parents: [m.parent] };
  };
  const propId = k => 'fake-id-' + String(k).replace(/[^A-Za-z0-9]+/g, '-');
  const sourceFolders = [], propFolders = {};
  for (const region of REGIONS) {
    const subs = FAKE_SOURCES[region].map(([nm, fl]) => {
      const where = 'S:' + region + '/' + nm;
      return mkFolder(where, nm, [], fl.map(([f, size, age]) => mkFile(where, f, size, age)), true);
    });
    const src = mkFolder('S:' + region, (opt.sourceName || {})[region] || PREFIX + region, subs, [], false);
    const tsubs = FAKE_TARGETS[region].map(([nm, fl]) => {
      const where = 'T:' + region + '/' + nm;
      return mkFolder(where, nm, [], fl.map(([f, size]) => mkFile(where, f, size, OLD)), false);
    });
    const tgt = mkFolder('T:' + region, (opt.targetName || {})[region] || region, tsubs, [], false);
    sourceFolders.push(src);
    propFolders[propId('SOURCE_FOLDER_' + PROP_KEYS[region])] = src;
    propFolders[propId('TARGET_FOLDER_' + PROP_KEYS[region])] = tgt;
  }
  const receiptsSub = mkFolder('S:Receipts/Silver Roots 2026-10-01', 'Silver Roots 2026-10-01', [],
                               [mkFile('S:Receipts/Silver Roots 2026-10-01', 'receipt.pdf', 100, OLD)], false);
  const receipts = mkFolder('S:Receipts', 'Receipts', [receiptsSub], [], false);
  const top = sourceFolders.concat(receipts);
  const root = mkFolder('S:root', 'My Drive', top, [mkFile('S:root', 'IMG_9000.jpg', 1000, OLD)], false);
  const trigger = wrap('Trigger', { getHandlerFunction: () => 'other', getUniqueId: () => 'fake-trigger', getEventType: () => undefined,
                                    getTriggerSource: () => undefined });
  const builder = wrap('TriggerBuilder', {});
  for (const k of ALLOW.TriggerBuilder) Object.defineProperty(builder, k, { value: () => (k === 'create' ? trigger : builder) });
  const propsValue = k => (mode === 'ids' ? propId(k) : null);
  const props = wrap('Properties', {
    getProperty: propsValue,
    getProperties: () => (mode === 'ids' ? new Proxy({}, { get: (_, k) => (typeof k === 'string' ? propsValue(k) : undefined) }) : {}),
    getKeys: () => [], setProperty: () => props, setProperties: () => props, deleteProperty: () => props,
  });
  const lock = wrap('Lock', { tryLock: () => true, waitLock: () => undefined, releaseLock: () => undefined, hasLock: () => true });
  const say = (...a) => { logs.push(a.map(String).join(' ')); };
  const globals = {
    DriveApp: wrap('DriveApp', {
      getFolders: () => iter(top), getFoldersByName: x => iter(top.filter(k => meta.get(k).name === x)),
      // an id handed out by getId(); a SOURCE_/TARGET_FOLDER_<KEY> property's folder; else (another property's id) the root
      getFolderById: x => byId[x] || propFolders[x] || root,
      getFileById: x => { if (byId[x]) return byId[x]; throw new Error('No item with the given ID (fake)'); },
      getRootFolder: () => root, searchFolders: () => iter(top), searchFiles: () => iter([]),
      getFiles: () => iter([]), getFilesByName: () => iter([]),
    }),
    Drive: wrap('Drive', {
      Files: wrap('Drive.Files', { list: () => ({ files: [], items: [] }), get: x => ({ id: x, name: 'x', parents: [] }),
                                   create: filesCreate, update: filesUpdate }),
      Drives: wrap('Drive.Drives', { get: x => ({ id: x, name: 'x' }), list: () => ({ drives: [] }) }),
    }),
    ScriptApp: wrap('ScriptApp', { newTrigger: () => builder, getProjectTriggers: () => [trigger], deleteTrigger: () => undefined }),
    PropertiesService: wrap('PropertiesService', { getScriptProperties: () => props }),
    LockService: wrap('LockService', { getScriptLock: () => lock }),
    Utilities: wrap('Utilities', { formatDate: d => new Date(d).toISOString(), sleep: () => undefined }),
    Logger: wrap('Logger', { log: say }),
    Session: wrap('Session', { getScriptTimeZone: () => 'America/Chicago' }),
    console: { log: say, info: say, warn: say, error: say },
  };
  for (const s of ['MailApp', 'GmailApp', 'UrlFetchApp', 'SpreadsheetApp', 'CacheService', 'DocumentApp', 'FormApp']) {
    globals[s] = wrap(s, {});
  }
  /** The sandbox's clock: `new Date()` and `Date.now()` read clock.t (moved by the fakes). */
  const install = c => {
    c.__fakeClock = () => clock.t;
    vm.runInContext('(function () { const R = Date, now = __fakeClock;' +
                    ' class FakeDate extends R { constructor(...a) { if (a.length) super(...a); else super(now()); }' +
                    ' static now() { return now(); } } Date = FakeDate; })(); delete globalThis.__fakeClock;', c);
    D = vm.runInContext('Date', c);
  };
  return { calls, moved, attempted, created, ops, logs, read, t0, globals, install };
}

const violations = calls => calls.filter(c => {
  const i = c.lastIndexOf('.');
  const type = c.slice(0, i), member = c.slice(i + 1);
  return !(ALLOW[type] || []).includes(member);
});

const ENTRIES = GS.length ? loadGs.declarations(GS_SRC).filter(nm => !nm.endsWith('_') && ctx && typeof ctx[nm] === 'function') : [];
/**
 * One entry point on a fresh fake Drive; the result's records are copies. Its `rerun(opt)` runs
 * the same entry point again on the SAME fake Drive (the trigger's next run), with other
 * options and the records starting afresh.
 */
function runEntry(name, mode, opt) {
  opt = opt || {};
  const env = fakeEnv(mode, opt);
  let c = null;
  const once = () => {
    let threw = '';
    try {
      if (!c) { c = loadGs.sandbox(GS, env.globals); env.install(c); }
      vm.runInContext(name + '();', c, { timeout: 5000 });
    } catch (e) { threw = String(e && e.message || e); }
    return { name, threw, text: env.logs.join('\n'), calls: env.calls.slice(), moved: env.moved.slice(),
             attempted: env.attempted.slice(), created: env.created.slice(), ops: env.ops.slice(),
             read: new Set(env.read), t0: env.t0, rerun };
  };
  const rerun = next => {
    for (const k of Object.keys(opt)) delete opt[k];
    Object.assign(opt, next || {});
    for (const a of [env.calls, env.moved, env.attempted, env.created, env.ops, env.logs]) a.length = 0;
    env.read.clear();
    return once();
  };
  return once();
}
const runEntries = (mode, opt) => ENTRIES.map(name => runEntry(name, mode, opt));
const fileNamesIn = text => FILE_STEMS.filter(s => text.includes(s));
{
  check('there are entry points (top-level functions not ending in `_`)', ENTRIES.length > 0, ENTRIES.join(', ') || 'none');
  const full = runEntries('ids');
  const bad = full.flatMap(r => violations(r.calls).map(c => r.name + ': ' + c));
  check('with every region set up in Script Properties, every call (the full apply path included) is in the allow-list ' +
        '(no sharing, links, copies, trash, mail)',
        ENTRIES.length > 0 && !bad.length, ENTRIES.length ? [...new Set(bad)].join(', ') : 'no entry points');
  const summary = rs => rs.map(r => r.name + ': ' + (r.threw || 'ok') + ' [' + r.calls.length + ' calls, ' + r.created.length +
                                    ' created, ' + r.moved.length + ' moves]').join('; ');
  check('…and at least one entry point reads the fake Drive (the run is not vacuous)',
        full.some(r => r.read.size > 0), summary(full));
  // the entry point that writes (tries a move, or makes a folder): the real run
  const applier = full.find(r => r.attempted.length || r.created.length);
  const outcome = r => ({ created: r.created.slice().sort(), moved: r.moved.slice().sort() });
  const WANT = { created: EXPECTED_CREATED, moved: EXPECTED_MOVES };
  check('one entry point is the real run (#132): each settled subfolder\'s files moved into a folder of its name made in the ' +
        'region folder, the resubmission\'s new photo merged into the folder already there, nothing else (not the uploading ' +
        'one, not the kept photo, not Receipts)',
        !!applier && !applier.threw && same(outcome(applier), WANT),
        applier ? applier.name + ': ' + (applier.threw || '') + ' ' + show(outcome(applier), WANT) : summary(full));
  check('…exactly one folder made per moved subfolder, through Drive.Files.create (none for the merge, none any other way)',
        !!applier && applier.ops.filter(o => o.op === 'create').length === EXPECTED_CREATED.length &&
        applier.created.length === EXPECTED_CREATED.length,
        applier ? applier.ops.filter(o => o.op === 'create').length + ' Files.create call(s); made ' + JSON.stringify(applier.created) : 'no applier');
  const banned = r => r.calls.filter(c => /\.(moveTo|setTrashed)$/.test(c) || c === 'Drive.Files.update{trashed}' ||
                                          /^Drive\.Files\.(remove|delete|emptyTrash|trash)$/.test(c));
  check('…no DriveApp moveTo at all on the apply path (Drive refuses a folder moved into a Shared Drive), nothing trashed or deleted: ' +
        'the emptied My Drive subfolder stays',
        !!applier && !banned(applier).length, applier ? [...new Set(banned(applier))].join(', ') : 'no applier');
  check('…every advanced Drive call (Files.create and Files.update) carries supportsAllDrives: true',
        !!applier && applier.ops.length > 0 && applier.ops.every(o => o.args.supportsAllDrives === true),
        applier ? applier.ops.length + ' call(s); without it: ' +
                  applier.ops.filter(o => o.args.supportsAllDrives !== true).map(o => o.op + ' ' + JSON.stringify(o.args)).join('; ') : 'no applier');
  check('…its log has the counts and the folder names, and no file name',
        !!applier && /\d/.test(applier.text) && ['Bright Stars 2026-10-14', 'Morning Wings 2026-10-13', 'Golden Flames 2026-10-13']
          .every(x => applier.text.includes(x)) && !fileNamesIn(applier.text).length,
        applier ? 'file names logged: ' + fileNamesIn(applier.text).join(', ') : 'no applier');
  const dry = full.find(r => r.read.size > 0 && !r.attempted.length && !r.created.length && !r.ops.length && !r.calls.some(WRITES) &&
                         !r.threw && ['Bright Stars 2026-10-14', 'Morning Wings 2026-10-13'].every(x => r.text.includes(x)));
  check('one entry point is the dry run: reads both drives, logs what it would move by folder name, writes nothing (no Files.create ' +
        'or Files.update, no moveTo), no file name',
        !!dry && !fileNamesIn(dry.text).length, dry ? dry.name + ': ' + fileNamesIn(dry.text).join(', ') : summary(full));
  const empty = runEntries('empty');
  const byId = empty.flatMap(r => r.calls.filter(c => BY_ID(c) || WRITES(c)).map(c => r.name + ': ' + c));
  check('with NO Script Properties, no entry point opens anything by id or changes anything (no id is hard-coded)',
        ENTRIES.length > 0 && !byId.length, ENTRIES.length ? [...new Set(byId)].join(', ') : 'no entry points');

  const A = applier ? applier.name : null;
  const tell = r => (r ? 'threw: ' + (r.threw || 'no') + '; made ' + JSON.stringify(r.created) + '; moved ' + JSON.stringify(r.moved) +
                         '; log: ' + r.text.slice(-400) : 'no applier');
  // a failure: logged by folder name, the rest of the run goes on, the run ends with an error
  const failedMove = A ? runEntry(A, 'ids', { failMoveOf: 'Bright Stars 2026-10-14' }) : null;
  const notBright = EXPECTED_MOVES.filter(m => !inSub(m, 'Africa', 'Bright Stars 2026-10-14'));
  check('a move whose file moves fail: the other move and the merge still happen, MOVE_FAILED names the folder (no file name), ' +
        'and the run ends with an error',
        !!failedMove && !!failedMove.threw && same(failedMove.moved.slice().sort(), notBright) &&
        /MOVE_FAILED[^\n]*Bright Stars 2026-10-14/.test(failedMove.text) && !fileNamesIn(failedMove.text + failedMove.threw).length,
        tell(failedMove));
  // the folder was made, its files were not moved: the next run sees the name on the Shared Drive once and merges
  const again = failedMove ? failedMove.rerun({}) : null;
  const bright = EXPECTED_MOVES.filter(m => inSub(m, 'Africa', 'Bright Stars 2026-10-14'));
  check('…the next run finishes it as a merge: both photos move into the folder made last time, no second folder of that name, ' +
        'nothing else moved, no error',
        !!again && !again.threw && same(again.moved.slice().sort(), bright) && !again.created.length, tell(again));
  const failedCreate = A ? runEntry(A, 'ids', { failCreateOf: 'Morning Wings 2026-10-13' }) : null;
  const notMorning = EXPECTED_MOVES.filter(m => !inSub(m, 'Asia', 'Morning Wings 2026-10-13'));
  check('a move whose folder cannot be made: none of its files is moved, the rest of the run goes on, MOVE_FAILED names it, ' +
        'the run ends with an error',
        !!failedCreate && !!failedCreate.threw && same(failedCreate.moved.slice().sort(), notMorning) &&
        !failedCreate.attempted.some(a => a.startsWith('S:Asia/Morning Wings 2026-10-13/')) &&
        /MOVE_FAILED[^\n]*Morning Wings 2026-10-13/.test(failedCreate.text) && same(failedCreate.created, ['T:Africa/Bright Stars 2026-10-14']),
        tell(failedCreate));
  const failedMerge = A ? runEntry(A, 'ids', { failMoveOf: 'Golden Flames 2026-10-13' }) : null;
  const notGolden = EXPECTED_MOVES.filter(m => !inSub(m, 'Africa', 'Golden Flames 2026-10-13'));
  check('a merge whose file move fails: both moves still happen, MERGE_FAILED names the folder (no file name), the run ends with an error',
        !!failedMerge && !!failedMerge.threw && same(failedMerge.moved.slice().sort(), notGolden) &&
        /MERGE_FAILED[^\n]*Golden Flames 2026-10-13/.test(failedMerge.text) && !fileNamesIn(failedMerge.text + failedMerge.threw).length,
        tell(failedMerge));
  // the clock jumps 7 minutes on each file moved: past the budget (and Apps Script's 6-minute limit) after the first
  const late = A ? runEntry(A, 'ids', { moveAdvanceMin: 7 }) : null;
  const lateOps = late ? late.ops.filter(o => o.t - late.t0 >= 6 * MIN) : [];
  check('the clock past the run\'s time budget after the FIRST file moved: no further Drive write (no file moved, no folder made), ' +
        'TIME_BUDGET logged',
        !!late && late.attempted.length === 1 && !lateOps.length && /TIME_BUDGET/.test(late.text),
        late ? 'files tried ' + late.attempted.length + '; Drive calls after the budget ' + lateOps.length + '; ' + (late.threw || '') +
               ' log: ' + late.text.slice(-300) : 'no applier');
  const slow = A ? runEntry(A, 'ids', { readAdvanceMin: 3 }) : null;
  const unreadMoved = slow ? slow.moved.filter(m => ![...slow.read].some(r => m.startsWith(r + '/')))
                                 .concat(slow.created.filter(c => ![...slow.read].some(r => r.slice(2) === c.slice(2)))) : ['no applier'];
  check('reading slow (3 minutes a subfolder): it stops reading new subfolders well before the budget and logs TIME_BUDGET',
        !!slow && slow.read.size < SOURCE_SUBS && /TIME_BUDGET/.test(slow.text),
        slow ? 'read ' + slow.read.size + ' of ' + SOURCE_SUBS + '; ' + (slow.threw || '') + ' log: ' + slow.text.slice(-300) : 'no applier');
  check('…and nothing it did not read is moved, nor a folder made for it', !!slow && !unreadMoved.length, unreadMoved.join(', '));
  for (const [what, opt] of [['TARGET_FOLDER_AFRICA is a folder named "Africa photos"', { targetName: { Africa: 'Africa photos' } }],
                             ['TARGET_FOLDER_ASIA is a folder named "asia"', { targetName: { Asia: 'asia' } }],
                             ['SOURCE_FOLDER_AFRICA is a folder named "Attendance photos - Africa (old)"',
                              { sourceName: { Africa: 'Attendance photos - Africa (old)' } }]]) {
    const r = A ? runEntry(A, 'ids', opt) : null;
    check(what + ': CONFIG refused, and no Drive write at all (not even the other regions\')',
          !!r && /CONFIG refused/.test(r.threw + '\n' + r.text) && !r.attempted.length && !r.created.length && !r.ops.length,
          r ? 'threw: ' + (r.threw || 'no') + '; moves tried ' + JSON.stringify(r.attempted) + '; made ' + JSON.stringify(r.created) +
              '; Drive calls ' + r.ops.length : 'no applier');
  }
}

// ---------------------------------------------------------------- the project around it
console.log('\ndrive-sync/ — manifest, clasp template, ids, sharing');
/** Code without comments (a // after start of line or whitespace; /* … *\/ blocks). */
const code = src => src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|\s)\/\/.*$/gm, '$1');
const gsCode = code(GS_SRC);
const readJson = f => { try { return JSON.parse(fs.readFileSync(f, 'utf8')); } catch (e) { return null; } };
{
  const manifest = readJson(path.join(DIR, 'appsscript.json'));
  check('drive-sync/appsscript.json parses: V8 and a timeZone',
        !!manifest && manifest.runtimeVersion === 'V8' && typeof manifest.timeZone === 'string' && manifest.timeZone.length > 0,
        JSON.stringify(manifest));
  const scopes = manifest && Array.isArray(manifest.oauthScopes) ? manifest.oauthScopes.slice().sort() : null;
  const usesDriveApp = /\bDriveApp\b/.test(gsCode), usesDrive = /\bDrive\s*\.\s*[A-Z]/.test(gsCode);
  const usesScriptApp = /\bScriptApp\b/.test(gsCode);
  const need = [];
  if (usesDriveApp || usesDrive) need.push(DRIVE_SCOPE);
  if (usesScriptApp) need.push(TRIGGER_SCOPE);
  need.sort();
  check('oauthScopes are exactly what the code uses: Drive, plus script.scriptapp iff it uses ScriptApp',
        !!scopes && need.includes(DRIVE_SCOPE) && same(scopes, need), 'declared ' + JSON.stringify(scopes) + ', needed ' + JSON.stringify(need));
  const adv = ((manifest && manifest.dependencies && manifest.dependencies.enabledAdvancedServices) || []);
  const a0 = adv[0] || {};
  check('the advanced Drive service is enabled for the code\'s Drive.* calls (#132): exactly one entry, userSymbol Drive, ' +
        'serviceId drive, version v3',
        !!manifest && usesDrive && adv.length === 1 && a0.userSymbol === 'Drive' && a0.serviceId === 'drive' && a0.version === 'v3',
        'code calls Drive.*: ' + usesDrive + '; enabledAdvancedServices ' + JSON.stringify(adv));
  check('no web app or API executable (nothing reachable by a link)',
        !!manifest && !('webapp' in manifest) && !('executionApi' in manifest), manifest ? Object.keys(manifest).join(',') : '');
  const known = new Set(['DriveApp', 'ScriptApp', 'PropertiesService', 'LockService']);
  const others = [...new Set((gsCode.match(/\b[A-Z][A-Za-z]*(?:App|Service)\b/g) || []).filter(s => !known.has(s)))];
  const session = gsCode.match(/\bSession\s*\.\s*(?!getScriptTimeZone\b)\w+/g) || [];
  check('Google services used: DriveApp / Drive, ScriptApp, PropertiesService, LockService only (Session only for its time zone)',
        GS.length > 0 && !others.length && !session.length, others.concat(session).join(', '));

  const clasp = exists ? fs.readdirSync(DIR).filter(f => /^\.clasp\.json/.test(f)) : [];
  const parsed = clasp.map(f => ({ f, j: readJson(path.join(DIR, f)) }));
  const insideDir = d => { const p = path.resolve(DIR, d); return p === DIR || p.startsWith(DIR + path.sep); };
  check('a .clasp.json template of its own: JSON, scriptId a string, rootDir (if any) inside drive-sync/',
        parsed.length > 0 && parsed.every(({ j }) => !!j && typeof j.scriptId === 'string' &&
                                          (j.rootDir === undefined || (typeof j.rootDir === 'string' && insideDir(j.rootDir)))),
        parsed.map(({ f, j }) => f + ' ' + JSON.stringify(j)).join('; ') || 'none');
}

function walk(d) {
  return fs.readdirSync(d, { withFileTypes: true }).flatMap(e =>
    e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)]);
}
{
  const files = exists ? walk(DIR) : [];
  const idLike = [];
  for (const f of files) {
    // adjacent string literals joined first: 'abc' + 'def' is 'abcdef'
    const src = fs.readFileSync(f, 'utf8').replace(/(['"`])\s*\+\s*(['"`])/g, '');
    for (const tok of src.match(/[0-9A-Za-z_-]{19,}/g) || []) {
      if (/\d/.test(tok) && /[a-z]/.test(tok) && /[A-Z]/.test(tok)) idLike.push(path.basename(f) + ': ' + tok.slice(0, 6) + '…');
    }
    for (const m of src.match(/ById\s*\(\s*['"`][^'"`]*['"`]/g) || []) idLike.push(path.basename(f) + ': ' + m);
  }
  check('no Drive, folder or script id in any drive-sync/ file (ids live in Script Properties)',
        files.length > 0 && !idLike.length, files.length ? idLike.join('; ') : 'no files');
  check('the folder ids are read from Script Properties', /PropertiesService\s*\.\s*getScriptProperties\s*\(/.test(gsCode));
  const BANNED = [/\bMailApp\b/, /\bGmailApp\b/, /\bUrlFetchApp\b/, /\bPermissions\b/, /\bsetSharing\b/,
                  /\badd(Viewer|Editor|Commenter)s?\b/, /\bget(Download)?Url\b/, /\bweb(View|Content)Link\b/,
                  /\bANYONE\w*/, /\bAccess\s*\./, /\bPermission\s*\./,
                  /\[\s*['"`][^\]]*\+/, /\+\s*['"`][^'"`\]]*['"`]\s*\]/];   // obj['set' + 'Sharing'], obj[x + 'Viewer']
  const hits = BANNED.filter(rx => rx.test(gsCode)).map(String);
  check('the code never names sharing, links, e-mail, access levels, or builds a member name with `+`',
        GS.length > 0 && !hits.length, GS.length ? hits.join(' ') : 'no .gs files');
}

console.log('\nappsscript/ — the form-submit project is not touched');
{
  const live = fs.readFileSync(path.join(REPO, 'appsscript', 'appsscript.json'), 'utf8');
  let base = null;
  try {
    base = execFileSync('git', ['show', 'origin/main:appsscript/appsscript.json'],
                        { cwd: REPO, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
  } catch (e) { base = null; }
  if (base === null) console.log('  skip appsscript/appsscript.json vs origin/main :: no origin/main in this checkout');
  else check('appsscript/appsscript.json is the same as on origin/main', live === base);
  const m = JSON.parse(live);
  const advLive = (m.dependencies && m.dependencies.enabledAdvancedServices) || [];
  check('appsscript/ declares no Drive scope or Drive advanced service',
        !(m.oauthScopes || []).some(s => /auth\/drive/.test(s)) && !advLive.some(a => a.serviceId === 'drive'), live);
}

finish();
