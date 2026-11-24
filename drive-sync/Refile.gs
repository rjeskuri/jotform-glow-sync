/**
 * The one-time re-filing of the club folders already on the Shared Drive (ticket #237,
 * docs/plans/2026-11-23-refile-photo-folders.md). Since #225 the mover files a new submission
 * subfolder under `<Region>/<Partner>/<YYYY-MM>/`; the folders it filed before then sit directly
 * in the region folder, named `<Club Name> <MM-DD-YYYY>` (since 2026-10-30) or the club alone
 * (before), with no partner in the name. This file moves each of them once under
 * `<Region>/<Partner>/<YYYY-MM>/`, or `<Region>/<Partner>/undated/` when its name has no date.
 *
 *   previewRefile    the dry run: reads the region folders, logs the plan, changes nothing; run
 *                    it again until a run logs `cycle complete` (no TIME_BUDGET line)
 *   refileExisting   the real run: the same read and plan, then carried out; run it again until
 *                    a run logs `cycle complete`, and then until such a run moves nothing
 *
 * The partner comes from REFILE_LIST, a club -> partner list that tools/refile_list.py writes
 * once from the sheet's Roster and Partners exports, as a file RefileList.gs
 * (`const REFILE_LIST = [{"region", "partner", "club"}, ...]`). It is pasted into the project
 * beside this file for the re-filing only and deleted afterwards; this file neither declares nor
 * reads it until an entry point runs. The mover reads no sheet: no new scope, no new service.
 * Missing or malformed (not an array; a row that is not an object, or whose partner or club is
 * not a non-empty string): both entry points refuse before any Drive call.
 *
 * The region folders: TARGET_FOLDER_<KEY> of each region in PHOTO_REGIONS (Mover.gs); a region
 * without it is skipped and logged. Each must be a live folder named exactly the region, on one
 * Shared Drive, not its root, or the run is refused before anything is read. One run at a time
 * with the mover (the script lock).
 *
 * The read, one folder per listing (#262): the account that runs the mover reaches the region
 * folders through folder sharing and is no member of the Shared Drive, and Drive refuses it a
 * listing that names more than one folder (2026-11-24: "The attempted action requires shared
 * drive membership."). So each Drive.Files.list here is `'<id>' in parents` ANDed with trashed /
 * mimeType / name terms only, on that Shared Drive (listSharedDrive_), three levels deep: the
 * region folder's live folders (id, name); each one's items (ids and types: its files counted,
 * no file's name asked) and, when it holds folders, their names; and theirs (names only).
 *
 * Runs and cycles: a big region takes several runs to read. What a run learns is kept for the
 * next in the Script Properties, under REFILE_STATE_PREVIEW_ (the dry run) and
 * REFILE_STATE_APPLY_ (the real run), apart, in values of REFILE_CHUNK characters; the re-filing
 * writes and deletes no other property. The runs from a first one to the one that leaves nothing
 * are a cycle: each region, in order, is read on from where the last run stopped (its folder
 * list again every run: a folder added, trashed or moved since counts as it now is, the contents
 * as read during the cycle), planned and logged by the run that completes its read, then (the
 * real run) its moves made, over as many runs as they take; a region read in full is not read
 * again in its cycle. previewRefile reads for the run's whole time budget, refileExisting for
 * half and moves for the rest. A run that leaves work logs per region `TIME_BUDGET: <Region>: <n>
 * folder(s) left to read` (or `left to move`, or `not read this run`) with the runs left at its
 * pace; the run that leaves none logs `cycle complete` and deletes what was kept, and the next run
 * starts a new cycle from the Drive as it then is. REFILE_LIST or the region folders changed
 * since the last run: what was kept is dropped, no move of the old plan made, and the read starts
 * again. A folder Drive fails to list is REFILE_FAILED: the read stops for that run, which ends
 * with an error, and the next one tries it again; at its REFILE_TRIES-th failure in a cycle it
 * stays where it is (`unread`), and so does every folder planned into it.
 *
 *   planRefile_(regions, list) -> {refile, stays}      (no Google service; inputs unchanged)
 *
 * regions  {<Region>: {id, folders: [Folder]}}: the region folder's id and its live folders
 *          Folder {id, name, files, folders: [Folder]}: files, the number of live files directly
 *          in it (read for the region folder's own folders, the only level it is used at)
 * list     REFILE_LIST's rows [{region, partner, club}]
 * refile   [{region, id, name, path: [<Partner>, <YYYY-MM | undated>], to: <region folder id>,
 *           partnerId, monthId}]: partnerId / monthId the folder found there by name, null when
 *          the real run makes it
 * stays    [{region, id, name, code, why}]
 * Every folder directly in a region folder is in exactly one of the two lists.
 *
 * What a folder's name says (each name trimmed):
 *   `<Partner> | <Club> | <MM-DD-YYYY> [| <Week>]`   Plan.gs photoPath_: that partner, that month;
 *                                                     no lookup
 *   `| <Club> | <MM-DD-YYYY> [| <Week>]`             (a blank partner) the club, that month
 *   `<Club> <MM-DD-YYYY>`                            (since 2026-10-30) the club, its month
 *   `<Partner> <Club> <MM-DD-YYYY> [<Week>]`          (the integration's spaces-only naming of
 *                                                     2026-11-23) the partner and club, its month
 *     these two, and any other name the two layouts do not match, read alike: the last
 *     date-shaped word with a word before it is the date, the words before it the club text
 *     (looked up below), every word after it dropped (the week; also e.g. Drive's ` (1)`)
 *   any of these, with a date that is not a real one stays: bad-date
 *   anything else (no such word: the club alone, before 2026-10-30) the whole name is the club,
 *   `undated`
 * The club's partner (REFILE_LIST): every row offers its club and `<club> - <partner>` (what
 * question 5 sends for a club two partners share), and each of them after `<partner> `,
 * compared whitespace-collapsed and lower-cased; the rows of the folder's own region first,
 * every row when none of them has the name. One partner found: filed there; none: stays
 * (no-partner); two or more: stays (ambiguous, naming them).
 *
 * What holds a folder where it is (the codes the dry run logs; exact names: case and spaces count):
 *   holds-folders   it holds a folder: a partner folder, or not a photo folder; never moved. Also
 *                   an empty folder named like a partner this run files into (one a cut-short
 *                   run left): it is that partner folder
 *   duplicate-name  two or more folders of its name in the region folder: all of them stay
 *   partner-name    a folder of files named like a partner this run files into in its region:
 *                   it, and every folder for that partner there
 *   partner-folders two or more partner folders of that name in the region folder
 *   month-folders   two or more month folders of that name in the partner folder
 *   exists          a folder of its name is already in that month folder
 *   no-partner, ambiguous, bad-date   (above)
 *   unread          (#262, added after planRefile_) Drive failed to list it, or the partner or
 *                   month folder it was planned into, REFILE_TRIES times in the cycle
 *
 * What the real run does, and never does: each folder planned is moved itself, whole, by one
 * Drive.Files.update ({}, addParents the month folder, removeParents the region folder,
 * supportsAllDrives), within the Shared Drive; its photos stay in it and nothing is renamed.
 * The partner and month folders, once per run each: the plan's, re-read by id (still a live
 * folder of that name in its parent), else the one of that name a listing finds there (the mover
 * may have made it since the read), else made by Drive.Files.create (supportsAllDrives); two or
 * more of that name there by then: REFILE_FAILED. Just before each move the folder is read by id:
 * still a live folder of its name (kept as a hash) whose one parent is the region folder, or it
 * is skipped (`moved or trashed since the read`, no error); after it, read back: its one parent
 * the month folder, or REFILE_FAILED. The time budget is checked before each folder, never
 * between finding or making its partner and month folders and its move. Never a configured
 * SOURCE_ / TARGET_FOLDER_ folder, the Shared Drive's root, anything in the trash; nothing
 * trashed, shared, copied or deleted. A failure is logged by code, region and folder name, the
 * rest goes on, and the run ends with an error (what it kept saved first); a move done, skipped
 * or failed leaves the kept plan. A cycle after a complete one moves nothing (a moved folder is
 * no longer directly in the region folder).
 *
 * The log: per region, in the run that completes its read, a count line, then one line per
 * folder directly in the region folder, by name, with its target path or its code and reason.
 * Never a file's name: the read asks Drive for no file's name.
 */

