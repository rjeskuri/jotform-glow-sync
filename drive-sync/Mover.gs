/**
 * The photo mover's entry points (ticket #89, docs/plans/2026-10-21-drive-photo-mover.md).
 * A standalone project owned by Ryan's company account, NOT the sheet's Apps Script
 * (appsscript/): a Drive scope there would stop its form-submit trigger until re-authorised
 * (CLAUDE.md rule 11). Setup and stopping it: drive-sync/README.md; RUNBOOK "Photo mover".
 *
 *   previewMoves        the dry run: reads both drives, logs the plan, changes nothing
 *   moveSettledPhotos   the real run (the trigger's handler): the same plan, then carried out
 *   installTrigger      every 15 minutes, moveSettledPhotos (once; a second install does nothing)
 *   removeTrigger       deletes that trigger: the mover stops
 *
 * Script Properties (Project Settings → Script Properties), one pair per region in use:
 *   SOURCE_FOLDER_<KEY>   the id of `Attendance photos - <Region>` in Ryan's My Drive
 *   TARGET_FOLDER_<KEY>   the id of that region's folder on the Shared Drive
 * with <KEY> AFRICA, ASIA, LATIN_AMERICA, US, TEMPLATE. A region with neither is skipped; one of
 * a pair alone, an id used twice, or no pair at all is refused before anything is opened; a
 * source folder not named exactly `Attendance photos - <Region>`, or a target folder not named
 * exactly `<Region>`, is refused before any subfolder is read.
 *
 * A run reads for at most half its time budget, then moves for the rest (TIME_BUDGET either way:
 * what was not read or not moved waits for the next run).
 *
 * Drive cannot move a folder from My Drive into a Shared Drive (#132: 403
 * teamDrivesFolderMoveInNotSupported, and DriveApp's moveTo fails the same way), so a move makes
 * a folder of the subfolder's name in the region folder and moves the plan's files into it, one
 * by one, through the advanced Drive service (Drive.Files.create / Drive.Files.update with
 * supportsAllDrives); a merge moves them the same way into the folder already there. The
 * emptied subfolder stays in My Drive (nothing is ever trashed); a move cut short by a failure
 * or the time budget is finished by a later run as a merge.
 *
 * The log holds counts and folder names (`<Club Name> <Attendance Date>`), never a file's name
 * or contents. Nothing here shares, links, copies, trashes or e-mails anything: a file only
 * ever moves (its parent changes), and a move never replaces a file.
 */

const SETTLE_MINUTES = 10;
const TRIGGER_MINUTES = 15;
const TRIGGER_HANDLER = 'moveSettledPhotos';
const RUN_BUDGET_MS = 4.5 * 60 * 1000;   // Apps Script stops a run at 6 minutes; the rest waits for the next
const REGION_KEYS = { 'Africa': 'AFRICA', 'Asia': 'ASIA', 'Latin America': 'LATIN_AMERICA', 'U.S': 'US',
                      'Template': 'TEMPLATE' };
const FOLDER_MIME = 'application/vnd.google-apps.folder';

function previewMoves() {
  runMover_(false);
}

function moveSettledPhotos() {
  runMover_(true);
}

function installTrigger() {
  readMoverConfig_();
  const existing = ScriptApp.getProjectTriggers().filter(t => t.getHandlerFunction() === TRIGGER_HANDLER);
  if (existing.length) {
    console.log('installTrigger: already installed (' + existing.length + '), nothing changed');
    return;
  }
  ScriptApp.newTrigger('moveSettledPhotos').timeBased().everyMinutes(TRIGGER_MINUTES).create();
  console.log('installTrigger: moveSettledPhotos every ' + TRIGGER_MINUTES + ' minutes');
}

function removeTrigger() {
  let removed = 0;
  for (const t of ScriptApp.getProjectTriggers()) {
    if (t.getHandlerFunction() !== TRIGGER_HANDLER) continue;
    ScriptApp.deleteTrigger(t);
    removed++;
  }
  console.log('removeTrigger: ' + removed + ' trigger(s) deleted; the mover is stopped');
}

