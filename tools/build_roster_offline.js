#!/usr/bin/env node
/**
 * Build the Roster / ClubRegistry / Partners / ReviewQueue / Audit tabs on
 * this machine, from an enrollment CSV, using the SAME code that runs inside
 * the spreadsheet (appsscript/*.gs). No Google APIs involved.
 *
 * Why: it lets the one-row-per-girl source of truth be produced and checked
 * before the sheet is touched, and uploaded in one go (tools/upload_roster.py)
 * instead of waiting for someone to paste and run the Apps Script. Because the
 * ID-minting code is literally the same file, the sheet's own rebuild later
 * reproduces every ID exactly.
 *
 * Existing state: the builder mirrors rebuildRosterFromResponses in Roster.gs
 * exactly, including what it does to tabs that already have rows:
 *   Roster        existing rows kept verbatim (IDs preserved), reactivations
 *                 flipped, new girls appended
 *   ClubRegistry  existing rows kept, new clubs appended
 *   Partners      existing rows kept, blank regions filled, new partners added
 *   ReviewQueue   issues appended unless the same open issue is already there
 *   Audit         one row appended
 * By default the previous local build (data/roster_build/) is the existing
 * state. Before uploading over a sheet that has been edited, export its live
 * tabs (sheets_client.py export-all DIR) and pass --existing DIR.
 *
 * Usage:
 *   node tools/build_roster_offline.js data/enrollment_2026-08-24.csv [--out data/roster_build] [--existing DIR]
 */
const fs = require('fs');
const path = require('path');
const os = require('os');

const REPO = path.resolve(__dirname, '..');
const GS = path.join(REPO, 'appsscript');

// ---------------------------------------------------------------- arguments
const argv = process.argv.slice(2);
if (!argv.length) {
  console.error('usage: node tools/build_roster_offline.js <enrollment.csv> [--out DIR] [--existing DIR]');
  process.exit(2);
}
const csvPath = argv[0];
function opt(name, dflt) {
  const i = argv.indexOf(name);
  return i === -1 ? dflt : argv[i + 1];
}
const outDir = path.resolve(REPO, opt('--out', 'data/roster_build'));
const existingDir = opt('--existing', fs.existsSync(path.join(outDir, 'Roster.csv')) ? outDir : null);

// local-time stamps, same text format Roster.gs writes (today_ / now_)
function pad(n) { return (n < 10 ? '0' : '') + n; }
const nowDate = new Date();
const TODAY = nowDate.getFullYear() + '-' + pad(nowDate.getMonth() + 1) + '-' + pad(nowDate.getDate());
const NOW = TODAY + ' ' + pad(nowDate.getHours()) + ':' + pad(nowDate.getMinutes()) + ':' + pad(nowDate.getSeconds());

// ------------------------------------------------ load the real .gs code
// Only the pure-logic files; Roster.gs/Menu.gs call SpreadsheetApp.
let src = '';
for (const f of ['Config.gs', 'Normalize.gs', 'Ids.gs', 'Regions.gs']) {
  src += fs.readFileSync(path.join(GS, f), 'utf8') + '\n';
}
src += '\nmodule.exports={TAB,ROSTER_COLS,RESPONSE_COLS,STATUS,PARTNER_REGIONS,PARTNER_REGION_NOTES,' +
       'tidy_,key_,asciiCode_,parseRoster_,lastName_,clubCode_,mintGirlId_};\n';
const bundle = path.join(os.tmpdir(), 'glow_gs_bundle_' + process.pid + '.js');
fs.writeFileSync(bundle, src);
const gs = require(bundle);
fs.unlinkSync(bundle);

const REVIEW_COLS = ['raised', 'issue', 'partner', 'club', 'detail', 'resolved'];
const PARTNER_COLS = ['partner', 'region', 'notes'];
const CLUB_COLS = ['club_code', 'partner', 'club', 'created'];
const AUDIT_COLS = ['when', 'action', 'detail'];

// ------------------------------------------------------------- CSV helpers
function parseCsv(text) {
  const rows = [];
  let row = [], field = '', inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') inQuotes = false;
      else field += c;
    } else if (c === '"') inQuotes = true;
    else if (c === ',') { row.push(field); field = ''; }
    else if (c === '\n') { row.push(field); rows.push(row); row = []; field = ''; }
    else if (c !== '\r') field += c;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  return rows;
}
function csvCell(v) {
  const s = v == null ? '' : String(v);
  return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}
function writeCsv(file, header, rows) {
  const lines = [header, ...rows].map(r => r.map(csvCell).join(','));
  fs.writeFileSync(file, lines.join('\n') + '\n');
}
function readCsvFile(file) {
  return parseCsv(fs.readFileSync(file, 'utf8').replace(/^﻿/, ''));
}
function readExisting(name, cols) {
  // rows of an existing tab as arrays padded to `cols`, or [] if absent
  if (!existingDir) return [];
  const file = path.join(existingDir, name + '.csv');
  if (!fs.existsSync(file)) return [];
  return readCsvFile(file).slice(1).map(r => {
    const out = cols.map((_, j) => (r[j] == null ? '' : r[j]));
    return out;
  }).filter(r => r.some(v => String(v).trim()));
}

