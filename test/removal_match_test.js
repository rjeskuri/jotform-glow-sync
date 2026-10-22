#!/usr/bin/env node
/**
 * Ticket #112: a REMOVE on the Club Roster Form that names a girl of the club
 * with a near spelling — capitals, accents and punctuation ignored — is
 * resolved by the matcher instead of raising "Removal did not match anyone"
 * (appsscript/RosterOps.gs planModification_, FormHandlers.gs
 * handleRosterChange_ / sendChangeConfirmation_).
 *
 * The rule under test ("ignoring capitals, accents and punctuation"): two
 * names are the same when their letters and digits (\p{L}\p{N}, any script)
 * agree once case and accents are folded — ANYTHING that is not a letter or a
 * digit is ignored, word breaks included ("Mary-Jo" = "Mary Jo" = "MaryJo" =
 * "Mary_Jo" = "Mary–Jo", "O'Brix" = "OBrix" = "O`Brix", "J.R." = "JR" = "J,R",
 * "(B)" = "[B]" = "B"). Accents are what NFKD + dropping combining marks folds,
 * on consonants too ("Peña" = "Pena", "Françoise" = "Francoise"); ø/ł/æ/ß and
 * U+02BC are not pinned either way. Every letter counts, vowels included: a
 * left-out word, a one-letter typo (vowel or consonant), a doubled or dropped
 * vowel, or a letter dropped ("Pea" for "Peña", "Sren" for "Søren") is NOT the
 * same name; a name that folds to nothing matches nobody.
 *
 *   exact key_ match (today's rule)         active → removed; inactive → already removed
 *   folded match, one candidate, active     removed (Audit names the rule)
 *   folded match, only inactive candidates  already removed, no ReviewQueue item
 *   folded match, 2+ candidates with an     "Removal did not match anyone", as today
 *     active one (two active; active+inactive)
 *   anything else (typo, missing word)      "Removal did not match anyone", as today
 *
 * Fictional names only (test/fixtures/make_fixture.py pools + the Zibblewick family).
 * No Google APIs: the handler section stubs them, as test/forms_logic_test.js does.
 *
 *   node test/removal_match_test.js
 */
const vm = require('vm');
const loadGs = require('./load_gs');
const { check, finish } = require('./helpers/js/check');

const gs = loadGs(null, null, { strict: true });
const rowObj = (arr, sheetRow) => {
  const o = {}; gs.ROSTER_COLS.forEach((c, i) => { o[c] = arr[i]; }); o._sheetRow = sheetRow; return o;
};
const freshState = () => ({ registry: { byKey: {}, byCode: {}, added: [] }, sequence: {} });

const P = 'Fixture Partner Alpha', CLUB = 'Sunrise Club', REGION = 'Africa', SRC = 'Roster Form Responses!60';
const TODAY = '2026-09-28';
const ITEM = 'Removal did not match anyone';

// A name wholly in another script: Arabic letters reading "fictional test" (not a name), and
// "second test" as the DIFFERENT name. Letters of any script count (\p{L}), not ASCII only.
const ARABIC = 'اختبار وهمي';
const ARABIC_OTHER = 'اختبار ثاني';

// ------------------------------------------------------------------ the club
// One Roster, every case of the table: the sheet row is the row's identity.
const ROSTER = [
  ['Lucía Zörblewick', 'active'],          // 2   accents
  ['Mary-Jo Thornquibble', 'active'],      // 3   hyphen
  ["Esther O'Marrowgate", 'active'],       // 4   apostrophe
  ['J.R. Fennwhistle', 'active'],          // 5   periods
  ['Dalia Ixworthing', 'active'],          // 6   plain (the exact-match control)
  ['Ana Lucía Kestrelby', 'active'],       // 7   a middle name a mentor may leave out
  ['Hope Wrenfoldy', 'active'],            // 8   a one-letter typo away from "Wrenfoldi"
  ['Zoë Halverquist', 'active'],           // 9   two ACTIVE girls whose names fold equal
  ['Zoe Halverquist', 'active'],           // 10
  ['Nadia Quillstrand', 'active'],         // 11  an active girl and an inactive one folding equal
  ['Nadía Quillstrand', 'inactive'],       // 12
  ['Rosa Lorrimane', 'inactive'],          // 13  two INACTIVE girls folding equal
  ['Rosá Lorrimane', 'inactive'],          // 14
  ['Grace Zibblewick', 'inactive'],        // 15  removed earlier, spelled as enrolled
  ['Inés Umberlash', 'inactive'],          // 16  removed earlier, accent
  ['Hana Nimbleford', 'active'],           // 17  two girls told apart by a marker letter
  ['Hana Nimbleford (B)', 'active'],       // 18
  ['Keza Brindlecote 2', 'active'],        // 19  a marker digit
  ['Peña Cobblewynd', 'active'],           // 20  a diacritic on a consonant: ñ folds to n, it is not dropped
  ['Françoise Jubbleton', 'active'],       // 21  ç folds to c
  ['Begoña Yexleyton', 'inactive'],        // 22  removed earlier, consonant diacritic
  ['Mia Grimboltz', 'active'],             // 23  two girls whose names differ only in the order of their vowels
  ['Mai Grimboltz', 'active'],             // 24
  ['Søren Vexmoorish', 'active'],          // 25  a letter NFKD does not decompose: it is a letter, never dropped
  [ARABIC, 'active'],                      // 26  a name wholly in another script
  ['??', 'active'],                        // 27  a row that is only punctuation (folds to nothing)
];
const rows = () => ROSTER.map(([name, status], i) => rowObj(
  ['SUNRISEC-' + gs.asciiCode_(gs.lastName_(name)) + '-00' + (i + 2), P, CLUB, REGION, name, gs.lastName_(name),
   status, '2026-08-26', status === 'inactive' ? '2026-08-01' : '', 'T!2'], i + 2));