/** [{region, source, target}] from Script Properties; throws, before any folder is opened, when unusable. */
function readMoverConfig_() {
  const props = PropertiesService.getScriptProperties();
  const regions = [], problems = [], seen = {};
  for (const region of PHOTO_REGIONS) {
    const key = REGION_KEYS[region];
    const sourceName = 'SOURCE_FOLDER_' + key, targetName = 'TARGET_FOLDER_' + key;
    const source = props.getProperty(sourceName), target = props.getProperty(targetName);
    if (!source && !target) continue;
    if (!source || !target) {
      problems.push((source ? targetName : sourceName) + ' is not set (' + (source ? sourceName : targetName) +
                    ' is): set both or neither');
      continue;
    }
    for (const pair of [[sourceName, source], [targetName, target]]) {
      if (Object.prototype.hasOwnProperty.call(seen, pair[1])) problems.push(pair[0] + ' has the same id as ' + seen[pair[1]]);
      else seen[pair[1]] = pair[0];
    }
    regions.push({ region: region, source: source, target: target });
  }
  if (!regions.length && !problems.length) {
    problems.push('no region is set up: add SOURCE_FOLDER_<KEY> and TARGET_FOLDER_<KEY> for at least one of ' +
                  PHOTO_REGIONS.map(r => REGION_KEYS[r]).join(', '));
  }
  if (problems.length) {
    throw new Error('CONFIG refused, Script Properties (drive-sync/README.md): ' + problems.join('; '));
  }
  return regions;
}

/** Read both drives, plan, log; with `apply`, carry the plan out. One run at a time (the script lock). */
function runMover_(apply) {
  const started = Date.now();
  const config = readMoverConfig_();
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10 * 1000)) {
    console.log('LOCKED: another run is still going; this one did nothing');
    return;
  }
  try {
    const opened = openRegionFolders_(config);
    const read = readDrives_(opened, started + RUN_BUDGET_MS / 2);
    const plan = planMoves_(read.sources, read.targets, new Date(), SETTLE_MINUTES);
    logPlan_(plan, config, apply);
    if (apply) carryOut_(plan, started + RUN_BUDGET_MS);
  } finally {
    lock.releaseLock();
  }
}

/**
 * [{region, source, target}] as Folders, every name checked before any subfolder is read: the
 * source exactly `Attendance photos - <Region>`, the target exactly `<Region>`.
 */
function openRegionFolders_(config) {
  const opened = config.map(c => ({ region: c.region, source: DriveApp.getFolderById(c.source),
                                    target: DriveApp.getFolderById(c.target) }));
  const problems = [];
  for (const o of opened) {
    const key = REGION_KEYS[o.region];
    if (o.source.getName() !== PHOTO_PREFIX + o.region) {
      problems.push('SOURCE_FOLDER_' + key + ' is a folder named "' + o.source.getName() + '", not "' +
                    PHOTO_PREFIX + o.region + '"');
    }
    if (o.target.getName() !== o.region) {
      problems.push('TARGET_FOLDER_' + key + ' is a folder named "' + o.target.getName() + '", not "' + o.region + '"');
    }
  }
  if (problems.length) throw new Error('CONFIG refused: ' + problems.join('; '));
  return opened;
}

/**
 * The planner's inputs: per region the source subfolders with their files, and beside each one
 * the target's subfolders of the same name (all the planner compares with), so a subfolder read
 * always has its target side read too. Past `readBy` no further subfolder is read
 * (TIME_BUDGET): what was not read is not in the plan, and waits for the next run.
 */
function readDrives_(opened, readBy) {
  const sources = [], targets = {};
  let stopped = false, count = 0;
  for (const o of opened) {
    const source = { id: o.source.getId(), name: o.source.getName(), subfolders: [] };
    const target = { id: o.target.getId(), subfolders: [] };
    sources.push(source);
    targets[o.region] = target;
    const looked = {};
    const it = stopped ? null : o.source.getFolders();
    while (it && it.hasNext()) {
      if (Date.now() > readBy) {
        stopped = true;
        break;
      }
      const sub = it.next();
      if (sub.isTrashed()) continue;
      const name = sub.getName();
      source.subfolders.push({ id: sub.getId(), name: name, files: describeFiles_(sub, true) });
      count++;
      if (Object.prototype.hasOwnProperty.call(looked, name)) continue;
      looked[name] = true;
      const same = o.target.getFoldersByName(name);
      while (same.hasNext()) {
        const t = same.next();
        if (t.isTrashed()) continue;
        target.subfolders.push({ id: t.getId(), name: t.getName(), files: describeFiles_(t, false) });
      }
    }
  }
  if (stopped) console.log('TIME_BUDGET: reading stopped after ' + count + ' subfolder(s); the rest waits for the next run');
  return { sources: sources, targets: targets };
}

function describeFiles_(folder, withDates) {
  const files = [];
  const it = folder.getFiles();
  while (it.hasNext()) {
    const f = it.next();
    if (f.isTrashed()) continue;
    const entry = { id: f.getId(), name: f.getName(), size: f.getSize() };
    if (withDates) entry.updated = f.getLastUpdated();
    files.push(entry);
  }
  return files;
}

