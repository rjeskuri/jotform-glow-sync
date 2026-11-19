#!/usr/bin/env node
/**
 * Offline tests for the JS test harness itself: test/load_gs.js (what it
 * exports, the implicit-global watch) and test/helpers/js/csv.js. Also: the
 * .gs files load together and no top-level name is declared in two of them
 * (Apps Script has one namespace for every file; a second declaration would
 * silently replace the first, depending on file order).
 */
const fs = require('fs');
const os = require('os');
const path = require('path');
const loadGs = require('./load_gs');
const { check, finish } = require('./helpers/js/check');
const { parseCsv, readCsv } = require('./helpers/js/csv');

const read = f => fs.readFileSync(path.join(loadGs.GS_DIR, f), 'utf8');
const ALL = fs.readdirSync(loadGs.GS_DIR).filter(f => f.endsWith('.gs')).sort();

console.log('load_gs.js — what it exports');
const pureNames = loadGs.declarations(loadGs.PURE.map(read).join('\n'));
const pure = loadGs();
check('no names: every top-level function / const of the pure files (' + pureNames.length + ')',
      Object.keys(pure).sort().join() === pureNames.slice().sort().join() &&
      ['clubKey_', 'PARTNER_REGIONS', 'DUP_GUARD', 'buildDispatchRequest_', 'planClub_'].every(n => n in pure),
      Object.keys(pure).length + ' exported');
check('names given: exactly those', Object.keys(loadGs(['tidy_', 'TAB'])).join() === 'tidy_,TAB');
const everything = loadGs(null, ALL, { strict: true });
const allNames = loadGs.declarations(ALL.map(read).join('\n'));
check('all ' + ALL.length + ' .gs files load together, strict, and export every top-level name (' + allNames.length + ')',
      Object.keys(everything).length === allNames.length &&
      ['onAnyFormSubmit', 'sendSfPendingDigest', 'onOpen', 'syncFormChoicesFromMenu', 'syncFormChoicesHourly'].every(n => typeof everything[n] === 'function'));
const owner = {}, twice = [];
for (const f of ALL) {
  for (const n of loadGs.declarations(read(f))) {
    if (owner[n]) twice.push(n + ' (' + owner[n] + ', ' + f + ')');
    else owner[n] = f;
  }
}
check('no top-level name is declared in two .gs files', !twice.length, twice.join('; '));

console.log('\nload_gs.js — the implicit-global watch');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'glow-load-gs-'));
try {
  const atLoad = path.join(tmp, 'AtLoad.gs');
  fs.writeFileSync(atLoad, 'const DECLARED = 1;\nleakedAtLoad = 2;\nfunction fine_() { return DECLARED; }\n');
  let threw = '';
  try { loadGs(null, [atLoad], { strict: true }); } catch (e) { threw = e.message; }
  check('strict: a load that makes an undeclared global throws, naming it',
        /undeclared globals: leakedAtLoad \(AtLoad\.gs\)/.test(threw), threw);
  check('…without strict it loads (the tools load this way)', loadGs(null, [atLoad]).fine_() === 1);

  const later = path.join(tmp, 'Later.gs');
  fs.writeFileSync(later, 'function leak_() { leakedLater = 3; }\nfunction stubbed_() { return 0; }\n');
  const ctx = loadGs.sandbox([later], { SomeService: {} });
  ctx.stubbed_ = () => 1;   // a test replacing a declared function
  const before = loadGs.strayGlobals(ctx);
  ctx.leak_();
  const after = loadGs.strayGlobals(ctx);
  check('a sandbox: its globals and a replaced function are not stray; a function that makes a global is caught',
        !before.length && after.join() === 'leakedLater (Later.gs)', before.join() + ' / ' + after.join());
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}

console.log('\nhelpers/js/csv.js');
check('quoted fields: commas, doubled quotes, newlines; a \\r dropped; a last line without a newline',
      JSON.stringify(parseCsv('a,"b, c","say ""hi""","line 1\nline 2"\r\nx,,z')) ===
      JSON.stringify([['a', 'b, c', 'say "hi"', 'line 1\nline 2'], ['x', '', 'z']]));
check('an empty field at the end of a line is kept', JSON.stringify(parseCsv('a,\nb,c\n')) === JSON.stringify([['a', ''], ['b', 'c']]));
const fixture = readCsv(path.join(__dirname, 'fixtures', 'enrollment_sample.csv'));
check('readCsv: the fixture, its header first (a byte-order mark would be dropped)',
      fixture.length > 20 && fixture[0][0] === 'Timestamp' && fixture[0].length === 11, fixture[0][0]);

finish();
