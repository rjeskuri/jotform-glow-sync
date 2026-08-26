/**
 * Offline harness: runs the Apps Script normalization + ID logic against the
 * REAL enrollment CSV, with no Google APIs involved. Proves the .gs code works
 * before it ever gets pasted into the spreadsheet.
 */
const fs = require('fs');
const path = require('path');

const GS = '/Users/ryaneskuri/jotform-glow-sync/appsscript';

// Load the pure-logic files (no SpreadsheetApp calls at top level).
let src = '';
for (const f of ['Normalize.gs', 'Ids.gs', 'Regions.gs']) {
  src += fs.readFileSync(path.join(GS, f), 'utf8') + '\n';
}
// Config constants used by the loaded functions
src = 'const TAB={RESPONSES:"Enrollment Responses"};' +
      'const RESPONSE_COLS={partner:"partner organization name",' +
      'club:"club name",roster:"please list the full name"};\n' + src;
// Expose the private (underscore) helpers to the harness
src += '\nmodule.exports={tidy_,key_,asciiCode_,parseRoster_,lastName_,' +
       'clubCode_,mintGirlId_,PARTNER_REGIONS,PARTNER_REGION_NOTES};\n';

const tmp = path.join(require('os').tmpdir(), 'glow_gs_bundle.js');
fs.writeFileSync(tmp, src);
const gs = require(tmp);

// ---- minimal CSV parser (handles quoted fields with embedded newlines) ----
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

const csv = parseCsv(fs.readFileSync(process.env.CSV ||
  '/Users/ryaneskuri/jotform-glow-sync/data/enrollment_2026-08-24.csv', 'utf8'));
const header = csv[0].map(h => h.toLowerCase());
const col = frag => header.findIndex(h => h.includes(frag));
const iP = col('partner organization name'), iC = col('club name'),
      iR = col('please list the full name');

// ---- replicate readResponses_ over the CSV ----
const byIdentity = {};
for (let r = 1; r < csv.length; r++) {
  const row = csv[r];
  if (!row || row.length <= Math.max(iP, iC, iR)) continue;
  const partner = gs.tidy_(row[iP]), club = gs.tidy_(row[iC]);
  if (!club) continue;
  const parsed = gs.parseRoster_(row[iR]);
  if (!parsed.names.length) continue;
  byIdentity[gs.key_(partner) + '||' + gs.key_(club)] =
    { partner, club, names: parsed.names, duplicates: parsed.duplicates, sourceRow: r + 1 };
}
const clubs = Object.values(byIdentity);

// ---- mint IDs exactly as rebuildRosterFromResponses would ----
const registry = { byKey: {}, byCode: {}, added: [] };
const sequence = {};
const ids = [], dupClubs = [];
for (const entry of clubs) {
  const code = gs.clubCode_(registry, entry.partner, entry.club);
  if (entry.duplicates.length) dupClubs.push(entry.club);
  for (const name of entry.names) {
    ids.push({ id: gs.mintGirlId_(sequence, code, name), club: entry.club, name });
  }
}

// ---- assertions ----
let failures = 0;
function check(label, cond, detail) {
  if (!cond) { failures++; console.log('  FAIL ' + label + (detail ? ' :: ' + detail : '')); }
  else console.log('  ok   ' + label + (detail ? ' :: ' + detail : ''));
}

console.log('Parsed ' + clubs.length + ' clubs, ' + ids.length + ' girls\n');

const unique = new Set(ids.map(x => x.id));
check('every girl ID is unique', unique.size === ids.length,
      unique.size + ' unique / ' + ids.length);

// IDs contain a real surname, so never print one unmasked
const mask = id => id.replace(/-[A-Z0-9]+-(\d{3})$/, '-XXXX-$1');
check('ID format CLUBCODE-LASTCODE-NNN',
      ids.every(x => /^[A-Z0-9]{1,8}-[A-Z0-9]{1,12}-\d{3}$/.test(x.id)),
      'e.g. ' + mask(ids[0].id));

const codes = new Set(Object.values(registry.byCode).map(e => e.code));
check('club codes unique', codes.size === Object.keys(registry.byKey).length,
      codes.size + ' codes for ' + Object.keys(registry.byKey).length + ' clubs');