const REFILE_DATE = /^(\d{2})-(\d{2})-(\d{4})$/;
const REFILE_UNDATED = 'undated';
const REFILE_NAME_SEP = ' - ';   // glow/sync.py SF_NAME_SEP: `<club> - <partner>`, a club two partners share
const REFILE_TRIES = 3;          // a folder Drive fails to list this many times in a cycle stays (unread)
const REFILE_STATE = 'REFILE_STATE_';   // the prefix of every Script Property the re-filing keeps between runs
const REFILE_CHUNK = 8000;       // characters per kept value, all ASCII: under Apps Script's 9 KB a value
const REFILE_NO_NAME = '\u0000'; // a name no Drive folder has: a stand-in for one the kept read does not know

function previewRefile() {
  runRefile_(false);
}

function refileExisting() {
  runRefile_(true);
}

/**
 * Check REFILE_LIST and the Script Properties, then, under the script lock, one run of the cycle (refileRun_) on what
 * the runs before kept; what it learned kept for the next (or, at the cycle's end, deleted) before any error is thrown.
 */
function runRefile_(apply) {
  const started = Date.now();
  const list = refileList_();
  const config = refileConfig_();
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10 * 1000)) {
    console.log('LOCKED: another run (the mover or a re-filing) is still going; this one read and moved nothing');
    return;
  }
  try {
    const driveId = openRefileRegions_(config.regions);
    console.log((apply ? 'REFILE RUN' : 'REFILE DRY RUN (nothing changes)') + ': regions ' +
                config.regions.map(c => c.region).join(', ') + '; REFILE_LIST ' + list.length + ' row(s)');
    for (const s of config.skipped) console.log(s);
    const state = loadRefileState_(apply, refileHash_(JSON.stringify([list, config.regions])));
    const run = { apply: apply, list: list, driveId: driveId, readBy: started + (apply ? RUN_BUDGET_MS / 2 : RUN_BUDGET_MS),
                  deadline: started + RUN_BUDGET_MS, stopRead: false, failed: [], skipped: [], moved: 0, made: 0,
                  folders: new Map(), never: null };
    let done = false, error = null;
    try {
      done = refileRun_(config.regions, state, run);
    } catch (e) {
      error = e;
    }
    saveRefileState_(apply, state, done && !error);
    if (error) throw error;
    if (run.failed.length) throw new Error(run.failed.length + ' failure(s): ' + run.failed[0]);
  } finally {
    lock.releaseLock();
  }
}