const modify = (removes, adds, current) => gs.planModification_(
  { partner: P, club: CLUB, source: SRC, submitted: TODAY, adds: adds || [], removes: removes },
  current || rows(), freshState(), REGION, TODAY);
/** What a plan did, as one string the table compares. */
const outcome = plan => {
  const parts = [];
  if (plan.deactivate.length) parts.push('removed ' + plan.deactivate.map(r => r._sheetRow).sort((a, b) => a - b).join('+'));
  if (plan.alreadyInactive.length) parts.push('already removed');
  if (plan.unmatched.length) parts.push('item');
  if (plan.keptBoth.length) parts.push('kept both');
  if (plan.reactivate.length) parts.push('reactivated');
  if (plan.toAppend.length) parts.push('added ' + plan.toAppend.length);
  parts.push(plan.issues.length + ' issue(s)');
  return parts.join(', ');
};

console.log('planModification_ — one REMOVE at a time, over the whole table');
// [typed, expected outcome, why]
const TABLE = [
  // exact key_ matches: today's behaviour, untouched
  ['Dalia Ixworthing', 'removed 6, 0 issue(s)', 'exact'],
  ['dalia ixworthing', 'removed 6, 0 issue(s)', 'exact, capitals'],
  ['  Lucía   Zörblewick ', 'removed 2, 0 issue(s)', 'exact, spacing'],
  ['Grace Zibblewick', 'already removed, 0 issue(s)', 'exact, inactive'],
  ['grace zibblewick', 'already removed, 0 issue(s)', 'exact, inactive, capitals'],
  ['Zoe Halverquist', 'removed 10, 0 issue(s)', 'exact beats her fold-twin (row 9 stays)'],
  ['Zoë Halverquist', 'removed 9, 0 issue(s)', 'exact beats her fold-twin (row 10 stays)'],
  ['Nadia Quillstrand', 'removed 11, 0 issue(s)', 'exact active, an inactive fold-twin on file'],
  ['Nadía Quillstrand', 'already removed, 0 issue(s)', 'exact inactive, an active fold-twin on file'],
  ['Hana Nimbleford', 'removed 17, 0 issue(s)', 'exact: the girl without the marker'],
  ['Rosa Lorrimane', 'already removed, 0 issue(s)', 'exact inactive, an inactive fold-twin on file'],
  ['Peña Cobblewynd', 'removed 20, 0 issue(s)', 'exact, consonant diacritic'],
  ['Begoña Yexleyton', 'already removed, 0 issue(s)', 'exact inactive, consonant diacritic'],
  ['Mia Grimboltz', 'removed 23, 0 issue(s)', 'exact; a vowel-order twin on file (row 24 stays)'],
  ['SØREN VEXMOORISH', 'removed 25, 0 issue(s)', 'exact (key_ lowercases ø too), capitals'],
  [ARABIC.replace(' ', '   '), 'removed 26, 0 issue(s)', 'exact, another script, spacing'],
  ['??', 'removed 27, 0 issue(s)', 'exact: the row that is only punctuation'],
  // folded match, exactly one candidate and she is active → removed
  ['Lucia Zorblewick', 'removed 2, 0 issue(s)', 'accents'],
  ['LUCIA ZORBLEWICK', 'removed 2, 0 issue(s)', 'accents + capitals'],
  ['Mary Jo Thornquibble', 'removed 3, 0 issue(s)', 'hyphen typed as a space'],
  ['MaryJo Thornquibble', 'removed 3, 0 issue(s)', 'hyphen left out'],
  ['Esther OMarrowgate', 'removed 4, 0 issue(s)', 'apostrophe left out'],
  ['Esther O’Marrowgate', 'removed 4, 0 issue(s)', 'curly apostrophe'],
  ['JR Fennwhistle', 'removed 5, 0 issue(s)', 'periods left out'],
  ['J. R. Fennwhistle', 'removed 5, 0 issue(s)', 'periods spaced'],
  ['Hana Nimbleford B', 'removed 18, 0 issue(s)', 'the marker letter counts, its parentheses do not'],
  ['Keza Brindlecote (2)', 'removed 19, 0 issue(s)', 'the marker digit counts, its parentheses do not'],
  ['Pena Cobblewynd', 'removed 20, 0 issue(s)', 'ñ typed as n (NFKD folds a consonant\'s mark too)'],
  ['PENA COBBLEWYND', 'removed 20, 0 issue(s)', 'ñ typed as n + capitals'],
  ['Francoise Jubbleton', 'removed 21, 0 issue(s)', 'ç typed as c'],
  ['Mía Grimboltz', 'removed 23, 0 issue(s)', 'accent on a vowel; her vowel-order twin (row 24) is no candidate'],
  ['Maí Grimboltz', 'removed 24, 0 issue(s)', 'accent on a vowel; her vowel-order twin (row 23) is no candidate'],
  // …anything that is not a letter or a digit is ignored, not just the marks above
  ['Mary–Jo Thornquibble', 'removed 3, 0 issue(s)', 'en dash for the hyphen'],
  ['Mary—Jo Thornquibble', 'removed 3, 0 issue(s)', 'em dash for the hyphen'],
  ['Mary_Jo Thornquibble', 'removed 3, 0 issue(s)', 'underscore for the hyphen'],
  ['Mary/Jo Thornquibble', 'removed 3, 0 issue(s)', 'slash for the hyphen'],
  ['Esther O`Marrowgate', 'removed 4, 0 issue(s)', 'backtick for the apostrophe'],
  ['Esther O‘Marrowgate', 'removed 4, 0 issue(s)', 'left quote for the apostrophe'],
  ['J,R Fennwhistle', 'removed 5, 0 issue(s)', 'a comma for the periods'],
  ['J·R· Fennwhistle', 'removed 5, 0 issue(s)', 'middle dots for the periods'],
  ['Hana Nimbleford [B]', 'removed 18, 0 issue(s)', 'brackets for the parentheses'],
  ['Hana Nimbleford {B}', 'removed 18, 0 issue(s)', 'braces for the parentheses'],
  ['Hana Nimbleford "B"', 'removed 18, 0 issue(s)', 'quotes for the parentheses'],
  ['Keza Brindlecote #2', 'removed 19, 0 issue(s)', 'a # before the marker digit'],
  [ARABIC.replace(' ', '-'), 'removed 26, 0 issue(s)', 'another script, a hyphen for the space'],
  [ARABIC.replace(' ', '، '), 'removed 26, 0 issue(s)', 'another script, an Arabic comma added'],
  // folded match, only inactive candidates → already removed, no item
  ['Ines Umberlash', 'already removed, 0 issue(s)', 'accent, inactive'],
  ['INES UMBERLASH', 'already removed, 0 issue(s)', 'accent + capitals, inactive'],
  ['Rósa Lorrimane', 'already removed, 0 issue(s)', 'two inactive fold-twins: still just already removed'],
  ['Begona Yexleyton', 'already removed, 0 issue(s)', 'ñ typed as n, inactive'],
  ['Ines Umberlash!', 'already removed, 0 issue(s)', 'a trailing ! (parseRoster_ keeps it), inactive'],
  // folded match, two or more candidates with an active one → the item, as today
  ['Zoé Halverquist', 'item, 1 issue(s)', 'two ACTIVE girls fold equal'],
  ['Nadiá Quillstrand', 'item, 1 issue(s)', 'an active and an inactive girl fold equal'],
  // beyond accents and punctuation → the item, as today
  ['Ana Kestrelby', 'item, 1 issue(s)', 'a middle name left out'],
  ['Hope Wrenfoldi', 'item, 1 issue(s)', 'a one-letter typo'],
  ['Lucia Zorblewik', 'item, 1 issue(s)', 'accents folded AND a typo'],
  ['Keza Brindlecote', 'item, 1 issue(s)', 'the marker left out (no plain row)'],
  ['Hana Nimbleford (C)', 'item, 1 issue(s)', 'a marker nobody has'],
  ['Nobody Testperson', 'item, 1 issue(s)', 'unknown'],
  // vowels count as much as consonants: a fold that keeps only a consonant skeleton fails these
  ['Dalio Ixworthing', 'item, 1 issue(s)', 'a vowel typo'],
  ['Dalia Ixwerthing', 'item, 1 issue(s)', 'a vowel typo in the surname'],
  ['Dali Ixworthing', 'item, 1 issue(s)', 'a vowel left out'],
  ['Daliaa Ixworthing', 'item, 1 issue(s)', 'a doubled vowel'],
  ['Dalia Ixwoorthing', 'item, 1 issue(s)', 'a doubled vowel in the surname'],
  ['Lucio Zorblewick', 'item, 1 issue(s)', 'accents folded AND a vowel typo'],
  ['Luca Zorblewick', 'item, 1 issue(s)', 'accents folded AND a vowel left out'],
  ['Ma Grimboltz', 'item, 1 issue(s)', 'both vowels left out: neither Grimboltz girl'],
  // a diacritic on a consonant folds to the letter; the letter dropped is another name
  ['Pea Cobblewynd', 'item, 1 issue(s)', 'the ñ dropped, not folded (active girl on file)'],
  ['Franoise Jubbleton', 'item, 1 issue(s)', 'the ç dropped, not folded'],
  ['Begoa Yexleyton', 'item, 1 issue(s)', 'the ñ dropped, not folded (inactive girl on file): still an item'],
  // letters are letters in any script; a dropped one is a typo, and no letters at all is nobody
  ['Sren Vexmoorish', 'item, 1 issue(s)', 'the ø dropped: a letter NFKD leaves alone is still a letter'],
  [ARABIC_OTHER, 'item, 1 issue(s)', 'a different name in another script: never removed'],
  ['--', 'item, 1 issue(s)', 'folds to nothing: matches nobody, not even the row that folds to nothing'],
  ['?', 'item, 1 issue(s)', 'folds to nothing (one ? against the ?? row)'],
  ['( )', 'item, 1 issue(s)', 'folds to nothing, with a space'],
];
TABLE.forEach(([typed, expected, why]) => {
  const plan = modify([typed]);
  const got = outcome(plan);
  check('REMOVE "' + typed + '" (' + why + ') → ' + expected, got === expected, got);
});

