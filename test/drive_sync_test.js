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
 *   moves    [{region, id, name, to}]      a whole subfolder (id) into the region folder (to)
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
 * in Script Properties they may call only the methods in ALLOW below (reading, moveTo,
 * createFolder, the trigger builder - never sharing, links, copies, trash or mail); with no
 * Script Properties at all they make no *ById call and change nothing.
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
    moves: list(p, 'moves').map(m => [m.region, m.id, m.name, m.to].join('|')).sort(),
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
      if (!there.length) { out.moves.push(key.concat(tgt.id).join('|')); continue; }
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
const seen = { moves: 0, merges: 0, waiting: 0, refused: 0, unknown: 0, kept: 0, sameSizeMoved: 0, empty: 0 };
let runs = 0;
for (let seed = 1; seed <= 8; seed++) {
  for (let k = 0; k < NOWS.length; k++) {
    const nowMs = NOWS[k], settle = SETTLES[(seed + k) % SETTLES.length];
    const { sources, targets } = layout(seed, nowMs, settle);
    const { want, empty, ignored } = oracle(sources, targets, nowMs, settle);
    for (const key of KEYS) seen[key] += want[key].length;
    seen.kept += want.merges.filter(m => m.split('|')[5]).length;
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
    check(label + ': moves, merges, waiting, refused and unknown are the rules\' answer',
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
        same(n10.moves, ['Africa|b|' + nm.b + '|tgt-africa', 'Africa|c|' + nm.c + '|tgt-africa']),
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
  const want = REGIONS.map((reg, i) => [reg, 'sub-' + i, sources[i].subfolders[0].name, targets[reg].id].join('|')).sort();
  check('Africa, Asia, Latin America, U.S, Template: each subfolder to its own region\'s folder',
        same(norm(r.plan).moves, want), r.error || show(norm(r.plan).moves, want));
  // the regions swapped round: the answer follows the names, not the order
  const reg2 = i => REGIONS[(i + 2) % REGIONS.length];
  const swapped = sources.map((s, i) => Object.assign({}, s, { name: PREFIX + reg2(i) }));
  const r2 = plan(swapped, targets, NOW, 10);
  const want2 = REGIONS.map((_, i) => [reg2(i), 'sub-' + i, sources[i].subfolders[0].name, targets[reg2(i)].id].join('|')).sort();
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
        same(norm(r.plan).moves, ['Asia|fresh|Evening Roots 2026-10-15|tgt-asia']), r.error || JSON.stringify(norm(r.plan)));
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
        !list(r.plan, 'waiting').some(e => e.id === 'tw') && same(norm(r.plan).moves, ['Asia|ok|Silver Roots 2026-10-13|tgt-asia']),
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
        same(n.moves, ['Africa|af-1|Golden Stars 2026-10-09|tgt-africa']), r.error || JSON.stringify(n));
  const outside = ['src-x1', 'x1-1', 'src-x2', 'x2-1', 'src-x3', 'x3-1', 'src-x4', 'src-x5', 'x5-1', 'src-x6', 'x6-1',
                   'src-x7', 'x7-1', 'src-x8', 'x8-1', 'src-x9', 'x9-1'].filter(x => ids(r.plan).has(x));
  check('folders not named exactly `Attendance photos - …` (other case, doubled or missing space) are in no list',
        !!r.plan && !outside.length, r.error || outside.join(', '));
  const withUs = plan(sources, Object.assign({}, targets, target('U.S')), NOW, 10);
  check('…and once U.S has a target, its subfolder moves there', norm(withUs.plan).moves.includes('U.S|us-1|Golden Stars 2026-10-09|tgt-us') &&
        same(norm(withUs.plan).unknown, ['src-eu']), withUs.error || JSON.stringify(norm(withUs.plan)));
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
  'Drive.Files': ['list', 'get', 'update'],
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
const WRITES = c => /\.(moveTo|createFolder|addFile|removeFile|addFolder|removeFolder)$/.test(c) || c === 'Drive.Files.update';

/** Fake Google services recording every member asked for ('Type.member'). mode: 'ids' | 'empty'. */
function fakeEnv(mode) {
  const calls = [];
  let D = Date;
  let n = 0;
  const wrap = (type, obj) => new Proxy(obj, {
    get(t, k) {
      if (typeof k !== 'string' || INTROSPECTION.has(k)) return t[k];
      calls.push(type + '.' + k);
      return k in t ? t[k] : function () { return undefined; };
    },
  });
  const iter = items => { let i = 0; return wrap('Iterator', { hasNext: () => i < items.length, next: () => items[i++],
                                                              getContinuationToken: () => null }); };
  const fakeFile = (name, size, ageMin) => {
    const id = 'fake-file-' + (++n);
    return wrap('File', { getId: () => id, getName: () => name, getSize: () => size, getMimeType: () => 'image/jpeg',
                          getLastUpdated: () => new D(Date.now() - ageMin * MIN), getDateCreated: () => new D(Date.now() - ageMin * MIN),
                          moveTo: () => undefined, getParents: () => iter([]), isTrashed: () => false });
  };
  const fakeFolder = (name, kids, files) => {
    const id = 'fake-folder-' + (++n);
    const self = wrap('Folder', {
      getId: () => id, getName: () => name, getFolders: () => iter(kids()), getFiles: () => iter(files()),
      getFoldersByName: x => iter(kids().filter(k => k.getName() === x)), getFilesByName: x => iter(files().filter(f => f.getName() === x)),
      createFolder: x => fakeFolder(x, () => [], () => []), moveTo: () => self, addFile: () => self, removeFile: () => self,
      addFolder: () => self, removeFolder: () => self, getLastUpdated: () => new D(Date.now() - OLD * MIN),
      getDateCreated: () => new D(Date.now() - OLD * MIN), getParents: () => iter([]), isTrashed: () => false,
      searchFolders: () => iter(kids()), searchFiles: () => iter(files()),
    });
    return self;
  };
  const sub = (name, ageMin) => fakeFolder(name, () => [], () => [fakeFile('IMG_100.jpg', 2048, ageMin), fakeFile('IMG_101.jpg', 4096, ageMin + 5)]);
  const root = fakeFolder('My Drive', () => [
    fakeFolder(PREFIX + 'Africa', () => [sub('Bright Stars 2026-10-14', OLD), sub('Rising Lights 2026-10-15', 1)], () => []),
    fakeFolder(PREFIX + 'Asia', () => [sub('Morning Wings 2026-10-13', OLD)], () => []),
    fakeFolder('Receipts', () => [sub('Silver Roots 2026-10-01', OLD)], () => [fakeFile('receipt.pdf', 100, OLD)]),
  ], () => [fakeFile('IMG_300.jpg', 1000, OLD)]);
  const trigger = wrap('Trigger', { getHandlerFunction: () => 'other', getUniqueId: () => 'fake-trigger', getEventType: () => undefined,
                                    getTriggerSource: () => undefined });
  const builder = wrap('TriggerBuilder', {});
  for (const k of ALLOW.TriggerBuilder) Object.defineProperty(builder, k, { value: () => (k === 'create' ? trigger : builder) });
  const propsValue = k => (mode === 'ids' ? 'fake-id-' + String(k).replace(/[^A-Za-z0-9]+/g, '-') : null);
  const props = wrap('Properties', {
    getProperty: propsValue,
    getProperties: () => (mode === 'ids' ? new Proxy({}, { get: (_, k) => (typeof k === 'string' ? propsValue(k) : undefined) }) : {}),
    getKeys: () => [], setProperty: () => props, setProperties: () => props, deleteProperty: () => props,
  });
  const lock = wrap('Lock', { tryLock: () => true, waitLock: () => undefined, releaseLock: () => undefined, hasLock: () => true });
  const globals = {
    DriveApp: wrap('DriveApp', {
      getFolders: () => root.getFolders(), getFoldersByName: x => root.getFoldersByName(x), getFolderById: () => root,
      getFileById: () => fakeFile('IMG_100.jpg', 2048, OLD), getRootFolder: () => root, searchFolders: () => root.getFolders(),
      searchFiles: () => root.getFiles(), getFiles: () => root.getFiles(), getFilesByName: x => root.getFilesByName(x),
    }),
    Drive: wrap('Drive', {
      Files: wrap('Drive.Files', { list: () => ({ files: [], items: [] }), get: id => ({ id, name: 'x', parents: [] }), update: () => ({}) }),
      Drives: wrap('Drive.Drives', { get: id => ({ id, name: 'x' }), list: () => ({ drives: [] }) }),
    }),
    ScriptApp: wrap('ScriptApp', { newTrigger: () => builder, getProjectTriggers: () => [trigger], deleteTrigger: () => undefined }),
    PropertiesService: wrap('PropertiesService', { getScriptProperties: () => props }),
    LockService: wrap('LockService', { getScriptLock: () => lock }),
    Utilities: wrap('Utilities', { formatDate: d => new Date(d).toISOString(), sleep: () => undefined }),
    Logger: wrap('Logger', { log: () => undefined }),
    Session: wrap('Session', { getScriptTimeZone: () => 'America/Chicago' }),
    console: { log() {}, info() {}, warn() {}, error() {} },
  };
  for (const s of ['MailApp', 'GmailApp', 'UrlFetchApp', 'SpreadsheetApp', 'CacheService', 'DocumentApp', 'FormApp']) {
    globals[s] = wrap(s, {});
  }
  return { calls, globals, setDate: d => { D = d; } };
}

const violations = calls => calls.filter(c => {
  const i = c.lastIndexOf('.');
  const type = c.slice(0, i), member = c.slice(i + 1);
  return !(ALLOW[type] || []).includes(member);
});

const ENTRIES = GS.length ? loadGs.declarations(GS_SRC).filter(nm => !nm.endsWith('_') && ctx && typeof ctx[nm] === 'function') : [];
function runEntries(mode) {
  return ENTRIES.map(name => {
    const env = fakeEnv(mode);
    let threw = '';
    try {
      const c = loadGs.sandbox(GS, env.globals);
      env.setDate(vm.runInContext('Date', c));
      vm.runInContext(name + '();', c, { timeout: 5000 });
    } catch (e) { threw = String(e && e.message || e); }
    return { name, calls: env.calls, threw };
  });
}
{
  check('there are entry points (top-level functions not ending in `_`)', ENTRIES.length > 0, ENTRIES.join(', ') || 'none');
  const full = runEntries('ids');
  const bad = full.flatMap(r => violations(r.calls).map(c => r.name + ': ' + c));
  check('with fictional ids in Script Properties, every call is in the allow-list (no sharing, links, copies, trash, mail)',
        ENTRIES.length > 0 && !bad.length, ENTRIES.length ? [...new Set(bad)].join(', ') : 'no entry points');
  check('…and at least one entry point reads the fake Drive (the run is not vacuous)',
        full.some(r => r.calls.some(c => /^(DriveApp|Drive)\./.test(c))),
        full.map(r => r.name + ': ' + (r.threw || 'ok') + ' [' + r.calls.length + ' calls]').join('; '));
  const empty = runEntries('empty');
  const byId = empty.flatMap(r => r.calls.filter(c => BY_ID(c) || WRITES(c)).map(c => r.name + ': ' + c));
  check('with NO Script Properties, no entry point opens anything by id or changes anything (no id is hard-coded)',
        ENTRIES.length > 0 && !byId.length, ENTRIES.length ? [...new Set(byId)].join(', ') : 'no entry points');
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
  check('advanced services: the Drive service exactly when the code calls Drive.*, nothing else',
        !!manifest && adv.every(a => a.serviceId === 'drive') && (adv.length > 0) === usesDrive, JSON.stringify(adv));
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