/** REFILE_LIST as pasted (RefileList.gs); throws, naming it, when it is missing or malformed. */
function refileList_() {
  const fix = ' (paste the RefileList.gs tools/refile_list.py writes; docs/plans/2026-11-23-refile-photo-folders.md)';
  if (typeof REFILE_LIST === 'undefined') throw new Error('REFILE_LIST refused: not defined in this project' + fix);
  const list = REFILE_LIST;
  if (!Array.isArray(list)) throw new Error('REFILE_LIST refused: not an array but ' + (list === null ? 'null' : typeof list) + fix);
  const text = v => typeof v === 'string' && v.trim() !== '';
  const bad = [];
  list.forEach((row, i) => {
    const what = row === null || typeof row !== 'object' || Array.isArray(row) ? 'not an object' :
      !text(row.partner) ? 'no partner' : !text(row.club) ? 'no club' :
      row.region !== undefined && typeof row.region !== 'string' ? 'a region that is not text' : '';
    if (what) bad.push('row ' + (i + 1) + ': ' + what);
  });
  if (bad.length) throw new Error('REFILE_LIST refused: ' + bad.length + ' bad row(s): ' + bad.slice(0, 5).join('; ') + fix);
  return list;
}

/**
 * {regions: [{region, target}], skipped: [<text>]}: TARGET_FOLDER_<KEY> of each region of PHOTO_REGIONS (the re-filing
 * needs no source folder). Unset: skipped. The same id twice, or none set: throws, before any folder is opened.
 */
function refileConfig_() {
  const props = PropertiesService.getScriptProperties();
  const regions = [], skipped = [], problems = [], seen = {};
  for (const region of PHOTO_REGIONS) {
    const name = 'TARGET_FOLDER_' + REGION_KEYS[region];
    const target = props.getProperty(name);
    if (!target) {
      skipped.push(region + ': skipped (' + name + ' not set)');
      continue;
    }
    if (Object.prototype.hasOwnProperty.call(seen, target)) problems.push(name + ' has the same id as ' + seen[target]);
    else seen[target] = name;
    regions.push({ region: region, target: target });
  }
  if (!regions.length && !problems.length) {
    problems.push('no TARGET_FOLDER_<KEY> is set (' + PHOTO_REGIONS.map(r => REGION_KEYS[r]).join(', ') + ')');
  }
  if (problems.length) throw new Error('CONFIG refused, Script Properties (drive-sync/README.md): ' + problems.join('; '));
  return { regions: regions, skipped: skipped };
}

/**
 * The id of the one Shared Drive the region folders are on. Each, read by Drive.Files.get, must be a live folder
 * named exactly its region, on a Shared Drive and not its root, all on the same one; otherwise CONFIG refused.
 */
function openRefileRegions_(regions) {
  const problems = [];
  let driveId = null, first = '';
  for (const c of regions) {
    const name = 'TARGET_FOLDER_' + REGION_KEYS[c.region];
    const got = Drive.Files.get(c.target, { fields: 'id, name, mimeType, trashed, driveId', supportsAllDrives: true });
    if (!got || got.mimeType !== FOLDER_MIME) {
      problems.push(name + ' is not a folder');
      continue;
    }
    if (got.name !== c.region) problems.push(name + ' is a folder named "' + got.name + '", not "' + c.region + '"');
    if (got.trashed !== false) problems.push(name + ' is in the trash');
    if (!got.driveId) problems.push(name + ' is not on a Shared Drive');
    else if (got.driveId === c.target) problems.push(name + ' is the Shared Drive itself (its root), not a region folder on it');
    else if (driveId === null) {
      driveId = got.driveId;
      first = name;
    } else if (got.driveId !== driveId) {
      problems.push(name + ' is on another Shared Drive than ' + first);
    }
  }
  if (problems.length) throw new Error('CONFIG refused: ' + problems.join('; '));
  return driveId;
}

/**
 * One run of the cycle on `state` (loadRefileState_), changed in place: first the read, region by region in order, of
 * each region not yet read in full, until `run.readBy` or a Drive failure; a region whose read this run completes is
 * planned and logged now, and with `run.apply` its moves kept; then, with `run.apply`, the kept moves, region by
 * region, until `run.deadline`. Logs what each region has left; true when none has any (the cycle's end).
 */