console.log('\nplanModification_ — what the plan carries for each kind of match');
{
  let plan = modify(['Lucia Zorblewick']);
  check('a folded removal deactivates the Roster row itself (the sheet row applyRosterPlan_ writes)',
        plan.deactivate.length === 1 && plan.deactivate[0]._sheetRow === 2 && plan.deactivate[0].full_name === 'Lucía Zörblewick',
        JSON.stringify(plan.deactivate.map(r => r._sheetRow)));
  check('…and nothing else moves: no reactivation, nothing minted, not unmatched, not already removed',
        !plan.reactivate.length && !plan.toAppend.length && !plan.unmatched.length && !plan.alreadyInactive.length &&
        !plan.keptBoth.length && !plan.alreadyActive.length);
  check('…its removed_date is the day the response was sent (removedOn), as for an exact removal',
        plan.removedOn === TODAY && modify(['Dalia Ixworthing']).removedOn === TODAY);

  plan = modify(['Ines Umberlash']);
  check('a folded already-removed carries the name AS TYPED (the mentor e-mail echoes it), never the Roster\'s spelling',
        plan.alreadyInactive.join('|') === 'Ines Umberlash', plan.alreadyInactive.join('|'));
  plan = modify(['Rósa Lorrimane']);
  check('two inactive fold-twins: one "already removed" entry, as typed; no deactivation, no item',
        plan.alreadyInactive.join('|') === 'Rósa Lorrimane' && !plan.deactivate.length && !plan.unmatched.length &&
        !plan.issues.length, outcome(plan));

  for (const [typed, who] of [['Zoé Halverquist', 'two active'], ['Nadiá Quillstrand', 'active + inactive'],
                              ['Ana Kestrelby', 'middle name left out'], ['Hope Wrenfoldi', 'one-letter typo']]) {
    plan = modify([typed]);
    const issue = plan.issues[0] || {};
    check('"' + typed + '" (' + who + '): the item exactly as today — title, source, typed name, dedupe key; nobody removed',
          !plan.deactivate.length && !plan.alreadyInactive.length && plan.unmatched.length === 1 &&
          plan.unmatched[0].name === typed && plan.issues.length === 1 && issue.issue === ITEM &&
          issue.partner === P && issue.club === CLUB && issue.dedupeKey === gs.key_(typed) &&
          issue.detail.startsWith(SRC + ': "' + typed + '" is not on this club\'s active roster') &&
          issue.detail.endsWith('. Nobody was removed; the mentor was told we would check.'),
          (issue.detail || outcome(plan)).slice(0, 120));
  }
  plan = modify(['Zoé Halverquist']);
  check('the ambiguous item still suggests the closest ACTIVE names (both fold-twins), as today',
        plan.unmatched[0].candidates.slice().sort().join('|') === 'Zoe Halverquist|Zoë Halverquist',
        plan.unmatched[0].candidates.join('|'));
}

