#!/usr/bin/env node
/**
 * Offline parity harness: runs the Apps Script normalization + ID logic
 * (Normalize.gs, Ids.gs, Regions.gs) in Node against an enrollment CSV and
 * checks it agrees with the Python tool. No Google APIs involved.
 *
 * Always runs on the synthetic fixture (test/fixtures/, fictional names, so
 * this passes on a fresh clone and in CI). When the real export is present
 * it runs on that too, with the real numbers pinned:
 *
 *   node test/parity_test.js                       # fixture (+ real data if data/ has it)
 *   CSV=path/to/export.csv node test/parity_test.js
 *   PARITY_REAL=0 node test/parity_test.js         # fixture only
 *
 * Real-data club keys come from test/helpers/py_clubs.py (spawned; set
 * PY_CLUBS=<json file> to supply them instead, PYTHON=<interpreter> to pick one).
 */
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const loadGs = require('./load_gs');

const REPO = path.resolve(__dirname, '..');
const gs = loadGs(['tidy_', 'key_', 'asciiCode_', 'parseRoster_', 'lastName_', 'clubCode_',
                   'mintGirlId_', 'PARTNER_REGIONS', 'PARTNER_REGION_NOTES', 'RESPONSE_COLS',
                   'REGIONS']);
const REGIONS = new Set(gs.REGIONS);   // the canonical list lives in Config.gs (backlog 38)

let failures = 0;
function check(label, cond, detail) {
  if (!cond) { failures++; console.log('  FAIL ' + label + (detail ? ' :: ' + detail : '')); }
  else console.log('  ok   ' + label + (detail ? ' :: ' + detail : ''));
}

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

/** Replicate readResponses_ over a CSV: last submission per (partner, club) wins. */
function readClubs(csvPath) {
  const csv = parseCsv(fs.readFileSync(csvPath, 'utf8').replace(/^﻿/, ''));
  const header = csv[0].map(h => h.toLowerCase());
  const col = frag => header.findIndex(h => h.includes(frag));
  const iP = col(gs.RESPONSE_COLS.partner), iC = col(gs.RESPONSE_COLS.club),
        iR = col(gs.RESPONSE_COLS.roster);
  const byIdentity = {};
  for (let r = 1; r < csv.length; r++) {
    const row = csv[r];
    if (!row || row.length <= Math.max(iP, iC, iR)) continue;
    const partner = gs.tidy_(row[iP]), club = gs.tidy_(row[iC]);
    if (!club) continue;   // mirrors read_sheet (readResponses_ also drops partner-less rows)
    const parsed = gs.parseRoster_(row[iR]);
    if (!parsed.names.length) continue;
    byIdentity[gs.key_(partner) + '||' + gs.key_(club)] =
      { partner, club, names: parsed.names, duplicates: parsed.duplicates, sourceRow: r + 1 };
  }
  return Object.values(byIdentity);
}

/** Mint IDs exactly as rebuildRosterFromResponses would. */
function mintIds(clubs) {
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
  return { registry, ids, dupClubs };
}

/** Every tracked-looking text file: anything that could be installed or published. */
function publicText(excludeDirs) {
  const skipDirs = new Set(['node_modules', 'data', 'backups', 'credentials', '.git', '.venv',
                            'venv', '__pycache__', 'worktrees', ...excludeDirs]);
  const exts = /\.(gs|md|py|js|json|yml|yaml|sh|csv|txt|toml)$/;
  const out = [];
  (function walk(dir) {
    for (const name of fs.readdirSync(dir)) {
      const full = path.join(dir, name);
      const rel = path.relative(REPO, full);
      if (skipDirs.has(name) || excludeDirs.includes(rel)) continue;
      if (name.startsWith('.') && name !== '.claude' && name !== '.github') continue;
      const st = fs.statSync(full);
      if (st.isDirectory()) walk(full);
      else if (exts.test(name) || name === 'Makefile' || name === 'CLAUDE.md') {
        out.push(fs.readFileSync(full, 'utf8'));
      }
    }
  })(REPO);
  return out.join('\n').toLowerCase();
}

const mask = id => id.replace(/-[A-Z0-9]+-(\d{3})$/, '-XXXX-$1');

