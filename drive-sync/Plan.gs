/**
 * The photo mover's decisions, with no Google service: which submission subfolders of Ryan's My
 * Drive go to which region folder of the Shared Drive (ticket #89,
 * docs/plans/2026-10-21-drive-photo-mover.md), which emptied ones go to the trash (#144), and
 * which photos and emptied folders under the Shared Drive's region folders go to its trash once
 * 90 days old (planTrash_, retentionFolders_: #181, epic #179,
 * docs/plans/2026-10-30-photo-retention.md; Mover.gs reads the Shared Drive for them and logs the
 * plan, #182, and the real run trashes it, each item re-checked just before, #185).
 * Mover.gs reads Drive, calls planMoves_ and does what the plan says; the dry run only logs it.
 * Tested offline in test/drive_sync_test.js.
 *
 *   planMoves_(sourceFolders, targetFolders, now, settleMinutes)
 *     -> {moves, merges, waiting, refused, unknown, remove}
 *
 * sourceFolders  [{id, name, subfolders: [{id, name, updated, folders: [{id, name}], trashed,
 *                                          files: [{id, name, size, updated}]}]}]
 *                Jotform's `Attendance photos - <Region>` folders (any other folder is ignored).
 *                A subfolder's `updated` is when the folder itself last changed; `folders` its own
 *                subfolders (Mover.gs leaves it out when it cannot tell the folder is empty: a
 *                file in the trash is still in it); `trashed` true when the folder is in Drive's
 *                trash, its `files` then what Jotform wrote into it after the mover trashed it
 *                (#144, the rescue), never a file a person trashed
 * targetFolders  {<Region>: {id, subfolders: [{id, name, files: [{id, name, size}]}]}}
 *                the Shared Drive's region folders; their subfolders need only be the ones whose
 *                name a source subfolder has (Mover.gs looks those up by name)
 *
 * moves    [{region, id, name, to, files}]  the name is not yet in the region folder (to): Mover.gs
 *          makes a folder of that name there and moves `files` (ALL the subfolder's file ids)
 *          into it, since Drive cannot move a My Drive folder into a Shared Drive (#132); the
 *          emptied subfolder stays in My Drive until a later run removes it
 * merges   [{region, id, name, into, files, kept}]  the name is already there once: `files` (ids)
 *          move into that folder, `kept` (ids) stay because a file of the same name and size is
 *          already there; nothing on the Shared Drive is ever replaced
 * waiting  [{region, id, name}]  a file changed less than settleMinutes ago (still uploading), or
 *          a subfolder of the same name in that region is moved, or merged with files, this run
 *          (a merge whose files are all kept moves nothing and never waits)
 * refused  [{region, id, name}]  two or more subfolders of that name on the Shared Drive already
 * unknown  [{id, name}]          `Attendance photos - <x>` where x is no region, or has no target
 * remove   [{region, id, name}]  (#144) not in the trash, no file, no subfolder, and the folder
 *          itself unchanged for at least settleMinutes: Mover.gs re-lists it and, still empty,
 *          moves it to the trash. Without `updated` or `folders` it is never removed (refuse
 *          rather than guess). A subfolder this run moves files out of had files, so it is
 *          removed on a later run, once it has settled
 *
 * A subfolder in the trash with files is planned like any other (moved, merged, waiting or
 * refused; one per name per run with a live one of its name). One in the trash with no file,
 * and a live one with no file that is not removed, are in no list.
 *
 *   retentionFolders_(drive, now, retentionDays) -> [folder id]
 *   planTrash_(drive, now, retentionDays, maxFiles) -> {files, folders, capped, outside}
 *
 * drive      {regions: {<Region>: <folder id>}, rootId, folders: [{id, name, parent, created, complete}],
 *             files: [{id, parent, created}]}
 *            regions: the TARGET_FOLDER_<KEY> ids; only a region of PHOTO_REGIONS that is an own key
 *            with a non-empty string id counts. rootId: the Shared Drive's id (its root). folders:
 *            EVERY untrashed folder on the Shared Drive, the region folders included, so a folder's
 *            child folders are always all known. files: the untrashed files the reader saw.
 *            parent: the item's one parent id, null when Drive gave none or more than one.
 *            created: a Date (Drive's createdTime); anything else (null, a string, an Invalid Date)
 *            is no date. complete: true when every untrashed FILE whose parent is this folder is in
 *            `files`; anything but true is not
 * walk up    from an item's parent: rootId, null, an id not in `folders` or an id already met means
 *            the item is outside (never trashed); otherwise the first configured region folder met
 *            is its region. A region folder's id and rootId are never in the plan, whatever they
 *            are listed as (a folder, a file, a region folder inside another region's)
 * due        now - max(file.created, created of the folder that is its parent) >= retentionDays *
 *            86,400,000 ms: no time zone, due at exactly that moment; never without both dates
 *
 * retentionFolders_  the ids of the folders strictly below a region folder whose own created is at
 *            least retentionDays old, in the order of `folders` (the reader lists their files in
 *            full); `complete` and `files` play no part
 * files      [{region, id, parent, top, due}]  the due files below a region folder, earliest due
 *            moment first, then id; at most maxFiles. top: the region folder's direct subfolder the
 *            file is under, null when it sits directly in the region folder (Mover.gs logs by it,
 *            ruling R14); due: its due moment, a Date
 * folders    [{region, id, name, parent, top}]  the folders to trash, deepest first (children
 *            before parents): strictly below a region folder, complete === true, itself at least
 *            retentionDays old, every file in it in `files` and every folder in it earlier in
 *            `folders`; top: the region folder's direct subfolder it is, or is under
 * capped     how many due files maxFiles left out (the folders above them stay)
 * outside    how many files of drive.files reach no region folder on the walk up
 *
 * Both throw when retentionDays is not a whole number of at least RETENTION_MIN_DAYS, planTrash_
 * also when maxFiles is not a whole number of at least 1. Like planMoves_, they touch no Google
 * service and do not change their inputs.
 */