console.log('\nplanModification_ — one response with every kind of REMOVE at once');
{
  const removes = ['dalia ixworthing', 'Lucia Zorblewick', 'Mary Jo Thornquibble', 'Esther OMarrowgate', 'JR Fennwhistle',
                   'Hana Nimbleford B', 'Keza Brindlecote (2)', 'Pena Cobblewynd', 'Mía Grimboltz',
                   ARABIC.replace(' ', '-'),                                                      // 10 removed: rows 6 2 3 4 5 18 19 20 23 26
                   'Grace Zibblewick', 'Ines Umberlash', 'Rósa Lorrimane', 'Begona Yexleyton',      // 4 already removed
                   'Zoé Halverquist', 'Nadiá Quillstrand', 'Ana Kestrelby', 'Hope Wrenfoldi', 'Nobody Testperson',
                   'Dalio Ixworthing', 'Pea Cobblewynd', 'Ma Grimboltz', 'Sren Vexmoorish', ARABIC_OTHER, '--'];   // 11 items
  const plan = modify(removes);
  check('removed: exactly the ten rows matched exactly or by folding, each once',
        plan.deactivate.map(r => r._sheetRow).sort((a, b) => a - b).join(',') === '2,3,4,5,6,18,19,20,23,26',
        plan.deactivate.map(r => r._sheetRow).join(','));
  check('already removed: the four inactive matches, as typed, in order',
        plan.alreadyInactive.join('|') === 'Grace Zibblewick|Ines Umberlash|Rósa Lorrimane|Begona Yexleyton', plan.alreadyInactive.join('|'));
  check('unmatched: the two ambiguous and the nine near or empty spellings, as typed, in order',
        plan.unmatched.map(u => u.name).join('|') === removes.slice(14).join('|'), plan.unmatched.map(u => u.name).join('|'));
  check('eleven items, one per unmatched name, nothing else on the queue',
        plan.issues.length === 11 && plan.issues.every(i => i.issue === ITEM) &&
        plan.issues.map(i => i.dedupeKey).join('|') === removes.slice(14).map(gs.key_).join('|'),
        plan.issues.map(i => i.issue + '/' + i.dedupeKey).join(' ; '));
  check('the fold-twins of the ambiguous names, the typo targets, the vowel-order twin, Søren and the ?? row all stay active ' +
        '(rows 7 8 9 10 11 17 21 24 25 27 untouched)',
        [7, 8, 9, 10, 11, 17, 21, 24, 25, 27].every(r => !plan.deactivate.some(d => d._sheetRow === r)));
  check('nothing reactivated, minted or kept',
        !plan.reactivate.length && !plan.toAppend.length && !plan.keptBoth.length && !plan.alreadyActive.length);
}

