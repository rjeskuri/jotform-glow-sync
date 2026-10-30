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
 *     -> {moves, merges, waiting, unknown, refused, remove}
 *
 *   sourceFolders  [{id, name, subfolders: [{id, name, updated: Date, folders: [{id, name}], trashed,
 *                                            files: [{id, name, size, updated: Date}]}]}]
 *                  the folders of Ryan's My Drive; only `Attendance photos - <Region>` counts,
 *                  with the prefix exactly so (case and spacing included). A subfolder's `updated`
 *                  is when the folder itself last changed, `folders` its own subfolders, `trashed`
 *                  true when it is in Drive's trash (#144: its `files` are then what Jotform wrote
 *                  into it after the mover trashed it, and nothing a person trashed)
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
 *   remove   [{region, id, name}]          (#144) a subfolder of a known region's folder that is not
 *            in the trash, has no file and no subfolder, and has itself not changed for at least
 *            settleMinutes (exactly settleMinutes counts, as for files): the mover trashes it
 *            after re-listing it. Without `updated` or `folders` it is never removed (refuse
 *            rather than guess). A subfolder this run moves files out of had files, so it is
 *            removed on a later run, if at all.
 *
 * A subfolder with no files is never moved or merged. A subfolder in the trash with files is
 * planned like any other (move, merge with kept, waiting, refused: the rescue, #144); one with
 * no files is in no list. Any other folder is in no list. The planner touches no Google service
 * and does not change its inputs (the dry run's plan).
 *
 * The entry points (top-level functions whose names do not end in `_`) are run with fake
 * DriveApp / Drive / ScriptApp / PropertiesService / LockService objects: with fictional ids
 * in Script Properties they may call only the methods in ALLOW below (reading, the trigger
 * builder, and on the apply path the advanced Drive service's Files.create / Files.update with
 * supportsAllDrives: true - never DriveApp's moveTo, which Drive refuses into a Shared Drive
 * (#132); never sharing, links, copies or mail); with no Script Properties at all they make no
 * *ById call and change nothing. Trash (#144) is allowed only as TRASH_RULES and UPDATE_RULES
 * below say: an empty, settled subfolder of a configured source folder, by Drive.Files.update
 * {trashed: true} inside the one trash helper, moveToTrash_(id, protectedIds), which refuses
 * before any Drive call a configured SOURCE_/TARGET_FOLDER_ id and the Shared Drive's root
 * (#185 reuses it); and a rescued file's {trashed: false} in the same Files.update as its move.
 * Never a file, a non-empty folder, a source folder itself, anything on the Shared Drive, a
 * permanent delete or emptyTrash.
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
    remove: list(p, 'remove').map(w => [w.region, w.id, w.name].join('|')).sort(),
  };
}
const KEYS = ['moves', 'merges', 'waiting', 'refused', 'unknown', 'remove'];
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

/**
 * #144: each subfolder's own state, from a PRNG of its own (the layouts above stay as they were):
 * `updated` (the folder itself, ages straddling the settle time), `folders` (now and then one),
 * `trashed` (now and then); an empty one now and then without `updated` or `folders`.
 */
function decorate(sources, seed, k, nowMs, settle) {
  const r = prng(5000 + seed * 10 + k);
  for (const s of sources) {
    for (const sf of s.subfolders) {
      sf.trashed = r() < 0.15;
      sf.folders = r() < 0.15 ? [{ id: sf.id + '-in', name: 'Morning Roots 2026-10-01' }] : [];
      sf.updated = nowMs - Math.round(r() * settle * 4 * 60) * 1000;
      if (!sf.files.length && r() < 0.1) delete sf[r() < 0.5 ? 'updated' : 'folders'];
    }
  }
  return sources;
}

/**
 * #144: now and then, beside a subfolder with photos in a region that has a target, a twin of the SAME name on the
 * other side of the trash (a live one beside one in the trash, or the reverse), with photos of its own (never on the
 * Shared Drive), before or after it. Returns the groups [{region, name, members}], which oracle() leaves to groupCheck.
 */
function addTwins(sources, targets, seed, k, nowMs, settle) {
  const r = prng(9000 + seed * 10 + k);
  const groups = [];
  for (const s of sources) {
    const region = s.name.slice(PREFIX.length);
    if (!s.name.startsWith(PREFIX) || !REGIONS.includes(region) || !own(targets, region)) continue;
    const withFiles = s.subfolders.filter(x => x.files.length);
    if (!withFiles.length || r() < 0.3) continue;
    const orig = withFiles[Math.floor(r() * withFiles.length)];
    const twin = { id: orig.id + '-twin', name: orig.name, trashed: !orig.trashed, folders: [], updated: nowMs - OLD * MIN,
                   files: [0, 1].slice(0, 1 + Math.floor(r() * 2)).map(j => ({
                     id: orig.id + '-twin-f' + j, name: 'IMG_3' + j + Math.floor(r() * 10) + '.jpg', size: 20000 + Math.floor(r() * 9000),
                     updated: nowMs - Math.round(r() * settle * 4 * 60) * 1000 })) };
    s.subfolders.splice(s.subfolders.indexOf(orig) + (r() < 0.5 ? 0 : 1), 0, twin);
    groups.push({ region, name: orig.name, members: [orig, twin] });
  }
  return groups;
}

/**
 * The one-per-name-per-run rule for a group of same-name subfolders, in or out of the trash, whichever the planner
 * takes first: one still uploading waits; with the name twice on the Shared Drive, a settled one is refused; otherwise
 * exactly one settled copy moves (the name not there: all its files) or merges files in (the name there once), and every
 * other settled copy with files to move waits - a copy whose files are all there already is a merge of nothing, never
 * waiting. '' when the plan keeps it, else what is wrong.
 */
function groupCheck(g, p, tgt, nowMs, settle) {
  const where = id => KEYS.filter(k2 => list(p, k2).some(e => e.id === id));
  const entry = (k2, id) => list(p, k2).find(e => e.id === id) || {};
  const there = tgt.subfolders.filter(t => t.name === g.name);
  const problems = [], claimers = [];
  let contenders = 0;
  for (const sf of g.members) {
    const w = where(sf.id).join(',');
    const newest = Math.max(...sf.files.map(f => f.updated));
    if (nowMs - newest < settle * MIN) { if (w !== 'waiting') problems.push(sf.id + ' still uploading, but in ' + (w || 'no list')); continue; }
    if (there.length > 1) { if (w !== 'refused') problems.push(sf.id + ' (name twice there) in ' + (w || 'no list')); continue; }
    const dup = f => !!there.length && there[0].files.some(t => t.name === f.name && t.size === f.size);
    const toMove = sf.files.filter(f => !dup(f)).map(f => f.id).sort();
    if (!toMove.length) {
      if (w !== 'merges' || (entry('merges', sf.id).files || []).length) problems.push(sf.id + ' (all there already) in ' + (w || 'no list'));
      continue;
    }
    contenders++;
    const k2 = there.length ? 'merges' : 'moves';
    if (w === k2) {
      const e = entry(k2, sf.id);
      if ((there.length ? e.into !== there[0].id : e.to !== tgt.id) || !same((e.files || []).map(fid).sort(), toMove)) {
        problems.push(sf.id + ' ' + k2 + ' wrongly: ' + JSON.stringify(e));
      }
      claimers.push(sf.id);
    } else if (w !== 'waiting') problems.push(sf.id + ' in ' + (w || 'no list') + ', not ' + k2 + ' or waiting');
  }
  if (contenders && claimers.length !== 1) {
    problems.push(claimers.length + ' of ' + contenders + ' settled same-name copies ' + (there.length ? 'merged' : 'moved') + ' (one per name per run)');
  }
  return problems.length ? g.region + ' "' + g.name + '": ' + problems.join('; ') : '';
}

/** What the plan must be, worked out from the rules alone (the subfolders in `grouped` are groupCheck's). */
function oracle(sources, targets, nowMs, settle, grouped) {
  const out = { moves: [], merges: [], waiting: [], refused: [], unknown: [], remove: [] }, empty = [], ignored = [];
  const trashedEmpty = [], rescued = [];
  for (const s of sources) {
    if (!s.name.startsWith(PREFIX)) { ignored.push(s.id); s.subfolders.forEach(x => ignored.push(x.id)); continue; }
    const region = s.name.slice(PREFIX.length);
    const tgt = REGIONS.includes(region) && own(targets, region) ? targets[region] : undefined;
    if (!tgt) { out.unknown.push(s.id); s.subfolders.forEach(x => ignored.push(x.id)); continue; }
    for (const sf of s.subfolders) {
      if (grouped && grouped.has(sf.id)) continue;
      const key = [region, sf.id, sf.name];
      if (!sf.files.length) {
        if (sf.trashed) { trashedEmpty.push(sf.id); continue; }
        empty.push(sf.id);
        if (Array.isArray(sf.folders) && !sf.folders.length && typeof sf.updated === 'number' &&
            nowMs - sf.updated >= settle * MIN) out.remove.push(key.join('|'));
        continue;
      }
      if (sf.trashed) rescued.push(sf.id);
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
  return { want: out, empty, ignored, trashedEmpty, rescued };
}

const NOWS = [Date.UTC(2027, 2, 5, 8, 0, 0), Date.UTC(2025, 11, 31, 23, 30, 0), Date.UTC(2026, 9, 21, 14, 7, 30)];
const SETTLES = [10, 15, 3];
const seen = { moves: 0, merges: 0, waiting: 0, refused: 0, unknown: 0, remove: 0, kept: 0, sameSizeMoved: 0, empty: 0,
               multiFileMoves: 0, emptyNotSettled: 0, emptyWithFolder: 0, emptyUnknownState: 0, trashedEmpty: 0,
               rescuedActed: 0, rescuedWaitingOrRefused: 0, sameNameMoved: 0, sameNameMerged: 0, sameNameWaitOrRefuse: 0 };
let runs = 0;
for (let seed = 1; seed <= 8; seed++) {
  for (let k = 0; k < NOWS.length; k++) {
    const nowMs = NOWS[k], settle = SETTLES[(seed + k) % SETTLES.length];
    const { sources, targets } = layout(seed, nowMs, settle);
    decorate(sources, seed, k, nowMs, settle);
    const groups = addTwins(sources, targets, seed, k, nowMs, settle);
    const grouped = new Set([].concat(...groups.map(g => g.members.map(x => x.id))));
    const { want, empty, ignored, trashedEmpty, rescued } = oracle(sources, targets, nowMs, settle, grouped);
    for (const g of groups) {   // the kinds of same-name group the table holds (each must occur)
      const there = targets[g.region].subfolders.filter(t => t.name === g.name).length;
      const settledBoth = g.members.every(x => nowMs - Math.max(...x.files.map(f => f.updated)) >= settle * MIN);
      if (!settledBoth || there > 1) seen.sameNameWaitOrRefuse++;
      else if (there) seen.sameNameMerged++;
      else seen.sameNameMoved++;
    }
    for (const key of KEYS) seen[key] += want[key].length;
    seen.kept += want.merges.filter(m => m.split('|')[5]).length;
    seen.multiFileMoves += want.moves.filter(m => m.split('|')[4].includes(',')).length;   // a move of 2+ files
    seen.empty += empty.length;
    seen.trashedEmpty += trashedEmpty.length;
    const inList = (k2, x) => want[k2].some(e => e.split('|')[1] === x);
    seen.rescuedActed += rescued.filter(x => inList('moves', x) || inList('merges', x)).length;
    seen.rescuedWaitingOrRefused += rescued.filter(x => inList('waiting', x) || inList('refused', x)).length;
    for (const s of sources) for (const sf of s.subfolders) {
      if (sf.files.length || sf.trashed || !empty.includes(sf.id)) continue;
      if (!Array.isArray(sf.folders) || typeof sf.updated !== 'number') seen.emptyUnknownState++;
      else if (sf.folders.length) seen.emptyWithFolder++;
      else if (nowMs - sf.updated < settle * MIN) seen.emptyNotSettled++;
    }
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
    for (const key of KEYS) got[key] = got[key].filter(e => !grouped.has(e.split('|')[1]));   // groupCheck's
    const groupProblems = p ? groups.map(g => groupCheck(g, p, targets[g.region], nowMs, settle)).filter(Boolean) : [];
    const label = 'seed ' + seed + ', now ' + new Date(nowMs).toISOString() + ', settle ' + settle + 'm';
    check(label + ': moves (each with all its files), merges, waiting, refused, unknown and remove are the rules\' answer ' +
          '(a subfolder in the trash with files planned like any other; a same-name pair in and out of the trash: one per name)',
          !error && same(got, want) && !groupProblems.length,
          error || (same(got, want) ? '' : show(got, want)) + (groupProblems.length ? ' SAME NAME: ' + groupProblems.join(' | ') : ''));
    const all = ids(p);
    const wrong = empty.filter(x => acted(p).some(e => e.id === x)).concat(ignored.filter(x => all.has(x)))
      .concat(trashedEmpty.filter(x => all.has(x)).map(x => x + ' (in the trash, empty)'));
    check(label + ': no empty subfolder moved; nothing outside a known region\'s folder planned; an empty one in the trash in no list',
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

console.log('\nplanMoves_ — an emptied subfolder is removed once it has settled (#144)');
{
  const sub = (id, name, ageMin, extra) => Object.assign({ id, name, files: [], folders: [], trashed: false, updated: NOW - ageMin * MIN },
                                                          extra || {});
  const sources = [
    { id: 'src-af', name: 'Attendance photos - Africa', subfolders: [
      sub('e1', 'Bright Stars 2026-10-14', 10 - 1 / 60),   // 9m59s
      sub('e2', 'Rising Lights 2026-10-14', 10),           // exactly 10m
      sub('e3', 'Golden Flames 2026-10-13', 25),
      sub('e4', 'Silver Voices 2026-10-13', OLD, { folders: [{ id: 'e4-in', name: 'Silver Voices 2026-10-13 extra' }] }),
      sub('e5', 'Morning Wings 2026-10-12', OLD, { trashed: true }),
      { id: 'e6', name: 'Evening Roots 2026-10-12', files: [], folders: [] },                        // no `updated`
      { id: 'e7', name: 'Evening Stars 2026-10-12', files: [], updated: NOW - OLD * MIN },          // no `folders`
      sub('e8', 'Golden Roots 2026-10-11', OLD, { files: [file('e8-f', 'IMG_100.jpg', 1000, OLD)] }),
      sub('e9', 'Rising Roots 2026-10-11', OLD, { files: [file('e9-f', 'IMG_100.jpg', 1100, 2)] }),
      sub('e10', 'Morning Stars 2026-10-11', OLD, { files: [file('e10-f', 'IMG_100.jpg', 1200, OLD)] }),   // kept only
    ] },
    { id: 'src-tp', name: 'Attendance photos - Template', subfolders: [sub('t1', 'Bright Wings 2026-10-10', 60)] },
    { id: 'src-eu', name: 'Attendance photos - Europe', subfolders: [sub('x1', 'Bright Roots 2026-10-10', OLD)] },
    { id: 'src-x', name: 'Receipts - Africa', subfolders: [sub('x2', 'Silver Roots 2026-10-10', OLD)] },
  ];
  const targets = Object.assign(target('Africa', [{ id: 'sd-empty', name: 'Golden Stars 2026-10-01', files: [] },
                                                  { id: 'sd-ms', name: 'Morning Stars 2026-10-11', files: [{ id: 't-ms', name: 'IMG_100.jpg', size: 1200 }] }]),
                                target('Template'));
  const nm = {};
  for (const s of sources) for (const x of s.subfolders) nm[x.id] = x.name;
  const rem = (region, id) => region + '|' + id + '|' + nm[id];
  const r10 = plan(sources, targets, NOW, 10);
  check('settle 10: empty, no subfolder, unchanged exactly 10m, 25m and 60m (Africa, Template): removed; 9m59s not',
        same(norm(r10.plan).remove, [rem('Africa', 'e2'), rem('Africa', 'e3'), rem('Template', 't1')]),
        r10.error || show(norm(r10.plan).remove, [rem('Africa', 'e2'), rem('Africa', 'e3'), rem('Template', 't1')]));
  const removed = new Set(list(r10.plan, 'remove').map(e => e.id));
  const never = [['e4', 'a subfolder of its own'], ['e5', 'in the trash already'], ['e6', 'no `updated`'], ['e7', 'no `folders`'],
                 ['e8', 'a settled file (it moves)'], ['e9', 'a file within the settle time (it waits)'],
                 ['e10', 'only files kept by a merge'], ['x1', 'an unknown region\'s folder'], ['x2', 'not an `Attendance photos -` folder'],
                 ['src-af', 'the source folder itself'], ['src-tp', 'the source folder itself'], ['sd-empty', 'an empty Shared Drive folder']];
  const wrongly = never.filter(([id]) => removed.has(id)).map(([id, why]) => id + ' (' + why + ')');
  check('…and beside them never removed: a subfolder with a subfolder, one in the trash (in no list at all), one whose state is ' +
        'unknown, any with a file (moved, waiting, kept), another folder\'s, a source folder itself, anything on the Shared Drive',
        !!r10.plan && removed.size > 0 && !wrongly.length && !ids(r10.plan).has('e5'),
        r10.error || (removed.size ? wrongly.join(', ') + (ids(r10.plan).has('e5') ? ' e5 in a list' : '') : 'nothing removed at all'));
  const r30 = plan(sources, targets, NOW, 30);
  check('settle 30: only the 60-minute one is removed', same(norm(r30.plan).remove, [rem('Template', 't1')]),
        r30.error || JSON.stringify(norm(r30.plan).remove));
  const later = plan(sources, targets, NOW + 60 * MIN, 10);
  check('an hour later: the 9m59s one is removed too (age from `now`); still none of the never-removed',
        same(norm(later.plan).remove, [rem('Africa', 'e1'), rem('Africa', 'e2'), rem('Africa', 'e3'), rem('Template', 't1')]),
        later.error || JSON.stringify(norm(later.plan).remove));
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

console.log('\nplanMoves_ — run after run, 15 minutes apart: each emptied subfolder is removed on a later run, never one with files (#144)');
{
  // the model of Drive: a move or merge takes the files out and the subfolder counts as changed then (Drive may
  // mark it so); a removal puts the subfolder in the trash, where it stays (the next plan sees it trashed)
  for (let seed = 1; seed <= 6; seed++) {
    const r = prng(300 + seed);
    let n = 0;
    const id = p => p + seed + '-' + (++n);
    const names = ['Bright Stars 2026-10-14', 'Rising Lights 2026-10-14', 'Golden Flames 2026-10-13'];
    const targets = { Africa: { id: 'tgt-af-' + seed, subfolders: [] }, Template: { id: 'tgt-tp-' + seed, subfolders: [] } };
    const sources = ['Africa', 'Template'].map(region => ({ id: id('src'), name: PREFIX + region, subfolders: [] }));
    const start = NOW;
    for (const s of sources) {
      const region = s.name.slice(PREFIX.length);
      for (const nm of names) {
        if (r() < 0.5) {
          targets[region].subfolders.push({ id: id('tsub'), name: nm, files: [100, 101].filter(() => r() < 0.6)
            .map(k => ({ id: id('t'), name: 'IMG_' + k + '.jpg', size: k * 10 })) });
        }
        const copies = 1 + Math.floor(r() * 3);
        for (let c = 0; c < copies; c++) {
          s.subfolders.push({ id: id('sub'), name: nm, folders: [], trashed: false, updated: start - OLD * MIN,
                              files: [100, 101, 102].filter(() => r() < 0.6)
                                .map(k => ({ id: id('f'), name: 'IMG_' + k + '.jpg', size: r() < 0.7 ? k * 10 : k * 10 + 1, updated: start - OLD * MIN })) });
        }
      }
      // emptied before the first run (settled), and one Jotform made 2 minutes before it (not yet)
      s.subfolders.push({ id: id('old'), name: 'Silver Roots 2026-10-09', files: [], folders: [], trashed: false, updated: start - OLD * MIN });
      s.subfolders.push({ id: id('new'), name: 'Morning Roots 2026-10-15', files: [], folders: [], trashed: false, updated: start - 2 * MIN });
    }
    const all = [].concat(...sources.map(s => s.subfolders));
    const hadFiles = new Set(all.filter(x => x.files.length).map(x => x.id));
    const emptiedOn = {}, removedOn = {}, problems = [];
    let runsUsed = 0, error = '', settledAll = false;
    for (let run = 0; run < 12; run++) {
      const at = start + run * 15 * MIN;
      const got = plan(sources, targets, at, 10);
      if (got.error) { error = got.error; break; }
      runsUsed = run + 1;
      const p = got.plan;
      for (const e of list(p, 'remove')) {
        const sf = all.find(x => x.id === e.id);
        if (!sf) { problems.push('run ' + run + ': removed an unknown id ' + e.id); continue; }
        if (sf.files.length) problems.push('run ' + run + ': removed ' + e.id + ' with files');
        if (sf.trashed) problems.push('run ' + run + ': removed ' + e.id + ' again');
        if (at - sf.updated < 10 * MIN) problems.push('run ' + run + ': removed ' + e.id + ' changed ' + (at - sf.updated) / MIN + 'm ago');
      }
      if (!list(p, 'moves').length && !list(p, 'merges').some(m => (m.files || []).length) && !list(p, 'waiting').length &&
          !list(p, 'remove').length) { settledAll = true; break; }
      for (const s of sources) {
        const region = s.name.slice(PREFIX.length);
        for (const m of list(p, 'moves').filter(x => x.region === region).concat(list(p, 'merges').filter(x => x.region === region))) {
          const from = s.subfolders.find(x => x.id === m.id);
          let into = m.into ? targets[region].subfolders.find(x => x.id === m.into) : null;
          if (!m.into) { into = { id: 'made-' + m.id, name: m.name, files: [] }; targets[region].subfolders.push(into); }
          for (const f of (m.files || []).map(fid)) {
            const i = from ? from.files.findIndex(x => x.id === f) : -1;
            if (i >= 0 && into) into.files.push(from.files.splice(i, 1)[0]);
          }
          if (from && (m.files || []).length) {
            from.updated = at;
            if (!from.files.length) emptiedOn[from.id] = run;
          }
        }
      }
      for (const e of list(p, 'remove')) {
        const sf = all.find(x => x.id === e.id);
        if (sf && !sf.trashed) { sf.trashed = true; removedOn[sf.id] = run; }
      }
    }
    const left = all.filter(x => !x.files.length && !x.trashed).map(x => x.id);
    const tooSoon = Object.keys(removedOn).filter(x => own(emptiedOn, x) && removedOn[x] <= emptiedOn[x]);
    const keptRemoved = all.filter(x => x.files.length && own(removedOn, x.id)).map(x => x.id);
    const fresh = all.filter(x => /^new/.test(x.id)).map(x => x.id);
    check('seed ' + seed + ': within ' + runsUsed + ' run(s) everything settles and every empty subfolder is in the trash',
          !error && settledAll && !left.length && !problems.length, error || problems.concat(left.map(x => x + ' left')).join(', '));
    check('seed ' + seed + ': each subfolder a run emptied is removed on a LATER run; one still holding kept files is never removed; ' +
          'the one Jotform had just made is not removed on the first run',
          !error && !tooSoon.length && !keptRemoved.length && Object.keys(emptiedOn).length > 0 &&
          Object.keys(emptiedOn).every(x => own(removedOn, x)) && fresh.every(x => removedOn[x] > 0) &&
          [...hadFiles].some(x => own(removedOn, x)),
          error || JSON.stringify({ tooSoon, keptRemoved, emptiedOn, removedOn }));
  }
}

console.log('\nplanMoves_ — the dry run: a plan and no side effects');
{
  const { sources, targets } = layout(42, NOW, 10);
  decorate(sources, 42, 0, NOW, 10);
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
             'searchFiles', 'getFiles', 'getFilesByName', 'getFilesByType'],
  Folder: ['getId', 'getName', 'getFolders', 'getFiles', 'getFoldersByName', 'getFilesByName', 'getFilesByType', 'createFolder',
           'moveTo', 'addFile', 'removeFile', 'addFolder', 'removeFolder', 'getLastUpdated', 'getDateCreated', 'getParents',
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
const WRITES = c => /\.(moveTo|createFolder|addFile|removeFile|addFolder|removeFolder|setTrashed)$/.test(c) ||
                    c === 'Drive.Files.update' || c === 'Drive.Files.create';

// Script Properties: SOURCE_FOLDER_<KEY> and TARGET_FOLDER_<KEY> per region (drive-sync/README.md)
const PROP_KEYS = { Africa: 'AFRICA', Asia: 'ASIA', 'Latin America': 'LATIN_AMERICA', 'U.S': 'US', Template: 'TEMPLATE' };
// the fake My Drive (#132, #144). Each subfolder: [name, files [[file, size, age in minutes, 'explicit' when a person
// trashed it]], {age: the folder's own age in minutes (default OLD), trashed: in Drive's trash, folders: [[name, files]]}].
// Africa: a settled, a still-uploading and a resubmitted subfolder; two emptied by earlier runs (settled: trashed); one
// Jotform has just made (no file yet: not trashed this run); one holding a subfolder (never trashed); two in the trash with
// photos Jotform re-sent into them (rescued as moves). Asia: a settled one, either side of the 10-minute settle time a
// 9-minute-old (waits) and an 11-minute-old (moves), an emptied one whose name is on the Shared Drive already (trashed), and
// in the trash: one rescued as a merge (one photo kept), one empty (ignored), one whose only photo a person trashed (left
// alone). Latin America: one refused (its name twice there; never trashed) and, in the trash, one whose photo was just
// re-sent (waits) and one refused. U.S: no subfolder at all. Template: one emptied and settled (trashed).
const EMPTIED = 'Golden Roots 2026-10-12';
const FAKE_SOURCES = {
  Africa: [['Bright Stars 2026-10-14', [['IMG_4471.jpg', 2048, OLD], ['IMG_4472.jpg', 4096, OLD]]],
           ['Rising Lights 2026-10-15', [['IMG_4480.jpg', 1500, 1]]],
           ['Golden Flames 2026-10-13', [['IMG_5501.jpg', 3000, OLD], ['IMG_5502.jpg', 3100, OLD]]],
           ['Silver Roots 2026-10-11', []],
           ['Rising Roots 2026-10-11', []],
           ['Morning Flames 2026-10-16', [], { age: 3 }],
           ['Evening Wings 2026-10-10', [], { folders: [['Golden Lights 2026-10-10', [['IMG_4590.jpg', 1800, OLD]]]] }],
           ['Bright Wings 2026-10-09', [['IMG_4601.jpg', 2200, OLD]], { trashed: true }],
           ['Morning Stars 2026-10-02', [['IMG_4701.jpg', 2300, OLD], ['IMG_4702.jpg', 2400, OLD], ['IMG_4703.jpg', 2500, OLD]],
            { trashed: true }]],
  Asia: [['Morning Wings 2026-10-13', [['IMG_6001.jpg', 5000, OLD]]],
         ['Evening Lights 2026-10-15', [['IMG_6101.jpg', 2600, 9]]],
         ['Silver Voices 2026-10-15', [['IMG_6201.jpg', 2700, 11]]],
         [EMPTIED, []],   // what an earlier run's move left behind: its photos are on the Shared Drive already
         ['Rising Stars 2026-10-08', [['IMG_6401.jpg', 2900, OLD], ['IMG_6402.jpg', 3900, OLD]], { trashed: true }],
         ['Golden Wings 2026-10-07', [], { trashed: true }],
         ['Silver Lights 2026-10-06', [['IMG_6501.jpg', 2950, OLD, 'explicit']], { trashed: true }]],
  'Latin America': [['Silver Flames 2026-10-04', [['IMG_7101.jpg', 3300, OLD]]],
                    ['Evening Roots 2026-10-05', [['IMG_7201.jpg', 3400, 2]], { trashed: true }],
                    ['Bright Voices 2026-10-04', [['IMG_7301.jpg', 3500, OLD]], { trashed: true }]],
  'U.S': [],
  Template: [['Golden Stars 2026-10-03', []]],
};
// the fake Shared Drive: Africa already holds the resubmission's name, with one of its two photos; Asia the emptied
// subfolder's name with its photo, the rescued merge's name with the photo it keeps, and an empty folder of its own; Latin
// America each refused name twice (empty folders among them, which the mover reads: never trashed)
const FAKE_TARGETS = { Africa: [['Golden Flames 2026-10-13', [['IMG_5501.jpg', 3000]]]],
                       Asia: [[EMPTIED, [['IMG_6301.jpg', 2900]]],
                              ['Rising Stars 2026-10-08', [['IMG_6401.jpg', 2900], ['IMG_6400.jpg', 1000]]],
                              ['Evening Stars 2026-10-01', []]],
                       'Latin America': [['Silver Flames 2026-10-04', []], ['Silver Flames 2026-10-04', [['IMG_7100.jpg', 100]]],
                                         ['Bright Voices 2026-10-04', []], ['Bright Voices 2026-10-04', []]],
                       'U.S': [], Template: [] };
const SOURCE_SUBS = Object.values(FAKE_SOURCES).reduce((a, s) => a + s.length, 0);
const LATE_UPLOAD = 'IMG_7777.jpg';   // a photo Jotform adds to a subfolder after the planner has read it (opt.lateUploadTo)
const LATE_FOLDER = 'Morning Voices 2026-10-17';   // a folder that appears in a subfolder after the planner read it (opt.lateFolderTo)
// opt.twin: one name twice in one region's source folder, a live subfolder and one in the trash, each with a photo to move
const TWIN = 'Rising Voices 2026-10-03', TWIN_REGION = 'Template';
const TWIN_LIVE_DIR = 'S:' + TWIN_REGION + '/' + TWIN, TWIN_BIN_DIR = TWIN_LIVE_DIR + ' [in the trash]';   // fake labels (same name)
const TWIN_LIVE_PHOTO = 'IMG_8101.jpg', TWIN_BIN_PHOTO = 'IMG_8102.jpg';
const TWIN_INTO = 'T:' + TWIN_REGION + '/' + TWIN;
const FILE_STEMS = ['IMG_4471', 'IMG_4472', 'IMG_4480', 'IMG_4590', 'IMG_4601', 'IMG_4701', 'IMG_4702', 'IMG_4703', 'IMG_5501',
                    'IMG_5502', 'IMG_6001', 'IMG_6101', 'IMG_6201', 'IMG_6301', 'IMG_6400', 'IMG_6401', 'IMG_6402', 'IMG_6501',
                    'IMG_7100', 'IMG_7101', 'IMG_7201', 'IMG_7301', 'IMG_7777', 'IMG_8101', 'IMG_8102', 'IMG_9000', 'receipt'];
const S = (region, name, f) => 'S:' + region + '/' + name + (f ? '/' + f : '');
// the real run (#132): a folder of each moved subfolder's name made ONCE in its region folder, each of its files moved
// into it; the merges' new photos into the folder already there (no folder made for a merge); #144: the photos in
// subfolders in the trash the same way (two moves in Africa, a merge in Asia)
const EXPECTED_CREATED = ['T:Africa/Bright Stars 2026-10-14', 'T:Africa/Bright Wings 2026-10-09', 'T:Africa/Morning Stars 2026-10-02',
                          'T:Asia/Morning Wings 2026-10-13', 'T:Asia/Silver Voices 2026-10-15'].sort();
const RESCUED = [S('Africa', 'Bright Wings 2026-10-09', 'IMG_4601.jpg'), S('Africa', 'Morning Stars 2026-10-02', 'IMG_4701.jpg'),
                 S('Africa', 'Morning Stars 2026-10-02', 'IMG_4702.jpg'), S('Africa', 'Morning Stars 2026-10-02', 'IMG_4703.jpg'),
                 S('Asia', 'Rising Stars 2026-10-08', 'IMG_6402.jpg')];
const EXPECTED_MOVES = ['S:Africa/Bright Stars 2026-10-14/IMG_4471.jpg -> T:Africa/Bright Stars 2026-10-14',
                        'S:Africa/Bright Stars 2026-10-14/IMG_4472.jpg -> T:Africa/Bright Stars 2026-10-14',
                        'S:Asia/Morning Wings 2026-10-13/IMG_6001.jpg -> T:Asia/Morning Wings 2026-10-13',
                        'S:Asia/Silver Voices 2026-10-15/IMG_6201.jpg -> T:Asia/Silver Voices 2026-10-15',
                        'S:Africa/Golden Flames 2026-10-13/IMG_5502.jpg -> T:Africa/Golden Flames 2026-10-13',
                        RESCUED[0] + ' -> T:Africa/Bright Wings 2026-10-09',
                        RESCUED[1] + ' -> T:Africa/Morning Stars 2026-10-02',
                        RESCUED[2] + ' -> T:Africa/Morning Stars 2026-10-02',
                        RESCUED[3] + ' -> T:Africa/Morning Stars 2026-10-02',
                        RESCUED[4] + ' -> T:Asia/Rising Stars 2026-10-08'].sort();
const isRescue = m => RESCUED.some(l => m.startsWith(l + ' -> '));
const RESCUED_INTO = Object.fromEntries(EXPECTED_MOVES.filter(isRescue).map(m => m.split(' -> ')));
// #144, the real run: the emptied, settled source subfolders are trashed, and nothing else ...
const EXPECTED_TRASHED = [S('Africa', 'Silver Roots 2026-10-11'), S('Africa', 'Rising Roots 2026-10-11'), S('Asia', EMPTIED),
                          S('Template', 'Golden Stars 2026-10-03')].sort();
// ... and 15 minutes later those the first run emptied, and the one Jotform had just made (by then 18 minutes unchanged)
const EXPECTED_TRASHED_LATER = [S('Africa', 'Bright Stars 2026-10-14'), S('Africa', 'Morning Flames 2026-10-16'),
                                S('Asia', 'Morning Wings 2026-10-13'), S('Asia', 'Silver Voices 2026-10-15')].sort();
// the dry run's counts per region: `would remove N` (above) and `would rescue N` (the subfolders in the trash it would move
// photos out of: not the empty one, not the one whose only photo a person trashed, not a waiting or refused one)
const WOULD = { Africa: { remove: 2, rescue: 2 }, Asia: { remove: 1, rescue: 1 }, 'Latin America': { remove: 0, rescue: 0 },
                'U.S': { remove: 0, rescue: 0 }, Template: { remove: 1, rescue: 0 } };
const TRASHED_SUBS = Object.entries(FAKE_SOURCES).flatMap(([reg, subs]) => subs.filter(s => s[2] && s[2].trashed).map(s => S(reg, s[0])));
const inSub = (m, region, name) => m.startsWith('S:' + region + '/' + name + '/');
const FAKE_SETTLE_MIN = 10;   // SETTLE_MINUTES at the entry point (checked below)
const DRIVE_FOLDER_MIME = 'application/vnd.google-apps.folder';
// the Shared Drive's root folder: in Drive v3 its id is the drive's id, which every item on that drive reports as `driveId`
const DRIVE_ROOT_ID = 'fake-drive-root-1';
// the fake's Script Properties: each SOURCE_/TARGET_FOLDER_<KEY> holds the id of its folder (as on the live project)
const propIdOf = k => 'fake-id-' + String(k).replace(/[^A-Za-z0-9]+/g, '-');
const CONFIGURED_IDS = REGIONS.flatMap(reg => ['SOURCE_FOLDER_', 'TARGET_FOLDER_'].map(p => propIdOf(p + PROP_KEYS[reg])));
/**
 * The one trash helper (#144; #185, the Shared Drive's 90-day retention, reuses it): moveToTrash_(id, protectedIds)
 * trashes the item `id` by Drive.Files.update({trashed: true}, id, null, {supportsAllDrives: true}) and nothing else;
 * it refuses (throws) BEFORE any Drive call when `id` is not a non-empty string, when protectedIds is not an array, or
 * when `id` is in protectedIds. Every caller hands it at least every configured SOURCE_FOLDER_/TARGET_FOLDER_ id and
 * the Shared Drive's root (its drive id): PROTECTED_IDS here. Every trash any run makes goes through it.
 */
const TRASH_HELPER = 'moveToTrash_';
const PROTECTED_IDS = CONFIGURED_IDS.concat(DRIVE_ROOT_ID);

/**
 * What a run may trash, and what a Files.update may send (#144), as data. A trash no TRASH_RULES entry allows, an
 * update no UPDATE_RULES entry allows, and every NEVER call is banned (`banned` below); so is, whatever the rules say,
 * any trash outside moveToTrash_ and any trash of a configured folder or the Shared Drive's root. The rules are a union
 * (a trash is allowed when ANY entry allows it): a later ticket (#185, the Shared Drive's 90-day retention) adds its own
 * entry to TRASH_RULES, and nothing else here changes. #144 allows no Shared Drive item. The fake records each trash, by
 * any door, as {via, label, isFolder, role ('source-sub': a subfolder of a configured `Attendance photos - <Region>`
 * folder | 'source-root' | 'shared' | 'other' | 'file'), structural (a configured folder or the Shared Drive's root),
 * viaHelper (inside a moveToTrash_ call), wasTrashed, children (items in it at the trash), settled (itself unchanged
 * for FAKE_SETTLE_MIN at the trash)}; each Files.update as {kind ('move': resource {} | 'rescue': {trashed: false} |
 * 'trash': {trashed: true} | 'other'), resource, args, trash, wasTrashed, wasExplicit, fromTrashedSourceSub}.
 */
const TRASH_RULES = [
  { what: 'an empty, settled subfolder of a configured `Attendance photos - <Region>` folder, by Drive.Files.update {trashed: true} (#144)',
    allows: t => t.via === 'Drive.Files.update' && t.isFolder && t.role === 'source-sub' && !t.wasTrashed && t.children === 0 && t.settled },
];
const UPDATE_RULES = [
  { what: 'a move: resource {}, with addParents and removeParents', allows: o => o.kind === 'move' },
  { what: 'a rescue: {trashed: false} in the same call as the move, of a file in the trash only through its trashed source subfolder',
    allows: o => o.kind === 'rescue' && o.wasTrashed && !o.wasExplicit && o.fromTrashedSourceSub },
  { what: 'a trash that TRASH_RULES allows', allows: o => o.kind === 'trash' && !!o.trash && TRASH_RULES.some(r => r.allows(o.trash)) },
];
const NEVER = c => /\.(moveTo|setTrashed|makeCopy|setSharing|addViewers?|addEditors?|addCommenters?)$/.test(c) ||
                   /^Drive\.(Files\.(remove|delete|emptyTrash|trash|untrash|copy)$|Permissions\b)/.test(c);
function banned(r) {
  const why = t => [t.via, t.isFolder ? 'a folder' : 'a FILE', t.role, t.wasTrashed ? 'already in the trash' : '',
                    t.children ? t.children + ' item(s) in it' : '', t.settled ? '' : 'not settled'].filter(Boolean).join(', ');
  return [...new Set(r.calls.filter(NEVER).map(c => 'called ' + c)
    .concat(r.trashes.filter(t => t.structural).map(t => 'trashed ' + t.label + ' (a configured folder or the Shared Drive\'s root)'))
    .concat(r.trashes.filter(t => !t.viaHelper).map(t => 'trashed ' + t.label + ' outside ' + TRASH_HELPER))
    .concat(r.trashes.filter(t => !TRASH_RULES.some(rule => rule.allows(t))).map(t => 'trashed ' + t.label + ' (' + why(t) + ')'))
    .concat(r.ops.filter(o => o.op === 'update' && !UPDATE_RULES.some(rule => rule.allows(o)))
      .map(o => 'Files.update ' + JSON.stringify(o.resource) + ' on ' + (o.label || o.fileId))))];
}

/**
 * A Drive v3 search query (`q`) as a predicate on the fake's items: `'<id>' in parents`, `trashed = | != true|false`,
 * `mimeType = | != '<x>'`, `name = | != '<x>'`, joined by and / or / not and parentheses. Anything else throws (the
 * fake does not guess). Also returns the parent ids and names it names, and whether it says `trashed` explicitly.
 */
function parseDriveQuery(q) {
  const src = String(q), toks = [];
  const re = /\s*(?:'((?:[^'\\]|\\.)*)'|(!=|=|\(|\))|([A-Za-z]+))/y;
  let i = 0;
  while (i < src.length && src.slice(i).trim()) {
    re.lastIndex = i;
    const m = re.exec(src);
    if (!m) throw new Error('Files.list: the query cannot be read at "' + src.slice(i, i + 20) + '" (fake)');
    i = re.lastIndex;
    toks.push(m[1] !== undefined ? { str: m[1].replace(/\\(.)/g, '$1') } : m[2] ? { op: m[2] } : { word: m[3] });
  }
  const info = { parents: [], names: [], trashedClause: false };
  let p = 0;
  const fail = what => {
    throw new Error('Files.list: unsupported query (fake knows \'<id>\' in parents, trashed, mimeType, name; and/or/not): ' + what +
                    ' in ' + src);
  };
  const isWord = w => !!toks[p] && toks[p].word !== undefined && toks[p].word.toLowerCase() === w;
  const operator = () => { const t = toks[p++]; if (!t || (t.op !== '=' && t.op !== '!=')) fail('an operator expected'); return t.op; };
  const clause = () => {
    const t = toks[p++];
    if (!t) fail('a term expected');
    if (t.str !== undefined) {
      if (!isWord('in')) fail('`in` expected');
      p++;
      if (!toks[p] || toks[p].word !== 'parents') fail('`parents` expected');
      p++;
      info.parents.push(t.str);
      return m => m.parent === t.str;
    }
    if (t.word === 'trashed') {
      const op = operator(), v = toks[p++];
      if (!v || (v.word !== 'true' && v.word !== 'false')) fail('trashed = true | false expected');
      info.trashedClause = true;
      const want = v.word === 'true';
      return op === '=' ? m => m.trashed === want : m => m.trashed !== want;
    }
    if (t.word === 'mimeType' || t.word === 'name') {
      const op = operator(), v = toks[p++];
      if (!v || v.str === undefined) fail('a quoted value expected after ' + t.word);
      if (t.word === 'name' && op === '=') info.names.push(v.str);
      const get = m => (t.word === 'name' ? m.name : (m.isFolder ? DRIVE_FOLDER_MIME : m.mime));
      return op === '=' ? m => get(m) === v.str : m => get(m) !== v.str;
    }
    return fail('the term ' + JSON.stringify(t));
  };
  const unary = () => {
    if (isWord('not')) { p++; const u = unary(); return m => !u(m); }
    if (toks[p] && toks[p].op === '(') {
      p++;
      const e = orExpr();
      if (!toks[p] || toks[p].op !== ')') fail('`)` expected');
      p++;
      return e;
    }
    return clause();
  };
  const andExpr = () => { let a = unary(); while (isWord('and')) { p++; const l = a, r = unary(); a = m => l(m) && r(m); } return a; };
  function orExpr() { let a = andExpr(); while (isWord('or')) { p++; const l = a, r = andExpr(); a = m => l(m) || r(m); } return a; }
  const test = orExpr();
  if (p !== toks.length) fail('trailing terms');
  return Object.assign({ test }, info);
}

/**
 * Fake Google services recording every member asked for ('Type.member'), the file moves made ('<file label> ->
 * <folder label>'), the folders created ('<parent label>/<name>'), every advanced Drive write (ops: op, kind, the clock
 * when it came, resource, args) and read (reads: Files.list / Files.get with their args), every trash by any door
 * (trashes, as TRASH_RULES above reads them), the log and the source subfolders read. The fake Drive behaves as the
 * live one did on 2026-10-23 (#132): DriveApp's Folder.moveTo / File.moveTo INTO a Shared Drive (T:*) folder throws; the
 * advanced service's Files.update moves a file only with supportsAllDrives true, addParents an existing folder and
 * removeParents the file's current parent, and never moves a folder (teamDrivesFolderMoveInNotSupported); Files.create
 * makes a real folder under its one parent, found by name afterwards like any other.
 *
 * #144, the trash as Drive documents it (the ticket's research, 2026-10-30): an item in a trashed folder reads trashed
 * true, explicitlyTrashed false; DriveApp's doors list trashed items too, isTrashed() true. What no source says is taken
 * at its worst: a parent change alone does NOT take a file out of the trash (only {trashed: false} in the update does).
 * Files.update {trashed: true} trashes the item and everything in it. Files.list answers its `q` (parseDriveQuery; a q
 * is required), returns Shared Drive items only with supportsAllDrives and includeItemsFromAllDrives, at most two per
 * page with a nextPageToken (Drive may return short pages), only the default fields (kind, id, name, mimeType) unless
 * `fields` asks (`files(...)`, `nextPageToken`; `size` as a string, `modifiedTime` RFC 3339, as v3 does); Files.get the
 * same fields rule, and a Shared Drive item only with supportsAllDrives. A move bumps both folders' last-updated time.
 *
 * mode: 'ids' (every SOURCE_/TARGET_FOLDER_<KEY> set, and any other property a fictional id) | 'empty' (no Script
 * Properties). opt: failMoveOf (a subfolder name whose files' moves throw), failCreateOf (a folder name whose
 * Files.create throws), moveAdvanceMin / readAdvanceMin (the clock jumps on each file moved / on each source subfolder's
 * files read), lateUploadTo (a source subfolder name: right after the FIRST listing of its files returns, one more fresh
 * photo, LATE_UPLOAD, is in it - as Jotform may add one between the planner's read and the move; every later listing
 * through any door sees it), lateFolderTo (a folder LATE_FOLDER appears in it once the run has listed both its files
 * and its folders), twin ('live-first' | 'trashed-first': TWIN in Template twice, a live subfolder with one photo and a
 * subfolder in the trash with one photo Jotform re-sent, its name not on the Shared Drive), lateRemoveFrom ('<source
 * subfolder name>/<file name>': right after the first listing that photo is gone from Drive), rescueStaysTrashed (a
 * {trashed: false} move changes the parents but the file stays in the trash), rescueNotMoved (it takes the file out of
 * the trash but leaves its parents), targetName / sourceName ({region: folder name}). A listing is any door onto a
 * folder's files: Folder.getFiles / searchFiles / getFilesByName / getFilesByType, DriveApp.getFiles / searchFiles
 * (`'<id>' in parents` finds that folder, anything else every folder) / getFilesByName / getFilesByType, and
 * Drive.Files.list naming the folder in parents (its later pages are the same listing). readCount holds how often each
 * source subfolder's files were listed, firstListing the ids its first listing returned, idOf each item's id by label,
 * state(label) an item's trashed / explicitlyTrashed / parent label now; listedAll how often ANY folder's files were
 * listed (by label), lookups every `<folder label> getFoldersByName <name>` (a Files.list with a name clause too).
 */
function fakeEnv(mode, opt) {
  opt = opt || {};
  const calls = [], moved = [], attempted = [], created = [], ops = [], reads = [], trashes = [], logs = [], read = new Set();
  const lookups = [], readCount = {}, firstListing = {}, idOf = {}, gone = {}, allFolders = [], listedAll = {}, byLabel = {};
  const helper = { depth: 0, calls: [] };   // moveToTrash_ calls (runEntry wraps it): depth > 0 while one runs
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
  const register = (self, m) => {
    meta.set(self, m);
    byId[m.id] = self;
    if (!own(byLabel, m.label)) { byLabel[m.label] = self; idOf[m.label] = m.id; }
  };
  // DriveApp's moveTo: into a Shared Drive folder it fails as the live one did (#132)
  const moveTo = (self, dest) => {
    attempted.push(label(self));
    if (onSharedDrive(dest)) throw new Error('cannot use this operation on a shared drive item (fake)');
    moved.push(label(self) + ' -> ' + label(dest));
    return self;
  };
  const below = m => (m.isFolder ? [].concat(...m.kids.map(k => [meta.get(k)].concat(below(meta.get(k)))), m.files.map(f => meta.get(f))) : []);
  /** A trash by any door: recorded with the item's state at that moment, then done (the item and everything in it trashed). */
  const trashItem = (item, via) => {
    const m = meta.get(item);
    const t = { via, id: m.id, label: m.label, isFolder: m.isFolder, role: m.role, structural: !!m.structural,
                viaHelper: helper.depth > 0, wasTrashed: m.trashed,
                children: m.isFolder ? m.kids.length + m.files.length : 0, settled: clock.t - m.updatedAt >= FAKE_SETTLE_MIN * MIN, t: clock.t };
    trashes.push(t);
    m.trashed = true;
    m.explicitlyTrashed = true;
    for (const d of below(m)) d.trashed = true;
    return t;
  };
  const setTrashed = (self, v) => {
    if (v) trashItem(self, 'DriveApp.setTrashed');
    else Object.assign(meta.get(self), { trashed: false, explicitlyTrashed: false });
    return self;
  };
  const mkFile = (where, name, size, ageMin, explicit) => {
    const id = 'fake-file-' + (++n);
    const mime = /\.pdf$/.test(name) ? 'application/pdf' : 'image/jpeg';
    const m = { id, name, mime, size, label: where + '/' + name, parent: null, isFolder: false, role: 'file',
                updatedAt: clock.t - ageMin * MIN, trashed: !!explicit, explicitlyTrashed: !!explicit };
    const self = wrap('File', {
      getId: () => id, getName: () => name, getSize: () => size, getMimeType: () => mime,
      getLastUpdated: () => new D(m.updatedAt), getDateCreated: () => new D(m.updatedAt),
      moveTo: dest => moveTo(self, dest), isTrashed: () => m.trashed, setTrashed: v => setTrashed(self, v),
      getParents: () => iter(m.parent && byId[m.parent] ? [byId[m.parent]] : []),
    });
    register(self, m);
    return self;
  };
  /**
   * A source subfolder's files, listed through any door: counted, and right after the FIRST listing the subfolder
   * changes under the mover's feet when an option says so (the listing returned is what was there before). Any later
   * listing sees the change.
   */
  const listed = m => {
    read.add(m.label);
    readCount[m.label] = (readCount[m.label] || 0) + 1;
    if (opt.readAdvanceMin) clock.t += opt.readAdvanceMin * MIN;
    const snapshot = m.files.slice();
    m.seen.files = true;
    lateFolder(m);
    if (readCount[m.label] === 1) {
      firstListing[m.label] = snapshot.map(f => meta.get(f).id);
      if (opt.lateUploadTo === m.name) {   // one more photo arrives
        const late = mkFile(m.label, LATE_UPLOAD, 777, 0);
        Object.assign(meta.get(late), { parent: m.id, trashed: m.trashed });
        m.files.push(late);
      }
      const at = opt.lateRemoveFrom && opt.lateRemoveFrom.indexOf(m.name + '/') === 0 ?
        m.files.findIndex(f => meta.get(f).name === opt.lateRemoveFrom.slice(m.name.length + 1)) : -1;
      if (at >= 0) {   // that photo is gone from Drive
        const g = meta.get(m.files.splice(at, 1)[0]);
        gone[g.id] = g.label;
        delete byId[g.id];
      }
    }
    return snapshot;
  };
  /**
   * opt.lateFolderTo: once the run has listed both that subfolder's files and its folders (any door, any order: the
   * planner's read), a folder LATE_FOLDER appears in it; any later listing sees it.
   */
  const lateFolder = m => {
    if (!m.isSourceSub || opt.lateFolderTo !== m.name || m.lateDone || !m.seen.files || !m.seen.folders) return;
    m.lateDone = true;
    const k = mkFolder(m.label + '/' + LATE_FOLDER, LATE_FOLDER, [], [], false, 0);
    meta.get(k).parent = m.id;
    m.kids.push(k);
  };
  const foldersOf = m => {   // a listing of a folder's own folders (the snapshot is what was there before)
    const snap = m.kids.slice();
    m.seen.folders = true;
    lateFolder(m);
    return snap;
  };
  function mkFolder(lbl, name, kids, files, isSourceSub, ageMin, role, fixedId) {
    const id = fixedId || 'fake-folder-' + (++n);
    const age = ageMin === undefined ? OLD : ageMin;
    const m = { id, name, label: lbl, kids, files, parent: null, isFolder: true, isSourceSub,
                role: lbl.startsWith('T:') ? 'shared' : (role || 'other'),
                updatedAt: clock.t - age * MIN, createdAt: clock.t - age * MIN, trashed: false, explicitlyTrashed: false,
                seen: { files: false, folders: false } };
    m.listing = () => {
      listedAll[lbl] = (listedAll[lbl] || 0) + 1;
      return isSourceSub ? listed(m) : files.slice();
    };
    const self = wrap('Folder', {
      getId: () => id, getName: () => name, getFolders: () => iter(foldersOf(m)),
      getFiles: () => iter(m.listing()),
      searchFiles: () => iter(m.listing()),
      getFoldersByName: x => { lookups.push(lbl + ' getFoldersByName ' + x); return iter(kids.filter(k => meta.get(k).name === x)); },
      getFilesByName: x => iter(m.listing().filter(f => meta.get(f).name === x)),
      getFilesByType: x => iter(m.listing().filter(f => meta.get(f).mime === x)),
      createFolder: x => {
        const made = mkFolder(lbl + '/' + x, x, [], [], false, 0);
        kids.push(made);
        meta.get(made).parent = id;
        created.push(lbl + '/' + x);
        return made;
      },
      moveTo: dest => moveTo(self, dest),
      addFile: () => self, removeFile: () => self, addFolder: () => self, removeFolder: () => self,
      getLastUpdated: () => new D(m.updatedAt), getDateCreated: () => new D(m.createdAt),
      getParents: () => iter(m.parent && byId[m.parent] ? [byId[m.parent]] : []), isTrashed: () => m.trashed,
      searchFolders: () => iter(foldersOf(m)), setTrashed: v => setTrashed(self, v),
    });
    register(self, m);
    for (const k of kids) meta.get(k).parent = id;
    for (const f of files) meta.get(f).parent = id;
    allFolders.push(self);
    return self;
  }
  /** Fixtures in the trash before the run: the folder explicitly, what is in it through it. */
  const binned = self => {
    const m = meta.get(self);
    m.trashed = m.explicitlyTrashed = true;
    for (const d of below(m)) d.trashed = true;
  };
  // DriveApp's own file doors: every folder's files (each source subfolder counted), or one folder's for `'<id>' in parents`
  const everyFile = () => [].concat(...allFolders.map(f => meta.get(f).listing()));
  const searched = q => {
    const m = /'([^']+)'\s+in\s+parents/.exec(String(q));
    return m && byId[m[1]] && meta.get(byId[m[1]]).isFolder ? meta.get(byId[m[1]]).listing() : everyFile();
  };
  // the advanced Drive service, v3: Drive.Files.create(resource, mediaData, optionalArgs), Drive.Files.update(resource,
  // fileId, mediaData, optionalArgs), Drive.Files.list(optionalArgs), Drive.Files.get(fileId, optionalArgs), as strict as Drive is
  const allDrives = (op, args) => {
    if (!args || args.supportsAllDrives !== true) throw new Error(op + ': File not found (fake: supportsAllDrives is not true)');
  };
  const resourceOf = m => {
    const r = { kind: 'drive#file', id: m.id, name: m.name, mimeType: m.isFolder ? DRIVE_FOLDER_MIME : m.mime,
                parents: m.parent ? [m.parent] : [], trashed: m.trashed, explicitlyTrashed: m.explicitlyTrashed,
                modifiedTime: new Date(m.updatedAt).toISOString(), createdTime: new Date(m.createdAt || m.updatedAt).toISOString() };
    if (!m.isFolder) r.size = String(m.size);
    if (m.label.startsWith('T:')) r.driveId = DRIVE_ROOT_ID;
    return r;
  };
  const DEFAULT_FIELDS = ['kind', 'id', 'name', 'mimeType'];
  /** 'a, b(c, d), e' -> [{name: 'a', sub: null}, {name: 'b', sub: ['c', 'd']}, {name: 'e', sub: null}] */
  const fieldList = s => {
    const out = [];
    let depth = 0, cur = '';
    for (const ch of String(s) + ',') {
      if (ch === ',' && !depth) {
        const t = cur.trim();
        const m = /^([\w*]+)\s*(?:\((.*)\))?$/.exec(t);
        if (t) out.push(m ? { name: m[1], sub: m[2] === undefined ? null : m[2].split(',').map(x => x.trim()).filter(Boolean) } : { name: t, sub: null });
        cur = '';
        continue;
      }
      if (ch === '(') depth++;
      if (ch === ')') depth--;
      cur += ch;
    }
    return out;
  };
  const pick = (res, names) => {
    const o = {};
    for (const k of names) { if (k === '*') Object.assign(o, res); else if (k in res) o[k] = res[k]; }
    return o;
  };
  const shapeFile = (res, fields) => pick(res, fields ? fieldList(fields).map(f => f.name) : DEFAULT_FIELDS);
  const shapeList = (page, next, fields) => {
    if (!fields) {
      const out = { kind: 'drive#fileList', incompleteSearch: false, files: page.map(r => pick(r, DEFAULT_FIELDS)) };
      if (next) out.nextPageToken = next;
      return out;
    }
    const out = {};
    for (const f of fieldList(fields)) {
      if (f.name === '*') {
        Object.assign(out, { kind: 'drive#fileList', incompleteSearch: false, files: page.map(r => Object.assign({}, r)) });
        if (next) out.nextPageToken = next;
      } else if (f.name === 'files') {
        out.files = page.map(r => (f.sub && !f.sub.includes('*') ? pick(r, f.sub) : Object.assign({}, r)));
      } else if (f.name === 'nextPageToken') {
        if (next) out.nextPageToken = next;
      } else if (f.name === 'kind') out.kind = 'drive#fileList';
      else if (f.name === 'incompleteSearch') out.incompleteSearch = false;
    }
    return out;
  };
  const PAGE = 2, pageTokens = {};
  let pages = 0;
  const filesList = args => {
    args = args || {};
    reads.push({ op: 'list', t: clock.t, args: Object.assign({}, args) });
    let results, offset;
    if (args.pageToken) {
      const tok = pageTokens[args.pageToken];
      if (!tok || tok.q !== args.q) throw new Error('Files.list: invalid pageToken, or another q with it (fake)');
      results = tok.results;
      offset = tok.offset;
    } else {
      if (typeof args.q !== 'string' || !args.q.trim()) throw new Error('Files.list: no q (fake: the mover never lists every file)');
      const parsed = parseDriveQuery(args.q);
      const everyDrive = args.supportsAllDrives === true && args.includeItemsFromAllDrives === true;
      let candidates;
      if (parsed.parents.length) {
        candidates = [];
        for (const pid of parsed.parents) {
          const pi = byId[pid];
          if (!pi || !meta.get(pi).isFolder) continue;
          const pm = meta.get(pi);
          for (const nm of parsed.names) lookups.push(pm.label + ' getFoldersByName ' + nm);
          const kidsSnap = pm.kids.slice(), filesSnap = pm.listing();
          foldersOf(pm);
          candidates.push(...kidsSnap, ...filesSnap);
        }
      } else candidates = Object.values(byId);
      results = candidates.map(x => meta.get(x)).filter(m => (everyDrive || !m.label.startsWith('T:')) && parsed.test(m)).map(resourceOf);
      offset = 0;
    }
    const size = Math.min(PAGE, args.pageSize > 0 ? args.pageSize : PAGE);
    const page = results.slice(offset, offset + size);
    let next = null;
    if (offset + size < results.length) {
      next = 'fake-page-' + (++pages);
      pageTokens[next] = { q: args.q, results, offset: offset + size };
    }
    return shapeList(page, next, args.fields);
  };
  const filesGet = (fileId, args) => {
    reads.push({ op: 'get', t: clock.t, fileId, args: Object.assign({}, args) });
    const item = byId[fileId];
    if (!item) throw new Error('Files.get: File not found: ' + String(fileId) + ' (fake)');
    const m = meta.get(item);
    if (m.label.startsWith('T:') && !(args && args.supportsAllDrives === true)) {
      throw new Error('Files.get: File not found: ' + String(fileId) + ' (fake: a Shared Drive item needs supportsAllDrives)');
    }
    return shapeFile(resourceOf(m), args && args.fields);
  };
  const filesCreate = (resource, media, args) => {
    ops.push({ op: 'create', t: clock.t, args: Object.assign({}, args) });
    allDrives('Files.create', args);
    const r = resource || {};
    const parent = Array.isArray(r.parents) && r.parents.length === 1 ? byId[r.parents[0]] : null;
    if (!parent || !meta.get(parent).isFolder) throw new Error('Files.create: parents must be one existing folder id (fake)');
    if (r.mimeType !== DRIVE_FOLDER_MIME) throw new Error('Files.create: only a folder is created here, not ' + r.mimeType + ' (fake)');
    if (typeof r.name !== 'string' || !r.name) throw new Error('Files.create: a name is required (fake)');
    if (opt.failCreateOf && r.name === opt.failCreateOf) throw new Error('Drive said no (fake)');
    const made = mkFolder(label(parent) + '/' + r.name, r.name, [], [], false, 0);
    meta.get(parent).kids.push(made);
    meta.get(made).parent = meta.get(parent).id;
    created.push(label(parent) + '/' + r.name);
    return { id: meta.get(made).id, name: r.name, mimeType: DRIVE_FOLDER_MIME, parents: [meta.get(parent).id] };
  };
  const filesUpdate = (resource, fileId, media, args) => {
    const r = resource || {};
    const keys = Object.keys(r);
    const kind = !keys.length ? 'move' : keys.length === 1 && r.trashed === true ? 'trash' :
      keys.length === 1 && r.trashed === false ? 'rescue' : 'other';
    const op = { op: 'update', kind, t: clock.t, args: Object.assign({}, args), fileId: fileId, resource: Object.assign({}, r), ok: false };
    ops.push(op);
    allDrives('Files.update', args);
    const item = byId[fileId];
    if (!item) {
      if (gone[fileId]) attempted.push(gone[fileId]);
      throw new Error('Files.update: File not found: ' + String(fileId) + ' (fake)');
    }
    const m = meta.get(item);
    op.label = m.label;
    if (kind === 'trash') {
      if (args.addParents || args.removeParents) { op.kind = 'other'; throw new Error('Files.update: a trash moves nothing (fake)'); }
      op.trash = trashItem(item, 'Drive.Files.update');
      op.ok = true;
      return shapeFile(resourceOf(m), args.fields);
    }
    attempted.push(m.label);
    if (kind === 'other') throw new Error('Files.update: a resource of {' + keys.join(', ') + '} is never sent here (fake)');
    const fromItem = m.parent ? byId[m.parent] : null;
    const from = fromItem ? meta.get(fromItem) : null;
    if (kind === 'rescue') {
      Object.assign(op, { wasTrashed: m.trashed, wasExplicit: m.explicitlyTrashed,
                          fromTrashedSourceSub: !!from && from.role === 'source-sub' && from.trashed });
      if (!args.addParents || !args.removeParents) {
        op.kind = 'other';
        throw new Error('Files.update: {trashed: false} only in the same call as the parent move (fake)');
      }
    }
    if (m.isFolder) throw new Error('Files.update: teamDrivesFolderMoveInNotSupported: Moving folders into shared drives is not supported (fake)');
    const dest = args.addParents ? byId[args.addParents] : null;
    if (!dest || !meta.get(dest).isFolder) throw new Error('Files.update: addParents is not one existing folder id (fake)');
    if (args.removeParents !== m.parent) throw new Error('Files.update: removeParents is not the file\'s parent (fake)');
    if (opt.failMoveOf && from.name === opt.failMoveOf) throw new Error('Drive said no (fake)');
    if (kind === 'rescue' && opt.rescueNotMoved) {   // Drive says yes, takes it out of the trash, leaves it where it was
      Object.assign(m, { trashed: false, explicitlyTrashed: false });
      op.ok = true;
      return shapeFile(resourceOf(m), args.fields);
    }
    from.files.splice(from.files.indexOf(item), 1);
    meta.get(dest).files.push(item);
    m.parent = meta.get(dest).id;
    from.updatedAt = clock.t;
    meta.get(dest).updatedAt = clock.t;
    if (kind === 'rescue' && !opt.rescueStaysTrashed) Object.assign(m, { trashed: false, explicitlyTrashed: false });
    moved.push(m.label + ' -> ' + label(dest));
    op.ok = true;
    if (opt.moveAdvanceMin) clock.t += opt.moveAdvanceMin * MIN;
    return shapeFile(resourceOf(m), args.fields);
  };
  const propId = propIdOf;
  const sourceFolders = [], propFolders = {}, targetFolders = [];
  for (const region of REGIONS) {
    const subs = FAKE_SOURCES[region].map(([nm, fl, x]) => {
      x = x || {};
      const where = S(region, nm);
      const inner = (x.folders || []).map(([inm, ifl]) =>
        mkFolder(where + '/' + inm, inm, [], ifl.map(([f, size, age]) => mkFile(where + '/' + inm, f, size, age)), false));
      const sub = mkFolder(where, nm, inner, fl.map(([f, size, age, how]) => mkFile(where, f, size, age, how === 'explicit')), true,
                           x.age, 'source-sub');
      if (x.trashed) binned(sub);
      return sub;
    });
    if (opt.twin && region === TWIN_REGION) {   // the same name in and out of the trash, in the order opt.twin says
      const live = mkFolder(TWIN_LIVE_DIR, TWIN, [], [mkFile(TWIN_LIVE_DIR, TWIN_LIVE_PHOTO, 4100, OLD)], true, undefined, 'source-sub');
      const bin = mkFolder(TWIN_BIN_DIR, TWIN, [], [mkFile(TWIN_BIN_DIR, TWIN_BIN_PHOTO, 4200, OLD)], true, undefined, 'source-sub');
      binned(bin);
      subs.push(...(opt.twin === 'trashed-first' ? [bin, live] : [live, bin]));
    }
    const src = mkFolder('S:' + region, (opt.sourceName || {})[region] || PREFIX + region, subs, [], false, undefined, 'source-root',
                         propId('SOURCE_FOLDER_' + PROP_KEYS[region]));
    const tsubs = FAKE_TARGETS[region].map(([nm, fl]) => {
      const where = 'T:' + region + '/' + nm;
      return mkFolder(where, nm, [], fl.map(([f, size]) => mkFile(where, f, size, OLD)), false);
    });
    const tgt = mkFolder('T:' + region, (opt.targetName || {})[region] || region, tsubs, [], false, undefined, undefined,
                         propId('TARGET_FOLDER_' + PROP_KEYS[region]));
    meta.get(src).structural = meta.get(tgt).structural = true;
    sourceFolders.push(src);
    targetFolders.push(tgt);
    propFolders[propId('SOURCE_FOLDER_' + PROP_KEYS[region])] = src;
    propFolders[propId('TARGET_FOLDER_' + PROP_KEYS[region])] = tgt;
  }
  // the Shared Drive's root holds the region folders; its id is the drive's id
  meta.get(mkFolder('T:drive', 'GLOW Shared Drive', targetFolders, [], false, undefined, undefined, DRIVE_ROOT_ID)).structural = true;
  const receiptsSub = mkFolder('S:Receipts/Silver Roots 2026-10-01', 'Silver Roots 2026-10-01', [],
                               [mkFile('S:Receipts/Silver Roots 2026-10-01', 'receipt.pdf', 100, OLD)], false);
  const receiptsEmpty = mkFolder('S:Receipts/Rising Wings 2026-10-01', 'Rising Wings 2026-10-01', [], [], false);   // empty, settled
  const receipts = mkFolder('S:Receipts', 'Receipts', [receiptsSub, receiptsEmpty], [], false);
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
      getRootFolder: () => root, searchFolders: () => iter(top), searchFiles: q => iter(searched(q)),
      getFiles: () => iter(everyFile()), getFilesByName: x => iter(everyFile().filter(f => meta.get(f).name === x)),
      getFilesByType: x => iter(everyFile().filter(f => meta.get(f).mime === x)),
    }),
    Drive: wrap('Drive', {
      Files: wrap('Drive.Files', { list: filesList, get: filesGet, create: filesCreate, update: filesUpdate }),
      Drives: wrap('Drive.Drives', { get: x => ({ id: x, name: 'GLOW Shared Drive' }), list: () => ({ drives: [{ id: DRIVE_ROOT_ID, name: 'GLOW Shared Drive' }] }) }),
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
  /** The sandbox's clock: `new Date()` and `Date.now()` read clock.t (moved by the fakes, and by advance()). */
  const install = c => {
    c.__fakeClock = () => clock.t;
    vm.runInContext('(function () { const R = Date, now = __fakeClock;' +
                    ' class FakeDate extends R { constructor(...a) { if (a.length) super(...a); else super(now()); }' +
                    ' static now() { return now(); } } Date = FakeDate; })(); delete globalThis.__fakeClock;', c);
    D = vm.runInContext('Date', c);
  };
  const state = lbl => {
    const x = byLabel[lbl];
    if (!x) return null;
    const m = meta.get(x);
    return { trashed: m.trashed, explicitlyTrashed: m.explicitlyTrashed,
             parent: m.parent && byId[m.parent] ? meta.get(byId[m.parent]).label : null,
             children: m.isFolder ? m.kids.length + m.files.length : 0 };
  };
  const advance = min => { clock.t += min * MIN; };
  return { calls, moved, attempted, created, ops, reads, trashes, logs, read, readCount, firstListing, idOf, listedAll, lookups, t0,
           globals, install, state, advance, helper };
}

const violations = calls => calls.filter(c => {
  const i = c.lastIndexOf('.');
  const type = c.slice(0, i), member = c.slice(i + 1);
  return !(ALLOW[type] || []).includes(member);
});

const ENTRIES = GS.length ? loadGs.declarations(GS_SRC).filter(nm => !nm.endsWith('_') && ctx && typeof ctx[nm] === 'function') : [];
const RUNS = [];   // every entry-point run in this file, for the last check: nothing banned, ever
/** moveToTrash_ wrapped in the sandbox (a test replaces a top-level function by assigning it): its calls recorded. */
function spyTrashHelper(c, helper) {
  const orig = c[TRASH_HELPER];
  if (typeof orig !== 'function') return;
  c[TRASH_HELPER] = function (id, protectedIds) {
    helper.calls.push({ id: id, protectedIds: Array.isArray(protectedIds) ? protectedIds.slice() : protectedIds });
    helper.depth++;
    try { return orig.apply(this, arguments); } finally { helper.depth--; }
  };
}
/**
 * One entry point on a fresh fake Drive; the result's records are copies (state and idOf read the fake Drive as it is
 * now). Its `rerun(opt)` runs the same entry point again on the SAME fake Drive (the trigger's next run), with other
 * options and the records starting afresh; opt.advanceMin moves the clock on first.
 */
function runEntry(name, mode, opt) {
  opt = opt || {};
  const env = fakeEnv(mode, opt);
  let c = null;
  const once = () => {
    let threw = '';
    try {
      if (!c) { c = loadGs.sandbox(GS, env.globals); env.install(c); spyTrashHelper(c, env.helper); }
      vm.runInContext(name + '();', c, { timeout: 5000 });
    } catch (e) { threw = String(e && e.message || e); }
    const res = { helperCalls: env.helper.calls.slice(), name, threw, text: env.logs.join('\n'), calls: env.calls.slice(), moved: env.moved.slice(),
                  attempted: env.attempted.slice(), created: env.created.slice(), ops: env.ops.slice(), reads: env.reads.slice(),
                  trashes: env.trashes.slice(), read: new Set(env.read), readCount: Object.assign({}, env.readCount),
                  firstListing: Object.assign({}, env.firstListing), listedAll: Object.assign({}, env.listedAll),
                  lookups: env.lookups.slice(), idOf: env.idOf, state: env.state, t0: env.t0, rerun };
    RUNS.push(res);
    return res;
  };
  const rerun = next => {
    for (const k of Object.keys(opt)) delete opt[k];
    Object.assign(opt, next || {});
    for (const a of [env.calls, env.moved, env.attempted, env.created, env.ops, env.reads, env.trashes, env.logs, env.lookups,
                     env.helper.calls]) a.length = 0;
    env.read.clear();
    for (const o of [env.readCount, env.firstListing, env.listedAll]) for (const k of Object.keys(o)) delete o[k];
    if (next && next.advanceMin) env.advance(next.advanceMin);
    return once();
  };
  return once();
}
const runEntries = (mode, opt) => ENTRIES.map(name => runEntry(name, mode, opt));
const fileNamesIn = text => FILE_STEMS.filter(s => text.includes(s));
const trashedOf = r => r.trashes.map(t => t.label).sort();
/** The numbers the log gives next to `removed` / `trashed` (e.g. `4 folder(s) removed`, `removed 4`). */
const removedNumbers = text => [].concat(...text.split('\n').map(l =>
  [...l.matchAll(/\b(\d+)\b[^\n\d]{0,30}\b(?:removed|trashed)\b|\b(?:removed|trashed)\b[^\n\d]{0,30}?\b(\d+)\b/g)].map(m => Number(m[1] || m[2]))));
{
  check('there are entry points (top-level functions not ending in `_`)', ENTRIES.length > 0, ENTRIES.join(', ') || 'none');
  const full = runEntries('ids');
  const bad = full.flatMap(r => violations(r.calls).map(c => r.name + ': ' + c));
  check('with every region set up in Script Properties, every call (the full apply path included) is in the allow-list ' +
        '(no sharing, links, copies, mail; no DriveApp setTrashed)',
        ENTRIES.length > 0 && !bad.length, ENTRIES.length ? [...new Set(bad)].join(', ') : 'no entry points');
  const summary = rs => rs.map(r => r.name + ': ' + (r.threw || 'ok') + ' [' + r.calls.length + ' calls, ' + r.created.length +
                                    ' created, ' + r.moved.length + ' moves, ' + r.trashes.length + ' trashed]').join('; ');
  check('…and at least one entry point reads the fake Drive (the run is not vacuous)',
        full.some(r => r.read.size > 0), summary(full));
  // the entry point that writes (tries a move, or makes a folder): the real run
  const applier = full.find(r => r.attempted.length || r.created.length);
  const outcome = r => ({ created: r.created.slice().sort(), moved: r.moved.slice().sort() });
  const WANT = { created: EXPECTED_CREATED, moved: EXPECTED_MOVES };
  const tell = r => (r ? 'threw: ' + (r.threw || 'no') + '; made ' + JSON.stringify(r.created) + '; moved ' + JSON.stringify(r.moved) +
                         '; trashed ' + JSON.stringify(trashedOf(r)) + '; log: ' + r.text.slice(-600) : 'no applier');
  check('one entry point is the real run (#132, #144): each settled subfolder\'s files moved into a folder of its name made in the ' +
        'region folder, the resubmission\'s new photo merged into the folder already there, the photos re-sent into subfolders in ' +
        'the trash moved the same way (two moves, one merge), nothing else (not the uploading one, not a kept photo, not Receipts)',
        !!applier && !applier.threw && same(outcome(applier), WANT),
        applier ? applier.name + ': ' + (applier.threw || '') + ' ' + show(outcome(applier), WANT) : summary(full));
  check('…exactly one folder made per moved subfolder, through Drive.Files.create (none for a merge, none any other way)',
        !!applier && applier.ops.filter(o => o.op === 'create').length === EXPECTED_CREATED.length &&
        applier.created.length === EXPECTED_CREATED.length,
        applier ? applier.ops.filter(o => o.op === 'create').length + ' Files.create call(s); made ' + JSON.stringify(applier.created) : 'no applier');
  check('…nothing banned on the apply path (TRASH_RULES, UPDATE_RULES, NEVER): no DriveApp moveTo or setTrashed, no permanent ' +
        'delete or emptyTrash, no trash of a file, a non-empty or unsettled folder, a source folder itself or a Shared Drive item, ' +
        'no Files.update resource but a move\'s {} or a rescue\'s {trashed: false}',
        !!applier && !banned(applier).length, applier ? banned(applier).join('; ') : 'no applier');
  // #144, the definition of done: an emptied, settled source subfolder is trashed on apply ...
  check('…the emptied, settled source subfolders (two in Africa, one in Asia, one in Template) are trashed, once each, by ' +
        'Drive.Files.update {trashed: true}; nothing else is trashed',
        !!applier && same(trashedOf(applier), EXPECTED_TRASHED) && EXPECTED_TRASHED.every(l => applier.state(l).trashed) &&
        applier.trashes.every(t => t.via === 'Drive.Files.update'),
        applier ? show(applier.trashes.map(t => t.label + ' via ' + t.via).sort(), EXPECTED_TRASHED) : 'no applier');
  const shortOf = h => (Array.isArray(h.protectedIds) ? PROTECTED_IDS.filter(id => !h.protectedIds.includes(id)) : ['no protectedIds array']);
  check('…every trash goes through ' + TRASH_HELPER + ' (each folder trashed inside a call of it, one call per trash), and each ' +
        'call is handed every configured SOURCE_FOLDER_/TARGET_FOLDER_ id and the Shared Drive\'s root to protect',
        !!applier && applier.trashes.length > 0 && applier.trashes.every(t => t.viaHelper) &&
        applier.helperCalls.length === applier.trashes.length && applier.helperCalls.every(h => !shortOf(h).length),
        applier ? applier.trashes.filter(t => !t.viaHelper).map(t => 'outside: ' + t.label).concat(
          applier.helperCalls.filter(h => shortOf(h).length).map(h => 'not protected: ' + shortOf(h).join(', '))).join('; ') +
          '; ' + applier.helperCalls.length + ' call(s), ' + applier.trashes.length + ' trash(es)' : 'no applier');
  // ... and these are not
  const NOT_TRASHED = [
    ['the subfolders this run moved files out of (they wait for a later run)',
     [S('Africa', 'Bright Stars 2026-10-14'), S('Asia', 'Morning Wings 2026-10-13'), S('Asia', 'Silver Voices 2026-10-15')]],
    ['a subfolder still holding a merge\'s kept photo', [S('Africa', 'Golden Flames 2026-10-13')]],
    ['a waiting subfolder (a file within the settle time)', [S('Africa', 'Rising Lights 2026-10-15'), S('Asia', 'Evening Lights 2026-10-15')]],
    ['a refused subfolder (its name twice on the Shared Drive)', [S('Latin America', 'Silver Flames 2026-10-04')]],
    ['a subfolder holding a subfolder, nor that subfolder or its photo',
     [S('Africa', 'Evening Wings 2026-10-10'), S('Africa', 'Evening Wings 2026-10-10/Golden Lights 2026-10-10'),
      S('Africa', 'Evening Wings 2026-10-10/Golden Lights 2026-10-10', 'IMG_4590.jpg')]],
    ['an empty subfolder that changed within the settle time (Jotform made it 3 minutes ago)', [S('Africa', 'Morning Flames 2026-10-16')]],
    ['a source folder itself (U.S\'s holds no subfolder at all)', REGIONS.map(reg => 'S:' + reg)],
    ['a folder outside every configured source folder (an empty, settled one included), nor My Drive itself',
     ['S:Receipts', 'S:Receipts/Rising Wings 2026-10-01', 'S:Receipts/Silver Roots 2026-10-01', 'S:root']],
  ];
  // (each of these only counts on a run that does trash: one that trashes nothing proves nothing here)
  const trashing = !!applier && applier.trashes.length > 0;
  for (const [why, labels] of NOT_TRASHED) {
    const hit = applier ? labels.filter(l => applier.trashes.some(t => t.label === l) || !applier.state(l) || applier.state(l).trashed) : labels;
    check('…while it trashes those, not trashed: ' + why, trashing && !hit.length, trashing ? hit.join(', ') : 'the run trashed nothing');
  }
  check('…nothing on the Shared Drive trashed (its empty folders included), no file trashed, nothing in the trash trashed again',
        trashing && !applier.trashes.some(t => t.label.startsWith('T:') || !t.isFolder || t.wasTrashed),
        trashing ? JSON.stringify(applier.trashes.filter(t => t.label.startsWith('T:') || !t.isFolder || t.wasTrashed)) : 'the run trashed nothing');
  check('…every advanced Drive write (Files.create and Files.update, the trash included) carries supportsAllDrives: true',
        !!applier && applier.ops.length > 0 && applier.ops.every(o => o.args.supportsAllDrives === true),
        applier ? applier.ops.length + ' call(s); without it: ' +
                  applier.ops.filter(o => o.args.supportsAllDrives !== true).map(o => o.op + ' ' + JSON.stringify(o.args)).join('; ') : 'no applier');
  const LOGGED = ['Bright Stars 2026-10-14', 'Morning Wings 2026-10-13', 'Golden Flames 2026-10-13', 'Silver Voices 2026-10-15',
                  'Evening Lights 2026-10-15', 'Bright Wings 2026-10-09', 'Morning Stars 2026-10-02', 'Rising Stars 2026-10-08',
                  'Evening Roots 2026-10-05', 'Bright Voices 2026-10-04', 'Silver Flames 2026-10-04'].concat(EXPECTED_TRASHED.map(l => l.split('/')[1]));
  check('…its log has the counts and the folder names (the rescued and the trashed ones included), and no file name',
        !!applier && /\d/.test(applier.text) && LOGGED.every(x => applier.text.includes(x)) && !fileNamesIn(applier.text).length,
        applier ? 'missing: ' + LOGGED.filter(x => !applier.text.includes(x)).join(', ') + '; file names logged: ' +
                  fileNamesIn(applier.text).join(', ') : 'no applier');
  check('…and the number of folders it actually trashed (' + EXPECTED_TRASHED.length + ', next to `removed` or `trashed`)',
        !!applier && removedNumbers(applier.text).includes(EXPECTED_TRASHED.length),
        applier ? 'numbers by removed/trashed: ' + JSON.stringify(removedNumbers(applier.text)) + '; log: ' + applier.text.slice(-400) : 'no applier');
  const mentions = (r, name) => r.moved.concat(r.created).filter(x => x.includes(name));
  check('…SETTLE_MINUTES is 10 at the entry point: the 9-minute-old subfolder waits (logged by name, nothing of it moved or made), ' +
        'the 11-minute-old one moves',
        !!applier && /waiting[^\n]*Evening Lights 2026-10-15/.test(applier.text) && !mentions(applier, 'Evening Lights 2026-10-15').length &&
        applier.created.includes('T:Asia/Silver Voices 2026-10-15') && applier.moved.some(m => inSub(m, 'Asia', 'Silver Voices 2026-10-15')),
        applier ? 'Evening Lights: ' + JSON.stringify(mentions(applier, 'Evening Lights 2026-10-15')) + '; Silver Voices: ' +
                  JSON.stringify(mentions(applier, 'Silver Voices 2026-10-15')) + '; log: ' + applier.text.slice(-400) : 'no applier');
  // a subfolder may be listed twice only to re-list it just before its trash, or (in the trash) once per trashed clause
  const limit = l => (EXPECTED_TRASHED.includes(l) || TRASHED_SUBS.includes(l) ? 2 : 1);
  const relisted = applier ? Object.entries(applier.readCount).filter(([l, c]) => c > limit(l)).map(([l, c]) => l + ' x' + c) : ['no applier'];
  check('…each source subfolder\'s files are listed once per run (through any door): the plan is carried out from what the planner ' +
        'read, never a re-listing; twice at most for one it trashes (re-listed just before the trash) and for one in the trash; ' +
        'every subfolder, in the trash or not, listed',
        !!applier && !relisted.length && Object.keys(applier.readCount).length === SOURCE_SUBS,
        relisted.join(', ') || (applier ? Object.keys(applier.readCount).length + ' of ' + SOURCE_SUBS + ' read: missing ' +
          Object.entries(FAKE_SOURCES).flatMap(([reg, subs]) => subs.map(s => S(reg, s[0]))).filter(l => !own(applier.readCount, l)).join(', ') : ''));
  // the ids: what the planner's first listing of each settled subfolder returned, minus the ones kept (same name and
  // size already on the Shared Drive), is exactly what Files.update moved - and all a move was ever sent
  const SETTLED = ['S:Africa/Bright Stars 2026-10-14', 'S:Asia/Morning Wings 2026-10-13', 'S:Asia/Silver Voices 2026-10-15',
                   'S:Africa/Golden Flames 2026-10-13', S('Africa', 'Bright Wings 2026-10-09'), S('Africa', 'Morning Stars 2026-10-02'),
                   S('Asia', 'Rising Stars 2026-10-08')];
  const KEPT = ['S:Africa/Golden Flames 2026-10-13/IMG_5501.jpg', S('Asia', 'Rising Stars 2026-10-08', 'IMG_6401.jpg')];
  const plannedIds = r => [].concat(...SETTLED.map(l => r.firstListing[l] || [])).filter(id => !KEPT.some(k => r.idOf[k] === id)).sort();
  const fileOps = r => r.ops.filter(o => o.op === 'update' && o.kind !== 'trash');
  const sentIds = r => fileOps(r).map(o => o.fileId);
  const movedIds = r => fileOps(r).filter(o => o.ok).map(o => o.fileId).sort();
  check('…the file ids moved are exactly the ids the planner\'s first listing of the settled subfolders returned (those in the ' +
        'trash included), minus the kept ones, and no other file id is ever sent to Files.update',
        !!applier && plannedIds(applier).length === EXPECTED_MOVES.length && same(movedIds(applier), plannedIds(applier)) &&
        sentIds(applier).every(id => plannedIds(applier).includes(id)),
        applier ? show(movedIds(applier), plannedIds(applier)) + '; sent ' + JSON.stringify(sentIds(applier)) : 'no applier');

  // the rescue (#144): a photo Jotform wrote into a subfolder the mover had trashed reads trashed (through its folder)
  const wrongRescue = applier ? RESCUED.filter(l => { const s = applier.state(l); return !s || s.trashed || s.parent !== RESCUED_INTO[l]; })
    .map(l => l + ' ' + JSON.stringify(applier.state(l))) : RESCUED;
  check('the rescue: each photo Jotform re-sent into a subfolder in the trash (four in two of Africa\'s, one in Asia\'s) is out of ' +
        'the trash, in the region folder\'s folder of its subfolder\'s name, and the run ends with no error',
        !!applier && !applier.threw && !wrongRescue.length, applier ? (applier.threw || '') + ' ' + wrongRescue.join('; ') : 'no applier');
  const LEFT = [[S('Asia', 'Rising Stars 2026-10-08', 'IMG_6401.jpg'), 'kept (its same-name-and-size copy is on the Shared Drive)'],
                [S('Asia', 'Silver Lights 2026-10-06', 'IMG_6501.jpg'), 'a person trashed it (explicitlyTrashed)'],
                [S('Latin America', 'Evening Roots 2026-10-05', 'IMG_7201.jpg'), 'within the settle time (waiting)'],
                [S('Latin America', 'Bright Voices 2026-10-04', 'IMG_7301.jpg'), 'its name twice on the Shared Drive (refused)']];
  // (only on a run that does rescue: one that never looks in the trash leaves everything there)
  const rescuing = !!applier && RESCUED.some(l => !applier.state(l).trashed);
  for (const [l, why] of LEFT) {
    const s = applier ? applier.state(l) : null;
    const touched = applier ? applier.ops.filter(o => o.fileId === applier.idOf[l]).length : 0;
    check('…while it rescues those, a photo in a subfolder in the trash ' + why + ': left in the trash where it was, never sent to ' +
          'Files.update', rescuing && !!s && s.trashed && s.parent === l.slice(0, l.lastIndexOf('/')) && !touched &&
          (l.indexOf('Silver Lights') < 0 || s.explicitlyTrashed),
          rescuing ? JSON.stringify(s) + '; Files.update calls on it: ' + touched : 'the run rescued nothing');
  }
  check('…the waiting and the refused one in the trash are logged by name (waiting, REFUSED); no folder made for the empty one, ' +
        'the person-trashed one, the waiting or the refused one',
        !!applier && /waiting[^\n]*Evening Roots 2026-10-05/.test(applier.text) && /REFUSED[^\n]*Bright Voices 2026-10-04/.test(applier.text) &&
        !['Golden Wings 2026-10-07', 'Silver Lights 2026-10-06', 'Evening Roots 2026-10-05', 'Bright Voices 2026-10-04']
          .some(x => applier.created.some(c => c.includes(x))), tell(applier));
  const rescuedIds = applier ? RESCUED.map(l => applier.idOf[l]) : [];
  const onRescued = applier ? applier.ops.filter(o => o.op === 'update' && rescuedIds.includes(o.fileId)) : [];
  check('…each rescued photo is moved by a Files.update carrying {trashed: false} together with addParents and removeParents (a ' +
        'parent change alone may leave it in the trash), and no other file\'s update carries {trashed: false}',
        !!applier && rescuedIds.every(id => onRescued.some(o => o.fileId === id && o.ok)) &&
        onRescued.every(o => o.kind === 'rescue' && !!o.args.addParents && !!o.args.removeParents) &&
        applier.ops.filter(o => o.kind === 'rescue').every(o => rescuedIds.includes(o.fileId)),
        applier ? onRescued.map(o => o.label + ' ' + JSON.stringify(o.resource) + ' ' + JSON.stringify(o.args)).join('; ') +
                  '; {trashed:false} elsewhere: ' + applier.ops.filter(o => o.kind === 'rescue' && !rescuedIds.includes(o.fileId)).map(o => o.label).join(', ') : 'no applier');

  const dry = full.find(r => r.read.size > 0 && !r.attempted.length && !r.created.length && !r.ops.length && !r.calls.some(WRITES) &&
                         !r.threw && ['Bright Stars 2026-10-14', 'Morning Wings 2026-10-13'].every(x => r.text.includes(x)));
  check('one entry point is the dry run: reads both drives, logs what it would move by folder name, writes nothing (no Files.create ' +
        'or Files.update, no moveTo, no trash), no file name',
        !!dry && !fileNamesIn(dry.text).length, dry ? dry.name + ': ' + fileNamesIn(dry.text).join(', ') : summary(full));
  const removeLines = r => r.text.split('\n').filter(l => /\bwould remove\b/.test(l));
  check('…the dry run says what it would remove, and trashes nothing and takes nothing out of the trash: the subfolders it would ' +
        'remove are where they were, every photo in the trash still in it',
        !!dry && removeLines(dry).length > 0 && !dry.trashes.length && !dry.ops.length && EXPECTED_TRASHED.every(l => !dry.state(l).trashed) &&
        RESCUED.every(l => dry.state(l).trashed && dry.state(l).parent === l.slice(0, l.lastIndexOf('/'))),
        dry ? 'would remove lines ' + removeLines(dry).length + '; trashed ' + JSON.stringify(trashedOf(dry)) + '; writes ' + dry.ops.length : 'no dry run');
  const regionLines = (text, reg) => text.split('\n').filter(l => l.startsWith(reg + ':'));
  const countIn = (lines, rx) => { for (const l of lines) { const m = rx.exec(l); if (m) return Number(m[1]); } return null; };
  const counts = dry ? Object.fromEntries(REGIONS.map(reg => [reg, { remove: countIn(regionLines(dry.text, reg), /\bwould remove (\d+)\b/),
                                                                    rescue: countIn(regionLines(dry.text, reg), /\bwould rescue (\d+)\b/) }])) : null;
  check('…its log, per region: `would remove N` (Africa 2, Asia 1, Template 1, none elsewhere: not the fresh one, not the one with ' +
        'a subfolder, not one in the trash) and `would rescue N` (subfolders in the trash it would move photos out of: Africa 2, ' +
        'Asia 1; not the empty one, not the person-trashed one, not the waiting or the refused one)',
        !!dry && same(counts, WOULD), dry ? show(counts, WOULD) + '; log: ' + dry.text.slice(0, 600) : 'no dry run');
  const WOULD_REMOVE =EXPECTED_TRASHED.map(l => l.split('/')[1]);
  const NOT_REMOVED = ['Morning Flames 2026-10-16', 'Evening Wings 2026-10-10', 'Golden Wings 2026-10-07', 'Golden Flames 2026-10-13',
                       'Bright Stars 2026-10-14', 'Rising Lights 2026-10-15', 'Silver Lights 2026-10-06', 'Silver Flames 2026-10-04',
                       'Rising Wings 2026-10-01'];
  check('…and names each folder it would remove on a `would remove` line, and no other folder',
        !!dry && WOULD_REMOVE.every(x => removeLines(dry).some(l => l.includes(x))) && !NOT_REMOVED.some(x => removeLines(dry).some(l => l.includes(x))),
        dry ? JSON.stringify(removeLines(dry)) : 'no dry run');
  // an emptied source subfolder (what a move leaves behind) costs one listing (and on the real run one more, just before its
  // trash): no target lookup by its name, no read of the same-name target folder - each would eat the read budget every run
  const GW = 'Golden Wings 2026-10-07';
  for (const [what, r, most] of [['the real run', applier, 2], ['the dry run', dry, 1]]) {
    const lookedUp = r ? r.lookups.filter(l => l === 'T:Asia getFoldersByName ' + EMPTIED) : [];
    const targetRead = r ? (r.listedAll['T:Asia/' + EMPTIED] || 0) : 0;
    const listedTimes = r ? (r.readCount['S:Asia/' + EMPTIED] || 0) : 0;
    check(what + ': an emptied source subfolder ("' + EMPTIED + '") costs ' + (most > 1 ? 'one listing, and one more just before its trash' :
          'one listing only') + ': no target lookup by its name, the same-name target folder\'s files not read, and nothing of it ' +
          'moved, merged or logged as a move, merge, waiting or refused',
          !!r && listedTimes >= 1 && listedTimes <= most && !lookedUp.length && !targetRead && !mentions(r, EMPTIED).length &&
          !new RegExp('\\b(move|merge|waiting|REFUSED)\\b[^\\n]*' + EMPTIED).test(r.text),
          r ? 'listed ' + listedTimes + 'x; target lookups by its name ' + lookedUp.length + '; target folder\'s files read ' + targetRead +
              'x; ' + tell(r) : 'no ' + what);
    const looked = r ? (r.readCount[S('Asia', GW)] || 0) : 0;
    check(what + ': a subfolder in the trash with no file ("' + GW + '") is looked into (the rescue lists it) and ignored: no target ' +
          'lookup by its name, no folder made, not trashed again, on no move, merge, waiting, refused, remove or rescue line',
          !!r && looked >= 1 && !r.lookups.some(l => l.endsWith(' getFoldersByName ' + GW)) && !mentions(r, GW).length &&
          !r.trashes.some(t => t.label === S('Asia', GW)) && !new RegExp('(mov|merg|wait|refus|remov|rescu)[^\\n]*' + GW, 'i').test(r.text),
          r ? 'listed ' + looked + 'x; lookups ' + JSON.stringify(r.lookups.filter(l => l.includes(GW))) + '; ' + tell(r) : 'no ' + what);
  }
  // the rescue's listings go through the advanced Drive service, and never rely on Drive's default for the trash
  const lists = r => r.reads.filter(x => x.op === 'list' && !x.args.pageToken);
  const unclear = r => r.reads.filter(x => x.op === 'list' && !/\btrashed\s*!?=\s*(true|false)\b/.test(String(x.args.q || '')));
  check('every Drive.Files.list query (real run and dry run) says `trashed = true` or `trashed = false` explicitly',
        !!applier && !!dry && lists(applier).length > 0 && !unclear(applier).length && !unclear(dry).length,
        applier && dry ? JSON.stringify(unclear(applier).concat(unclear(dry)).map(x => x.args.q)) : 'no applier or no dry run');
  const srcListed = (r, reg) => lists(r).some(x => new RegExp("'" + r.idOf['S:' + reg] + "'\\s+in\\s+parents").test(String(x.args.q)) &&
                                                   /\btrashed\s*=\s*true\b/.test(String(x.args.q)));
  check('…the subfolders in the trash are found by a Drive.Files.list of each source folder\'s children with `trashed = true` ' +
        '(Africa, Asia, Latin America; real run and dry run)',
        !!applier && !!dry && ['Africa', 'Asia', 'Latin America'].every(reg => srcListed(applier, reg) && srcListed(dry, reg)),
        applier && dry ? JSON.stringify(lists(applier).map(x => x.args.q)) : 'no applier or no dry run');

  const empty = runEntries('empty');
  const byIdCalls = empty.flatMap(r => r.calls.filter(c => BY_ID(c) || WRITES(c)).map(c => r.name + ': ' + c));
  check('with NO Script Properties, no entry point opens anything by id or changes anything (no id is hard-coded)',
        ENTRIES.length > 0 && !byIdCalls.length && empty.every(r => !r.trashes.length),
        ENTRIES.length ? [...new Set(byIdCalls)].join(', ') : 'no entry points');

  const A = applier ? applier.name : null;
  // a failure: logged by folder name, the rest of the run goes on, the run ends with an error
  const failedMove = A ? runEntry(A, 'ids', { failMoveOf: 'Bright Stars 2026-10-14' }) : null;
  const notBright = EXPECTED_MOVES.filter(m => !inSub(m, 'Africa', 'Bright Stars 2026-10-14'));
  check('a move whose file moves fail: the other moves and the merges still happen, MOVE_FAILED names the folder (no file name), ' +
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
        /MOVE_FAILED[^\n]*Morning Wings 2026-10-13/.test(failedCreate.text) &&
        same(failedCreate.created.slice().sort(), EXPECTED_CREATED.filter(c => c !== 'T:Asia/Morning Wings 2026-10-13')),
        tell(failedCreate));
  // a photo arriving between the planner's read and the move (the same run, minutes later): unsettled, it stays
  for (const [sub, kind] of [['Bright Stars 2026-10-14', 'a move'], ['Golden Flames 2026-10-13', 'a merge']]) {
    const r = A ? runEntry(A, 'ids', { lateUploadTo: sub }) : null;
    const planned = EXPECTED_MOVES.filter(m => inSub(m, 'Africa', sub));
    const lateId = r ? r.idOf['S:Africa/' + sub + '/' + LATE_UPLOAD] : null;
    check('a photo uploaded into "' + sub + '" (' + kind + ') after the planner read it: the planned files move, the new one stays in ' +
          'My Drive (it has not settled; its id is never sent to Files.update), nothing else changes, no error',
          !!r && !r.threw && !r.moved.some(m => m.includes(LATE_UPLOAD)) && planned.every(m => r.moved.includes(m)) &&
          same(r.moved.slice().sort(), EXPECTED_MOVES) && !fileNamesIn(r.text).length &&
          !(lateId && r.ops.some(o => o.fileId === lateId)),
          tell(r));
  }
  // the opposite disagreement: a planned photo gone from Drive after the planner's read: the mover goes by the plan, tries
  // it, logs the failure by folder name, and still moves the rest - the gone photo's sibling that comes AFTER it included
  for (const [sub, goneFile, code] of [['Bright Stars 2026-10-14', 'IMG_4471.jpg', 'MOVE_FAILED'],
                                       ['Golden Flames 2026-10-13', 'IMG_5502.jpg', 'MERGE_FAILED']]) {
    const r = A ? runEntry(A, 'ids', { lateRemoveFrom: sub + '/' + goneFile }) : null;
    const goneLabel = 'S:Africa/' + sub + '/' + goneFile;
    const rest = EXPECTED_MOVES.filter(m => !m.startsWith(goneLabel + ' '));
    check('a planned photo gone from "' + sub + '" after the planner read it: the mover tries it (the plan, not a re-listing), ' + code +
          ' names the folder (no file name), every other planned file still moves (the next one in that subfolder too), the run ' +
          'ends with an error',
          !!r && !!r.threw && r.attempted.includes(goneLabel) && same(r.moved.slice().sort(), rest) &&
          new RegExp(code + '[^\\n]*' + sub).test(r.text) && !fileNamesIn(r.text + r.threw).length,
          r ? 'tried gone: ' + r.attempted.includes(goneLabel) + '; ' + tell(r) : 'no applier');
  }
  const failedMerge = A ? runEntry(A, 'ids', { failMoveOf: 'Golden Flames 2026-10-13' }) : null;
  const notGolden = EXPECTED_MOVES.filter(m => !inSub(m, 'Africa', 'Golden Flames 2026-10-13'));
  check('a merge whose file move fails: the moves still happen, MERGE_FAILED names the folder (no file name), the run ends with an error',
        !!failedMerge && !!failedMerge.threw && same(failedMerge.moved.slice().sort(), notGolden) &&
        /MERGE_FAILED[^\n]*Golden Flames 2026-10-13/.test(failedMerge.text) && !fileNamesIn(failedMerge.text + failedMerge.threw).length,
        tell(failedMerge));
  // #144: the rescue re-reads each photo it took out of the trash
  for (const [what, o] of [['still in the trash (Drive kept it there though the parents changed)', { rescueStaysTrashed: true }],
                           ['not in its target folder (Drive took it out of the trash but left it where it was)', { rescueNotMoved: true }]]) {
    const r = A ? runEntry(A, 'ids', o) : null;
    const folders = ['Bright Wings 2026-10-09', 'Morning Stars 2026-10-02', 'Rising Stars 2026-10-08'];
    const unnamed = r ? folders.filter(f => !new RegExp('(FAILED|REFUSED)[^\\n]*' + f).test(r.text)) : folders;
    const others = EXPECTED_MOVES.filter(m => !isRescue(m));
    check('a rescued photo the re-read finds ' + what + ': each such folder named on a FAILED (or REFUSED) line, no file name, every ' +
          'other move still made, the run ends with an error',
          !!r && !!r.threw && !unnamed.length && others.every(m => r.moved.includes(m)) && !fileNamesIn(r.text + r.threw).length,
          r ? 'not named: ' + unnamed.join(', ') + '; ' + tell(r) : 'no applier');
  }
  // #144: the trash re-lists the subfolder just before it; what changed since the planner read it is not trashed
  for (const [what, o, sub, arrived] of [['a photo arrives in', { lateUploadTo: 'Silver Roots 2026-10-11' }, 'Silver Roots 2026-10-11', LATE_UPLOAD],
                                         ['a folder appears in', { lateFolderTo: 'Rising Roots 2026-10-11' }, 'Rising Roots 2026-10-11', LATE_FOLDER]]) {
    const r = A ? runEntry(A, 'ids', o) : null;
    const lbl = S('Africa', sub), rest = EXPECTED_TRASHED.filter(l => l !== lbl);
    const arrivedState = r ? r.state(lbl + '/' + arrived) : null;
    check(what + ' "' + sub + '" (empty when the planner read it) before its trash: it is not trashed, nor what arrived (not moved ' +
          'either), the other emptied subfolders are; the log gives the number actually trashed (' + rest.length + '); no error',
          !!r && !r.threw && same(trashedOf(r), rest) && !r.state(lbl).trashed && !!arrivedState && !arrivedState.trashed &&
          arrivedState.parent === lbl && !r.moved.some(m => m.includes(arrived)) && removedNumbers(r.text).includes(rest.length),
          r ? 'arrived: ' + JSON.stringify(arrivedState) + '; numbers by removed/trashed ' + JSON.stringify(removedNumbers(r.text)) +
              '; ' + tell(r) : 'no applier');
  }
  // #144: the same name in and out of the trash in one region: one per name per run, as for two live copies - at most
  // one folder of that name made on the Shared Drive, ever; the other copy waits, and merges into it on the next run
  const TWIN_PHOTOS = [TWIN_LIVE_DIR + '/' + TWIN_LIVE_PHOTO, TWIN_BIN_DIR + '/' + TWIN_BIN_PHOTO];
  const madeTwin = r => r.created.filter(c => c === TWIN_INTO).length;
  for (const order of ['live-first', 'trashed-first']) {
    const r1 = A ? runEntry(A, 'ids', { twin: order }) : null;
    const s1 = r1 ? TWIN_PHOTOS.map(l => r1.state(l)) : [];
    const inFolder = s1.filter(s => s && s.parent === TWIN_INTO).length;
    const stayed = r1 ? (s1[0].parent === TWIN_INTO || s1[0].parent === TWIN_LIVE_DIR) &&
                        (s1[1].parent === TWIN_INTO ? !s1[1].trashed : s1[1].trashed && s1[1].parent === TWIN_BIN_DIR) : false;
    check('the same name live and in the trash, each with a photo, in one region (' + order + '): the run makes ONE folder of ' +
          'that name on the Shared Drive and moves one of the two photos into it (out of the trash if it was there); the other ' +
          'photo stays where it was, its subfolder logged as waiting; no error, nothing banned',
          !!r1 && !r1.threw && madeTwin(r1) === 1 && inFolder === 1 && stayed && new RegExp('waiting[^\\n]*' + TWIN).test(r1.text) &&
          !banned(r1).length,
          r1 ? 'folders of that name made ' + madeTwin(r1) + '; photos ' + JSON.stringify(s1) + '; ' + tell(r1) : 'no applier');
    const r2 = r1 ? r1.rerun({ twin: order, advanceMin: 15 }) : null;
    const s2 = r2 ? TWIN_PHOTOS.map(l => r2.state(l)) : [];
    check('…and the next run (15 minutes later) merges the other photo into that same folder: both photos in the one folder, ' +
          'neither in the trash, no second folder of that name on the Shared Drive, no error, nothing banned',
          !!r2 && !r2.threw && madeTwin(r2) === 0 && s2.every(s => s && s.parent === TWIN_INTO && !s.trashed) && !banned(r2).length,
          r2 ? 'folders of that name made ' + madeTwin(r2) + '; photos ' + JSON.stringify(s2) + '; ' + tell(r2) : 'no applier');
  }
  // #144: the next trigger, 15 minutes later, on the same Drive: what the first run emptied is trashed now
  const first = A ? runEntry(A, 'ids') : null;
  const later = first ? first.rerun({ advanceMin: 15 }) : null;
  const LATER_MOVES = [S('Africa', 'Rising Lights 2026-10-15', 'IMG_4480.jpg') + ' -> T:Africa/Rising Lights 2026-10-15',
                       S('Asia', 'Evening Lights 2026-10-15', 'IMG_6101.jpg') + ' -> T:Asia/Evening Lights 2026-10-15',
                       S('Latin America', 'Evening Roots 2026-10-05', 'IMG_7201.jpg') + ' -> T:Latin America/Evening Roots 2026-10-05'].sort();
  const keptStill = [S('Africa', 'Golden Flames 2026-10-13'), S('Africa', 'Evening Wings 2026-10-10')].concat(REGIONS.map(reg => 'S:' + reg));
  check('15 minutes later (the next run, the same Drive): the subfolders the first run emptied are trashed (settled by then), and ' +
        'the one Jotform had just made (18 minutes unchanged, still empty); nothing the first run trashed is trashed again; not the ' +
        'one with a kept photo, not the one with a subfolder, not a source folder',
        !!later && !later.threw && same(trashedOf(later), EXPECTED_TRASHED_LATER) && keptStill.every(l => !later.state(l).trashed),
        later ? show(trashedOf(later), EXPECTED_TRASHED_LATER) + '; ' + tell(later) : 'no applier');
  const er = S('Latin America', 'Evening Roots 2026-10-05', 'IMG_7201.jpg');
  check('…and it moves what had been waiting, the photo re-sent into a subfolder in the trash included (out of the trash, in a ' +
        'folder of its subfolder\'s name)',
        !!later && same(later.moved.slice().sort(), LATER_MOVES) && !later.state(er).trashed &&
        later.state(er).parent === 'T:Latin America/Evening Roots 2026-10-05',
        later ? show(later.moved.slice().sort(), LATER_MOVES) + '; ' + JSON.stringify(later.state(er)) : 'no applier');
  // the clock jumps 7 minutes on each file moved: past the budget (and Apps Script's 6-minute limit) after the first
  const late = A ? runEntry(A, 'ids', { moveAdvanceMin: 7 }) : null;
  const lateOps = late ? late.ops.filter(o => o.t - late.t0 >= 6 * MIN) : [];
  check('the clock past the run\'s time budget after the FIRST file moved: no further Drive write (no file moved, no folder made, ' +
        'nothing trashed), TIME_BUDGET logged',
        !!late && late.attempted.length === 1 && !lateOps.length && /TIME_BUDGET/.test(late.text),
        late ? 'files tried ' + late.attempted.length + '; Drive calls after the budget ' + lateOps.length + '; ' + (late.threw || '') +
               ' log: ' + late.text.slice(-300) : 'no applier');
  // Apps Script stops a run at 6 minutes: the budget must end well before, with time for the last file move
  const late5 = A ? runEntry(A, 'ids', { moveAdvanceMin: 5 }) : null;
  const late5Ops = late5 ? late5.ops.filter(o => o.t - late5.t0 >= 5 * MIN) : [];
  check('…and the budget ends under 5 minutes (Apps Script stops at 6): a 5-minute jump per file also stops the run after the first file',
        !!late5 && late5.attempted.length === 1 && !late5Ops.length && /TIME_BUDGET/.test(late5.text),
        late5 ? 'files tried ' + late5.attempted.length + '; Drive calls from 5 min on ' + late5Ops.length + '; ' + (late5.threw || '') +
                ' log: ' + late5.text.slice(-300) : 'no applier');
  const slow = A ? runEntry(A, 'ids', { readAdvanceMin: 3 }) : null;
  const unreadMoved = slow ? slow.moved.filter(m => ![...slow.read].some(r => m.startsWith(r + '/')))
                                 .concat(slow.created.filter(c => ![...slow.read].some(r => r.slice(2) === c.slice(2))))
                                 .concat(slow.trashes.filter(t => !slow.read.has(t.label)).map(t => 'trashed ' + t.label)) : ['no applier'];
  check('reading slow (3 minutes a subfolder): it stops reading new subfolders well before the budget and logs TIME_BUDGET',
        !!slow && slow.read.size < SOURCE_SUBS && /TIME_BUDGET/.test(slow.text),
        slow ? 'read ' + slow.read.size + ' of ' + SOURCE_SUBS + '; ' + (slow.threw || '') + ' log: ' + slow.text.slice(-300) : 'no applier');
  check('…and nothing it did not read is moved, trashed, or a folder made for it', !!slow && !unreadMoved.length, unreadMoved.join(', '));
  for (const [what, opt] of [['TARGET_FOLDER_AFRICA is a folder named "Africa photos"', { targetName: { Africa: 'Africa photos' } }],
                             ['TARGET_FOLDER_ASIA is a folder named "asia"', { targetName: { Asia: 'asia' } }],
                             ['SOURCE_FOLDER_AFRICA is a folder named "Attendance photos - Africa (old)"',
                              { sourceName: { Africa: 'Attendance photos - Africa (old)' } }]]) {
    const r = A ? runEntry(A, 'ids', opt) : null;
    check(what + ': CONFIG refused, and no Drive write at all (not even the other regions\', no trash)',
          !!r && /CONFIG refused/.test(r.threw + '\n' + r.text) && !r.attempted.length && !r.created.length && !r.ops.length &&
          !r.trashes.length,
          r ? 'threw: ' + (r.threw || 'no') + '; moves tried ' + JSON.stringify(r.attempted) + '; made ' + JSON.stringify(r.created) +
              '; Drive calls ' + r.ops.length + '; trashed ' + JSON.stringify(trashedOf(r)) : 'no applier');
  }
  const everBanned = RUNS.flatMap(r => banned(r).map(b => r.name + ': ' + b));
  check('across every entry-point run above (' + RUNS.length + ': failures, late changes, time budgets and refusals included): ' +
        'nothing banned', RUNS.length > 0 && !everBanned.length, [...new Set(everBanned)].join('; '));
}

console.log('\ndrive-sync/ — the one trash helper, ' + TRASH_HELPER + '(id, protectedIds) (#144; #185 reuses it)');
{
  const env = fakeEnv('ids');
  let hc = null, loadErr = '';
  try {
    if (GS.length) { hc = loadGs.sandbox(GS, env.globals); env.install(hc); }
  } catch (e) { loadErr = e.message; }
  const helper = hc && typeof hc[TRASH_HELPER] === 'function' ? hc[TRASH_HELPER] : null;
  check('drive-sync/ defines the trash helper ' + TRASH_HELPER, !!helper, loadErr || (hc ? typeof hc[TRASH_HELPER] : 'not loaded'));
  /** One call of the helper: whether it threw, and what it asked of Drive meanwhile. */
  const attempt = (id, prot) => {
    const at = { calls: env.calls.length, ops: env.ops.length, reads: env.reads.length, trashes: env.trashes.length };
    let threw = '';
    try { helper(id, prot); } catch (e) { threw = String(e && e.message || e) || 'threw'; }
    return { threw, drive: env.calls.slice(at.calls).filter(c => /^(Drive|DriveApp|Folder|File)\./.test(c)),
             ops: env.ops.slice(at.ops), reads: env.reads.slice(at.reads), trashes: env.trashes.slice(at.trashes) };
  };
  const untouched = r => !!r && !!r.threw && !r.drive.length && !r.ops.length && !r.reads.length && !r.trashes.length;
  const show1 = r => JSON.stringify(r && { threw: r.threw, drive: r.drive, ops: r.ops.length, trashes: r.trashes.length });
  const refusals = CONFIGURED_IDS.map(id => [id, 'configured']).concat([[DRIVE_ROOT_ID, 'the Shared Drive\'s root'],
                                                                         ['', 'an empty id'], [undefined, 'no id'], [42, 'not a string']]);
  const notRefused = helper ? refusals.map(([id, why]) => [why + ' ' + id, attempt(id, PROTECTED_IDS.slice())])
    .filter(([, r]) => !untouched(r)).map(([w, r]) => w + ': ' + show1(r)) : ['no helper'];
  check('…it refuses (throws), before any Drive call, each configured SOURCE_FOLDER_/TARGET_FOLDER_ id (all ten), the Shared ' +
        'Drive\'s root, and an id that is empty, missing or not a string',
        !!helper && !notRefused.length, notRefused.join('; '));
  const emptied = env.idOf[S('Asia', EMPTIED)], other = env.idOf[S('Africa', 'Silver Roots 2026-10-11')];
  const noList = helper ? attempt(emptied, undefined) : null;
  const listed = helper ? attempt(other, PROTECTED_IDS.concat(other)) : null;
  check('…and, before any Drive call, any id when it is not handed an array of ids to protect, and any id in that array (the ' +
        'caller\'s own protections)', untouched(noList) && untouched(listed), show1(noList) + '; ' + show1(listed));
  const ok = helper ? attempt(emptied, PROTECTED_IDS.slice()) : null;
  check('…while an emptied, settled source subfolder it trashes: one Drive.Files.update {trashed: true} with supportsAllDrives ' +
        'on that id and nothing else (no permanent delete, no other write)',
        !!ok && !ok.threw && ok.ops.length === 1 && ok.ops[0].kind === 'trash' && ok.ops[0].fileId === emptied &&
        ok.ops[0].args.supportsAllDrives === true && ok.trashes.length === 1 && ok.trashes[0].id === emptied &&
        !ok.drive.some(NEVER) && !!env.state(S('Asia', EMPTIED)).trashed,
        show1(ok) + (ok ? ' ' + JSON.stringify(ok.ops.map(o => [o.kind, o.fileId, o.resource, o.args])) : ''));
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
  // #144 (#185 reuses it): the code trashes in one place, the helper
  const bodyOf = (src, name) => {
    const at = src.search(new RegExp('\\bfunction\\s+' + name + '\\s*\\('));
    if (at < 0) return null;
    for (let j = src.indexOf('{', at), depth = 0; j >= 0 && j < src.length; j++) {
      if (src[j] === '{') depth++;
      else if (src[j] === '}' && !--depth) return src.slice(at, j + 1);
    }
    return null;
  };
  const helperSrc = bodyOf(gsCode, TRASH_HELPER);
  const elsewhere = helperSrc ? gsCode.replace(helperSrc, '') : gsCode;
  // (a planner input's `trashed: true` is not a trash: only an update sending it is)
  const TRUE_TRASH = /\bupdate\s*\(\s*\{[^}]*\btrashed['"]?\s*:\s*true\b/;
  check('the code trashes in one place: a Files.update sending `{trashed: true}` only inside ' + TRASH_HELPER + ', no setTrashed, ' +
        'no permanent delete or emptyTrash anywhere',
        !!helperSrc && TRUE_TRASH.test(helperSrc) && !TRUE_TRASH.test(elsewhere) &&
        !/\bsetTrashed\b|\bemptyTrash\b|\bFiles\s*\.\s*(remove|delete)\b/.test(gsCode),
        helperSrc ? 'trashed: true outside it: ' + TRUE_TRASH.test(elsewhere) + '; banned names: ' +
                    (gsCode.match(/\bsetTrashed\b|\bemptyTrash\b|\bFiles\s*\.\s*(remove|delete)\b/g) || []).join(', ') : 'no ' + TRASH_HELPER);
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
