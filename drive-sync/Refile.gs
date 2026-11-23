/**
 * The one-time re-filing of the club folders already on the Shared Drive (ticket #237,
 * docs/plans/2026-11-23-refile-photo-folders.md). Since #225 the mover files a new submission
 * subfolder under `<Region>/<Partner>/<YYYY-MM>/`; the folders it filed before then sit directly
 * in the region folder, named `<Club Name> <MM-DD-YYYY>` (since 2026-10-30) or the club alone
 * (before), with no partner in the name. This file moves each of them once under
 * `<Region>/<Partner>/<YYYY-MM>/`, or `<Region>/<Partner>/undated/` when its name has no date.
 *
 *   previewRefile    the dry run: reads the region folders, logs the plan, changes nothing
 *   refileExisting   the real run: the same read and plan, then carried out; run it again until
 *                    it moves nothing (what the time budget left waits for the next run)
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
 * with the mover (the script lock). Each region folder is read by listing (Drive.Files.list on
 * that Shared Drive, `trashed = false`), three levels deep: its folders, theirs, and theirs
 * again (names only); for its own folders also how many files each holds. Past half the time
 * budget a region not read in full is not planned this run (TIME_BUDGET).
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
 *   `<Club> <MM-DD-YYYY>`                            (since 2026-10-30) the last word the date:
 *                                                     the club before it, its month
 *   `<Partner> <Club> <MM-DD-YYYY> [<Week>]`          (the integration's spaces-only naming of
 *                                                     2026-11-23) the last date-shaped word the
 *                                                     date, anything after it the week: the
 *                                                     partner and club before it, its month
 *   any of these, with a date that is not a real one stays: bad-date
 *   anything else (the club alone, before 2026-10-30) the whole name is the club, `undated`
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
 *
 * What the real run does, and never does: each folder planned is moved itself, whole, by one
 * Drive.Files.update ({}, addParents the month folder, removeParents the region folder,
 * supportsAllDrives), within the Shared Drive; its photos stay in it and nothing is renamed.
 * A missing partner or month folder is made by Drive.Files.create (supportsAllDrives), once per
 * run. Just before each move the folder is read by id: still a live folder of its name whose one
 * parent is the region folder, or it is skipped (`moved or trashed since the read`, no error);
 * after it, read back: its one parent the month folder, or REFILE_FAILED. The time budget is
 * checked before each folder, never between making its partner and month folders and its move.
 * Never a configured SOURCE_ / TARGET_FOLDER_ folder, the Shared Drive's root, anything in the
 * trash; nothing trashed, shared, copied or deleted. A failure is logged by code, region and
 * folder name, the rest goes on, and the run ends with an error. A re-run after a complete run
 * moves nothing (a moved folder is no longer directly in the region folder).
 *
 * The log: per region a count line, then one line per folder directly in the region folder, by
 * name, with its target path or its code and reason. Never a file's name: the read asks Drive
 * for no file's name.
 */

const REFILE_DATE = /^(\d{2})-(\d{2})-(\d{4})$/;
const REFILE_UNDATED = 'undated';
const REFILE_NAME_SEP = ' - ';   // glow/sync.py SF_NAME_SEP: `<club> - <partner>`, a club two partners share
const REFILE_BATCH = 20;         // folders whose children one Drive query lists

function previewRefile() {
  runRefile_(false);
}

function refileExisting() {
  runRefile_(true);
}

/** Check REFILE_LIST and the Script Properties, then, under the script lock, read, plan, log; with `apply`, carry it out. */
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
    const read = readRefile_(config.regions, driveId, started + RUN_BUDGET_MS / 2);
    const plan = planRefile_(read.regions, list);
    logRefile_(plan, config, read, list.length, apply);
    if (apply) carryOutRefile_(plan, driveId, started + RUN_BUDGET_MS);
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
 * planRefile_'s regions, read by listing (Drive.Files.list on the Shared Drive `driveId`, `trashed = false`): each
 * region folder's folders with the number of files each holds, their folders, and theirs (names only). No file's
 * name is asked for. Once `readBy` passes (checked before each page), the region being read and every one after it
 * are left out (`unread`): a region is planned only when read in full.
 */
function readRefile_(regions, driveId, readBy) {
  const read = {}, unread = [];
  for (const c of regions) {
    const folders = unread.length ? null : readRefileRegion_(c.target, driveId, readBy);
    if (folders) read[c.region] = { id: c.target, folders: folders };
    else unread.push(c.region);
  }
  return { regions: read, unread: unread };
}