const PHOTO_PREFIX = 'Attendance photos - ';
const PHOTO_REGIONS = ['Africa', 'Asia', 'Latin America', 'U.S', 'Template'];
const RETENTION_MIN_DAYS = 90;

function planMoves_(sourceFolders, targetFolders, now, settleMinutes) {
  const plan = { moves: [], merges: [], waiting: [], refused: [], unknown: [], remove: [] };
  const settleMs = settleMinutes * 60 * 1000;
  const nowMs = now.getTime();
  const actedOn = {};   // region -> {subfolder name: true}, one per name per run
  for (const source of sourceFolders) {
    if (source.name.indexOf(PHOTO_PREFIX) !== 0) continue;
    const region = source.name.slice(PHOTO_PREFIX.length);
    const target = photoTarget_(targetFolders, region);
    if (!target) {
      plan.unknown.push({ id: source.id, name: source.name });
      continue;
    }
    if (!Object.prototype.hasOwnProperty.call(actedOn, region)) actedOn[region] = {};
    const acted = actedOn[region];
    for (const sub of source.subfolders) {
      if (!sub.files.length) {
        if (isRemovable_(sub, nowMs, settleMs)) plan.remove.push({ region: region, id: sub.id, name: sub.name });
        continue;
      }
      const entry = { region: region, id: sub.id, name: sub.name };
      const newest = Math.max.apply(null, sub.files.map(f => f.updated.getTime()));
      if (nowMs - newest < settleMs) {
        plan.waiting.push(entry);
        continue;
      }
      const there = target.subfolders.filter(t => t.name === sub.name);
      if (there.length > 1) {
        plan.refused.push(entry);
        continue;
      }
      const claimed = Object.prototype.hasOwnProperty.call(acted, sub.name);
      if (!there.length) {
        if (claimed) {
          plan.waiting.push(entry);
          continue;
        }
        acted[sub.name] = true;
        plan.moves.push({ region: region, id: sub.id, name: sub.name, to: target.id, files: sub.files.map(f => f.id) });
        continue;
      }
      const isDuplicate = f => there[0].files.some(t => t.name === f.name && t.size === f.size);
      const merge = { region: region, id: sub.id, name: sub.name, into: there[0].id,
                      files: sub.files.filter(f => !isDuplicate(f)).map(f => f.id),
                      kept: sub.files.filter(isDuplicate).map(f => f.id) };
      // a merge that moves nothing (every file already there) changes nothing, so it does not
      // claim the name: a same-name copy with new photos still merges this run
      if (merge.files.length && claimed) {
        plan.waiting.push(entry);
        continue;
      }
      if (merge.files.length) acted[sub.name] = true;
      plan.merges.push(merge);
    }
  }
  return plan;
}

/** The region's target folder: only for a region in PHOTO_REGIONS that targetFolders has as its own key. */
function photoTarget_(targetFolders, region) {
  if (PHOTO_REGIONS.indexOf(region) < 0) return null;
  if (!Object.prototype.hasOwnProperty.call(targetFolders, region)) return null;
  return targetFolders[region] || null;
}

/** An empty subfolder (no files) the mover may trash: not in the trash, no subfolder, itself settled. */
function isRemovable_(sub, nowMs, settleMs) {
  if (sub.trashed || !Array.isArray(sub.folders) || sub.folders.length) return false;
  const at = sub.updated && typeof sub.updated.getTime === 'function' ? sub.updated.getTime() : NaN;
  return !isNaN(at) && nowMs - at >= settleMs;
}

