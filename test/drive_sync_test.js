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
 * Never a file, a non-empty folder, a source folder itself, a permanent delete or emptyTrash; on
 * the Shared Drive only what #185's retention entry of TRASH_RULES allows (with RETENTION_DAYS set).
 *
 * #181: planTrash_ and retentionFolders_, the Shared Drive's 90-day trash planned offline (epic #179), have their
 * own contract and section after planMoves_'s (search `#181`). #182: RETENTION_DAYS, the one-Shared-Drive check, the
 * Shared Drive reads and the would-trash preview of both entry points, on the fake's dated Shared Drive (RET_ITEMS),
 * have theirs after the entry points' (search `#182`). #185: the real run's trash of that plan, its re-checks, the
 * cap, failures, the time budget and its log, inside #182's section (search `#185`).
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

// ================================================================ #181: the 90-day trash on the Shared Drive
/**
 * planTrash_ and retentionFolders_ (drive-sync/Plan.gs, ticket #181, epic #179 rulings R1-R3, R6, R14): pure, like
 * planMoves_. Nothing calls them yet (#182 wires them into Mover.gs).
 *
 *   retentionFolders_(drive, now, retentionDays) -> [folder id]
 *   planTrash_(drive, now, retentionDays, maxFiles) -> {files, folders, capped, outside}
 *
 *   drive    {regions: {<Region>: <folder id>}   only a region of PHOTO_REGIONS that is an OWN key counts
 *             rootId: <the Shared Drive's id>,
 *             folders: [{id, name, parent, created: Date, complete}]   every untrashed folder, region folders included
 *             files: [{id, parent, created: Date}]}
 *   walk up  from an item's parent: the first configured region folder met is its region; rootId, null, an id not in
 *            `folders`, or one met already first: outside, never trashed. A region folder and rootId never are.
 *   due      now - max(file.created, its parent folder's created) >= retentionDays * 86,400,000 (ms, 24-hour days,
 *            no time zone); never without a valid Date on both sides
 *   files    [{region, id, parent, top, due}]  earliest due moment first, then id, at most maxFiles; top = the region
 *            folder's direct subfolder it is under (null directly in the region folder); due = its due moment
 *   folders  [{region, id, name, parent, top}]  strictly below a region folder, complete === true, itself at least
 *            retentionDays old, every file in it in `files`, every folder in it earlier in `folders` (children first);
 *            top = the direct subfolder of the region folder it is, or is under
 *   capped   how many due files maxFiles left out;   outside  how many files reach no region folder
 *
 * The inputs are written here with `created` in ms (or null, 'invalid', or absent) and revived into the sandbox's
 * Dates ('invalid' an Invalid Date). Every club name is fictional.
 */
{
  console.log('\nplanTrash_ — generated Shared Drive trees against an independent oracle');
  const DAY = 24 * 60 * MIN;
  const planTrashFn = ctx && typeof ctx.planTrash_ === 'function' ? ctx.planTrash_ : null;
  const oldFoldersFn = ctx && typeof ctx.retentionFolders_ === 'function' ? ctx.retentionFolders_ : null;
  check('planTrash_ and retentionFolders_ are top-level functions of drive-sync/', !!planTrashFn && !!oldFoldersFn,
        ctx ? 'planTrash_ ' + typeof ctx.planTrash_ + ', retentionFolders_ ' + typeof ctx.retentionFolders_ : 'not loaded');

  const reviveDrive = ctx ? vm.runInContext(
    '(function (s) { return JSON.parse(s, function (k, v) { if (k !== "created") return v; ' +
    'return typeof v === "number" ? new Date(v) : v === "invalid" ? new Date(NaN) : v; }); })', ctx) : null;
  const ARGS = '__retentionTestArgs__';
  /** ctx[fn](...args) run inside the sandbox with a time limit: a walk up that never ends fails, it does not hang. */
  const inSandbox = (fn, args) => {
    if (!ctx || typeof ctx[fn] !== 'function') return { out: null, error: fn + ' is not defined' };
    ctx[ARGS] = args;
    try {
      return { out: vm.runInContext(fn + '.apply(null, ' + ARGS + ')', ctx, { timeout: 5000 }), error: '' };
    } catch (e) {
      return { out: null, error: String(e && e.message || e) || 'threw' };
    } finally { delete ctx[ARGS]; }
  };
  const sandboxDrive = (drive, tweak) => { const d = reviveDrive(JSON.stringify(drive)); if (tweak) tweak(d); return d; };
  const trashPlan = (drive, nowMs, days, maxFiles, tweak) => {
    if (!reviveDrive) return { plan: null, error: 'not loaded' };
    const r = inSandbox('planTrash_', [sandboxDrive(drive, tweak), new CtxDate(nowMs), days, maxFiles]);
    return { plan: r.out, error: r.error };
  };
  const oldFolders = (drive, nowMs, days, tweak) => {
    if (!reviveDrive) return { ids: null, error: 'not loaded' };
    const r = inSandbox('retentionFolders_', [sandboxDrive(drive, tweak), new CtxDate(nowMs), days]);
    return { ids: r.out, error: r.error || (Array.isArray(r.out) ? '' : 'not an array: ' + JSON.stringify(r.out)) };
  };
  const sortedIds = a => (Array.isArray(a) ? a.map(String).sort() : a);

  const tv = x => (x && typeof x.getTime === 'function' ? x.getTime() : x);
  const tag = (...a) => a.map(v => (v === null ? '<null>' : v === undefined ? '<undefined>' : String(v))).join('|');
  const fileKey = f => tag(f.region, f.id, f.parent, f.top, tv(f.due));
  const folderKey = f => tag(f.region, f.id, f.name, f.parent, f.top);
  /** The plan as strings: files in their order, folders as a set, the two counts. */
  const normT = p => ({ files: list(p, 'files').map(fileKey), folders: list(p, 'folders').map(folderKey).sort(),
                        capped: p ? p.capped : undefined, outside: p ? p.outside : undefined });
  const planIds = p => list(p, 'files').map(e => e && e.id).concat(list(p, 'folders').map(e => e && e.id));
  const folderOrder = p => list(p, 'folders').map(e => e && e.id);
  /** '' when every folder comes before the folder it is in (children before parents) and nothing is listed twice. */
  const orderProblems = p => {
    const fl = list(p, 'folders'), at = new Map(), bad = [];
    fl.forEach((f, i) => { if (at.has(f.id)) bad.push(f.id + ' twice'); else at.set(f.id, i); });
    fl.forEach((f, i) => { if (at.has(f.parent) && at.get(f.parent) < i) bad.push(f.id + ' after the folder it is in, ' + f.parent); });
    const fi = list(p, 'files').map(f => f.id);
    if (new Set(fi).size !== fi.length) bad.push('a file twice');
    return bad.join(', ');
  };
  const shuffle = (a, r) => {
    for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
    return a;
  };
  const defineKey = (o, k, v) => Object.defineProperty(o, k, { value: v, enumerable: true, writable: true, configurable: true });

  /**
   * What planTrash_ and retentionFolders_ must return, worked out from the rules alone (the ticket's Context), on a
   * drive written here (created in ms; null, 'invalid' or absent: no valid Date).
   */
  function trashOracle(drive, nowMs, days, maxFiles) {
    const R = days * DAY;
    const byId = new Map(drive.folders.map(d => [d.id, d]));
    const regionAt = new Map();
    for (const reg of REGIONS) {
      if (own(drive.regions, reg) && typeof drive.regions[reg] === 'string') regionAt.set(drive.regions[reg], reg);
    }
    const valid = t => typeof t === 'number' && isFinite(t);
    const guarded = id => regionAt.has(id) || id === drive.rootId;
    const climb = start => {   // {region, chain: the folders met, nearest first} or {why}
      const met = new Set(), chain = [];
      let cur = start;
      for (;;) {
        if (cur === null || cur === undefined) return { why: 'null' };
        if (regionAt.has(cur)) return { region: regionAt.get(cur), chain };
        if (cur === drive.rootId) return { why: 'root' };
        if (!byId.has(cur)) return { why: 'unknown' };
        if (met.has(cur)) return { why: 'loop' };
        met.add(cur);
        chain.push(cur);
        cur = byId.get(cur).parent;
      }
    };
    const due = [], notDue = [], outside = [];
    for (const f of drive.files) {
      const w = climb(f.parent);
      if (!w.region) { outside.push({ id: f.id, why: w.why }); continue; }
      const pf = byId.get(f.parent);
      const e = { region: w.region, id: f.id, parent: f.parent, top: w.chain.length ? w.chain[w.chain.length - 1] : null,
                  depth: w.chain.length, file: f, folder: pf };
      if (guarded(f.id)) { e.why = 'guarded'; notDue.push(e); continue; }
      if (!pf || !valid(f.created) || !valid(pf.created)) { e.why = 'no date'; notDue.push(e); continue; }
      e.due = Math.max(f.created, pf.created);
      if (nowMs - e.due >= R) due.push(e);
      else { e.why = 'young'; notDue.push(e); }
    }
    due.sort((a, b) => a.due - b.due || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    const files = due.slice(0, maxFiles), capped = due.slice(files.length);
    const planned = new Set(files.map(e => e.id)), cappedIds = new Set(capped.map(e => e.id));
    const kids = new Map(), held = new Map();
    for (const d of drive.folders) { if (!kids.has(d.parent)) kids.set(d.parent, []); kids.get(d.parent).push(d); }
    for (const f of drive.files) { if (!held.has(f.parent)) held.set(f.parent, []); held.get(f.parent).push(f); }
    const memo = new Map();
    const goes = d => {
      if (memo.has(d.id)) return memo.get(d.id);
      memo.set(d.id, false);
      const ok = !!climb(d.parent).region && !guarded(d.id) && d.complete === true && valid(d.created) &&
                 nowMs - d.created >= R && (held.get(d.id) || []).every(f => planned.has(f.id)) &&
                 (kids.get(d.id) || []).every(goes);
      memo.set(d.id, ok);
      return ok;
    };
    const folders = [], kept = [], old = [];
    for (const d of drive.folders) {
      const w = climb(d.parent);
      if (!w.region || guarded(d.id)) continue;
      const e = { region: w.region, id: d.id, name: d.name, parent: d.parent,
                  top: w.chain.length ? w.chain[w.chain.length - 1] : d.id, depth: w.chain.length + 1, d };
      if (valid(d.created) && nowMs - d.created >= R) old.push(d.id);
      if (goes(d)) { folders.push(e); continue; }
      const why = new Set();   // why it stays (for the table's coverage)
      if (d.complete !== true) why.add('incomplete');
      if (!valid(d.created) || nowMs - d.created < R) why.add('young');
      for (const f of held.get(d.id) || []) why.add(cappedIds.has(f.id) ? 'capped' : planned.has(f.id) ? '' : 'descendant');
      for (const c of kids.get(d.id) || []) if (!goes(c)) why.add(regionAt.has(c.id) ? 'region inside' : 'descendant');
      why.delete('');
      e.why = [...why];
      kept.push(e);
    }
    return {
      want: { files: files.map(e => tag(e.region, e.id, e.parent, e.top, e.due)), folders: folders.map(folderKey).sort(),
              capped: capped.length, outside: outside.length },
      due, files, capped, notDue, outside, folders, kept, old: old.sort(), R, valid,
    };
  }

  /**
   * A Shared Drive: each region's folder at the root (four in five configured; the rest are plain folders there) with
   * subfolders down to depth 3 (half of them old) and files at depths 0 to 3, every time straddling the retention
   * time, exactly on it or 1 ms short now and then, and now and then null, unparseable or missing; `complete` now and
   * then false, missing, 'true' or 1. Now and then one region's folder sits inside another region's tree. Outside every
   * region folder: a `Kept` folder at the root, files at the root, items with no parent or an unknown one (some named
   * like Object built-ins), a two-folder loop with a folder hanging off it, a folder that is its own parent, and keys
   * of `regions` that are no region (Europe, `U.S `, asia, __proto__, constructor, toString) naming root folders.
   * Folders and files come in a shuffled order.
   */
  function trashLayout(seed, nowMs, days) {
    const r = prng(7000 + seed * 7);
    const R = days * DAY;
    const pick = a => a[Math.floor(r() * a.length)];
    const pad = (x, w) => String(x).padStart(w, '0');
    let n = 0;
    const nid = p => p + pad(seed, 2) + '-' + pad(++n, 4);
    const rootId = 'root' + pad(seed, 2);
    const regions = {}, folders = [], files = [];
    const age = () => { const x = r(); return x < 0.07 ? R : x < 0.14 ? R - 1 : Math.floor(r() * 2.2 * R); };
    const when = () => { const x = r(); return x < 0.025 ? null : x < 0.05 ? 'invalid' : x < 0.07 ? undefined : nowMs - age(); };
    const old = () => nowMs - R - Math.floor(r() * R);
    const club = () => pick(WORDS) + ' ' + pick(NOUNS) + ' ' + pad(1 + Math.floor(r() * 12), 2) + '-' +
                       pad(1 + Math.floor(r() * 28), 2) + '-2026';
    const folder = (parent, name, created, complete) => {
      const d = { id: nid('d'), name, parent, created, complete };
      folders.push(d);
      return d;
    };
    const file = (parent, created) => { const f = { id: nid('f'), parent, created }; files.push(f); return f; };
    const tree = (parent, depth, into) => {
      const nf = Math.floor(r() * 3);
      for (let i = 0; i < nf; i++) file(parent, when());
      if (depth >= 3) return;
      const nk = depth === 0 ? 2 + Math.floor(r() * 4) : r() < 0.6 ? 1 + Math.floor(r() * 2) : 0;
      for (let i = 0; i < nk; i++) {
        const d = folder(parent, depth === 0 ? club() : pick(['extra', 'more photos', 'Day 2', club()]), r() < 0.45 ? old() : when(),
                         r() < 0.85 ? true : pick([false, undefined, 'true', 1]));
        into.push(d);
        tree(d.id, depth + 1, into);
      }
    };
    const regionTree = {};
    for (const reg of REGIONS) {
      const d = folder(rootId, reg, nowMs - age(), r() < 0.6);
      regionTree[reg] = [d];
      if (r() < 0.8) regions[reg] = d.id;
      tree(d.id, 0, regionTree[reg]);
    }
    if (Object.keys(regions).length < 2) { regions.Africa = regionTree.Africa[0].id; regions.Asia = regionTree.Asia[0].id; }
    const configured = REGIONS.filter(reg => own(regions, reg));
    let nested = null;
    if (r() < 0.45) {   // a misconfiguration: a region's folder inside another region's folder, or deeper in its tree
      const i = Math.floor(r() * (configured.length - 1));
      const j = i + 1 + Math.floor(r() * (configured.length - 1 - i));
      // the host: any folder of that tree, or a new one made in it (old, complete, nothing else in it: kept for that alone)
      const host = r() < 0.5 ? pick(regionTree[configured[i]]) : folder(pick(regionTree[configured[i]]).id, club(), old(), true);
      regionTree[configured[j]][0].parent = host.id;
      nested = { region: configured[j], id: regionTree[configured[j]][0].id, host: host.id };
    }
    const kept = folder(rootId, 'Kept', old(), true);
    file(kept.id, old());
    folder(kept.id, club(), old(), true);
    file(rootId, old());
    file(null, old());
    const orphan = folder(null, club(), old(), true);
    file(orphan.id, old());
    const lost = folder('ghost' + pad(seed, 2), club(), old(), true);
    file(lost.id, old());
    file('gone' + pad(seed, 2), old());
    file(pick(['toString', 'constructor', '__proto__', 'hasOwnProperty', 'valueOf']), old());
    const l1 = folder(null, club(), old(), true), l2 = folder(l1.id, club(), old(), true);
    l1.parent = l2.id;
    file(l2.id, old());
    const l3 = folder(l1.id, 'extra', old(), true);
    file(l3.id, old());
    const self = folder(null, club(), old(), true);
    self.parent = self.id;
    file(self.id, old());
    const odd = [];
    for (const k of ['Europe', 'U.S ', 'asia', '__proto__', 'constructor', 'toString']) {
      if (r() < 0.5) continue;
      const d = folder(rootId, k, old(), true);
      defineKey(regions, k, d.id);
      file(d.id, old());
      odd.push(k);
    }
    shuffle(folders, r);
    shuffle(files, r);
    return { drive: { regions, rootId, folders, files }, nested, odd };
  }

  const T_NOWS = [Date.UTC(2027, 0, 22, 9, 0, 0), Date.UTC(2027, 3, 10, 0, 0, 0), Date.UTC(2026, 11, 30, 23, 59, 59, 999)];
  const T_DAYS = [90, 91, 120];
  const tseen = { due0: 0, due1: 0, due2: 0, due3: 0, young: 0, noDate: 0, keptByFolderTime: 0, keptByFileTime: 0,
                  dueExactly: 0, shortByOneMs: 0, foldersTrashed: 0, trashedAboveTrashed: 0, trashedAtDepth3: 0,
                  keptIncomplete: 0, keptTooYoung: 0, keptForCappedFile: 0, keptYoungDescendant: 0, keptAroundRegionFolder: 0,
                  outsideRoot: 0, outsideNull: 0, outsideUnknown: 0, outsideLoop: 0, nestedRegionFiles: 0, cappedLayouts: 0,
                  uncappedLayouts: 0, oddKeys: 0, dueInIncompleteFolder: 0 };
  const dueRegions = new Set();
  let tRuns = 0, tMatched = 0;
  for (let seed = 1; seed <= 8; seed++) {
    for (let k = 0; k < T_NOWS.length; k++) {
      const nowMs = T_NOWS[k], days = T_DAYS[(seed + k) % T_DAYS.length];
      const { drive, nested, odd } = trashLayout(seed, nowMs, days);
      const all = trashOracle(drive, nowMs, days, Infinity).due.length;
      const maxFiles = [100, Math.max(1, Math.floor(all / 2)), Math.max(1, all - 1), all + 2][(seed + 2 * k) % 4];
      const o = trashOracle(drive, nowMs, days, maxFiles);
      const { plan: p, error } = trashPlan(drive, nowMs, days, maxFiles);
      tRuns++;
      const got = normT(p);
      const label = 'seed ' + seed + ', now ' + new Date(nowMs).toISOString() + ', ' + days + ' days, maxFiles ' + maxFiles;
      const ok = !error && same(got, o.want);
      check(label + ': files (in order, with region, parent, top and due moment), folders, capped and outside are the rules\' answer',
            ok, error || (ok ? o.files.length + ' file(s), ' + o.folders.length + ' folder(s), capped ' + o.capped.length +
                          ', outside ' + o.outside.length : show(got, o.want)));
      const guardedIds = new Set([drive.rootId].concat(Object.values(drive.regions)));
      const outsideIds = new Set(o.outside.map(e => e.id));
      for (const d of drive.folders) if (!o.folders.some(e => e.id === d.id) && !o.kept.some(e => e.id === d.id)) outsideIds.add(d.id);
      const wrong = planIds(p).filter(x => guardedIds.has(x) || outsideIds.has(x));
      const order = orderProblems(p);
      check(label + ': folders children before parents, nothing twice; no region folder, rootId or outside item in the plan',
            !error && !!p && !order && !wrong.length, error || order + (wrong.length ? ' WRONG: ' + wrong.join(', ') : ''));
      if (!ok) continue;
      tMatched++;
      for (const e of o.due) {
        tseen['due' + Math.min(e.depth, 3)]++;
        dueRegions.add(e.region);
        if (nowMs - e.due === o.R) tseen.dueExactly++;
        if (e.folder && e.folder.complete !== true) tseen.dueInIncompleteFolder++;
      }
      for (const e of o.notDue) {
        if (e.why === 'no date') { tseen.noDate++; continue; }
        if (e.why !== 'young') continue;
        tseen.young++;
        const fileOld = nowMs - e.file.created >= o.R, folderOld = nowMs - e.folder.created >= o.R;
        if (fileOld && !folderOld) tseen.keptByFolderTime++;
        if (folderOld && !fileOld) tseen.keptByFileTime++;
        if (nowMs - Math.max(e.file.created, e.folder.created) === o.R - 1) tseen.shortByOneMs++;
      }
      tseen.foldersTrashed += o.folders.length;
      tseen.trashedAboveTrashed += o.folders.filter(e => o.folders.some(c => c.parent === e.id)).length;
      tseen.trashedAtDepth3 += o.folders.filter(e => e.depth === 3).length;
      for (const e of o.kept) {
        if (e.why.length !== 1) continue;   // kept for one reason alone
        const w = e.why[0];
        if (w === 'incomplete') tseen.keptIncomplete++;
        if (w === 'young') tseen.keptTooYoung++;
        if (w === 'capped') tseen.keptForCappedFile++;
        if (w === 'descendant') tseen.keptYoungDescendant++;
        if (w === 'region inside') tseen.keptAroundRegionFolder++;
      }
      for (const e of o.outside) tseen['outside' + e.why[0].toUpperCase() + e.why.slice(1)]++;
      if (nested) tseen.nestedRegionFiles += o.due.concat(o.notDue).filter(e => e.region === nested.region).length;
      tseen[o.capped.length ? 'cappedLayouts' : 'uncappedLayouts']++;
      tseen.oddKeys += odd.length;
    }
  }
  check('planTrash_ — the table covers every outcome (' + tMatched + ' of ' + tRuns + ' layouts planned as the rules say): ' +
        'due at depth 0 to 3 in every region, young, no date, kept by either time, due at exactly the moment and not 1 ms ' +
        'before, emptied folders bottom-up, a folder kept for each reason alone (a young descendant, an incomplete listing, ' +
        'too young itself, a capped file, a region folder inside), outside by the root, null, an unknown id and a loop, ' +
        'a nested region folder, capped and uncapped, keys that are no region',
        tRuns > 0 && tMatched === tRuns && Object.values(tseen).every(v => v > 0) && dueRegions.size === REGIONS.length,
        JSON.stringify(tseen) + ' regions with due files: ' + [...dueRegions].join(', '));

  // ---------------------------------------------------------------- specific cases
  const ROOT = 'drive-root-181';
  const tm = v => (typeof v === 'string' && v !== 'invalid' ? Date.parse(v) : v);
  const FD = (id, name, parent, created, extra) => Object.assign({ id, name, parent, created: tm(created), complete: true }, extra || {});
  const FL = (id, parent, created) => ({ id, parent, created: tm(created) });
  const AFRICA = FD('reg-africa', 'Africa', ROOT, '2026-10-21T15:00:00Z');   // the worked examples' region folder A
  const fe = (region, id, parent, top, moment) => tag(region, id, parent, top, tm(moment));
  const fo = (region, id, name, parent, top) => tag(region, id, name, parent, top);

  console.log('\nplanTrash_ — the later of the file\'s and its folder\'s createdTime decides (worked examples 1, 5, 6)');
  {
    // the worked examples of the ticket (1, 2, 4, 5, 6) on one Shared Drive
    const drive = {
      regions: { Africa: 'reg-africa', Asia: 'reg-asia', 'Latin America': 'reg-latam' }, rootId: ROOT,
      folders: [AFRICA, FD('reg-asia', 'Asia', ROOT, '2026-10-21T15:00:00Z'), FD('reg-latam', 'Latin America', ROOT, '2026-10-21T15:00:00Z'),
                FD('sunrise', 'Sunrise Club 10-23-2026', 'reg-africa', '2026-10-24T09:00:00Z'),
                FD('morning', 'Morning Star Club', 'reg-asia', '2026-10-25T10:00:00Z'),
                FD('held-new', 'Bright Lights 07-01-2026', 'reg-latam', '2026-11-02T10:00:00Z'),
                FD('old-club', 'Silver Roots Club', 'reg-latam', '2026-10-01T00:00:00Z'),
                FD('new-club', 'Evening Flames Club', 'reg-africa', '2027-01-10T00:00:00Z')],
      files: [FL('f2', 'sunrise', '2026-10-23T08:01:00Z'), FL('f1', 'sunrise', '2026-10-23T08:00:00Z'),
              FL('a', 'morning', '2026-10-25T09:50:00Z'), FL('b', 'morning', '2026-10-29T15:00:00Z'),
              FL('d', 'reg-africa', '2026-10-22T10:00:00Z'),
              FL('h5new', 'held-new', '2026-07-01T00:00:00Z'), FL('h5merged', 'morning', '2026-07-01T00:00:00Z'),
              FL('h6old', 'old-club', '2026-05-01T00:00:00Z'), FL('h6new', 'new-club', '2026-05-01T00:00:00Z')],
    };
    // id: [region, parent, top, due moment, due from] - the ticket's numbers, worked by hand
    const DUE = {
      f1: ['Africa', 'sunrise', 'sunrise', '2026-10-24T09:00:00Z', '2027-01-22T09:00:00Z'],          // 1: the folder's time
      f2: ['Africa', 'sunrise', 'sunrise', '2026-10-24T09:00:00Z', '2027-01-22T09:00:00Z'],
      a: ['Asia', 'morning', 'morning', '2026-10-25T10:00:00Z', '2027-01-23T10:00:00Z'],             // 2: the folder's
      b: ['Asia', 'morning', 'morning', '2026-10-29T15:00:00Z', '2027-01-27T15:00:00Z'],             // 2: its own
      d: ['Africa', 'reg-africa', null, '2026-10-22T10:00:00Z', '2027-01-20T10:00:00Z'],             // 4: its own
      h5new: ['Latin America', 'held-new', 'held-new', '2026-11-02T10:00:00Z', '2027-01-31T10:00:00Z'],   // 5: the new folder's
      h5merged: ['Asia', 'morning', 'morning', '2026-10-25T10:00:00Z', '2027-01-23T10:00:00Z'],      // 5: merged
      h6old: ['Latin America', 'old-club', 'old-club', '2026-10-01T00:00:00Z', '2026-12-30T00:00:00Z'],   // 6: on arrival
      h6new: ['Africa', 'new-club', 'new-club', '2027-01-10T00:00:00Z', '2027-04-10T00:00:00Z'],     // 6: the new folder's
    };
    const entryOf = id => fe(DUE[id][0], id, DUE[id][1], DUE[id][2], DUE[id][3]);
    const wrongEdges = [];
    for (const id of Object.keys(DUE)) {
      const from = tm(DUE[id][4]);
      const before = trashPlan(drive, from - 1, 90, 100), on = trashPlan(drive, from, 90, 100);
      const err = before.error || on.error;
      const entry = list(on.plan, 'files').find(e => e.id === id);
      if (err) wrongEdges.push(id + ': ' + err);
      else if (list(before.plan, 'files').some(e => e.id === id)) wrongEdges.push(id + ': due 1 ms before ' + DUE[id][4]);
      else if (!entry) wrongEdges.push(id + ': not due at ' + DUE[id][4]);
      else if (fileKey(entry) !== entryOf(id)) wrongEdges.push(id + ': ' + show(fileKey(entry), entryOf(id)));
    }
    check('each file is due from the LATER of its own and its folder\'s createdTime, + 90 days, and not 1 ms before ' +
          '(f1, f2, a, h5new by the folder; b, d by the file; h5merged and h6old due on arrival; h6new 90 days after its new folder), ' +
          'with region, parent, top and that due moment',
          !!planTrashFn && !wrongEdges.length, wrongEdges.join('; ') || (planTrashFn ? '' : 'planTrash_ is not defined'));
    const SNAP = [   // now -> [files in order], [folders]
      ['2027-01-21T12:00:00Z', ['h6old', 'd'], ['old-club']],
      ['2027-01-22T09:00:00Z', ['h6old', 'd', 'f1', 'f2'], ['old-club', 'sunrise']],
      ['2027-01-24T12:00:00Z', ['h6old', 'd', 'f1', 'f2', 'a', 'h5merged'], ['old-club', 'sunrise']],
      ['2027-01-27T15:00:00Z', ['h6old', 'd', 'f1', 'f2', 'a', 'h5merged', 'b'], ['morning', 'old-club', 'sunrise']],
      ['2027-01-31T10:00:00Z', ['h6old', 'd', 'f1', 'f2', 'a', 'h5merged', 'b', 'h5new'], ['held-new', 'morning', 'old-club', 'sunrise']],
      ['2027-04-10T00:00:00Z', ['h6old', 'd', 'f1', 'f2', 'a', 'h5merged', 'b', 'h5new', 'h6new'],
       ['held-new', 'morning', 'new-club', 'old-club', 'sunrise']],
    ];
    const FOLDER = { sunrise: ['Africa', 'Sunrise Club 10-23-2026', 'reg-africa'], morning: ['Asia', 'Morning Star Club', 'reg-asia'],
                     'held-new': ['Latin America', 'Bright Lights 07-01-2026', 'reg-latam'],
                     'old-club': ['Latin America', 'Silver Roots Club', 'reg-latam'], 'new-club': ['Africa', 'Evening Flames Club', 'reg-africa'] };
    for (const [now, fileIds, folderIds] of SNAP) {
      const r = trashPlan(drive, tm(now), 90, 100);
      const want = { files: fileIds.map(entryOf), folders: folderIds.map(x => fo(FOLDER[x][0], x, FOLDER[x][1], FOLDER[x][2], x)).sort(),
                     capped: 0, outside: 0 };
      check('at ' + now + ': files ' + fileIds.join(', ') + ' (earliest due moment first, a tie by id); folders ' + folderIds.join(', ') +
            ' (example 1: Sunrise Club 10-23-2026 goes once f1 and f2 do; example 2: Morning Star Club kept while b is young)',
            !r.error && same(normT(r.plan), want), r.error || show(normT(r.plan), want));
    }
  }

  console.log('\nplanTrash_ — exactly 90 days after the due moment is due, 1 ms less is not (24-hour days, UTC)');
  {
    // example 7: the folder made 2026-10-23T08:00:00.000Z, the file older; and a file younger than its old folder
    const drive = {
      regions: { Africa: 'reg-africa' }, rootId: ROOT,
      folders: [AFRICA, FD('b7', 'Bright Stars 10-23-2026', 'reg-africa', '2026-10-23T08:00:00.000Z'),
                FD('o7', 'Golden Voices 10-01-2026', 'reg-africa', '2026-10-01T00:00:00.000Z')],
      files: [FL('q-older', 'b7', '2026-09-01T00:00:00.000Z'), FL('q-own', 'o7', '2026-10-30T23:59:59.999Z')],
    };
    const cases = [   // [file, folder that goes with it, due from at 90 days: worked by hand]
      ['q-older', 'b7', '2027-01-21T08:00:00.000Z'],   // not 07:59:59.999Z; US daylight saving ends 2026-11-01, changing nothing
      ['q-own', 'o7', '2027-01-28T23:59:59.999Z'],
    ];
    const origTz = process.env.TZ;
    const zones = ['UTC', 'America/New_York', 'Europe/London', 'Australia/Lord_Howe', 'Asia/Kolkata'];
    const misses = [];
    try {
      for (const zone of zones) {
        process.env.TZ = zone;   // the host's zone must change nothing (a local-time `setDate(+90)` would)
        for (const [id, dir, iso] of cases) {
          const from = tm(iso);
          const before = trashPlan(drive, from - 1, 90, 100), on = trashPlan(drive, from, 90, 100);
          const inB = list(before.plan, 'files').some(e => e.id === id) || list(before.plan, 'folders').some(e => e.id === dir);
          const inOn = list(on.plan, 'files').some(e => e.id === id) && list(on.plan, 'folders').some(e => e.id === dir);
          if (before.error || on.error || inB || !inOn) misses.push(zone + ' ' + id + ': ' + (before.error || on.error || (inB ? 'due 1 ms early' : 'not due on time')));
        }
      }
    } finally { if (origTz === undefined) delete process.env.TZ; else process.env.TZ = origTz; }
    check('example 7: due (file and emptied folder) at exactly 2027-01-21T08:00:00.000Z, not at 07:59:59.999Z; a file younger ' +
          'than its folder at its own time + 90 days to the ms; the same in UTC, New York, London, Lord Howe and Kolkata',
          !!planTrashFn && !misses.length, misses.join('; ') || (planTrashFn ? '' : 'planTrash_ is not defined'));
    const byDays = [];
    for (const days of [90, 91, 120, 365]) {
      for (const [id, dir, iso] of cases) {
        const from = tm(iso) + (days - 90) * DAY;   // a day is 86,400,000 ms whatever the calendar
        const before = trashPlan(drive, from - 1, days, 100), on = trashPlan(drive, from, days, 100);
        if (before.error || on.error || list(before.plan, 'files').some(e => e.id === id) || !list(on.plan, 'files').some(e => e.id === id)) {
          byDays.push(days + ' days, ' + id + ': ' + (before.error || on.error || 'wrong'));
        }
      }
    }
    check('retentionDays 91, 120 and 365 move the due moment by exactly that many times 86,400,000 ms (and 1 ms before is not due)',
          !!planTrashFn && !byDays.length, byDays.join('; ') || (planTrashFn ? '' : 'planTrash_ is not defined'));
    // no valid Date on either side: never due, however old the other side is
    const nd = {
      regions: { Africa: 'reg-africa', Asia: 'reg-asia' }, rootId: ROOT,
      folders: [AFRICA, FD('reg-asia', 'Asia', ROOT, 'invalid'),
                FD('ok', 'Rising Wings 09-01-2026', 'reg-africa', '2026-09-01T00:00:00Z'),
                FD('fold-null', 'Silver Wings 09-01-2026', 'reg-africa', null),
                FD('fold-bad', 'Golden Lights 09-01-2026', 'reg-africa', 'invalid'),
                FD('fold-none', 'Evening Stars 09-01-2026', 'reg-africa', undefined)],
      files: [FL('ok-1', 'ok', '2026-08-01T00:00:00Z'), FL('file-null', 'ok', null), FL('file-bad', 'ok', 'invalid'),
              FL('file-none', 'ok', undefined), FL('in-null', 'fold-null', '2026-01-01T00:00:00Z'),
              FL('in-bad', 'fold-bad', '2026-01-01T00:00:00Z'), FL('in-none', 'fold-none', '2026-01-01T00:00:00Z'),
              FL('in-asia', 'reg-asia', '2026-01-01T00:00:00Z')],
    };
    const r = trashPlan(nd, Date.UTC(2027, 5, 1), 90, 100);
    check('a file with a null, unparseable or missing created, or in a folder (a region folder included) whose created is so: ' +
          'never due, however old the other side; its folder kept; the file beside them with both dates still due',
          !r.error && same(list(r.plan, 'files').map(e => e.id), ['ok-1']) && !list(r.plan, 'folders').length &&
          r.plan.capped === 0 && r.plan.outside === 0, r.error || JSON.stringify(normT(r.plan)));
  }

  console.log('\nplanTrash_ — files directly in a region folder and nested at depth 1 to 3 are trashed when due');
  {
    const nowMs = Date.UTC(2027, 2, 1, 0, 0, 0);
    const regions = {}, folders = [], files = [], want = [], chains = [];
    REGIONS.forEach((reg, i) => {
      const R0 = 'reg-' + i, d1 = 'r' + i + '-d1', d2 = 'r' + i + '-d2', d3 = 'r' + i + '-d3', s1 = 'r' + i + '-s1', s2 = 'r' + i + '-s2';
      regions[reg] = R0;
      // listed deepest first and the region folder last: the order of the input decides nothing
      folders.push(FD(d3, 'more photos', d2, '2026-09-03T00:00:00Z'), FD(s2, 'extra', s1, '2026-09-02T00:00:00Z'),
                   FD(d2, 'extra', d1, '2026-09-02T00:00:00Z'), FD(s1, WORDS[(i + 3) % 6] + ' ' + NOUNS[i] + ' 09-01-2026', R0, '2026-09-01T00:00:00Z'),
                   FD(d1, WORDS[i] + ' ' + NOUNS[i] + ' 09-01-2026', R0, '2026-09-01T00:00:00Z'), FD(R0, reg, ROOT, '2026-08-01T00:00:00Z'));
      // each file later than its folder (its own time decides); region i's hour i keeps the regions interleaved
      const t = k => Date.UTC(2026, 9, 1 + 3 * k, i);
      [[R0, null], [d1, d1], [d2, d1], [d3, d1]].forEach(([parent, top], k) => {
        files.push(FL('r' + i + '-f' + k, parent, t(k)));
        want.push({ key: tag(reg, 'r' + i + '-f' + k, parent, top, t(k)), at: t(k), id: 'r' + i + '-f' + k });
      });
      files.push(FL('r' + i + '-o1', s1, t(4)));
      want.push({ key: tag(reg, 'r' + i + '-o1', s1, s1, t(4)), at: t(4), id: 'r' + i + '-o1' });
      files.push(FL('r' + i + '-y0', R0, '2027-02-15T00:00:00Z'), FL('r' + i + '-y2', s2, '2027-02-16T00:00:00Z'));   // young
      chains.push({ reg, R0, go: [d3, d2, d1], keep: [s2, s1],
                    names: { [d1]: WORDS[i] + ' ' + NOUNS[i] + ' 09-01-2026', [d2]: 'extra', [d3]: 'more photos' }, parents: { [d1]: R0, [d2]: d1, [d3]: d2 } });
    });
    // depth 6 in Africa: z1 > z2 > ... > z6, a due file at the bottom
    const z = [1, 2, 3, 4, 5, 6].map(k => 'z' + k);
    z.forEach((id, k) => folders.push(FD(id, k ? 'level ' + (k + 1) : 'Rising Roots 09-05-2026', k ? z[k - 1] : 'reg-0', '2026-09-05T00:00:00Z')));
    files.push(FL('z-f', 'z6', '2026-10-20T00:00:00Z'));
    want.push({ key: tag('Africa', 'z-f', 'z6', 'z1', Date.parse('2026-10-20T00:00:00Z')), at: Date.parse('2026-10-20T00:00:00Z'), id: 'z-f' });
    want.sort((a, b) => a.at - b.at || (a.id < b.id ? -1 : 1));
    const drive = { regions, rootId: ROOT, folders, files };
    const r = trashPlan(drive, nowMs, 90, 100);
    check('every region (Africa, Asia, Latin America, U.S, Template): the due file directly in the region folder (top null) ' +
          'and those at depth 1, 2 and 3 (top the region folder\'s direct subfolder) are in `files`, with region, parent and ' +
          'due moment, earliest first across the regions; nothing capped, nothing outside',
          !r.error && same(normT(r.plan).files, want.map(w => w.key)) && r.plan.capped === 0 && r.plan.outside === 0,
          r.error || show(normT(r.plan).files, want.map(w => w.key)));
    const young = list(r.plan, 'files').filter(e => /-y\d$/.test(e.id)).map(e => e.id);
    const keptGone = chains.flatMap(c => c.keep).filter(x => folderOrder(r.plan).includes(x));
    check('…a young file at depth 0 or 2 is not, and the folders above it (with a due file of their own) stay',
          !r.error && !!r.plan && !young.length && !keptGone.length, r.error || young.concat(keptGone).join(', '));
    const order = folderOrder(r.plan);
    const wantFolders = chains.flatMap(c => c.go.map(x => fo(c.reg, x, c.names[x], c.parents[x], c.go[2]))).concat(
      z.map((id, k) => fo('Africa', id, k ? 'level ' + (k + 1) : 'Rising Roots 09-05-2026', k ? z[k - 1] : 'reg-0', 'z1'))).sort();
    const chainOrder = chains.every(c => c.go.every((x, k) => k === 0 || order.indexOf(c.go[k - 1]) < order.indexOf(x)));
    const zOrder = z.every((x, k) => k === 0 || order.indexOf(x) < order.indexOf(z[k - 1]));
    check('…the emptied folders at depth 3, 2 and 1 go, deepest first, with region, name, parent and top; depth 6 too: the ' +
          'due file, then its six folders from the bottom up; never a region folder',
          !r.error && same(normT(r.plan).folders, wantFolders) && chainOrder && zOrder && !orderProblems(r.plan) &&
          !order.some(x => /^reg-/.test(x)),
          r.error || show(normT(r.plan).folders, wantFolders) + ' order ' + order.join(','));
  }

  console.log('\nplanTrash_ — emptied folders go children before parents; a folder with a kept descendant is kept with all its ancestors');
  {
    // example 3, Latin America: G holds g1 and a folder a person made, E, which holds x
    const ex3 = {
      regions: { 'Latin America': 'reg-latam' }, rootId: ROOT,
      folders: [FD('reg-latam', 'Latin America', ROOT, '2026-10-21T15:00:00Z'),
                FD('G', 'Golden Wings 11-02-2026', 'reg-latam', '2026-11-02T12:00:00Z'), FD('E', 'extra', 'G', '2026-11-05T09:00:00Z')],
      files: [FL('x', 'E', '2026-11-02T11:55:00Z'), FL('g1', 'G', '2026-11-02T11:50:00Z')],
    };
    const on = trashPlan(ex3, tm('2027-02-03T09:00:00Z'), 90, 100), early = trashPlan(ex3, tm('2027-02-03T09:00:00Z') - 1, 90, 100);
    const wantOn = [fe('Latin America', 'g1', 'G', 'G', '2026-11-02T12:00:00Z'), fe('Latin America', 'x', 'E', 'G', '2026-11-05T09:00:00Z')];
    check('example 3 at 2027-02-03T09:00Z: files g1 (due by G\'s time), x (by E\'s); folders [E, G] in that order, top G for both',
          !on.error && same(normT(on.plan).files, wantOn) && same(folderOrder(on.plan), ['E', 'G']) &&
          same(list(on.plan, 'folders').map(folderKey), [fo('Latin America', 'E', 'extra', 'G', 'G'),
                                                          fo('Latin America', 'G', 'Golden Wings 11-02-2026', 'reg-latam', 'G')]),
          on.error || JSON.stringify(normT(on.plan)) + ' order ' + folderOrder(on.plan));
    check('…1 ms earlier: g1 only; E is kept (x not due) and so is G above it',
          !early.error && same(normT(early.plan).files, wantOn.slice(0, 1)) && !folderOrder(early.plan).length,
          early.error || JSON.stringify(normT(early.plan)));
    // a chain, a branch, and a kept descendant, the folders listed in three orders
    const O = '2026-09-01T00:00:00Z', nowMs = Date.UTC(2027, 2, 1);
    const base = [FD('reg-africa', 'Africa', ROOT, '2026-08-01T00:00:00Z'), FD('reg-asia', 'Asia', ROOT, '2026-08-01T00:00:00Z'),
                  FD('reg-tp', 'Template', ROOT, '2026-08-01T00:00:00Z'),
                  FD('c1', 'Bright Stars 09-01-2026', 'reg-africa', O), FD('c2', 'extra', 'c1', O), FD('c3', 'extra', 'c2', O), FD('c4', 'extra', 'c3', O),
                  FD('b1', 'Silver Wings 09-01-2026', 'reg-asia', O), FD('b2a', 'Day 1', 'b1', O), FD('b3', 'more photos', 'b2a', O), FD('b2b', 'Day 2', 'b1', O),
                  FD('k1', 'Evening Roots 09-01-2026', 'reg-tp', O), FD('k2', 'extra', 'k1', O), FD('k3', 'more photos', 'k2', O),
                  FD('k2b', 'Day 2', 'k1', O)];
    const files = [FL('c1-f', 'c1', '2026-10-01T00:00:00Z'), FL('c2-f', 'c2', '2026-10-02T00:00:00Z'), FL('c3-f', 'c3', '2026-10-03T00:00:00Z'),
                   FL('c4-f', 'c4', '2026-10-04T00:00:00Z'), FL('b3-f', 'b3', '2026-10-05T00:00:00Z'), FL('b2b-f', 'b2b', '2026-10-06T00:00:00Z'),
                   FL('k1-f', 'k1', '2026-10-07T00:00:00Z'), FL('k2-f', 'k2', '2026-10-08T00:00:00Z'),
                   FL('k3-young', 'k3', '2027-02-20T00:00:00Z')];
    const orders = { 'parents first': base.slice(), 'children first': base.slice().reverse(), shuffled: shuffle(base.slice(), prng(1181)) };
    for (const [how, fl] of Object.entries(orders)) {
      const r = trashPlan({ regions: { Africa: 'reg-africa', Asia: 'reg-asia', Template: 'reg-tp' }, rootId: ROOT, folders: fl, files },
                          nowMs, 90, 100);
      const order = folderOrder(r.plan);
      const pos = x => order.indexOf(x);
      check('folders listed ' + how + ': a chain of four goes exactly c4, c3, c2, c1; a branch: b3 before b2a, b2a and b2b before b1',
            !r.error && same(order.filter(x => /^c/.test(x)), ['c4', 'c3', 'c2', 'c1']) &&
            same(order.filter(x => /^b/.test(x)).sort(), ['b1', 'b2a', 'b2b', 'b3']) &&
            pos('b3') < pos('b2a') && pos('b2a') < pos('b1') && pos('b2b') < pos('b1') && !orderProblems(r.plan),
            r.error || order.join(', '));
      check('…a young file three levels down (k3): k3, k2 and k1 are kept while their due files go, and k1\'s other, emptied ' +
            'subfolder (k2b) goes', !r.error && same(order.filter(x => /^k/.test(x)), ['k2b']) &&
            ['k1-f', 'k2-f'].every(x => list(r.plan, 'files').some(e => e.id === x)) &&
            !list(r.plan, 'files').some(e => e.id === 'k3-young'), r.error || JSON.stringify(normT(r.plan)));
    }
  }

  console.log('\nplanTrash_ — an emptied folder younger than 90 days (a move cut short) is kept; an incomplete one is kept');
  {
    const nowMs = Date.UTC(2027, 1, 1, 12, 0, 0), R = 90 * DAY, OLD_T = nowMs - 200 * DAY;
    const sub = (id, created, extra) => FD(id, 'Rising Stars 10-01-2026', 'reg-africa', created, extra);
    const drive = {
      regions: { Africa: 'reg-africa' }, rootId: ROOT,
      folders: [FD('reg-africa', 'Africa', ROOT, OLD_T),
                sub('e-exact', nowMs - R), sub('e-short', nowMs - R + 1), sub('e-new', nowMs - 2 * 60 * MIN),
                sub('e-false', OLD_T, { complete: false }), sub('e-absent', OLD_T, { complete: undefined }),
                sub('e-string', OLD_T, { complete: 'true' }), sub('e-one', OLD_T, { complete: 1 }),
                sub('e-bad', 'invalid'), sub('e-null', null),
                sub('p-short', OLD_T), FD('e-short2', 'extra', 'p-short', nowMs - 10 * DAY),
                sub('p-ok', OLD_T), FD('e-ok', 'extra', 'p-ok', OLD_T),
                sub('i-due', OLD_T, { complete: false }),
                sub('y-folder', nowMs - 10 * DAY)],
      files: [FL('i-f1', 'i-due', OLD_T + DAY), FL('i-f2', 'i-due', OLD_T + 2 * DAY), FL('y-old', 'y-folder', '2026-01-01T00:00:00Z')],
    };
    const r = trashPlan(drive, nowMs, 90, 100);
    const order = folderOrder(r.plan), has = x => order.includes(x);
    check('an emptied folder exactly 90 days old goes; 1 ms younger, or made 2 hours ago (a move cut short, merged into next run), is kept',
          !r.error && has('e-exact') && !has('e-short') && !has('e-new'), r.error || order.join(', '));
    check('complete false, missing, \'true\' or 1: kept (only complete === true is a full listing); the due files of an incomplete ' +
          'folder are still trashed',
          !r.error && !['e-false', 'e-absent', 'e-string', 'e-one', 'i-due'].some(has) &&
          same(list(r.plan, 'files').map(e => e.id), ['i-f1', 'i-f2']), r.error || JSON.stringify(normT(r.plan)));
    check('a folder with no valid created (unparseable or null) is kept; above a young emptied folder its parent is kept; ' +
          'a young folder\'s old file waits for the folder; e-ok then p-ok go, in that order, and nothing else',
          !r.error && same(order.slice().sort(), ['e-exact', 'e-ok', 'p-ok']) && order.indexOf('e-ok') < order.indexOf('p-ok') &&
          !list(r.plan, 'files').some(e => e.id === 'y-old'), r.error || order.join(', '));
    const r91 = trashPlan(drive, nowMs, 91, 100);
    check('…with retentionDays 91 the 90-day-old emptied folder is kept too',
          !r91.error && same(folderOrder(r91.plan).slice().sort(), ['e-ok', 'p-ok']), r91.error || folderOrder(r91.plan).join(', '));
  }

  console.log('\nplanTrash_ — region folder ids and rootId never appear in the plan, even a region folder nested empty and old in another region\'s folder');
  {
    const O = '2026-08-01T00:00:00Z', nowMs = Date.UTC(2027, 3, 1);
    const regions = { Africa: 'reg-af', Asia: 'reg-as', Template: 'reg-tp', 'U.S': 'reg-us', 'Latin America': 'reg-la' };
    const drive = {
      regions, rootId: ROOT,
      folders: [FD('reg-af', 'Africa', ROOT, O), FD('reg-as', 'Asia', ROOT, O), FD('reg-la', 'Latin America', ROOT, O),
                FD('reg-tp', 'Template', 'reg-af', O),                          // Template's folder inside Africa's, empty and old
                FD('af-empty', 'Golden Flames 08-02-2026', 'reg-af', O),
                FD('as-x', 'Morning Lights 08-02-2026', 'reg-as', O), FD('reg-us', 'U.S', 'as-x', O),   // U.S's inside an Asia subfolder
                FD('us-sub', 'Bright Roots 08-03-2026', 'reg-us', O)],
      files: [FL('as-x-f', 'as-x', '2026-08-05T00:00:00Z'), FL('us-1', 'reg-us', '2026-08-06T00:00:00Z'), FL('us-2', 'us-sub', '2026-08-07T00:00:00Z')],
    };
    const r = trashPlan(drive, nowMs, 90, 100);
    const want = { files: [fe('Asia', 'as-x-f', 'as-x', 'as-x', '2026-08-05T00:00:00Z'), fe('U.S', 'us-1', 'reg-us', null, '2026-08-06T00:00:00Z'),
                           fe('U.S', 'us-2', 'us-sub', 'us-sub', '2026-08-07T00:00:00Z')],
                   folders: [fo('Africa', 'af-empty', 'Golden Flames 08-02-2026', 'reg-af', 'af-empty'),
                             fo('U.S', 'us-sub', 'Bright Roots 08-03-2026', 'reg-us', 'us-sub')].sort(), capped: 0, outside: 0 };
    check('every region folder old, complete and empty (Latin America at the root, Template\'s inside Africa\'s): none in the plan; ' +
          'U.S\'s folder inside an Asia subfolder: never trashed, its contents count for U.S (the first region met), and the ' +
          'Asia subfolder holding it is kept; the empty subfolder beside them goes',
          !r.error && same(normT(r.plan), want), r.error || show(normT(r.plan), want));
    // the root listed among the folders (a reader's mistake), with no parent and with a region folder as its parent
    const leaks = [];
    for (const rootParent of [null, 'reg-af']) {
      const d2 = { regions: { Africa: 'reg-af' }, rootId: ROOT,
                   folders: [FD('reg-af', 'Africa', ROOT, O), FD(ROOT, 'GLOW Shared Drive', rootParent, O), FD('af-1', 'Silver Stars 08-02-2026', 'reg-af', O)],
                   files: [FL('in-root', ROOT, O), FL('af-1-f', 'af-1', O)] };
      const r2 = trashPlan(d2, nowMs, 90, 100);
      const ok = !r2.error && same(normT(r2.plan).files, [fe('Africa', 'af-1-f', 'af-1', 'af-1', O)]) &&
                 same(folderOrder(r2.plan), ['af-1']) && r2.plan.outside === 1;
      if (!ok) leaks.push('root\'s parent ' + rootParent + ': ' + (r2.error || JSON.stringify(normT(r2.plan))));
    }
    check('rootId listed as a folder, old, complete and empty (no parent, or even a region folder as its parent): never in ' +
          '`folders`; a file in it is outside', !leaks.length, leaks.join('; '));
    // file entries carrying a region folder's id or the root's (a reader's mistake) inside an old, complete subfolder
    const d3 = { regions: { Africa: 'reg-af', Asia: 'reg-as' }, rootId: ROOT,
                 folders: [FD('reg-af', 'Africa', ROOT, O), FD('reg-as', 'Asia', ROOT, O), FD('af-club', 'Evening Lights 08-02-2026', 'reg-af', O)],
                 files: [FL('reg-af', 'af-club', O), FL(ROOT, 'af-club', O), FL('reg-as', 'reg-af', O), FL('af-ok', 'af-club', O)] };
    const r3 = trashPlan(d3, nowMs, 90, 100);
    check('a file entry whose id is a region folder\'s or the root\'s is never in `files`, and the folder holding it is not ' +
          'trashed (that would take it along); the real file beside it is',
          !r3.error && same(list(r3.plan, 'files').map(e => e.id), ['af-ok']) && !folderOrder(r3.plan).length,
          r3.error || JSON.stringify(normT(r3.plan)));
  }

  console.log('\nplanTrash_ — a walk up reaching the root, null, an unknown id or a loop before a region folder: outside, never trashed, no crash');
  {
    const O = '2026-08-01T00:00:00Z', nowMs = Date.UTC(2027, 1, 1, 12);
    const folders = [FD('reg-af', 'Africa', ROOT, O), FD('af-club', 'Sunrise Club 08-02-2026', 'reg-af', O),
                     FD('kept', 'Kept', ROOT, O), FD('kept-sub', 'Golden Roots 08-02-2026', 'kept', O),
                     FD('archive', 'Archive', ROOT, O), FD('archive-a', 'Silver Voices 08-02-2026', 'archive', O), FD('archive-b', 'extra', 'archive', O),
                     FD('orphan', 'Rising Lights 08-02-2026', null, O), FD('lost', 'Evening Wings 08-02-2026', 'ghost-1', O),
                     FD('loop-1', 'Bright Wings 08-02-2026', 'loop-2', O), FD('loop-2', 'Morning Roots 08-02-2026', 'loop-1', O),
                     FD('loop-3', 'extra', 'loop-1', O), FD('self', 'Golden Stars 08-02-2026', 'self', O),
                     FD('tri-1', 'Silver Flames 08-02-2026', 'tri-2', O), FD('tri-2', 'Day 2', 'tri-3', O), FD('tri-3', 'Day 3', 'tri-1', O)];
    const outsideFiles = [FL('k-1', 'kept', O), FL('ar-1', 'archive-a', O), FL('o-1', 'orphan', O), FL('g-1', 'lost', O),
                          FL('l-1', 'loop-1', O), FL('l-2', 'loop-2', O), FL('s-1', 'self', O), FL('t-1', 'tri-3', O),
                          FL('n-1', null, O), FL('r-1', ROOT, O), FL('u-1', 'gone-1', O), FL('e-1', '', O),
                          FL('x-ts', 'toString', O), FL('x-ctor', 'constructor', O), FL('x-proto', '__proto__', O),
                          FL('x-hop', 'hasOwnProperty', O), FL('x-vo', 'valueOf', O)];
    const files = [FL('af-1', 'af-club', O)].concat(outsideFiles);
    const want = { files: [fe('Africa', 'af-1', 'af-club', 'af-club', O)],
                   folders: [fo('Africa', 'af-club', 'Sunrise Club 08-02-2026', 'reg-af', 'af-club')], capped: 0, outside: outsideFiles.length };
    for (const [how, fl, fi] of [['as listed', folders, files], ['loops first, reversed', folders.slice().reverse(), files.slice().reverse()]]) {
      const r = trashPlan({ regions: { Africa: 'reg-af' }, rootId: ROOT, folders: fl, files: fi }, nowMs, 90, 100);
      check('(' + how + ') old files at the root, in a root folder (Kept, Archive and below), with no parent, an unknown parent ' +
            '(ghost, \'\', toString, constructor, __proto__, hasOwnProperty, valueOf), in a two- or three-folder loop or a folder ' +
            'that is its own parent: outside (' + outsideFiles.length + '), none trashed, none of those folders trashed; the ' +
            'Africa file and folder still are', !r.error && same(normT(r.plan), want), r.error || show(normT(r.plan), want));
    }
    const ex8 = trashPlan({ regions: { Africa: 'reg-africa' }, rootId: ROOT, folders: [AFRICA, FD('kept', 'Kept', ROOT, '2026-01-05T00:00:00Z')],
                            files: [FL('old-photo', 'kept', '2026-01-04T00:00:00Z')] }, Date.UTC(2027, 1, 1), 90, 100);
    check('example 8: a root folder `Kept` with an old photo: outside 1, nothing in `files` or `folders`',
          !ex8.error && same(normT(ex8.plan), { files: [], folders: [], capped: 0, outside: 1 }), ex8.error || JSON.stringify(normT(ex8.plan)));
    const nullRegion = trashPlan({ regions: { Africa: null }, rootId: ROOT, folders: [FD('d-null', 'Silver Roots 08-02-2026', null, O)],
                                   files: [FL('p-null', null, O), FL('p-in', 'd-null', O)] }, nowMs, 90, 100);
    check('a region whose folder id is null: a file with no parent, and a folder with none, are still outside; nothing trashed',
          !nullRegion.error && same(normT(nullRegion.plan), { files: [], folders: [], capped: 0, outside: 2 }),
          nullRegion.error || JSON.stringify(normT(nullRegion.plan)));
  }

  console.log('\nplanTrash_ — Europe, "U.S " (trailing space), asia, __proto__, constructor, toString as region keys: ignored, no crash');
  {
    const O = '2026-08-01T00:00:00Z', nowMs = Date.UTC(2027, 1, 1, 12);
    const ODD = ['Europe', 'U.S ', 'asia', '__proto__', 'constructor', 'toString', 'hasOwnProperty', ' Asia', 'africa'];
    const build = withAsia => {
      const regions = {};
      if (withAsia) regions.Asia = 'reg-as';
      const folders = [FD('reg-as', 'Asia', ROOT, O), FD('as-club', 'Morning Star Club', 'reg-as', O)];
      const files = [FL('as-1', 'as-club', O)];
      ODD.forEach((k, i) => {
        defineKey(regions, k, 'odd-' + i);
        folders.push(FD('odd-' + i, k, ROOT, O), FD('odd-' + i + '-sub', 'Bright Stars 08-02-2026', 'odd-' + i, O));
        files.push(FL('odd-' + i + '-f', 'odd-' + i, O));
      });
      return { regions, rootId: ROOT, folders, files };
    };
    const want = { files: [fe('Asia', 'as-1', 'as-club', 'as-club', O)], folders: [fo('Asia', 'as-club', 'Morning Star Club', 'reg-as', 'as-club')],
                   capped: 0, outside: ODD.length };
    const r = trashPlan(build(true), nowMs, 90, 100);
    check('Asia beside keys Europe, `U.S `, asia, __proto__, constructor, toString, hasOwnProperty, ` Asia`, africa (each naming ' +
          'an old root folder with an old photo and an empty subfolder): only Asia counts; the rest are outside, never trashed',
          !r.error && same(normT(r.plan), want), r.error || show(normT(r.plan), want));
    const none = trashPlan(build(false), nowMs, 90, 100);
    check('…with no real region key at all: nothing trashed, every file outside, no crash',
          !none.error && same(normT(none.plan), { files: [], folders: [], capped: 0, outside: ODD.length + 1 }),
          none.error || JSON.stringify(normT(none.plan)));
    const inherited = trashPlan(build(true), nowMs, 90, 100, d => Object.setPrototypeOf(d.regions, { Africa: 'odd-0', Template: 'odd-1' }));
    check('…and Africa or Template inherited from the regions object\'s prototype, not its own key: ignored too',
          !inherited.error && same(normT(inherited.plan), want), inherited.error || show(normT(inherited.plan), want));
  }

  console.log('\nplanTrash_ — the cap: maxFiles by the earliest due moment across regions, capped counted, their folders kept');
  {
    const nowMs = Date.UTC(2027, 1, 1);
    // [id, region, parent, top, created]: in the order the rules give (each file younger than its folder, so its own time)
    const CAP = [['cap-q', 'Asia', 'as-1', 'as-1', '2026-09-01T00:00:00Z'], ['cap-b', 'Africa', 'af-1', 'af-1', '2026-09-01T06:00:00Z'],
                 ['cap-z', 'Latin America', 'la-1', 'la-1', '2026-09-02T00:00:00Z'], ['cap-d', 'Africa', 'af-2', 'af-2', '2026-09-03T00:00:00Z'],
                 ['cap-h', 'Asia', 'as-2', 'as-2', '2026-09-04T00:00:00Z'], ['cap-m', 'Asia', 'as-2', 'as-2', '2026-09-04T00:00:00Z'],
                 ['cap-a', 'Africa', 'af-2', 'af-2', '2026-09-05T00:00:00Z'], ['cap-y', 'Latin America', 'la-2a', 'la-2', '2026-09-06T00:00:00Z'],
                 ['cap-e', 'Latin America', 'la-2a', 'la-2', '2026-09-07T00:00:00Z'], ['cap-k', 'Asia', 'reg-as', null, '2026-09-08T00:00:00Z']];
    const F = '2026-08-15T00:00:00Z';
    const FOLD = { 'as-1': ['Asia', 'Rising Stars 08-15-2026', 'reg-as', 'as-1'], 'af-1': ['Africa', 'Bright Voices 08-15-2026', 'reg-af', 'af-1'],
                   'la-1': ['Latin America', 'Golden Roots 08-15-2026', 'reg-la', 'la-1'], 'af-2': ['Africa', 'Silver Wings 08-15-2026', 'reg-af', 'af-2'],
                   'as-2': ['Asia', 'Evening Stars 08-15-2026', 'reg-as', 'as-2'], 'la-2': ['Latin America', 'Morning Flames 08-15-2026', 'reg-la', 'la-2'],
                   'la-2a': ['Latin America', 'extra', 'la-2', 'la-2'] };
    const NEEDS = { 'as-1': ['cap-q'], 'af-1': ['cap-b'], 'la-1': ['cap-z'], 'af-2': ['cap-d', 'cap-a'], 'as-2': ['cap-h', 'cap-m'],
                    'la-2a': ['cap-y', 'cap-e'], 'la-2': ['cap-y', 'cap-e'] };   // la-2 holds la-2a only
    const drive = {
      regions: { Africa: 'reg-af', Asia: 'reg-as', 'Latin America': 'reg-la' }, rootId: ROOT,
      folders: [FD('reg-la', 'Latin America', ROOT, '2026-08-01T00:00:00Z'), FD('reg-as', 'Asia', ROOT, '2026-08-01T00:00:00Z'),
                FD('reg-af', 'Africa', ROOT, '2026-08-01T00:00:00Z'), FD('af-3', 'Rising Roots 08-15-2026', 'reg-af', F)]
        .concat(Object.entries(FOLD).map(([id, [, name, parent]]) => FD(id, name, parent, F))),
      files: CAP.slice().reverse().map(([id, , parent, , c]) => FL(id, parent, c)).concat([FL('cap-young', 'af-3', '2027-01-20T00:00:00Z')]),
    };
    const wrong = [];
    for (let k = 1; k <= CAP.length + 1; k++) {
      const r = trashPlan(drive, nowMs, 90, k);
      const sel = CAP.slice(0, k), chosen = new Set(sel.map(c => c[0]));
      const want = { files: sel.map(([id, reg, parent, top, c]) => fe(reg, id, parent, top, c)),
                     folders: Object.keys(NEEDS).filter(f => NEEDS[f].every(x => chosen.has(x)))
                       .map(f => fo(FOLD[f][0], f, FOLD[f][1], FOLD[f][2], FOLD[f][3])).sort(),
                     capped: Math.max(0, CAP.length - k), outside: 0 };
      if (r.error || !same(normT(r.plan), want) || orderProblems(r.plan)) {
        wrong.push('maxFiles ' + k + ': ' + (r.error || show(normT(r.plan), want) + ' ' + orderProblems(r.plan)));
      }
    }
    check('maxFiles 1 to 11 over ten due files in Africa, Asia and Latin America: the first maxFiles by due moment across the ' +
          'regions (a tie by id, whatever the input order), capped the rest; a folder goes only once all its files are in, ' +
          'and the folder above a capped file\'s folder stays (la-2 above la-2a)', !!planTrashFn && !wrong.length,
          wrong.join(' || ') || (planTrashFn ? '' : 'planTrash_ is not defined'));
    // the mover's own cap (R6): 150 due files, 100 per run
    const rr = prng(18100);
    const big = { regions: { Africa: 'reg-af', Asia: 'reg-as', 'Latin America': 'reg-la' }, rootId: ROOT,
                  folders: [FD('reg-af', 'Africa', ROOT, '2026-08-01T00:00:00Z'), FD('reg-as', 'Asia', ROOT, '2026-08-01T00:00:00Z'),
                            FD('reg-la', 'Latin America', ROOT, '2026-08-01T00:00:00Z')], files: [] };
    const regIds = ['reg-af', 'reg-as', 'reg-la'], regNames = ['Africa', 'Asia', 'Latin America'], expect = [];
    for (let i = 0; i < 30; i++) {
      const id = 'big-' + String(i).padStart(2, '0');
      big.folders.push(FD(id, WORDS[i % 6] + ' ' + NOUNS[(i * 5) % 6] + ' 08-20-2026', regIds[i % 3], '2026-08-20T00:00:00Z'));
      for (let j = 0; j < 5; j++) {
        const fidv = 'bf-' + String(Math.floor(rr() * 1e6)).padStart(6, '0') + '-' + String(i * 5 + j).padStart(3, '0');
        const c = Date.UTC(2026, 8, 1) + Math.floor(rr() * 40) * DAY;   // whole days: many ties, broken by id
        big.files.push(FL(fidv, id, c));
        expect.push({ id: fidv, folder: id, key: tag(regNames[i % 3], fidv, id, id, c), c });
      }
    }
    shuffle(big.files, rr);
    expect.sort((a, b) => a.c - b.c || (a.id < b.id ? -1 : 1));
    const first = expect.slice(0, 100), inFirst = new Set(first.map(e => e.id));
    const goneFolders = big.folders.filter(d => /^big-/.test(d.id) && expect.filter(e => e.folder === d.id).every(e => inFirst.has(e.id)))
      .map(d => d.id).sort();
    const rb = trashPlan(big, nowMs, 90, 100);
    check('150 due files in 30 folders, maxFiles 100: the 100 earliest by due moment then id, capped 50, and only the folders ' +
          'all of whose files are among them', !rb.error && same(normT(rb.plan).files, first.map(e => e.key)) && rb.plan.capped === 50 &&
          same(folderOrder(rb.plan).slice().sort(), goneFolders),
          rb.error || 'files ' + list(rb.plan, 'files').length + ', capped ' + (rb.plan && rb.plan.capped) + ', folders ' + folderOrder(rb.plan).join(','));
  }

  console.log('\nplanTrash_ — retentionDays below 90 or not a whole number, maxFiles below 1: throws');
  {
    const drive = { regions: { Africa: 'reg-africa' }, rootId: ROOT,
                    folders: [AFRICA, FD('s', 'Sunrise Club 10-23-2026', 'reg-africa', '2026-10-24T09:00:00Z')],
                    files: [FL('f1', 's', '2026-10-23T08:00:00Z'), FL('f2', 's', '2026-10-23T08:01:00Z')] };
    const nowMs = Date.UTC(2027, 1, 1);   // 100 days after the folder: due at 90, and at 89
    const BAD_DAYS = [89, 0, -90, 90.5, 89.999, NaN, '90', null, undefined, Infinity];
    const BAD_MAX = [0, -1, 1.5, NaN, '100', null, undefined, Infinity];
    const shown = v => (typeof v === 'string' ? JSON.stringify(v) : String(v));
    const notThrown = BAD_DAYS.filter(v => !trashPlan(drive, nowMs, v, 100).error).map(shown);
    check('retentionDays 89, 0, -90, 90.5, 89.999, NaN, \'90\', null, undefined, Infinity: refused (throws)',
          !!planTrashFn && !notThrown.length, planTrashFn ? 'not refused: ' + notThrown.join(', ') : 'planTrash_ is not defined');
    const notThrownMax = BAD_MAX.filter(v => !trashPlan(drive, nowMs, 90, v).error).map(shown);
    check('maxFiles 0, -1, 1.5, NaN, \'100\', null, undefined, Infinity: refused (throws)',
          !!planTrashFn && !notThrownMax.length, planTrashFn ? 'not refused: ' + notThrownMax.join(', ') : 'planTrash_ is not defined');
    const fine = [[90, 100, 2], [91, 100, 2], [99, 100, 2], [100, 100, 0], [365, 100, 0], [90, 1, 1]].map(([d, m, n]) => {
      const r = trashPlan(drive, nowMs, d, m);
      return r.error || list(r.plan, 'files').length !== n ? d + '/' + m + ': ' + (r.error || list(r.plan, 'files').length + ' file(s), want ' + n) : '';
    }).filter(Boolean);
    check('…while retentionDays 90, 91, 99, 100, 365 and maxFiles 1 or 100 plan (2, 2, 2, 0, 0 files: the folder is 99 days 15 hours old; 1 with maxFiles 1)',
          !!planTrashFn && !fine.length, fine.join('; ') || (planTrashFn ? '' : 'planTrash_ is not defined'));
  }

  console.log('\nretentionFolders_ — exactly the folders strictly below a region folder whose own created is at least retentionDays old; never a region folder, rootId or an outside folder');
  {
    let checked = 0, nonEmpty = 0;
    const misses = [];
    for (let seed = 1; seed <= 8; seed++) {
      for (let k = 0; k < T_NOWS.length; k++) {
        const nowMs = T_NOWS[k], days = T_DAYS[(seed + k) % T_DAYS.length];
        const { drive } = trashLayout(seed, nowMs, days);
        const want = trashOracle(drive, nowMs, days, Infinity).old;
        const got = oldFolders(drive, nowMs, days), bare = oldFolders(Object.assign({}, drive, { files: [] }), nowMs, days);
        checked++;
        if (want.length) nonEmpty++;
        if (got.error || bare.error || !same(sortedIds(got.ids), want) || !same(sortedIds(bare.ids), want)) {
          misses.push('seed ' + seed + ' now ' + new Date(nowMs).toISOString() + ': ' +
                      (got.error || bare.error || show(sortedIds(got.ids), want)));
        }
      }
    }
    check('generated trees (' + checked + '): the old folders below a region folder, whatever their files or `complete`, ' +
          'the same with `files` empty; no region folder, root, outside, loop or undated folder',
          !!oldFoldersFn && !misses.length && nonEmpty === checked, misses.join(' || ') || (oldFoldersFn ? '' : 'retentionFolders_ is not defined'));
    const nowMs = Date.UTC(2027, 1, 1, 12), R = 90 * DAY, O = nowMs - 150 * DAY;
    const drive = {
      regions: { Africa: 'reg-af', Template: 'reg-tp', Europe: 'odd-eu' }, rootId: ROOT,
      folders: [FD('reg-af', 'Africa', ROOT, O), FD('reg-tp', 'Template', 'reg-af', O), FD('reg-us', 'U.S', ROOT, O),
                FD('exact', 'Sunrise Club 10-01-2026', 'reg-af', nowMs - R, { complete: false }),
                FD('short', 'Rising Stars 10-01-2026', 'reg-af', nowMs - R + 1),
                FD('deep', 'extra', 'exact', O), FD('bad', 'Golden Wings 10-01-2026', 'reg-af', 'invalid'),
                FD('none', 'Silver Roots 10-01-2026', 'reg-af', null), FD('tp-sub', 'Evening Voices 10-01-2026', 'reg-tp', O),
                FD('us-sub', 'Bright Flames 10-01-2026', 'reg-us', O), FD('odd-eu', 'Europe', ROOT, O), FD('eu-sub', 'Morning Wings 10-01-2026', 'odd-eu', O),
                FD('kept', 'Kept', ROOT, O), FD('orphan', 'Silver Stars 10-01-2026', null, O), FD('lost', 'Golden Stars 10-01-2026', 'ghost-1', O),
                FD('loop-1', 'Day 1', 'loop-2', O), FD('loop-2', 'Day 2', 'loop-1', O), FD(ROOT, 'GLOW Shared Drive', 'reg-af', O)],
      files: [FL('x', 'exact', O)],
    };
    const r90 = oldFolders(drive, nowMs, 90), r120 = oldFolders(drive, nowMs, 120);
    check('exactly 90 days old (even listed incomplete) and one deeper: in; 1 ms younger, no valid created, a region folder ' +
          '(Template\'s inside Africa\'s), U.S\'s unconfigured folder and its subfolder, a key that is no region (Europe), the root ' +
          '(even listed below Africa), Kept, no parent, an unknown parent, a loop: never; inside Template\'s folder: in',
          !r90.error && same(sortedIds(r90.ids), ['deep', 'exact', 'tp-sub']), r90.error || JSON.stringify(r90.ids));
    check('…with retentionDays 120 the 90-day-old folder is out', !r120.error && same(sortedIds(r120.ids), ['deep', 'tp-sub']),
          r120.error || JSON.stringify(r120.ids));
  }

  console.log('\nplanTrash_ — no Google service touched, inputs unchanged, the same inputs give the same plan, no implicit globals');
  {
    const nowMs = Date.UTC(2027, 1, 1, 12), days = 90;
    const { drive } = trashLayout(42, nowMs, days);
    const d = reviveDrive ? sandboxDrive(drive) : null;
    const now = new CtxDate(nowMs);
    const snap = x => JSON.stringify(x, function (k, v) {
      const o = this[k];
      return Object.prototype.toString.call(o) === '[object Date]' ? 'Date ' + o.getTime() : v;
    });
    const before = snap(d);
    touched.length = 0;
    const p1 = inSandbox('planTrash_', [d, now, days, 7]), p2 = inSandbox('planTrash_', [d, now, days, 7]);
    const o1 = inSandbox('retentionFolders_', [d, now, days]), o2 = inSandbox('retentionFolders_', [d, now, days]);
    const err = p1.error || p2.error || o1.error || o2.error;
    check('no Google service is touched by planTrash_ or retentionFolders_ (DriveApp, Drive, PropertiesService …)',
          !err && !touched.length, err || touched.join(', '));
    check('the inputs are unchanged after planning (Dates, order and every field included; `now` too)',
          !err && !!d && snap(d) === before && now.getTime() === nowMs, err || 'changed');
    check('the same inputs give the same plan and the same folder list, in the same order',
          !err && snap(p1.out) === snap(p2.out) && snap(o1.out) === snap(o2.out) && list(p1.out, 'files').length > 0 &&
          list(p1.out, 'folders').length > 0, err || snap(p1.out).slice(0, 300));
    const stray = ctx ? loadGs.strayGlobals(ctx) : ['not loaded'];
    check('no implicit globals made by planTrash_ or retentionFolders_', !err && !stray.length, err || stray.join(', '));
  }

  console.log('\nplanTrash_ — run after run, the plan applied each time: everything due is gone within ceil(due / maxFiles) runs, and nothing else');
  {
    let spread = 0;
    for (let seed = 21; seed <= 26; seed++) {
      const nowMs = Date.UTC(2027, 1, 14, 9, 0, 0), days = 90;
      const { drive } = trashLayout(seed, nowMs, days);
      const start = trashOracle(drive, nowMs, days, Infinity);
      const dueIds = start.due.map(e => e.id).sort(), goIds = start.folders.map(e => e.id).sort();
      const maxFiles = 2 + seed % 5;
      const bound = Math.max(1, Math.ceil(dueIds.length / maxFiles));
      const model = { regions: drive.regions, rootId: drive.rootId, folders: drive.folders.slice(), files: drive.files.slice() };
      const trashedFiles = [], trashedFolders = [], problems = [];
      let worked = 0, error = '', ended = false;
      for (let run = 0; run < bound + 3; run++) {
        const got = trashPlan(model, nowMs, days, maxFiles);
        if (got.error) { error = got.error; break; }
        const p = got.plan, want = trashOracle(model, nowMs, days, maxFiles).want;
        if (!same(normT(p), want)) problems.push('run ' + run + ': ' + show(normT(p), want));
        if (!list(p, 'files').length && !list(p, 'folders').length) { ended = true; break; }
        worked++;
        for (const f of list(p, 'files')) {
          const i = model.files.findIndex(x => x.id === f.id);
          if (i < 0) { problems.push('run ' + run + ': ' + f.id + ' is not on the drive'); continue; }
          model.files.splice(i, 1);
          trashedFiles.push(f.id);
        }
        for (const fd of list(p, 'folders')) {   // in the plan's order, as the mover trashes them
          const inIt = model.files.filter(x => x.parent === fd.id).length + model.folders.filter(x => x.parent === fd.id).length;
          if (inIt) problems.push('run ' + run + ': folder ' + fd.id + ' trashed with ' + inIt + ' item(s) still in it');
          const i = model.folders.findIndex(x => x.id === fd.id);
          if (i < 0) { problems.push('run ' + run + ': folder ' + fd.id + ' is not on the drive'); continue; }
          model.folders.splice(i, 1);
          trashedFolders.push(fd.id);
        }
      }
      check('seed ' + seed + ': ' + dueIds.length + ' due file(s), maxFiles ' + maxFiles + ': gone within ' + bound + ' run(s) (' + worked +
            ' used), every emptied folder with them, and the next run plans nothing',
            !error && ended && worked <= bound && same(trashedFiles.slice().sort(), dueIds) && same(trashedFolders.slice().sort(), goIds),
            error || 'files ' + show(trashedFiles.slice().sort(), dueIds) + ' folders ' + show(trashedFolders.slice().sort(), goIds));
      check('seed ' + seed + ': nothing else - each run the rules\' answer, no folder trashed with anything in it, never a ' +
            'region folder, the root or an outside item',
            !error && !problems.length && !trashedFolders.concat(trashedFiles).some(x => x === drive.rootId ||
              Object.values(drive.regions).includes(x) || start.outside.some(e => e.id === x)),
            error || problems.join('; '));
      if (!error && ended && !problems.length && worked >= 3) spread++;
    }
    check('…and at least one of those drives took three or more runs, as the rules said (the cap spreads the trash over runs)',
          spread > 0, String(spread));
  }
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
                    'IMG_7100', 'IMG_7101', 'IMG_7201', 'IMG_7301', 'IMG_7777', 'IMG_8101', 'IMG_8102', 'IMG_9000', 'receipt',
                    'RET_', 'IMG_8201', 'IMG_8202']; // #182's Shared Drive photos (RET_ITEMS); #185's and #191's merged photos
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
 * #182: the fake Shared Drive's dated photos and folders for the 90-day retention (epic #179), on the fake in every
 * run (with RETENTION_DAYS unset nothing may read them). [label, age in days (createdTime = now - age days, to the ms)
 * or the raw createdTime string Drive would report, {trashed}]. A label ending in .jpg is a file, anything else a
 * folder; `T:drive/...` sits at the Shared Drive's root. The region folders themselves are RET_REGION_AGE days old; the
 * Shared Drive folders of FAKE_TARGETS, and what the moves make, are hours old (never due). Worked by hand in RET_WANT.
 */
const RDAY = 24 * 60 * MIN;
const RET_REGION_AGE = 400;
const RET_ITEMS = [
  // Africa: a photo directly in the region folder (due) beside two young ones (three: its listing takes two pages)
  ['T:Africa/RET_A0.jpg', 120], ['T:Africa/RET_A0y.jpg', 10], ['T:Africa/RET_A0z.jpg', 30],
  // due and young photos in an old subfolder (the young one is on its listing's second page), and a nested folder
  // two deep with a distinctive name and an old photo: the nested folder goes, the subfolder stays (its young photo)
  ['T:Africa/Sunrise Club 07-01-2026', 120], ['T:Africa/Sunrise Club 07-01-2026/RET_A1.jpg', 119],
  ['T:Africa/Sunrise Club 07-01-2026/RET_A2.jpg', 118], ['T:Africa/Sunrise Club 07-01-2026/RET_A3.jpg', 5],
  ['T:Africa/Sunrise Club 07-01-2026/Nested Zebra Album', 110],
  ['T:Africa/Sunrise Club 07-01-2026/Nested Zebra Album/RET_A4.jpg', 100],
  // an old subfolder whose photos are all due (it goes with them), an emptied old one (goes) and an emptied young one
  ['T:Africa/Bright Stars 07-10-2026', 100], ['T:Africa/Bright Stars 07-10-2026/RET_A5.jpg', 100],
  ['T:Africa/Bright Stars 07-10-2026/RET_A6.jpg', 95],
  ['T:Africa/Golden Wings 06-01-2026', 150], ['T:Africa/Rising Lights 10-20-2026', 10],
  // a club-only folder (made before 2026-10-30) holding one old and one young photo
  ['T:Africa/Morning Star Club', 200], ['T:Africa/Morning Star Club/RET_A7.jpg', 180], ['T:Africa/Morning Star Club/RET_A8.jpg', 20],
  // an old photo in a new folder (the folder's time decides: not due); an unparseable createdTime on a file, on a folder
  ['T:Africa/Silver Roots 10-25-2026', 5], ['T:Africa/Silver Roots 10-25-2026/RET_A9.jpg', 200],
  ['T:Africa/Evening Roots 06-15-2026', 140], ['T:Africa/Evening Roots 06-15-2026/RET_A10.jpg', 'not a time'],
  ['T:Africa/Golden Voices 06-20-2026', 'garbage'], ['T:Africa/Golden Voices 06-20-2026/RET_A11.jpg', 130],
  // Asia: two photos directly in the region folder, an old subfolder emptied by its three due photos, and an old
  // subfolder in the trash (its photos in the trash through it: never read, never counted)
  ['T:Asia/RET_S0.jpg', 200], ['T:Asia/RET_S0b.jpg', 150],
  ['T:Asia/Evening Lights 06-01-2026', 150], ['T:Asia/Evening Lights 06-01-2026/RET_S1.jpg', 140],
  ['T:Asia/Evening Lights 06-01-2026/RET_S2.jpg', 130], ['T:Asia/Evening Lights 06-01-2026/RET_S3.jpg', 120],
  ['T:Asia/Morning Flames 05-20-2026', 160, { trashed: true }], ['T:Asia/Morning Flames 05-20-2026/RET_S4.jpg', 155],
  ['T:Asia/Morning Flames 05-20-2026/RET_S5.jpg', 150],
  // Template: a chain three deep, every level with one due photo: all three folders go, deepest first
  ['T:Template/Silver Wings 05-01-2026', 200], ['T:Template/Silver Wings 05-01-2026/RET_T1.jpg', 190],
  ['T:Template/Silver Wings 05-01-2026/Nested Kiwi Shots', 190], ['T:Template/Silver Wings 05-01-2026/Nested Kiwi Shots/RET_T2.jpg', 185],
  ['T:Template/Silver Wings 05-01-2026/Nested Kiwi Shots/Nested Mango Shots', 180],
  ['T:Template/Silver Wings 05-01-2026/Nested Kiwi Shots/Nested Mango Shots/RET_T3.jpg', 175],
  // outside the region folders: an old photo in a folder at the Shared Drive's root
  ['T:drive/Kept Photos Archive', 300], ['T:drive/Kept Photos Archive/RET_K1.jpg', 250],
];
const RET_FILE_NAMES = RET_ITEMS.map(i => i[0].slice(i[0].lastIndexOf('/') + 1)).filter(n => /\.jpg$/.test(n));

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
 * 'trash': {trashed: true} | 'other'), resource, media, args, trash, wasTrashed, wasExplicit, fromTrashedSourceSub}.
 *
 * #185 adds retention's entry, and only it: the union of #144's and retention's allowances. For it each trash also
 * records, as the fake sees the item at the moment of the call: driveId (the drive it is on; undefined in My Drive),
 * region (the first configured TARGET_FOLDER_ folder met walking up from its parent, null when the root, a missing
 * parent or a loop comes first), createdMs and parentCreatedMs (Drive's createdTime of it and of its parent, NaN when
 * unparseable), liveChildren (its untrashed files and folders), retentionDays (the Script Property as the run reads
 * it: a whole number of at least 90, else null), t (the clock), and planned / parentAsPlanned / regionAsPlanned (the
 * real planTrash_ planned it this run, with that parent and that region: runEntry's spy records the plan before any
 * test replaces it). newly lists the ids the trash took out of service (it and what was in it, untrashed before).
 */