// ------------------------------------- readResponses_ (mirror of Normalize.gs)
const csv = readCsvFile(csvPath);
const header = csv[0].map(h => String(h).toLowerCase());
function col(fragment) {
  const i = header.findIndex(h => h.includes(fragment));
  if (i === -1) throw new Error('No column containing "' + fragment + '"');
  return i;
}
const iPartner = col(gs.RESPONSE_COLS.partner);
const iClub = col(gs.RESPONSE_COLS.club);
const iRoster = col(gs.RESPONSE_COLS.roster);

const byIdentity = {};
for (let r = 1; r < csv.length; r++) {
  const row = csv[r];
  if (!row || row.length <= Math.max(iPartner, iClub, iRoster)) continue;
  const partner = gs.tidy_(row[iPartner]);
  const club = gs.tidy_(row[iClub]);
  if (!partner || !club) continue;
  const parsed = gs.parseRoster_(row[iRoster]);
  if (!parsed.names.length) continue;
  byIdentity[gs.key_(partner) + '||' + gs.key_(club)] = {
    partner, club, names: parsed.names, duplicates: parsed.duplicates, sourceRow: r + 1,
  };
}
const clubs = Object.values(byIdentity);

// ------------------------------------------ existing state (loadIdState_)
const registry = { byKey: {}, byCode: {}, added: [] };
const sequence = {};
const registryRows = readExisting('ClubRegistry', CLUB_COLS);
for (const row of registryRows) {
  const code = gs.tidy_(row[0]), partner = gs.tidy_(row[1]), club = gs.tidy_(row[2]);
  if (!code) continue;
  const entry = { code, partner, club };
  registry.byKey[gs.key_(partner) + '||' + gs.key_(club)] = entry;
  registry.byCode[code] = entry;
}
const existingRows = readExisting('Roster', gs.ROSTER_COLS).map(v => {
  const row = {};
  gs.ROSTER_COLS.forEach((c, j) => { row[c] = v[j]; });
  return row;
});
for (const row of existingRows) {
  const id = gs.tidy_(row.girl_id);
  const m = id.match(/^(.*)-(\d+)$/);
  if (!m) continue;
  const stem = m[1], n = parseInt(m[2], 10);
  if (!sequence[stem] || n > sequence[stem]) sequence[stem] = n;
}
const existingByClub = {};
for (const row of existingRows) {
  const ck = gs.key_(row.partner) + '||' + gs.key_(row.club);
  (existingByClub[ck] = existingByClub[ck] || []).push(row);
}

// ------------------------------------------------ regions (loadPartnerRegions_)
const regions = {};
Object.keys(gs.PARTNER_REGIONS).forEach(p => {
  if (gs.PARTNER_REGIONS[p]) regions[gs.key_(p)] = gs.PARTNER_REGIONS[p];
});
const partnerRows = readExisting('Partners', PARTNER_COLS);
for (const row of partnerRows) {
  const partner = gs.tidy_(row[0]), region = gs.tidy_(row[1]);
  if (partner && region) regions[gs.key_(partner)] = region;   // tab wins
}

// ------------------------------------- rebuildRosterLocked_ (mirror)
const rosterOut = existingRows.map(r => gs.ROSTER_COLS.map(c => (r[c] == null ? '' : r[c])));
const issues = [], partnersSeen = {}, noRegion = {};
let newGirls = 0, reactivated = 0;

