/**
 * The photo mover's decisions, with no Google service: which submission subfolders of Ryan's My
 * Drive go to which region folder of the Shared Drive (ticket #89,
 * docs/plans/2026-10-21-drive-photo-mover.md), and which emptied ones go to the trash (#144).
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
 */

const PHOTO_PREFIX = 'Attendance photos - ';
const PHOTO_REGIONS = ['Africa', 'Asia', 'Latin America', 'U.S', 'Template'];

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