console.log('\nplanModification_ — ADD and REMOVE in the same response');
{
  let plan = modify(['dalia ixworthing'], ['Dalia Ixworthing']);
  check('the same name under ADD and REMOVE: kept, as today (not removed, no item)',
        outcome(plan) === 'kept both, 0 issue(s)' && plan.alreadyActive.join() === 'Dalia Ixworthing', outcome(plan));
  // Ryan's rule (2026-10-22): a misspelled name is corrected by REMOVE wrong + ADD right — no rename.
  // The two spellings fold equal, and that must NOT make the pair "kept both".
  for (const [onFile, typedRight] of [['Lucía Zörblewick', 'Lucia Zorblewick'], ['Lucia Zorblewick', 'Lucía Zörblewick'],
                                      ["Esther O'Marrowgate", 'Esther OMarrowgate']]) {
    const one = [rowObj(['SUNRISEC-X-001', P, CLUB, REGION, onFile, gs.lastName_(onFile), 'active', '2026-08-26', '', 'T!2'], 2)];
    plan = modify([onFile], [typedRight], one);
    check('REMOVE "' + onFile + '" + ADD "' + typedRight + '": the old spelling removed, the new one minted; not "kept both", no item',
          plan.deactivate.length === 1 && plan.deactivate[0]._sheetRow === 2 && plan.toAppend.length === 1 &&
          plan.toAppend[0][gs.ROSTER_COLS.indexOf('full_name')] === typedRight && !plan.keptBoth.length &&
          !plan.unmatched.length && !plan.issues.length && !plan.alreadyActive.length, outcome(plan));
  }
}

console.log('\nplanModification_ — an empty club, and nothing to remove');
{
  const plan = modify(['Lucia Zorblewick'], [], []);
  check('no rows at all: the item, as today', outcome(plan) === 'item, 1 issue(s)', outcome(plan));
  check('no removes: nothing removed, no item', outcome(modify([])) === '0 issue(s)');
}

// --------------------------------------------- the handler, Google services stubbed
// Audit, FormLog, the ReviewQueue and the mentor e-mail, from handleRosterChange_
// (FormHandlers.gs). The spreadsheet is plain arrays, as test/forms_logic_test.js's sheetWorld.
console.log('\nhandleRosterChange_ — Audit, ReviewQueue, Roster and the mentor e-mail (Google services stubbed)');
const HANDLER_FILES = ['Config.gs', 'Normalize.gs', 'Ids.gs', 'Regions.gs', 'RosterOps.gs', 'Roster.gs', 'FormHandlers.gs',
                       'Dispatch.gs'];
function sheetWorld(tabs) {
  const out = { tabs, mails: [], audits: [], notified: [] };
  const colNum = letters => letters.split('').reduce((n, ch) => n * 26 + ch.charCodeAt(0) - 64, 0);
  const sheet = name => ({
    getName: () => name,
    getLastRow: () => tabs[name].length,
    getLastColumn: () => Math.max(0, ...tabs[name].map(r => r.length)),
    getRange: (r, c, nr, nc) => {
      nr = nr || 1; nc = nc || 1;
      const put = (i, j, v) => {
        while (tabs[name].length < r + i) tabs[name].push([]);
        tabs[name][r - 1 + i][c - 1 + j] = v;
      };
      return {
        getValues: () => tabs[name].slice(r - 1, r - 1 + nr).map(row => Array.from({ length: nc }, (_, j) => row[c - 1 + j] ?? '')),
        setValues: vals => vals.forEach((v, i) => v.forEach((x, j) => put(i, j, x))),
        setValue: v => put(0, 0, v),
        setFontWeight: () => ({}),
      };
    },
    getRangeList: a1s => ({ setValue: v => a1s.forEach(a => {
      const m = /^([A-Z]+)(\d+)$/.exec(a); sheet(name).getRange(+m[2], colNum(m[1])).setValue(v); }) }),
    appendRow: row => { tabs[name].push(row.slice()); },
    setFrozenRows: () => {},
  });
  const ctx = loadGs.sandbox(HANDLER_FILES, {
    SpreadsheetApp: { getActive: () => ({ getSheetByName: n => (tabs[n] ? sheet(n) : null),
                                           insertSheet: n => { tabs[n] = []; return sheet(n); },
                                           getSpreadsheetTimeZone: () => 'America/New_York' }) },
    PropertiesService: { getScriptProperties: () => ({ getProperty: () => null }) },
    MailApp: { sendEmail: o => out.mails.push(o) },
  });
  ctx.today_ = () => TODAY;
  ctx.now_ = () => TODAY + ' 09:00:00';
  ctx.audit_ = (action, detail) => out.audits.push(action + ': ' + detail);
  ctx.formLogAdd_ = () => {};
  ctx.trySyncChoices_ = () => {};
  ctx.tryNotifySync_ = why => out.notified.push(why);
  out.ctx = ctx;
  out.girl = id => tabs.Roster.find(r => r[0] === id) || [];
  out.status = id => out.girl(id)[6] + '|' + out.girl(id)[8];
  return out;
}
const HQ = vm.runInContext('Q', loadGs.sandbox(['Config.gs'], {}));
const MOON = 'Moonrise Club';
const girlRow = (id, clubName, name, status, removed) =>
  [id, P, clubName, REGION, name, name.split(' ').pop(), status, '2026-08-26', removed || '', 'Enrollment Responses!2'];
