#!/usr/bin/env node
'use strict';
/**
 * Parse every Apps Script file with V8 so a syntax error can never reach the
 * live sheet through `clasp push` (a broken file breaks EVERY form handler).
 * Also loads the pure-logic files together, which catches a reference to a
 * symbol that was renamed in another file.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const loadGs = require('../test/load_gs');

const dir = loadGs.GS_DIR;
const files = fs.readdirSync(dir).filter(f => f.endsWith('.gs')).sort();
let failures = 0;
for (const f of files) {
  try {
    new vm.Script(fs.readFileSync(path.join(dir, f), 'utf8'), { filename: f });
  } catch (err) {
    failures++;
    console.log('  FAIL ' + f + ' :: ' + err.message);
  }
}
try {
  loadGs(['TAB', 'ROSTER_COLS', 'parseRoster_', 'planClub_', 'buildDispatchRequest_']);
} catch (err) {
  failures++;
  console.log('  FAIL pure files do not load together :: ' + err.message);
}
if (failures) {
  console.log('gs: ' + failures + ' FAILURE(S)');
  process.exit(1);
}
console.log('gs: ' + files.length + ' files parse');