check('no empty last-name codes', ids.every(x => !/--/.test(x.id)));

// accents folded
const accented = ids.filter(x => /[À-ÿ]/.test(x.name));
check('accented surnames produce ASCII ids', accented.every(x => /^[A-Z0-9-]+$/.test(x.id)),
      accented.length + ' accented names, sample ' +
      (accented[0] ? mask(accented[0].id) : 'n/a'));

// same surname within a club gets distinct sequence numbers
const stems = {};
ids.forEach(x => { const s = x.id.replace(/-\d{3}$/, ''); (stems[s] = stems[s] || []).push(x.id); });
const shared = Object.entries(stems).filter(([, v]) => v.length > 1);
check('shared surnames get distinct numbers',
      shared.every(([, v]) => new Set(v).size === v.length),
      shared.length + ' surname groups share a club, largest ' +
      Math.max(0, ...shared.map(([, v]) => v.length)));

// duplicate-name clubs still detected
check('duplicate-name clubs flagged', dupClubs.length > 0,
      dupClubs.length + ' clubs flagged for review');

// invisible characters gone
check('no invisible characters survive',
      ids.every(x => !/[​-‏⁠﻿]/.test(x.name)));

// numbering stripped
check('list numbering stripped', ids.every(x => !/^\d+[.)]/.test(x.name)),
      'sample names: ' + ids.slice(0, 2).map(x => x.name.replace(/\S/g, 'x')).join(', '));

// every partner in the sheet has a derived region (Regions.gs is current)
const REGIONS = new Set(['Africa', 'Asia', 'Latin America', 'U.S']);
const derived = {};
Object.keys(gs.PARTNER_REGIONS).forEach(p => { derived[gs.key_(p)] = gs.PARTNER_REGIONS[p]; });
const partners = [...new Set(clubs.map(c => gs.key_(c.partner)))];
const noRegion = partners.filter(p => !REGIONS.has(derived[p]));
check('every sheet partner has a derived region', noRegion.length === 0,
      (partners.length - noRegion.length) + '/' + partners.length +
      (noRegion.length ? ' — missing: ' + noRegion.join('; ') +
       ' (re-run tools/derive_partner_regions.py --write)' : ''));
check('every derived region has a note for the Partners tab',
      Object.keys(gs.PARTNER_REGIONS).every(p => gs.PARTNER_REGION_NOTES[p]));

// no real girl's name appears in anything that gets installed or published:
// the Sheet scripts (form help text, messages), docs, tools
const publicText = [];
for (const dir of ['appsscript', 'tools', 'docs', 'test']) {
  for (const f of fs.readdirSync(path.join(GS, '..', dir))) {
    if (/\.(gs|md|py|js)$/.test(f)) publicText.push(fs.readFileSync(path.join(GS, '..', dir, f), 'utf8'));
  }
}
publicText.push(fs.readFileSync(path.join(GS, '..', 'README.md'), 'utf8'));
const haystack = publicText.join('\n').toLowerCase();
const leaked = [...new Set(ids.map(x => x.name.toLowerCase()))]
  .filter(n => n.split(' ').length >= 2 && haystack.includes(n));
check('no enrolled girl\'s name appears in scripts, docs or tools', leaked.length === 0,
      leaked.length ? leaked.length + ' name(s) found — replace with fictional examples' : 'scanned ' + ids.length + ' names');

// ---- parity with the Python tool's club canonicalization ----
const pyClubs = JSON.parse(fs.readFileSync(process.env.PY_CLUBS ||
  '/Users/ryaneskuri/jotform-glow-sync/data/py_clubs.json', 'utf8'));
const jsKeys = new Set(clubs.map(c => gs.key_(c.partner) + '||' + gs.key_(c.club)));
const pyKeys = new Set(pyClubs);
const onlyJs = [...jsKeys].filter(k => !pyKeys.has(k));
const onlyPy = [...pyKeys].filter(k => !jsKeys.has(k));
check('club set matches the Python tool exactly',
      onlyJs.length === 0 && onlyPy.length === 0,
      onlyJs.length + ' only-JS, ' + onlyPy.length + ' only-Python');

console.log('\n' + (failures ? failures + ' FAILURES' : 'ALL CHECKS PASSED'));
process.exit(failures ? 1 : 0);