function refileRun_(regions, state, run) {
  const notes = [];
  for (const c of regions) {
    const s = state.g[c.region] || (state.g[c.region] = { p: 'r', r: {}, t: {}, b: [] });
    if (s.p !== 'r') {
      console.log(c.region + ': read in full and planned earlier in this cycle (that run\'s log has its plan)' +
                  (s.p === 'm' ? '; ' + s.m.length + ' folder(s) to move' : run.apply ? '; its moves done' : ''));
      continue;
    }
    if (run.stopRead || Date.now() > run.readBy) {
      notes.push('TIME_BUDGET: ' + c.region + ': not read this run (' + (run.stopRead ? 'the read stopped at a Drive failure' :
                 'no read time left') + '); a later run reads it');
      continue;
    }
    const got = readRefileRegion_(c, s, run);
    if (got.dropped) {   // its REFILE_FAILED line says so; the next cycle tries it again
      state.g[c.region] = { p: 'd' };
      continue;
    }
    if (got.left !== 0) {
      notes.push('TIME_BUDGET: ' + c.region + ': ' + (got.left === null ? 'its folder not listed in full ' +
                 (run.stopRead ? '(Drive failed)' : 'in time') :
                 got.left + ' folder(s) left to read' + refilePace_(got.left, got.read)) + '; not planned yet, the next run reads on');
      continue;
    }
    const plan = planRefileRead_(c, s, got.listed, run.list);
    logRefileRegion_(c.region, plan, run.apply);
    state.g[c.region] = run.apply ? refileMoves_(plan) : { p: 'd' };
  }
  if (run.apply) {
    run.never = new Set(configuredFolderIds_().all.concat([run.driveId]));
    for (const c of regions) {
      const s = state.g[c.region];
      if (s.p !== 'm') continue;
      const before = s.m.length;
      moveRefile_(c, s, run);
      if (!s.m.length) state.g[c.region] = { p: 'd' };
      else notes.push('TIME_BUDGET: ' + c.region + ': ' + s.m.length + ' folder(s) left to move' + refilePace_(s.m.length, before - s.m.length) +
                      '; the next run moves on from this read');
    }
    console.log('done: ' + run.moved + ' folder(s) moved, ' + run.made + ' partner or month folder(s) made, ' + run.skipped.length +
                ' skipped (moved or trashed since the read), ' + run.failed.length + ' failure(s)');
    for (const s of run.skipped) console.log(s);
  }
  for (const f of run.failed) console.log(f);
  for (const n of notes) console.log(n);
  const done = regions.every(c => state.g[c.region].p === 'd');
  console.log(done ? 'cycle complete: every region read in full and planned' + (run.apply ? ', its moves done' : '') +
                     '; the next run starts a new read' :
                     'not finished: run ' + (run.apply ? 'refileExisting' : 'previewRefile') + ' again, it carries on from here');
  return done;
}

/** ', about <k> more run(s) at this run's pace' for `left` still to do after `did` done this run; '' when none was done. */
function refilePace_(left, did) {
  return did > 0 ? ', about ' + Math.ceil(left / did) + ' more run(s) at this run\'s pace (' + did + ' this run)' : '';
}

/**
 * Reads on in the region folder `c`, one folder per Drive.Files.list (listSharedDrive_: `'<id>' in parents` ANDed with
 * trashed / mimeType terms), from where the kept read `s` stopped, until `run.readBy` (checked before each listing
 * and each page) or a Drive failure (run.stopRead). The region folder is listed again in full (its live folders, id
 * and name); a folder of it no longer there leaves `s`. Then each of them not yet read: its live items, ids and types
 * only (its files counted), and its folders' names when it holds any; and each of those: its folders' names, kept as
 * hashes. Returns {listed, left, read, dropped}: the region folder's folders, and how many folders still need a listing
 * (both null when the region folder's own listing did not finish in time or failed; `dropped` when that was its
 * REFILE_TRIES-th failure), and the listings done besides the region folder's.
 *   s  {p: 'r', r: {<id>: <files> | [<files>, [[<id>, <name>, null | [<hash of a folder's name in it>]]]]},
 *       t: {<id>: <failed listings>}, b: [<id> Drive failed to list REFILE_TRIES times]}
 */
function readRefileRegion_(c, s, run) {
  const folders = " and trashed = false and mimeType = '" + FOLDER_MIME + "'", bad = new Set(s.b);
  let read = 0;
  /** The items (`fields`) of the folder `f` the listing `q` gives; null when out of time, or Drive failed (counted). */
  const list = (f, q, fields) => {
    if (run.stopRead || Date.now() > run.readBy) return null;
    try {
      const got = listSharedDrive_(run.driveId, "'" + f.id + "' in parents" + q, fields, run.readBy);
      if (!got.complete) return null;
      read++;
      return got.files;
    } catch (e) {
      const tries = (s.t[f.id] || 0) + 1;
      s.t[f.id] = tries;
      if (tries >= REFILE_TRIES) {
        s.b.push(f.id);
        bad.add(f.id);
      }
      run.stopRead = true;
      run.failed.push('REFILE_FAILED ' + c.region + ' "' + f.name + '": Drive did not list it (try ' + tries + ' of ' + REFILE_TRIES +
                      (tries >= REFILE_TRIES ? ': left out of this cycle, unread' : ': the next run tries again') + '): ' + errorText_(e));
      return null;
    }
  };
  const top = list({ id: c.target, name: c.region + ' (the region folder)' }, folders, 'id, name');
  if (!top) return { listed: null, left: null, read: 0, dropped: bad.has(c.target) };
  read = 0;
  const listed = top, live = new Set(listed.map(f => f.id));
  for (const id of Object.keys(s.r)) if (!live.has(id)) delete s.r[id];
  for (const f of listed) {
    if (run.stopRead || Date.now() > run.readBy) break;
    if (bad.has(f.id)) continue;
    if (!Object.prototype.hasOwnProperty.call(s.r, f.id)) {
      const items = list(f, ' and trashed = false', 'id, mimeType');
      if (!items) break;
      const files = items.filter(x => x.mimeType !== FOLDER_MIME).length;
      if (files === items.length) {
        s.r[f.id] = files;
        continue;
      }
      const subs = list(f, folders, 'id, name');
      if (!subs) break;
      s.r[f.id] = [files, subs.map(x => [x.id, x.name, null])];
    }
    const v = s.r[f.id];
    if (typeof v === 'number') continue;
    for (const d of v[1]) {
      if (d[2] !== null || bad.has(d[0])) continue;
      const inside = list({ id: d[0], name: f.name + '/' + d[1] }, folders, 'name');
      if (!inside) break;
      d[2] = inside.map(x => refileHash_(x.name));
    }
  }
  return { listed: listed, left: refileLeft_(listed, s), read: read };
}