const world = () => sheetWorld({
  Roster: [['girl_id', 'partner', 'club', 'region', 'full_name', 'last_name', 'status', 'added_date', 'removed_date', 'source'],
    girlRow('T1', CLUB, 'Lucía Zörblewick', 'active'),
    girlRow('T2', CLUB, 'Inés Umberlash', 'inactive', '2026-08-01'),
    girlRow('T3', CLUB, 'Dalia Ixworthing', 'active'),
    girlRow('T4', CLUB, "Esther O'Marrowgate", 'active'),
    girlRow('T5', CLUB, 'Zoë Halverquist', 'active'),
    girlRow('T6', CLUB, 'Zoe Halverquist', 'active'),
    girlRow('T7', MOON, 'Lucia Zorblewick', 'inactive', '2026-08-01'),   // another club's girl: never a candidate
    girlRow('T8', MOON, 'Dalia Ixworthing', 'active'),
    girlRow('T9', CLUB, 'Peña Cobblewynd', 'active'),                     // a diacritic on a consonant
    girlRow('T10', CLUB, 'Begoña Yexleyton', 'inactive', '2026-08-01'),
    girlRow('T11', CLUB, 'Mary-Jo Thornquibble', 'active'),               // punctuation inside the name
  ],
  ClubRegistry: [['club_code', 'partner', 'club', 'created']],
  Partners: [['partner', 'region', 'notes'], [P, REGION, '']],
  ReviewQueue: [['raised', 'issue', 'partner', 'club', 'detail', 'resolved']],
});
const change = (clubName, remove, email) => ({ [HQ.ACTION]: HQ.ACTION_MOD, [HQ.PARTNER_MOD]: P, [HQ.CLUB_PREFIX + P + ')']: clubName,
                                               [HQ.REMOVE]: remove, [HQ.MENTOR_EMAIL_MOD]: email === undefined ? 'mentor@example.org' : email });
const RQ = 'Roster Form Responses';
const noGirls = s => !/z[oö]rblewick|umberlash|ixworthing|marrowgate|halverquist|cobblewynd|yexleyton|thornquibble/i.test(s);
// The Audit summary names the rule a folded removal matched by. The wording is the coder's; the
// clause that names it carries the count.
const RULE = /spelling|accent|punctuation|fold/i;
const ruleClause = (summary, n) => summary.split(/[,;]/).some(c => RULE.test(c) && new RegExp('\\b' + n + '\\b').test(c));
const section = (body, title) => {
  const lines = body.split('\n'), at = lines.indexOf(title);
  if (at === -1) return null;
  const out = [];
  for (let i = at + 1; i < lines.length && lines[i].startsWith('  - '); i++) out.push(lines[i].slice(4));
  return out;
};

console.log('\n  the exact-match control (today\'s path)');
let w = world();
const exact = w.ctx.handleRosterChange_(change(CLUB, 'Dalia Ixworthing'), RQ + '!61', TODAY);
check('REMOVE spelled as enrolled: removed, dated today; one Audit line with "1 removed"; no item; the Audit does not name a rule',
      w.status('T3') === 'inactive|' + TODAY && w.audits.length === 1 && w.audits[0] === 'rosterChangeForm: ' + exact &&
      /\b1 removed\b/.test(exact) && !RULE.test(exact) && !/did not match|already removed/.test(exact) &&
      w.tabs.ReviewQueue.length === 1 && noGirls(exact), exact);
check('…the other club\'s girl of the same name is untouched', w.status('T8') === 'active|');

console.log('\n  a REMOVE that differs from one active girl only by accents');
w = world();
const folded = w.ctx.handleRosterChange_(change(CLUB, 'Lucia Zorblewick'), RQ + '!62', TODAY);
check('she is removed on the Roster, dated the day the response was sent', w.status('T1') === 'inactive|' + TODAY, w.status('T1'));
check('no ReviewQueue item', w.tabs.ReviewQueue.length === 1, JSON.stringify(w.tabs.ReviewQueue[1] || null));
check('Audit: one line, = the FormLog result; "1 removed"; counts only, no name',
      w.audits.length === 1 && w.audits[0] === 'rosterChangeForm: ' + folded && /\b1 removed\b/.test(folded) &&
      !/did not match/.test(folded) && noGirls(folded), folded);
check('Audit names the rule the removal matched by (spelling/accent/punctuation/fold), with its count (1)',
      RULE.test(folded) && ruleClause(folded, 1), folded);
check('the Jotform sync is asked for, as for any removal', w.notified.join() === 'rosterChangeForm', w.notified.join());
let body = (w.mails[0] || { body: '' }).body;
check('the mentor e-mail lists her under "Removed:" AS TYPED, and never the Roster\'s spelling',
      w.mails.length === 1 && (section(body, 'Removed:') || []).join('|') === 'Lucia Zorblewick' &&
      !/Zörblewick/.test(body) && !/could NOT find/.test(body),
      w.mails.length + ' mail(s): ' + JSON.stringify(section(body, 'Removed:')) + (/Zörblewick/.test(body) ? ' (Roster spelling leaked)' : ''));