for (const entry of clubs) {
  partnersSeen[gs.key_(entry.partner)] = entry.partner;
  const ck = gs.key_(entry.partner) + '||' + gs.key_(entry.club);
  const region = regions[gs.key_(entry.partner)] || '';
  if (!region) noRegion[gs.key_(entry.partner)] = entry.partner;

  if (entry.duplicates.length) {
    issues.push({
      issue: 'Same name listed twice', partner: entry.partner, club: entry.club,
      detail: entry.duplicates.join(', ') +
        ' — if these are different girls, add something to tell them apart in ' +
        'the sheet (e.g. "Anh Nguyen (A)"), then re-run.',
    });
  }

  const code = gs.clubCode_(registry, entry.partner, entry.club);
  const current = existingByClub[ck] || [];
  const byName = {};
  current.forEach(row => { byName[gs.key_(row.full_name)] = row; });

  for (const name of entry.names) {
    const found = byName[gs.key_(name)];
    if (found) {
      if (found.status === gs.STATUS.INACTIVE) {
        found.status = gs.STATUS.ACTIVE; found.removed_date = '';
        const idx = existingRows.indexOf(found);
        rosterOut[idx] = gs.ROSTER_COLS.map(c => (found[c] == null ? '' : found[c]));
        reactivated++;
      }
      continue;
    }
    rosterOut.push([
      gs.mintGirlId_(sequence, code, name), entry.partner, entry.club, region,
      name, gs.lastName_(name), gs.STATUS.ACTIVE, TODAY, '',
      gs.TAB.RESPONSES + '!' + entry.sourceRow,
    ]);
    newGirls++;
  }

  const submitted = {};
  entry.names.forEach(n => { submitted[gs.key_(n)] = true; });
  const vanished = current.filter(row =>
    row.status === gs.STATUS.ACTIVE && !submitted[gs.key_(row.full_name)]);
  if (vanished.length) {
    issues.push({
      issue: 'Girls missing from the latest enrollment', partner: entry.partner, club: entry.club,
      detail: vanished.length + ' girl(s) on file are not in the newest submission. ' +
        'They are still active — use the Roster Modification form to remove anyone ' +
        'who has actually left.',
    });
  }
}

Object.keys(noRegion).forEach(k => {
  issues.push({
    issue: 'Partner has no region', partner: noRegion[k], club: '',
    detail: 'Girls were added without a region, so they will not reach any regional ' +
      'attendance form. Fill in the region on the Partners tab, then run GLOW → Refresh regions.',
  });
});

// ------------------------------------------------------------------ output
fs.mkdirSync(outDir, { recursive: true });

writeCsv(path.join(outDir, 'Roster.csv'), gs.ROSTER_COLS, rosterOut);

// saveClubRegistry_: existing rows verbatim, new clubs appended
const registryOut = registryRows.slice();
for (const e of registry.added) registryOut.push([e.code, e.partner, e.club, TODAY]);
writeCsv(path.join(outDir, 'ClubRegistry.csv'), CLUB_COLS, registryOut);

// seedPartners_: existing rows kept; blank region (and blank note) filled; new appended
const derivedNotes = {};
Object.keys(gs.PARTNER_REGIONS).forEach(p => { derivedNotes[gs.key_(p)] = gs.PARTNER_REGION_NOTES[p] || ''; });
const derived = {};
Object.keys(gs.PARTNER_REGIONS).forEach(p => { derived[gs.key_(p)] = gs.PARTNER_REGIONS[p]; });
const known = {};
const partnersOut = partnerRows.map(r => {
  const k = gs.key_(r[0]);
  if (!k) return r;
  known[k] = true;
  if (!gs.tidy_(r[1]) && derived[k]) {
    return [r[0], derived[k], gs.tidy_(r[2]) ? r[2] : derivedNotes[k]];
  }
  return r;
});
Object.keys(partnersSeen).sort().forEach(k => {
  if (!k || known[k]) return;
  partnersOut.push([partnersSeen[k], derived[k] || '',
                    derived[k] ? derivedNotes[k] : 'region needed']);
});
writeCsv(path.join(outDir, 'Partners.csv'), PARTNER_COLS, partnersOut);

// review_: append issues not already open
const reviewRows = readExisting('ReviewQueue', REVIEW_COLS);
const open = {};
for (const r of reviewRows) {
  if (!gs.tidy_(r[5])) open[gs.key_(r[1]) + '||' + gs.key_(r[2]) + '||' + gs.key_(r[3])] = true;
}
const reviewOut = reviewRows.slice();
let newIssues = 0;
for (const i of issues) {
  if (open[gs.key_(i.issue) + '||' + gs.key_(i.partner) + '||' + gs.key_(i.club)]) continue;
  reviewOut.push([TODAY, i.issue, i.partner, i.club, i.detail, '']);
  newIssues++;
}
writeCsv(path.join(outDir, 'ReviewQueue.csv'), REVIEW_COLS, reviewOut);

const missingRegion = Object.keys(noRegion).length;
const summary = clubs.length + ' clubs, ' + newGirls + ' new girls, ' + reactivated +
  ' reactivated, ' + issues.length + ' for review' +
  (missingRegion ? ', ' + missingRegion + ' partner(s) missing a region' : '');
// Audit.csv holds only THIS run's row: upload_roster.py appends it to the sheet
writeCsv(path.join(outDir, 'Audit.csv'), AUDIT_COLS, [[NOW, 'build_roster_offline', summary]]);

console.log(summary + ' (' + newIssues + ' newly queued)');
console.log('Roster rows: ' + rosterOut.length + '  (' + existingRows.length + ' pre-existing' +
            (existingDir ? ' from ' + path.relative(REPO, existingDir) : '') + ')');
console.log('Wrote ' + path.relative(REPO, outDir) + '/{Roster,ClubRegistry,Partners,ReviewQueue,Audit}.csv');