const TRASH_RULES = [
  { what: 'an empty, settled subfolder of a configured `Attendance photos - <Region>` folder, by Drive.Files.update {trashed: true} (#144)',
    allows: t => t.via === 'Drive.Files.update' && t.isFolder && t.role === 'source-sub' && !t.wasTrashed && t.children === 0 && t.settled },
  { what: 'retention (#185): a Shared Drive item planTrash_ planned this run, below a configured region folder (never one, never ' +
          'the root), its parent and region as planned, by Drive.Files.update {trashed: true}: a file past its due moment ' +
          '(RETENTION_DAYS after the later of its own and its folder\'s createdTime), or a folder at least RETENTION_DAYS old ' +
          'with no untrashed child at the moment of the call',
    allows: t => t.via === 'Drive.Files.update' && t.driveId === DRIVE_ROOT_ID && !t.structural && !t.wasTrashed && !!t.region &&
                 t.planned === true && t.parentAsPlanned === true && t.regionAsPlanned === true &&
                 typeof t.retentionDays === 'number' && t.retentionDays >= 90 &&
                 (t.isFolder ? t.liveChildren === 0 && t.t - t.createdMs >= t.retentionDays * RDAY
                   : t.t - Math.max(t.createdMs, t.parentCreatedMs) >= t.retentionDays * RDAY) },
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
                    t.children ? t.children + ' item(s) in it' : '', t.settled ? '' : 'not settled',
                    t.driveId ? 'on the Shared Drive' : 'in My Drive', t.region ? 'under ' + t.region : 'under no region folder',
                    t.liveChildren ? t.liveChildren + ' untrashed item(s) in it' : '', t.planned ? '' : 'not planned',
                    t.planned && !t.parentAsPlanned ? 'not in its planned folder' : '',
                    t.planned && !t.regionAsPlanned ? 'not in its planned region' : ''].filter(Boolean).join(', ');
  return [...new Set(r.calls.filter(NEVER).map(c => 'called ' + c)
    .concat(r.trashes.filter(t => t.structural).map(t => 'trashed ' + t.label + ' (a configured folder or the Shared Drive\'s root)'))
    .concat(r.trashes.filter(t => !t.viaHelper).map(t => 'trashed ' + t.label + ' outside ' + TRASH_HELPER))
    .concat(r.trashes.filter(t => !TRASH_RULES.some(rule => rule.allows(t))).map(t => 'trashed ' + t.label + ' (' + why(t) + ')'))
    .concat(r.ops.filter(o => o.op === 'update' && !UPDATE_RULES.some(rule => rule.allows(o)))
      .map(o => 'Files.update ' + JSON.stringify(o.resource) + ' on ' + (o.label || o.fileId))))];
}