/** How many folders of the region folder's `listed` folders, or of theirs, the kept read `s` still has to list. */
function refileLeft_(listed, s) {
  const bad = new Set(s.b);
  let left = 0;
  for (const f of listed) {
    if (bad.has(f.id)) continue;
    const v = s.r[f.id];
    if (v === undefined) left++;
    else if (typeof v !== 'number') left += v[1].filter(d => d[2] === null && !bad.has(d[0])).length;
  }
  return left;
}

/**
 * planRefile_ on a region read in full over the cycle's runs: its folders as this run listed them (`listed`), their
 * contents as the kept read `s` has them. A month folder's folders are kept as name hashes: each is given to
 * planRefile_ as the region folder's folder of that name (for `exists`), or a name none of them has. A folder Drive
 * would not list (s.b) is given as holding a folder, so it is never moved, and stays `unread`, as does each folder
 * planned into it.
 */
function planRefileRead_(c, s, listed, list) {
  const bad = new Set(s.b), byHash = new Map();
  for (const f of listed) {
    const h = refileHash_(f.name);
    if (!byHash.has(h)) byHash.set(h, []);
    if (byHash.get(h).indexOf(f.name) < 0) byHash.get(h).push(f.name);
  }
  const inMonth = hashes => {
    const out = [];
    for (const h of hashes || []) {
      for (const name of byHash.get(h) || [REFILE_NO_NAME + h]) out.push({ id: '', name: name, files: null, folders: [] });
    }
    return out;
  };
  const folders = listed.map(f => {
    const v = bad.has(f.id) ? [1, [['', REFILE_NO_NAME, []]]] : s.r[f.id];
    if (typeof v === 'number') return { id: f.id, name: f.name, files: v, folders: [] };
    return { id: f.id, name: f.name, files: v[0],
             folders: v[1].map(d => ({ id: d[0], name: d[1], files: null, folders: bad.has(d[0]) ? [] : inMonth(d[2]) })) };
  });
  const plan = planRefile_({ [c.region]: { id: c.target, folders: folders } }, list);
  const unread = (e, why) => ({ region: e.region, id: e.id, name: e.name, code: 'unread', why: why });
  const times = REFILE_TRIES + ' times this cycle';
  plan.stays = plan.stays.map(e => (bad.has(e.id) ? unread(e, 'Drive failed to list it ' + times + '; never moved, the next cycle ' +
                                                            'reads it again') : e));
  const into = e => bad.has(e.partnerId) || bad.has(e.monthId);
  for (const e of plan.refile.filter(into)) {
    plan.stays.push(unread(e, 'Drive failed to list ' + c.region + '/' + e.path.join('/') + ' (or its partner folder) ' + times +
                              '; the next cycle plans it again'));
  }
  plan.refile = plan.refile.filter(e => !into(e));
  return plan;
}

/** A region's plan as kept between runs, its moves in plan order: {p: 'm', d: [[partner, month, partnerId, monthId]], m: [[id, name hash, d index]]}. */
function refileMoves_(plan) {
  const d = [], at = new Map(), m = [];
  for (const e of plan.refile) {
    const k = JSON.stringify([e.path, e.partnerId, e.monthId]);
    if (!at.has(k)) {
      at.set(k, d.length);
      d.push([e.path[0], e.path[1], e.partnerId || '', e.monthId || '']);
    }
    m.push([e.id, refileHash_(e.name), at.get(k)]);
  }
  return { p: 'm', d: d, m: m };
}

/**
 * The kept read and plan of this entry point (`apply`: the real run's, else the dry run's), {v, h, g: {<Region>: {p:
 * 'r' (reading, readRefileRegion_) | 'm' (moving, refileMoves_) | 'd' (done), ...}}}; a new one when none is kept, it
 * cannot be read, or `hash` (REFILE_LIST and the region folders) is not the one it was kept with.
 */