check('the other club\'s inactive girl of that folded name is untouched', w.status('T7') === 'inactive|2026-08-01', w.status('T7'));

console.log('\n  a REMOVE that differs from an already-removed girl only by an accent');
w = world();
const already = w.ctx.handleRosterChange_(change(CLUB, 'Ines Umberlash'), RQ + '!63', TODAY);
check('nothing changes on the Roster: she stays inactive with her original removed_date',
      w.status('T2') === 'inactive|2026-08-01' && w.tabs.Roster.length === 12, w.status('T2'));
check('no ReviewQueue item', w.tabs.ReviewQueue.length === 1, JSON.stringify(w.tabs.ReviewQueue[1] || null));
check('Audit: "1 already removed", no "did not match", 0 removed; counts only, no name',
      w.audits.length === 1 && w.audits[0] === 'rosterChangeForm: ' + already && /\b1 already removed\b/.test(already) &&
      /\b0 removed\b/.test(already) && !/did not match/.test(already) && noGirls(already), already);
check('no Jotform sync asked for (nothing changed)', !w.notified.length, w.notified.join());
body = (w.mails[0] || { body: '' }).body;
check('the mentor e-mail lists her under "Already removed earlier (no change):" AS TYPED, never the Roster\'s spelling',
      w.mails.length === 1 && (section(body, 'Already removed earlier (no change):') || []).join('|') === 'Ines Umberlash' &&
      !/Inés/.test(body) && !/could NOT find/.test(body), JSON.stringify(section(body, 'Already removed earlier (no change):')));

console.log('\n  a REMOVE two active girls fold equal to');
w = world();
const ambiguous = w.ctx.handleRosterChange_(change(CLUB, 'Zoé Halverquist'), RQ + '!64', TODAY);
const item = w.tabs.ReviewQueue[1] || [];
check('both stay active; the item is raised exactly as today', w.status('T5') === 'active|' && w.status('T6') === 'active|' &&
      w.tabs.ReviewQueue.length === 2 && item[1] === ITEM && item[2] === P && item[3] === CLUB &&
      String(item[4]).startsWith(RQ + '!64: "Zoé Halverquist" is not on this club\'s active roster'), String(item[4]).slice(0, 100));
check('Audit: "1 removal(s) did not match", 0 removed, no rule named',
      /\b0 removed\b/.test(ambiguous) && /1 removal\(s\) did not match/.test(ambiguous) && !RULE.test(ambiguous) && noGirls(ambiguous), ambiguous);
body = (w.mails[0] || { body: '' }).body;
check('the mentor is told we could not find her, with her name as typed only',
      /could NOT find/.test(body) && body.includes('  - Zoé Halverquist') && !/Zoë|Zoe /.test(body));

console.log('\n  another club\'s girls are never candidates');
w = world();
const moon = w.ctx.handleRosterChange_(change(MOON, 'LUCIA ZÖRBLEWICK'), RQ + '!65', TODAY);
check('Moonrise Club has only an inactive girl of that folded name: already removed, no item — ' +
      'Sunrise Club\'s active one is not a candidate and stays active',
      w.status('T1') === 'active|' && w.status('T7') === 'inactive|2026-08-01' && w.tabs.ReviewQueue.length === 1 &&
      /\b1 already removed\b/.test(moon) && !/did not match/.test(moon), moon);

console.log('\n  several folded removals in one response');
w = world();
const several = w.ctx.handleRosterChange_(change(CLUB, 'Lucia Zorblewick\nEsther OMarrowgate\nDalia Ixworthing'), RQ + '!66', TODAY);
check('all three removed (two by folding, one exact); no item',
      w.status('T1') === 'inactive|' + TODAY && w.status('T4') === 'inactive|' + TODAY && w.status('T3') === 'inactive|' + TODAY &&
      w.tabs.ReviewQueue.length === 1, [w.status('T1'), w.status('T4'), w.status('T3')].join(' '));
