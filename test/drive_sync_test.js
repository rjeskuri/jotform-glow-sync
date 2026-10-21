#!/usr/bin/env node
'use strict';
/**
 * Offline tests for drive-sync/ (ticket #89): the standalone Apps Script project that moves
 * Jotform's photo subfolders from Ryan's My Drive (`Attendance photos - <Region>`) into the
 * matching region folder on the company Shared Drive. Only the PURE planning function runs
 * here; the Drive calls are exercised by the dry run on Ryan's account (RUNBOOK).
 *
 * The contract (drive-sync/*.gs, loaded together in a vm sandbox like appsscript/):
 *
 *   planMoves_(sourceFolders, targetFolders, now, settleMinutes) -> {moves, merges, waiting, unknown}
 *
 *   sourceFolders  [{id, name, subfolders: [{id, name, files: [{id, name, size, updated: Date}]}]}]
 *                  the folders of Ryan's My Drive; only `Attendance photos - <Region>` counts
 *   targetFolders  {<Region>: {id, subfolders: [{id, name, files: [{id, name, size}]}]}}
 *                  the Shared Drive's region folders (ids from Script Properties), by region
 *   now            a Date;  settleMinutes  a number
 *
 *   moves    [{region, id, name, to}]      a whole subfolder (id) into the region folder (to)
 *   merges   [{region, id, name, into, files, kept}]
 *            a subfolder whose name already exists in the region folder (into = that folder's
 *            id): `files` are the source files to move into it, `kept` the source files left
 *            where they are because a file of the same name AND size is already there
 *            (each entry a file id, or the file object with its id)
 *   waiting  [{region, id, name}]          its newest file changed less than settleMinutes ago
 *   unknown  [{id, name}]                  an `Attendance photos - …` folder whose region is not
 *            one of Africa, Asia, Latin America, U.S, Template or has no target: left alone
 *
 * A subfolder with no files is never moved or merged. Any other folder is not touched or
 * reported. The planner touches no Google service and does not change its inputs (that is the
 * dry run: the plan without side effects).
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
const ALLOWED_SCOPES = [DRIVE_SCOPE, 'https://www.googleapis.com/auth/script.scriptapp'];

const exists = fs.existsSync(DIR) && fs.statSync(DIR).isDirectory();
const GS = exists ? fs.readdirSync(DIR).filter(f => f.endsWith('.gs')).sort().map(f => path.join(DIR, f)) : [];

// Google services: touching any of them from the planner (or at load time) is a side effect
const touched = [];
const trap = name => new Proxy({}, {
  get(_, k) { touched.push(name + '.' + String(k)); throw new Error(name + ' touched by the planner'); },
});
const SERVICES = ['DriveApp', 'Drive', 'PropertiesService', 'ScriptApp', 'MailApp', 'GmailApp',
                  'UrlFetchApp', 'LockService', 'CacheService', 'SpreadsheetApp', 'Session'];
const globals = {};
for (const s of SERVICES) globals[s] = trap(s);

console.log('drive-sync/ — the project loads, and defines the planner');
let ctx = null, loadError = '';
try {
  if (GS.length) ctx = loadGs.sandbox(GS, globals);
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
    moves: list(p, 'moves').map(m => [m.region, m.id, m.to].join('|')).sort(),
    merges: list(p, 'merges').map(m => [m.region, m.id, m.into,
                                        (m.files || []).map(fid).sort().join(','),
                                        (m.kept || []).map(fid).sort().join(',')].join('|')).sort(),
    waiting: list(p, 'waiting').map(w => [w.region, w.id].join('|')).sort(),
    unknown: list(p, 'unknown').map(u => u.id).sort(),
  };
}
const ids = p => new Set([].concat(list(p, 'moves'), list(p, 'merges'), list(p, 'waiting'),
                                   list(p, 'unknown')).map(e => e && e.id));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const show = (a, b) => 'got ' + JSON.stringify(a) + ' want ' + JSON.stringify(b);

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
      if (r() < 0.4) {   // a resubmission: the same subfolder name is already on the Shared Drive
        const tfiles = [];
        for (const f of files) {
          const roll = r();
          if (roll < 0.4) tfiles.push({ id: id('t'), name: f.name, size: f.size });            // identical
          else if (roll < 0.7) tfiles.push({ id: id('t'), name: f.name, size: f.size + 1 + Math.floor(r() * 500) });
        }
        tfiles.push({ id: id('t'), name: 'IMG_9' + Math.floor(r() * 10) + '.jpg', size: 5000 });
        tgt.subfolders.push({ id: id('tsub'), name, files: tfiles });
      }
    }
    // a Shared Drive subfolder with no counterpart in My Drive
    tgt.subfolders.push({ id: id('tsub'), name: 'Golden Roots 2026-09-30', files: [{ id: id('t'), name: 'IMG_100.jpg', size: 1 }] });
    sources.push(src);
  }
  // an unknown region and folders that are none of the mover's business
  for (const name of [PREFIX + 'Europe', 'Attendance photos', 'Receipts - Africa', 'Old ' + PREFIX + 'Asia']) {
    sources.push({ id: id('src'), name, subfolders: [
      { id: id('sub'), name: 'Silver Wings 2026-10-02', files: [{ id: id('f'), name: 'IMG_100.jpg', size: 2000, updated: nowMs - 600 * MIN }] },
    ] });
  }
  return { sources, targets };
}

/** What the plan must be, worked out from the rules alone. */
function oracle(sources, targets, nowMs, settle) {
  const out = { moves: [], merges: [], waiting: [], unknown: [] }, empty = [], ignored = [];
  for (const s of sources) {
    if (!s.name.startsWith(PREFIX)) { ignored.push(s.id); s.subfolders.forEach(x => ignored.push(x.id)); continue; }
    const region = s.name.slice(PREFIX.length);
    const tgt = REGIONS.includes(region) ? targets[region] : undefined;
    if (!tgt) { out.unknown.push(s.id); s.subfolders.forEach(x => ignored.push(x.id)); continue; }
    for (const sf of s.subfolders) {
      if (!sf.files.length) { empty.push(sf.id); continue; }
      const newest = Math.max(...sf.files.map(f => f.updated));
      if (nowMs - newest < settle * MIN) { out.waiting.push(region + '|' + sf.id); continue; }
      const there = tgt.subfolders.find(t => t.name === sf.name);
      if (!there) { out.moves.push([region, sf.id, tgt.id].join('|')); continue; }
      const dup = f => there.files.some(t => t.name === f.name && t.size === f.size);
      out.merges.push([region, sf.id, there.id, sf.files.filter(f => !dup(f)).map(f => f.id).sort().join(','),
                       sf.files.filter(dup).map(f => f.id).sort().join(',')].join('|'));
    }
  }
  for (const k of Object.keys(out)) out[k].sort();
  return { want: out, empty, ignored };
}