function loadRefileState_(apply, hash) {
  const prefix = refileStatePrefix_(apply);
  const props = PropertiesService.getScriptProperties().getProperties();
  const fresh = { v: 1, h: hash, g: {} }, count = prefix + 'n';
  if (!Object.prototype.hasOwnProperty.call(props, count)) return fresh;
  let state = null;
  try {
    const n = Number(props[count]);
    let text = '';
    for (let i = 0; i < n; i++) {
      if (typeof props[prefix + i] !== 'string') throw new Error('part ' + i + ' of ' + n + ' missing');
      text += props[prefix + i];
    }
    state = JSON.parse(text);
  } catch (e) {
    console.log('the progress kept by the last run (' + prefix + '*) could not be read (' + errorText_(e) + '): the read starts again');
    return fresh;
  }
  if (!state || state.v !== 1 || state.h !== hash || !state.g) {
    console.log('REFILE_LIST or the region folders changed since the last run: what it kept is dropped (no move of its plan is ' +
                'made) and the read starts again');
    return fresh;
  }
  return state;
}

/**
 * `state` kept for the next run, as ASCII JSON in values of REFILE_CHUNK characters (prefix + '0', '1', ..., and
 * prefix + 'n' their count) in one setProperties, then this prefix's values left over deleted; with `done`, every value
 * of this prefix deleted. No other property is written or deleted.
 */
function saveRefileState_(apply, state, done) {
  const prefix = refileStatePrefix_(apply);
  const store = PropertiesService.getScriptProperties(), count = prefix + 'n';
  let parts = 0;
  if (!done) {
    const text = JSON.stringify(state).replace(/[\u007f-\uffff]/g, ch => '\\u' + ('000' + ch.charCodeAt(0).toString(16)).slice(-4));
    const values = {};
    for (let i = 0; i < text.length; i += REFILE_CHUNK) values[prefix + (parts++)] = text.slice(i, i + REFILE_CHUNK);
    values[count] = String(parts);
    store.setProperties(values);
  } else if (store.getProperty(count) !== null) {
    store.deleteProperty(count);
  }
  for (const k of store.getKeys()) {
    const part = k.indexOf(prefix) === 0 ? k.slice(prefix.length) : null;
    if (part !== null && part !== 'n' && !(/^\d+$/.test(part) && Number(part) < parts)) store.deleteProperty(k);
  }
}

function refileStatePrefix_(apply) {
  return REFILE_STATE + (apply ? 'APPLY_' : 'PREVIEW_');
}