check('Audit: the rule clause carries the folded count (2); no name', ruleClause(several, 2) && noGirls(several), several);
body = (w.mails[0] || { body: '' }).body;
check('the e-mail\'s "Removed:" has the three names as typed; neither Roster spelling appears',
      (section(body, 'Removed:') || []).slice().sort().join('|') === 'Dalia Ixworthing|Esther OMarrowgate|Lucia Zorblewick' &&
      !/Zörblewick|O'Marrowgate/.test(body), JSON.stringify(section(body, 'Removed:')));

console.log('\n  a diacritic on a consonant, end to end: the letter typed plain matches, the letter dropped does not');
w = world();
const pena = w.ctx.handleRosterChange_(change(CLUB, 'Pena Cobblewynd'), RQ + '!70', TODAY);
check('REMOVE "Pena Cobblewynd" for an active "Peña Cobblewynd": removed, dated today; no item; Audit "1 removed" + the rule; no name',
      w.status('T9') === 'inactive|' + TODAY && w.tabs.ReviewQueue.length === 1 && /\b1 removed\b/.test(pena) &&
      ruleClause(pena, 1) && noGirls(pena), pena);
body = (w.mails[0] || { body: '' }).body;
check('…the e-mail\'s "Removed:" lists "Pena Cobblewynd" as typed; "Peña" never appears',
      (section(body, 'Removed:') || []).join('|') === 'Pena Cobblewynd' && !/Peña/.test(body), JSON.stringify(section(body, 'Removed:')));
w = world();
const pea = w.ctx.handleRosterChange_(change(CLUB, 'Pea Cobblewynd'), RQ + '!71', TODAY);
check('REMOVE "Pea Cobblewynd" (the ñ dropped): she stays active; the item; Audit "0 removed, 1 removal(s) did not match"',
      w.status('T9') === 'active|' && w.tabs.ReviewQueue.length === 2 && (w.tabs.ReviewQueue[1] || [])[1] === ITEM &&
      /\b0 removed\b/.test(pea) && /1 removal\(s\) did not match/.test(pea) && !RULE.test(pea), pea);
w = world();
const begona = w.ctx.handleRosterChange_(change(CLUB, 'Begona Yexleyton'), RQ + '!72', TODAY);
check('REMOVE "Begona Yexleyton" for an inactive "Begoña Yexleyton": already removed, no item, Roster untouched',
      w.status('T10') === 'inactive|2026-08-01' && w.tabs.ReviewQueue.length === 1 && /\b1 already removed\b/.test(begona) &&
      /\b0 removed\b/.test(begona) && !/did not match/.test(begona) && noGirls(begona), begona);
body = (w.mails[0] || { body: '' }).body;
check('…the e-mail lists "Begona Yexleyton" as typed under "Already removed earlier (no change):"; "Begoña" never appears',
      (section(body, 'Already removed earlier (no change):') || []).join('|') === 'Begona Yexleyton' && !/Begoña/.test(body),
      JSON.stringify(section(body, 'Already removed earlier (no change):')));
w = world();
const begoa = w.ctx.handleRosterChange_(change(CLUB, 'Begoa Yexleyton'), RQ + '!73', TODAY);
check('REMOVE "Begoa Yexleyton" (the ñ dropped) for the inactive girl: still the item, not "already removed"',
      w.tabs.ReviewQueue.length === 2 && (w.tabs.ReviewQueue[1] || [])[1] === ITEM && /1 removal\(s\) did not match/.test(begoa) &&
      !/already removed/.test(begoa), begoa);

console.log('\n  other punctuation, end to end: an underscore for a hyphen, a trailing ! the parser keeps');
w = world();
const underscore = w.ctx.handleRosterChange_(change(CLUB, 'Mary_Jo Thornquibble'), RQ + '!75', TODAY);
check('REMOVE "Mary_Jo Thornquibble" for an active "Mary-Jo Thornquibble": removed, dated today; no item; Audit "1 removed" + the rule; no name',
      w.status('T11') === 'inactive|' + TODAY && w.tabs.ReviewQueue.length === 1 && /\b1 removed\b/.test(underscore) &&
      ruleClause(underscore, 1) && noGirls(underscore), underscore);
body = (w.mails[0] || { body: '' }).body;
check('…the e-mail\'s "Removed:" lists "Mary_Jo Thornquibble" as typed; "Mary-Jo" never appears',
      (section(body, 'Removed:') || []).join('|') === 'Mary_Jo Thornquibble' && !/Mary-Jo/.test(body), JSON.stringify(section(body, 'Removed:')));
w = world();
const bang = w.ctx.handleRosterChange_(change(CLUB, 'Ines Umberlash!'), RQ + '!76', TODAY);
check('REMOVE "Ines Umberlash!" for the inactive "Inés Umberlash": already removed, no item, Roster untouched',
      w.status('T2') === 'inactive|2026-08-01' && w.tabs.ReviewQueue.length === 1 && /\b1 already removed\b/.test(bang) &&
      !/did not match/.test(bang) && noGirls(bang), bang);
body = (w.mails[0] || { body: '' }).body;
check('…the e-mail lists "Ines Umberlash!" as typed under "Already removed earlier (no change):"; "Inés" never appears',
      (section(body, 'Already removed earlier (no change):') || []).join('|') === 'Ines Umberlash!' && !/Inés/.test(body),
      JSON.stringify(section(body, 'Already removed earlier (no change):')));

console.log('\n  a vowel typo, end to end');
w = world();
const dalio = w.ctx.handleRosterChange_(change(CLUB, 'Dalio Ixworthing'), RQ + '!74', TODAY);
body = (w.mails[0] || { body: '' }).body;
check('REMOVE "Dalio Ixworthing": "Dalia Ixworthing" stays active; the item; Audit "0 removed, 1 removal(s) did not match"; ' +
      'the mentor is told we could not find her',
      w.status('T3') === 'active|' && w.tabs.ReviewQueue.length === 2 && (w.tabs.ReviewQueue[1] || [])[1] === ITEM &&
      /\b0 removed\b/.test(dalio) && /1 removal\(s\) did not match/.test(dalio) && !RULE.test(dalio) &&
      /could NOT find/.test(body) && body.includes('  - Dalio Ixworthing'), dalio);

console.log('\n  no mentor e-mail address: the same Roster outcome, no mail');
w = world();
const quiet = w.ctx.handleRosterChange_(change(CLUB, 'Lucia Zorblewick', ''), RQ + '!67', TODAY);
check('removed, no item, no mail', w.status('T1') === 'inactive|' + TODAY && w.tabs.ReviewQueue.length === 1 &&
      !w.mails.length && ruleClause(quiet, 1), quiet);

check('no Apps Script code the tests ran made an undeclared global', !loadGs.strayGlobals().length,
      loadGs.strayGlobals().join(', '));
finish();