function runDataset({ name, csvPath, pyClubs, pins, real }) {
  const clubs = readClubs(csvPath);
  const { registry, ids, dupClubs } = mintIds(clubs);
  console.log(`\n${name}: parsed ${clubs.length} clubs, ${ids.length} girls`);

  const unique = new Set(ids.map(x => x.id));
  check('every girl ID is unique', unique.size === ids.length, unique.size + ' unique / ' + ids.length);
  check('ID format CLUBCODE-LASTCODE-NNN',
        ids.every(x => /^[A-Z0-9]{1,8}-[A-Z0-9]{1,12}-\d{3}$/.test(x.id)), 'e.g. ' + mask(ids[0].id));
  const codes = new Set(Object.values(registry.byCode).map(e => e.code));
  check('club codes unique', codes.size === Object.keys(registry.byKey).length,
        codes.size + ' codes for ' + Object.keys(registry.byKey).length + ' clubs');
  check('no empty last-name codes', ids.every(x => !/--/.test(x.id)));

  const accented = ids.filter(x => /[À-ÿ]/.test(x.name));
  check('accented surnames produce ASCII ids',
        accented.length > 0 && accented.every(x => /^[A-Z0-9-]+$/.test(x.id)),
        accented.length + ' accented names, sample ' + (accented[0] ? mask(accented[0].id) : 'n/a'));

  const stems = {};
  ids.forEach(x => { const s = x.id.replace(/-\d{3}$/, ''); (stems[s] = stems[s] || []).push(x.id); });
  const shared = Object.entries(stems).filter(([, v]) => v.length > 1);
  check('shared surnames get distinct numbers',
        shared.length > 0 && shared.every(([, v]) => new Set(v).size === v.length),
        shared.length + ' surname groups share a club, largest ' + Math.max(0, ...shared.map(([, v]) => v.length)));

  check('duplicate-name clubs flagged', dupClubs.length > 0, dupClubs.length + ' clubs flagged for review');
  check('no invisible characters survive', ids.every(x => !/[​-‏⁠﻿]/.test(x.name)));
  check('list numbering stripped', ids.every(x => !/^\d+[.)]/.test(x.name)),
        'sample names: ' + ids.slice(0, 2).map(x => x.name.replace(/\S/g, 'x')).join(', '));

  if (pins) {
    check(`pinned counts: ${pins.clubs} clubs / ${pins.girls} girls / ${pins.duplicate_name_clubs} duplicate-name clubs`,
          clubs.length === pins.clubs && ids.length === pins.girls && dupClubs.length === pins.duplicate_name_clubs,
          `${clubs.length} / ${ids.length} / ${dupClubs.length}`);
  }

  // regions: the real partners must all be covered by Regions.gs; the fixture's are fictional
  const derived = {};
  Object.keys(gs.PARTNER_REGIONS).forEach(p => { derived[gs.key_(p)] = gs.PARTNER_REGIONS[p]; });
  const partners = [...new Set(clubs.map(c => gs.key_(c.partner)))];
  const noRegion = partners.filter(p => !REGIONS.has(derived[p]));
  if (real) {
    check('every sheet partner has a derived region', noRegion.length === 0,
          (partners.length - noRegion.length) + '/' + partners.length +
          (noRegion.length ? ' — missing: ' + noRegion.join('; ') + ' (re-run tools/derive_partner_regions.py <csv> --write)' : ''));
    if (pins && pins.partners) check(`pinned ${pins.partners} partners`, partners.length === pins.partners, String(partners.length));
  } else {
    check('fixture partners are fictional: none has a derived region', noRegion.length === partners.length,
          partners.length + ' partners, Regions.gs coverage is checked with real data only');
    if (pins && pins.partners) check(`pinned ${pins.partners} partners`, partners.length === pins.partners, String(partners.length));
  }
  check('every derived region has a note for the Partners tab',
        Object.keys(gs.PARTNER_REGIONS).every(p => gs.PARTNER_REGION_NOTES[p]));

  // no enrolled girl's name appears in anything that gets installed or published
  // (fixture mode only proves the scan runs: the tests themselves legitimately
  // contain the fictional names, so test/ is excluded there and only there)
  const haystack = publicText(real ? [] : ['test']);
  const leaked = [...new Set(ids.map(x => x.name.toLowerCase()))]
    .filter(n => n.split(' ').length >= 2 && haystack.includes(n));
  check(real ? "no enrolled girl's name appears in scripts, docs, tests or config"
             : 'leak scan runs (fictional names; test/ excluded in fixture mode)',
        leaked.length === 0,
        leaked.length ? leaked.length + ' name(s) found — replace with fictional examples' : 'scanned ' + ids.length + ' names');

  // parity with the Python tool's club canonicalization
  if (pyClubs) {
    const jsKeys = new Set(clubs.map(c => gs.key_(c.partner) + '||' + gs.key_(c.club)));
    const pyKeys = new Set(pyClubs);
    const onlyJs = [...jsKeys].filter(k => !pyKeys.has(k));
    const onlyPy = [...pyKeys].filter(k => !jsKeys.has(k));
    check('club set matches the Python tool exactly', onlyJs.length === 0 && onlyPy.length === 0,
          onlyJs.length + ' only-JS, ' + onlyPy.length + ' only-Python');
  } else {
    check('club set matches the Python tool exactly', false, 'no Python club list available');
  }
}

// ---- datasets ----
const fixtureCsv = path.join(__dirname, 'fixtures', 'enrollment_sample.csv');
const expected = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'expected.json'), 'utf8'));
runDataset({ name: 'fixture', csvPath: fixtureCsv, pyClubs: expected.py_clubs, pins: expected, real: false });

const realCsv = process.env.CSV || path.join(REPO, 'data', 'enrollment_2026-08-24.csv');
if (process.env.PARITY_REAL !== '0' && fs.existsSync(realCsv)) {
  let pyClubs = null;
  if (process.env.PY_CLUBS) {
    pyClubs = JSON.parse(fs.readFileSync(process.env.PY_CLUBS, 'utf8'));
  } else {
    const venv = path.join(REPO, '.venv', 'bin', 'python3');
    const python = process.env.PYTHON || (fs.existsSync(venv) ? venv : 'python3');
    const r = spawnSync(python, [path.join(__dirname, 'helpers', 'py_clubs.py'), realCsv], { encoding: 'utf8' });
    if (r.status === 0) pyClubs = JSON.parse(r.stdout);
    else console.log('  !  py_clubs.py failed: ' + (r.stderr || r.error));
  }
  // the 2026-08-24 export's numbers are pinned wherever that file lives (CSV= may point outside the checkout)
  const pins = path.basename(realCsv) === 'enrollment_2026-08-24.csv'
    ? { clubs: 328, girls: 6210, duplicate_name_clubs: 16, partners: 47 } : null;
  runDataset({ name: 'real data (' + path.relative(REPO, realCsv) + ')', csvPath: realCsv, pyClubs, pins, real: true });
} else {
  console.log('\nreal data: skipped (no ' + path.relative(REPO, realCsv) + ')');
}

console.log('\n' + (failures ? failures + ' FAILURES' : 'ALL CHECKS PASSED'));
process.exit(failures ? 1 : 0);