function retentionFolders_(drive, now, retentionDays) {
  const tree = retentionTree_(drive, now, retentionDays);
  return drive.folders.filter(d => !tree.guarded(d.id) && tree.walkUp(d.parent) && tree.isOld(timeOf_(d.created)))
    .map(d => d.id);
}

function planTrash_(drive, now, retentionDays, maxFiles) {
  const tree = retentionTree_(drive, now, retentionDays);
  if (!Number.isInteger(maxFiles) || maxFiles < 1) {
    throw new Error('planTrash_ refused: maxFiles must be a whole number of at least 1, not ' +
                    typeof maxFiles + ' ' + String(maxFiles));
  }
  const due = [];
  let outside = 0;
  for (const f of drive.files) {
    const at = tree.walkUp(f.parent);
    if (!at) {
      outside++;
      continue;
    }
    if (tree.guarded(f.id)) continue;   // a reader's mistake: never planned, so its folder stays too
    const moment = Math.max(timeOf_(f.created), tree.createdOf(f.parent));   // NaN without both dates
    if (!tree.isOld(moment)) continue;
    due.push({ region: at.region, id: f.id, parent: f.parent, top: at.top, due: new Date(moment) });
  }
  due.sort((a, b) => a.due.getTime() - b.due.getTime() || compareIds_(a.id, b.id));
  const files = due.slice(0, maxFiles);
  const planned = new Set(files.map(e => e.id));
  // a folder holding anything that stays (a file not planned, a region folder, the root) stays,
  // and so does every folder above it
  const keep = new Set();
  for (const f of drive.files) if (!planned.has(f.id)) keep.add(f.parent);
  const below = [];   // the folders strictly below a region folder, with their walk up
  for (const d of drive.folders) {
    if (tree.guarded(d.id)) {
      keep.add(d.parent);
      continue;
    }
    const at = tree.walkUp(d.parent);
    if (at) below.push({ folder: d, at: at });
  }
  // deepest first, so every folder in a folder is decided before it: children before parents
  below.sort((a, b) => b.at.depth - a.at.depth || compareIds_(a.folder.id, b.folder.id));
  const folders = [];
  for (const entry of below) {
    const d = entry.folder;
    if (keep.has(d.id) || d.complete !== true || !tree.isOld(timeOf_(d.created))) {
      keep.add(d.parent);
      continue;
    }
    folders.push({ region: entry.at.region, id: d.id, name: d.name, parent: d.parent,
                   top: entry.at.top === null ? d.id : entry.at.top });
  }
  return { files: files, folders: folders, capped: due.length - files.length, outside: outside };
}

/**
 * The Shared Drive as planTrash_ and retentionFolders_ see it: the walk up (null when outside,
 * else {region, depth: the folders met below the region folder, top: the farthest of them or
 * null}), the ids never trashed, a folder's created and the clock. Refuses a retentionDays that
 * is not a whole number of at least RETENTION_MIN_DAYS.
 */
function retentionTree_(drive, now, retentionDays) {
  if (!Number.isInteger(retentionDays) || retentionDays < RETENTION_MIN_DAYS) {
    throw new Error('retention refused: retentionDays must be a whole number of at least ' + RETENTION_MIN_DAYS +
                    ', not ' + typeof retentionDays + ' ' + String(retentionDays));
  }
  const regionOf = new Map();   // configured region folder id -> region
  for (const region of PHOTO_REGIONS) {
    if (!Object.prototype.hasOwnProperty.call(drive.regions, region)) continue;
    const id = drive.regions[region];
    if (typeof id === 'string' && id) regionOf.set(id, region);
  }
  const byId = new Map(drive.folders.map(d => [d.id, d]));
  const rootId = drive.rootId;
  const nowMs = now.getTime(), retentionMs = retentionDays * 24 * 60 * 60 * 1000;
  return {
    guarded: id => regionOf.has(id) || id === rootId,
    createdOf: id => (byId.has(id) ? timeOf_(byId.get(id).created) : NaN),
    isOld: ms => nowMs - ms >= retentionMs,   // false for NaN
    walkUp: parentId => {
      const met = [];
      let id = parentId;
      for (;;) {
        // the root before the regions: a region configured as the root would take in the whole drive
        if (id === null || id === undefined || id === rootId) return null;
        if (regionOf.has(id)) {
          return { region: regionOf.get(id), depth: met.length, top: met.length ? met[met.length - 1] : null };
        }
        if (!byId.has(id) || met.indexOf(id) >= 0) return null;
        met.push(id);
        id = byId.get(id).parent;
      }
    },
  };
}

/** A Date's time in ms; NaN for anything that is not a Date (null, a string, a number) or is an Invalid Date. */
function timeOf_(value) {
  return Object.prototype.toString.call(value) === '[object Date]' ? value.getTime() : NaN;
}

function compareIds_(a, b) {
  return a < b ? -1 : a > b ? 1 : 0;
}
