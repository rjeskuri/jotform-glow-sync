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
 * a pair alone, an id used twice, or no pair at all is refused before anything is opened.
 *
 * The log holds counts and folder names (`<Club Name> <Attendance Date>`), never a file's name
 * or contents. Nothing here shares, links, copies, trashes or e-mails anything: a file only
 * ever moves (Folder.moveTo / File.moveTo), and a move never replaces a file.
 */

const SETTLE_MINUTES = 10;
const TRIGGER_MINUTES = 15;
const TRIGGER_HANDLER = 'moveSettledPhotos';
const RUN_BUDGET_MS = 4.5 * 60 * 1000;   // Apps Script stops a run at 6 minutes; the rest waits for the next
const REGION_KEYS = { 'Africa': 'AFRICA', 'Asia': 'ASIA', 'Latin America': 'LATIN_AMERICA', 'U.S': 'US',
                      'Template': 'TEMPLATE' };

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
    const folders = {};   // id -> Folder, every folder the plan can name
    const sources = [], targets = {};
    for (const c of config) {
      const source = DriveApp.getFolderById(c.source);
      const target = DriveApp.getFolderById(c.target);
      if (source.getName() !== PHOTO_PREFIX + c.region) {
        throw new Error('CONFIG refused: SOURCE_FOLDER_' + REGION_KEYS[c.region] + ' is a folder named "' +
                        source.getName() + '", not "' + PHOTO_PREFIX + c.region + '"');
      }
      const described = describeSource_(source, folders);
      sources.push(described);
      folders[target.getId()] = target;
      targets[c.region] = describeTarget_(target, described.subfolders.map(s => s.name), folders);
    }
    const plan = planMoves_(sources, targets, new Date(), SETTLE_MINUTES);
    logPlan_(plan, config, apply);
    if (apply) carryOut_(plan, folders, started + RUN_BUDGET_MS);
  } finally {
    lock.releaseLock();
  }
}

/** {id, name, subfolders: [{id, name, files: [{id, name, size, updated}]}]}; trashed items left out. */
function describeSource_(folder, folders) {
  const subfolders = [];
  const it = folder.getFolders();
  while (it.hasNext()) {
    const sub = it.next();
    if (sub.isTrashed()) continue;
    folders[sub.getId()] = sub;
    subfolders.push({ id: sub.getId(), name: sub.getName(), files: describeFiles_(sub, true) });
  }
  return { id: folder.getId(), name: folder.getName(), subfolders: subfolders };
}

/** {id, subfolders}: only the subfolders named like one of `names` (all the planner compares with). */
function describeTarget_(folder, names, folders) {
  const subfolders = [], done = {};
  for (const name of names) {
    if (Object.prototype.hasOwnProperty.call(done, name)) continue;
    done[name] = true;
    const it = folder.getFoldersByName(name);
    while (it.hasNext()) {
      const sub = it.next();
      if (sub.isTrashed()) continue;
      folders[sub.getId()] = sub;
      subfolders.push({ id: sub.getId(), name: sub.getName(), files: describeFiles_(sub, false) });
    }
  }
  return { id: folder.getId(), subfolders: subfolders };
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

/** Moves first, then merges, until the time budget; every failure logged by code, then one error. */
function carryOut_(plan, folders, deadline) {
  const failed = [];
  let deferred = 0, moved = 0, filesMoved = 0;
  const late = () => Date.now() > deadline;
  for (const m of plan.moves) {
    if (late()) { deferred++; continue; }
    try {
      folders[m.id].moveTo(folders[m.to]);
      moved++;
    } catch (e) {
      failed.push('MOVE_FAILED ' + m.region + ' "' + m.name + '": ' + errorText_(e));
    }
  }
  for (const m of plan.merges) {
    for (const fileId of m.files) {
      if (late()) { deferred++; continue; }
      try {
        DriveApp.getFileById(fileId).moveTo(folders[m.into]);
        filesMoved++;
      } catch (e) {
        failed.push('MERGE_FAILED ' + m.region + ' "' + m.name + '": ' + errorText_(e));
      }
    }
  }
  console.log('done: ' + moved + ' folder(s) moved, ' + filesMoved + ' file(s) merged, ' + failed.length +
              ' failure(s)' + (deferred ? ', ' + deferred + ' left for the next run (TIME_BUDGET)' : ''));
  for (const f of failed) console.log(f);
  if (failed.length) throw new Error(failed.length + ' move(s) failed: ' + failed[0]);
}

function errorText_(e) {
  return String(e && e.message || e).slice(0, 200);
}