/** A 53-bit hash of `text` (cyrb53) in base 36: what the kept read and plan hold for a folder's name, and for REFILE_LIST. */
function refileHash_(text) {
  const s = String(text);
  let h1 = 0xdeadbeef, h2 = 0x41c6ce57;
  for (let i = 0; i < s.length; i++) {
    const ch = s.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(36);
}

/** 'YYYY-MM' of a date MM-DD-YYYY that is a real calendar date, '' otherwise (as Plan.gs photoPath_ reads one). */
function refileMonth_(text) {
  const d = REFILE_DATE.exec(text);
  if (!d) return '';
  const month = Number(d[1]), day = Number(d[2]), year = Number(d[3]);
  const real = new Date(Date.UTC(year, month - 1, day));
  if (real.getUTCFullYear() !== year || real.getUTCMonth() !== month - 1 || real.getUTCDate() !== day) return '';
  return d[3] + '-' + d[1];
}

/** glow.text.key: whitespace collapsed, lower-cased. */
function refileKey_(text) {
  return String(text).split(/\s+/).filter(Boolean).join(' ').toLowerCase();
}

/**
 * What a folder's name says (the top comment): {path: [<Partner>, <month>]} for a layout name with its partner,
 * {club, month} when the partner is to be looked up, or {code: 'bad-date', why}.
 */
function refileName_(name) {
  const layout = photoPath_(name);
  if (layout.length) return { path: layout };
  const text = String(name).trim();
  const parts = text.split('|').map(p => p.trim());
  let club = text, date = '';
  if ((parts.length === 3 || parts.length === 4) && parts[1] && REFILE_DATE.test(parts[2])) {
    club = parts[1];
    date = parts[2];
  } else {
    // the last date-shaped word is the date, anything after it the week; at least one word before it
    const words = text.split(/\s+/);
    for (let i = words.length - 1; i > 0; i--) {
      if (!REFILE_DATE.test(words[i])) continue;
      club = words.slice(0, i).join(' ');
      date = words[i];
      break;
    }
  }
  if (!date) return { club: club, month: REFILE_UNDATED };
  const month = refileMonth_(date);
  if (!month) return { code: 'bad-date', why: 'its date "' + date + '" is not a real date' };
  return { club: club, month: month };
}

/**
 * REFILE_LIST as the lookup reads it: {get(club text, region) -> {partner} | {code, why}}, each row's names keyed
 * once: its club, `<club> - <partner>`, and each of them after its partner and a space (the integration's spaces-only
 * naming of 2026-11-23, `<Partner> <Club Name> <MM-DD-YYYY> <Week>`).
 */
function refileIndex_(list) {
  const byName = new Map();
  for (const r of list) {
    const row = { regionKey: refileKey_(r.region === undefined ? '' : r.region), partner: r.partner, partnerKey: refileKey_(r.partner) };
    const names = [r.club, r.club + REFILE_NAME_SEP + r.partner];
    for (const name of names.concat(names.map(n => r.partner + ' ' + n))) {
      const k = refileKey_(name);
      if (!byName.has(k)) byName.set(k, []);
      if (byName.get(k).indexOf(row) < 0) byName.get(k).push(row);
    }
  }
  return {
    get: (club, region) => {
      const shown = club.split(/\s+/).filter(Boolean).join(' ');
      const all = byName.get(refileKey_(club)) || [], regionKey = refileKey_(region);
      const own = all.filter(row => row.regionKey === regionKey);
      const partners = [], seen = new Set();
      for (const row of own.length ? own : all) {
        if (seen.has(row.partnerKey)) continue;
        seen.add(row.partnerKey);
        partners.push(row.partner);
      }
      if (partners.length === 1) return { partner: partners[0] };
      if (!partners.length) {
        return { code: 'no-partner', why: 'no club "' + shown + '" in REFILE_LIST (by its name or `<club> - <partner>`, either ' +
                                          'with its partner before it)' };
      }
      return { code: 'ambiguous', why: 'the club "' + shown + '" has ' + partners.length + ' partners in REFILE_LIST: ' +
                                       partners.join(', ') };
    },
  };
}

function planRefile_(regions, list) {
  const plan = { refile: [], stays: [] };
  const index = refileIndex_(list);
  for (const region of Object.keys(regions)) {
    const r = regions[region];
    const roots = r.folders || [];
    const stay = (f, code, why) => plan.stays.push({ region: region, id: f.id, name: f.name, code: code, why: why });
    const holding = roots.filter(f => (f.folders || []).length > 0);
    const others = roots.filter(f => !(f.folders || []).length);
    const target = new Map();   // folder id -> {path} | {code, why}
    for (const f of others) {
      const said = refileName_(f.name);
      if (said.path || said.code) {
        target.set(f.id, said);
        continue;
      }
      const found = index.get(said.club, region);
      target.set(f.id, found.partner ? { path: [found.partner, said.month] } : found);
    }
    const targeted = new Set(others.map(f => target.get(f.id)).filter(t => t.path).map(t => t.path[0]));
    // an empty folder named like a partner this run files into is that partner folder (a cut-short run left it)
    const emptyPartners = others.filter(f => f.files === 0 && targeted.has(f.name));
    const photos = others.filter(f => emptyPartners.indexOf(f) < 0);
    const named = new Map();
    for (const f of photos) named.set(f.name, (named.get(f.name) || 0) + 1);
    const partnerNamed = new Set(photos.map(f => f.name).filter(n => targeted.has(n)));
    const partnerFolders = holding.concat(emptyPartners);
    for (const f of holding) {
      stay(f, 'holds-folders', 'it holds ' + f.folders.length + ' folder(s): a partner folder, or not a photo folder; never moved');
    }
    for (const f of emptyPartners) {
      stay(f, 'holds-folders', 'empty, and named like a partner this run files into: it is that partner folder; never moved');
    }
    for (const f of photos) {
      const t = target.get(f.id);
      if (named.get(f.name) > 1) {
        stay(f, 'duplicate-name', named.get(f.name) + ' folders of this name in the region folder; merge or rename them by hand');
        continue;
      }
      if (partnerNamed.has(f.name)) {
        stay(f, 'partner-name', 'named like the partner "' + f.name + '" this run files into: it and that partner\'s folders stay; ' +
                                'rename or move it by hand');
        continue;
      }
      if (t.code) {
        stay(f, t.code, t.why);
        continue;
      }
      const partner = t.path[0], month = t.path[1];
      if (partnerNamed.has(partner)) {
        stay(f, 'partner-name', 'a folder of files in the region folder is named "' + partner + '", like its partner folder; ' +
                                'rename or move that one by hand');
        continue;
      }
      const pfs = partnerFolders.filter(d => d.name === partner);
      if (pfs.length > 1) {
        stay(f, 'partner-folders', pfs.length + ' folders named "' + partner + '" in the region folder; merge them by hand');
        continue;
      }
      const pf = pfs.length ? pfs[0] : null;
      const mfs = pf ? (pf.folders || []).filter(d => d.name === month) : [];
      if (mfs.length > 1) {
        stay(f, 'month-folders', mfs.length + ' folders named "' + month + '" in "' + partner + '"; merge them by hand');
        continue;
      }
      const mf = mfs.length ? mfs[0] : null;
      if (mf && (mf.folders || []).some(d => d.name === f.name)) {
        stay(f, 'exists', 'a folder of this name is already in ' + region + '/' + partner + '/' + month + '; merge them by hand');
        continue;
      }
      plan.refile.push({ region: region, id: f.id, name: f.name, path: [partner, month], to: r.id,
                         partnerId: pf ? pf.id : null, monthId: mf ? mf.id : null });
    }
  }
  return plan;
}

/** A region's plan: a count line, then each folder directly in the region folder by name (never a file's). */
function logRefileRegion_(region, plan, apply) {
  const verb = apply ? '' : 'would ';
  const byName = (a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0);
  const refile = plan.refile.filter(e => e.region === region).sort(byName);
  const stays = plan.stays.filter(e => e.region === region).sort(byName);
  const codes = {};
  for (const s of stays) codes[s.code] = (codes[s.code] || 0) + 1;
  const tally = Object.keys(codes).sort().map(c => c + ' ' + codes[c]).join(', ');
  console.log(region + ': ' + verb + 'refile ' + refile.length + ', stays ' + stays.length + (tally ? ' (' + tally + ')' : ''));
  for (const e of refile) {
    const made = (e.partnerId ? [] : ['partner']).concat(e.monthId ? [] : ['month']);
    console.log('  ' + verb + 'refile "' + e.name + '" to ' + region + '/' + e.path.join('/') +
                (made.length ? ' (' + verb + 'make its ' + made.join(' and ') + ' folder' + (made.length > 1 ? 's)' : ')') : ''));
  }
  for (const s of stays) console.log('  stays "' + s.name + '": ' + s.code + ': ' + s.why);
}

/**
 * The kept moves of the region folder `c` (s.m, in plan order) until `run.deadline` (checked before each folder, and
 * after its re-check, before its partner folder is found or made); each one done, skipped or failed leaves s.m. Each:
 * read by id, still a live folder of its name (its hash) whose one parent is the region folder, or skipped; its partner
 * and month folders (refileFolderIn_); one Files.update moving it; a read-back (REFILE_FAILED unless in the month folder).
 */
function moveRefile_(c, s, run) {
  let i = 0;
  for (; i < s.m.length; i++) {
    if (Date.now() > run.deadline) break;
    const id = s.m[i][0], d = s.d[s.m[i][2]];
    let where = c.region + ' folder ' + id;
    try {
      if (run.never.has(id) || !run.never.has(c.target)) throw new Error('refused: a configured folder or the Shared Drive\'s root');
      const now = Drive.Files.get(id, { fields: 'id, name, mimeType, trashed, parents', supportsAllDrives: true });
      if (now && typeof now.name === 'string') where = c.region + ' "' + now.name + '"';
      if (!now || now.mimeType !== FOLDER_MIME || now.trashed !== false || refileHash_(now.name) !== s.m[i][1] ||
          oneParent_(now) !== c.target) {
        run.skipped.push('  skipped ' + where + ': moved or trashed (or renamed) since the read; the next cycle looks again');
        continue;
      }
      if (Date.now() > run.deadline) break;
      const partnerId = refileFolderIn_(c.target, d[0], d[2], run);
      const monthId = refileFolderIn_(partnerId, d[1], d[3], run);
      Drive.Files.update({}, id, null, { addParents: monthId, removeParents: c.target, supportsAllDrives: true });
      const back = Drive.Files.get(id, { fields: 'parents, trashed', supportsAllDrives: true });
      if (!back || back.trashed !== false || oneParent_(back) !== monthId) {
        run.failed.push('REFILE_FAILED ' + where + ': Drive answered the move but the read-back does not show it in ' + c.region + '/' +
                        d[0] + '/' + d[1] + '; look for it by hand');
        continue;
      }
      run.moved++;
    } catch (err) {
      run.failed.push('REFILE_FAILED ' + where + ': ' + errorText_(err));
    }
  }
  s.m = s.m.slice(i);
}

/**
 * The id of the live folder `name` directly in `parent` a move goes into, once per run each (run.folders): the plan's
 * `kept` id when Drive still shows it so (a live folder of that name whose one parent is `parent`), else the one folder
 * of that name a listing there finds (the mover may have made it since the read), else one made now (Drive.Files.create,
 * supportsAllDrives). Two or more of that name, or one Drive did not confirm: throws, for every move into it this run.
 */
function refileFolderIn_(parent, name, kept, run) {
  const k = JSON.stringify([parent, name]);
  if (!run.folders.has(k)) {
    let got;
    try {
      let now = null;
      try {
        now = kept ? Drive.Files.get(kept, { fields: 'id, name, mimeType, trashed, parents', supportsAllDrives: true }) : null;
      } catch (e) {
        now = null;   // gone since the read: looked up by name
      }
      if (now && now.mimeType === FOLDER_MIME && now.trashed === false && now.name === name && oneParent_(now) === parent) {
        got = { id: kept };
      } else {
        const q = "'" + parent + "' in parents and name = '" + String(name).replace(/\\/g, '\\\\').replace(/'/g, "\\'") +
          "' and mimeType = '" + FOLDER_MIME + "' and trashed = false";
        const found = listSharedDrive_(run.driveId, q, 'id, name', Infinity).files.filter(f => f.name === name);
        if (found.length > 1) throw new Error(found.length + ' folders of that name there since the read; merge them by hand');
        if (found.length) {
          got = { id: found[0].id };
        } else {
          const made = Drive.Files.create({ name: name, mimeType: FOLDER_MIME, parents: [parent] }, null, { supportsAllDrives: true });
          if (!made || !made.id) throw new Error('Drive did not confirm it');
          run.made++;
          got = { id: made.id };
        }
      }
    } catch (e) {
      got = { error: errorText_(e) };
    }
    run.folders.set(k, got);
  }
  const got = run.folders.get(k);
  if (got.error) throw new Error('the folder "' + name + '": ' + got.error);
  return got.id;
}
