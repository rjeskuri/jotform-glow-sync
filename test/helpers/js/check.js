'use strict';
/**
 * The JS tests' one assertion and their last line (test/*_test.js):
 *
 *   const { check, finish } = require('./helpers/js/check');
 *   check('label', cond, 'detail shown either way');   // "  ok   label :: detail" or "  FAIL …"
 *   finish();   // "ALL CHECKS PASSED", or "N FAILURES" and exit 1
 */
let failures = 0;

function check(label, cond, detail) {
  console.log((cond ? '  ok   ' : '  FAIL ') + label + (detail ? ' :: ' + detail : ''));
  if (!cond) failures++;
  return !!cond;
}

function finish() {
  console.log('\n' + (failures ? failures + ' FAILURES' : 'ALL CHECKS PASSED'));
  process.exit(failures ? 1 : 0);
}

module.exports = { check, finish };