const NOWS = [Date.UTC(2027, 2, 5, 8, 0, 0), Date.UTC(2025, 11, 31, 23, 30, 0), Date.UTC(2026, 9, 21, 14, 7, 30)];
const SETTLES = [10, 15, 3];
const seen = { moves: 0, merges: 0, waiting: 0, unknown: 0, kept: 0, empty: 0 };
let runs = 0;
for (let seed = 1; seed <= 6; seed++) {
  for (let k = 0; k < NOWS.length; k++) {
    const nowMs = NOWS[k], settle = SETTLES[(seed + k) % SETTLES.length];
    const { sources, targets } = layout(seed, nowMs, settle);
    const { want, empty, ignored } = oracle(sources, targets, nowMs, settle);
    for (const key of ['moves', 'merges', 'waiting', 'unknown']) seen[key] += want[key].length;
    seen.kept += want.merges.filter(m => m.split('|')[4]).length;
    seen.empty += empty.length;
    const { plan: p, error } = plan(sources, targets, nowMs, settle);
    runs++;
    const got = norm(p);
    got.waiting = got.waiting.filter(w => !empty.includes(w.split('|')[1]));   // an empty one may wait
    const label = 'seed ' + seed + ', now ' + new Date(nowMs).toISOString() + ', settle ' + settle + 'm';
    check(label + ': moves, merges, waiting and unknown are the rules\' answer',
          !error && same(got, want), error || (same(got, want) ? '' : show(got, want)));
    const all = ids(p);
    const wrong = empty.filter(x => list(p, 'moves').concat(list(p, 'merges')).some(e => e.id === x))
      .concat(ignored.filter(x => all.has(x)));
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
  const tg = target('Africa');
  const r10 = plan(sources, tg, NOW, 10);
  const n10 = norm(r10.plan);
  check('settle 10: 9m59s waits, exactly 10m moves, 25m moves',
        same(n10.waiting, ['Africa|a', 'Africa|d']) && same(n10.moves, ['Africa|b|tgt-africa', 'Africa|c|tgt-africa']),
        r10.error || JSON.stringify(n10));
  check('the NEWEST file decides: a 5-hour-old photo beside a 2-minute-old one waits',
        n10.waiting.includes('Africa|d') && !n10.moves.some(m => m.includes('|d|')), r10.error || JSON.stringify(n10));
  const r30 = plan(sources, tg, NOW, 30);
  check('settle 30: the 25-minute-old subfolder waits too', same(norm(r30.plan).waiting, ['Africa|a', 'Africa|b', 'Africa|c', 'Africa|d']),
        r30.error || JSON.stringify(norm(r30.plan)));
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
  const want = REGIONS.map((reg, i) => reg + '|sub-' + i + '|' + targets[reg].id).sort();
  check('Africa, Asia, Latin America, U.S, Template: each subfolder to its own region\'s folder',
        same(norm(r.plan).moves, want), r.error || show(norm(r.plan).moves, want));
  const moved = list(r.plan, 'moves').find(m => m.id === 'sub-2');
  check('the move names the region ("Latin America") and the subfolder', !!moved && moved.region === 'Latin America' &&
        moved.name === sources[2].subfolders[0].name, JSON.stringify(moved));
  // the regions swapped round: the answer follows the names, not the order
  const swapped = sources.map((s, i) => Object.assign({}, s, { name: PREFIX + REGIONS[(i + 2) % REGIONS.length] }));
  const r2 = plan(swapped, targets, NOW, 10);
  const want2 = REGIONS.map((_, i) => REGIONS[(i + 2) % REGIONS.length] + '|sub-' + i + '|' + targets[REGIONS[(i + 2) % REGIONS.length]].id).sort();
  check('folders renamed to other regions: the targets follow the names', same(norm(r2.plan).moves, want2),
        r2.error || show(norm(r2.plan).moves, want2));
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
    { id: 'existing', name, files: [{ id: 't-same', name: 'IMG_100.jpg', size: 48211 }, { id: 't-smaller', name: 'IMG_101.jpg', size: 50007 }] },
  ] }, Africa: { id: 'tgt-africa', subfolders: [{ id: 'af-same-name', name: 'Evening Roots 2026-10-15', files: [] }] } };
  const r = plan(sources, targets, NOW, 10);
  const m = list(r.plan, 'merges').find(x => x.id === 'resub');
  check('the same subfolder name on the Shared Drive: a merge into that folder, not a move',
        !!m && m.into === 'existing' && m.region === 'Asia' && !list(r.plan, 'moves').some(x => x.id === 'resub'),
        r.error || JSON.stringify(r.plan));
  check('same name and size: kept (reported), not moved', !!m && same((m.kept || []).map(fid), ['s-same']) &&
        !(m.files || []).map(fid).includes('s-same'), JSON.stringify(m));
  check('same name, other size, and a new name: moved in beside what is there',
        !!m && same((m.files || []).map(fid).sort(), ['s-bigger', 's-new']), JSON.stringify(m));
  const planned = JSON.stringify(r.plan || {});
  check('the Shared Drive\'s own files appear nowhere in the plan (nothing there is replaced)',
        !!r.plan && !/t-same|t-smaller/.test(planned), planned);
  check('a name that exists only in ANOTHER region\'s folder is a plain move',
        same(norm(r.plan).moves, ['Asia|fresh|tgt-asia']), r.error || JSON.stringify(norm(r.plan)));
  const early = plan(sources, targets, NOW - 35 * MIN, 10);
  check('a resubmission still uploading waits; it is not merged half-way',
        norm(early.plan).waiting.includes('Asia|resub') && !list(early.plan, 'merges').length,
        early.error || JSON.stringify(norm(early.plan)));
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
  ];
  const targets = Object.assign(target('Africa'), target('Asia'));
  const r = plan(sources, targets, NOW, 10);
  const n = norm(r.plan);
  check('a region with no target (U.S here) and a region that does not exist (Europe): reported, left alone',
        same(n.unknown, ['src-eu', 'src-us']) && !ids(r.plan).has('eu-1') && !ids(r.plan).has('us-1'),
        r.error || JSON.stringify(n));
  check('an empty subfolder is neither moved nor merged; its settled neighbour moves',
        !list(r.plan, 'moves').concat(list(r.plan, 'merges')).some(e => e.id === 'af-empty') &&
        same(n.moves, ['Africa|af-1|tgt-africa']), r.error || JSON.stringify(n));
  const outside = ['src-x1', 'x1-1', 'src-x2', 'x2-1', 'src-x3', 'x3-1', 'src-x4'].filter(x => ids(r.plan).has(x));
  check('folders not named `Attendance photos - …` are not moved, merged, waited on or reported',
        !!r.plan && !outside.length, r.error || outside.join(', '));
  const withUs = plan(sources, Object.assign({}, targets, target('U.S')), NOW, 10);
  check('…and once U.S has a target, its subfolder moves there', norm(withUs.plan).moves.includes('U.S|us-1|tgt-us') &&
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

// ---------------------------------------------------------------- the project around it
console.log('\ndrive-sync/ — manifest, ids, sharing');
const readJson = f => { try { return JSON.parse(fs.readFileSync(f, 'utf8')); } catch (e) { return null; } };
{
  const manifest = readJson(path.join(DIR, 'appsscript.json'));
  check('drive-sync/appsscript.json parses, V8', !!manifest && manifest.runtimeVersion === 'V8', JSON.stringify(manifest));
  const scopes = manifest && Array.isArray(manifest.oauthScopes) ? manifest.oauthScopes : null;
  check('oauthScopes declared explicitly: Drive, and nothing beyond Drive (+ script.scriptapp for the trigger)',
        !!scopes && scopes.includes(DRIVE_SCOPE) && scopes.every(s => ALLOWED_SCOPES.includes(s)), JSON.stringify(scopes));
  const adv = ((manifest && manifest.dependencies && manifest.dependencies.enabledAdvancedServices) || []);
  check('advanced services: none, or Drive alone', !!manifest && adv.every(a => a.serviceId === 'drive'), JSON.stringify(adv));
  check('no web app or API executable (nothing reachable by a link)',
        !!manifest && !('webapp' in manifest) && !('executionApi' in manifest), manifest ? Object.keys(manifest).join(',') : '');
  const clasp = exists ? fs.readdirSync(DIR).filter(f => /^\.clasp\.json/.test(f)) : [];
  check('a .clasp.json template of its own, with a scriptId field',
        clasp.some(f => /"scriptId"/.test(fs.readFileSync(path.join(DIR, f), 'utf8'))), clasp.join(', ') || 'none');
}

/** Code without comments (a // after start of line or whitespace; /* … *\/ blocks). */
const code = src => src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|\s)\/\/.*$/gm, '$1');
function walk(d) {
  return fs.readdirSync(d, { withFileTypes: true }).flatMap(e =>
    e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)]);
}
{
  const files = exists ? walk(DIR) : [];
  const idLike = [];
  for (const f of files) {
    const src = fs.readFileSync(f, 'utf8');
    for (const tok of src.match(/[0-9A-Za-z_-]{19,}/g) || []) {
      if (/\d/.test(tok) && /[a-z]/.test(tok) && /[A-Z]/.test(tok)) idLike.push(path.basename(f) + ': ' + tok.slice(0, 6) + '…');
    }
    for (const m of src.match(/ById\s*\(\s*['"`][^'"`]*['"`]/g) || []) idLike.push(path.basename(f) + ': ' + m);
  }
  check('no Drive, folder or script id in any drive-sync/ file (ids live in Script Properties)',
        files.length > 0 && !idLike.length, files.length ? idLike.join('; ') : 'no files');
  const gsCode = GS.map(f => code(fs.readFileSync(f, 'utf8'))).join('\n');
  check('the folder ids are read from Script Properties', /PropertiesService\s*\.\s*getScriptProperties\s*\(/.test(gsCode));
  const BANNED = [/\bMailApp\b/, /\bGmailApp\b/, /\bUrlFetchApp\b/, /\bPermissions\b/, /\bsetSharing\s*\(/,
                  /\badd(Viewer|Editor|Commenter)s?\s*\(/, /\bget(Download)?Url\s*\(/, /\bweb(View|Content)Link\b/];
  const hits = BANNED.filter(rx => rx.test(gsCode)).map(String);
  check('it never shares, links or e-mails a file (no MailApp, sharing, permissions, URLs)', GS.length > 0 && !hits.length,
        GS.length ? hits.join(' ') : 'no .gs files');
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
