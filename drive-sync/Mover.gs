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
 *   RETENTION_DAYS        (#182, epic #179, docs/plans/2026-10-30-photo-retention.md) the Shared
 *                         Drive's photo retention: absent or blank, off (`retention off`); a whole
 *                         number of at least 90 (spaces trimmed), on; anything else is refused
 *                         before anything is opened. With it on, every target folder must be on one
 *                         Shared Drive, none in the trash and none that drive's root, or the run is
 *                         refused before any move.
 *
 * A run reads for at most half its time budget, then moves for the rest (TIME_BUDGET either way:
 * what was not read or not moved waits for the next run). With retention on, both entry points
 * then read that Shared Drive, inside the same budget, plan with Plan.gs planTrash_ and log what
 * it would trash, per region: counts, and the names of the region folders' direct subfolders only
 * (ruling R14). A retention read that fails is RETENTION_FAILED: nothing previewed or trashed, the
 * moves done as ever, and the run ends with an error after them. The dry run changes nothing on the
 * Shared Drive; the real run then trashes that plan (#185, trashRetention_): the due photos, at most
 * 100 a run, then the emptied folders below the region folders, children first, each re-checked
 * just before its trash and sent through moveToTrash_. Never a region folder, the Shared Drive's
 * root, anything outside the region folders, a photo before its due moment or a folder with
 * anything left in it.
 *
 * Drive cannot move a folder from My Drive into a Shared Drive (#132: 403
 * teamDrivesFolderMoveInNotSupported, and DriveApp's moveTo fails the same way), so a move makes
 * a folder of the subfolder's name in the region folder and moves the plan's files into it, one
 * by one, through the advanced Drive service (Drive.Files.create / Drive.Files.update with
 * supportsAllDrives); a merge moves them the same way into the folder already there. A move cut
 * short by a failure or the time budget is finished by a later run as a merge.
 *
 * Where (#225, docs/plans/2026-11-19-photo-folders-partner-month.md): a subfolder named
 * `<Partner> | <Club Name> | <MM-DD-YYYY> | <Week>` goes in `<Partner>/<YYYY-MM>` under the region
 * folder (Plan.gs photoPath_), any other name directly in the region folder as before. The partner
 * and month folders are found by name (one in Drive's trash does not count) and reused, or made
 * by Drive.Files.create (supportsAllDrives) by the real run when missing, once per run; two of one
 * name at a level: that subfolder is REFUSED, logged with the reason, and nothing of it moves.
 * The dry run makes nothing and logs each subfolder's target path. Nothing is ever renamed.
 *
 * What it trashes in My Drive (#144), and only on the real run: an emptied source subfolder, once
 * it holds no file and no subfolder and has not changed for SETTLE_MINUTES (Plan.gs `remove`),
 * re-read and re-listed just before, to Drive's trash (restorable for 30 days), through
 * moveToTrash_, the one trash, which refuses a configured folder and the Shared Drive's root
 * whatever its caller says. Never a file there, a folder with anything in it, a source folder
 * itself; on the Shared Drive only retention's plan (above); nowhere a permanent delete or an
 * emptied trash. The rescue: a photo Jotform writes into a subfolder the
 * mover had trashed is in the trash through its folder; each run lists the source folders'
 * subfolders in the trash (the advanced Drive service, `trashed = true` stated), and moves such a
 * photo like any other, out of the trash in the same Files.update ({trashed: false}), then re-reads
 * it (RESCUE_FAILED when it is still in the trash or not where it was sent). A file a person
 * trashed is left alone.
 *
 * The log holds counts and folder names (the submission subfolders', their partner and month
 * folders'; for retention only the region folders' direct subfolders), never a file's name or
 * contents. Nothing here shares,
 * links, copies or e-mails anything: a file only ever moves (its parent changes, and out of the
 * trash when the rescue finds it there) or, on the Shared Drive once due, goes to its trash; a
 * move never replaces a file.
 */

const SETTLE_MINUTES = 10;
const TRIGGER_MINUTES = 15;
const TRIGGER_HANDLER = 'moveSettledPhotos';
const RUN_BUDGET_MS = 4.5 * 60 * 1000;   // Apps Script stops a run at 6 minutes; the rest waits for the next
const REGION_KEYS = { 'Africa': 'AFRICA', 'Asia': 'ASIA', 'Latin America': 'LATIN_AMERICA', 'U.S': 'US',
                      'Template': 'TEMPLATE' };
const FOLDER_MIME = 'application/vnd.google-apps.folder';
const BIN_BATCH = 20;   // subfolders in the trash whose files one Drive query lists (#144, the rescue)
const RETENTION_MAX_FILES = 100;   // due files planned per run, earliest due first (ruling R6); the rest: RETENTION_CAP
const RETENTION_PAGE_SIZE = 1000;  // Drive's largest Files.list page

function previewMoves() {
  runMover_(false);
}

function moveSettledPhotos() {
  runMover_(true);
}

function installTrigger() {
  readMoverConfig_();
  readRetentionDays_();
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

/**
 * The Script Property RETENTION_DAYS (#182, ruling R4): null when absent or blank (retention off), else a whole number
 * of at least RETENTION_MIN_DAYS, spaces trimmed; anything else throws, before any folder is opened.
 */
function readRetentionDays_() {
  const raw = PropertiesService.getScriptProperties().getProperty('RETENTION_DAYS');
  const text = raw === null || raw === undefined ? '' : String(raw).trim();
  if (!text) return null;
  const days = /^\d+$/.test(text) ? Number(text) : NaN;
  if (!Number.isSafeInteger(days) || days < RETENTION_MIN_DAYS) {
    throw new Error('CONFIG refused, Script Properties (drive-sync/README.md): RETENTION_DAYS is "' + text.slice(0, 40) +
                    '", not a whole number of days of at least ' + RETENTION_MIN_DAYS + ' (delete it to turn retention off)');
  }
  return days;
}

/**
 * Read both drives, plan, log; with `apply`, carry the plan out. With RETENTION_DAYS set, then the retention preview
 * (#182), after the moves even when one failed (ruling R7), and with `apply` the trash of its plan (#185); a failure of
 * any of them ends the run with an error that names each, after all. One run at a time (the script lock).
 */
function runMover_(apply) {
  const started = Date.now();
  const config = readMoverConfig_();
  const days = readRetentionDays_();
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10 * 1000)) {
    console.log('LOCKED: another run is still going; this one did nothing');
    return;
  }
  try {
    const opened = openRegionFolders_(config);
    const driveId = days === null ? null : sharedDriveOf_(config);
    const protect = apply ? protectedIds_(config) : null;
    const read = readDrives_(opened, started + RUN_BUDGET_MS / 2);
    const plan = holdRefusedPaths_(planMoves_(read.sources, read.targets, new Date(), SETTLE_MINUTES), read.levels);
    logPlan_(plan, config, apply, read.inTrash);
    if (days === null) console.log('retention off (RETENTION_DAYS not set)');
    let moveError = null;
    const movedInto = [];   // #191: the Shared Drive folders carryOut_ made or merged files into, kept even when it throws
    if (apply) {
      try {
        carryOut_(plan, started + RUN_BUDGET_MS, read, protect, movedInto);
      } catch (e) {
        moveError = e;
      }
    }
    const retention = days === null ? null : previewRetention_(config, driveId, days, started + RUN_BUDGET_MS, apply);
    const failures = retention && retention.failure ? [retention.failure] : [];
    if (apply && retention && retention.planned) {
      const trashFailure = trashRetention_(retention.planned, config, driveId, started + RUN_BUDGET_MS, protect, movedInto);
      if (trashFailure) failures.push(trashFailure);
    }
    if (moveError) throw failures.length ? new Error(errorText_(moveError) + '; ' + failures.join('; ')) : moveError;
    if (failures.length) throw new Error(failures.join('; '));
  } finally {
    lock.releaseLock();
  }
}

/**
 * With retention on (#182, ruling R5): the id of the one Shared Drive every target folder is on, read by
 * Drive.Files.get. Each must report a driveId, all the same one, not be in the trash, and not be that drive's root
 * (its id is the drive's: the root holds everything, a region folder never may); otherwise CONFIG refused, before
 * any move.
 */
function sharedDriveOf_(config) {
  const problems = [];
  let driveId = null, firstName = '';
  for (const c of config) {
    const name = 'TARGET_FOLDER_' + REGION_KEYS[c.region];
    const got = Drive.Files.get(c.target, { fields: 'id, driveId, trashed', supportsAllDrives: true });
    if (!got || !got.driveId) {
      problems.push(name + ' is not on a Shared Drive');
      continue;
    }
    if (got.driveId === c.target) problems.push(name + ' is the Shared Drive itself (its root), not a region folder on it');
    if (got.trashed !== false) problems.push(name + ' is in the trash');
    if (driveId === null) {
      driveId = got.driveId;
      firstName = name;
    } else if (got.driveId !== driveId) {
      problems.push(name + ' is on another Shared Drive than ' + firstName);
    }
  }
  if (problems.length) {
    throw new Error('CONFIG refused, RETENTION_DAYS is set and needs every target folder on one Shared Drive: ' +
                    problems.join('; '));
  }
  return driveId;
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
 * The planner's inputs: per region the source subfolders, live and in the trash, with their
 * files, and beside each one with files the target's subfolders of the same name at its path
 * (Plan.gs photoPath_: directly in the region folder, or in its <Partner>/<YYYY-MM> folders, #225;
 * all the planner compares with), so a subfolder read always has its target side read too. The
 * partner and month folders are read by name once per run each, those in the trash left out, into
 * `levels` (readPath_); below a missing one nothing is read, below two of one name nothing either
 * (refused). A live subfolder is
 * read through DriveApp (its files, its own subfolders, when it last changed); the subfolders in
 * the trash and their files through the advanced Drive service, `trashed = true` stated (#144,
 * the rescue). An emptied subfolder (no files: what a move left behind) costs its one listing and
 * nothing more. Past `readBy` no further subfolder is read (TIME_BUDGET): what was not read is not
 * in the plan, and waits for the next run. Also returned: inTrash {subfolder id: true},
 * sourceIds {region: source folder id} and levels {region: readPath_'s levels}.
 */
function readDrives_(opened, readBy) {
  const sources = [], targets = {}, inTrash = {}, sourceIds = {}, levels = {};
  let stopped = false, count = 0;
  const outOfTime = () => {
    if (Date.now() > readBy) stopped = true;
    return stopped;
  };
  for (const o of opened) {
    const source = { id: o.source.getId(), name: o.source.getName(), subfolders: [] };
    const target = { id: o.target.getId(), subfolders: [] };
    sources.push(source);
    targets[o.region] = target;
    sourceIds[o.region] = source.id;
    levels[o.region] = {};
    if (stopped) continue;
    const looked = {}, seen = {};
    const add = sub => {
      source.subfolders.push(sub);
      seen[sub.id] = true;
      count++;
      if (!sub.files.length || Object.prototype.hasOwnProperty.call(looked, sub.name)) return;
      looked[sub.name] = true;
      const path = photoPath_(sub.name);
      const at = readPath_(o.target, path, levels[o.region]);
      if (!at.folder) return;
      for (const t of liveFoldersNamed_(at.folder, sub.name)) {
        target.subfolders.push({ id: t.getId(), name: t.getName(), path: path, files: describeFiles_(t) });
      }
    };
    const it = o.source.getFolders();
    while (it.hasNext() && !outOfTime()) {
      const sub = it.next();
      if (!sub.isTrashed()) add(describeSubfolder_(sub));
    }
    if (stopped) continue;
    const bins = listFiles_("'" + source.id + "' in parents and trashed = true and mimeType = '" + FOLDER_MIME + "'", 'id, name')
      .filter(b => !Object.prototype.hasOwnProperty.call(seen, b.id));
    for (let i = 0; i < bins.length && !outOfTime(); i += BIN_BATCH) {
      const batch = bins.slice(i, i + BIN_BATCH);
      const filesOf = describeBinnedFiles_(batch.map(b => b.id));
      for (const b of batch) {
        inTrash[b.id] = true;
        add({ id: b.id, name: b.name, trashed: true, files: filesOf[b.id] });
      }
    }
  }
  if (stopped) console.log('TIME_BUDGET: reading stopped after ' + count + ' subfolder(s); the rest waits for the next run');
  return { sources: sources, targets: targets, inTrash: inTrash, sourceIds: sourceIds, levels: levels };
}

/** The folders named `name` directly in `folder`, those in Drive's trash left out (DriveApp lists them too). */
function liveFoldersNamed_(folder, name) {
  const live = [];
  const it = folder.getFoldersByName(name);
  while (it.hasNext()) {
    const d = it.next();
    if (!d.isTrashed()) live.push(d);
  }
  return live;
}

/**
 * The folder at `path` ([] or [<Partner>, <YYYY-MM>]) below the region folder `target` (#225),
 * read one level at a time; each level read once per run into `levels` {JSON of the path down to
 * it: {id, folder, refused}}, which the real run then fills in as it makes the missing ones
 * (pathFolderId_). A level of no live folder of that name: id and folder null, and every level
 * below it too, unread; two or more: `refused` says so and nothing below it is read. Returns the
 * last level reached: {folder: null} when missing or refused.
 */
function readPath_(target, path, levels) {
  let at = { id: target.getId(), folder: target, refused: '' };
  for (let k = 0; k < path.length; k++) {
    const key = JSON.stringify(path.slice(0, k + 1));
    if (!Object.prototype.hasOwnProperty.call(levels, key)) {
      const live = at.folder ? liveFoldersNamed_(at.folder, path[k]) : [];
      levels[key] = live.length > 1 ?
        { id: null, folder: null, refused: live.length + ' folders named "' + path[k] + '" in ' +
                                            (k ? '"' + path.slice(0, k).join('/') + '"' : 'the region folder') } :
        { id: live.length ? live[0].getId() : null, folder: live.length ? live[0] : null, refused: '' };
    }
    at = levels[key];
    if (at.refused) return at;
  }
  return at;
}

/** Why the folders of `path` refuse it (two of one name at a level, as read), '' when they do not. */
function pathRefusal_(path, levels) {
  for (let k = 1; k <= path.length; k++) {
    const at = levels[JSON.stringify(path.slice(0, k))];
    if (at && at.refused) return at.refused;
  }
  return '';
}

/**
 * The plan with each move and merge whose path the read refused (pathRefusal_) taken out and put
 * among the refused, with its reason `why`: nothing of that subfolder moves this run (#225).
 */
function holdRefusedPaths_(plan, levels) {
  const why = e => (e.path && e.path.length && levels[e.region] ? pathRefusal_(e.path, levels[e.region]) : '');
  const held = plan.moves.concat(plan.merges).filter(e => why(e))
    .map(e => ({ region: e.region, id: e.id, name: e.name, path: e.path, why: why(e) }));
  if (!held.length) return plan;
  const ids = new Set(held.map(e => e.id));
  return Object.assign({}, plan, { moves: plan.moves.filter(e => !ids.has(e.id)), merges: plan.merges.filter(e => !ids.has(e.id)),
                                   refused: plan.refused.concat(held) });
}

/**
 * The id of the folder a move's new folder goes in: the region folder `to` for path [], else the
 * last of its <Partner>/<YYYY-MM> folders, each one the read found reused, each one missing made
 * (Drive.Files.create, supportsAllDrives) and kept in `levels` for the moves after it, and pushed
 * to `movedInto`. Throws when a level was not read or was refused, or Drive does not confirm one.
 */
function pathFolderId_(move, levels, movedInto) {
  let parent = move.to;
  const path = move.path || [];
  for (let k = 0; k < path.length; k++) {
    const at = levels ? levels[JSON.stringify(path.slice(0, k + 1))] : null;
    if (!at || at.refused) throw new Error('the folder "' + path.slice(0, k + 1).join('/') + '" was not read as one folder');
    if (!at.id) {
      const made = Drive.Files.create({ name: path[k], mimeType: FOLDER_MIME, parents: [parent] }, null, { supportsAllDrives: true });
      if (!made || !made.id) throw new Error('Drive did not confirm the folder "' + path.slice(0, k + 1).join('/') + '"');
      at.id = made.id;
      movedInto.push(made.id);
    }
    parent = at.id;
  }
  return parent;
}

/** ' to <Region>/<Partner>/<YYYY-MM>' for an entry filed below the region folder, '' for one filed in it. */
function pathText_(e) {
  return e.path && e.path.length ? ' to ' + e.region + '/' + e.path.join('/') : '';
}

/**
 * A live source subfolder as Plan.gs takes it: its files not in the trash, its own subfolders,
 * when it last changed. A file in the trash still in it (a person trashed it) moves nothing but
 * makes it not empty: `folders` is then left out, and the planner never removes it.
 */
function describeSubfolder_(sub) {
  const files = [], folders = [];
  let held = false;
  const fi = sub.getFiles();
  while (fi.hasNext()) {
    const f = fi.next();
    if (f.isTrashed()) {
      held = true;
      continue;
    }
    files.push({ id: f.getId(), name: f.getName(), size: f.getSize(), updated: f.getLastUpdated() });
  }
  const di = sub.getFolders();
  while (di.hasNext()) {
    const d = di.next();
    folders.push({ id: d.getId(), name: d.getName() });
  }
  const entry = { id: sub.getId(), name: sub.getName(), updated: sub.getLastUpdated(), trashed: false, files: files };
  if (!held) entry.folders = folders;
  return entry;
}

/**
 * {subfolder id: [file]}: the files the rescue moves (#144) out of the source subfolders in the
 * trash `binIds`, all listed by one query (they stay in the trash for 30 days: one listing each,
 * every run, would eat the read budget). Only a file Drive says is in the trash through its folder
 * (explicitlyTrashed false: Jotform wrote it in after the mover trashed the folder); a file a
 * person trashed is left alone. Settled from the later of its modified and created times (an
 * upload may keep an older modified time); with neither, now (it waits).
 */
function describeBinnedFiles_(binIds) {
  const byBin = {};
  for (const id of binIds) byBin[id] = [];
  const inBins = binIds.map(id => "'" + id + "' in parents").join(' or ');
  for (const f of listFiles_('(' + inBins + ") and trashed = true and mimeType != '" + FOLDER_MIME + "'",
                             'id, name, size, modifiedTime, createdTime, explicitlyTrashed, parents')) {
    const bin = (f.parents || []).filter(p => Object.prototype.hasOwnProperty.call(byBin, p))[0];
    if (!bin || f.explicitlyTrashed !== false) continue;
    const times = [Date.parse(f.modifiedTime), Date.parse(f.createdTime)].filter(t => !isNaN(t));
    byBin[bin].push({ id: f.id, name: f.name, size: Number(f.size),
                      updated: new Date(times.length ? Math.max.apply(null, times) : Date.now()) });
  }
  return byBin;
}

/** A Shared Drive folder's files not in the trash, by name and size (what a merge compares with). */
function describeFiles_(folder) {
  const files = [];
  const it = folder.getFiles();
  while (it.hasNext()) {
    const f = it.next();
    if (f.isTrashed()) continue;
    files.push({ id: f.getId(), name: f.getName(), size: f.getSize() });
  }
  return files;
}

/**
 * Every file or folder the query `q` matches, page by page (Drive may return a short page), with
 * `fields` of each. Every q here states `trashed` (Drive's default lists the trash too).
 */
function listFiles_(q, fields) {
  const found = [];
  let pageToken = null;
  do {
    const args = { q: q, fields: 'nextPageToken, files(' + fields + ')', supportsAllDrives: true, includeItemsFromAllDrives: true };
    if (pageToken) args.pageToken = pageToken;
    const page = Drive.Files.list(args);
    for (const f of page.files || []) found.push(f);
    pageToken = page.nextPageToken || null;
  } while (pageToken);
  return found;
}

/**
 * Per region: one count line, then a line per subfolder by name. No file names. `rescue` counts
 * the subfolders in the trash (inTrash) that photos move out of; `remove` the emptied ones trashed.
 */
function logPlan_(plan, config, apply, inTrash) {
  const verb = apply ? '' : 'would ';
  console.log((apply ? 'RUN' : 'DRY RUN (nothing changes)') + ': regions ' + config.map(c => c.region).join(', ') +
              '; settle ' + SETTLE_MINUTES + ' min');
  const bin = e => (inTrash[e.id] ? ' (in the trash)' : '');
  for (const c of config) {
    const of = list => list.filter(e => e.region === c.region);
    const moves = of(plan.moves), merges = of(plan.merges), waiting = of(plan.waiting), refused = of(plan.refused);
    const remove = of(plan.remove);
    const filesIn = merges.reduce((n, m) => n + m.files.length, 0), kept = merges.reduce((n, m) => n + m.kept.length, 0);
    const rescue = moves.concat(merges.filter(m => m.files.length)).filter(m => inTrash[m.id]).length;
    console.log(c.region + ': ' + verb + 'move ' + moves.length + ', ' + verb + 'merge ' + merges.length +
                ' (' + filesIn + ' file(s) in, ' + kept + ' kept), waiting ' + waiting.length +
                ', refused ' + refused.length + ', ' + verb + 'remove ' + remove.length + ', ' + verb + 'rescue ' + rescue);
    for (const m of moves) console.log('  ' + verb + 'move "' + m.name + '"' + pathText_(m) + bin(m));
    for (const m of merges) {
      console.log('  ' + verb + 'merge "' + m.name + '"' + pathText_(m) + bin(m) + ': ' + m.files.length + ' file(s) in, ' +
                  m.kept.length + ' kept in My Drive (same name and size already on the Shared Drive)');
    }
    for (const w of waiting) console.log('  waiting "' + w.name + '"' + pathText_(w) + bin(w));
    for (const r of refused) {
      console.log('  REFUSED "' + r.name + '"' + pathText_(r) + bin(r) + ': ' +
                  (r.why || 'two or more folders of this name') + ' on the Shared Drive; move it by hand');
    }
    for (const e of remove) {
      console.log('  ' + verb + 'remove "' + e.name + '": empty, unchanged for ' + SETTLE_MINUTES + ' min or more; to the trash');
    }
  }
  for (const u of plan.unknown) console.log('UNKNOWN "' + u.name + '": no such region or no target; left alone');
}

/**
 * Moves first, then merges, then the removals, until the time budget (checked before the folder is
 * made, before each file and before each removal). A move: a folder of the subfolder's name made
 * in the region folder, then the plan's files into it (only those: the subfolder is never listed
 * again); when Drive does not confirm the folder, none of its files moves this run. A subfolder in
 * the trash (read.inTrash) moves the same way, its files out of the trash (moveFiles_). A removal
 * (#144): the emptied subfolder re-read and re-listed just before (whyNotRemove_), then trashed by
 * moveToTrash_ with `protect`; one that changed since the planner read it stays, logged by name.
 * Every failure is logged by code, region and folder name, the rest of the run goes on, then one
 * error. A move whose folder exists but whose files did not all move is a merge on the next run.
 * `movedInto` (#191) gets the id of each Shared Drive folder made, and each merged into, before its
 * first file moves (an array the caller keeps, so a failure's error does not lose it).
 */
function carryOut_(plan, deadline, read, protect, movedInto) {
  const failed = [], left = [];
  let deferred = 0, moved = 0, filesMoved = 0, filesMerged = 0, rescued = 0, removed = 0;
  const late = () => Date.now() > deadline;
  const fromTrash = m => Object.prototype.hasOwnProperty.call(read.inTrash, m.id);
  for (const m of plan.moves) {
    if (late()) { deferred++; continue; }
    let made;
    try {
      const parent = pathFolderId_(m, read.levels && read.levels[m.region], movedInto);
      made = Drive.Files.create({ name: m.name, mimeType: FOLDER_MIME, parents: [parent] }, null, { supportsAllDrives: true });
    } catch (e) {
      failed.push('MOVE_FAILED ' + m.region + ' "' + m.name + '": folder not confirmed, its files stay in My Drive ' +
                  '(the next run merges if it exists): ' + errorText_(e));
      continue;
    }
    movedInto.push(made.id);
    const r = moveFiles_(m, made.id, 'MOVE_FAILED', late, failed, fromTrash(m));
    filesMoved += r.moved;
    rescued += r.rescued;
    if (r.deferred) deferred++;
    else if (!r.failed) moved++;
  }
  for (const m of plan.merges) {
    if (!m.files.length) continue;
    if (late()) { deferred++; continue; }
    movedInto.push(m.into);
    const r = moveFiles_(m, m.into, 'MERGE_FAILED', late, failed, fromTrash(m));
    filesMerged += r.moved;
    rescued += r.rescued;
    if (r.deferred) deferred++;
  }
  for (const e of plan.remove) {
    if (late()) { deferred++; continue; }
    try {
      const why = whyNotRemove_(e, read.sourceIds[e.region]);
      if (why) {
        left.push('  not trashed "' + e.name + '": ' + why + ' since it was read; the next run looks again');
        continue;
      }
      if (late()) { deferred++; continue; }
      moveToTrash_(e.id, protect);
      removed++;
    } catch (err) {
      failed.push('REMOVE_FAILED ' + e.region + ' "' + e.name + '": ' + errorText_(err));
    }
  }
  console.log('done: ' + moved + ' folder(s) moved (' + filesMoved + ' file(s)), ' + filesMerged + ' file(s) merged, ' +
              rescued + ' of these file(s) out of the trash; ' + removed + ' emptied folder(s) removed (to the trash); ' +
              failed.length + ' failure(s)' +
              (deferred ? ', ' + deferred + ' folder(s) left for the next run (TIME_BUDGET)' : ''));
  for (const l of left) console.log(l);
  for (const f of failed) console.log(f);
  if (failed.length) throw new Error(failed.length + ' failure(s): ' + failed[0]);
}

/**
 * The plan entry's files (ids), each into the folder `into` by one Drive.Files.update, until
 * `late()`: {moved, rescued, failed, deferred}; a failure is pushed to `failed` as `<code>
 * <region> "<folder name>": <error>` (never a file's name) and the next file is still tried. From
 * a subfolder in the trash (`fromTrash`, the rescue) the same update takes the file out of the
 * trash ({trashed: false}: a parent change alone may leave it there), and the file is re-read:
 * still in the trash, or not in `into`, is RESCUE_FAILED.
 */
function moveFiles_(entry, into, code, late, failed, fromTrash) {
  const r = { moved: 0, rescued: 0, failed: 0, deferred: false };
  for (const fileId of entry.files) {
    if (late()) { r.deferred = true; break; }
    try {
      Drive.Files.update(fromTrash ? { trashed: false } : {}, fileId, null,
                         { addParents: into, removeParents: entry.id, supportsAllDrives: true });
      if (fromTrash) {
        const now = Drive.Files.get(fileId, { fields: 'trashed,parents', supportsAllDrives: true });
        const wrong = now.trashed !== false ? 'is still in the trash' :
          (now.parents || []).indexOf(into) < 0 ? 'is not in the folder it was moved to' : '';
        if (wrong) {
          failed.push('RESCUE_FAILED ' + entry.region + ' "' + entry.name + '": a photo taken out of the trash ' + wrong +
                      ' (Drive said yes); find it by hand (RUNBOOK "Photo mover")');
          r.failed++;
          continue;
        }
        r.rescued++;
      }
      r.moved++;
    } catch (e) {
      failed.push(code + ' ' + entry.region + ' "' + entry.name + '": ' + errorText_(e));
      r.failed++;
    }
  }
  return r;
}

/**
 * '' when the plan's emptied subfolder may go to the trash now, else why not: re-read just before
 * (#144), it must still be a folder in its source folder, not in the trash, unchanged for
 * SETTLE_MINUTES, and hold nothing at all, in the trash or not (one page asked for; a further
 * page counts as something).
 */
function whyNotRemove_(entry, sourceId) {
  const now = Drive.Files.get(entry.id, { fields: 'mimeType, trashed, parents, modifiedTime', supportsAllDrives: true });
  if (now.mimeType !== FOLDER_MIME || now.trashed !== false || (now.parents || []).indexOf(sourceId) < 0) {
    return 'moved or trashed';
  }
  if (!(Date.now() - Date.parse(now.modifiedTime) >= SETTLE_MINUTES * 60 * 1000)) return 'changed';
  const page = Drive.Files.list({ q: "'" + entry.id + "' in parents and (trashed = false or trashed = true)",
                                  fields: 'nextPageToken, files(id)', pageSize: 1,
                                  supportsAllDrives: true, includeItemsFromAllDrives: true });
  return (page.files || []).length || page.nextPageToken ? 'something arrived in it' : '';
}

/**
 * The retention preview (#182, epic #179, rulings R7 and R14): the Shared Drive `driveId` read, Plan.gs planTrash_ run
 * on it and its plan logged (logRetention_); nothing is trashed or changed. The reads, each on the drive's corpus with
 * `trashed = false` stated and followed to its last page, until `deadline` (checked before each page):
 *   1. every folder on the drive (the region folders included), so every walk up resolves offline;
 *   2. the files created at or before now - days: a pre-filter, since no other file can be due;
 *   3. the files of each folder retentionFolders_ names (the old ones below a region folder), then of each region
 *      folder; a folder is `complete` once its listing reached its last page, and only then.
 * Steps 1 or 2 not done by the deadline: retention is skipped this run (TIME_BUDGET), so planTrash_ never sees a
 * partial folder list. Step 3 not done: the folders not listed in full stay incomplete (never emptied this run) and
 * the rest is planned. A Drive error at any step: RETENTION_FAILED, nothing planned. Returns {failure: the
 * RETENTION_FAILED text the caller ends the run with, '' otherwise; planned: {trash: planTrash_'s plan, drive: what it
 * was given, now, days} for trashRetention_ (#185, on `apply` only), null when nothing was planned}. Drive's
 * createdTime reaches the planner as a Date (driveTime_); an item's parent is its one parent, null with none or more.
 */
function previewRetention_(config, driveId, days, deadline, apply) {
  const now = new Date();
  const notFolder = "mimeType != '" + FOLDER_MIME + "' and trashed = false";
  let step = 'the cutoff';
  try {
    const cutoff = new Date(now.getTime() - days * 24 * 60 * 60 * 1000).toISOString();
    console.log('retention ' + days + ' days (due once a photo and its folder were both created at or before ' + cutoff +
                (apply ? '): the plan below goes to the trash, each item re-checked just before'
                       : '): a preview, nothing on the Shared Drive goes to the trash'));
    step = 'the search for the Shared Drive\'s folders';
    const found = listSharedDrive_(driveId, "mimeType = '" + FOLDER_MIME + "' and trashed = false", 'id, name, createdTime, parents',
                                   deadline);
    if (!found.complete) {
      console.log('TIME_BUDGET: retention skipped (folder list incomplete); it waits for the next run');
      return { failure: '', planned: null };
    }
    step = 'the search for the files created at or before the cutoff';
    const due = listSharedDrive_(driveId, notFolder + " and createdTime <= '" + cutoff + "'", 'id, createdTime, parents', deadline);
    if (!due.complete) {
      console.log('TIME_BUDGET: retention skipped (due-file search incomplete); it waits for the next run');
      return { failure: '', planned: null };
    }
    const regions = {};
    for (const c of config) regions[c.region] = c.target;
    const folders = found.files.map(f => ({ id: f.id, name: f.name, parent: oneParent_(f), created: driveTime_(f.createdTime),
                                            complete: false }));
    const drive = { regions: regions, rootId: driveId, folders: folders, files: [] };
    const seen = new Set();
    const addFiles = list => {
      for (const f of list) {
        if (seen.has(f.id)) continue;
        seen.add(f.id);
        drive.files.push({ id: f.id, parent: oneParent_(f), created: driveTime_(f.createdTime) });
      }
    };
    addFiles(due.files);
    const byId = new Map(folders.map(d => [d.id, d]));
    const toList = retentionFolders_(drive, now, days).concat(config.map(c => c.target));
    let listed = 0;
    for (const id of toList) {
      step = 'the listing of folder ' + (listed + 1) + ' of ' + toList.length + ' (the old folders, then the region folders)';
      const got = listSharedDrive_(driveId, "'" + id + "' in parents and " + notFolder, 'id, createdTime, parents', deadline);
      addFiles(got.files);
      if (!got.complete) break;
      if (byId.has(id)) byId.get(id).complete = true;
      listed++;
    }
    if (listed < toList.length) {
      console.log('TIME_BUDGET: retention listed the files of ' + listed + ' of ' + toList.length +
                  ' folder(s) in time; no folder it did not list in full is planned this run');
    }
    step = 'the plan';
    const trash = planTrash_(drive, now, days, RETENTION_MAX_FILES);
    logRetention_(trash, config, days, byId);
    return { failure: '', planned: { trash: trash, drive: drive, now: now, days: days } };
  } catch (e) {
    const failure = 'RETENTION_FAILED ' + step + ': ' + errorText_(e) + '; nothing previewed this run';
    console.log(failure);
    return { failure: failure, planned: null };
  }
}

/**
 * Files.list on the Shared Drive `driveId` alone (corpora 'drive'), `q` followed through nextPageToken to its last
 * page unless `deadline` passes first (checked before each page): {files, complete}. A Drive error throws.
 */
function listSharedDrive_(driveId, q, fields, deadline) {
  const files = [];
  let pageToken = null;
  do {
    if (Date.now() > deadline) return { files: files, complete: false };
    const args = { q: q, fields: 'nextPageToken, files(' + fields + ')', pageSize: RETENTION_PAGE_SIZE, corpora: 'drive',
                   driveId: driveId, supportsAllDrives: true, includeItemsFromAllDrives: true };
    if (pageToken) args.pageToken = pageToken;
    const page = Drive.Files.list(args);
    for (const f of page.files || []) files.push(f);
    pageToken = page.nextPageToken || null;
  } while (pageToken);
  return { files: files, complete: true };
}

/** An item's one parent id; null when Drive gives none or more than one (the planner then counts it outside). */
function oneParent_(item) {
  return Array.isArray(item.parents) && item.parents.length === 1 ? item.parents[0] : null;
}

/** Drive's createdTime (RFC 3339) as a Date; null for anything else (never due: refuse rather than guess). */
function driveTime_(text) {
  const rfc3339 = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/;
  const ms = typeof text === 'string' && rfc3339.test(text) ? Date.parse(text) : NaN;
  return isNaN(ms) ? null : new Date(ms);
}

/**
 * planTrash_'s plan as the log's `would trash` lines (ruling R14): per configured region its counts, then per region
 * subfolder affected (a region folder's direct subfolder, `top`) its counts with everything deeper under it, by name,
 * and the files directly in the region folder; then how many old files lie outside the region folders, and
 * RETENTION_CAP with the due files the cap left out. No file's name, and no folder's but a region subfolder's.
 */
function logRetention_(trash, config, days, foldersById) {
  for (const c of config) {
    const files = trash.files.filter(f => f.region === c.region), folders = trash.folders.filter(d => d.region === c.region);
    console.log(c.region + ': retention ' + days + ' days: would trash ' + files.length + ' file(s) and ' + folders.length +
                ' folder(s)');
    const tops = new Map();
    const under = id => {
      if (!tops.has(id)) tops.set(id, { name: foldersById.get(id).name, files: 0, folders: 0 });
      return tops.get(id);
    };
    let direct = 0;
    for (const f of files) {
      if (f.top === null) direct++;
      else under(f.top).files++;
    }
    for (const d of folders) under(d.top).folders++;
    const named = [...tops.values()].sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    for (const t of named) {
      console.log('  would trash ' + t.files + ' file(s) and ' + t.folders + ' folder(s) under "' + t.name + '"');
    }
    if (direct) console.log('  would trash ' + direct + ' file(s) directly in the region folder');
  }
  console.log('retention: ' + trash.outside + ' old file(s) outside the region folders, left alone');
  if (trash.capped) console.log('RETENTION_CAP: ' + trash.capped + ' due file(s) left for the next run');
}

/**
 * The real run's trash of the retention plan (#185, epic #179, rulings R1, R3, R6, R8, R9, R14): `planned` is what
 * previewRetention_ read and planTrash_ planned. Every trash is moveToTrash_(id, protect), the one trash (#144).
 *
 * First the whole plan is checked against the read, before any Drive call: each item a non-empty id, not a configured
 * SOURCE_/TARGET_FOLDER_ id, not the drive's root, not a region folder, in the read with its planned parent (a folder
 * also listed there in full), and its walk up there reaching its planned region's folder. One item that is not:
 * TRASH_REFUSED, nothing trashed this run, the run ends with an error (refuse rather than guess: the planner is wrong).
 *
 * Then the files, at most RETENTION_MAX_FILES, the earliest due first (RETENTION_CAP for the rest), then the folders in
 * the plan's order (children before parents), each re-checked just before its trash (R9), against Drive now:
 *   the item   Files.get: not in the trash, a file (a folder), on the drive, its one parent the planned one;
 *   its walk up  from that parent up to the planned region's folder, every folder on the way (planned or not, at any
 *              depth) read by Files.get once per run, before the first trash under it: an untrashed folder on the
 *              drive whose one live parent is still the one the run read; a folder moved (into another region's
 *              folder, out of the region folders, or anywhere else) or trashed skips everything under it;
 *   a file     the later of its own and its folder's createdTime still at or before the cutoff;
 *   a folder   its own createdTime at or before the cutoff, and re-listed (`trashed = false`, files and folders) to its
 *              last page with nothing in it.
 * Kept this run, before any Drive call for it (#191): each folder in `movedInto` (carryOut_ made it or merged files
 * into it) and every folder above it up to its region folder, by the read's tree; Drive's search may not yet show a
 * photo just moved in, at the read or at the re-list. Counted like a failed re-check.
 * A failed re-check skips the item without an error (`not trashed "<region subfolder>"`); a Drive error is
 * `TRASH_FAILED <Region> "<region subfolder>"` (no subfolder for a photo directly in the region folder) and the rest
 * goes on; a folder still holding what was not trashed fails its re-list and stays. The deadline is checked before
 * each item and after its re-check reads (TIME_BUDGET: the rest waits for the next run). The log: per region with
 * something planned `<Region>: … trashed N file(s) and M folder(s)`, then per region subfolder, by name only (R14).
 * Returns the failure the run ends with, '' when none.
 */
function trashRetention_(planned, config, driveId, deadline, protect, movedInto) {
  const trash = planned.trash, drive = planned.drive, days = planned.days;
  const cutoffMs = planned.now.getTime() - days * 24 * 60 * 60 * 1000;
  const tree = retentionTree_(drive, planned.now, days);
  const never = new Set(configuredFolderIds_().all.concat(protect, driveId));
  const regionFolder = new Map(config.map(c => [c.region, c.target]));
  const readFiles = new Map(drive.files.map(f => [f.id, f])), readFolders = new Map(drive.folders.map(d => [d.id, d]));
  const keptNow = new Set();   // #191: the folders this run moved files into and those above them, as read
  for (const id of movedInto) {
    for (let at = id; readFolders.has(at) && !tree.guarded(at) && !keptNow.has(at); at = readFolders.get(at).parent) {
      keptNow.add(at);
    }
  }
  const queue = [], refused = new Map();
  const place = (e, isFolder) => {
    const id = e && typeof e === 'object' ? e.id : null;
    const read = typeof id === 'string' && id ? (isFolder ? readFolders : readFiles).get(id) : undefined;
    const at = read && !never.has(id) && !tree.guarded(id) && read.parent === e.parent && (!isFolder || read.complete === true) ?
      tree.walkUp(e.parent) : null;
    if (!at || at.region !== e.region || !regionFolder.has(e.region)) {
      const region = e && regionFolder.has(e.region) ? e.region : '?';
      refused.set(region, (refused.get(region) || 0) + 1);
      return;
    }
    queue.push({ isFolder: isFolder, id: id, parent: e.parent, region: e.region,
                 top: isFolder && at.top === null ? id : at.top, due: isFolder ? NaN : timeOf_(e.due) });
  };
  for (const f of Array.isArray(trash.files) ? trash.files : []) place(f, false);
  for (const d of Array.isArray(trash.folders) ? trash.folders : []) place(d, true);
  if (refused.size) {
    let n = 0;
    for (const [region, count] of refused) {
      n += count;
      console.log('TRASH_REFUSED ' + region + ': ' + count + ' planned item(s) refused (a configured folder, the Shared Drive\'s ' +
                  'root, a region folder, or not below its region folder as read); nothing on the Shared Drive trashed this run');
    }
    return 'TRASH_REFUSED: ' + n + ' planned item(s) refused; nothing on the Shared Drive trashed this run';
  }
  const dueOf = e => (isNaN(e.due) ? Infinity : e.due);
  const files = queue.filter(e => !e.isFolder).sort((a, b) => dueOf(a) - dueOf(b) || compareIds_(a.id, b.id));
  const capped = Math.max(0, files.length - RETENTION_MAX_FILES);
  const order = files.slice(0, RETENTION_MAX_FILES).concat(queue.filter(e => e.isFolder));

  const get = id => Drive.Files.get(id, { fields: 'id, mimeType, trashed, parents, createdTime, driveId', supportsAllDrives: true });
  const walked = new Map();   // folder id -> its Files.get this run, or the error it gave: each folder read once
  const folderNow = id => {
    if (!walked.has(id)) {
      try {
        walked.set(id, get(id));
      } catch (err) {
        walked.set(id, { error: errorText_(err) });
      }
    }
    const got = walked.get(id);
    if (got.error) throw new Error(got.error);
    return got;
  };
  const stillUnder = (parentId, regionId) => {
    const met = new Set();
    for (let id = parentId; id !== regionId;) {
      const read = readFolders.get(id);
      if (!read || never.has(id) || met.has(id)) return false;
      met.add(id);
      const got = folderNow(id);
      if (got.mimeType !== FOLDER_MIME || got.trashed !== false || got.driveId !== driveId || oneParent_(got) !== read.parent) {
        return false;
      }
      id = read.parent;
    }
    return true;
  };
  /** '' when the item may go to the trash now, else why not; a Drive error throws. */
  const whyNot = e => {
    const item = get(e.id);
    if (item.trashed !== false || (item.mimeType === FOLDER_MIME) !== e.isFolder || item.driveId !== driveId ||
        oneParent_(item) !== e.parent) {
      return 'moved or trashed';
    }
    if (!stillUnder(e.parent, regionFolder.get(e.region))) return 'a folder above it moved or trashed';
    const own = timeOf_(driveTime_(item.createdTime));
    if (!e.isFolder) {
      const folder = timeOf_(driveTime_(folderNow(e.parent).createdTime));
      return Math.max(own, folder) <= cutoffMs ? '' : 'no longer due';
    }
    if (!(own <= cutoffMs)) return 'too young';
    const inIt = listSharedDrive_(driveId, "'" + e.id + "' in parents and trashed = false", 'id', deadline);
    return !inIt.complete ? 'not listed in time' : inIt.files.length ? 'not empty' : '';
  };

  const tally = new Map();   // region -> {files, folders, direct, keptDirect, tops: Map(top id -> {files, folders, kept})}
  for (const e of order) {
    if (!tally.has(e.region)) tally.set(e.region, { files: 0, folders: 0, direct: 0, keptDirect: 0, tops: new Map() });
  }
  const topOf = e => {
    const t = tally.get(e.region).tops;
    if (!t.has(e.top)) t.set(e.top, { files: 0, folders: 0, kept: 0 });
    return t.get(e.top);
  };
  const nameOf = top => readFolders.get(top).name;
  const failed = [];
  const late = () => Date.now() > deadline;
  let left = 0;
  for (let i = 0; i < order.length; i++) {
    const e = order[i];
    if (late()) { left = order.length - i; break; }
    if (keptNow.has(e.id)) {   // #191: a folder, so under a region subfolder (or one itself)
      topOf(e).kept++;
      continue;
    }
    try {
      const why = whyNot(e);
      if (late()) { left = order.length - i; break; }
      if (why) {
        if (e.top === null) tally.get(e.region).keptDirect++;
        else topOf(e).kept++;
        continue;
      }
      moveToTrash_(e.id, protect);
      const t = tally.get(e.region);
      if (e.isFolder) {
        t.folders++;
        topOf(e).folders++;
      } else {
        t.files++;
        if (e.top === null) t.direct++;
        else topOf(e).files++;
      }
    } catch (err) {
      failed.push('TRASH_FAILED ' + e.region + (e.top === null ? '' : ' "' + nameOf(e.top) + '"') + ': ' + errorText_(err));
    }
  }
  for (const c of config) {
    const t = tally.get(c.region);
    if (!t) continue;
    console.log(c.region + ': retention ' + days + ' days: trashed ' + t.files + ' file(s) and ' + t.folders + ' folder(s)');
    const tops = [...t.tops.entries()].map(([id, n]) => Object.assign({ name: nameOf(id) }, n))
      .sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    for (const n of tops) {
      if (n.files || n.folders) console.log('  trashed ' + n.files + ' file(s) and ' + n.folders + ' folder(s) under "' + n.name + '"');
    }
    if (t.direct) console.log('  trashed ' + t.direct + ' file(s) directly in the region folder');
    for (const n of tops) {
      if (n.kept) {
        console.log('  not trashed "' + n.name + '": ' + n.kept + ' item(s) kept by the re-check (moved, trashed or re-dated ' +
                    'since the read, a folder not empty, or a folder this run moved photos into or one above it); the next ' +
                    'run looks again');
      }
    }
    if (t.keptDirect) {
      console.log('  not trashed: ' + t.keptDirect + ' file(s) directly in the region folder kept by the re-check (moved, ' +
                  'trashed or re-dated since the read); the next run looks again');
    }
  }
  if (capped) console.log('RETENTION_CAP: ' + capped + ' due file(s) left for the next run (at most ' + RETENTION_MAX_FILES + ' a run)');
  if (left) {
    console.log('TIME_BUDGET: retention trash stopped with ' + left + ' of ' + order.length + ' planned item(s) left; they wait ' +
                'for the next run');
  }
  for (const f of failed) console.log(f);
  return failed.length ? failed.length + ' retention trash failure(s): ' + failed[0] : '';
}

/**
 * The ids no trash may touch, handed to every moveToTrash_ call: each configured source and
 * target folder, and the Shared Drive's root.
 */
function protectedIds_(config) {
  const ids = [];
  for (const c of config) ids.push(c.source, c.target);
  return ids.concat(sharedDriveRoots_(config.map(c => c.target)));
}

/** Every id in a SOURCE_FOLDER_<KEY> / TARGET_FOLDER_<KEY> Script Property, usable or not: {all, targets}. */
function configuredFolderIds_() {
  const props = PropertiesService.getScriptProperties();
  const all = [], targets = [];
  for (const region of PHOTO_REGIONS) {
    const source = props.getProperty('SOURCE_FOLDER_' + REGION_KEYS[region]);
    const target = props.getProperty('TARGET_FOLDER_' + REGION_KEYS[region]);
    if (source) all.push(source);
    if (target) {
      all.push(target);
      targets.push(target);
    }
  }
  return { all: all, targets: targets };
}

const DRIVE_ROOTS_ = {};   // target folder id -> the id of the Shared Drive it is on ('' if none), read once per execution

/**
 * The roots of the Shared Drives the target folders are on: in Drive v3 a shared drive's root
 * folder has the drive's id, which every item on it reports as `driveId`.
 */
function sharedDriveRoots_(targetIds) {
  const roots = [];
  for (const t of targetIds) {
    if (!Object.prototype.hasOwnProperty.call(DRIVE_ROOTS_, t)) {
      const got = Drive.Files.get(t, { fields: 'driveId', supportsAllDrives: true });
      DRIVE_ROOTS_[t] = (got && got.driveId) || '';
    }
    if (DRIVE_ROOTS_[t] && roots.indexOf(DRIVE_ROOTS_[t]) < 0) roots.push(DRIVE_ROOTS_[t]);
  }
  return roots;
}

/**
 * The one trash (#144; #185 reuses it): the item `id` to Drive's trash (restorable for 30 days),
 * by one Drive.Files.update {trashed: true}; never a permanent delete. It refuses (throws), before
 * any Drive call, an id that is not a non-empty string, `protectedIds` that is not an array, an id
 * in it, and on its own, whatever the caller passes, any id in a SOURCE_FOLDER_ / TARGET_FOLDER_
 * Script Property and the root of the Shared Drive a target folder is on (read once per
 * execution, by the run before its first trash; a caller that has not read it costs one Drive
 * read per target here first). What may go is the caller's rule; what never may, this guard's.
 */
function moveToTrash_(id, protectedIds) {
  if (typeof id !== 'string' || !id) throw new Error('TRASH refused: no item id');
  if (!Array.isArray(protectedIds)) throw new Error('TRASH refused: no list of ids to protect');
  if (protectedIds.indexOf(id) >= 0) throw new Error('TRASH refused: a protected folder');
  const configured = configuredFolderIds_();
  if (configured.all.indexOf(id) >= 0) throw new Error('TRASH refused: a configured source or target folder');
  if (sharedDriveRoots_(configured.targets).indexOf(id) >= 0) throw new Error('TRASH refused: the root of a Shared Drive');
  Drive.Files.update({ trashed: true }, id, null, { supportsAllDrives: true });
}

function errorText_(e) {
  return String(e && e.message || e).slice(0, 200);
}