/** Per region: one count line, then a line per subfolder by name. No file names. */
function logPlan_(plan, config, apply) {
  const verb = apply ? '' : 'would ';
  console.log((apply ? 'RUN' : 'DRY RUN (nothing changes)') + ': regions ' + config.map(c => c.region).join(', ') +
              '; settle ' + SETTLE_MINUTES + ' min');
  for (const c of config) {
    const of = list => list.filter(e => e.region === c.region);
    const moves = of(plan.moves), merges = of(plan.merges), waiting = of(plan.waiting), refused = of(plan.refused);
    const filesIn = merges.reduce((n, m) => n + m.files.length, 0), kept = merges.reduce((n, m) => n + m.kept.length, 0);
    console.log(c.region + ': ' + verb + 'move ' + moves.length + ', ' + verb + 'merge ' + merges.length +
                ' (' + filesIn + ' file(s) in, ' + kept + ' kept), waiting ' + waiting.length +
                ', refused ' + refused.length);
    for (const m of moves) console.log('  ' + verb + 'move "' + m.name + '"');
    for (const m of merges) {
      console.log('  ' + verb + 'merge "' + m.name + '": ' + m.files.length + ' file(s) in, ' + m.kept.length +
                  ' kept in My Drive (same name and size already on the Shared Drive)');
    }
    for (const w of waiting) console.log('  waiting "' + w.name + '"');
    for (const r of refused) {
      console.log('  REFUSED "' + r.name + '": two or more folders of this name on the Shared Drive; move it by hand');
    }
  }
  for (const u of plan.unknown) console.log('UNKNOWN "' + u.name + '": no such region or no target; left alone');
}

/**
 * Moves first, then merges, until the time budget (checked before the folder is made and before
 * each file). A move: a folder of the subfolder's name made in the region folder, then the plan's
 * files into it (only those: the subfolder is never listed again); when the folder cannot be
 * made, none of its files moves. Every failure is logged by code, region and folder name, the
 * rest of the run goes on, then one error. A move whose folder was made but whose files did not
 * all move is a merge on the next run.
 */
function carryOut_(plan, deadline) {
  const failed = [];
  let deferred = 0, moved = 0, filesMoved = 0, filesMerged = 0;
  const late = () => Date.now() > deadline;
  for (const m of plan.moves) {
    if (late()) { deferred++; continue; }
    let made;
    try {
      made = Drive.Files.create({ name: m.name, mimeType: FOLDER_MIME, parents: [m.to] }, null, { supportsAllDrives: true });
    } catch (e) {
      failed.push('MOVE_FAILED ' + m.region + ' "' + m.name + '": no folder made, its files stay: ' + errorText_(e));
      continue;
    }
    const r = moveFiles_(m, made.id, 'MOVE_FAILED', late, failed);
    filesMoved += r.moved;
    if (r.deferred) deferred++;
    else if (!r.failed) moved++;
  }
  for (const m of plan.merges) {
    if (!m.files.length) continue;
    if (late()) { deferred++; continue; }
    const r = moveFiles_(m, m.into, 'MERGE_FAILED', late, failed);
    filesMerged += r.moved;
    if (r.deferred) deferred++;
  }
  console.log('done: ' + moved + ' folder(s) moved (' + filesMoved + ' file(s)), ' + filesMerged + ' file(s) merged, ' +
              failed.length + ' failure(s)' +
              (deferred ? ', ' + deferred + ' folder(s) left for the next run (TIME_BUDGET)' : ''));
  for (const f of failed) console.log(f);
  if (failed.length) throw new Error(failed.length + ' move(s) failed: ' + failed[0]);
}

/**
 * The plan entry's files (ids), each into the folder `into` by one Drive.Files.update, until
 * `late()`: {moved, failed, deferred}; a failure is pushed to `failed` as `<code> <region>
 * "<folder name>": <error>` (never a file's name) and the next file is still tried.
 */
function moveFiles_(entry, into, code, late, failed) {
  const r = { moved: 0, failed: 0, deferred: false };
  for (const fileId of entry.files) {
    if (late()) { r.deferred = true; break; }
    try {
      Drive.Files.update({}, fileId, null, { addParents: into, removeParents: entry.id, supportsAllDrives: true });
      r.moved++;
    } catch (e) {
      failed.push(code + ' ' + entry.region + ' "' + entry.name + '": ' + errorText_(e));
      r.failed++;
    }
  }
  return r;
}

function errorText_(e) {
  return String(e && e.message || e).slice(0, 200);
}