/** An item's createdTime in ms as the fake's Drive reports it (#182): NaN when it reports an unparseable one. */
const itemCreatedMs = m => (m.createdRaw !== undefined ? Date.parse(m.createdRaw) : (m.createdAt || m.updatedAt));
const RFC3339 = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,9})?(Z|[+-]\d{2}:\d{2})$/;
/**
 * A Drive v3 search query (`q`) as a predicate on the fake's items: `'<id>' in parents`, `trashed = | != true|false`,
 * `mimeType = | != '<x>'`, `name = | != '<x>'`, `createdTime <= | < | = | != | > | >= '<RFC 3339>'` (#182), joined by
 * and / or / not and parentheses. Anything else throws (the fake does not guess). Also returns the parent ids and names
 * it names, whether it says `trashed` explicitly (and to what), its mimeType clauses and its createdTime clauses.
 */
function parseDriveQuery(q) {
  const src = String(q), toks = [];
  const re = /\s*(?:'((?:[^'\\]|\\.)*)'|(!=|<=|>=|=|<|>|\(|\))|([A-Za-z]+))/y;
  let i = 0;
  while (i < src.length && src.slice(i).trim()) {
    re.lastIndex = i;
    const m = re.exec(src);
    if (!m) throw new Error('Files.list: the query cannot be read at "' + src.slice(i, i + 20) + '" (fake)');
    i = re.lastIndex;
    toks.push(m[1] !== undefined ? { str: m[1].replace(/\\(.)/g, '$1') } : m[2] ? { op: m[2] } : { word: m[3] });
  }
  const info = { parents: [], names: [], trashedClause: false, trashedValues: [], mimes: [], created: [] };
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
      info.trashedValues.push(op === '=' ? want : !want);
      return op === '=' ? m => m.trashed === want : m => m.trashed !== want;
    }
    if (t.word === 'createdTime') {
      const o = toks[p++];
      const CMP = { '<=': (a, b) => a <= b, '<': (a, b) => a < b, '=': (a, b) => a === b, '!=': (a, b) => a !== b,
                    '>': (a, b) => a > b, '>=': (a, b) => a >= b };
      if (!o || !own(CMP, o.op || '')) fail('a comparison expected after createdTime');
      const v = toks[p++];
      if (!v || v.str === undefined || !RFC3339.test(v.str)) fail('a quoted RFC 3339 date-time expected after createdTime');
      const at = Date.parse(v.str);
      info.created.push({ op: o.op, at });
      return m => { const c = itemCreatedMs(m); return !isNaN(c) && CMP[o.op](c, at); };
    }
    if (t.word === 'mimeType' || t.word === 'name') {
      const op = operator(), v = toks[p++];
      if (!v || v.str === undefined) fail('a quoted value expected after ' + t.word);
      if (t.word === 'name' && op === '=') info.names.push(v.str);
      if (t.word === 'mimeType') info.mimes.push({ op, value: v.str });
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
 *
 * #182, the Shared Drive for the 90-day retention. Script Properties: RETENTION_DAYS is opt.retentionDays (absent:
 * null, as Apps Script answers an unset key), opt.props overrides any key; every other key as above. The Shared Drive
 * holds RET_ITEMS (and opt.extra, the same shape with ages in ms) besides FAKE_TARGETS; every item on it reports
 * createdTime (RFC 3339, to the ms; or the raw string given), parents [its one parent] and driveId (the drive of its
 * root ancestor: DRIVE_ROOT_ID; opt.targetDrive {region: other drive id | null for none} moves a target folder and all
 * below it to another drive or off every Shared Drive). opt.trashedTarget: that region's target folder is in the
 * trash. opt.moveFolders [[label, new parent label]], opt.rootName (the root's name). Files.list knows corpora 'drive'
 * (driveId required, and only that drive's items returned; never the root itself) and the createdTime clause, pages at
 * most two items, and records each read with its kind ('source': a My Drive folder named in parents | 'listing': a
 * Shared Drive folder named in parents | 'folders': no parents, mimeType = folder | 'due': no parents, a createdTime
 * clause | 'other'), its chain (the first page and the pages that follow it), page number, whether it was the last
 * page, and the q's trashed values, mimeType and createdTime clauses and parents. opt.searchAdvanceMin: the clock jumps
 * that many minutes on each page of a drive-wide folder search; opt.listAdvanceMin: on each page of a Shared Drive
 * folder's listing; opt.failSearch {kind, page, of}: that page of that kind of search throws (with `of`, a folder label,
 * only a listing naming that folder). model() lists every item as the fake holds it now; labelOf(id); planTrashCalls,
 * planTrash_'s calls (runEntry spies on it: each folder's id and `complete`, and the folders it planned).
 *
 * #185, the trash on the Shared Drive. A Files.update {trashed: true} trashes the item and everything in it, and every
 * later read sees it (Files.get trashed true, a `trashed = false` listing leaves it out, DriveApp isTrashed() true).
 * opt.failTrashOf [labels]: a {trashed: true} update of one of them throws (Drive says no; nothing trashed; the op keeps
 * the attempt as its `trash`, refused: true, so UPDATE_RULES judge it as any trash).
 * opt.trashAdvanceMin: the clock jumps that many minutes after each Shared Drive trash. opt.recheckAdvanceMin: after
 * planTrash_ has returned, on each Files.get and each Files.list page. opt.afterPlan [[what, label, x]]: right after
 * the run's first planTrash_ returns (after the read, before any trash), the Shared Drive changes: 'move' (label into
 * the folder labelled x), 'trash' (a person trashes it), 'created' (its createdTime becomes now - x ms), 'add' (a new
 * photo, or folder for a label not ending .jpg, created now - x ms). opt.afterFirstTrash [[what, label, x]]: the same
 * changes, right after the run's first Shared Drive trash (mid-trash); opt.midTrash, changes picked after the n-th photo
 * trash or the first folder trash (midTrash below). opt.replacePlan({idOf, Date, now, args, planTrash}): what
 * planTrash_ returns instead of its own plan (args: the call's; planTrash: the real one; the real plan is still
 * recorded, for TRASH_RULES). Every read and write carries `seq`, their order. opt.extraSources
 * [[region, name, files]]: more My Drive subfolders, as in FAKE_SOURCES. opt.staleIndexOf (a Shared Drive folder's
 * label): the first Files.list naming it in parents misses what this run moved into it (Drive's search index behind
 * its writes); later listings see it.
 *
 * #191, Drive's search index behind a merge for the whole run. opt.staleIndexAlways [Shared Drive folder labels]: every
 * search this run (any Files.list, whatever its q, and DriveApp's doors onto a folder's files) misses the files this
 * run moved into one of those folders, at the read and at the re-check alike; Files.get by id sees them where they
 * are; the next run's searches see them (the index caught up). staleHits records each search that missed one
 * ({folder: its label, afterPlan: planTrash_ had returned}). opt.beforeRetentionRead [[what, label, x]]: opt.afterPlan's
 * changes, made right before the run's first drive-wide folder search (the retention read's first step: after the
 * moves, before the Shared Drive is read). opt.unlistedAlways [labels]: Drive's search at its most contrary: no
 * `'<parent>' in parents` search this run, nor DriveApp's doors onto the parent, returns these items; a drive-wide
 * search still finds them (with their parents) and Files.get sees them. opt.moveKeepsModified [folder labels]: a move
 * into one of them leaves its modifiedTime as it was (Drive need not bump a folder's when a file lands in it).
 * planSeq: the `seq` of the last Drive read or write before the run's first planTrash_ returned (null before).
 */
function fakeEnv(mode, opt) {
  opt = opt || {};
  const calls = [], moved = [], attempted = [], created = [], ops = [], reads = [], trashes = [], logs = [], read = new Set();
  const planTrashCalls = [];
  // #185: what planTrash_ planned this run (id -> {parent, region}), whether it has returned, whether opt.afterPlan ran;
  // the ids this run moved (opt.staleIndexOf)
  const planState = { planned: false, after: false, midDone: false, beforeRead: false, planSeq: null, ids: new Map() },
        movedIn = new Set(), stale = { used: false }, staleHits = [];   // #191: beforeRead, planSeq, staleHits
  // #185: every Drive read and write gets the next number (`seq`: their order, the clock aside); the opt.midTrash changes
  // made, and how many Shared Drive trashes (photos, folders) this run has made
  const order = { seq: 0, files: 0, folders: 0 }, midApplied = [];
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
  /** #191, opt.staleIndexAlways: true (and recorded) for an item this run moved into one of those folders: no search finds it. */
  const staleHit = mm => {
    const lbls = [].concat(opt.staleIndexAlways || []);
    if (!lbls.length || !mm || !movedIn.has(mm.id) || !lbls.some(l => idOf[l] === mm.parent)) return false;
    staleHits.push({ folder: meta.get(byId[mm.parent]).label, afterPlan: planState.planned });
    return true;
  };
  /** #191, opt.unlistedAlways: true for an item no listing of its parent returns this run. */
  const unlisted = x => [].concat(opt.unlistedAlways || []).includes((meta.get(x) || {}).label);
  // DriveApp's moveTo: into a Shared Drive folder it fails as the live one did (#132)
  const moveTo = (self, dest) => {
    attempted.push(label(self));
    if (onSharedDrive(dest)) throw new Error('cannot use this operation on a shared drive item (fake)');
    moved.push(label(self) + ' -> ' + label(dest));
    return self;
  };
  const below = m => (m.isFolder ? [].concat(...m.kids.map(k => [meta.get(k)].concat(below(meta.get(k)))), m.files.map(f => meta.get(f))) : []);
  /** #185: the region an item is under now: the first configured TARGET_FOLDER_ folder met walking up from its parent. */
  const regionWalk = m => {
    const targets = {};
    for (const reg of REGIONS) {
      const id = propsValue('TARGET_FOLDER_' + PROP_KEYS[reg]);
      if (id) targets[id] = reg;
    }
    const met = new Set();
    for (let id = m.parent; ;) {
      if (!id || id === DRIVE_ROOT_ID || met.has(id) || !byId[id]) return null;
      if (own(targets, id)) return targets[id];
      met.add(id);
      id = meta.get(byId[id]).parent;
    }
  };
  /** #185: RETENTION_DAYS as the run reads it (a whole number of at least 90, spaces trimmed), else null. */
  const retentionDaysNow = () => {
    const v = propsValue('RETENTION_DAYS');
    const s = v === null || v === undefined ? '' : String(v).trim();
    return /^\d+$/.test(s) && Number(s) >= 90 ? Number(s) : null;
  };
  /**
   * A trash by any door: recorded with the item's state at that moment, then done (the item and everything in it
   * trashed). #185: `refused` (opt.failTrashOf) describes the attempt the same way and throws, recording and changing
   * nothing else, so the rules still judge what was asked for.
   */
  const trashItem = (item, via, refused) => {
    const m = meta.get(item);
    const parentM = m.parent && byId[m.parent] ? meta.get(byId[m.parent]) : null;
    const region = regionWalk(m), plannedAs = planState.ids.get(m.id);
    const t = { via, id: m.id, label: m.label, isFolder: m.isFolder, role: m.role, structural: !!m.structural,
                viaHelper: helper.depth > 0, wasTrashed: m.trashed,
                children: m.isFolder ? m.kids.length + m.files.length : 0, settled: clock.t - m.updatedAt >= FAKE_SETTLE_MIN * MIN, t: clock.t,
                driveId: driveOf(m), region, createdMs: itemCreatedMs(m), parentCreatedMs: parentM ? itemCreatedMs(parentM) : NaN,
                liveChildren: m.isFolder ? m.kids.concat(m.files).filter(k => !meta.get(k).trashed).length : 0,
                retentionDays: retentionDaysNow(), planned: !!plannedAs,
                parentAsPlanned: !!plannedAs && plannedAs.parent === m.parent, regionAsPlanned: !!plannedAs && plannedAs.region === region,
                newly: [m].concat(below(m)).filter(d => !d.trashed).map(d => d.id) };
    if (refused) {
      refused.trash = Object.assign(t, { refused: true, newly: [] });
      throw new Error('Drive said no (fake trash)');
    }
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
    const snap = m.kids.filter(k => !unlisted(k));   // (#191: all of them, unless opt.unlistedAlways says otherwise)
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
      return isSourceSub ? listed(m) : files.filter(f => !staleHit(meta.get(f)) && !unlisted(f));   // #191: the index behind
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
  /** The drive an item is on (#182): that of its root ancestor, or a target folder's override; undefined in My Drive. */
  const driveOf = m => {
    let cur = m;
    for (let i = 0; cur && i < 100; i++) {
      if (own(cur, 'driveOverride')) return cur.driveOverride || undefined;
      if (cur.id === DRIVE_ROOT_ID) return DRIVE_ROOT_ID;
      cur = cur.parent && byId[cur.parent] ? meta.get(byId[cur.parent]) : null;
    }
    return undefined;
  };
  const resourceOf = m => {
    const r = { kind: 'drive#file', id: m.id, name: m.name, mimeType: m.isFolder ? DRIVE_FOLDER_MIME : m.mime,
                parents: m.parent ? [m.parent] : [], trashed: m.trashed, explicitlyTrashed: m.explicitlyTrashed,
                modifiedTime: new Date(m.updatedAt).toISOString(),
                createdTime: m.createdRaw !== undefined ? m.createdRaw : new Date(itemCreatedMs(m)).toISOString() };
    if (!m.isFolder) r.size = String(m.size);
    const drive = driveOf(m);
    if (drive) r.driveId = drive;
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
  let pages = 0, chains = 0;
  const filesList = args => {
    args = args || {};
    const rec = { op: 'list', t: clock.t, seq: ++order.seq, args: Object.assign({}, args) };
    reads.push(rec);
    let results, offset, chain;
    if (args.pageToken) {
      const tok = pageTokens[args.pageToken];
      if (!tok || tok.q !== args.q) throw new Error('Files.list: invalid pageToken, or another q with it (fake)');
      results = tok.results;
      offset = tok.offset;
      chain = tok.chain;
    } else {
      if (typeof args.q !== 'string' || !args.q.trim()) throw new Error('Files.list: no q (fake: the mover never lists every file)');
      const parsed = parseDriveQuery(args.q);
      if (opt.beforeRetentionRead && !planState.beforeRead && !parsed.parents.length && !parsed.created.length &&
          parsed.mimes.some(x => x.op === '=' && x.value === DRIVE_FOLDER_MIME)) {   // #191: a change before the retention read
        planState.beforeRead = true;
        for (const step of opt.beforeRetentionRead) mutate(step);
      }
      // #182: corpora as Drive takes it: 'drive' needs a driveId and returns that drive's items only
      if (args.corpora !== undefined && args.corpora !== 'drive' && args.corpora !== 'user') {
        throw new Error('Files.list: corpora ' + JSON.stringify(args.corpora) + ' (fake knows drive and user)');
      }
      if (args.corpora === 'drive' && (typeof args.driveId !== 'string' || !args.driveId)) {
        throw new Error('Files.list: corpora drive needs the driveId (fake)');
      }
      if (args.driveId !== undefined && args.corpora !== 'drive') throw new Error('Files.list: a driveId only with corpora drive (fake)');
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
          let snap = kidsSnap.concat(filesSnap).filter(x => !unlisted(x));   // #191: opt.unlistedAlways
          if (opt.staleIndexOf && idOf[opt.staleIndexOf] === pid && !stale.used) {   // #185: the index behind this run's moves
            stale.used = true;
            snap = snap.filter(x => !movedIn.has(meta.get(x).id));
          }
          candidates.push(...snap);
        }
      } else candidates = Object.values(byId).filter(x => meta.get(x).id !== DRIVE_ROOT_ID);   // a drive's root is no search result
      results = candidates.map(x => meta.get(x)).filter(m => (everyDrive || !m.label.startsWith('T:')) &&
                                                             (args.corpora !== 'drive' || driveOf(m) === args.driveId) && parsed.test(m) &&
                                                             !staleHit(m))   // #191: the index behind a merge, any search
        .map(resourceOf);
      offset = 0;
      const labels = parsed.parents.map(pid => (byId[pid] ? meta.get(byId[pid]).label : ''));
      const kind = parsed.parents.length ? (labels.some(l => l.startsWith('S:')) ? 'source' : 'listing') :
        parsed.created.length ? 'due' : parsed.mimes.some(x => x.op === '=' && x.value === DRIVE_FOLDER_MIME) ? 'folders' : 'other';
      chain = { id: ++chains, kind, pages: 0, parents: parsed.parents.slice(), trashedValues: parsed.trashedValues.slice(),
                mimes: parsed.mimes.slice(), created: parsed.created.slice() };
    }
    chain.pages++;
    const size = Math.min(PAGE, args.pageSize > 0 ? args.pageSize : PAGE);
    const page = results.slice(offset, offset + size);
    let next = null;
    if (offset + size < results.length) {
      next = 'fake-page-' + (++pages);
      pageTokens[next] = { q: args.q, results, offset: offset + size, chain };
    }
    Object.assign(rec, { kind: chain.kind, chain: chain.id, page: chain.pages, last: !next, parents: chain.parents,
                         trashedValues: chain.trashedValues, mimes: chain.mimes, created: chain.created, returned: page.length });
    if (opt.searchAdvanceMin && chain.kind === 'folders') clock.t += opt.searchAdvanceMin * MIN;
    if (opt.listAdvanceMin && chain.kind === 'listing') clock.t += opt.listAdvanceMin * MIN;
    if (opt.recheckAdvanceMin && planState.planned) clock.t += opt.recheckAdvanceMin * MIN;
    if (opt.failSearch && opt.failSearch.kind === chain.kind && opt.failSearch.page === chain.pages &&
        (!opt.failSearch.of || chain.parents.includes(idOf[opt.failSearch.of]))) {
      rec.failed = true;   // the caller never got this page
      throw new Error('Drive said no (fake search)');
    }
    return shapeList(page, next, args.fields);
  };
  const filesGet = (fileId, args) => {
    reads.push({ op: 'get', t: clock.t, seq: ++order.seq, fileId, args: Object.assign({}, args) });
    if (opt.recheckAdvanceMin && planState.planned) clock.t += opt.recheckAdvanceMin * MIN;
    const item = byId[fileId];
    if (!item) throw new Error('Files.get: File not found: ' + String(fileId) + ' (fake)');
    const m = meta.get(item);
    if (m.label.startsWith('T:') && !(args && args.supportsAllDrives === true)) {
      throw new Error('Files.get: File not found: ' + String(fileId) + ' (fake: a Shared Drive item needs supportsAllDrives)');
    }
    return shapeFile(resourceOf(m), args && args.fields);
  };
  const filesCreate = (resource, media, args) => {
    ops.push({ op: 'create', t: clock.t, seq: ++order.seq, args: Object.assign({}, args) });
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
    const op = { op: 'update', kind, t: clock.t, seq: ++order.seq, args: Object.assign({}, args), fileId: fileId,
                 resource: Object.assign({}, r), media: media, ok: false };
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
      if (opt.failTrashOf && opt.failTrashOf.includes(m.label)) trashItem(item, 'Drive.Files.update', op);   // #185: throws
      op.trash = trashItem(item, 'Drive.Files.update');
      op.ok = true;
      if (opt.trashAdvanceMin && m.label.startsWith('T:')) clock.t += opt.trashAdvanceMin * MIN;
      if (opt.afterFirstTrash && m.label.startsWith('T:') && !planState.midDone) {   // #185: the drive changes mid-trash
        planState.midDone = true;
        for (const step of opt.afterFirstTrash) mutate(step);
      }
      if (m.label.startsWith('T:')) midTrash(m);
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
    if (![].concat(opt.moveKeepsModified || []).includes(meta.get(dest).label)) meta.get(dest).updatedAt = clock.t;   // #191
    if (kind === 'rescue' && !opt.rescueStaysTrashed) Object.assign(m, { trashed: false, explicitlyTrashed: false });
    moved.push(m.label + ' -> ' + label(dest));
    movedIn.add(m.id);
    op.ok = true;
    if (opt.moveAdvanceMin) clock.t += opt.moveAdvanceMin * MIN;
    return shapeFile(resourceOf(m), args.fields);
  };
  const propId = propIdOf;
  const sourceFolders = [], propFolders = {}, targetFolders = [];
  for (const region of REGIONS) {
    const extraSubs = (opt.extraSources || []).filter(e => e[0] === region).map(e => e.slice(1));   // #185
    const subs = FAKE_SOURCES[region].concat(extraSubs).map(([nm, fl, x]) => {
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
  meta.get(mkFolder('T:drive', opt.rootName || 'GLOW Shared Drive', targetFolders.slice(), [], false, undefined, undefined,
                    DRIVE_ROOT_ID)).structural = true;
  // #182: the dated photos and folders on the Shared Drive (RET_ITEMS, then opt.extra), the region folders old
  for (const tgt of targetFolders) meta.get(tgt).createdAt = clock.t - RET_REGION_AGE * RDAY;
  const toTrash = [];
  const place = (lbl, created, x) => {
    const cut = lbl.lastIndexOf('/');
    const parentLabel = lbl.slice(0, cut), name = lbl.slice(cut + 1);
    const parent = byLabel[parentLabel];
    if (cut < 0 || !parent || !meta.get(parent).isFolder) throw new Error('fake: no folder ' + parentLabel + ' for ' + lbl);
    const isDir = !/\.jpg$/.test(name);
    const self = isDir ? mkFolder(lbl, name, [], [], false) : mkFile(parentLabel, name, 1000 + (n % 9000), OLD);
    const m = meta.get(self);
    if (typeof created === 'number') m.createdAt = clock.t - created;
    else m.createdRaw = String(created);
    m.parent = meta.get(parent).id;
    (isDir ? meta.get(parent).kids : meta.get(parent).files).push(self);
    if (x && x.trashed) toTrash.push(self);
  };
  for (const [lbl, days, x] of RET_ITEMS) place(lbl, typeof days === 'number' ? days * RDAY : days, x);
  for (const [lbl, ms, x] of opt.extra || []) place(lbl, ms, x);
  for (const [lbl, to] of opt.moveFolders || []) {
    const x = byLabel[lbl], dest = byLabel[to], m = meta.get(x);
    const from = meta.get(byId[m.parent]);
    from.kids.splice(from.kids.indexOf(x), 1);
    meta.get(dest).kids.push(x);
    m.parent = meta.get(dest).id;
  }
  for (const [reg, drive] of Object.entries(opt.targetDrive || {})) meta.get(byLabel['T:' + reg]).driveOverride = drive;
  if (opt.trashedTarget) toTrash.push(byLabel['T:' + opt.trashedTarget]);
  for (const x of toTrash) binned(x);
  /** #185, opt.afterPlan: one change on the Shared Drive between the read and the trash. */
  const mutate = ([what, lbl, x]) => {
    if (what === 'add') return place(lbl, x);
    const it = byLabel[lbl];
    if (!it) throw new Error('fake: no item ' + lbl);
    const m = meta.get(it);
    if (what === 'move') {
      const dest = byLabel[x], from = meta.get(byId[m.parent]), key = m.isFolder ? 'kids' : 'files';
      if (!dest || !meta.get(dest).isFolder) throw new Error('fake: no folder ' + x);
      from[key].splice(from[key].indexOf(it), 1);
      meta.get(dest)[key].push(it);
      m.parent = meta.get(dest).id;
    } else if (what === 'trash') binned(it);
    else if (what === 'created') { m.createdAt = clock.t - x; delete m.createdRaw; }
    else throw new Error('fake: no change ' + what);
    return undefined;
  };
  /**
   * #185: runEntry's spy hands each planTrash_ result here: the real plan is recorded (TRASH_RULES' planned), the first
   * time opt.afterPlan changes the Shared Drive, and opt.replacePlan's plan (if any) is what the code gets.
   */
  const onPlanned = (out, c, args, orig) => {
    planState.planned = true;
    for (const e of [].concat((out && out.files) || [], (out && out.folders) || [])) {
      if (e && e.id) planState.ids.set(e.id, { parent: e.parent, region: e.region });
    }
    if (!planState.after) {
      planState.after = true;
      planState.planSeq = order.seq;   // #191
      for (const step of opt.afterPlan || []) mutate(step);
    }
    return opt.replacePlan ? opt.replacePlan({ idOf, Date: vm.runInContext('Date', c), now: clock.t, args: [...args],
                                               planTrash: (...a) => orig.apply(null, a) }) : out;
  };
  /**
   * #185, opt.midTrash [{after: n (the n-th Shared Drive photo trash) | 'folder' (the first Shared Drive folder trash),
   * change: view => [[what, label, x]]}]: right after that trash, change(view) picks the changes from what is left
   * (view.left(): the planned items not yet in the trash, {label, isFolder, parent: its parent's label}); they are made
   * and recorded in midApplied.
   */
  const midTrash = m => {
    if (m.isFolder) order.folders++;
    else order.files++;
    for (const e of opt.midTrash || []) {
      if (e.done || (e.after === 'folder' ? !(m.isFolder && order.folders === 1) : m.isFolder || order.files !== e.after)) continue;
      e.done = true;
      const left = () => [...planState.ids.keys()].filter(id => byId[id] && !meta.get(byId[id]).trashed).map(id => {
        const x = meta.get(byId[id]);
        return { label: x.label, isFolder: x.isFolder, parent: x.parent && byId[x.parent] ? meta.get(byId[x.parent]).label : null };
      }).sort((a, b) => (a.label < b.label ? -1 : a.label > b.label ? 1 : 0));
      const steps = e.change({ left });
      for (const step of steps) mutate(step);
      midApplied.push({ after: e.after, steps });
    }
  };
  const newRun = () => {   // the trigger's next run on the same fake Drive
    Object.assign(planState, { planned: false, after: false, midDone: false, beforeRead: false, planSeq: null });
    planState.ids.clear();
    movedIn.clear();
    stale.used = false;
    staleHits.length = 0;
    Object.assign(order, { files: 0, folders: 0 });
    midApplied.length = 0;
  };
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
  const propsValue = k => {
    if (mode !== 'ids') return null;
    if (opt.props && own(opt.props, k)) return opt.props[k];
    if (k === 'RETENTION_DAYS') return own(opt, 'retentionDays') ? opt.retentionDays : null;   // #182: its own value
    return propId(k);
  };
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
  const model = () => Object.values(byId).map(x => {
    const m = meta.get(x);
    return { id: m.id, label: m.label, name: m.name, isFolder: m.isFolder, parent: m.parent, created: itemCreatedMs(m),
             trashed: m.trashed, driveId: driveOf(m) };
  });
  const labelOf = id => (byId[id] ? meta.get(byId[id]).label : own(gone, id) ? gone[id] : null);
  return { calls, moved, attempted, created, ops, reads, trashes, logs, read, readCount, firstListing, idOf, listedAll, lookups, t0,
           globals, install, state, advance, helper, model, labelOf, planTrashCalls, onPlanned, newRun, midApplied, staleHits,
           planSeq: () => planState.planSeq };
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
 * #182: planTrash_ wrapped in the sandbox, each call recorded: the folders it was given ({id, complete}), retentionDays,
 * maxFiles, and the ids of the folders it planned. #185: its result goes through onPlanned (the fake's hook: the plan
 * recorded, opt.afterPlan, opt.replacePlan), and the code gets what that returns.
 */
function spyPlanTrash(c, calls, onPlanned) {
  const orig = c.planTrash_;
  if (typeof orig !== 'function') return;
  c.planTrash_ = function (drive, now, days, maxFiles) {
    const rec = { folders: drive && Array.isArray(drive.folders) ? drive.folders.map(d => ({ id: d && d.id, complete: d && d.complete })) : null,
                  days, maxFiles, planned: null };
    calls.push(rec);
    let out = orig.apply(this, arguments);
    if (onPlanned) out = onPlanned(out, c, arguments, orig);
    rec.planned = out && Array.isArray(out.folders) ? out.folders.map(f => f && f.id) : null;
    return out;
  };
}
/**
 * One entry point on a fresh fake Drive; the result's records are copies (state and idOf read the fake Drive as it is
 * now). Its `rerun(opt)` runs the same entry point again on the SAME fake Drive (the trigger's next run), with other
 * options and the records starting afresh; opt.advanceMin moves the clock on first. #185: modelBefore() is model()
 * with this run's trashes undone (the Shared Drive as its retention read saw it: after the moves, before the trashes).
 */
function runEntry(name, mode, opt) {
  opt = opt || {};
  const env = fakeEnv(mode, opt);
  let c = null;
  const once = () => {
    let threw = '';
    try {
      if (!c) {
        c = loadGs.sandbox(GS, env.globals);
        env.install(c);
        spyTrashHelper(c, env.helper);
        spyPlanTrash(c, env.planTrashCalls, env.onPlanned);
      }
      vm.runInContext(name + '();', c, { timeout: 5000 });
    } catch (e) { threw = String(e && e.message || e); }
    const newly = new Set([].concat(...env.trashes.map(t => t.newly || [])));
    const res = { helperCalls: env.helper.calls.slice(), name, threw, text: env.logs.join('\n'), calls: env.calls.slice(), moved: env.moved.slice(),
                  attempted: env.attempted.slice(), created: env.created.slice(), ops: env.ops.slice(), reads: env.reads.slice(),
                  trashes: env.trashes.slice(), read: new Set(env.read), readCount: Object.assign({}, env.readCount),
                  firstListing: Object.assign({}, env.firstListing), listedAll: Object.assign({}, env.listedAll),
                  lookups: env.lookups.slice(), idOf: env.idOf, state: env.state, t0: env.t0, rerun,
                  planTrashCalls: env.planTrashCalls.slice(), model: env.model, labelOf: env.labelOf, opt: Object.assign({}, opt),
                  modelBefore: () => env.model().map(m => (newly.has(m.id) ? Object.assign({}, m, { trashed: false }) : m)),
                  midApplied: env.midApplied.slice(), staleHits: env.staleHits.slice(), planSeq: env.planSeq() };
    RUNS.push(res);
    return res;
  };
  const rerun = next => {
    for (const k of Object.keys(opt)) delete opt[k];
    Object.assign(opt, next || {});
    env.newRun();   // (#191: staleHits too)
    for (const a of [env.calls, env.moved, env.attempted, env.created, env.ops, env.reads, env.trashes, env.logs, env.lookups,
                     env.helper.calls, env.planTrashCalls]) a.length = 0;
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

// ================================================================ #182: the retention read path and the would-trash preview
/**
 * #182 (epic #179, rulings R4, R5, R7, R12, R14; docs/plans/2026-10-30-photo-retention.md): with the Script Property
 * RETENTION_DAYS set, both entry points read the Shared Drive the target folders are on, run #181's planTrash_ and log
 * what it would trash; the dry run trashes or changes nothing on the Shared Drive, the real run nothing outside that
 * plan (#185 trashes the plan, on apply: its own part at the end of this section). The contract, as these tests read it:
 *
 *   RETENTION_DAYS  absent or blank (spaces only): off, `retention off` logged, no retention read, planTrash_ not
 *                   called. A whole number of 90 or more, spaces trimmed: on. Anything else: CONFIG refused for the whole
 *                   run, naming RETENTION_DAYS, before any folder is opened (no *ById call, no Drive read, no write).
 *   one Shared Drive  with retention on, before any move: each target folder (Drive.Files.get) has a driveId, all the
 *                   same, none trashed; otherwise CONFIG refused, no write.
 *   the reads       after the moves and inside the run's time budget, every one a Drive.Files.list with corpora 'drive',
 *                   that driveId, supportsAllDrives and includeItemsFromAllDrives, `trashed = false` stated, followed
 *                   through nextPageToken to the end: every folder on the drive; the files with createdTime at or before
 *                   now - days; every file of each folder retentionFolders_ names; every file directly in each configured
 *                   region folder (the ticket's comment of 2026-10-30). Never My Drive, never DriveApp. Drive's
 *                   createdTime strings reach planTrash_ as Dates (an unparseable one is never due). A folder list not
 *                   complete by the deadline (slow, or a search that fails): retention skipped, planTrash_ not called,
 *                   no would-trash count; on the deadline a TIME_BUDGET line that says retention.
 *   the log         per configured region a line starting `<Region>:` with `would trash N file(s)` and `M folder(s)`;
 *                   after it a `would trash` line per region subfolder affected, naming it, with its counts (everything
 *                   deeper counted under it), and one with `directly` for the files directly in the region folder; the
 *                   number planTrash_ gives as `outside` next to the word `outside`; with more due than the cap of 100,
 *                   RETENTION_CAP and the number left. Never a file name, nor the name of a folder deeper than a region
 *                   folder's direct subfolder, outside the region folders, or in the trash.
 *
 * The expected plans are worked by hand for the fixed layouts (RET_WANT and below) and by an oracle written from the
 * rules for the generated ones; the oracle must agree with the hand-worked numbers.
 */
console.log('\n#182 — RETENTION_DAYS, one Shared Drive, the reads and the would-trash preview (nothing trashed on the Shared Drive)');
{
  const FROM = RUNS.length;   // this section's runs: the last checks look at them
  const PREVIEW = 'previewMoves', REAL = 'moveSettledPhotos', BOTH = [PREVIEW, REAL];
  const R_MAX = 100;          // RETENTION_MAX_FILES (ruling R6)
  const BUDGET = 5 * MIN;     // the run's budget ends under 5 minutes (checked above)
  const TARGET_IDS = Object.fromEntries(REGIONS.map(reg => [reg, propIdOf('TARGET_FOLDER_' + PROP_KEYS[reg])]));
  const retRun = (name, days, opt) => runEntry(name, 'ids', Object.assign(days === undefined ? {} : { retentionDays: days }, opt || {}));
  const said = r => r.threw + '\n' + r.text;
  const valid = t => typeof t === 'number' && isFinite(t);
  const sortObj = o => Object.keys(o).sort().map(k => [k, o[k]]);
  const canon = w => JSON.stringify({ regions: sortObj(w.regions), direct: sortObj(w.direct), tops: sortObj(w.tops),
                                      outside: w.outside, capped: w.capped });

  /**
   * What the preview must say, from the rules alone (R1-R3, R6, R14), on the fake's Shared Drive as the run left it
   * (`model`). want: {regions: {<Region>: [files, folders]}, direct: {<Region>: files directly in its folder},
   * tops: {<region subfolder name>: [region, files, folders under it]}, outside, capped}; tops: every region folder's
   * direct subfolder's name; never: names no log may hold; old: the folders retentionFolders_ names; stats; plan (#185):
   * {files: the planned file ids, earliest due first; folders: the planned folder ids}.
   * `outside` counts the old files (createdTime at or before now - days) whose walk up meets no configured region
   * folder: the reads see no other file there.
   */
  function retentionWant(model, regions, rootId, nowMs, days, maxFiles) {
    const R = days * RDAY, cutoff = nowMs - R;
    const corpus = model.filter(m => m.driveId === rootId && !m.trashed && m.id !== rootId);
    const folders = new Map(corpus.filter(m => m.isFolder).map(m => [m.id, m]));
    const files = corpus.filter(m => !m.isFolder);
    const regionAt = new Map();
    for (const reg of REGIONS) if (own(regions, reg) && typeof regions[reg] === 'string' && regions[reg]) regionAt.set(regions[reg], reg);
    const guarded = id => regionAt.has(id) || id === rootId;
    const climb = start => {   // the root before the regions; {region, chain: the folders met, nearest first} or null
      const chain = [];
      for (let cur = start; ;) {
        if (cur === null || cur === undefined || cur === rootId) return null;
        if (regionAt.has(cur)) return { region: regionAt.get(cur), chain };
        if (!folders.has(cur) || chain.includes(cur)) return null;
        chain.push(cur);
        cur = folders.get(cur).parent;
      }
    };
    const stats = { dueDirect: 0, dueDeep: 0, folders: 0, foldersDeep: 0, keptOld: 0, dueExactly: 0, shortByOneMs: 0, noDate: 0,
                    inTrash: 0, oldFileYoungFolder: 0, capped: 0 };
    const due = [];
    let outside = 0;
    for (const f of files) {
      const w = climb(f.parent);
      if (!w) { if (valid(f.created) && f.created <= cutoff) outside++; continue; }
      if (guarded(f.id)) continue;
      const pc = folders.has(f.parent) ? folders.get(f.parent).created : NaN;
      if (!valid(f.created) || !valid(pc)) { if (valid(f.created) ? f.created <= cutoff : valid(pc) && pc <= cutoff) stats.noDate++; continue; }
      const at = Math.max(f.created, pc);
      if (nowMs - at >= R) { due.push({ f, at, w }); if (at === cutoff) stats.dueExactly++; continue; }
      if (nowMs - at === R - 1) stats.shortByOneMs++;
      if (f.created <= cutoff) stats.oldFileYoungFolder++;
    }
    due.sort((a, b) => a.at - b.at || (a.f.id < b.f.id ? -1 : a.f.id > b.f.id ? 1 : 0));
    const planned = due.slice(0, maxFiles), plannedIds = new Set(planned.map(e => e.f.id));
    const kidsOf = new Map(), filesOf = new Map();
    const push = (map, k, v) => { if (!map.has(k)) map.set(k, []); map.get(k).push(v); };
    for (const d of folders.values()) push(kidsOf, d.parent, d);
    for (const f of files) push(filesOf, f.parent, f);
    const isOld = d => valid(d.created) && nowMs - d.created >= R;
    const memo = new Map();
    const goes = d => {
      if (memo.has(d.id)) return memo.get(d.id);
      memo.set(d.id, false);
      const v = !guarded(d.id) && !!climb(d.parent) && isOld(d) && (filesOf.get(d.id) || []).every(f => plannedIds.has(f.id)) &&
                (kidsOf.get(d.id) || []).every(goes);
      memo.set(d.id, v);
      return v;
    };
    const want = { regions: {}, direct: {}, tops: {}, outside, capped: due.length - planned.length };
    for (const reg of regionAt.values()) want.regions[reg] = [0, 0];
    const bump = (reg, topId, k) => { const nm = folders.get(topId).name; (want.tops[nm] = want.tops[nm] || [reg, 0, 0])[k]++; };
    for (const e of planned) {
      want.regions[e.w.region][0]++;
      if (e.w.chain.length) bump(e.w.region, e.w.chain[e.w.chain.length - 1], 1);
      else { want.direct[e.w.region] = (want.direct[e.w.region] || 0) + 1; stats.dueDirect++; }
      if (e.w.chain.length >= 2) stats.dueDeep++;
    }
    const tops = [], never = [], old = [];
    for (const d of folders.values()) {
      if (guarded(d.id)) continue;
      const w = climb(d.parent);
      if (w && !w.chain.length) tops.push(d.name);
      else if (!REGIONS.includes(d.name)) never.push(d.name);
      if (w && isOld(d)) old.push(d.id);
      if (goes(d)) {
        want.regions[w.region][1]++;
        bump(w.region, w.chain.length ? w.chain[w.chain.length - 1] : d.id, 2);
        stats.folders++;
        if (w.chain.length) stats.foldersDeep++;
      } else if (w && isOld(d)) stats.keptOld++;
    }
    for (const m of model) {
      if (m.driveId !== rootId || m.id === rootId) continue;
      if (!m.isFolder) never.push(m.name);
      else if (m.trashed && !REGIONS.includes(m.name)) { never.push(m.name); stats.inTrash++; }
    }
    stats.capped = want.capped;
    const topNames = [...new Set(tops)];
    const plan = { files: planned.map(e => e.f.id), folders: [...folders.values()].filter(d => !guarded(d.id) && goes(d)).map(d => d.id) };
    return { want, tops: topNames, never: [...new Set(never)].filter(nm => !topNames.includes(nm)), old, stats, plan };
  }
  // the Shared Drive as the run's retention read saw it (#185: the real run's own trashes undone)
  const wantOf = (r, days, regions) => retentionWant(r.modelBefore ? r.modelBefore() : r.model(), regions || TARGET_IDS, DRIVE_ROOT_ID,
                                                     r.t0, days, R_MAX);

  /** The retention lines of a log, read back into the shape of retentionWant's `want` (lines naming nothing known: stray). */
  function retentionView(text, topNames) {
    const v = { regions: {}, direct: {}, tops: {}, stray: [], outside: [], cap: [] };
    let cur = null;
    for (const line of String(text).split('\n')) {
      const before = [...line.matchAll(/(\d+)[^\d\n]{0,40}\boutside\b/g)];   // `1 outside …`, else `outside: 1`
      for (const m of before.length ? before : line.matchAll(/\boutside\b[^\d\n]{0,40}?(\d+)/g)) v.outside.push(Number(m[1]));
      for (const m of line.matchAll(/\bRETENTION_CAP\b\D{0,40}?(\d+)/g)) v.cap.push(Number(m[1]));
      const wt = /\bwould trash (\d+) file/.exec(line), fo = /\bwould trash \d+ file[^\n]*?(\d+) folder/.exec(line);
      const counts = [wt ? Number(wt[1]) : null, fo ? Number(fo[1]) : null];
      const reg = REGIONS.find(x => line.trim().startsWith(x + ':'));
      if (reg !== undefined) {
        cur = wt ? reg : null;
        if (wt) v.regions[reg] = counts;
        continue;
      }
      if (!wt) continue;
      const named = topNames.filter(nm => line.includes(nm));
      if (named.length === 1) v.tops[named[0]] = [cur].concat(counts);
      else if (named.length > 1) v.stray.push(line.trim());
      else if (/\bdirectly\b/.test(line) && cur) v.direct[cur] = counts[0];
      else if (/"[^"]+"/.test(line) || /\bdirectly\b/.test(line)) v.stray.push(line.trim());
    }
    return v;
  }
  function retentionProblems(v, want) {
    const p = [];
    for (const [reg, c] of Object.entries(want.regions)) {
      if (!same(v.regions[reg], c)) p.push(reg + ' ' + (v.regions[reg] ? show(v.regions[reg], c) : 'has no "' + reg + ': ... would trash N file(s) ... M folder(s)" line, want ' + JSON.stringify(c)));
    }
    for (const reg of Object.keys(v.regions)) if (!own(want.regions, reg)) p.push(reg + ': a would-trash line for a region not configured');
    const direct = Object.fromEntries(Object.entries(v.direct).filter(([, n]) => n !== 0));
    if (!same(sortObj(direct), sortObj(want.direct))) p.push('directly in a region folder ' + show(direct, want.direct));
    for (const [nm, c] of Object.entries(want.tops)) {
      if (!same(v.tops[nm], c)) p.push('"' + nm + '" ' + (v.tops[nm] ? show(v.tops[nm], c) : 'on no would-trash line, want ' + JSON.stringify(c)));
    }
    for (const nm of Object.keys(v.tops)) if (!own(want.tops, nm)) p.push('"' + nm + '" named on a would-trash line, but nothing under it is to be trashed');
    for (const l of v.stray) p.push('a would-trash line naming something else: ' + l);
    const allAre = (a, n) => a.length > 0 && a.every(x => x === n);
    if (want.outside ? !allAre(v.outside, want.outside) : v.outside.some(x => x !== 0)) p.push('outside ' + show(v.outside, want.outside));
    if (want.capped ? !allAre(v.cap, want.capped) : v.cap.some(x => x !== 0)) p.push('RETENTION_CAP ' + show(v.cap, want.capped));
    return p;
  }
  const namesProblems = (text, w) => w.never.filter(nm => String(text).includes(nm)).map(nm => 'the log names "' + nm + '"')
    .concat(fileNamesIn(String(text)).map(s => 'a file name in the log (' + s + '...)'));
  /** Problems with run r's preview against `hand` (worked by hand; the oracle must agree) or, without it, the oracle. */
  const previewProblems = (r, days, hand, regions) => {
    const w = wantOf(r, days, regions);
    const p = retentionProblems(retentionView(r.text, w.tops), hand || w.want).concat(namesProblems(r.text, w));
    if (hand && canon(w.want) !== canon(hand)) p.unshift('THE TEST\'S ORACLE DISAGREES with the hand-worked plan: ' + canon(w.want));
    if (r.threw) p.unshift('threw: ' + r.threw);
    return p;
  };
  const lists = r => r.reads.filter(x => x.op === 'list');
  const retentionReads = r => lists(r).filter(x => x.kind !== 'source');   // every Files.list not of a My Drive folder
  const chainsOf = r => {
    const m = new Map();
    for (const x of lists(r)) { if (x.chain === undefined) continue; if (!m.has(x.chain)) m.set(x.chain, []); m.get(x.chain).push(x); }
    return [...m.values()];
  };
  const toEnd = ch => !ch[0].args.pageToken && ch[ch.length - 1].last === true && !ch[ch.length - 1].failed;
  const onDrive = x => x.args.corpora === 'drive' && x.args.driveId === DRIVE_ROOT_ID && x.args.supportsAllDrives === true &&
                       x.args.includeItemsFromAllDrives === true;
  const untrashedOnly = x => x.trashedValues.length > 0 && x.trashedValues.every(t => t === false);
  const sharedWrites = r => r.ops.filter(o => o.op === 'update' && /^T:/.test(r.labelOf(o.fileId) || '')).map(o => 'Files.update on ' + r.labelOf(o.fileId))
    .concat(r.trashes.filter(t => t.label.startsWith('T:')).map(t => 'trashed ' + t.label));
  const IN_TRASH_AT_START = RET_ITEMS.filter(i => i[0].startsWith('T:Asia/Morning Flames 05-20-2026')).map(i => i[0]);
  const retStateChanged = r => RET_ITEMS.map(i => i[0]).filter(l => !r.state(l) || r.state(l).trashed !== IN_TRASH_AT_START.includes(l));
  const myDriveTrashed = r => trashedOf(r).filter(l => !l.startsWith('T:'));
  const movesAsBefore = r => (same(r.moved.slice().sort(), EXPECTED_MOVES) ? [] : ['moved ' + show(r.moved.slice().sort(), EXPECTED_MOVES)])
    .concat(same(r.created.slice().sort(), EXPECTED_CREATED) ? [] : ['made ' + show(r.created.slice().sort(), EXPECTED_CREATED)])
    .concat(same(myDriveTrashed(r), EXPECTED_TRASHED) ? [] : ['trashed in My Drive ' + show(myDriveTrashed(r), EXPECTED_TRASHED)]);
  /** Nothing written by retention: the dry run writes nothing at all; the real run only #144's moves and removals. */
  const noRetentionWrite = r => (r.name === PREVIEW ? (r.ops.length || r.trashes.length || r.calls.some(WRITES) ? ['the dry run wrote: ' +
    r.ops.length + ' op(s), ' + r.trashes.length + ' trash(es)'] : []) : movesAsBefore(r)).concat(sharedWrites(r))
    .concat(retStateChanged(r).map(l => 'changed ' + l)).concat(banned(r));
  /** #185: a Shared Drive write that is not a trash by Files.update (a trash may be retention's; its own checks judge it). */
  const sharedNonTrash = r => r.ops.filter(o => o.op === 'update' && o.kind !== 'trash' && /^T:/.test(r.labelOf(o.fileId) || ''))
    .map(o => 'Files.update ' + JSON.stringify(o.resource) + ' on ' + r.labelOf(o.fileId))
    .concat(r.trashes.filter(t => t.label.startsWith('T:') && t.via !== 'Drive.Files.update').map(t => 'trashed ' + t.label + ' by ' + t.via));
  /**
   * #185: a run whose retention plans in full: the dry run writes nothing at all; the real run #144's moves and removals
   * as without retention and, on the Shared Drive, nothing outside the rules' plan (wantOf): what it trashes of the plan,
   * and that it trashes all of it, is #185's to check below.
   */
  const outsideThePlan = (r, days, regions) => {
    if (r.name === PREVIEW) return noRetentionWrite(r);
    const w = wantOf(r, days, regions);
    const plan = new Set(w.plan.files.concat(w.plan.folders).map(id => r.labelOf(id)));
    return movesAsBefore(r).concat(sharedNonTrash(r))
      .concat(r.trashes.filter(t => t.label.startsWith('T:') && !plan.has(t.label)).map(t => 'trashed ' + t.label + ', not in the plan'))
      .concat(RET_ITEMS.map(i => i[0]).filter(l => !r.state(l) || (r.state(l).trashed !== IN_TRASH_AT_START.includes(l) && !plan.has(l)))
        .map(l => 'changed ' + l))
      .concat(banned(r));
  };
  const budgetLine = r => /TIME_BUDGET[^\n]*\bretention\b|\bretention\b[^\n]*TIME_BUDGET/i.test(r.text);

  // the hand-worked plans of RET_ITEMS (with the fake's FAKE_TARGETS, all hours old, and what the moves make)
  const RET_TOPS_90 = { 'Sunrise Club 07-01-2026': ['Africa', 3, 1],      // RET_A1, A2 and the nested A4; the nested folder
                        'Bright Stars 07-10-2026': ['Africa', 2, 1],      // A5, A6, then the emptied folder itself
                        'Golden Wings 06-01-2026': ['Africa', 0, 1],      // emptied, old
                        'Morning Star Club': ['Africa', 1, 0],            // A7 (A8 young keeps the folder)
                        'Evening Lights 06-01-2026': ['Asia', 3, 1],      // S1-S3, then the folder
                        'Silver Wings 05-01-2026': ['Template', 3, 3] };  // T1-T3 and the three folders
  const RET_WANT = {
    90: { regions: { Africa: [7, 3], Asia: [5, 1], 'Latin America': [0, 0], 'U.S': [0, 0], Template: [3, 3] },
          direct: { Africa: 1, Asia: 2 }, tops: RET_TOPS_90, outside: 1, capped: 0 },
    // A0 (exactly 120 days) and A7 due in Africa, Golden Wings goes; Asia's S3 exactly 120 days: due
    120: { regions: { Africa: [2, 1], Asia: [5, 1], 'Latin America': [0, 0], 'U.S': [0, 0], Template: [3, 3] },
           direct: { Africa: 1, Asia: 2 },
           tops: { 'Golden Wings 06-01-2026': ['Africa', 0, 1], 'Morning Star Club': ['Africa', 1, 0],
                   'Evening Lights 06-01-2026': ['Asia', 3, 1], 'Silver Wings 05-01-2026': ['Template', 3, 3] },
           outside: 1, capped: 0 },
    // nothing is 365 days old but the region folders; the outside photo (250 days) is younger than the cutoff too
    365: { regions: { Africa: [0, 0], Asia: [0, 0], 'Latin America': [0, 0], 'U.S': [0, 0], Template: [0, 0] },
           direct: {}, tops: {}, outside: 0, capped: 0 },
  };

  // ---------------------------------------------------------------- broad: generated Shared Drives against the oracle
  /**
   * Extra trees for the fake Shared Drive (opt.extra, ages in ms): in every region folder 0-2 photos directly in it and
   * 1-4 subfolders `<Club> MM-DD-2026` (now and then in the trash) with photos and nested folders down to depth 3, every
   * time straddling the retention time (exactly on it, or 1 ms short, now and then; now and then unparseable); outside,
   * a root folder with photos and maybe a photo at the root.
   */
  function genRetention(seed, days) {
    const r = prng(18200 + seed * 13);
    const R = days * RDAY;
    const pick = a => a[Math.floor(r() * a.length)];
    const pad = x => String(x).padStart(2, '0');
    const used = new Set(RET_ITEMS.map(i => i[0].split('/')[1]).concat(...Object.values(FAKE_TARGETS).map(t => t.map(x => x[0]))));
    const items = [];
    let k = 0;
    const age = () => { const x = r(); return x < 0.07 ? R : x < 0.14 ? R - 1 : Math.floor(r() * 2.2 * R); };
    const when = () => (r() < 0.05 ? 'not a date' : age());
    const old = () => R + Math.floor(r() * R);
    const club = () => {
      let nm;
      do { nm = pick(WORDS) + ' ' + pick(NOUNS) + ' ' + pad(1 + Math.floor(r() * 12)) + '-' + pad(1 + Math.floor(r() * 28)) + '-2026'; }
      while (used.has(nm));
      used.add(nm);
      return nm;
    };
    const file = parent => items.push([parent + '/RETG-s' + seed + '-f' + (++k) + '.jpg', when()]);
    const tree = (lbl, depth) => {
      for (let i = 0, nf = Math.floor(r() * 4); i < nf; i++) file(lbl);
      for (let i = 0, nk = depth < 3 && r() < 0.55 ? 1 + Math.floor(r() * 2) : 0; i < nk; i++) {
        const inner = lbl + '/Inner-s' + seed + '-n' + (++k) + '-shots';
        items.push([inner, r() < 0.6 ? old() : when()]);
        tree(inner, depth + 1);
      }
    };
    for (const reg of REGIONS) {
      for (let i = 0, nd = Math.floor(r() * 3); i < nd; i++) file('T:' + reg);
      for (let i = 0, nt = 1 + Math.floor(r() * 4); i < nt; i++) {
        const top = 'T:' + reg + '/' + club();
        items.push([top, r() < 0.55 ? old() : when(), r() < 0.1 ? { trashed: true } : undefined]);
        tree(top, 1);
      }
    }
    // outside: never within seconds of the cutoff (the `outside` count is a note in the log, not a boundary to pin)
    const away = () => (r() < 0.5 ? R + 5000 + Math.floor(r() * R) : Math.floor(r() * (R - 5000)));
    const arch = 'T:drive/Archive-s' + seed + '-shots';
    items.push([arch, old()]);
    for (let i = 0, n = 1 + Math.floor(r() * 3); i < n; i++) items.push([arch + '/RETG-s' + seed + '-f' + (++k) + '.jpg', away()]);
    if (r() < 0.6) items.push(['T:drive/RETG-s' + seed + '-f' + (++k) + '.jpg', away()]);
    return items;
  }
  const GEN_DAYS = [['90', 90], [' 120 ', 120], ['91', 91]];
  const covered = {};
  let genRuns = 0, genOk = 0, oracleChecked = false;
  for (let seed = 1; seed <= 6; seed++) {
    const [dayStr, days] = GEN_DAYS[seed % GEN_DAYS.length];
    const name = BOTH[seed % 2];
    const r = retRun(name, dayStr, { extra: genRetention(seed, days) });
    const w = wantOf(r, days);
    const p = previewProblems(r, days).concat(outsideThePlan(r, days));
    genRuns++;
    if (!p.length) genOk++;
    for (const [k2, v] of Object.entries(w.stats)) covered[k2] = (covered[k2] || 0) + v;
    check('RETENTION_DAYS ' + JSON.stringify(dayStr) + ', generated Shared Drive ' + seed + ' (' + name + '): per region the would-trash ' +
          'files and folders, per region subfolder affected its counts (nested ones under it), the files directly in a region ' +
          'folder, outside and RETENTION_CAP are the rules\' answer; no file, nested, outside or trashed folder named; nothing ' +
          'written on the Shared Drive outside the plan (#185)',
          !p.length, p.slice(0, 6).join('; ') || canon(w.want));
  }
  {
    const base = retRun(PREVIEW, '90');   // the oracle on the hand-worked layout
    oracleChecked = canon(wantOf(base, 90).want) === canon(RET_WANT[90]) && canon(wantOf(base, 120).want) === canon(RET_WANT[120]);
  }
  check('…the generated table covers every outcome (' + genOk + ' of ' + genRuns + ' as the rules say): due directly in a region ' +
        'folder and nested two or more deep, emptied folders at and below the region subfolders, an old folder kept for what is ' +
        'in it, due at exactly the cutoff and 1 ms short, an unparseable date, a folder in the trash, an old photo in a young ' +
        'folder; and the oracle agrees with the hand-worked plans',
        genRuns > 0 && genOk === genRuns && oracleChecked &&
        ['dueDirect', 'dueDeep', 'folders', 'foldersDeep', 'keptOld', 'dueExactly', 'shortByOneMs', 'noDate', 'inTrash', 'oldFileYoungFolder']
          .every(k2 => covered[k2] > 0), JSON.stringify(covered) + (oracleChecked ? '' : '; THE ORACLE DISAGREES WITH RET_WANT'));

  // ---------------------------------------------------------------- the hand-worked layout
  const dry = retRun(PREVIEW, '90'), real = retRun(REAL, '90');
  const dryP = previewProblems(dry, 90, RET_WANT[90]).concat(noRetentionWrite(dry));
  check('RETENTION_DAYS 90: the dry run logs would-trash counts for the photo directly in a region folder, the nested one and ' +
        'the subfolder ones, the emptied old subfolder, and outside 1; no write (Africa 7 files and 3 folders, Asia 5 and 1 with ' +
        '2 directly in it, Template 3 and 3, Latin America and U.S 0; not the young, the old-photo-in-a-new-folder, the ' +
        'unparseable or the trashed ones)', !dryP.length, dryP.slice(0, 8).join('; '));
  const realP = previewProblems(real, 90, RET_WANT[90]).concat(outsideThePlan(real, 90));
  check('the real run with RETENTION_DAYS 90 logs the same plan: its moves, folders made and #144\'s removals as without ' +
        'retention, nothing on the Shared Drive trashed or changed outside the plan (#185 trashes the plan: below), nothing ' +
        'banned, no error', !realP.length, realP.slice(0, 8).join('; '));
  const capRun = retRun(REAL, '90', { extra: [['T:Latin America/Golden Roots 05-05-2026', 160 * RDAY]].concat(
    Array.from({ length: 110 }, (_, k) => ['T:Latin America/Golden Roots 05-05-2026/RET_B' + String(k).padStart(3, '0') + '.jpg',
                                           Math.round((141 + 8 * (k + 0.5) / 110) * RDAY)])) });
  // 125 due: the 100 earliest are 6 of RET_ITEMS (S0, T1, T2, A7, T3, S0b) and 94 of the 110 141-149 days old
  const CAP_WANT = { regions: { Africa: [1, 1], Asia: [2, 0], 'Latin America': [94, 0], 'U.S': [0, 0], Template: [3, 3] },
                     direct: { Asia: 2 },
                     tops: { 'Morning Star Club': ['Africa', 1, 0], 'Golden Wings 06-01-2026': ['Africa', 0, 1],
                             'Silver Wings 05-01-2026': ['Template', 3, 3], 'Golden Roots 05-05-2026': ['Latin America', 94, 0] },
                     outside: 1, capped: 25 };
  const capP = previewProblems(capRun, 90, CAP_WANT).concat(outsideThePlan(capRun, 90));
  check('RETENTION_DAYS 90 with 125 files due: the preview counts the 100 with the earliest due moment (across regions; an ' +
        'emptied folder still goes), RETENTION_CAP 25; the real run trashes nothing outside the plan (none of the 25 left out; ' +
        '#185 checks it trashes the 100)', !capP.length, capP.slice(0, 8).join('; '));

  // ---------------------------------------------------------------- RETENTION_DAYS
  const off = BOTH.map(nm => retRun(nm));
  const offProblems = r => {
    const p = [];
    if (!/\bretention off\b/i.test(r.text)) p.push('no "retention off" line');
    const ret = retentionReads(r);
    if (ret.length) p.push(ret.length + ' Files.list not of a My Drive folder: ' + ret.slice(0, 2).map(x => x.args.q).join(' | '));
    const gets = r.reads.filter(x => x.op === 'get' && !/^S:/.test(r.labelOf(x.fileId) || ''));
    const tIds = Object.values(TARGET_IDS);
    if (r.name === PREVIEW ? gets.length : gets.some(x => !tIds.includes(x.fileId)) || tIds.some(id => gets.filter(x => x.fileId === id).length > 1)) {
      p.push('Files.get on the Shared Drive: ' + gets.map(x => r.labelOf(x.fileId)).join(', '));
    }
    const readRet = RET_ITEMS.map(i => i[0]).filter(l => r.listedAll[l] || r.reads.some(x => String(x.args.q || '').includes("'" + r.idOf[l] + "'") ||
                                                                                       x.fileId === r.idOf[l]));
    if (readRet.length) p.push('read ' + readRet.slice(0, 3).join(', '));
    if (r.planTrashCalls.length) p.push('planTrash_ called');
    if (/\bwould trash\b/.test(r.text)) p.push('a would-trash line');
    if (/CONFIG refused/.test(said(r))) p.push('CONFIG refused');
    return p.map(x => r.name + ': ' + x);
  };
  const offP = off.flatMap(offProblems);
  check('RETENTION_DAYS unset: every existing check passes unchanged, no retention call, "retention off" logged (both entry ' +
        'points: no Shared Drive search or listing, no Files.get of it beyond #144\'s target-folder read on apply, none in the ' +
        'dry run, the dated folders never read, planTrash_ not called)', !offP.length, offP.join('; '));
  const refusalProblems = r => {
    const p = [];
    if (!/CONFIG refused/.test(said(r))) p.push('not CONFIG refused');
    else if (!/RETENTION_DAYS/.test(said(r))) p.push('the refusal does not name RETENTION_DAYS');
    if (r.ops.length || r.trashes.length || r.attempted.length || r.created.length) p.push('wrote (' + r.ops.length + ' op(s))');
    if (r.reads.length || r.calls.some(BY_ID)) p.push('opened or read Drive first: ' + [...new Set(r.calls.filter(BY_ID))].join(', ') + ', ' + r.reads.length + ' read(s)');
    if (r.planTrashCalls.length) p.push('planTrash_ called');
    return p;
  };
  const BAD_DAYS = ['89', '0', '90.5', 'ninety', '-90', 'abc', '90 days'];
  const badP = BAD_DAYS.flatMap(v => BOTH.map(nm => [v, nm, refusalProblems(retRun(nm, v))])).filter(x => x[2].length)
    .map(([v, nm, p]) => JSON.stringify(v) + ' ' + nm + ': ' + p.join(', '));
  check('RETENTION_DAYS 89, 0, 90.5, ninety, -90 (and abc, "90 days"): CONFIG refused, no Drive write; refused for the whole ' +
        'run, naming RETENTION_DAYS, before any folder is opened or read (both entry points)', !badP.length, badP.join('; '));
  const trimP = [[' 90 ', 90, PREVIEW], [' 120 ', 120, REAL], ['365', 365, PREVIEW]].flatMap(([v, days, nm]) => {
    const r = retRun(nm, v);
    return previewProblems(r, days, RET_WANT[days]).concat(outsideThePlan(r, days)).map(x => JSON.stringify(v) + ' ' + nm + ': ' + x);
  });
  check('RETENTION_DAYS " 90 " is 90: the same preview as 90; " 120 " (spaces trimmed) and 365 preview with that many days ' +
        '(Africa 2 files and 1 folder at 120, nothing at all at 365, outside 0)', !trimP.length, trimP.slice(0, 8).join('; '));
  const blankP = [['', PREVIEW], ['   ', REAL]].flatMap(([v, nm]) => offProblems(retRun(nm, v)).map(x => JSON.stringify(v) + ' ' + x));
  check('RETENTION_DAYS blank ("" or spaces only) means off: "retention off", no retention call, not refused',
        !blankP.length, blankP.join('; '));

  // ---------------------------------------------------------------- one Shared Drive (R5)
  const driveP = [['a target folder on no Shared Drive (no driveId)', { targetDrive: { Asia: null } }],
                  ['a target folder on a second Shared Drive', { targetDrive: { Template: 'fake-drive-root-2' } }],
                  ['a target folder in the trash', { trashedTarget: 'Latin America' }]].flatMap(([what, o]) => BOTH.map(nm => {
    const r = retRun(nm, '90', o), p = [];
    if (!/CONFIG refused/.test(said(r))) p.push('not CONFIG refused');
    if (r.ops.length || r.trashes.length || r.attempted.length || r.created.length) p.push('wrote (' + r.ops.length + ' op(s), ' + r.attempted.length + ' move(s) tried)');
    if (retentionReads(r).length) p.push('searched the Shared Drive');
    if (r.planTrashCalls.length) p.push('planTrash_ called');
    return p.length ? what + ', ' + nm + ': ' + p.join(', ') : '';
  })).filter(Boolean);
  check('retention on, a target outside a Shared Drive, on two Shared Drives, or trashed: CONFIG refused, no Drive write ' +
        '(before any move; both entry points)', !driveP.length, driveP.join('; '));
  // #181's low finding, ruled 2026-10-30 (the orchestrator): a target folder id equal to the Shared Drive's own id is
  // CONFIG refused (with retention on: the one-Shared-Drive check reads the driveId). The root is named like the region
  // here, so the name check alone would let it through
  const rootP = BOTH.flatMap(nm => {
    const r = retRun(nm, '90', { props: { TARGET_FOLDER_TEMPLATE: DRIVE_ROOT_ID }, rootName: 'Template',
                                 extra: [['T:drive/RET_R1.jpg', 200 * RDAY]] });
    const p = [];
    if (!/CONFIG refused/.test(said(r))) p.push('not CONFIG refused');
    else if (!/TARGET_FOLDER_TEMPLATE/.test(said(r))) p.push('the refusal does not name TARGET_FOLDER_TEMPLATE');
    if (r.ops.length || r.trashes.length || r.attempted.length || r.created.length) p.push('wrote (' + r.ops.length + ' op(s), ' + r.attempted.length + ' move(s) tried)');
    if (retentionReads(r).length) p.push('searched the Shared Drive');
    if (r.planTrashCalls.length || /\bwould trash\b/.test(r.text)) p.push('planned or previewed');
    return p.map(x => nm + ': ' + x);
  });
  check('retention on, TARGET_FOLDER_TEMPLATE set to the Shared Drive\'s own id (its root, named "Template"): CONFIG refused, ' +
        'naming TARGET_FOLDER_TEMPLATE, before any move; no write, no Shared Drive search, nothing planned (both entry points)',
        !rootP.length, rootP.join('; '));
  const NEST_TOPS = Object.assign({}, RET_TOPS_90);
  delete NEST_TOPS['Golden Wings 06-01-2026'];
  const NEST_WANT = { regions: { Africa: [7, 2], Asia: [5, 1], 'Latin America': [0, 0], 'U.S': [0, 0], Template: [3, 3] },
                      direct: { Africa: 1, Asia: 2 }, tops: NEST_TOPS, outside: 1, capped: 0 };
  const nestP = BOTH.flatMap(nm => {
    const r = retRun(nm, '90', { moveFolders: [['T:Template', 'T:Africa/Golden Wings 06-01-2026']] });
    return previewProblems(r, 90, NEST_WANT).concat(outsideThePlan(r, 90)).map(x => nm + ': ' + x);
  });
  check('a configured region folder nested inside another region\'s folder (Template\'s inside Africa\'s emptied old ' +
        '"Golden Wings 06-01-2026"): its tree counts for Template, the folder holding it is kept and not named, Africa ' +
        'would trash 7 files and 2 folders; no write outside the plan', !nestP.length, nestP.slice(0, 6).join('; '));

  // ---------------------------------------------------------------- the reads
  const readP = [];
  {
    const r = dry, chains = chainsOf(r), cutoff = r.t0 - 90 * RDAY;
    const full = (what, pick, multi) => {
      const got = chains.filter(ch => pick(ch[0]));
      const good = got.filter(ch => toEnd(ch) && ch.every(onDrive) && untrashedOnly(ch[0]) && (!multi || ch.length >= 2));
      if (!good.length) {
        readP.push(what + ': ' + (got.length ? got.map(ch => ch.length + ' page(s)' + (toEnd(ch) ? '' : ', not to the end') +
          (ch.every(onDrive) ? '' : ', not all on the drive\'s corpus with both flags') + (untrashedOnly(ch[0]) ? '' : ', `trashed = false` not stated')).join(' | ') : 'never asked'));
      }
    };
    const FOLDER_IS = x => x.mimes.some(m => m.op === '=' && m.value === DRIVE_FOLDER_MIME);
    const FILE_IS = x => x.mimes.some(m => m.op === '!=' && m.value === DRIVE_FOLDER_MIME);
    full('every folder on the drive (mimeType = folder, no parents)', x => x.kind === 'folders' && FOLDER_IS(x), true);
    full('the files created at or before now - 90 days', x => x.kind === 'due' && FILE_IS(x) &&
         x.created.some(c => (c.op === '<=' || c.op === '<') && Math.abs(c.at - cutoff) <= 1000), true);
    const w = wantOf(r, 90);
    for (const id of w.old) full('the listing of the old folder ' + r.labelOf(id), x => x.kind === 'listing' && x.parents.includes(id), false);
    const sunrise = r.idOf['T:Africa/Sunrise Club 07-01-2026'];
    if (!chains.some(ch => ch[0].kind === 'listing' && ch[0].parents.includes(sunrise) && ch.length >= 2 && toEnd(ch))) {
      readP.push('the three-photo old folder\'s listing is not followed to its second page');
    }
    if (w.old.length !== 10) readP.push('(the test expected 10 old folders, its oracle found ' + w.old.length + ')');
  }
  check('the drive-wide folder search, the due-file search and the old folders\' listings are followed through nextPageToken ' +
        '(each on corpora \'drive\' with the driveId, supportsAllDrives and includeItemsFromAllDrives, `trashed = false` stated; ' +
        'the cutoff now - 90 days, to the second; each of the 10 old folders below a region folder listed in full)',
        !readP.length, readP.slice(0, 8).join('; '));
  const regionP = [];
  for (const r of [dry, real]) {
    for (const [reg, id] of Object.entries(TARGET_IDS)) {
      const ch = chainsOf(r).filter(c => c[0].kind === 'listing' && c[0].parents.includes(id) && toEnd(c) && c.every(onDrive) && untrashedOnly(c[0]));
      if (!ch.length) regionP.push(r.name + ': ' + reg + '\'s region folder');
    }
    const af = chainsOf(r).filter(c => c[0].kind === 'listing' && c[0].parents.includes(TARGET_IDS.Africa));
    if (!af.some(c => c.length >= 2 && toEnd(c))) regionP.push(r.name + ': Africa\'s three photos not paged to the end');
  }
  check('each configured region folder\'s own files are listed in full too (retentionFolders_ never names a region folder; the ' +
        'ticket\'s comment of 2026-10-30), on the drive\'s corpus, `trashed = false` stated, both entry points',
        !regionP.length, regionP.length ? 'not listed in full: ' + regionP.join(', ') : '');

  // ---------------------------------------------------------------- the time budget and a failed search
  const slow = BOTH.map(nm => retRun(nm, '90', { searchAdvanceMin: 2 }));
  const slowP = slow.flatMap(r => {
    const p = [];
    if (!lists(r).some(x => x.kind === 'folders')) p.push('no folder search');
    const late = retentionReads(r).filter(x => x.t - r.t0 >= BUDGET);
    if (late.length) p.push(late.length + ' Shared Drive read(s) after the budget');
    if (!budgetLine(r)) p.push('no TIME_BUDGET line for retention');
    if (r.planTrashCalls.length) p.push('planTrash_ called on a partial folder list');
    if (/\bwould trash\b/.test(r.text)) p.push('would-trash counts logged from a partial folder list');
    return p.concat(noRetentionWrite(r)).map(x => r.name + ': ' + x);
  });
  check('a folder list cut by the run budget: retention skipped, TIME_BUDGET logged, planTrash_ not called (2 minutes a page: ' +
        'no read past the budget, no would-trash count; the real run\'s moves and removals all done first, as without retention)',
        !slowP.length, slowP.slice(0, 6).join('; '));
  const starved = retRun(REAL, '90', { moveAdvanceMin: 7 });
  const starvedP = [];
  if (starved.attempted.length !== 1) starvedP.push(starved.attempted.length + ' file move(s) tried, want 1');
  if (retentionReads(starved).some(x => x.t - starved.t0 >= BUDGET)) starvedP.push('a Shared Drive search after the budget');
  if (!budgetLine(starved)) starvedP.push('no TIME_BUDGET line for retention');
  if (starved.planTrashCalls.length || /\bwould trash\b/.test(starved.text)) starvedP.push('planned or logged would-trash counts');
  check('…and the moves first: when they use up the budget (7 minutes a file), retention reads nothing after it and is skipped ' +
        '(TIME_BUDGET), planTrash_ not called', !starvedP.length, starvedP.join('; ') + ' log: ' + starved.text.slice(-300));
  // ruled 2026-10-30 (the orchestrator): a retention search or listing that fails logs `RETENTION_FAILED <what>` (counts
  // and folder names only), the moves still happen, no would-trash line that run, and the run ends with an error after
  // the moves
  /** The folders whose listing (`'<id>' in parents`, `trashed = false`, no createdTime clause) the run read to its last page. */
  const fullyListed = r => {
    const ids = new Set();
    for (const ch of chainsOf(r)) {
      const x = ch[0];
      if (x.kind !== 'listing' || !toEnd(ch) || x.created.length || !untrashedOnly(x) ||
          x.mimes.some(m => !(m.op === '!=' && m.value === DRIVE_FOLDER_MIME))) continue;
      for (const id of x.parents) ids.add(id);
    }
    return ids;
  };
  const failedRun = (r, kind, label) => {
    const p = [];
    if (!lists(r).some(x => x.kind === kind && x.page === 2 && x.failed && (!label || x.parents.includes(r.idOf[label])))) {
      p.push('the failing page was never asked for');
    }
    if (!/\bRETENTION_FAILED\b/.test(r.text)) p.push('no RETENTION_FAILED line');
    if (!r.threw) p.push('the run does not end with an error');
    if (/\bwould trash\b/.test(r.text)) p.push('would-trash lines logged in a run whose retention read failed');
    p.push(...namesProblems(said(r), wantOf(r, 90)));
    return p.concat(noRetentionWrite(r)).map(x => r.name + ': ' + x);
  };
  const searchFail = BOTH.map(nm => [retRun(nm, '90', { failSearch: { kind: 'folders', page: 2 } }), 'folders'])
    .concat([[retRun(REAL, '90', { failSearch: { kind: 'due', page: 2 } }), 'due']]);
  const searchFailP = searchFail.flatMap(([r, kind]) => failedRun(r, kind)
    .concat(kind === 'folders' && r.planTrashCalls.length ? [r.name + ': planTrash_ called on a partial folder list'] : []));
  check('a retention search that fails (the folder search on its second page, both entry points; the due-file search, the ' +
        'real run): RETENTION_FAILED logged (no file or nested folder name), no would-trash line, the moves as without ' +
        'retention, the run ends with an error; planTrash_ never called on a partial folder list',
        !searchFailP.length, searchFailP.slice(0, 6).join('; '));
  const SUNRISE = 'T:Africa/Sunrise Club 07-01-2026';   // its second page holds its young photo (RET_A3)
  const listFailP = BOTH.flatMap(nm => {
    const r = retRun(nm, '90', { failSearch: { kind: 'listing', page: 2, of: SUNRISE } });
    const id = r.idOf[SUNRISE];
    return failedRun(r, 'listing', SUNRISE).concat(r.planTrashCalls.flatMap(c =>
      (c.folders || []).filter(d => d.id === id && d.complete === true).map(() => nm + ': ' + SUNRISE + ' handed complete: true')
        .concat((c.planned || []).filter(x => x === id).map(() => nm + ': ' + SUNRISE + ' planned for the trash'))));
  });
  check('an old folder\'s listing that fails on its second page (Sunrise Club 07-01-2026, whose second page holds its young ' +
        'photo): RETENTION_FAILED logged, no would-trash line, the moves as without retention, the run ends with an error; ' +
        'if planned at all, that folder is never handed complete: true nor planned (both entry points)',
        !listFailP.length, listFailP.slice(0, 6).join('; '));
  const cutP = BOTH.flatMap(nm => {
    const r = retRun(nm, '90', { listAdvanceMin: 1.5 }), p = [], full = fullyListed(r), w = wantOf(r, 90);
    if (!lists(r).some(x => x.kind === 'listing')) p.push('no Shared Drive folder listed');
    else if (w.old.every(id => full.has(id))) p.push('(every old folder was listed in full: the budget did not cut the listings)');
    const late = retentionReads(r).filter(x => x.t - r.t0 >= BUDGET);
    if (late.length) p.push(late.length + ' Shared Drive read(s) after the budget');
    if (!budgetLine(r)) p.push('no TIME_BUDGET line for retention');
    for (const c of r.planTrashCalls) {
      const bad = (c.folders || []).filter(d => d.complete === true && !full.has(d.id)).map(d => r.labelOf(d.id));
      if (bad.length) p.push('complete: true for a folder not listed to its last page: ' + bad.join(', '));
      const wrong = (c.planned || []).filter(x => !full.has(x)).map(x => r.labelOf(x));
      if (wrong.length) p.push('planned a folder not listed to its last page: ' + wrong.join(', '));
    }
    return p.concat(noRetentionWrite(r)).map(x => nm + ': ' + x);
  });
  check('the budget running out among the old folders\' listings (1.5 minutes a listing page): TIME_BUDGET for retention, no ' +
        'read past the budget, and no folder not listed to its last page is handed complete: true or planned (planTrash_ not ' +
        'called, or called with those incomplete); the moves as without retention, no write (both entry points)',
        !cutP.length, cutP.slice(0, 6).join('; '));

  // ---------------------------------------------------------------- what the log may name, and My Drive
  const namesP = [dry, real].flatMap(r => {
    const w = wantOf(r, 90), v = retentionView(r.text, w.tops);
    const missing = Object.keys(RET_TOPS_90).filter(nm => !v.tops[nm]);
    const p = missing.length ? ['the affected region subfolders not named: ' + missing.join(', ')] : [];
    const wrong = Object.keys(v.tops).filter(nm => !own(RET_TOPS_90, nm)).map(nm => 'an unaffected region subfolder named: ' + nm);
    return p.concat(wrong, v.stray.map(l => 'a line naming something else: ' + l), namesProblems(r.text, w)).map(x => r.name + ': ' + x);
  });
  check('retention logs name region subfolders only: no file name, never the nested folder\'s name ("Nested Zebra Album", ' +
        '"Nested Kiwi Shots", "Nested Mango Shots"), nor the outside folder\'s or a folder in the trash; the six region ' +
        'subfolders affected are named, the unaffected ones are not', !namesP.length, namesP.slice(0, 8).join('; '));
  const driveAppCalls = r => r.calls.filter(c => /^(DriveApp|Folder|File|Iterator)\./.test(c)).sort();
  const myDriveReads = r => r.reads.filter(x => (x.op === 'list' && x.kind === 'source') || (x.op === 'get' && /^S:/.test(r.labelOf(x.fileId) || '')))
    .map(x => x.op + ' ' + (x.op === 'list' ? x.args.q + (x.args.pageToken ? ' (a later page)' : '') : x.fileId + ' ' + x.args.fields)).sort();
  const sOnly = o => sortObj(Object.fromEntries(Object.entries(o).filter(([l]) => l.startsWith('S:'))));
  const relimit = l => (EXPECTED_TRASHED.includes(l) || TRASHED_SUBS.includes(l) ? 2 : 1);
  const myP = BOTH.flatMap((nm, i) => {
    const on = [dry, real][i], o = off[i], p = [];
    if (!same(driveAppCalls(on), driveAppCalls(o))) p.push('DriveApp calls differ from the run without retention');
    if (!same(myDriveReads(on), myDriveReads(o))) p.push('My Drive reads differ from the run without retention');
    if (!same(sOnly(on.listedAll), sOnly(o.listedAll)) || !same(sortObj(on.readCount), sortObj(o.readCount))) p.push('My Drive listings differ');
    const over = Object.entries(on.readCount).filter(([l, c]) => c > relimit(l)).map(([l, c]) => l + ' x' + c);
    if (over.length || Object.keys(on.readCount).length !== SOURCE_SUBS) p.push('source subfolders listed: ' + (over.join(', ') || Object.keys(on.readCount).length + ' of ' + SOURCE_SUBS));
    const ret = retentionReads(on);
    if (!ret.length) p.push('no Shared Drive search at all');
    const offCorpus = ret.filter(x => !onDrive(x));
    if (offCorpus.length) p.push(offCorpus.length + ' search(es) not on the drive\'s corpus: ' + JSON.stringify(offCorpus[0].args).slice(0, 160));
    return p.map(x => nm + ': ' + x);
  });
  check('retention never reads My Drive: with RETENTION_DAYS 90 the DriveApp calls, the My Drive listings and reads are exactly ' +
        'those of the run without it (each source subfolder listed once, as #144 says), and every retention search is on the ' +
        'Shared Drive\'s corpus (corpora \'drive\', its driveId)', !myP.length, myP.join('; '));

  // ================================================================ #185: the trash on apply
  /**
   * #185 (epic #179, rulings R1, R3, R6, R8, R9, R14; docs/plans/2026-10-30-photo-retention.md): with RETENTION_DAYS set,
   * the real run (moveSettledPhotos) trashes what planTrash_ planned, after the moves and the preview; the dry run still
   * writes nothing. The contract, as these tests read it:
   *
   *   what       every file of the plan, then its folders, each only after everything of the plan in it (children before
   *              parents), each by moveToTrash_ (#144's one trash) handed PROTECTED_IDS: Drive.Files.update({trashed:
   *              true}, id, null, {supportsAllDrives: true}). Nothing else on the Shared Drive is written.
   *   never      a configured folder (source or target; a region folder nested inside another region's too), the
   *              drive's root, anything outside the region folders, anything in My Drive but #144's removals, a file
   *              before its due moment, a folder with an untrashed child: TRASH_RULES' retention entry, as the fake sees
   *              the item at the moment of the call. With planTrash_ replaced by one that returns a configured id or the
   *              drive's id: no Files.update carries it, TRASH_REFUSED is logged, the run ends with an error.
   *   re-checks  just before the trash, against what the read saw: a file moved, trashed or no longer due (its own or its
   *              folder's createdTime) is skipped; so is everything under a folder whose parent changed (into another
   *              region's folder, or out of the region folders) at any level of the walk up; a folder with an untrashed
   *              child at that moment (one that arrived after the read, or one its listing missed) is kept, and so are
   *              the folders above it. A skip is no error.
   *   cap        at most 100 files a run, the earliest due first (RETENTION_CAP); the next run trashes the rest.
   *   failures   a trash Drive refuses: `TRASH_FAILED <Region> "<region subfolder>"` (`TRASH_FAILED <Region>` for a photo
   *              directly in a region folder); the rest goes on, the run ends with an error. A MOVE_FAILED does not skip
   *              retention, and the error names both.
   *   budget     no trash once the run's time budget is spent (a TIME_BUDGET line saying trash or retention); the next run
   *              goes on with the rest.
   *   the log    per configured region with something trashed a line starting `<Region>:` with `trashed N file(s) and M
   *              folder(s)`; per region subfolder with something trashed under it (itself included) `trashed N file(s)
   *              and M folder(s) under "<name>"`; the numbers what was trashed. `not trashed "<region subfolder>"` where
   *              a re-check kept something. Never a file's name, nor a deeper folder's.
   *
   * The expected trashes are worked by hand for RET_ITEMS (HAND below) and by #182's oracle (retentionWant's plan) for
   * the generated drives; the oracle must agree with the hand-worked lists.
   */
  {
    const R185 = [];   // this part's runs
    const run185 = (name, days, opt) => { const r = retRun(name, days, opt); R185.push(r); return r; };
    const AF = 'T:Africa/', AS = 'T:Asia/', TP = 'T:Template/';
    const SUN = AF + 'Sunrise Club 07-01-2026', ZEBRA = SUN + '/Nested Zebra Album', BRIGHT = AF + 'Bright Stars 07-10-2026';
    const GOLDEN = AF + 'Golden Wings 06-01-2026', MSC = AF + 'Morning Star Club', EVE = AS + 'Evening Lights 06-01-2026';
    const SW = TP + 'Silver Wings 05-01-2026', KIWI = SW + '/Nested Kiwi Shots', MANGO = KIWI + '/Nested Mango Shots';
    const F = { A0: AF + 'RET_A0.jpg', A1: SUN + '/RET_A1.jpg', A2: SUN + '/RET_A2.jpg', A4: ZEBRA + '/RET_A4.jpg',
                A5: BRIGHT + '/RET_A5.jpg', A6: BRIGHT + '/RET_A6.jpg', A7: MSC + '/RET_A7.jpg', S0: AS + 'RET_S0.jpg',
                S0b: AS + 'RET_S0b.jpg', S1: EVE + '/RET_S1.jpg', S2: EVE + '/RET_S2.jpg', S3: EVE + '/RET_S3.jpg',
                T1: SW + '/RET_T1.jpg', T2: KIWI + '/RET_T2.jpg', T3: MANGO + '/RET_T3.jpg' };
    // RETENTION_DAYS 90 on RET_ITEMS, by hand (RET_WANT[90]): 15 photos, then 7 folders
    const HAND = Object.values(F).concat([ZEBRA, BRIGHT, GOLDEN, EVE, MANGO, KIWI, SW]).sort();
    const TOPS_90 = Object.fromEntries(Object.entries(RET_TOPS_90).map(([nm, c]) => [nm, c.slice(1)]));
    const NESTED = ['Nested Zebra Album', 'Nested Kiwi Shots', 'Nested Mango Shots', 'Nested Plum Shots', 'Kept Photos Archive'];
    const minus = (a, b) => a.filter(x => !b.includes(x)).sort();
    const diff = (got, want) => 'missing ' + JSON.stringify(minus(want, got).slice(0, 6)) + ', extra ' + JSON.stringify(minus(got, want).slice(0, 6));
    const retTrashes = r => r.trashes.filter(t => t.label.startsWith('T:'));
    const trashedT = r => retTrashes(r).map(t => t.label).sort();
    const planOf = (r, days, regions) => { const w = wantOf(r, days, regions); return w.plan.files.concat(w.plan.folders).map(id => r.labelOf(id)).sort(); };
    /** Was a trash ({trashed: true}) ever sent for the item `lbl`? */
    const trashSent = (r, lbl) => r.idOf[lbl] !== undefined && r.ops.some(o => o.op === 'update' && o.fileId === r.idOf[lbl] &&
                                                                         (o.kind === 'trash' || !!(o.resource && o.resource.trashed === true)));
    /** Files first, then folders; a folder only after everything of the plan in it (labels are paths as created). */
    const orderProblems = r => {
      const ts = retTrashes(r), p = [];
      const firstFolder = ts.findIndex(t => t.isFolder);
      const lateFile = firstFolder < 0 ? null : ts.slice(firstFolder).find(t => !t.isFolder);
      if (lateFile) p.push('a photo trashed after a folder (' + lateFile.label + ' after ' + ts[firstFolder].label + ')');
      ts.forEach((t, i) => {
        if (!t.isFolder) return;
        const inIt = ts.slice(i + 1).find(u => u.label.startsWith(t.label + '/'));
        if (inIt) p.push(t.label + ' trashed before ' + inIt.label + ', which is in it');
      });
      return p;
    };
    /** Each Shared Drive trash: inside moveToTrash_ handed PROTECTED_IDS, by Files.update({trashed: true}, id, null, {supportsAllDrives: true}). */
    const callProblems = r => {
      const p = [];
      for (const t of retTrashes(r)) {
        const op = r.ops.find(o => o.op === 'update' && o.trash === t);
        if (!t.viaHelper) p.push(t.label + ': trashed outside ' + TRASH_HELPER);
        const h = r.helperCalls.filter(x => x.id === t.id);
        if (!h.length || h.some(x => !Array.isArray(x.protectedIds) || PROTECTED_IDS.some(id => !x.protectedIds.includes(id)))) {
          p.push(t.label + ': ' + TRASH_HELPER + ' not handed every configured id and the root');
        }
        if (!op) { p.push(t.label + ': trashed by no Files.update'); continue; }
        if (!same(Object.keys(op.resource), ['trashed']) || op.resource.trashed !== true) p.push(t.label + ': resource ' + JSON.stringify(op.resource));
        if (op.media !== null && op.media !== undefined) p.push(t.label + ': media ' + typeof op.media);
        if (op.args.supportsAllDrives !== true || 'addParents' in op.args || 'removeParents' in op.args) p.push(t.label + ': args ' + JSON.stringify(op.args));
      }
      return p;
    };
    const TRASHED_RX = /\btrashed (\d+) files?(?:\(s\))? and (\d+) folders?(?:\(s\))?/;
    /** The `trashed N file(s) and M folder(s)` lines of a log: {regions, tops (by the region subfolder named), stray}. */
    function trashedView(text, topNames) {
      const v = { regions: {}, tops: {}, stray: [] };
      for (const line of String(text).split('\n')) {
        if (/\bwould trash\b/.test(line)) continue;
        const m = TRASHED_RX.exec(line);
        if (!m) continue;
        const counts = [Number(m[1]), Number(m[2])];
        const named = topNames.filter(nm => line.includes('"' + nm + '"'));
        const reg = REGIONS.find(x => line.trim().startsWith(x + ':'));
        if (named.length === 1) v.tops[named[0]] = counts;
        else if (!named.length && !/"/.test(line) && reg !== undefined) v.regions[reg] = counts;
        else if (!named.length && !/"/.test(line) && /\bdirectly\b/.test(line)) continue;
        else v.stray.push(line.trim());
      }
      return v;
    }
    /** The log's trashed counts against {<Region>: [files, folders]} and {<region subfolder>: [files, folders]}; its names. */
    function logProblems(r, days, wantRegions, wantTops) {
      const w = wantOf(r, days), v = trashedView(r.text, w.tops), p = [];
      for (const reg of REGIONS) {
        const want = wantRegions[reg] || [0, 0], got = v.regions[reg];
        if (got ? !same(got, want) : want[0] + want[1] > 0) {
          p.push(reg + ': ' + (got ? 'trashed ' + show(got, want) : 'no `' + reg + ': … trashed N file(s) and M folder(s)` line, want ' + JSON.stringify(want)));
        }
      }
      for (const nm of new Set(Object.keys(wantTops).concat(Object.keys(v.tops)))) {
        const want = wantTops[nm] || [0, 0], got = v.tops[nm];
        if (got ? !same(got, want) : want[0] + want[1] > 0) {
          p.push('"' + nm + '": ' + (got ? 'trashed ' + show(got, want) : 'on no `trashed N file(s) and M folder(s) under "…"` line, want ' + JSON.stringify(want)));
        }
      }
      return p.concat(v.stray.map(l => 'a trashed line naming something else: ' + l), namesProblems(said(r), w));
    }

    // ---------------------------------------------------------------- the fake's trash
    {
      const env = fakeEnv('ids', { retentionDays: '90' });
      const D = env.globals.Drive.Files, all = { supportsAllDrives: true, includeItemsFromAllDrives: true };
      const id = l => env.idOf[l];
      D.update({ trashed: true }, id(BRIGHT), null, { supportsAllDrives: true });
      const photo = D.get(id(F.A5), { fields: 'trashed, explicitlyTrashed', supportsAllDrives: true });
      const folder = D.get(id(BRIGHT), { fields: 'trashed', supportsAllDrives: true });
      const live = D.list(Object.assign({ q: "'" + id(BRIGHT) + "' in parents and trashed = false", fields: 'files(id)' }, all));
      const binned = D.list(Object.assign({ q: "'" + id(BRIGHT) + "' in parents and trashed = true", fields: 'nextPageToken, files(id)' }, all));
      const byName = D.list(Object.assign({ q: "'" + id('T:Africa') + "' in parents and name = 'Bright Stars 07-10-2026' and trashed = false",
                                            fields: 'files(id)' }, all));
      const app = env.globals.DriveApp.getFolderById(id(BRIGHT)).isTrashed();
      check('the fake (#185): a Files.update({trashed: true}) of a Shared Drive folder is a trash every later read sees: it and ' +
            'its photos read trashed (the photos not explicitly), a `trashed = false` listing of it, or of its parent by its ' +
            'name, finds nothing, a `trashed = true` one finds its two photos, DriveApp says isTrashed()',
            photo.trashed === true && photo.explicitlyTrashed === false && folder.trashed === true && !(live.files || []).length &&
            !(byName.files || []).length && (binned.files || []).length === 2 && !binned.nextPageToken && app === true,
            JSON.stringify({ photo, folder, live, binned, byName, app }));
    }

    // ---------------------------------------------------------------- what is trashed: the hand-worked layout, then generated drives
    const handP = [];
    {
      const oracle = planOf(real, 90);
      if (!same(oracle, HAND)) handP.push('THE TEST\'S ORACLE DISAGREES with the hand-worked plan: ' + diff(oracle, HAND));
      if (real.threw) handP.push('threw: ' + real.threw);
      if (!same(trashedT(real), HAND)) handP.push('trashed on the Shared Drive: ' + diff(trashedT(real), HAND));
      handP.push(...orderProblems(real), ...callProblems(real), ...sharedNonTrash(real), ...banned(real), ...movesAsBefore(real));
      const notInTrash = HAND.filter(l => !real.state(l).trashed);
      if (notInTrash.length) handP.push('not in the trash after the run: ' + notInTrash.slice(0, 6).join(', '));
      const changed = RET_ITEMS.map(i => i[0]).filter(l => !HAND.includes(l) && real.state(l).trashed !== IN_TRASH_AT_START.includes(l));
      if (changed.length) handP.push('changed outside the plan: ' + changed.join(', '));
      if (dry.trashes.length || dry.ops.length) handP.push('the dry run wrote: ' + dry.ops.length + ' op(s), ' + dry.trashes.length + ' trash(es)');
    }
    check('RETENTION_DAYS 90: the real run trashes exactly the plan: the photo directly in a region folder, the nested and ' +
          'subfolder ones, then the emptied folders children first, through Files.update({trashed: true}) with supportsAllDrives ' +
          '(Africa 7 photos and 3 folders, Asia 5 and 1, Template 3 and 3: every photo, then the folders, each after everything ' +
          'of the plan in it; each by one ' + TRASH_HELPER + ' call handed every configured id and the root, resource ' +
          '{trashed: true} alone, no media, no parent change; nothing else on the Shared Drive changed; #144\'s moves and ' +
          'removals as without retention; no error; the dry run on the same drive writes nothing)',
          !handP.length, handP.slice(0, 8).join('; '));
    const GEN185 = [['90', 90], [' 120 ', 120], ['91', 91]];
    const genP = [], cover = {};
    let genN = 0, genTrashed = 0;
    for (let seed = 7; seed <= 14; seed++) {
      const [dayStr, days] = GEN185[seed % GEN185.length];
      const extra = genRetention(seed, days);
      const rr = run185(REAL, dayStr, { extra }), rd = run185(PREVIEW, dayStr, { extra });
      const w = wantOf(rr, days);
      for (const [k2, v] of Object.entries(w.stats)) cover[k2] = (cover[k2] || 0) + v;
      const want = w.plan.files.concat(w.plan.folders).map(id => rr.labelOf(id)).sort();
      const tops = Object.fromEntries(Object.entries(w.want.tops).map(([nm, c]) => [nm, c.slice(1)]));
      genTrashed += retTrashes(rr).length;
      const p = (rr.threw ? ['threw: ' + rr.threw] : [])
        .concat(same(trashedT(rr), want) ? [] : ['trashed ' + diff(trashedT(rr), want)])
        .concat(orderProblems(rr), callProblems(rr), sharedNonTrash(rr), banned(rr), movesAsBefore(rr),
                logProblems(rr, days, w.want.regions, tops))
        .concat(rd.trashes.length || rd.ops.length ? ['the dry run wrote: ' + rd.ops.length + ' op(s), ' + rd.trashes.length + ' trash(es)'] : []);
      genN++;
      if (p.length) genP.push('seed ' + seed + ' (' + JSON.stringify(dayStr) + '): ' + p.slice(0, 4).join('; '));
    }
    const uncovered = ['dueDirect', 'dueDeep', 'folders', 'foldersDeep', 'keptOld', 'dueExactly', 'shortByOneMs', 'noDate', 'inTrash',
                       'oldFileYoungFolder'].filter(k2 => !(cover[k2] > 0));
    check('…and on ' + genN + ' generated Shared Drives (RETENTION_DAYS "90", " 120 ", "91"; the real and the dry run on each; ' +
          genTrashed + ' item(s) trashed): the real run trashes exactly what the rules plan (an oracle of their own), photos ' +
          'first, folders children first, each through ' + TRASH_HELPER + ' with supportsAllDrives, its `trashed` lines counting ' +
          'them per region and region subfolder, no file or nested folder named; the dry run writes nothing; the drives hold ' +
          'due photos directly in a region folder and two or more deep, emptied folders at and below the region subfolders, an ' +
          'old folder kept for what is in it, due at exactly the cutoff and 1 ms short, an unparseable date, a folder in the ' +
          'trash, an old photo in a young folder',
          genN > 0 && !genP.length && !uncovered.length,
          genP.slice(0, 4).join(' | ') + (uncovered.length ? ' NOT COVERED: ' + uncovered.join(', ') : ''));

    // ---------------------------------------------------------------- never trashed
    const S7 = AS + 'RET_S7.jpg', S8 = AS + 'RET_S8.jpg', YOUNG_DIR = AS + 'Rising Voices 08-02-2026', EXACT_DIR = AS + 'Golden Lights 08-02-2026';
    const edge = run185(REAL, '90', { extra: [[S7, 90 * RDAY - 1], [S8, 90 * RDAY], [YOUNG_DIR, 90 * RDAY - 1], [EXACT_DIR, 90 * RDAY]] });
    const nest = run185(REAL, '90', { moveFolders: [['T:Template', GOLDEN]] });
    const CONFIGURED = REGIONS.flatMap(reg => ['T:' + reg, 'S:' + reg]).concat('T:drive');
    const OUTSIDE = ['T:drive/Kept Photos Archive', 'T:drive/Kept Photos Archive/RET_K1.jpg'];
    const NOT_DUE = [AF + 'RET_A0y.jpg', AF + 'RET_A0z.jpg', SUN + '/RET_A3.jpg', MSC + '/RET_A8.jpg', AF + 'Silver Roots 10-25-2026/RET_A9.jpg',
                     AF + 'Evening Roots 06-15-2026/RET_A10.jpg', AF + 'Golden Voices 06-20-2026/RET_A11.jpg', AF + 'Rising Lights 10-20-2026',
                     S7, YOUNG_DIR];
    const WITH_CHILD = [SUN, MSC, AF + 'Silver Roots 10-25-2026', AF + 'Evening Roots 06-15-2026', AF + 'Golden Voices 06-20-2026'];
    const neverP = [];
    for (const [tag, r, wantSet, more] of [['the 90-day edges', edge, HAND.concat(S8, EXACT_DIR).sort(), []],
                                           ['Template\'s region folder inside Africa\'s "Golden Wings 06-01-2026"', nest, minus(HAND, [GOLDEN]),
                                            ['T:Template', GOLDEN]]]) {
      const oracle = planOf(r, 90);
      if (!same(oracle, wantSet)) neverP.push(tag + ': THE TEST\'S ORACLE DISAGREES: ' + diff(oracle, wantSet));
      if (r.threw) neverP.push(tag + ': threw ' + r.threw);
      if (!same(trashedT(r), wantSet)) neverP.push(tag + ': trashed on the Shared Drive: ' + diff(trashedT(r), wantSet));
      for (const [why, labels] of [['a configured folder or the root', CONFIGURED], ['outside the region folders', OUTSIDE],
                                   ['not yet due', NOT_DUE], ['a folder with a child', WITH_CHILD],
                                   ['already in the trash', IN_TRASH_AT_START], ['the nested region folder or the folder holding it', more]]) {
        const hit = labels.filter(l => r.state(l) && (trashSent(r, l) || r.state(l).trashed !== IN_TRASH_AT_START.includes(l)));
        if (hit.length) neverP.push(tag + ': ' + why + ', trashed or sent a trash: ' + hit.join(', '));
      }
      if (!same(myDriveTrashed(r), EXPECTED_TRASHED)) neverP.push(tag + ': My Drive trashed ' + show(myDriveTrashed(r), EXPECTED_TRASHED));
      neverP.push(...banned(r).map(b => tag + ': ' + b));
    }
    check('never trashed: configured folders, a nested region folder, the root, outside the region folders, My Drive beyond ' +
          '#144, items not yet due, folders with a child (nor what was in the trash already: no trash ever sent for any of them; ' +
          'a photo and a folder 1 ms short of 90 days stay, the photo and the emptied folder at exactly 90 days go; with ' +
          'Template\'s region folder inside Africa\'s "Golden Wings 06-01-2026" that folder stays too; in My Drive only #144\'s ' +
          'removals; nothing banned)', !neverP.length, neverP.slice(0, 8).join('; '));

    // ---------------------------------------------------------------- a wrong planner
    const sid = reg => propIdOf('SOURCE_FOLDER_' + PROP_KEYS[reg]);
    const longAgo = (D, now) => new D(now - 200 * RDAY);
    const SANDBOX = [
      ['the Africa region folder and the drive as due photos', {}, [TARGET_IDS.Africa, DRIVE_ROOT_ID], ({ Date: D, now }) => ({
        files: [{ region: 'Africa', id: TARGET_IDS.Africa, parent: DRIVE_ROOT_ID, top: null, due: longAgo(D, now) },
                { region: 'Africa', id: DRIVE_ROOT_ID, parent: null, top: null, due: longAgo(D, now) }],
        folders: [], capped: 0, outside: 0 })],
      ['the Africa region folder and the drive as emptied folders', {}, [TARGET_IDS.Africa, DRIVE_ROOT_ID], () => ({
        files: [],
        folders: [{ region: 'Africa', id: TARGET_IDS.Africa, name: 'Africa', parent: DRIVE_ROOT_ID, top: TARGET_IDS.Africa },
                  { region: 'Asia', id: DRIVE_ROOT_ID, name: 'GLOW Shared Drive', parent: null, top: TARGET_IDS.Asia }],
        capped: 0, outside: 0 })],
      ['Template\'s region folder inside Africa\'s "Golden Wings 06-01-2026" as an Africa folder, the drive as a photo',
       { moveFolders: [['T:Template', GOLDEN]] }, [TARGET_IDS.Template, DRIVE_ROOT_ID], ({ Date: D, now, idOf }) => ({
        files: [{ region: 'Africa', id: DRIVE_ROOT_ID, parent: null, top: null, due: longAgo(D, now) }],
        folders: [{ region: 'Africa', id: TARGET_IDS.Template, name: 'Template', parent: idOf[GOLDEN], top: idOf[GOLDEN] }],
        capped: 0, outside: 0 })],
      ['the Asia source folder (My Drive) as a due photo, the drive as a folder', {}, [sid('Asia'), DRIVE_ROOT_ID], ({ Date: D, now }) => ({
        files: [{ region: 'Asia', id: sid('Asia'), parent: null, top: null, due: longAgo(D, now) }],
        folders: [{ region: 'Asia', id: DRIVE_ROOT_ID, name: 'GLOW Shared Drive', parent: null, top: TARGET_IDS.Asia }],
        capped: 0, outside: 0 })],
      ['an old photo outside the region folders (in "Kept Photos Archive" at the root) as an Africa due photo, with its true ' +
       'parent, and that archive folder as an emptied Africa folder', {}, ['T:drive/Kept Photos Archive/RET_K1.jpg', 'T:drive/Kept Photos Archive'],
       ({ Date: D, now, idOf }) => ({
         files: [{ region: 'Africa', id: idOf['T:drive/Kept Photos Archive/RET_K1.jpg'], parent: idOf['T:drive/Kept Photos Archive'],
                   top: null, due: longAgo(D, now) }],
         folders: [{ region: 'Africa', id: idOf['T:drive/Kept Photos Archive'], name: 'Kept Photos Archive', parent: DRIVE_ROOT_ID,
                     top: idOf['T:drive/Kept Photos Archive'] }],
         capped: 0, outside: 0 })],
      // not refused by its id: the later-of clock, re-read on its live folder, keeps it (an error is not required)
      ['an old photo in a young folder the plan does not hold (RET_A9, 200 days, in "Silver Roots 10-25-2026", 5 days) passed as due',
       {}, [AF + 'Silver Roots 10-25-2026/RET_A9.jpg'], ({ Date: D, now, idOf }) => ({
         files: [{ region: 'Africa', id: idOf[AF + 'Silver Roots 10-25-2026/RET_A9.jpg'], parent: idOf[AF + 'Silver Roots 10-25-2026'],
                   top: idOf[AF + 'Silver Roots 10-25-2026'], due: longAgo(D, now) }],
         folders: [], capped: 0, outside: 0 }), false],
    ];
    const boxP = [];
    for (const [what, o, badRefs, replacePlan, refuse] of SANDBOX) {
      const r = run185(REAL, '90', Object.assign({ replacePlan }, o)), p = [];
      const bad = badRefs.map(x => (own(r.idOf, x) ? r.idOf[x] : x));   // a label, or an id
      const sent = r.ops.filter(x => x.op === 'update' && bad.includes(x.fileId)).map(x => r.labelOf(x.fileId) + ' ' + JSON.stringify(x.resource));
      if (sent.length) p.push('Files.update on ' + sent.join(', '));
      const binnedBad = bad.map(id => r.labelOf(id)).filter(l => l && r.state(l) && r.state(l).trashed);
      if (binnedBad.length) p.push('in the trash: ' + binnedBad.join(', '));
      if (retTrashes(r).length) p.push('trashed on the Shared Drive: ' + trashedT(r).join(', '));
      if (refuse !== false && !/\bTRASH_REFUSED\b/.test(r.text)) p.push('no TRASH_REFUSED line');
      if (refuse !== false && !r.threw) p.push('the run ends with no error');
      if (!r.planTrashCalls.length) p.push('(planTrash_ never called: the test replaced nothing)');
      p.push(...movesAsBefore(r), ...banned(r));
      if (p.length) boxP.push(what + ': ' + p.join('; '));
    }
    check('planTrash_ replaced by one returning a region folder id and the drive id: no Files.update carries either, ' +
          'TRASH_REFUSED, the run ends in an error (as due photos, as emptied folders, a region folder nested inside another ' +
          'region\'s, a configured source folder, a photo and a folder outside the region folders planned as Africa\'s: none ' +
          'trashed or sent to Files.update, nothing on the Shared Drive trashed, the moves and #144\'s removals as without ' +
          'retention, nothing banned; an old photo in a young folder the plan does not hold, passed as due, is never sent a ' +
          'trash either)', !boxP.length, boxP.slice(0, 7).join(' | '));

    // ---------------------------------------------------------------- the re-checks
    const MERGED = 'S:Africa/Golden Wings 06-01-2026/IMG_8201.jpg';
    const MERGE_SOURCES = [['Africa', 'Golden Wings 06-01-2026', [['IMG_8201.jpg', 3100, OLD]]]];
    const L1 = MANGO + '/RET_L1.jpg', PLUM = EVE + '/Nested Plum Shots', L2 = GOLDEN + '/RET_L2.jpg';
    // [what, opt, trashed (the rest of the plan), never trashed nor sent a trash, a folder the plan must hold]
    const RECHECK = [
      ['moved, trashed or no longer due after the read (a photo moved into the old emptied "Golden Wings 06-01-2026", one a ' +
       'person trashed, one whose createdTime is now 10 days, a region subfolder whose createdTime is now 20 days, a nested ' +
       'folder moved into Latin America\'s region folder)',
       { afterPlan: [['move', F.A7, GOLDEN], ['trash', F.S1], ['created', F.A0, 10 * RDAY], ['created', BRIGHT, 20 * RDAY],
                     ['move', KIWI, 'T:Latin America']] },
       [F.A1, F.A2, F.A4, ZEBRA, F.S0, F.S0b, F.S2, F.S3, F.T1],
       [F.A7, GOLDEN, F.S1, F.A0, F.A5, F.A6, BRIGHT, F.T2, F.T3, MANGO, KIWI]],
      ['folders moved out of their region folder after the read (a region subfolder three levels above its last photo moved ' +
       'outside the region folders; a nested folder, a region subfolder and the old emptied folder into another region\'s)',
       { afterPlan: [['move', SW, 'T:drive/Kept Photos Archive'], ['move', ZEBRA, 'T:Asia'], ['move', EVE, 'T:Latin America'],
                     ['move', GOLDEN, 'T:Asia']] },
       [F.A0, F.A1, F.A2, F.A5, F.A6, BRIGHT, F.A7, F.S0, F.S0b],
       [F.T1, F.T2, F.T3, KIWI, MANGO, SW, F.A4, ZEBRA, F.S1, F.S2, F.S3, EVE, GOLDEN]],
      ['late children (after the read: a photo three deep, a folder in a region subfolder, a photo in the old emptied folder)',
       { afterPlan: [['add', L1, 1 * RDAY], ['add', PLUM, 0], ['add', L2, 2 * RDAY]] },
       minus(HAND, [MANGO, KIWI, SW, EVE, GOLDEN]), [MANGO, KIWI, SW, EVE, GOLDEN, L1, PLUM, L2]],
      ['a photo merged this run into the old emptied "Golden Wings 06-01-2026"', { extraSources: MERGE_SOURCES },
       minus(HAND, [GOLDEN]), [GOLDEN, MERGED]],
      ['the same, that folder\'s listing missing the merged photo (Drive\'s index behind the move: the plan holds the folder)',
       { extraSources: MERGE_SOURCES, staleIndexOf: GOLDEN }, minus(HAND, [GOLDEN]), [GOLDEN, MERGED], GOLDEN],
      // folders the plan does NOT hold, above planned items: only a walk up Drive's live parents sees them move
      ['unplanned folders moved into another region\'s folder after the read ("Sunrise Club 07-01-2026", kept for its young ' +
       'photo, above two planned photos and the planned nested folder with its photo; "Morning Star Club" above a planned ' +
       'photo); and a planned emptied folder\'s own createdTime now 20 days ("Golden Wings 06-01-2026", no photo in it)',
       { afterPlan: [['move', SUN, 'T:Asia'], ['move', MSC, 'T:Latin America'], ['created', GOLDEN, 20 * RDAY]] },
       minus(HAND, [F.A1, F.A2, F.A4, ZEBRA, F.A7, GOLDEN]), [F.A1, F.A2, F.A4, ZEBRA, F.A7, GOLDEN]],
      ['an unplanned folder moved outside the region folders, another one\'s createdTime now 20 days, after the read ("Sunrise ' +
       'Club 07-01-2026" into "Kept Photos Archive" at the root; "Morning Star Club": its old photo no longer due)',
       { afterPlan: [['move', SUN, 'T:drive/Kept Photos Archive'], ['created', MSC, 20 * RDAY]] },
       minus(HAND, [F.A1, F.A2, F.A4, ZEBRA, F.A7]), [F.A1, F.A2, F.A4, ZEBRA, F.A7]],
      // mid-trash, right after the first Shared Drive trash: each item's own re-check is just before its trash (R9), not
      // a snapshot taken once (whichever item went first is out of it: it was trashed before the change)
      ['changes mid-trash, after the first trash (a photo moved outside the region folders, one whose createdTime is now ' +
       '10 days, one a person trashed, a late photo in a planned folder, the old emptied folder moved into another region\'s)',
       { afterFirstTrash: [['move', F.T2, 'T:drive/Kept Photos Archive'], ['created', F.A0, 10 * RDAY], ['trash', F.S2],
                           ['add', EVE + '/RET_L3.jpg', 0], ['move', GOLDEN, 'T:Asia']] },
       minus(HAND, [F.T2, F.A0, F.S2, EVE, GOLDEN]), [F.T2, F.A0, F.S2, EVE, GOLDEN, EVE + '/RET_L3.jpg'], null, true],
      // an UNPLANNED nested folder above planned items ("Nested Kiwi Shots" holding a young photo, so neither it nor
      // "Silver Wings 05-01-2026" is planned; T2 in it and "Nested Mango Shots" with T3 below it are): only a walk up
      // Drive's live parents, nested folders included, sees it move
      ['an unplanned nested folder moved into another region\'s folder after the read ("Nested Kiwi Shots", kept for a young ' +
       'photo, above a planned photo and the planned "Nested Mango Shots" with its photo)',
       { extra: [[KIWI + '/RET_Y1.jpg', 5 * RDAY]], afterPlan: [['move', KIWI, 'T:Latin America']] },
       minus(HAND, [F.T2, F.T3, MANGO, KIWI, SW]), [F.T2, F.T3, MANGO, KIWI, SW, KIWI + '/RET_Y1.jpg'], MANGO, false, KIWI],
      ['the same unplanned nested folder moved outside the region folders after the read (into "Kept Photos Archive" at the root)',
       { extra: [[KIWI + '/RET_Y1.jpg', 5 * RDAY]], afterPlan: [['move', KIWI, 'T:drive/Kept Photos Archive']] },
       minus(HAND, [F.T2, F.T3, MANGO, KIWI, SW]), [F.T2, F.T3, MANGO, KIWI, SW, KIWI + '/RET_Y1.jpg'], MANGO, false, KIWI],
      // a planned folder a person trashed (its photo with it) is never sent a trash again
      ['a planned folder a person trashed after the read ("Nested Zebra Album", its planned photo in the trash through it)',
       { afterPlan: [['trash', ZEBRA]] }, minus(HAND, [ZEBRA, F.A4]), [ZEBRA, F.A4]],
      ['the same, mid-trash (a person trashes "Nested Zebra Album" right after the first trash)',
       { afterFirstTrash: [['trash', ZEBRA]] }, minus(HAND, [ZEBRA, F.A4]), [ZEBRA, F.A4], null, true],
    ];
    const recheckRuns = [], recheckP = [];
    /** A re-check run: no error; `must` trashed; `kept` never trashed nor sent a trash; nothing outside HAND; nothing banned. */
    const recheckProblems = (r, must, kept) => {
      const p = r.threw ? ['threw: ' + r.threw] : [], got = trashedT(r);
      const missing = must.filter(l => !got.includes(l));
      if (missing.length) p.push('not trashed: ' + missing.join(', '));
      const hit = kept.filter(l => got.includes(l) || trashSent(r, l));
      if (hit.length) p.push('trashed, or sent a trash, though it changed after the read: ' + hit.join(', '));
      const extra = got.filter(l => !HAND.includes(l));
      if (extra.length) p.push('trashed outside the plan: ' + extra.join(', '));
      return p.concat(banned(r));
    };
    for (const [what, o, mustAll, keptAll, plannedLbl, mid, unplannedLbl] of RECHECK) {
      const r = run185(REAL, '90', o);
      recheckRuns.push(r);
      const first = mid && retTrashes(r).length ? retTrashes(r)[0].label : null;
      const kept = keptAll.filter(l => l !== first), must = mustAll.concat(first && keptAll.includes(first) ? [first] : []);
      const p = recheckProblems(r, must, kept);
      if (mid && !first) p.push('(nothing trashed: the change never came)');
      if (o.extraSources) {
        const s = r.state(MERGED);
        if (!s || s.parent !== GOLDEN || s.trashed) p.push('the merged photo is not in "Golden Wings 06-01-2026", untrashed: ' + JSON.stringify(s));
      }
      if (plannedLbl && !r.planTrashCalls.some(c => (c.planned || []).includes(r.idOf[plannedLbl]))) {
        p.push('(the plan does not hold ' + plannedLbl + ': this row proves nothing)');
      }
      if (unplannedLbl && r.planTrashCalls.some(c => (c.planned || []).includes(r.idOf[unplannedLbl]))) {
        p.push('(the plan holds ' + unplannedLbl + ': this row proves nothing)');
      }
      if (p.length) recheckP.push(what.split(' (')[0] + ': ' + p.slice(0, 5).join('; '));
    }
    // per-trash freshness: changes picked from what is left, after the 5th photo trash (a photo moved outside the region
    // folders, another re-dated to 1 day, both in planned folders where there are such) and after the first folder trash
    // (a young photo into a planned folder still there, "Silver Wings 05-01-2026" where it is; the emptied "Golden Wings
    // 06-01-2026" into Asia's region folder): a snapshot taken once, after the first trash, misses both
    {
      const isPlanned = l => HAND.includes(l);
      const r = run185(REAL, '90', { midTrash: [
        { after: 5, change: v => {
          const files = v.left().filter(x => !x.isFolder);
          const moved = files.find(x => isPlanned(x.parent)) || files[0];
          const redated = files.find(x => x !== moved && x.parent !== moved.parent && isPlanned(x.parent)) || files.find(x => x !== moved);
          return [['move', moved.label, 'T:drive/Kept Photos Archive'], ['created', redated.label, 1 * RDAY]];
        } },
        { after: 'folder', change: v => {
          const folders = v.left().filter(x => x.isFolder);
          const young = folders.find(x => x.label === SW) || folders.find(x => x.label !== GOLDEN);
          const steps = young ? [['add', young.label + '/RET_L4.jpg', 0]] : [];
          if (folders.some(x => x.label === GOLDEN)) steps.push(['move', GOLDEN, 'T:Asia']);
          return steps;
        } }] });
      const above = l => HAND.filter(x => l.startsWith(x + '/'));   // the planned folders holding l
      const kept = [];
      for (const a of r.midApplied) {
        for (const [what, lbl] of a.steps) {
          if (what === 'add') kept.push(lbl, ...above(lbl));
          else if (what === 'created') kept.push(lbl, ...above(lbl));
          else kept.push(lbl);   // moved: what was under it stays under it
        }
      }
      const p = recheckProblems(r, minus(HAND, kept), [...new Set(kept)]);
      if (!r.midApplied.some(a => a.after === 5)) p.push('(the 5th photo trash never came: nothing changed mid-trash)');
      if (!r.midApplied.some(a => a.after === 'folder' && a.steps.length)) p.push('(no folder trashed: nothing changed after the first one)');
      if (p.length) recheckP.push('changes picked after the 5th photo trash and after the first folder trash (' +
                                  JSON.stringify(r.midApplied.map(a => a.steps.map(s => s[0] + ' ' + s[1]))) + '): ' + p.slice(0, 5).join('; '));
    }
    check('re-checks: moved, trashed or no-longer-due files skipped; a folder moved out of its region at any level keeps ' +
          'everything under it; a late child keeps its folder and the ancestors; no error (thirteen runs: what changed after ' +
          'the read is never trashed nor sent a trash, the rest of the plan is trashed, nothing outside it; a photo merged into ' +
          'an old emptied folder this run keeps it, also when that folder\'s listing missed the photo; folders the plan does ' +
          'not hold, a region subfolder or nested deeper, moved into another region\'s folder or outside, or their createdTime ' +
          'changed, keep what is under them; an emptied folder whose own createdTime is now young is kept; a planned folder a ' +
          'person trashed is never sent a trash; changes after the first trash, after the 5th photo trash and after the first ' +
          'folder trash are seen too; nothing banned)',
          !recheckP.length, recheckP.slice(0, 13).join(' | '));

    // ---------------------------------------------------------------- #191: the folders this run merged into
    /**
     * #191 (epic #179; the low finding on PR #190): a young photo this run merged into an old Shared Drive folder, Drive's
     * search index behind the merge at the read's listing AND at the re-list just before the trash (opt.staleIndexAlways:
     * every search this run misses it, Files.get sees it), so the folder looks emptied both times. That folder (that one:
     * old empty folders of its name elsewhere, in another region or nested, still go), and every planned folder above it up
     * to (never) the region folder, and nothing else (old empty folders beside it, beside a folder above it or inside it,
     * in the same region subfolder, still go), is not trashed nor sent a trash that run, whatever Drive's search returns: also when
     * no listing of the folders above it returns the one below (opt.unlistedAlways), and when the merge left the folder's
     * modifiedTime as it was (opt.moveKeepsModified). Each is skipped before any Drive call for it: once planTrash_ has
     * returned, no listing names it, no write touches it, and no Files.get reads it but the walk up of a planned item below
     * it. The rest of the plan is trashed (other due folders of the same region included); no error, no failure; `not
     * trashed "<region subfolder>"` logged, the `trashed` counts without them, no file's name and no nested folder's on a
     * retention line. The next run, the index caught up, keeps it: the photo is young. The dry run on the same drive writes
     * nothing and previews as ever. Not repeated here: the index behind at the read only (RECHECK's stale row: the re-list
     * sees the photo) or at the re-list only (the read sees the photo: the plan never holds the folder, RECHECK's merge row).
     */
    {
      const EVE_MERGED = 'S:Asia/Evening Lights 06-01-2026/IMG_8202.jpg';
      const EVE_SOURCES = [['Asia', 'Evening Lights 06-01-2026', [['IMG_8202.jpg', 3200, OLD]]]];
      // decoys: old, empty, due folders named as the merged-into one, in Asia's region folder and nested in an Africa one
      const ASIA_GW = AS + 'Golden Wings 06-01-2026', SUN_GW = SUN + '/Golden Wings 06-01-2026';
      // decoys beside and below the kept chain, in its region subfolder: old, empty, due folders that still go (the
      // merged-into folder and the folders above it are kept, nothing else): beside it in the folder above it (FIG in
      // "Bright Stars 07-10-2026", LIME in "Nested Mango Shots"), beside a folder above it (PEAR in "Silver Wings
      // 05-01-2026", beside "Nested Kiwi Shots"), inside it (DATE in "Golden Wings 06-01-2026"); ages varied
      const FIG = BRIGHT + '/Nested Fig Album', LIME = MANGO + '/Nested Lime Shots', PEAR = SW + '/Nested Pear Shots',
            DATE = GOLDEN + '/Nested Date Album';
      const DECOY_NAMES = ['Nested Fig Album', 'Nested Lime Shots', 'Nested Pear Shots', 'Nested Date Album'];
      const DEEP_EXTRA = [[PEAR, 160 * RDAY], [LIME, 95 * RDAY], [DATE, 130 * RDAY]];
      // decoys holding due photos (they go with them), and folders above the merged one holding no photo of their own
      // (kept all the same): FIG holds RET_F1 (and, in the blind nested run, "Bright Stars 07-10-2026"'s own two photos,
      // moved into it before the read: that folder then holds only FIG and the merged-into folder); in both three-deep runs
      // "Nested Kiwi Shots"'s photo RET_T2 is moved into PEAR before the read, so it holds only "Nested Mango Shots"
      const F1 = FIG + '/RET_F1.jpg', FIG_EXTRA = [[FIG, 120 * RDAY], [F1, 140 * RDAY]];
      const N ={ sun: 'Sunrise Club 07-01-2026', bright: 'Bright Stars 07-10-2026', golden: 'Golden Wings 06-01-2026',
                  msc: 'Morning Star Club', eve: 'Evening Lights 06-01-2026', sw: 'Silver Wings 05-01-2026' };
      const tops90 = over => Object.assign({}, TOPS_90, over);

      // the fake: the index behind the merge at every search of the run, Files.get not; the next run's searches see it;
      // opt.unlistedAlways and opt.moveKeepsModified
      {
        const env = fakeEnv('ids', { retentionDays: '90', staleIndexAlways: [GOLDEN], unlistedAlways: [ZEBRA],
                                     moveKeepsModified: [GOLDEN] });
        const D = env.globals.Drive.Files, all = { supportsAllDrives: true, includeItemsFromAllDrives: true };
        const id = l => env.idOf[l];
        const every = q => {
          const got = [];
          let tok = null;
          do {
            const pg = D.list(Object.assign({ q, fields: 'nextPageToken, files(id)', corpora: 'drive', driveId: DRIVE_ROOT_ID }, all,
                                            tok ? { pageToken: tok } : {}));
            got.push(...(pg.files || []).map(f => f.id));
            tok = pg.nextPageToken || null;
          } while (tok);
          return got;
        };
        const modified = l => D.get(id(l), { fields: 'modifiedTime', supportsAllDrives: true }).modifiedTime;
        const SRC = S('Africa', 'Bright Stars 2026-10-14'), PHOTO = SRC + '/IMG_4471.jpg';
        const before = { golden: modified(GOLDEN), src: modified(SRC) };
        env.advance(1);   // (so a bumped modifiedTime differs)
        D.update({}, id(PHOTO), null, { addParents: id(GOLDEN), removeParents: id(SRC), supportsAllDrives: true });
        const inGolden = "'" + id(GOLDEN) + "' in parents and trashed = false";
        const first = every(inGolden), second = every(inGolden);
        const wide = every("mimeType != '" + DRIVE_FOLDER_MIME + "' and trashed = false");
        const app = [];
        for (const it = env.globals.DriveApp.getFolderById(id(GOLDEN)).getFiles(); it.hasNext();) app.push(it.next().getId());
        const got = D.get(id(PHOTO), { fields: 'parents, trashed', supportsAllDrives: true });
        const hits = env.staleHits.length;
        const inSun = every("'" + id(SUN) + "' in parents and trashed = false");
        const sunApp = [];
        for (const it = env.globals.DriveApp.getFolderById(id(SUN)).getFolders(); it.hasNext();) sunApp.push(it.next().getId());
        const allFolders = every("mimeType = '" + DRIVE_FOLDER_MIME + "' and trashed = false");
        const zebra = D.get(id(ZEBRA), { fields: 'parents, trashed', supportsAllDrives: true });
        const kept = { golden: modified(GOLDEN), src: modified(SRC) };
        env.newRun();
        const after = every(inGolden);
        check('the fake (#191): with staleIndexAlways, every search of the run misses a photo the run moved into that folder ' +
              '(its listing twice, a drive-wide search, DriveApp\'s getFiles), Files.get sees it there, the next run\'s listing ' +
              'finds it; with unlistedAlways a folder is in no listing of its parent (Files.list, DriveApp\'s getFolders) but in ' +
              'the drive-wide folder search, Files.get giving its parent; with moveKeepsModified the move leaves that folder\'s ' +
              'modifiedTime (the source subfolder\'s still changes)',
              !first.includes(id(PHOTO)) && !second.includes(id(PHOTO)) && !wide.includes(id(PHOTO)) && wide.includes(id(F.A5)) &&
              !app.includes(id(PHOTO)) && same(got.parents, [id(GOLDEN)]) && got.trashed === false && hits >= 4 &&
              after.includes(id(PHOTO)) && !inSun.includes(id(ZEBRA)) && inSun.includes(id(F.A1)) && !sunApp.includes(id(ZEBRA)) &&
              allFolders.includes(id(ZEBRA)) && same(zebra.parents, [id(SUN)]) && zebra.trashed === false &&
              kept.golden === before.golden && kept.src !== before.src,
              JSON.stringify({ first, second, wideHasIt: wide.includes(id(PHOTO)), app, got, hits, after,
                               zebraInSun: inSun.includes(id(ZEBRA)), sunApp: sunApp.length, zebra, before, kept }));
      }

      /**
       * Each run: opt; plan, what the plan holds (as the read sees it); kept, never trashed nor sent a trash this run (the
       * rest of the plan is trashed); photos, [merged photo, the folder it must still be in]; regions / tops, the `trashed`
       * counts [files, folders] per region and per region subfolder; notTrashed, the region subfolders on a `not trashed`
       * line; hidden, the merged-into folder's name when it is nested (on no retention line).
       */
      const nested = { plan: HAND.concat(FIG, F1).sort(), regions: { Africa: [8, 2], Asia: [5, 1], Template: [3, 3] },
                       tops: { [N.sun]: [3, 1], [N.bright]: [3, 1], [N.msc]: [1, 0], [N.eve]: [3, 1], [N.sw]: [3, 3] },
                       notTrashed: [N.bright], hidden: [N.golden] };
      const deep = { plan: HAND.concat(PEAR, LIME, DATE).sort(), regions: { Africa: [7, 2], Asia: [5, 1], Template: [3, 3] },
                     tops: { [N.sun]: [3, 1], [N.bright]: [2, 1], [N.msc]: [1, 0], [N.eve]: [3, 1], [N.sw]: [3, 3] },
                     notTrashed: [N.sw], hidden: [N.golden] };
      const ROWS = [
        { what: 'a young photo merged into the old emptied "Golden Wings 06-01-2026" (Africa; the merge leaves its modifiedTime; ' +
                'two old empty folders of its name, Asia\'s region subfolder and one nested in "Sunrise Club 07-01-2026", still ' +
                'go, and so does the old empty "Nested Date Album" inside it)',
          opt: { extraSources: MERGE_SOURCES, staleIndexAlways: [GOLDEN], moveKeepsModified: [GOLDEN],
                 extra: [[ASIA_GW, 150 * RDAY], [SUN_GW, 150 * RDAY], [DATE, 130 * RDAY]] },
          plan: HAND.concat(ASIA_GW, SUN_GW, DATE).sort(), kept: [GOLDEN], photos: [[MERGED, GOLDEN]],
          regions: { Africa: [7, 4], Asia: [5, 2], Template: [3, 3] },
          // (two region subfolders of one name: Africa's line for "Nested Date Album" and Asia's decoy's both read [0, 1])
          tops: tops90({ [N.sun]: [3, 2], [N.golden]: [0, 1] }), notTrashed: [N.golden], hidden: [] },
        { what: 'young photos merged into it and into Asia\'s old "Evening Lights 06-01-2026", whose three due photos go this run ' +
                '(neither merge changes its folder\'s modifiedTime)',
          opt: { extraSources: MERGE_SOURCES.concat(EVE_SOURCES), staleIndexAlways: [GOLDEN, EVE], moveKeepsModified: [GOLDEN, EVE] },
          plan: HAND, kept: [GOLDEN, EVE], photos: [[MERGED, GOLDEN], [EVE_MERGED, EVE]],
          regions: { Africa: [7, 2], Asia: [5, 0], Template: [3, 3] }, tops: tops90({ [N.golden]: [0, 0], [N.eve]: [3, 0] }),
          notTrashed: [N.golden, N.eve], hidden: [] },
        Object.assign({ what: 'nested: "Golden Wings 06-01-2026", merged into, moved by a person into the old "Bright Stars ' +
                              '07-10-2026" before the retention read (its two due photos go, it and the folder above it stay; ' +
                              '"Nested Fig Album" beside it there with its due photo, and "Nested Zebra Album" in Africa, still go)',
                        opt: { extraSources: MERGE_SOURCES, staleIndexAlways: [GOLDEN], beforeRetentionRead: [['move', GOLDEN, BRIGHT]],
                               extra: FIG_EXTRA },
                        kept: [GOLDEN, BRIGHT], photos: [[MERGED, GOLDEN]] }, nested),
        Object.assign({ what: 'nested three deep: the same folder moved into Template\'s "Nested Mango Shots" before the retention ' +
                              'read, "Nested Kiwi Shots"\'s photo into "Nested Pear Shots" (the three planned folders above it ' +
                              'stay, "Nested Kiwi Shots" with no photo of its own, the three due photos go; "Nested Lime Shots" ' +
                              'beside it, "Nested Pear Shots" beside "Nested Kiwi Shots" with that photo, "Nested Date Album" ' +
                              'inside it and Africa\'s due folders still go)',
                        opt: { extraSources: MERGE_SOURCES, staleIndexAlways: [GOLDEN],
                               beforeRetentionRead: [['move', GOLDEN, MANGO], ['move', F.T2, PEAR]], extra: DEEP_EXTRA },
                        kept: [GOLDEN, MANGO, KIWI, SW], bare: [KIWI], photos: [[MERGED, GOLDEN]] }, deep),
        Object.assign({ what: 'nested, the folder above it blind to it and holding no photo of its own: as the nested run, its ' +
                              'two photos moved into "Nested Fig Album" before the read, and no listing of "Bright Stars ' +
                              '07-10-2026" this run returns "Golden Wings 06-01-2026"',
                        opt: { extraSources: MERGE_SOURCES, staleIndexAlways: [GOLDEN],
                               beforeRetentionRead: [['move', GOLDEN, BRIGHT], ['move', F.A5, FIG], ['move', F.A6, FIG]],
                               unlistedAlways: [GOLDEN], extra: FIG_EXTRA },
                        kept: [GOLDEN, BRIGHT], bare: [BRIGHT], photos: [[MERGED, GOLDEN]] }, nested),
        Object.assign({ what: 'three deep, each folder above it blind to the one below: as the three-deep run, and no listing of ' +
                              '"Nested Mango Shots", "Nested Kiwi Shots" or "Silver Wings 05-01-2026" this run returns the ' +
                              'folder in it ("Nested Kiwi Shots" holding no photo of its own, as there)',
                        opt: { extraSources: MERGE_SOURCES, staleIndexAlways: [GOLDEN],
                               beforeRetentionRead: [['move', GOLDEN, MANGO], ['move', F.T2, PEAR]],
                               unlistedAlways: [GOLDEN, MANGO, KIWI], extra: DEEP_EXTRA },
                        kept: [GOLDEN, MANGO, KIWI, SW], bare: [KIWI], photos: [[MERGED, GOLDEN]] }, deep),
      ];
      const photoProblems = (r, photos) => photos.flatMap(([photo, folder]) => {
        const s = r.state(photo);
        return s && s.parent === folder && !s.trashed ? [] : ['the merged photo is not in ' + folder + ', untrashed: ' + JSON.stringify(s)];
      });
      /** No error; the plan but `kept` trashed; `kept` never trashed nor sent a trash; nothing outside the plan; nothing banned. */
      const mergedProblems = (r, plan, kept) => {
        const p = r.threw ? ['threw: ' + r.threw] : [], got = trashedT(r);
        const missing = minus(plan, kept).filter(l => !got.includes(l));
        if (missing.length) p.push('not trashed: ' + missing.join(', '));
        const hit = kept.filter(l => got.includes(l) || trashSent(r, l));
        if (hit.length) p.push('trashed, or sent a trash, though this run merged into it or into a folder below it: ' + hit.join(', '));
        const extra = got.filter(l => !plan.includes(l));
        if (extra.length) p.push('trashed outside the plan: ' + extra.join(', '));
        return p.concat(banned(r));
      };
      /**
       * Skipped before any Drive call: once planTrash_ has returned, no Files.list names a kept folder in parents, no write
       * touches one, and no Files.get reads one with nothing of the plan below it (the walk up of a planned item reads the
       * folders above that item, kept or not).
       */
      const touchProblems = (r, plan, kept) => {
        if (r.planSeq === null || r.planSeq === undefined) return ['(planTrash_ never returned: this row proves nothing)'];
        const rest = minus(plan, kept), quiet = kept.filter(k => !rest.some(l => l.startsWith(k + '/')));
        const labelOf = new Map(kept.filter(l => r.idOf[l] !== undefined).map(l => [r.idOf[l], l]));
        const p = [];
        for (const x of r.reads) {
          if (x.seq <= r.planSeq) continue;
          if (x.op === 'list') for (const id of x.parents || []) if (labelOf.has(id)) p.push('a listing of ' + labelOf.get(id));
          if (x.op === 'get' && labelOf.has(x.fileId) && quiet.includes(labelOf.get(x.fileId))) p.push('a Files.get of ' + labelOf.get(x.fileId));
        }
        for (const o of r.ops) if (o.seq > r.planSeq && labelOf.has(o.fileId)) p.push('a Files.' + o.op + ' of ' + labelOf.get(o.fileId));
        return [...new Set(p)].map(x => x + ' after planTrash_ returned');
      };
      const mergedRuns = [], mergedP = [];
      for (const row of ROWS) {
        const r = run185(REAL, '90', row.opt);
        mergedRuns.push(r);
        const p = mergedProblems(r, row.plan, row.kept).concat(photoProblems(r, row.photos), touchProblems(r, row.plan, row.kept));
        if (/\bTRASH_(FAILED|REFUSED)\b|\bRETENTION_FAILED\b/.test(r.text)) p.push('a retention failure or refusal logged');
        const counts = [...r.text.matchAll(/\b(\d+) (?:retention trash )?failure/g)].map(m => Number(m[1])).filter(x => x > 0);
        if (counts.length) p.push('a failure count of ' + counts.join(', '));
        for (const [, folder] of row.photos) {
          if (!r.staleHits.some(h => h.folder === folder && !h.afterPlan)) p.push('(the read saw the photo in ' + folder + ': this row proves nothing)');
        }
        for (const [, lbl, into] of row.opt.beforeRetentionRead || []) {
          if (!r.state(lbl) || r.state(lbl).parent !== into) p.push('(' + lbl + ' is not in ' + into + ': this row proves nothing)');
        }
        const before = r.modelBefore();
        for (const lbl of row.bare || []) {   // a kept folder above the merged one with no photo of its own, as the read saw it
          if (before.some(m => !m.isFolder && !m.trashed && m.parent === r.idOf[lbl])) p.push('(' + lbl + ' holds a photo: this row proves nothing)');
        }
        if (p.length) mergedP.push(row.what.split(' (')[0] + ': ' + p.slice(0, 6).join('; '));
      }
      // the dry run on the same drive: nothing written, the preview as without the merges (nothing merges in a dry run)
      {
        const d = run185(PREVIEW, '90', ROWS[1].opt);
        const p = (d.threw ? ['threw: ' + d.threw] : []).concat(d.ops.length || d.trashes.length ? ['wrote ' + d.ops.length + ' op(s), ' +
          d.trashes.length + ' trash(es)'] : []).concat(retentionProblems(retentionView(d.text, wantOf(d, 90).tops), RET_WANT[90]));
        if (p.length) mergedP.push('the dry run: ' + p.slice(0, 4).join('; '));
      }
      check('a folder this run merged a young photo into is not trashed that run though Drive\'s index misses the photo at the ' +
            'read and at the re-list, nor any planned folder above it, never the region folder, each skipped before any Drive ' +
            'call for it; the rest of the plan is trashed, old empty folders beside it, beside a folder above it and inside ' +
            'it included (six runs: "Golden Wings 06-01-2026" emptied and old, the merge leaving its modifiedTime, while old ' +
            'empty folders of its name in Asia and nested in Africa, and one inside it, go; it and Asia\'s "Evening Lights ' +
            '06-01-2026", whose due photos go; it nested in "Bright Stars 07-10-2026", "Nested Fig Album" beside it and ' +
            '"Nested Zebra Album" still trashed; it three deep in Template, the three folders above it kept, "Nested Lime ' +
            'Shots" beside it, "Nested Pear Shots" beside "Nested Kiwi Shots" and one inside it trashed; the decoys holding ' +
            'due photos go with them; a folder above it with no photo of its own is kept; both nested ones again with no ' +
            'listing of a folder above it returning the folder below: each merged photo still in its folder, untrashed; after ' +
            'planTrash_ no listing or write of a kept folder, no Files.get of one with nothing planned below it; no error, no ' +
            'failure; nothing banned; the dry run writes nothing and previews as ever)',
            !mergedP.length, mergedP.slice(0, 6).join(' | '));

      // the next run, 15 minutes later, the index caught up: the photo is seen, and young
      const nextP = [];
      for (const i of [1, 2]) {
        const { what, kept, photos } = ROWS[i];
        const r2 = mergedRuns[i].rerun({ retentionDays: '90', advanceMin: 15 });
        R185.push(r2);
        const p = r2.threw ? ['threw: ' + r2.threw] : [];
        const hit = kept.filter(l => (r2.state(l) && r2.state(l).trashed) || trashSent(r2, l));
        if (hit.length) p.push('in the trash, or sent a trash by the next run: ' + hit.join(', '));
        p.push(...photoProblems(r2, photos));
        if (retTrashes(r2).length) p.push('the next run trashed on the Shared Drive: ' + trashedT(r2).join(', '));
        p.push(...banned(r2));
        if (p.length) nextP.push(what.split(' (')[0].split(',')[0] + ': ' + p.slice(0, 5).join('; '));
      }
      check('…and the next run, 15 minutes later with the index caught up, keeps them: the photos are young (both merged ' +
            'folders, and the nested one with the folder above it: none in the trash or sent a trash, the photos where they were ' +
            'merged, nothing trashed on the Shared Drive, no error, nothing banned)', !nextP.length, nextP.slice(0, 4).join(' | '));

      // the log: counts and region subfolder names only
      const logM = [];
      ROWS.forEach(({ what, regions, tops, notTrashed, hidden }, i) => {
        const r = mergedRuns[i];
        // (a nested merged-into folder's name is in the log as the My Drive subfolder merged: #132's line, not retention's)
        const p = logProblems(r, 90, regions, tops).filter(x => !hidden.some(nm => x === 'the log names "' + nm + '"'));
        for (const nm of notTrashed) {
          if (!new RegExp('\\bnot trashed\\b[^\\n]*"' + nm + '"').test(r.text)) p.push('no `not trashed "' + nm + '"` line');
        }
        const named = r.text.split('\n').filter(l => /\btrashed\b|\bTRASH_|\bRETENTION_/.test(l) &&
                                                     hidden.concat(NESTED, DECOY_NAMES).some(nm => l.includes(nm)));
        if (named.length) p.push('a retention line names a nested folder: ' + named[0].trim());
        if (p.length) logM.push(what.split(' (')[0] + ': ' + p.slice(0, 5).join('; '));
      });
      check('…its log: `not trashed "<region subfolder>"` for each kept merged-into folder (by its region subfolder when ' +
            'nested), the `trashed` counts per region and region subfolder without the kept folders (the decoys of its name ' +
            'counted), no file\'s name, no nested folder\'s name on a retention line (the six runs above)',
            !logM.length, logM.slice(0, 6).join(' | '));
    }

    // ---------------------------------------------------------------- the cap
    const GR = 'T:Latin America/Golden Roots 05-05-2026';
    const B = k => GR + '/RET_B' + String(k).padStart(3, '0') + '.jpg';
    const range = (a, b) => Array.from({ length: b - a + 1 }, (_, i) => a + i);
    const capExtra = [[GR, 160 * RDAY]].concat(range(0, 109).map(k => [B(k), Math.round((141 + 8 * (k + 0.5) / 110) * RDAY)]));
    // 125 due: the 100 earliest are 6 of RET_ITEMS and B016-B109; then the other 25 (B000-B015 and 9 of RET_ITEMS)
    const CAP1 = [F.S0, F.T1, F.T2, F.A7, F.T3, F.S0b, GOLDEN, MANGO, KIWI, SW].concat(range(16, 109).map(B)).sort();
    const CAP2 = [F.S1, F.S2, F.S3, F.A0, F.A1, F.A2, F.A4, F.A5, F.A6, ZEBRA, BRIGHT, EVE, GR].concat(range(0, 15).map(B)).sort();
    const capNums = r => [...r.text.matchAll(/\bRETENTION_CAP\b\D{0,40}?(\d+)/g)].map(m => Number(m[1]));
    const capP2 = [];
    {
      const c1 = run185(REAL, '90', { extra: capExtra });
      const o1 = planOf(c1, 90);
      if (!same(o1, CAP1)) capP2.push('THE TEST\'S ORACLE DISAGREES (the first run): ' + diff(o1, CAP1));
      if (c1.threw) capP2.push('the first run threw: ' + c1.threw);
      if (!same(trashedT(c1), CAP1)) capP2.push('the first run trashed ' + diff(trashedT(c1), CAP1));
      const n1 = retTrashes(c1).filter(t => !t.isFolder).length;
      if (n1 !== 100) capP2.push('the first run trashed ' + n1 + ' photo(s), want 100');
      const cap1 = capNums(c1);
      if (!cap1.length || cap1.some(x => x !== 25)) capP2.push('the first run: RETENTION_CAP ' + JSON.stringify(cap1) + ', want 25');
      capP2.push(...banned(c1).map(b => 'the first run: ' + b));
      const firstRight = same(trashedT(c1), CAP1);
      const c2 = c1.rerun({ retentionDays: '90', advanceMin: 15 });
      R185.push(c2);
      const o2 = planOf(c2, 90);   // (on what the first run left: the hand-worked CAP2 only once it trashed CAP1)
      if (firstRight && !same(o2, CAP2)) capP2.push('THE TEST\'S ORACLE DISAGREES (the next run): ' + diff(o2, CAP2));
      if (c2.threw) capP2.push('the next run threw: ' + c2.threw);
      if (!same(trashedT(c2), CAP2)) capP2.push('the next run trashed ' + diff(trashedT(c2), CAP2));
      if (capNums(c2).some(x => x !== 0)) capP2.push('the next run: RETENTION_CAP ' + JSON.stringify(capNums(c2)));
      capP2.push(...banned(c2).map(b => 'the next run: ' + b));
      // the cap holds in the trash itself: planTrash_ handed maxFiles 1000 (a wrong caller) plans all 125
      const c3 = run185(REAL, '90', { extra: capExtra, replacePlan: ({ args, planTrash }) => planTrash(args[0], args[1], args[2], 1000) });
      const n3 = retTrashes(c3).filter(t => !t.isFolder).length;
      if (!c3.planTrashCalls.some(c => (c.planned || []).includes(c3.idOf[GR]))) capP2.push('(maxFiles 1000: the plan does not hold all 125: proves nothing)');
      if (n3 > 100) capP2.push('maxFiles 1000: ' + n3 + ' photos trashed in one run, want at most 100');
      const notEarliest = trashedT(c3).filter(l => !CAP1.includes(l));
      if (notEarliest.length) capP2.push('maxFiles 1000: trashed beyond the 100 earliest: ' + notEarliest.slice(0, 6).join(', '));
      if (!capNums(c3).some(x => x > 0)) capP2.push('maxFiles 1000: no RETENTION_CAP line from the trash (the preview, capped 0, has none)');
      capP2.push(...banned(c3).map(b => 'maxFiles 1000: ' + b));
    }
    check('more than 100 due: the 100 earliest trashed, RETENTION_CAP logged, the next run trashes the rest (125 due: 6 of the ' +
          'hand-worked layout and the 94 oldest of 110 photos 141-149 days old in Latin America, with the four folders they ' +
          'empty, RETENTION_CAP 25; 15 minutes later the other 25 and the four folders they empty, no RETENTION_CAP; with ' +
          'planTrash_ handed maxFiles 1000 the trash still stops at 100, none beyond the 100 earliest, RETENTION_CAP logged)',
          !capP2.length, capP2.slice(0, 6).join('; '));

    // ---------------------------------------------------------------- failures
    const failP = [];
    const failT = run185(REAL, '90', { failTrashOf: [F.A5, F.T3, ZEBRA, F.S0] });
    {
      const want = minus(HAND, [F.A5, F.T3, ZEBRA, F.S0, BRIGHT, MANGO, KIWI, SW]);   // the folders still holding them stay
      if (!failT.threw) failP.push('refused trashes: the run ends with no error');
      if (!same(trashedT(failT), want)) failP.push('refused trashes: trashed ' + diff(trashedT(failT), want));
      for (const rx of [/TRASH_FAILED Africa "Bright Stars 07-10-2026"/, /TRASH_FAILED Africa "Sunrise Club 07-01-2026"/,
                        /TRASH_FAILED Template "Silver Wings 05-01-2026"/, /TRASH_FAILED Asia\b/]) {
        if (!rx.test(said(failT))) failP.push('refused trashes: no line matching ' + rx);
      }
      const named = NESTED.filter(nm => said(failT).includes(nm)).concat(fileNamesIn(said(failT)));
      if (named.length) failP.push('refused trashes: names ' + named.join(', '));
      failP.push(...banned(failT).map(b => 'refused trashes: ' + b));
      const BS = 'Bright Stars 2026-10-14';   // a My Drive subfolder whose photos' moves fail (MOVE_FAILED)
      const failM = run185(REAL, '90', { failMoveOf: BS });
      if (!/\bMOVE_FAILED\b/.test(failM.threw)) failP.push('a failed move: the run does not end with MOVE_FAILED: ' + (failM.threw || 'no error'));
      if (!same(trashedT(failM), HAND)) failP.push('a failed move: trashed ' + diff(trashedT(failM), HAND));
      const preview = retentionProblems(retentionView(failM.text, wantOf(failM, 90).tops), RET_WANT[90]);
      if (preview.length) failP.push('a failed move: the would-trash lines: ' + preview.slice(0, 3).join('; '));
      failP.push(...banned(failM).map(b => 'a failed move: ' + b));
      const failMT = run185(REAL, '90', { failMoveOf: BS, failTrashOf: [F.S0] });
      if (!/\bMOVE_FAILED\b/.test(failMT.threw) || !/\bTRASH_FAILED\b/.test(failMT.threw)) {
        failP.push('a failed move and a refused trash: the error does not name both: ' + (failMT.threw || 'no error'));
      }
      if (!same(trashedT(failMT), minus(HAND, [F.S0]))) failP.push('a failed move and a refused trash: trashed ' + diff(trashedT(failMT), minus(HAND, [F.S0])));
      const failMR = run185(REAL, '90', { failMoveOf: BS, failSearch: { kind: 'folders', page: 2 } });
      if (!/\bMOVE_FAILED\b/.test(failMR.threw) || !/\bRETENTION_FAILED\b/.test(failMR.threw)) {
        failP.push('a failed move and a failed retention read: the error does not name both: ' + (failMR.threw || 'no error'));
      }
      if (retTrashes(failMR).length) failP.push('a failed move and a failed retention read: trashed ' + trashedT(failMR).join(', '));
    }
    check('TRASH_FAILED names the region and the region subfolder only, the rest goes on, the run ends in an error; a ' +
          'MOVE_FAILED does not skip retention (four trashes Drive refuses: a photo in a region subfolder, one three deep, a ' +
          'nested folder, a photo directly in a region folder: each region subfolder on a TRASH_FAILED line, no file or nested ' +
          'folder named, the folders still holding them kept, the rest of the plan trashed; with a MOVE_FAILED the plan is ' +
          'previewed and trashed all the same; the error names both with a TRASH_FAILED, and with a RETENTION_FAILED, which ' +
          'trashes nothing)', !failP.length, failP.slice(0, 6).join('; '));

    // ---------------------------------------------------------------- the time budget
    const trashBudget = r => /TIME_BUDGET[^\n]*\b(trash|retention)|\b(trash|retention)[^\n]*TIME_BUDGET/i.test(r.text);
    const budgetP = [];
    {
      const cut = (tag, r) => {
        const got = trashedT(r), late = r.ops.filter(o => o.t - r.t0 >= BUDGET);
        if (!got.length) budgetP.push(tag + ': nothing trashed before the budget ran out');
        if (got.length >= HAND.length) budgetP.push(tag + ': all ' + got.length + ' trashed; the budget never stopped it');
        if (late.length) {
          budgetP.push(tag + ': ' + late.length + ' Drive write(s) from 5 minutes on: ' +
                       late.slice(0, 3).map(o => (o.label || o.fileId) + ' at ' + ((o.t - r.t0) / MIN) + ' min').join(', '));
        }
        if (!trashBudget(r)) budgetP.push(tag + ': no TIME_BUDGET line for the trash');
        const extra = got.filter(l => !HAND.includes(l));
        if (extra.length) budgetP.push(tag + ': trashed outside the plan: ' + extra.join(', '));
        budgetP.push(...banned(r).map(b => tag + ': ' + b));
        return got;
      };
      const b1 = run185(REAL, '90', { trashAdvanceMin: 2 });
      const first = cut('2 minutes a trash', b1);
      const b2 = b1.rerun({ retentionDays: '90', advanceMin: 15 });
      R185.push(b2);
      if (b2.threw) budgetP.push('the next run threw: ' + b2.threw);
      const both = first.concat(trashedT(b2)).sort();
      if (!same(both, HAND)) budgetP.push('the two runs together trashed ' + diff(both, HAND));
      cut('half a minute a re-check read', run185(REAL, '90', { recheckAdvanceMin: 0.5 }));
    }
    check('past the run budget: no trash, TIME_BUDGET logged (the clock 2 minutes on per Shared Drive trash: part of the plan ' +
          'trashed, no Drive write from 5 minutes on, TIME_BUDGET for the trash, the next run 15 minutes later trashes the ' +
          'rest; half a minute per Drive read after the plan: the same)', !budgetP.length, budgetP.slice(0, 6).join('; '));

    // ---------------------------------------------------------------- the log
    const lateKids = recheckRuns[2];
    const logP = logProblems(real, 90, { Africa: [7, 3], Asia: [5, 1], Template: [3, 3] }, TOPS_90).map(x => 'the real run: ' + x)
      .concat(logProblems(lateKids, 90, { Africa: [7, 2], Asia: [5, 0], Template: [3, 0] },
                          { 'Sunrise Club 07-01-2026': [3, 1], 'Bright Stars 07-10-2026': [2, 1], 'Morning Star Club': [1, 0],
                            'Evening Lights 06-01-2026': [3, 0], 'Silver Wings 05-01-2026': [3, 0] }).map(x => 'late children: ' + x))
      .concat(['Silver Wings 05-01-2026', 'Evening Lights 06-01-2026', 'Golden Wings 06-01-2026']
        .filter(nm => !new RegExp('\\bnot trashed\\b[^\\n]*"' + nm + '"').test(lateKids.text))
        .map(nm => 'late children: no `not trashed "' + nm + '"` line'))
      .concat(logProblems(failT, 90, { Africa: [6, 1], Asia: [4, 1], Template: [2, 0] },
                          { 'Sunrise Club 07-01-2026': [3, 0], 'Bright Stars 07-10-2026': [1, 0], 'Golden Wings 06-01-2026': [0, 1],
                            'Morning Star Club': [1, 0], 'Evening Lights 06-01-2026': [3, 1], 'Silver Wings 05-01-2026': [2, 0] })
        .map(x => 'refused trashes: ' + x));
    for (const [tag, r] of [['the real run', real], ['late children', lateKids], ['refused trashes', failT]]) {
      for (const nm of NESTED) if (said(r).includes(nm)) logP.push(tag + ': names "' + nm + '"');
    }
    check('retention logs carry counts and region subfolder names, never a file name or a nested folder\'s name (per region ' +
          '`<Region>: … trashed N file(s) and M folder(s)`, per region subfolder `… under "<name>"`, the numbers what was ' +
          'trashed: the whole plan; with late children what the re-checks left; with refused trashes what Drive took; `not ' +
          'trashed "<region subfolder>"` where a re-check kept something; never "Nested Zebra Album", "Nested Kiwi Shots", ' +
          '"Nested Mango Shots", "Nested Plum Shots" or a file)', !logP.length, logP.slice(0, 8).join('; '));

    // ---------------------------------------------------------------- each trash re-checked just before it (R9)
    /**
     * In the order of the fake's reads and writes (seq): every Shared Drive trash sent (refused ones too) follows, since
     * the Drive write before it, a Files.get of that item; a folder's also a listing `'<id>' in parents and trashed =
     * false` (no mimeType or createdTime clause: files and folders) followed to its last page. The walk up its parents
     * may be read once per folder per run (the ticket's Context): not checked here.
     */
    const freshProblems = r => {
      const p = [], writes = r.ops.slice().sort((a, b) => a.seq - b.seq), chains = chainsOf(r);
      let checked = 0;
      for (const o of writes) {
        if (o.op !== 'update' || o.kind !== 'trash' || !o.trash || !/^T:/.test(o.trash.label)) continue;
        checked++;
        const before = writes.filter(w => w.seq < o.seq), since = before.length ? before[before.length - 1].seq : 0;
        const between = x => x.seq > since && x.seq < o.seq;
        if (!r.reads.some(x => x.op === 'get' && x.fileId === o.fileId && between(x))) {
          p.push(o.trash.label + ': no Files.get of it since the Drive write before its trash');
        }
        if (o.trash.isFolder && !chains.some(ch => ch[0].parents.includes(o.fileId) && untrashedOnly(ch[0]) && !ch[0].mimes.length &&
                                                   !ch[0].created.length && between(ch[0]) && between(ch[ch.length - 1]) &&
                                                   ch[ch.length - 1].last === true && !ch[ch.length - 1].failed)) {
          p.push(o.trash.label + ': not re-listed (`trashed = false`, to its last page) since the Drive write before its trash');
        }
      }
      return { p, checked };
    };
    const freshRuns = [real].concat(R185).map(r => [r, freshProblems(r)]);
    const freshChecked = freshRuns.reduce((n, [, f]) => n + f.checked, 0);
    const freshP = freshRuns.filter(([, f]) => f.p.length).map(([r, f]) => r.name + ' ' + JSON.stringify(r.opt.retentionDays) + ': ' +
                                                                         f.p.slice(0, 3).join('; '));
    check('…re-checks just before each trash, in the order of Drive\'s reads and writes: each of the ' + freshChecked + ' Shared ' +
          'Drive trash(es) in this part\'s runs follows a Files.get of that item made since the Drive write before it, and each ' +
          'folder\'s also a listing of it (`\'<id>\' in parents and trashed = false`, no other clause) to its last page made since ' +
          'then (the walk up its parents may be read once per folder per run)',
          freshChecked > 0 && !freshP.length, freshP.slice(0, 6).join(' | ') || (freshChecked ? '' : 'no trash on the Shared Drive in any run'));

    // ---------------------------------------------------------------- the rules, and every run of this part
    const okFile = { via: 'Drive.Files.update', id: 'x1', label: SUN + '/RET_X1.jpg', isFolder: false, role: 'file', structural: false,
                     viaHelper: true, wasTrashed: false, children: 0, settled: true, t: 1000 * RDAY, driveId: DRIVE_ROOT_ID,
                     region: 'Africa', createdMs: 800 * RDAY, parentCreatedMs: 850 * RDAY, liveChildren: 0, retentionDays: 90,
                     planned: true, parentAsPlanned: true, regionAsPlanned: true };
    const okFolder = Object.assign({}, okFile, { id: 'x2', label: SUN, isFolder: true, role: 'shared', children: 2, parentCreatedMs: 600 * RDAY });
    const ok144 = { via: 'Drive.Files.update', id: 'x3', label: S('Asia', EMPTIED), isFolder: true, role: 'source-sub', structural: false,
                    viaHelper: true, wasTrashed: false, children: 0, settled: true, t: 1000 * RDAY, driveId: undefined, region: null,
                    createdMs: 999 * RDAY, parentCreatedMs: NaN, liveChildren: 0, retentionDays: null, planned: false,
                    parentAsPlanned: false, regionAsPlanned: false };
    const asRun = x => ({ calls: x.calls || [], trashes: x.trashes || [], ops: x.ops || [] });
    const trashOp = t => ({ op: 'update', kind: 'trash', fileId: t.id, label: t.label, resource: { trashed: true },
                            args: { supportsAllDrives: true }, trash: t });
    const withTrash = t => asRun({ trashes: [t], ops: [trashOp(t)] });
    const fileTrash = o => withTrash(Object.assign({}, okFile, o)), dirTrash = o => withTrash(Object.assign({}, okFolder, o));
    const upd = (resource, args, more) => asRun({ ops: [Object.assign({ op: 'update', kind: 'other', fileId: 'x9', label: AF + 'RET_X9.jpg',
                                                                        resource, args: Object.assign({ supportsAllDrives: true }, args) }, more)] });
    const PARENTS = { addParents: 'p', removeParents: 'q' };
    const MUST_BAN = ['Drive.Files.delete', 'Drive.Files.remove', 'Drive.Files.emptyTrash', 'Drive.Files.trash', 'Drive.Files.untrash',
                      'Folder.setTrashed', 'File.setTrashed'].map(c => ['a call of ' + c, asRun({ calls: [c] })]).concat([
      ['{trashed: true} with addParents and removeParents', upd({ trashed: true }, PARENTS)],
      ['{trashed: true} with another key', upd({ trashed: true, name: 'x' }, {})],
      ['{trashed: false} of a file a person trashed', upd({ trashed: false }, PARENTS, { kind: 'rescue', wasTrashed: true, wasExplicit: true, fromTrashedSourceSub: true })],
      ['{trashed: false} of a Shared Drive item', upd({ trashed: false }, PARENTS, { kind: 'rescue', wasTrashed: true, wasExplicit: false, fromTrashedSourceSub: false })],
      ['{trashed: false} of a file not in the trash', upd({ trashed: false }, PARENTS, { kind: 'rescue', wasTrashed: false, wasExplicit: false, fromTrashedSourceSub: true })],
      ['a trash of a configured folder', dirTrash({ structural: true })],
      ['a trash outside the region folders', fileTrash({ region: null })],
      ['a trash in My Drive but #144\'s', fileTrash({ driveId: undefined })],
      ['a trash of a photo before its due moment (its folder too young)', fileTrash({ parentCreatedMs: 950 * RDAY })],
      ['a trash of a photo with no date', fileTrash({ createdMs: NaN })],
      ['a trash of a folder with an untrashed child', dirTrash({ liveChildren: 1 })],
      ['a trash of a folder younger than RETENTION_DAYS', dirTrash({ createdMs: 950 * RDAY })],
      ['a trash with retention off', fileTrash({ retentionDays: null })],
      ['a trash of something planTrash_ did not plan', fileTrash({ planned: false, parentAsPlanned: false, regionAsPlanned: false })],
      ['a trash of a photo moved since the plan', fileTrash({ parentAsPlanned: false })],
      ['a trash of an item now in another region', fileTrash({ regionAsPlanned: false })],
      ['a trash of an item already in the trash', fileTrash({ wasTrashed: true })],
      ['a trash outside ' + TRASH_HELPER, fileTrash({ viaHelper: false })],
      ['a trash by DriveApp setTrashed', asRun({ calls: ['Folder.setTrashed'], trashes: [Object.assign({}, okFolder, { via: 'DriveApp.setTrashed' })] })],
    ]);
    const MUST_ALLOW = [['a due Shared Drive photo', withTrash(okFile)], ['an emptied old Shared Drive folder (its photos in the trash)', withTrash(okFolder)],
                        ['#144: an emptied, settled source subfolder', withTrash(ok144)], ['a move', upd({}, PARENTS, { kind: 'move' })],
                        ['#144\'s rescue', upd({ trashed: false }, PARENTS, { kind: 'rescue', wasTrashed: true, wasExplicit: false, fromTrashedSourceSub: true })]];
    const rulesP = MUST_BAN.filter(([, x]) => !banned(x).length).map(([w]) => 'not banned: ' + w)
      .concat(MUST_ALLOW.filter(([, x]) => banned(x).length).map(([w, x]) => 'banned: ' + w + ' (' + banned(x).join('; ') + ')'));
    const runsP = R185.flatMap(r => banned(r).concat(r.calls.filter(NEVER).map(c => 'called ' + c)).map(b => r.name + ': ' + b));
    const trashing = R185.filter(r => retTrashes(r).length).length;
    check('forbidden calls (the union with #144): delete, emptyTrash, setTrashed, a trash mixed with parent changes or other ' +
          'keys, an untrash outside the rescue (the rules ban these, Files.trash and untrash, and every Shared Drive trash ' +
          'retention\'s entry does not allow: a configured folder, outside the region folders, My Drive, not yet due, no date, ' +
          'a folder with an untrashed child or too young, retention off, not planned, moved or in another region since, ' +
          'already trashed, outside ' + TRASH_HELPER + ', by setTrashed; they allow #144\'s removal and rescue, a move, a due ' +
          'photo and an emptied old folder; across this part\'s ' + R185.length + ' runs, ' + trashing + ' of them trashing on ' +
          'the Shared Drive, nothing banned)',
          !rulesP.length && trashing > 0 && !runsP.length,
          rulesP.concat([...new Set(runsP)]).slice(0, 8).join('; ') || (trashing ? '' : 'no run trashed anything on the Shared Drive'));
  }

  // ---------------------------------------------------------------- `complete`, in every run that plans
  const configuredIds = new Set(Object.values(TARGET_IDS).concat(DRIVE_ROOT_ID));   // complete plays no part for these
  const planning = RUNS.slice(FROM).filter(r => r.planTrashCalls.length);
  const completeP = planning.flatMap(r => {
    const full = fullyListed(r);
    return r.planTrashCalls.flatMap(c => (c.folders || []).filter(d => !configuredIds.has(d.id) && (d.complete === true) !== full.has(d.id))
      .map(d => r.name + ' ' + JSON.stringify(r.opt.retentionDays) + ': ' + (r.labelOf(d.id) || d.id) + ' complete ' +
                JSON.stringify(d.complete) + (full.has(d.id) ? ' though listed to its last page' : ' though not listed to its last page')));
  });
  check('planTrash_ is handed `complete: true` exactly for the folders whose listing (`\'<id>\' in parents`, `trashed = false`, ' +
        'no createdTime clause) reached its last page, and for no other folder, in every run of this section that plans (' +
        planning.length + ')', planning.length > 0 && !completeP.length,
        completeP.slice(0, 6).join('; ') || (planning.length ? '' : 'planTrash_ never called'));

  // ---------------------------------------------------------------- every run: the flags, and nothing new allowed
  const mine = RUNS.slice(FROM);
  const flagless = RUNS.flatMap(r => r.reads.concat(r.ops).filter(x => !x.args || x.args.supportsAllDrives !== true ||
                                                                      (x.op === 'list' && x.args.includeItemsFromAllDrives !== true))
    .map(x => r.name + ': Files.' + x.op + ' ' + JSON.stringify(x.args || {}).slice(0, 140)));
  check('every Drive.Files call carries supportsAllDrives, every list includeItemsFromAllDrives (every entry-point run in this ' +
        'file, #144\'s listings of My Drive included; ' + RUNS.length + ' runs)',
        mine.some(r => retentionReads(r).length > 0) && !flagless.length,
        [...new Set(flagless)].slice(0, 6).join('; ') || (mine.some(r => retentionReads(r).length > 0) ? '' : 'no retention search in any run'));
  const bannedHere = mine.flatMap(r => banned(r).concat(r.name === PREVIEW ? sharedWrites(r) : sharedNonTrash(r)).map(b => r.name + ': ' + b));
  const previewed = mine.filter(r => r.name === REAL && /\bwould trash [1-9]/.test(r.text)).length;
  check('the forbidden-call rules (#144\'s TRASH_RULES and UPDATE_RULES, with retention\'s allowance of #185) hold across this ' +
        'section\'s ' + mine.length + ' runs: real runs that preview would-trash counts (' + previewed + ') write nothing on the ' +
        'Shared Drive but a trash TRASH_RULES allows, the dry runs nothing at all, and nothing banned',
        previewed > 0 && !bannedHere.length, [...new Set(bannedHere)].slice(0, 6).join('; '));
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