/** One region folder's tree as planRefile_ takes it, or null when a listing did not finish by `readBy`. */
function readRefileRegion_(regionId, driveId, readBy) {
  const folderQ = " and trashed = false and mimeType = '" + FOLDER_MIME + "'";
  const top = listSharedDrive_(driveId, "'" + regionId + "' in parents" + folderQ, 'id, name', readBy);
  if (!top.complete) return null;
  const roots = top.files.map(f => ({ id: f.id, name: f.name, files: 0, folders: [] }));
  /** The folders (and with `countFiles` the files) directly in `parents`, added to them; null when out of time. */
  const children = (parents, countFiles) => {
    const byId = new Map(parents.map(p => [p.id, p]));
    const added = [];
    for (let i = 0; i < parents.length; i += REFILE_BATCH) {
      const inBatch = '(' + parents.slice(i, i + REFILE_BATCH).map(p => "'" + p.id + "' in parents").join(' or ') + ')';
      const got = listSharedDrive_(driveId, inBatch + folderQ, 'id, name, parents', readBy);
      if (!got.complete) return null;
      for (const f of got.files) {
        const parent = (f.parents || []).map(id => byId.get(id)).filter(Boolean)[0];
        if (!parent) continue;
        const folder = { id: f.id, name: f.name, files: null, folders: [] };
        parent.folders.push(folder);
        added.push(folder);
      }
      if (!countFiles) continue;
      const files = listSharedDrive_(driveId, inBatch + " and trashed = false and mimeType != '" + FOLDER_MIME + "'", 'id, parents',
                                     readBy);
      if (!files.complete) return null;
      for (const f of files.files) {
        const parent = (f.parents || []).map(id => byId.get(id)).filter(Boolean)[0];
        if (parent) parent.files++;
      }
    }
    return added;
  };
  const second = children(roots, true);
  if (!second) return null;
  return children(second, false) ? roots : null;
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

/** The plan, per region: a count line, then each folder directly in the region folder by name (never a file's). */
function logRefile_(plan, config, read, rows, apply) {
  const verb = apply ? '' : 'would ';
  console.log((apply ? 'REFILE RUN' : 'REFILE DRY RUN (nothing changes)') + ': regions ' +
              config.regions.map(c => c.region).join(', ') + '; REFILE_LIST ' + rows + ' row(s)');
  for (const s of config.skipped) console.log(s);
  for (const region of read.unread) {
    console.log('TIME_BUDGET: ' + region + ' not read in full in time; not planned this run (the next run reads it again)');
  }
  const byName = (a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0);
  for (const region of Object.keys(read.regions)) {
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
}

/**
 * The plan's moves, in order, until `deadline` (checked before each folder, and after its re-check, before its
 * partner folder is made). Each: re-read by id (refileRecheck_), its partner and month folders found or made (once
 * per run each; one Drive did not confirm is not tried again this run), one Files.update moving it, a read-back.
 */
function carryOutRefile_(plan, driveId, deadline) {
  const never = new Set(configuredFolderIds_().all.concat([driveId]));
  const made = new Map();     // JSON [parent id, name] -> the id made, or {error} when Drive did not confirm it
  const failed = [], skipped = [];
  let moved = 0, madeCount = 0, left = 0;
  const late = () => Date.now() > deadline;
  const folderIn = (parent, name, have) => {
    if (have) return have;
    const k = JSON.stringify([parent, name]);
    if (!made.has(k)) {
      try {
        const got = Drive.Files.create({ name: name, mimeType: FOLDER_MIME, parents: [parent] }, null, { supportsAllDrives: true });
        if (!got || !got.id) throw new Error('Drive did not confirm the folder "' + name + '"');
        made.set(k, got.id);
        madeCount++;
      } catch (e) {
        made.set(k, { error: errorText_(e) });
      }
    }
    const id = made.get(k);
    if (typeof id !== 'string') throw new Error('the folder "' + name + '" was not made this run: ' + id.error);
    return id;
  };
  for (let i = 0; i < plan.refile.length; i++) {
    const e = plan.refile[i];
    if (late()) {
      left = plan.refile.length - i;
      break;
    }
    const where = e.region + ' "' + e.name + '"';
    try {
      if (never.has(e.id) || !never.has(e.to)) throw new Error('refused: a configured folder or the Shared Drive\'s root');
      if (!refileRecheck_(e)) {
        skipped.push('  skipped "' + e.name + '": moved or trashed (or renamed) since the read; the next run looks again');
        continue;
      }
      if (late()) {
        left = plan.refile.length - i;
        break;
      }
      const partnerId = folderIn(e.to, e.path[0], e.partnerId);
      const monthId = folderIn(partnerId, e.path[1], e.monthId);
      Drive.Files.update({}, e.id, null, { addParents: monthId, removeParents: e.to, supportsAllDrives: true });
      const now = Drive.Files.get(e.id, { fields: 'parents, trashed', supportsAllDrives: true });
      if (!now || now.trashed !== false || oneParent_(now) !== monthId) {
        failed.push('REFILE_FAILED ' + where + ': Drive answered the move but the read-back does not show it in ' + e.region + '/' +
                    e.path.join('/') + '; look for it by hand');
        continue;
      }
      moved++;
    } catch (err) {
      failed.push('REFILE_FAILED ' + where + ': ' + errorText_(err));
    }
  }
  console.log('done: ' + moved + ' folder(s) moved, ' + madeCount + ' partner or month folder(s) made, ' + skipped.length +
              ' skipped (moved or trashed since the read), ' + failed.length + ' failure(s)' +
              (left ? ', ' + left + ' folder(s) left for the next run (TIME_BUDGET)' : ''));
  for (const s of skipped) console.log(s);
  for (const f of failed) console.log(f);
  if (failed.length) throw new Error(failed.length + ' failure(s): ' + failed[0]);
}

/** Whether the planned folder, read by id now, is still a live folder of its name whose one parent is its region folder. */
function refileRecheck_(e) {
  const now = Drive.Files.get(e.id, { fields: 'id, name, mimeType, trashed, parents', supportsAllDrives: true });
  return !!now && now.mimeType === FOLDER_MIME && now.trashed === false && now.name === e.name && oneParent_(now) === e.to;
}
