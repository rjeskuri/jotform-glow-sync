/**
 * The photo mover's decisions, with no Google service: which submission subfolders of Ryan's My
 * Drive go to which region folder of the Shared Drive (ticket #89,
 * docs/plans/2026-10-21-drive-photo-mover.md). Mover.gs reads Drive, calls planMoves_ and does
 * what the plan says; the dry run only logs it. Tested offline in test/drive_sync_test.js.
 *
 *   planMoves_(sourceFolders, targetFolders, now, settleMinutes) -> {moves, merges, waiting, refused, unknown}
 *
 * sourceFolders  [{id, name, subfolders: [{id, name, files: [{id, name, size, updated}]}]}]
 *                Jotform's `Attendance photos - <Region>` folders (any other folder is ignored)
 * targetFolders  {<Region>: {id, subfolders: [{id, name, files: [{id, name, size}]}]}}
 *                the Shared Drive's region folders; their subfolders need only be the ones whose
 *                name a source subfolder has (Mover.gs looks those up by name)
 *
 * moves    [{region, id, name, to, files}]  the name is not yet in the region folder (to): Mover.gs
 *          makes a folder of that name there and moves `files` (ALL the subfolder's file ids)
 *          into it, since Drive cannot move a My Drive folder into a Shared Drive (#132); the
 *          emptied subfolder stays in My Drive
 * merges   [{region, id, name, into, files, kept}]  the name is already there once: `files` (ids)
 *          move into that folder, `kept` (ids) stay because a file of the same name and size is
 *          already there; nothing on the Shared Drive is ever replaced
 * waiting  [{region, id, name}]  a file changed less than settleMinutes ago (still uploading), or
 *          a subfolder of the same name in that region is moved, or merged with files, this run
 *          (a merge whose files are all kept moves nothing and never waits)
 * refused  [{region, id, name}]  two or more subfolders of that name on the Shared Drive already
 * unknown  [{id, name}]          `Attendance photos - <x>` where x is no region, or has no target
 *
 * A subfolder with no files is in no list (Jotform has not uploaded yet, or a merge left nothing).
 */

const PHOTO_PREFIX = 'Attendance photos - ';
const PHOTO_REGIONS = ['Africa', 'Asia', 'Latin America', 'U.S', 'Template'];

function planMoves_(sourceFolders, targetFolders, now, settleMinutes) {
  const plan = { moves: [], merges: [], waiting: [], refused: [], unknown: [] };
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
      if (!sub.files.length) continue;
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
