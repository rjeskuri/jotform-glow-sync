#!/usr/bin/env node
/**
 * Offline tests for the roster-change decisions in appsscript/RosterOps.gs —
 * the code behind the New Club Enrollment and Roster Modification forms,
 * including the replay guard — and for FormHandlers.gs's FormLog keys and
 * "Process any missed form responses" plan. Runs the real .gs files in Node
 * against a real club from the enrollment CSV plus synthetic edge cases. No
 * Google APIs involved (the handler sections stub them).
 *
 *   node test/forms_logic_test.js   (the real-CSV section runs only if data/enrollment_2026-08-24.csv exists)
 */
const fs = require('fs');
const path = require('path');
const loadGs = require('./load_gs');

const REPO = path.resolve(__dirname, '..');
const gs = loadGs(['ROSTER_COLS', 'STATUS', 'tidy_', 'key_', 'asciiCode_', 'parseRoster_', 'lastName_', 'clubCode_',
                   'mintGirlId_', 'planClub_', 'planModification_', 'closestNames_',
                   'chooseRegion_', 'canonicalRegion_', 'derivedPartnerRegions_', 'REGIONS']);

let failures = 0;
function check(label, cond, detail) {
  console.log((cond ? '  ok   ' : '  FAIL ') + label + (detail ? ' :: ' + detail : ''));
  if (!cond) failures++;
}
const col = name => gs.ROSTER_COLS.indexOf(name);
const rowObj = (arr, sheetRow) => {
  const o = {}; gs.ROSTER_COLS.forEach((c, i) => { o[c] = arr[i]; }); o._sheetRow = sheetRow; return o;
};
const freshState = () => ({ registry: { byKey: {}, byCode: {}, added: [] }, sequence: {} });

// ---------------------------------------------------------------- a club
// Synthetic roster so the test never prints real names.
const partner = 'Test Partner Org', club = 'Sunrise Club', region = 'Africa';
const names = ['Amina Qwertyson Alpha', 'Grace Zibblewick', 'Mary Zibblewick', 'Fatuma Qwertyson',
               'Lucía Zörblewick', 'Joy Blorptest'];

console.log('planClub_ — first enrollment');
let state = freshState();
let plan = gs.planClub_({ partner, club, names, duplicates: [], source: 'T!2' }, [], state, region, '2026-08-26');
check('every girl minted', plan.toAppend.length === names.length);
check('club code minted', plan.code === 'SUNRISEC', plan.code);
const ids = plan.toAppend.map(r => r[col('girl_id')]);
check('same surname → distinct numbers',
      ids.filter(i => i.indexOf('-ZIBBLEWICK-') !== -1).sort().join(',') === 'SUNRISEC-ZIBBLEWICK-001,SUNRISEC-ZIBBLEWICK-002');
check('accent folded in id', ids.some(i => i === 'SUNRISEC-ZORBLEWICK-001'), ids.join(' '));
check('row shape = ROSTER_COLS', plan.toAppend.every(r => r.length === gs.ROSTER_COLS.length));
check('source recorded', plan.toAppend[0][col('source')] === 'T!2');
check('no issues on a clean roster', plan.issues.length === 0);

// pretend those rows now live in the sheet (rows 2..7)
let current = plan.toAppend.map((r, i) => rowObj(r, i + 2));

console.log('\nplanClub_ — re-submission with a short list and a duplicate');
state = freshState();
// registry must know the club so the code is reused, sequence must know the ids
state.registry.byKey[gs.key_(partner) + '||' + gs.key_(club)] = { code: 'SUNRISEC', partner, club };
state.registry.byCode.SUNRISEC = state.registry.byKey[gs.key_(partner) + '||' + gs.key_(club)];
ids.forEach(id => { const m = id.match(/^(.*)-(\d+)$/); state.sequence[m[1]] = Math.max(state.sequence[m[1]] || 0, +m[2]); });
plan = gs.planClub_({ partner, club, names: ['amina qwertyson alpha', 'New Girl Testling'], duplicates: ['Grace Zibblewick'], source: 'T!9' },
                    current, state, region, '2026-08-27');
check('case-insensitive match keeps existing girl', plan.toAppend.length === 1 && plan.toAppend[0][col('full_name')] === 'New Girl Testling');
check('vanished girls reported, not removed', plan.vanished.length === 5 && plan.issues.some(i => i.issue === 'Girls missing from the latest enrollment'));
check('duplicate name queued', plan.issues.some(i => i.issue === 'Same name listed twice'));
check('no reactivation when all active', plan.reactivate.length === 0);

console.log('\nplanModification_ — add / remove / reactivate');
current[1].status = gs.STATUS.INACTIVE; current[1].removed_date = '2026-08-01';   // Grace left earlier
state = freshState();
state.registry.byKey[gs.key_(partner) + '||' + gs.key_(club)] = { code: 'SUNRISEC', partner, club };
state.registry.byCode.SUNRISEC = state.registry.byKey[gs.key_(partner) + '||' + gs.key_(club)];
ids.forEach(id => { const m = id.match(/^(.*)-(\d+)$/); state.sequence[m[1]] = Math.max(state.sequence[m[1]] || 0, +m[2]); });
plan = gs.planModification_({
  partner, club, source: 'RC!3',
  adds: ['GRACE ZIBBLEWICK', 'Mary Zibblewick', 'Hope Zibblewick'],
  removes: ['fatuma qwertyson', 'Amina Qwertyson', 'Nobody Here'],
}, current, state, region, '2026-08-28');
check('inactive girl reactivated (same id)', plan.reactivate.length === 1 && plan.reactivate[0].girl_id === current[1].girl_id);
check('active girl reported as already there', plan.alreadyActive.length === 1 && plan.alreadyActive[0] === 'Mary Zibblewick');
check('new girl gets the NEXT number, never reused', plan.toAppend.length === 1 && plan.toAppend[0][col('girl_id')] === 'SUNRISEC-ZIBBLEWICK-003');
check('exact (case-insensitive) removal deactivates', plan.deactivate.length === 1 && plan.deactivate[0].full_name === 'Fatuma Qwertyson');
check('partial name is NOT removed, gets a suggestion',
      plan.unmatched.some(u => u.name === 'Amina Qwertyson' && u.candidates[0] === 'Amina Qwertyson Alpha'));
check('unknown name is NOT removed, no suggestion', plan.unmatched.some(u => u.name === 'Nobody Here' && u.candidates.length === 0));
check('one review issue per unmatched removal', plan.issues.length === 2 && plan.issues.every(i => i.issue === 'Removal did not match anyone'));

check('plan shape is uniform (deactivate present on every plan)',
      Array.isArray(plan.deactivate) && Array.isArray(gs.planClub_({ partner, club, names: [], duplicates: [] }, [], freshState(), region, '2026-08-28').deactivate));

console.log('\nplanModification_ — a name both added and removed is not removed');
plan = gs.planModification_({ partner, club, adds: ['Joy Blorptest'], removes: ['Joy Blorptest'] }, current, state, region, '2026-08-28');
check('add wins over remove for the same name; reported as kept, not unmatched',
      plan.deactivate.length === 0 && plan.alreadyActive.length === 1 && plan.keptBoth.length === 1 && plan.unmatched.length === 0 && plan.issues.length === 0);

console.log('\nplanModification_ — removing an already-inactive girl');
plan = gs.planModification_({ partner, club, adds: [], removes: ['Grace Zibblewick'] }, current, state, region, '2026-08-28');
check('already inactive → noted, no suggestions, no review issue',
      plan.deactivate.length === 0 && plan.alreadyInactive.length === 1 && plan.unmatched.length === 0 && plan.issues.length === 0);

console.log('\nplanModification_ — duplicate names in the ADD list are queued like on the New Club form');
plan = gs.planModification_({ partner, club, adds: ['Zara Testling'], duplicates: ['Zara Testling'], removes: [] }, current, state, region, '2026-08-28');
check('duplicate add raises "Same name listed twice" with a dedupe key',
      plan.issues.length === 1 && plan.issues[0].issue === 'Same name listed twice' && !!plan.issues[0].dedupeKey);
check('unmatched removals carry the name as dedupe key',
      gs.planModification_({ partner, club, adds: [], removes: ['Ghost Name'] }, current, state, region, '2026-08-28').issues[0].dedupeKey === 'ghost name');

// ------------------------------------------------ the replay guard (BACKLOG 41)
console.log('\nthe replay guard: an older response never puts back girls removed after it was sent');
{
  const moon = 'Moonrise Club', SRC = 'Roster Form Responses!2', KEPT = 'Removed girls not put back by an older response';
  const girl = (name, status, removed, sheetRow) => rowObj(['MOONRISE-' + gs.asciiCode_(gs.lastName_(name)) + '-00' + sheetRow,
      partner, moon, region, name, gs.lastName_(name), status, '2026-08-26', removed, 'T!2'], sheetRow);
  const moonRows = () => [
    girl('Grace Zibblewick', gs.STATUS.INACTIVE, '2026-09-12', 2),    // removed after the response
    girl('Mary Zibblewick', gs.STATUS.INACTIVE, '2026-08-31', 3),     // removed the day it was sent
    girl('Joy Blorptest', gs.STATUS.INACTIVE, '2026-08-01', 4),       // removed before it
    girl('Lucía Zörblewick', gs.STATUS.INACTIVE, '', 5),              // removal day not recorded
    girl('Amina Qwertyson', gs.STATUS.ACTIVE, '', 6),
  ];
  const moonState = () => {
    const st = freshState();
    st.registry.byKey[gs.key_(partner) + '||' + gs.key_(moon)] = st.registry.byCode.MOONRISE = { code: 'MOONRISE', partner, club: moon };
    return st;
  };
  const listed = ['GRACE ZIBBLEWICK', 'Mary Zibblewick', 'Joy Blorptest', 'Lucía Zörblewick', 'Amina Qwertyson'];
  const club_ = submitted => gs.planClub_({ partner, club: moon, names: listed, duplicates: [], source: SRC, submitted },
                                          moonRows(), moonState(), region, '2026-09-13');
  const rowsOf = list => list.map(r => r._sheetRow).join(',');

  const none = [club_(undefined), club_(''), club_(null), club_('  ')];
  check('no submitted (missing, blank, null): today\'s behaviour exactly — every inactive girl listed comes back',
        none.every(p => rowsOf(p.reactivate) === '2,3,4,5' && !p.keptRemoved.length && !p.issues.length && !p.toAppend.length));

  let p = club_('2026-08-31');
  check('sent 08-31, run 09-13: removed 09-12 and removal day unknown → kept removed; removed 08-31 and 08-01 → back',
        rowsOf(p.keptRemoved.map(k => k.row)) === '2,5' && rowsOf(p.reactivate) === '3,4', rowsOf(p.reactivate));
  check('kept-removed names are as the mentor typed them (for the e-mail)',
        p.keptRemoved.map(k => k.name).join('|') === 'GRACE ZIBBLEWICK|Lucía Zörblewick');
  const issue = p.issues[0] || { detail: '' };
  check('one ReviewQueue item for the response, tagged with its row',
        p.issues.length === 1 && issue.issue === KEPT && issue.dedupeKey === SRC && issue.club === moon && issue.partner === partner);
  check('its detail: source, sent day, count and Roster rows — never a name',
        issue.detail.startsWith(SRC + ' (sent 2026-08-31): 2 girl(s) it lists were removed after it was sent') &&
        issue.detail.includes('Roster rows 2, 5') && !/zibblewick|z[oö]rblewick|blorptest|qwertyson/i.test(issue.detail), issue.detail);

  p = club_('2026-09-13');
  check('a response sent today (the trigger path): everyone comes back, as before',
        rowsOf(p.reactivate) === '2,3,4,5' && !p.keptRemoved.length && !p.issues.length);
  p = club_('2026-09-12');
  check('sent the same day as the removal: she comes back (removed_date has no time of day)',
        rowsOf(p.reactivate) === '2,3,4' && rowsOf(p.keptRemoved.map(k => k.row)) === '5');

  // Review finding RG-2: a removal day after today (a hand edit, 12/09 read as December) must not
  // block a fresh ADD — the e-mail tells the mentor to send the form again.
  const later = () => { const r = moonRows(); r[1].removed_date = '2026-12-09'; return r; };
  const today13 = (submitted, rows) => gs.planClub_({ partner, club: moon, names: listed, duplicates: [], source: SRC, submitted },
                                                    rows, moonState(), region, '2026-09-13');
  const freshAdd = gs.planModification_({ partner, club: moon, source: SRC, submitted: '2026-09-13',
      adds: ['Mary Zibblewick'], removes: [] }, later(), moonState(), region, '2026-09-13');
  check('a removal day after today counts as unreadable: sent today (a fresh ADD) → back; sent earlier → kept removed',
        rowsOf(today13('2026-09-13', later()).reactivate) === '2,3,4,5' && rowsOf(freshAdd.reactivate) === '3' &&
        !freshAdd.keptRemoved.length && !freshAdd.issues.length &&
        rowsOf(today13('2026-08-31', later()).keptRemoved.map(k => k.row)) === '2,3,5',
        rowsOf(freshAdd.reactivate) + ' / ' + rowsOf(today13('2026-09-13', later()).reactivate));

  const odd = moonRows();
  odd[0].removed_date = '2026-09-12 10:00:00';
  odd[2].removed_date = new Date('2026-08-01T12:00:00Z');   // a raw Date cell loadRoster_ did not turn into text
  p = gs.planClub_({ partner, club: moon, names: listed, duplicates: [], submitted: '2026-08-31' }, odd, moonState(), region, '2026-09-13');
  check('a removal day followed by a time is read as that day; an unreadable cell counts as unknown (kept)',
        rowsOf(p.keptRemoved.map(k => k.row)) === '2,4,5' && rowsOf(p.reactivate) === '3');
  check('no source: the item is still raised, with no tag', p.issues.length === 1 && p.issues[0].dedupeKey === '' &&
        p.issues[0].detail.startsWith('(sent 2026-08-31): 3 girl(s)'));

  const bad = ['2026-8-31', '31/08/2026', '2026-08-31 10:00', 'yesterday', new Date('2026-08-31T12:00:00Z')].filter(v => {
    try { club_(v); return true; } catch (e) { return !/submitted must be yyyy-MM-dd/.test(e.message); }
  });
  check('a submitted that is not exactly yyyy-MM-dd is refused (throws), never ignored', !bad.length, bad.join(' | '));

  const mod = submitted => gs.planModification_({ partner, club: moon, source: SRC, submitted,
      adds: ['grace zibblewick', 'Joy Blorptest', 'Hope Testling'], removes: ['Grace Zibblewick', 'Amina Qwertyson'] },
      moonRows(), moonState(), region, '2026-09-13');
  p = mod('2026-08-31');
  check('Club Roster Form ADD: removed after it was sent → kept removed; removed before → back; unknown name → minted',
        rowsOf(p.keptRemoved.map(k => k.row)) === '2' && p.keptRemoved[0]?.name === 'grace zibblewick' &&
        rowsOf(p.reactivate) === '4' && p.toAppend.length === 1);
  check('the same name under REMOVE is "already removed", never "kept on the roster"',
        p.alreadyInactive.join() === 'Grace Zibblewick' && !p.keptBoth.length && rowsOf(p.deactivate) === '6');
  check('one ReviewQueue item (the kept-removed one), no "did not match"',
        p.issues.length === 1 && p.issues[0].issue === KEPT && p.issues[0].detail.includes('1 girl(s)') &&
        p.issues[0].detail.includes('Roster rows 2. '));
  p = mod(undefined);
  check('…and with no submitted, exactly as before: back on the roster, kept under both lists',
        rowsOf(p.reactivate) === '2,4' && p.keptBoth.join() === 'Grace Zibblewick' && !p.keptRemoved.length && !p.issues.length);
  check('its removals are dated the day it was sent (both sides of the guard are sent days); never after today; none → today',
        mod('2026-08-31').removedOn === '2026-08-31' && mod(undefined).removedOn === '2026-09-13' &&
        mod('2026-09-13').removedOn === '2026-09-13' && mod('2026-09-14').removedOn === '2026-09-13');
  check('every plan carries keptRemoved (uniform shape)',
        Array.isArray(gs.planClub_({ partner, club, names: [], duplicates: [] }, [], freshState(), region, '2026-08-28').keptRemoved) &&
        Array.isArray(gs.planModification_({ partner, club, adds: [], removes: [] }, [], freshState(), region, '2026-08-28').keptRemoved));

  // 2026-09-13: Roster Form Responses!2 (a new-club response sent 08-31) re-ran after its
  // 20 girls had been removed on 09-12, and put all 20 back.
  const nato = ['Alpha', 'Bravo', 'Charlie', 'Delta', 'Echo', 'Foxtrot', 'Golf', 'Hotel', 'India', 'Juliet',
                'Kilo', 'Lima', 'Mike', 'November', 'Oscar', 'Papa', 'Quebec', 'Romeo', 'Sierra', 'Tango'];
  const twenty = nato.map((n, i) => girl('Testgirl ' + n, gs.STATUS.INACTIVE, '2026-09-12', 100 + i));
  const replay = gs.planClub_({ partner, club: moon, names: nato.map(n => 'Testgirl ' + n), duplicates: [], source: SRC,
                                submitted: '2026-08-31' }, twenty, moonState(), region, '2026-09-13');
  check('regression, the 2026-09-13 replay: 0 put back, 20 kept removed, one item, nothing minted',
        !replay.reactivate.length && replay.keptRemoved.length === 20 && replay.issues.length === 1 &&
        !replay.toAppend.length && !replay.vanished.length && replay.issues[0]?.detail.includes('20 girl(s)'));
}

console.log('\nclosestNames_');
check('ranks by shared words', gs.closestNames_('Zibblewick', ['Mary Zibblewick', 'Grace Zibblewick', 'Joy Blorptest']).length === 2);
check('empty query → no candidates', gs.closestNames_('   ', ['Mary Zibblewick']).length === 0);

console.log('\nchooseRegion_ / canonicalRegion_ — the Region picker (backlog 38)');
check('REGIONS pinned, U.S with one dot', gs.REGIONS.join('|') === 'Africa|Asia|Latin America|U.S', gs.REGIONS.join('|'));
check('Partners tab wins over form and derived', gs.chooseRegion_('Asia', 'Africa', 'U.S') === 'Asia');
check('tab value used verbatim after tidy (a staff typo is not vetoed)', gs.chooseRegion_(' africa ', 'Asia', '') === 'africa');
check('form answer used when the tab is blank', gs.chooseRegion_('', 'Latin America', 'Africa') === 'Latin America');
check('form answer canonicalized: case + whitespace', gs.chooseRegion_('', '  u.s ', '') === 'U.S');
check('invalid form answer falls through to derived', gs.chooseRegion_('', 'Europe', 'Africa') === 'Africa');
check('all blank or undefined → empty string',
      gs.chooseRegion_('', '', '') === '' && gs.chooseRegion_(undefined, undefined, undefined) === '');
check('"U.S." (trailing dot) is not a region', gs.canonicalRegion_('U.S.') === '');
check('"USA" is not a region', gs.canonicalRegion_('USA') === '');
check('blank / whitespace / null / undefined → empty',
      ['', '   ', null, undefined].every(v => gs.canonicalRegion_(v) === ''));
check('every canonical region maps to itself', gs.REGIONS.every(r => gs.canonicalRegion_(r) === r));
check('derived map keys are key_-normalized, values non-empty', (function () {
  const d = gs.derivedPartnerRegions_();
  const ks = Object.keys(d);
  return ks.length > 0 && ks.every(k => k === gs.key_(k) && !!d[k]);
})());

// ------------------------------- FormLog keys and the missed-responses menu
// FormHandlers.gs calls Google services only inside functions, so its pure
// helpers load next to Config.gs and Normalize.gs (as dispatch_test.js does).
console.log('\nFormLog keys and "Process any missed form responses" (FormHandlers.gs)');
const fh = loadGs(['Q', 'OTHER_PARTNER', 'MISSED', 'RETRY_PREFIXES', 'RESPONSE_STAMP_FORMAT', 'missedOrder_',
                   'isRetryResult_', 'responseTail_', 'responseKeyOf_', 'sameCellAcrossZones_', 'indexFormLog_',
                   'responseDone_', 'planMissedRun_', 'missedPreviewText_', 'previewError_',
                   'daysBetween_'],
                  ['Config.gs', 'Normalize.gs', 'FormHandlers.gs']);
const FQ = fh.Q;
const ORG = 'Test Partner Org';
// A Timestamp cell whose text is `wall`, read while the spreadsheet is at UTC+offsetMin:
// what responseStamp_ returns for it (the milliseconds depend on the zone, the text does not).
const cellAt = (wall, offsetMin) => {
  const m = /^(\d{4})-(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d)\.(\d{3})$/.exec(wall);
  return { wall, ms: Date.UTC(+m[1], m[2] - 1, +m[3], +m[4], +m[5], +m[6], +m[7]) - offsetMin * 60000 };
};
const newClubAnswers = c => ({ [FQ.ACTION]: FQ.ACTION_NEW, [FQ.PARTNER_NEW]: ORG, [FQ.CLUB]: c,
                               [FQ.ROSTER]: 'Grace Zibblewick\nMary Zibblewick',
                               [FQ.MENTOR_EMAIL]: 'mentor@example.org' });
const changeAnswers = c => ({ [FQ.ACTION]: FQ.ACTION_MOD, [FQ.PARTNER_MOD]: ORG,
                              [FQ.CLUB_PREFIX + ORG + ')']: c, [FQ.REMOVE]: 'Grace Zibblewick',
                              [FQ.MENTOR_EMAIL_MOD]: 'mentor@example.org' });
const reportAnswers = f => ({ [FQ.FB_FORM]: f, [FQ.FB_WHAT]: 'Grace Zibblewick is not on the list',
                              [FQ.FB_EMAIL]: 'mentor@example.org' });

// The key this code wrote before 2026-09-27 (which|<ms>|partner|club) — what FormLog holds today.
const legacyKey = (which, stamp, answers) => which + '|' + stamp.ms + '|' + fh.responseTail_(answers);

console.log('\n  the key: the Timestamp cell\'s own text, whatever the time zone');
{
  const utc = cellAt('2026-08-31 12:04:30.549', 0), utc4 = cellAt('2026-08-31 12:04:30.549', -240);
  check('new club: form|w:<wall>|partner|club',
        fh.responseKeyOf_('ROSTER', utc4, newClubAnswers('Sunrise Club')) ===
        'ROSTER|w:2026-08-31 12:04:30.549|Test Partner Org|Sunrise Club');
  check('one cell read at UTC and at UTC-4: the same key, milliseconds 4 h apart',
        fh.responseKeyOf_('ROSTER', utc, newClubAnswers('Sunrise Club')) ===
        fh.responseKeyOf_('ROSTER', utc4, newClubAnswers('Sunrise Club')) && utc4.ms - utc.ms === 14400000);
}
check('roster change: the club comes from its partner\'s section',
      fh.responseKeyOf_('ROSTER', cellAt('2026-09-27 08:00:00.000', -240), changeAnswers('Sunrise Club')) ===
      'ROSTER|w:2026-09-27 08:00:00.000|Test Partner Org|Sunrise Club');
check('problem report: the form it names stands in for the partner, no club',
      fh.responseKeyOf_('FEEDBACK', cellAt('2026-09-02 22:23:23.680', -240), reportAnswers('Latin America Attendance Form')) ===
      'FEEDBACK|w:2026-09-02 22:23:23.680|Latin America Attendance Form|');
check('a stamp that is not a date keeps its text',
      fh.responseKeyOf_('ROSTER', { text: '9/1/2026 1:33:23' }, newClubAnswers('Sunrise Club')) ===
      'ROSTER|9/1/2026 1:33:23|Test Partner Org|Sunrise Club');
check('partner/club tidied (spaces, invisible characters)',
      fh.responseTail_({ [FQ.PARTNER_NEW]: ' Test​ Partner  Org ', [FQ.CLUB]: 'Sunrise Club ' }) ===
      'Test Partner Org|Sunrise Club');
check('stamp format pinned (yyyy, not the week-year YYYY)', fh.RESPONSE_STAMP_FORMAT === 'yyyy-MM-dd HH:mm:ss.SSS');
{
  const src = fs.readFileSync(path.join(REPO, 'appsscript', 'FormHandlers.gs'), 'utf8');
  check('the stamp is read in the spreadsheet\'s zone, never the script\'s',
        /getSpreadsheetTimeZone\(\)/.test(src) && !/getScriptTimeZone/.test(src));
}

console.log('\n  FormLog results');
check('ERROR: is the one retry prefix', fh.RETRY_PREFIXES.join(',') === 'ERROR:');
check('ERROR means try again; anything else (even blank) means done',
      fh.isRetryResult_('ERROR: STAFF_NOTIFY_EMAIL is not set') && !fh.isRetryResult_('emailed staff') &&
      !fh.isRetryResult_('') && !fh.isRetryResult_(null));
{
  const idx = fh.indexFormLog_([['ROSTER', 4, 'ROSTER|9|x|y', 'ERROR: boom'],
                                ['ROSTER', 4, 'ROSTER|9|x|y', 'new club y (x): 2 girls added'],
                                ['ROSTER', 5, 'ROSTER|10|x|z', 'ERROR: boom'],
                                ['ROSTER', 6, '', 'orphan row without a key']]);
  check('a later success counts as done', idx.done['ROSTER|9|x|y'] === true && idx.okRows['ROSTER|4'] === true &&
        idx.legacy['ROSTER|x|y'].join() === '9');
  check('a failure alone does not', !idx.done['ROSTER|10|x|z'] && !idx.legacy['ROSTER|x|z'] &&
        idx.errorsByRow['ROSTER|5'] === 'ERROR: boom');
  check('rows without a key are ignored', !idx.okRows['ROSTER|6']);
}

console.log('\n  keys written before 2026-09-27 still count');
{
  const answers = newClubAnswers('Sunrise Club');
  const wall = '2026-08-31 12:04:30.549';
  const doneAt = (loggedMin, readMin, a) => fh.responseDone_('ROSTER', cellAt(wall, readMin), a || answers,
      fh.indexFormLog_([['ROSTER', 2, legacyKey('ROSTER', cellAt(wall, loggedMin), answers), 'new club Sunrise Club (Test Partner Org): 2 girls added']]));
  check('logged at UTC, read at UTC, +4 h, -5 h, +5:30, +13 h, +14 h, -12 h',
        [0, 240, -300, 330, 780, 840, -720].every(m => doneAt(0, m)));
  check('logged at UTC+14, read at UTC-12: the full 26 h', doneAt(840, -720));
  const t = cellAt(wall, 0).ms;
  check('not a millisecond off the quarter-hour, not beyond 26 h',
        !fh.sameCellAcrossZones_(t, t + 4 * 3600000 + 1) && !fh.sameCellAcrossZones_(t, t + 7 * 60000) &&
        !fh.sameCellAcrossZones_(t, t + 26 * 3600000 + 15 * 60000) && fh.sameCellAcrossZones_(t, t - 26 * 3600000));
  check('not for another club', !doneAt(0, -240, newClubAnswers('Moonrise Club')));
  check('not for the other form', !fh.responseDone_('FEEDBACK', cellAt(wall, -240), answers,
      fh.indexFormLog_([['ROSTER', 2, legacyKey('ROSTER', cellAt(wall, 0), answers), 'ok']])));
  check('a failure under an old key never counts', !fh.responseDone_('ROSTER', cellAt(wall, -240), answers,
      fh.indexFormLog_([['ROSTER', 2, legacyKey('ROSTER', cellAt(wall, 0), answers), 'ERROR: boom']])));
  check('a new key matches on the stamp alone: a club cell edited later does not re-open the row',
        fh.responseDone_('ROSTER', cellAt(wall, -240), newClubAnswers('Sunrise Club (renamed)'),
            fh.indexFormLog_([['ROSTER', 2, fh.responseKeyOf_('ROSTER', cellAt(wall, -240), answers), 'ok']])));
  const textIdx = fh.indexFormLog_([['ROSTER', 2, 'ROSTER|9/1/2026 1:33:23|Test Partner Org|Sunrise Club', 'ok']]);
  check('a text stamp matches exactly, nothing else',
        fh.responseDone_('ROSTER', { text: '9/1/2026 1:33:23' }, answers, textIdx) &&
        !fh.responseDone_('ROSTER', { text: '9/1/2026 1:33:24' }, answers, textIdx));
}

console.log('\n  the menu plan: the 2026-09-13 replay cannot happen again');
{
  // Rows 2-3 and report 2 were logged under the old key while the sheet was at UTC; today it
  // is at UTC-4 (the 2026-09-02 change). Row 7 has a new key; row 9 was logged under a club
  // spelling its cell no longer has (re-keyed some other way).
  const r2 = cellAt('2026-08-31 12:04:30.549', 0), r3 = cellAt('2026-08-31 12:07:26.625', 0);
  const f2 = cellAt('2026-09-02 22:23:23.680', 0), r7 = cellAt('2026-09-20 10:00:00.001', -240);
  const r9 = cellAt('2026-09-01 09:00:00.000', 0);
  const log = [
    ['ROSTER', 2, 'ROSTER|' + r2.ms + '|Test Partner Org|Sunrise Club', 'existing club Sunrise Club (Test Partner Org): 0 girls added'],
    ['ROSTER', 3, legacyKey('ROSTER', r3, changeAnswers('Moonrise Club')), 'Moonrise Club (Test Partner Org): 0 added, 0 reactivated, 1 removed'],
    ['FEEDBACK', 2, legacyKey('FEEDBACK', f2, reportAnswers('Latin America Attendance Form')), 'ERROR: STAFF_NOTIFY_EMAIL is not set in Script Properties'],
    ['ROSTER', 7, fh.responseKeyOf_('ROSTER', r7, newClubAnswers('Starlight Club')), 'new club Starlight Club (Test Partner Org): 2 girls added'],
    ['ROSTER', 9, legacyKey('ROSTER', r9, newClubAnswers('Old Galaxy Club')), 'new club Old Galaxy Club (Test Partner Org): 2 girls added'],
  ];
  const today = '2026-09-27';
  const at = (stamp, min) => cellAt(stamp.wall, min);
  const responsesAt = min => [
    { which: 'ROSTER', row: 2, tab: 'Roster Form Responses', stamp: at(r2, min), answers: newClubAnswers('Sunrise Club') },
    { which: 'ROSTER', row: 3, tab: 'Roster Form Responses', stamp: at(r3, min), answers: changeAnswers('Moonrise Club') },
    { which: 'ROSTER', row: 5, tab: 'Roster Form Responses', stamp: cellAt('2026-09-27 08:00:00.000', min), answers: changeAnswers('Sunrise Club') },
    { which: 'ROSTER', row: 6, tab: 'Roster Form Responses', stamp: cellAt('2026-09-17 08:00:00.000', min), answers: newClubAnswers('Comet Club') },
    { which: 'ROSTER', row: 7, tab: 'Roster Form Responses', stamp: at(r7, min), answers: newClubAnswers('Starlight Club') },
    { which: 'ROSTER', row: 8, tab: 'Roster Form Responses', stamp: cellAt('2026-09-20 08:00:00.000', min), answers: newClubAnswers('Nova Club') },
    { which: 'ROSTER', row: 9, tab: 'Roster Form Responses', stamp: at(r9, min), answers: newClubAnswers('Galaxy Club') },
    { which: 'FEEDBACK', row: 2, tab: 'Feedback', stamp: at(f2, min), answers: reportAnswers('Latin America Attendance Form') },
  ];
  const responses = responsesAt(-240);
  const oldCheckDone = r => log.some(l => l[2] === legacyKey(r.which, r.stamp, r.answers) && !/^ERROR:/.test(l[3]));
  check('regression: the old millisecond check would re-run rows 2 and 3 today',
        !oldCheckDone(responses[0]) && !oldCheckDone(responses[1]));
  const plan = fh.planMissedRun_(responses, fh.indexFormLog_(log), today, 7);
  const src = items => items.map(i => i.source).join(', ');
  check('rows 2 and 3 are recognised as done (old keys, shifted by the zone change)',
        !/!2\b|!3\b/.test(src(plan.run.concat(plan.old, plan.held).filter(i => i.which === 'ROSTER'))));
  check('a row FormLog has as processed under a key that no longer matches is HELD, never run',
        src(plan.held) === 'Roster Form Responses!9', src(plan.held));
  check('run = the failed report first, then new rows up to 7 days old',
        src(plan.run) === 'Feedback!2, Roster Form Responses!5, Roster Form Responses!8', src(plan.run));
  check('a never-logged Club Roster Form row over 7 days old needs its own YES',
        src(plan.old) === 'Roster Form Responses!6', src(plan.old));
  check('the failed report is a retry with its last error; new rows are new',
        plan.run[0].status === 'retry' && /STAFF_NOTIFY_EMAIL/.test(plan.run[0].lastError) &&
        plan.run[1].status === 'new');
  // Process everything that ran (new keys, as the code writes them), then change the zone again.
  const after = log.concat(plan.run.concat(plan.old).map(i => [i.which, i.row, i.key, 'ok']));
  const later = [780, -720].map(min => fh.planMissedRun_(responsesAt(min), fh.indexFormLog_(after), today, 7));
  check('after a later switch to UTC+13 or UTC-12: nothing to run, only the held row',
        later.every(p => !p.run.length && !p.old.length && src(p.held) === 'Roster Form Responses!9'));
  const fresh = fh.planMissedRun_(responsesAt(-240).concat([{ which: 'ROSTER', row: 10, tab: 'Roster Form Responses',
      stamp: cellAt('2026-09-27 09:30:00.250', -240), answers: newClubAnswers('Sunrise Club') }]),
      fh.indexFormLog_(after), today, 7);
  check('a brand-new submission is still picked up', src(fresh.run) === 'Roster Form Responses!10', src(fresh.run));
  const lateReport = fh.planMissedRun_([{ which: 'FEEDBACK', row: 9, tab: 'Feedback',
      stamp: cellAt('2026-08-01 08:00:00.000', -240), answers: reportAnswers('U.S Attendance Form') }],
      fh.indexFormLog_([]), today, 7);
  check('a problem report is never "old" (it only e-mails staff)', lateReport.run.length === 1 && !lateReport.old.length);
  const noDate = fh.planMissedRun_([{ which: 'ROSTER', row: 9, tab: 'Roster Form Responses',
      stamp: { text: 'not a date' }, answers: newClubAnswers('Sunrise Club') }], fh.indexFormLog_([]), today, 7);
  check('a Club Roster Form row with no readable date counts as old', noDate.old.length === 1 && !noDate.run.length);

  console.log('\n  the preview');
  const text = fh.missedPreviewText_('Problem reports (1):', plan.run.slice(0, 1), 15);
  check('a line names row, date, kind, form and the last error',
        text.split('\n')[1] === '• row 2 · sent 2026-09-02 22:23 · problem report · about the Latin America ' +
        'Attendance Form · retry after ERROR: STAFF_NOTIFY_EMAIL is not set in Script Properties');
  const all = fh.missedPreviewText_('All:', plan.run.concat(plan.old, plan.held), 15);
  check('club (partner) for Club Roster Form rows',
        all.includes('roster change · Sunrise Club (Test Partner Org)') && all.includes('new club · Comet Club (Test Partner Org)'));
  check('never a girl\'s name or an e-mail address from the answers',
        !/Zibblewick|example\.org|@/.test(all));
  check('e-mail addresses in an error are blanked; long errors are cut',
        fh.previewError_('ERROR: could not email mentor@example.org: quota') === 'ERROR: could not email <e-mail> quota' &&
        fh.previewError_('ERROR: ' + 'x'.repeat(200)).length === 80);
  const many = Array.from({ length: 20 }, (_, i) => ({ row: i + 2, sent: '2026-09-27 08:00', kind: 'new club', what: 'Club (Org)' }));
  const capped = fh.missedPreviewText_('Many:', many, fh.MISSED.MAX_LISTED).split('\n');
  check('at most MAX_LISTED rows, then "… and N more"',
        capped.length === 17 && capped[16] === '… and 5 more', capped.length + ' lines');
  check('a new-organization row shows the typed partner',
        fh.missedPreviewText_('x', fh.planMissedRun_([{ which: 'ROSTER', row: 4, tab: 'T',
            stamp: cellAt('2026-09-27 08:00:00.000', -240),
            answers: { [FQ.ACTION]: FQ.ACTION_NEW, [FQ.PARTNER_NEW]: fh.OTHER_PARTNER,
                       [FQ.NEW_PARTNER]: 'Brand New Org', [FQ.CLUB]: 'Sunrise Club' } }],
            fh.indexFormLog_([]), today, 7).run, 15).includes('Sunrise Club (Brand New Org)'));
}
console.log('\n  held rows, failed old rows');
{
  const today = '2026-09-27';
  // Someone sorted the tab: Alpha (processed at row 5) now sits at row 6; Bravo (never run) at row 5.
  const alpha = cellAt('2026-09-26 08:00:00.000', -240), bravo = cellAt('2026-09-26 09:00:00.000', -240);
  const alphaKey = fh.responseKeyOf_('ROSTER', alpha, newClubAnswers('Alpha Club'));
  const sorted = [
    { which: 'ROSTER', row: 5, tab: 'Roster Form Responses', stamp: bravo, answers: newClubAnswers('Bravo Club') },
    { which: 'ROSTER', row: 6, tab: 'Roster Form Responses', stamp: alpha, answers: newClubAnswers('Alpha Club') },
  ];
  const src = items => items.map(i => i.source).join(', ');
  const before = fh.planMissedRun_(sorted, fh.indexFormLog_([['ROSTER', 5, alphaKey, 'new club Alpha Club (Test Partner Org): 2 girls added']]), today, 7);
  check('after a sort, the never-run row that landed on a logged row number is held', src(before.held) === 'Roster Form Responses!5' && !before.run.length);
  const released = fh.planMissedRun_(sorted, fh.indexFormLog_([['ROSTER', 'released 5 by Ryan 2026-09-27', alphaKey, 'new club Alpha Club (Test Partner Org): 2 girls added']]), today, 7);
  check('RUNBOOK release (change that FormLog row\'s sheet_row): only the held row runs, Alpha stays done',
        src(released.run) === 'Roster Form Responses!5' && !released.held.length && !released.old.length);
  const wrong = fh.planMissedRun_(sorted, fh.indexFormLog_([['ROSTER', 5, alphaKey, 'ERROR: released']]), today, 7);
  check('(why not by turning its result into ERROR: that would offer the processed Alpha again)',
        /!6/.test(src(wrong.run)));
  const failedOld = fh.planMissedRun_([{ which: 'ROSTER', row: 4, tab: 'Roster Form Responses',
      stamp: cellAt('2026-09-10 08:00:00.000', -240), answers: newClubAnswers('Sunrise Club') }],
      fh.indexFormLog_([['ROSTER', 4, fh.responseKeyOf_('ROSTER', cellAt('2026-09-10 08:00:00.000', -240), newClubAnswers('Sunrise Club')), 'ERROR: incomplete submission: missing roster']]), today, 7);
  check('a Club Roster Form row that FAILED more than 7 days ago is old too (a retry replays into today\'s roster)',
        failedOld.old.length === 1 && failedOld.old[0].status === 'retry' && /incomplete/.test(failedOld.old[0].lastError) && !failedOld.run.length);
  const dismissed = fh.planMissedRun_([{ which: 'FEEDBACK', row: 2, tab: 'Feedback', stamp: cellAt('2026-09-02 22:23:23.680', -240),
      answers: reportAnswers('Latin America Attendance Form') }],
      fh.indexFormLog_([['FEEDBACK', 2, 'FEEDBACK|' + cellAt('2026-09-02 22:23:23.680', 0).ms + '|Latin America Attendance Form|',
                         'resolved by hand by Ryan 2026-09-27']]), today, 7);
  check('RUNBOOK dismiss (an old ERROR result rewritten by hand) counts as done, across the zone change',
        !dismissed.run.length && !dismissed.old.length && !dismissed.held.length);
}

console.log('\n  the menu run itself (processMissedResponses; Google services stubbed)');
{
  const vm = require('vm');
  const src = ['Config.gs', 'Normalize.gs', 'FormHandlers.gs']
      .map(f => fs.readFileSync(path.join(loadGs.GS_DIR, f), 'utf8')).join('\n');
  // Returns what ran and what Audit got, answering the YES/NO dialogs in turn.
  const runMenu = (responses, log, replies) => {
    const ran = [], audits = [], dialogs = [];
    const ctx = vm.createContext({
      console,
      SpreadsheetApp: { getUi: () => ({
        alert: (title, text, buttons) => { dialogs.push(text); return buttons === 'YES_NO' ? replies.shift() : 'OK'; },
        Button: { YES: 'YES', NO: 'NO' }, ButtonSet: { YES_NO: 'YES_NO', OK: 'OK' } }) },
      LockService: { getDocumentLock: () => ({ tryLock: () => true, releaseLock: () => {} }) },
      Utilities: { sleep: () => {} },
    });
    vm.runInContext(src, ctx);
    // function declarations are properties of the vm's global object, so these replace them
    ctx.readMissedSnapshot_ = () => ({ zone: 'America/New_York', sheets: {}, responses,
                                       index: ctx.indexFormLog_(log), today: '2026-09-27' });
    ctx.runConfirmed_ = item => { ran.push(item.source); return item.source + ' ok'; };
    ctx.audit_ = (action, detail) => audits.push(action + ': ' + detail);
    vm.runInContext('processMissedResponses()', ctx);
    return { ran, audits, dialogs };
  };
  const R = (row, day, club, isChange) => ({ which: 'ROSTER', row, tab: 'Roster Form Responses',
      stamp: cellAt(day + ' 08:00:00.000', -240), answers: isChange ? changeAnswers(club) : newClubAnswers(club) });
  const responses = [R(8, '2026-09-24', 'Comet Club', true), R(6, '2026-09-17', 'Comet Club'), R(5, '2026-09-26', 'Nova Club'),
                     { which: 'FEEDBACK', row: 2, tab: 'Feedback', stamp: cellAt('2026-09-02 22:23:23.680', -240),
                       answers: reportAnswers('Latin America Attendance Form') }];
  const all = runMenu(responses, [], ['YES', 'YES', 'YES']);
  check('three questions (problem reports, recent Club Roster Form rows, old ones), then the result', all.dialogs.length === 4 &&
        /^Problem reports/.test(all.dialogs[0]) && /^Club Roster Form responses not yet/.test(all.dialogs[1]) &&
        /more than 7 days ago/.test(all.dialogs[2]), all.dialogs.length + ' dialogs');
  check('YES to all: rows run in sheet order, the old enrollment (6) before its change (8)',
        all.ran.join(', ') === 'Feedback!2, Roster Form Responses!5, Roster Form Responses!6, Roster Form Responses!8',
        all.ran.join(', '));
  check('Audit: started (before the first row) and finished',
        all.audits.length === 2 && /^processMissedResponses: started: Feedback!2, /.test(all.audits[0]) &&
        /^processMissedResponses: finished: .*; 0 left$/.test(all.audits[1]));
  const noOld = runMenu(responses, [], ['YES', 'YES', 'NO']);
  check('NO to the old rows: they do not run, and Audit says they were declined',
        noOld.ran.join(', ') === 'Feedback!2, Roster Form Responses!5, Roster Form Responses!8' &&
        /declined: Roster Form Responses!6/.test(noOld.audits[0]));
  const none = runMenu(responses, [], ['NO', 'NO', 'NO']);
  check('NO to everything: nothing runs; the only write is one Audit row',
        !none.ran.length && none.audits.length === 1 &&
        /^processMissedResponses: cancelled at the preview \(would have run Feedback!2, /.test(none.audits[0]));
  const nothing = runMenu([], [], []);
  check('nothing pending: one "Nothing to process." message, no Audit row',
        !nothing.ran.length && !nothing.audits.length && nothing.dialogs.join() === 'Nothing to process.');
}

check('daysBetween_: whole days, NaN for a non-date',
      fh.daysBetween_('2026-09-20', '2026-09-27') === 7 && Number.isNaN(fh.daysBetween_('', '2026-09-27')));
check('menu limits: 240 s budget (6-minute limit), 30 s lock wait (< the trigger\'s 120 s), 7 days, 15 lines',
      fh.MISSED.BUDGET_MS === 240000 && fh.MISSED.LOCK_WAIT_MS === 30000 &&
      fh.MISSED.OLD_AFTER_DAYS === 7 && fh.MISSED.MAX_LISTED === 15);

// ------------------ problem reports that are roster changes; the weekly e-mail
console.log('\nProblem reports → ReviewQueue, and the weekly e-mail (FormHandlers.gs)');
const pr = loadGs(['Q', 'TAB', 'REVIEW_ISSUES', 'OTHER_ISSUE', 'DIGEST', 'looksLikeRosterChange_',
                   'feedbackReviewItem_', 'sentDayOfKey_', 'responseRowTag_', 'reviewDigest_',
                   'sfPendingLines_'],
                  ['Config.gs', 'Normalize.gs', 'FormHandlers.gs']);
const PQ = pr.Q;
const CANARY = 'Hope Fennwhistle';   // a fictional girl: must never reach an e-mail, a digest or Audit
const report = (form, what, extra) => Object.assign({ [PQ.FB_FORM]: form, [PQ.FB_WHAT]: what }, extra || {});

console.log('\n  which reports are roster changes');
{
  const AF = 'Africa Attendance Form', LA = 'Latin America Attendance Form';
  const cases = [
    ['GLOW – Club Roster Form', 'The form would not let me choose my club.', {}, 'form'],
    ['Club Roster Form (add or remove girls)', 'x', {}, 'form'],
    [AF, 'Two new girls joined this week: Hana Marrowgate and Esther Ostrivane.', {}, 'text'],
    ['Something else', 'Amara Fennwhistle left for boarding school, so we now have 18 girls.', {}, 'text'],
    [AF, 'The list of girls on the attendance form is not the updated one.', {}, 'text'],
    [AF, 'Please add Chiara Pellucidor and Dalia Thornquibble to the roster.', {}, 'text'],
    [AF, 'Please remove Grace Zibblewick from our club, she moved away.', {}, 'text'],
    [LA, 'Por favor quitar a Grace Zibblewick de la lista, se fue a otra ciudad.', {}, 'text'],
    [LA, 'Dos niñas nuevas: Hana Marrowgate y Esther Ostrivane.', {}, 'text'],
    [AF, 'The form will not submit.', { [PQ.FB_DOING]: 'Add two girls to our list' }, 'text'],
    [AF, 'Nova Girls Club: two girls left.', { [PQ.FB_CLUB]: 'Nova Girls Club' }, 'text'],
    [AF, 'The page left me on a blank screen after I pressed Submit.', {}, ''],
    [AF, 'I could not add a photo of today\'s session.', {}, ''],
    ['Something else', 'The list of clubs is missing mine.', {}, ''],
    [AF, 'When I choose our club, the girls\' names do not show.', {}, ''],
    [AF, 'I typed my own name as the club name by mistake. Please change it.', {}, ''],
    [AF, 'The new orientation session is missing from the list.', {}, ''],
    [LA, 'La sesión de hoy fue sobre autoestima y las niñas participaron mucho.', {}, ''],
    [LA, 'Tuve que actualizar la página y la lista no carga.', {}, ''],
    [AF, 'Nova Girls Club: the form left me on a blank page.', { [PQ.FB_CLUB]: 'Nova Girls Club' }, ''],
    [LA, 'Grace Zibblewick is not on the list', {}, ''],
    [AF, '', {}, ''],
  ];
  const wrong = cases.filter(([f, w, x, want]) => pr.looksLikeRosterChange_(report(f, w, x)) !== want)
      .map(([f, w]) => w.slice(0, 40));
  check('22 wordings classified as expected (Club Roster Form chosen, roster words + change words, Spanish)',
        !wrong.length, wrong.join(' | '));
  // Accepted misses (no roster word, other form chosen): "Please remove Grace Zibblewick,
  // who moved away." / "Please add Chiara Pellucidor and Dalia Thornquibble." Every real
  // request of this kind chose the Club Roster Form; the staff e-mail goes out regardless.
}

console.log('\n  the ReviewQueue item never carries the report');
{
  const a = report('GLOW – Club Roster Form', 'Please remove ' + CANARY,
                   { [PQ.FB_DOING]: CANARY, [PQ.FB_PARTNER]: '=HYPERLINK("x")', [PQ.FB_CLUB]: 'Bright Stars',
                     [PQ.FB_EMAIL]: 'mentor@example.org' });
  const it = pr.feedbackReviewItem_(a, 'Feedback!7', '2026-09-20', 'form');
  check('issue, tag = the source, partner/club as typed', it.issue === 'Roster change sent as a problem report' &&
        it.dedupeKey === 'Feedback!7' && it.club === 'Bright Stars');
  check('a leading = is stripped (never a formula in the sheet)', it.partner === 'HYPERLINK("x")', it.partner);
  const typedAs = v => pr.feedbackReviewItem_(report('x', 'y', { [PQ.FB_PARTNER]: v }), 'Feedback!9', '', 'text').partner;
  const bypass = ['= =1+1', '- =x', '@ =A1', '+ + =1', '=\t=x', '\u00a0=x', '\u200b=x'].filter(v => /^[=+\-@]/.test(typedAs(v)));
  check('…and no mix of = + - @ and spaces gets one through', !bypass.length && typedAs('= =1+1') === '1+1', bypass.join(' | '));
  check('detail: where, when, why — never the report text or the reply address',
        it.detail.startsWith('Feedback!7 (sent 2026-09-20; Club Roster Form chosen): enter it on the Club Roster Form') &&
        !/Fennwhistle|example\.org/.test(it.detail));
  check('typed partner/club capped at 80 characters',
        pr.feedbackReviewItem_(report('x', 'y', { [PQ.FB_CLUB]: 'x'.repeat(200) }), 'Feedback!8', '', 'text').club.length === 80);
  check('the sent day comes from a new key; an older key gives none',
        pr.sentDayOfKey_('FEEDBACK|w:2026-09-20 08:15:38.000|GLOW – Club Roster Form|') === '2026-09-20' &&
        pr.sentDayOfKey_('FEEDBACK|1789820138000|GLOW – Club Roster Form|') === '');
  check('only response-row tags may be shown; name tags never',
        pr.responseRowTag_('x [#Feedback!7]') === 'Feedback!7' &&
        pr.responseRowTag_('x [#Roster Form Responses!41]') === 'Roster Form Responses!41' &&
        pr.responseRowTag_('x [#hope fennwhistle]') === '' && pr.responseRowTag_('x [#a|b]') === '' &&
        pr.responseRowTag_('x [#Sheet9!3]') === '' && pr.responseRowTag_('no tag') === '');
}

console.log('\n  the weekly e-mail\'s ReviewQueue section');
{
  const known = { partners: { 'fixture partner alpha': 'Fixture Partner Alpha' }, clubs: { 'bright stars': 'Bright Stars' } };
  const rq = (row, raised, issue, partner, club, detail, resolved) => ({ row, raised, issue, partner, club, detail, resolved: resolved || '' });
  const rows = [
    rq(2, '2026-08-26', 'Same name listed twice', 'Fixture Partner Alpha', 'Bright Stars', CANARY + ', ' + CANARY + ' — listed more than once [#hope fennwhistle]'),
    rq(3, '2026-09-26', 'Removal did not match anyone', 'Fixture Partner Alpha', 'Bright Stars', '"' + CANARY + '" is not on this club\'s active roster [#hope fennwhistle]'),
    rq(4, '2026-09-27', 'Roster change sent as a problem report', '', CANARY + ' Club', 'Feedback!7 (sent 2026-09-20; report text): … [#Feedback!7]'),
    rq(5, '2026-09-10', 'Typed by hand about ' + CANARY, '', '', ''),
    rq(6, '2026-09-01', 'Removal did not match anyone', 'Fixture Partner Alpha', 'Bright Stars', CANARY, 'resolved 2026-09-20 by Ryan: removed as Roster Form Responses!41'),
    rq(7, '', 'Partner has no region', 'Fixture Partner Alpha', '', 'x'),
  ];
  const d = pr.reviewDigest_(rows, '2026-09-28', known);
  const text = d.lines.join('\n');
  check('5 open (resolved rows left out), 2 new this week', d.open === 5 && d.fresh === 2, d.open + '/' + d.fresh);
  check('no girl\'s name anywhere: not from a tag, a typed club, a hand-typed issue or the detail',
        !/fennwhistle/i.test(text));
  check('the problem-report item first, with its Feedback row and an off-file club masked',
        d.lines[2] === 'Roster change sent as a problem report: 1 open, 1 new, oldest 1 day(s)' &&
        d.lines[3] === '  - row 4 · raised 2026-09-27 · (partner not given) / (club not on file) · Feedback!7', d.lines[3]);
  check('on-file partner/club shown; ages in days; an unknown date shows "?"',
        text.includes('Same name listed twice: 1 open, oldest 33 day(s)') &&
        text.includes('  - row 3 · raised 2026-09-26 · Fixture Partner Alpha / Bright Stars') &&
        text.includes('  - row 7 · raised ? · Fixture Partner Alpha / (club not given)') && !/NaN/.test(text));
  check('an issue the code never raises is grouped as "Other (added by hand)"',
        text.includes(pr.OTHER_ISSUE + ': 1 open'));
  const many = Array.from({ length: 12 }, (_, i) => rq(i + 2, '2026-09-20', 'Removal did not match anyone', 'Fixture Partner Alpha', 'Bright Stars', 'x'));
  const capped = pr.reviewDigest_(many, '2026-09-28', known).lines;
  check('at most DIGEST.MAX_PER_ISSUE lines per issue, then "… and N more"',
        capped.filter(l => l.startsWith('  - row')).length === pr.DIGEST.MAX_PER_ISSUE && capped.includes('  … and 2 more'));
  const edge = pr.reviewDigest_([rq(2, '2026-09-21', 'Partner has no region', 'Fixture Partner Alpha', '', 'x'),
                                 rq(3, '2026-09-28', 'Partner has no region', 'Fixture Partner Alpha', '', 'x'),
                                 rq(4, CANARY + ' said so', 'Partner has no region', 'Fixture Partner Alpha', '', 'x')], '2026-09-28', known);
  check('"new" = raised since the previous Monday e-mail: 7 days ago yes, today no (it counts next week)',
        edge.fresh === 1 && edge.lines.join('\n').includes('Partner has no region: 3 open, 1 new'), String(edge.fresh));
  check('a raised cell that is not a date prints "?" (the cell is free text)',
        edge.lines.join('\n').includes('  - row 4 · raised ? ·') && !/fennwhistle/i.test(edge.lines.join('\n')));
  const backlog = Array.from({ length: 11 }, (_, i) => rq(i + 2, '2026-09-01', 'Same name listed twice', 'Fixture Partner Alpha', 'Bright Stars', 'x'))
      .concat([rq(40, '2026-09-27', 'Same name listed twice', 'Fixture Partner Alpha', 'Bright Stars', 'x')]);
  const blines = pr.reviewDigest_(backlog, '2026-09-28', known).lines;
  check('over the cap, this week\'s item is still listed (first), the backlog after it',
        blines.includes('  - row 40 · raised 2026-09-27 · Fixture Partner Alpha / Bright Stars') &&
        blines.indexOf('  - row 40 · raised 2026-09-27 · Fixture Partner Alpha / Bright Stars') < blines.indexOf('  - row 2 · raised 2026-09-01 · Fixture Partner Alpha / Bright Stars') &&
        blines.includes('  … and 2 more'));
  check('nothing open → no section', pr.reviewDigest_([rows[4]], '2026-09-28', known).lines.length === 0 &&
        pr.sfPendingLines_([]).length === 0);
}

console.log('\n  the handler and the weekly e-mail, run with Google services stubbed');
{
  const vm = require('vm');
  const src = ['Config.gs', 'Normalize.gs', 'Roster.gs', 'FormHandlers.gs']
      .map(f => fs.readFileSync(path.join(loadGs.GS_DIR, f), 'utf8')).join('\n');
  // A spreadsheet of plain arrays: tabs[name] = rows (row 1 = header).
  const world = (opts) => {
    const tabs = {}, mails = [], audits = [];
    const sheet = name => ({
      getName: () => name,
      getLastRow: () => tabs[name].length,
      getLastColumn: () => Math.max(0, ...tabs[name].map(r => r.length)),
      getRange: (r, c, nr, nc) => ({
        getValues: () => {
          if (opts.down === name) throw new Error('sheet unavailable');
          return tabs[name].slice(r - 1, r - 1 + nr).map(row => Array.from({ length: nc }, (_, j) => row[c - 1 + j] ?? ''));
        },
        setValues: vals => {
          if (opts.down === name) throw new Error('sheet unavailable');
          vals.forEach((v, i) => { tabs[name][r - 1 + i] = v.slice(); });
        },
        setFontWeight: () => ({}),
      }),
      setFrozenRows: () => {},
    });
    const ctx = vm.createContext({
      console,
      SpreadsheetApp: { getActive: () => ({ getSheetByName: n => (tabs[n] ? sheet(n) : null),
                                             insertSheet: n => { tabs[n] = []; return sheet(n); },
                                             getSpreadsheetTimeZone: () => 'America/New_York' }) },
      PropertiesService: { getScriptProperties: () => ({ getProperty: k => (opts.props || {})[k] || null }) },
      MailApp: { sendEmail: o => { if (opts.mailFails > 0) { opts.mailFails--; throw new Error('quota'); } mails.push(o); } },
      Utilities: { formatDate: d => d.toISOString().slice(0, 10) },
    });
    vm.runInContext(src, ctx);
    ctx.today_ = () => '2026-09-28';
    ctx.now_ = () => '2026-09-28 09:00:00';
    ctx.audit_ = (action, detail) => audits.push(action + ': ' + detail);
    ctx.formLogAdd_ = () => {};
    tabs.ReviewQueue = [vm.runInContext('REVIEW_COLS', ctx).slice()];
    return { ctx, tabs, mails, audits, sheet };
  };
  const STAFF = { STAFF_NOTIFY_EMAIL: 'staff@example.org' };
  const KEY = 'FEEDBACK|w:2026-09-20 08:15:38.000|GLOW – Club Roster Form|';
  const change = () => report('GLOW – Club Roster Form', 'Please remove ' + CANARY,
      { [PQ.FB_CLUB]: 'Bright Stars', [PQ.FB_EMAIL]: 'mentor@example.org' });
  const clean = s => !/Fennwhistle|Bright Stars|mentor@example\.org/.test(s);

  let w = world({ props: STAFF });
  const res = w.ctx.runResponse_('FEEDBACK', w.sheet('Feedback'), 7, change(), KEY);
  const item = w.tabs.ReviewQueue[1] || [];
  check('a roster-change report: one ReviewQueue row, tagged, dated from its key, no report text',
        w.tabs.ReviewQueue.length === 2 && item[1] === 'Roster change sent as a problem report' &&
        item[4].endsWith(' [#Feedback!7]') && item[4].includes('(sent 2026-09-20; Club Roster Form chosen)') &&
        !/Fennwhistle|example\.org/.test(item[4]));
  check('…and one staff e-mail with the note; FormLog result says queued',
        w.mails.length === 1 && w.mails[0].body.includes('Staff note: looks like a roster change; on the ReviewQueue as Feedback!7.') &&
        w.mails[0].replyTo === 'mentor@example.org' && res === 'emailed staff; roster change queued', res);
  check('Audit names the source only (no girl, no typed club, no reply address)',
        w.audits.length === 1 && w.audits[0].endsWith('; ReviewQueue [#Feedback!7]') && clean(w.audits.join('\n')));
  w = world({ props: STAFF });
  const textStamp = w.ctx.runResponse_('FEEDBACK', w.sheet('Feedback'), 7, change(), 'FEEDBACK|9/20/2026 8:15:38|GLOW – Club Roster Form|');
  check('a problem report whose Timestamp is not a date still goes to staff (only the Club Roster Form needs a sent day)',
        textStamp === 'emailed staff; roster change queued' && w.mails.length === 1, textStamp);

  w = world({ props: STAFF, mailFails: 1 });
  let threw = false;
  try { w.ctx.handleFeedback_(change(), 'Feedback!7', KEY); } catch (e) { threw = /quota/.test(e.message); }
  w.ctx.handleFeedback_(change(), 'Feedback!7', KEY);
  check('a failed send, then the retry: one e-mail and still one ReviewQueue row (queued before sending)',
        threw && w.mails.length === 1 && w.tabs.ReviewQueue.length === 2);

  w = world({ props: STAFF, down: 'ReviewQueue' });
  const down = w.ctx.handleFeedback_(change(), 'Feedback!7', KEY);
  check('the ReviewQueue unavailable: still e-mailed, "add it by hand", result NOT queued (never ERROR)',
        w.mails.length === 1 && w.mails[0].body.includes('could NOT be added to the ReviewQueue') &&
        down === 'emailed staff; roster change NOT queued (see Audit)' &&
        w.audits.some(x => x.startsWith('tryReview_: could not add 1 item(s) (Roster change sent as a problem report) for Feedback!7')) &&
        clean(w.audits.join('\n')));

  w = world({ props: {} });
  threw = false;
  try { w.ctx.handleFeedback_(change(), 'Feedback!7', KEY); } catch (e) { threw = /STAFF_NOTIFY_EMAIL/.test(e.message); }
  check('STAFF_NOTIFY_EMAIL unset: throws, nothing queued or sent', threw && w.tabs.ReviewQueue.length === 1 && !w.mails.length);

  // the reply box's e-mail validation may be missing (a wording run that stopped part-way):
  // a typed non-address never becomes the Reply-To, so it can never fail the staff e-mail
  w = world({ props: STAFF });
  const notAddress = report('Africa Attendance Form', 'The page left me on a blank screen.', { [PQ.FB_EMAIL]: 'call me on whatsapp' });
  const na = w.ctx.handleFeedback_(notAddress, 'Feedback!9', KEY);
  check('a reply "address" that is not one: e-mailed without Reply-To, the body says why',
        na === 'emailed staff' && w.mails.length === 1 && !('replyTo' in w.mails[0]) &&
        w.mails[0].body.includes('(not an e-mail address, so not set as Reply-To)'), JSON.stringify(Object.keys(w.mails[0] || {})));
  w = world({ props: STAFF });
  w.ctx.handleFeedback_(report('Africa Attendance Form', 'Blank screen.', { [PQ.FB_EMAIL]: ' mentor@example.org ' }), 'Feedback!9', KEY);
  check('…a real address (spaces trimmed): the Reply-To, no note', w.mails[0].replyTo === 'mentor@example.org' &&
        !w.mails[0].body.includes('not set as Reply-To'));

  w = world({ props: STAFF });
  const plain = w.ctx.handleFeedback_(report('Africa Attendance Form', 'The page left me on a blank screen.'), 'Feedback!8', KEY);
  check('any other report: e-mail only, as before', plain === 'emailed staff' && w.tabs.ReviewQueue.length === 1 &&
        !w.mails[0].body.includes('Staff note'));

  // the weekly e-mail
  const weekly = (reviewRows, sfRows, props) => {
    const x = world({ props });
    x.tabs.ReviewQueue = x.tabs.ReviewQueue.concat(reviewRows.map(r => r(x.ctx)));
    x.tabs.ClubRegistry = [['club_code', 'partner', 'club', 'created'], ['BRIGHTST', 'Fixture Partner Alpha', 'Bright Stars', '2026-08-26']];
    x.tabs['SF Pending'] = [vm.runInContext('SF_PENDING_COLS', x.ctx).slice()].concat(sfRows);
    x.ctx.sendSfPendingDigest();
    return x;
  };
  const dateCell = ctx => vm.runInContext('new Date("2026-09-26T12:00:00Z")', ctx);   // a Date as getValues returns it
  const openRows = [ctx => [dateCell(ctx), 'Removal did not match anyone', 'Fixture Partner Alpha', 'Bright Stars', '"' + CANARY + '" … [#hope fennwhistle]', ''],
                    () => ['2026-09-10', 'Roster change sent as a problem report', '', '', 'Feedback!7 (sent 2026-09-10; report text) [#Feedback!7]', '']];
  const sfRow = ['2026-09-20', 'Fixture Partner Alpha', 'Nova Club', 'Africa', 12, 'Mentor Testperson', 'mentor@example.org', 'Kenya', 'pending', ''];
  w = weekly(openRows, [], STAFF);
  check('ReviewQueue only: one e-mail, "GLOW weekly: 2 open ReviewQueue item(s)"; a date cell and a text date both dated',
        w.mails.length === 1 && w.mails[0].subject === 'GLOW weekly: 2 open ReviewQueue item(s)' &&
        w.mails[0].body.includes('raised 2026-09-26') && w.mails[0].body.includes('raised 2026-09-10') &&
        w.mails[0].body.includes('1 new this week') &&
        !/fennwhistle/i.test(w.mails[0].body), w.mails[0] && w.mails[0].subject);
  check('Audit: counts only', w.audits.join() ===
        'sendSfPendingDigest: emailed staff@example.org: 2 open ReviewQueue item(s) (1 new this week), 0 club(s) pending in Salesforce');
  w = weekly(openRows, [sfRow], STAFF);
  check('both: the ReviewQueue section first, then Salesforce as before',
        w.mails[0].subject === 'GLOW weekly: 2 open ReviewQueue item(s) · 1 club(s) pending in Salesforce' &&
        w.mails[0].body.indexOf('open ReviewQueue item(s)') < w.mails[0].body.indexOf('waiting to be created in Salesforce') &&
        w.mails[0].body.includes('added 2026-09-20'));
  w = weekly([() => ['2026-09-10', 'Same name listed twice', '', '', 'x', 'resolved 2026-09-20 by Ryan: one girl']], [], STAFF);
  check('nothing open and nothing pending: no e-mail, no Audit', !w.mails.length && !w.audits.length);
  w = weekly(openRows, [sfRow], {});
  check('STAFF_NOTIFY_EMAIL unset: no e-mail, an Audit row with both counts',
        !w.mails.length && w.audits.join() === 'sendSfPendingDigest: 2 open ReviewQueue item(s) (1 new this week), 1 club(s) pending in Salesforce but STAFF_NOTIFY_EMAIL is not set');
}

console.log('\n  the replay guard in the Club Roster Form handlers (Google services stubbed)');
{
  const vm = require('vm');
  const src = ['Config.gs', 'Normalize.gs', 'Ids.gs', 'Regions.gs', 'RosterOps.gs', 'Roster.gs', 'FormHandlers.gs']
      .map(f => fs.readFileSync(path.join(loadGs.GS_DIR, f), 'utf8')).join('\n');
  // A spreadsheet of plain arrays (tabs[name] = rows, row 1 = header) with what the handlers call.
  const world = (zone) => {
    const tabs = {}, mails = [], audits = [], formLog = [], syncs = [];
    const cell = (name, r, c) => { const t = tabs[name]; while (t.length < r) t.push([]); return t[r - 1]; };
    const sheet = name => ({
      getName: () => name,
      getLastRow: () => tabs[name].length,
      getLastColumn: () => Math.max(0, ...tabs[name].map(r => r.length)),
      getRange: (r, c, nr, nc) => ({
        getValues: () => tabs[name].slice(r - 1, r - 1 + (nr || 1))
            .map(row => Array.from({ length: nc || 1 }, (_, j) => row[c - 1 + j] ?? '')),
        setValues: vals => vals.forEach((v, i) => { const row = cell(name, r + i); v.forEach((x, j) => { row[c - 1 + j] = x; }); }),
        setValue: v => { cell(name, r)[c - 1] = v; },
        setFontWeight: () => ({}),
      }),
      getRangeList: a1s => ({ setValue: v => a1s.forEach(a1 => {
        const m = /^([A-Z])(\d+)$/.exec(a1);
        cell(name, +m[2])[m[1].charCodeAt(0) - 65] = v;
      }) }),
      appendRow: row => { tabs[name].push(row.slice()); },
      setFrozenRows: () => {},
    });
    const ctx = vm.createContext({
      console,
      SpreadsheetApp: { getActive: () => ({ getSheetByName: n => (tabs[n] ? sheet(n) : null),
                                             insertSheet: n => { tabs[n] = []; return sheet(n); },
                                             getSpreadsheetTimeZone: () => zone }) },
      PropertiesService: { getScriptProperties: () => ({ getProperty: () => null }) },
      MailApp: { sendEmail: o => mails.push(o) },
      Utilities: { formatDate: (d, z, fmt) => {
        if (fmt !== 'yyyy-MM-dd') throw new Error('stub: format ' + fmt);
        return new Intl.DateTimeFormat('en-CA', { timeZone: z, year: 'numeric', month: '2-digit', day: '2-digit' }).format(d);
      } },
    });
    vm.runInContext(src, ctx);
    ctx.today_ = () => '2026-09-28';
    ctx.now_ = () => '2026-09-28 09:00:00';
    ctx.audit_ = (action, detail) => audits.push(action + ': ' + detail);
    ctx.formLogAdd_ = (which, row, key, result) => formLog.push(result);
    ctx.trySyncChoices_ = () => {};
    ctx.tryNotifySync_ = why => syncs.push(why);
    const at = iso => vm.runInContext('new Date("' + iso + '")', ctx);   // a Date cell as getValues returns it
    const C = n => vm.runInContext(n, ctx);
    tabs.ReviewQueue = [C('REVIEW_COLS').slice()];
    tabs.ClubRegistry = [C('CLUB_COLS').slice(), ['SUNRISEC', ORG, 'Sunrise Club', '2026-08-26']];
    tabs.Partners = [C('PARTNER_COLS').slice(), [ORG, 'Africa', '']];
    const g = (id, name, status, removed) => [id, ORG, 'Sunrise Club', 'Africa', name, name.split(' ').pop(), status, '2026-08-26', removed, 'T!2'];
    tabs.Roster = [C('ROSTER_COLS').slice(),
      g('SUNRISEC-ZIBBLEWICK-001', 'Grace Zibblewick', 'inactive', at('2026-09-12T04:00:00Z')),   // a Date cell: 09-12 in New York
      g('SUNRISEC-BLORPTEST-001', 'Joy Blorptest', 'inactive', at('2026-09-11T02:00:00Z')),       // 09-10 in New York, 09-11 in UTC
      g('SUNRISEC-ZIBBLEWICK-002', 'Mary Zibblewick', 'active', ''),
      g('SUNRISEC-ZORBLEWICK-001', 'Lucía Zörblewick', 'inactive', '2026-08-01'),                 // text
    ];
    return { ctx, tabs, mails, audits, formLog, syncs, sheet, at };
  };
  const RQ = 'Roster Form Responses';
  const sentOn = day => 'ROSTER|w:' + day + ' 08:00:00.000|' + ORG + '|Sunrise Club';
  const change = () => ({ [FQ.ACTION]: FQ.ACTION_MOD, [FQ.PARTNER_MOD]: ORG, [FQ.CLUB_PREFIX + ORG + ')']: 'Sunrise Club',
                          [FQ.ADD]: 'GRACE ZIBBLEWICK\nJoy Blorptest\nLucía Zörblewick', [FQ.REMOVE]: 'Mary Zibblewick',
                          [FQ.MENTOR_EMAIL_MOD]: 'mentor@example.org' });
  const isDate = v => Object.prototype.toString.call(v) === '[object Date]';   // a Date from the vm's realm
  const status = (w, r) => w.tabs.Roster[r - 1][6] + '|' + (isDate(w.tabs.Roster[r - 1][8]) ? 'Date' : w.tabs.Roster[r - 1][8]);
  const noGirls = s => !/zibblewick|blorptest|z[oö]rblewick/i.test(s);

  let w = world('America/New_York');
  const rows = w.ctx.loadRoster_().rows;
  check('loadRoster_: a Date cell becomes its day in the SPREADSHEET\'s zone; text stays text',
        rows[0].removed_date === '2026-09-12' && rows[1].removed_date === '2026-09-10' &&
        rows[3].removed_date === '2026-08-01' && rows[2].removed_date === '' && rows[0].added_date === '2026-08-26',
        rows.map(r => r.removed_date).join(','));
  check('…the same instant in a UTC spreadsheet is the next day (the zone is the sheet\'s)',
        world('UTC').ctx.loadRoster_().rows[1].removed_date === '2026-09-11');

  // A roster change sent 09-10 that only runs on 09-28 (a retry, or confirmed in the menu).
  let result = w.ctx.runResponse_('ROSTER', w.sheet(RQ), 5, change(), sentOn('2026-09-10'));
  check('sent 09-10, run 09-28: removed 09-12 stays removed; removed 09-10 (the sheet\'s zone) and 08-01 come back; ' +
        'its REMOVE is dated 09-10, the day it was sent',
        status(w, 2) === 'inactive|Date' && status(w, 3) === 'active|' && status(w, 5) === 'active|' &&
        status(w, 4) === 'inactive|2026-09-10', [2, 3, 4, 5].map(r => status(w, r)).join(' '));
  const item = w.tabs.ReviewQueue[1] || [];
  check('one ReviewQueue row: tagged with the response, Roster row numbers, no name',
        w.tabs.ReviewQueue.length === 2 && item[1] === 'Removed girls not put back by an older response' &&
        item[2] === ORG && item[3] === 'Sunrise Club' &&
        String(item[4]).startsWith(RQ + '!5 (sent 2026-09-10): 1 girl(s)') && String(item[4]).includes('Roster rows 2.') &&
        String(item[4]).endsWith(' [#' + RQ + '!5]') && noGirls(String(item[4])), String(item[4]));
  check('FormLog result and Audit: counts, no names',
        w.formLog[0] === 'Sunrise Club (' + ORG + '): 0 added, 2 reactivated, 1 removed, 1 kept removed' &&
        w.audits.length === 1 && w.audits[0] === 'rosterChangeForm: ' + result && noGirls(w.audits.join('\n')), w.formLog[0]);
  const body = (w.mails[0] || { body: '' }).body;
  const kept = body.split('\n').indexOf('Not added back — they are marked removed on the roster. ' +
                                        'If one of them has rejoined the club, send the form again to add her:');
  check('the mentor e-mail lists her as the mentor typed her, under "Not added back"',
        w.mails.length === 1 && kept !== -1 && body.split('\n')[kept + 1] === '  - GRACE ZIBBLEWICK' &&
        !body.includes('Grace Zibblewick'),
        w.mails.length + ' mail(s), heading at line ' + kept + ', ' + body.split('\n').length + ' lines');

  result = w.ctx.runResponse_('ROSTER', w.sheet(RQ), 5, change(), sentOn('2026-09-10'));
  check('run again: still one ReviewQueue row, she is still removed',
        w.tabs.ReviewQueue.length === 2 && status(w, 2) === 'inactive|Date' && /1 kept removed/.test(result), result);

  w = world('America/New_York');
  result = w.ctx.runResponse_('ROSTER', w.sheet(RQ), 6, change(), sentOn('2026-09-28'));
  check('the same change sent today (the trigger): everyone listed comes back, as before; no item, no note',
        status(w, 2) === 'active|' && status(w, 3) === 'active|' && status(w, 5) === 'active|' &&
        w.tabs.ReviewQueue.length === 1 && !/kept removed/.test(result) && !w.mails[0].body.includes('Not added back'), result);

  w = world('America/New_York');
  result = w.ctx.runResponse_('ROSTER', w.sheet(RQ), 7, change(), 'ROSTER|9/10/2026 8:00:00|' + ORG + '|Sunrise Club');
  // Review finding RG-1: run unguarded it put back the girl removed 09-12, while the menu's
  // warning for old rows (where such a row lands) promises girls removed since stay removed.
  const refused = w.tabs.ReviewQueue[1] || [];
  check('a Timestamp that is not a date: no sent day, so refused — Roster untouched, FormLog ERROR, queued, no e-mail',
        /^ERROR: its Timestamp cell is not a date/.test(result) && w.formLog[0] === result &&
        status(w, 2) === 'inactive|Date' && status(w, 3) === 'inactive|Date' && status(w, 4) === 'active|' &&
        status(w, 5) === 'inactive|2026-08-01' && w.tabs.ReviewQueue.length === 2 &&
        refused[1] === 'Form response could not be processed' &&
        String(refused[4]).startsWith(RQ + '!7: its Timestamp cell is not a date') &&
        !w.mails.length && !w.audits.length, result);
  // a retry fails the same way, so the item must not send staff to the menu (integration review F2)
  check('…its item says to enter it fresh and resolve FormLog by hand, not to retry from the menu',
        String(refused[4]).includes('enter the change fresh') && String(refused[4]).includes('resolved by hand') &&
        !String(refused[4]).includes('then run "Process any missed'), String(refused[4]).slice(-110));
  w = world('America/New_York');
  result = w.ctx.runResponse_('ROSTER', w.sheet(RQ), 8, { [FQ.ACTION]: FQ.ACTION_NEW, [FQ.PARTNER_NEW]: ORG,
      [FQ.CLUB]: 'Sunrise Club', [FQ.ROSTER]: 'Grace Zibblewick' }, 'ROSTER|8/31/2026 8:00:00|' + ORG + '|Sunrise Club');
  check('…the new-club branch is refused the same way', /^ERROR: its Timestamp cell is not a date/.test(result) &&
        status(w, 2) === 'inactive|Date' && w.tabs.ReviewQueue.length === 2, result);

  // The trigger was down (a scope-adding push not yet authorized): responses sent earlier all run
  // on 09-28 from the menu, in sheet order. Review finding 2026-09-28: if a removal were dated the
  // day it RAN, a REMOVE and a later-sent ADD for the same girl would keep her removed.
  const one = (field, name) => ({ [FQ.ACTION]: FQ.ACTION_MOD, [FQ.PARTNER_MOD]: ORG,
                                  [FQ.CLUB_PREFIX + ORG + ')']: 'Sunrise Club', [field]: name });
  const at = (day, hh) => 'ROSTER|w:' + day + ' ' + hh + ':00:00.000|' + ORG + '|Sunrise Club';
  const lateRun = steps => {
    const x = world('America/New_York');
    const seen = steps.map(([field, day, hh], i) => {
      x.ctx.runResponse_('ROSTER', x.sheet(RQ), 10 + i, one(field, 'Mary Zibblewick'), at(day, hh));
      return status(x, 4);
    });
    return { seen, queue: x.tabs.ReviewQueue.length - 1 };
  };
  let run = lateRun([[FQ.REMOVE, '2026-09-27', '10'], [FQ.ADD, '2026-09-27', '11']]);
  check('REMOVE at 10:00 then ADD at 11:00 on 09-27, both run 09-28: dated 09-27, so the ADD wins — she is back, no item',
        run.seen.join(' → ') === 'inactive|2026-09-27 → active|' && !run.queue, run.seen.join(' → '));
  run = lateRun([[FQ.REMOVE, '2026-09-26', '10'], [FQ.ADD, '2026-09-27', '10']]);
  check('REMOVE sent 09-26, ADD sent 09-27, both run 09-28: she is back',
        run.seen.join(' → ') === 'inactive|2026-09-26 → active|' && !run.queue, run.seen.join(' → '));
  run = lateRun([[FQ.REMOVE, '2026-09-27', '10'], [FQ.ADD, '2026-09-26', '10']]);
  check('…but an ADD sent 09-26 that only runs after a REMOVE sent 09-27 (a retry): the later removal wins, one item',
        run.seen.join(' → ') === 'inactive|2026-09-27 → inactive|2026-09-27' && run.queue === 1, run.seen.join(' → '));

  // The 2026-09-13 case: "Enroll a NEW club" re-sent for a club on file, replayed later.
  w = world('America/New_York');
  const enroll = { [FQ.ACTION]: FQ.ACTION_NEW, [FQ.PARTNER_NEW]: ORG, [FQ.CLUB]: 'Sunrise Club', [FQ.REGION]: 'Africa',
                   [FQ.ROSTER]: 'Grace Zibblewick\nJoy Blorptest\nMary Zibblewick\nLucía Zörblewick',
                   [FQ.MENTOR_EMAIL]: 'mentor@example.org' };
  result = w.ctx.runResponse_('ROSTER', w.sheet(RQ), 2, enroll, sentOn('2026-08-31'));
  check('new-club branch, sent 08-31: removed 09-12 and 09-10 stay removed, 08-01 comes back; one item; no mentor e-mail',
        status(w, 2) === 'inactive|Date' && status(w, 3) === 'inactive|Date' && status(w, 5) === 'active|' &&
        w.tabs.ReviewQueue.length === 2 && String(w.tabs.ReviewQueue[1][4]).includes('2 girl(s)') &&
        String(w.tabs.ReviewQueue[1][4]).includes('Roster rows 2, 3.') && !w.mails.length &&
        result === 'existing club Sunrise Club (' + ORG + '): 0 girls added, 1 reactivated, 2 kept removed, 1 for review',
        result);
}

console.log('\nThe duplicate-club guard (RosterOps.gs newClubHoldReasons_, BACKLOG 11b)');
const dg = loadGs(['DUP_GUARD', 'STATUS', 'newClubHoldReasons_', 'clubNamesClose_', 'partnersClose_', 'matchWords_',
                   'numberTag_', 'similarity_']);
{
  console.log('\n  similarity_ = Python difflib.SequenceMatcher(None, a, b).ratio()');
  // values from Python 3 difflib, pinned
  const pinned = [['bravehaert', 'braveheart', 0.9], ['shining stars', 'shinning stars', 0.9629629629629629],
                  ['vision', 'rise', 0.4], ['abcd', 'bcde', 0.75], ['chacarita', 'traslasierra', 0.38095238095238093],
                  ['empowerment kenya', 'empowerment uganda', 0.8], ['aaab', 'abaa', 0.5], ['xyz', '', 0], ['', '', 1]];
  const off = pinned.filter(([a, b, want]) => Math.abs(dg.similarity_(a, b) - want) > 1e-12)
      .map(([a, b]) => a + '/' + b + '=' + dg.similarity_(a, b));
  check('9 pairs agree with difflib to 1e-12 (ties broken earliest in a, then in b)', !off.length, off.join(' | '));

  console.log('\n  words, numbers, close names');
  check('matchWords_: folded, dots dropped, split on punctuation, letters from digits',
        dg.matchWords_('Hillside G.L.O.W club , Northfield').join(' ') === 'hillside glow club northfield' &&
        dg.matchWords_('Lubbock GC-2').join(' ') === 'lubbock gc 2' && dg.matchWords_('Club2B').join(' ') === 'club 2 b' &&
        dg.matchWords_('Fundación  Demo').join(' ') === 'fundacion demo' &&
        dg.matchWords_("Bishop's B R/C").join(' ') === 'bishops b r c' && dg.matchWords_('Bishop’s').join(' ') === 'bishops');
  check('numberTag_: digits and roman numerals, sorted; none → ""',
        dg.numberTag_(['club', '02']) === '2' && dg.numberTag_(['club', 'ii']) === '2' && dg.numberTag_(['club']) === '' &&
        dg.numberTag_(['constructor']) === '');
  const close = [['BRIGHT GIRLS', 'BRIGHT GIRLS (TESTVILLE SEC SCH)'], ['BRAVEHEART GIRLS', 'BRAVEHAERT GIRLS'],
                 ['Hillside GLOW Club Northfield', 'Hillside G.L.O.W club , Northfield'], ['Riverside', 'Club Glow Riverside'],
                 ['Shining Stars', 'Shinning Stars'], ['Harbor Club', 'Harbor Club 2'], ['Harbor Club 2', 'Harbor Club II'],
                 ['Las Lomitas', 'Las Lomitas primaria'], ['BRAVEHEART GIRLS', 'BRAVEHAERT GIRLS (TESTVILLE SEC SCH)'],
                 ['Orbit', 'Orbit (A)']];
  const apart = [['Harbor Club 1', 'Harbor Club 2'], ['Vision GLOW Club', 'Rise GLOW Club'],
                 ['Club Glow Chacarita', 'Club Glow Traslasierra'], ['GLOW Club', 'Girls Club'], ['Sunrise Club', 'Starlight Club'],
                 ['Harbor Club (1)', 'Harbor Club (2)'], ['SKY GIRLS (TESTVILLE SEC SCH)', 'ROYAL GIRLS (TESTVILLE SEC SCH)'],
                 ['(TESTVILLE SEC SCH)', '(TESTVILLE PRI SCH)'], ['(TESTVILLE SEC SCH)', '(NORTHFIELD SEC SCH)'],
                 ['Las Lomitas primaria', 'Las Lomitas secundaria'],
                 ['SKY GIRLS (TESTVILLE PRI SCH)', 'SKY GIRLS (TESTVILLE SEC SCH)'], ['Orbit (A)', 'Orbit (B)'],
                 ['Harbor 2 - Club A', 'Harbor 2 - Club B'], ["TESTVILLE'S A R/C JHS GLOW CLUB", "TESTVILLE'S B R/C JHS GLOW CLUB"],
                 ['FHX Global Glow', 'TMX Global Glow']];
  const wrongClose = close.filter(([a, b]) => !dg.clubNamesClose_(a, b) || !dg.clubNamesClose_(b, a));
  const wrongApart = apart.filter(([a, b]) => dg.clubNamesClose_(a, b) || dg.clubNamesClose_(b, a));
  check('clubNamesClose_: suffix, typo, punctuation, containment, one number added, typo + school — close either way round',
        !wrongClose.length, wrongClose.map(p => p.join(' / ')).join(' | '));
  check('clubNamesClose_: different numbers, section letters or school levels, different distinctive words, the same school only, filler only — apart',
        !wrongApart.length, wrongApart.map(p => p.join(' / ')).join(' | '));
  const pClose = [['Fundacion Demo', 'Fundación Demo'], ['Demo', 'Fundación Demo'], ['TARN', 'Test Aid Relief Network'],
                  ['Test Aid Relief Network', 'TARN'], ['Test Aid Releif Network', 'Test Aid Relief Network'],
                  ['fixture-partner alpha', 'Fixture Partner Alpha']];
  const pApart = [['Brand New Org', 'Fixture Partner Alpha'], ['TAR', 'Test Aid Relief Network'], ['Moonbeam Collective', 'Fundación Demo'],
                  ['Foundation', 'Fundación Demo'], ['TA', 'Test Aid']];
  check('partnersClose_: accents, containment, acronym both ways, typo, punctuation — close',
        pClose.every(([t, k]) => dg.partnersClose_(t, k)), pClose.filter(([t, k]) => !dg.partnersClose_(t, k)).join(' | '));
  check('partnersClose_: unrelated, a partial acronym, filler only — apart',
        pApart.every(([t, k]) => !dg.partnersClose_(t, k)), pApart.filter(([t, k]) => dg.partnersClose_(t, k)).join(' | '));

  console.log('\n  when a new-club response is held');
  const first = ['Ada', 'Bea', 'Cora', 'Dina', 'Eva', 'Fay', 'Gia', 'Hana', 'Ivy', 'Jo'];
  const girls = (surname, n, from) => first.slice(from || 0, (from || 0) + n).map(f => f + ' ' + surname);
  const R = (p, c, names, status) => names.map(n => ({ partner: p, club: c, full_name: n, status: status || 'active' }));
  const A = 'Fixture Partner Alpha';
  const sunrise = girls('Quillfeather', 4);
  const rows = [].concat(
      R(A, 'BRIGHT GIRLS', girls('Marrowgate', 5)), R(A, 'BRAVEHEART GIRLS', girls('Ostrivane', 4)),
      R(A, 'Hillside GLOW Club Northfield', girls('Thornquibble', 3)), R(A, 'Harbor Club 1', girls('Pellucidor', 3)),
      R(A, 'Vision GLOW Club', girls('Blorptest', 3)), R(A, 'Sunrise Club', sunrise),
      R(A, 'Sunrise Club', ['Jo Quillfeather'], 'inactive'),
      R('Fundación Demo', 'Club Glow Riverside', girls('Zibblewick', 3)),
      R('Test Aid Relief Network', 'Lotus Club', girls('Qwertyson', 3)),
      R('Other Partner Beta', 'Moonrise Club', girls('Fennwhistle', 3)),
      R(A, 'Old Club', ['Lucía Zörblewick', 'Eva Zörblewick', 'Fay Zörblewick'], 'inactive'),
      [{ partner: '', club: 'Stray', full_name: 'Ada Nowhere', status: 'active' }]);
  const partners = [A, 'Fundación Demo', 'Test Aid Relief Network', 'YWTU', ''];
  const fresh = girls('Newperson', 4);
  const hold = (partner, club, names, typed) =>
      dg.newClubHoldReasons_({ partner, club, names, typedPartner: !!typed }, rows, partners);
  const kinds = r => r.map(x => x.kind).join(',');
  const texts = r => r.map(x => x.text).join(' / ');
  let r;
  r = hold(A, 'BRIGHT GIRLS (TESTVILLE SEC SCH)', fresh);
  check('club name with a school added: held (club), the club on file named',
        kinds(r) === 'club' && texts(r) === 'the club name is close to BRIGHT GIRLS (Fixture Partner Alpha), already enrolled', texts(r));
  r = hold(A, 'BRAVEHAERT GIRLS', fresh);
  check('a typo of a club on file: held (club)', kinds(r) === 'club' && texts(r).includes('BRAVEHEART GIRLS'), texts(r));
  r = hold(A, 'Hillside G.L.O.W club , Northfield', fresh);
  check('stray punctuation and spacing: held (club)', kinds(r) === 'club', texts(r));
  check('a numbered sibling, a different name, the same name under another partner: imported',
        !hold(A, 'Harbor Club 2', fresh).length && !hold(A, 'Rise GLOW Club', fresh).length &&
        !hold('Other Partner Beta', 'BRIGHT GIRLS', fresh).length);
  r = hold(A, 'Starlight Club', sunrise.slice(0, 3).concat(['Hana Newperson']));
  check('3 of 4 names active in one club: held (names), with the counts and that club',
        kinds(r) === 'names' && texts(r) === '3 of the 4 names sent are active in Sunrise Club (Fixture Partner Alpha)', texts(r));
  r = hold('Moonbeam Collective', 'Evening Club', girls('Fennwhistle', 2).concat(['Hana Newperson']), true);
  check('names active in another partner\'s club: held too (a retyped organization)',
        kinds(r) === 'names' && texts(r).includes('2 of the 3 names sent are active in Moonrise Club (Other Partner Beta)'), texts(r));
  check('under MIN_SHARED or under half: imported',
        !hold(A, 'Starlight Club', [sunrise[0], 'Hana Newperson']).length &&
        !hold(A, 'Starlight Club', sunrise.slice(0, 2).concat(girls('Newperson', 3))).length && dg.DUP_GUARD.MIN_SHARED === 2);
  check('only ACTIVE girls count for names (a club\'s removed girls may enrol elsewhere)',
        !hold(A, 'Starlight Club', ['Lucia Zorblewick', 'Eva Zörblewick', 'Fay Zörblewick']).length);
  check('names compare with accents and case folded',
        kinds(hold('Moonbeam Collective', 'Evening Club', ['cora fennwhistle', 'BEA FENNWHISTLE'], true)) === 'names');
  r = hold('Fundacion Demo', 'Riverside', fresh, true);
  check('typed organization = a partner on file without its accent: held (club + partner); its clubs are compared too',
        kinds(r) === 'club,partner' && texts(r).includes('Club Glow Riverside (Fundación Demo)') &&
        texts(r).includes('the organization was typed as "Fundacion Demo", close to Fundación Demo on file'), texts(r));
  check('typed acronym of a partner, or the long form of an acronym on file: held (partner)',
        kinds(hold('TARN', 'Evening Club', fresh, true)) === 'partner' &&
        kinds(hold('Young Women Test Union', 'Evening Club', fresh, true)) === 'partner');
  check('typed = a partner on file (any case): it IS that partner, so no partner reason',
        !hold('fixture partner alpha', 'Evening Club', fresh, true).length);
  check('a new organization, a new club, new names: imported', !hold('Moonbeam Collective', 'Evening Club', fresh, true).length);
  check('the same organization chosen from the dropdown is never a partner reason',
        !hold('Fundacion Demo', 'Evening Club', fresh, false).length);

  console.log('\n  an exact re-enrollment (the club is on file)');
  r = hold(A, 'sunrise club', girls('Newperson', 4));
  check('none of the names on file, none of its girls in the list: held (reenroll)',
        kinds(r) === 'reenroll' && texts(r) === 'this club is already enrolled, but only 0 of the 4 names sent are on its ' +
        'roster, and 0 of its 4 active girls are in the list', texts(r));
  check('the same list with a new girl, a short list, half its girls plus many new: imported (as today)',
        !hold(A, 'Sunrise Club', sunrise.concat(['Hana Newperson'])).length && !hold(A, 'Sunrise Club', sunrise.slice(0, 1)).length &&
        !hold(A, 'Sunrise Club', sunrise.slice(0, 2).concat(girls('Newperson', 6))).length);
  check('a removed girl listed again counts as on file (she is reactivated)',
        !hold(A, 'Sunrise Club', ['Jo Quillfeather']).length);
  r = hold(A, 'Sunrise Club', [sunrise[0]].concat(girls('Newperson', 6)));
  check('one old name among six new: held', kinds(r) === 'reenroll' && texts(r).includes('1 of the 7 names') && texts(r).includes('1 of its 4'), texts(r));
  check('an exact re-enrollment gets no club or names reason (siblings are expected)',
        !hold(A, 'Harbor Club 1', girls('Pellucidor', 3)).length);
  const everything = [hold(A, 'BRIGHT GIRLS (TESTVILLE SEC SCH)', fresh), hold(A, 'Starlight Club', sunrise.slice(0, 3)),
                      hold('Moonbeam Collective', 'Evening Club', girls('Fennwhistle', 3), true), hold(A, 'Sunrise Club', fresh)];
  check('reasons never carry a girl\'s name', !/Quillfeather|Fennwhistle|Newperson|Ada |Bea /.test(everything.map(texts).join(' ')));
  const many = dg.newClubHoldReasons_({ partner: A, club: 'Star', names: fresh },
      ['Star 1', 'Star 2', 'Star 3', 'Star 4'].map(c => ({ partner: A, club: c, full_name: 'Ivy Starling', status: 'active' })), [A]);
  check('at most MAX_LISTED candidates named, then "and N more"',
        texts(many) === 'the club name is close to Star 1 (Fixture Partner Alpha); Star 2 (Fixture Partner Alpha); ' +
        'Star 3 (Fixture Partner Alpha) and 1 more, already enrolled', texts(many));
}

// ------------------------- Club Roster Form responses (the handlers, stubbed)
console.log('\nClub Roster Form text is sheet-safe (BACKLOG 44)');
const nz = loadGs(['sheetText_', 'parseFormRoster_', 'parseRoster_', 'foldKey_', 'lastName_', 'newRosterRow_']);
{
  const leaks = ['=1+1', '= =1+1', '- =x', '@ =A1', '+ + =1', '=\t=x', ' =x', '​=x', '  -@+=x']
      .filter(v => /^[\s=+\-@]/.test(nz.sheetText_(v)) || nz.sheetText_(v) === '');
  check('sheetText_: no leading = + - @ or space survives, whatever the mix', !leaks.length, leaks.join(' | '));
  check('sheetText_: tidies, and leaves ordinary text (and inner = + - @) alone',
        nz.sheetText_('  Nova   Club ') === 'Nova Club' && nz.sheetText_('Club A+B = @home - 2') === 'Club A+B = @home - 2' &&
        nz.sheetText_(null) === '' && nz.sheetText_('=') === '');
  const r = nz.parseFormRoster_('=Grace Zibblewick\n+Mary Zibblewick\n1. @Joy Blorptest\n- =Grace Zibblewick\nGrace Zibblewick\n=\n@Amina Qwertyson Alpha');
  check('parseFormRoster_: every name sheet-safe, numbering and bullets still stripped',
        r.names.join('|') === 'Grace Zibblewick|Mary Zibblewick|Joy Blorptest|Amina Qwertyson Alpha', r.names.join('|'));
  check('parseFormRoster_: a repeat, and names the strip makes equal, are repeats (sheet-safe too)',
        r.duplicates.join('|') === 'Grace Zibblewick|Grace Zibblewick', r.duplicates.join('|'));
  // Only the start of the name is stripped: inner words stay as typed, so a name like
  // "Ada Ostrivane - Pellucidor" still matches the Roster, where enrolled names are unstripped
  // (review finding: the word-by-word strip made her a second active girl). Her last word is
  // filed on its own as last_name, so newRosterRow_ strips that cell.
  const w = nz.parseFormRoster_('Ivy =1+1\nJo +HYPERLINK("x")\nHana -A1 @Newperson\nUma = =Newperson\nIvy 1+1\n' +
                                '=Kai -\nMary-Jane Zibble-wick\nAda Ostrivane - Pellucidor\n=Ada Ostrivane - Pellucidor');
  check('parseFormRoster_: only the leading run goes; inner words (and a standalone -) stay as typed',
        w.names.join('|') === 'Ivy =1+1|Jo +HYPERLINK("x")|Hana -A1 @Newperson|Uma = =Newperson|Ivy 1+1|Kai|' +
            'Mary-Jane Zibble-wick|Ada Ostrivane - Pellucidor' &&
        w.duplicates.join('|') === 'Ada Ostrivane - Pellucidor' && !w.names.some(n => /^[=+\-@]/.test(n)),
        w.names.join('|'));
  const lastCells = w.names.map(n => nz.newRosterRow_({ sequence: {} }, 'EVENINGC', { partner: 'P', club: 'C' },
                                                       'Africa', n, '2026-09-28'));
  const cellLeaks = lastCells.flat().map(String).filter(c => /^[=+\-@]/.test(c));
  check('newRosterRow_: no cell starts with = + - @ — last_name without its leading run, full_name as given',
        !cellLeaks.length && lastCells.map(r => r[5]).join('|') ===
            '1+1|HYPERLINK("x")|Newperson|Newperson|1+1|Kai|Zibble-wick|Pellucidor' &&
        lastCells.every((r, i) => r[4] === w.names[i]), cellLeaks.join(' | '));
  const plain = 'Grace Zibblewick\n2) Mary Zibblewick\n• Joy Blorptest\nmary zibblewick';
  check('parseFormRoster_ = parseRoster_ on ordinary text (the enrollment import keeps parseRoster_)',
        JSON.stringify(nz.parseFormRoster_(plain)) === JSON.stringify(nz.parseRoster_(plain)));
  check('foldKey_: case and accents folded, nothing else', nz.foldKey_(' Lucía  ZÖRBLEWICK ') === 'lucia zorblewick' &&
        nz.foldKey_('G.L.O.W') === 'g.l.o.w');
}

const HANDLER_FILES = ['Config.gs', 'Normalize.gs', 'Ids.gs', 'Regions.gs', 'RosterOps.gs', 'Roster.gs', 'FormHandlers.gs'];
const handlerSrc = HANDLER_FILES.map(f => fs.readFileSync(path.join(loadGs.GS_DIR, f), 'utf8')).join('\n');
/**
 * A spreadsheet of plain arrays (tabs[name] = rows, row 1 = header) with the
 * real handler code loaded over it. Records e-mails, Audit, FormLog, Jotform
 * sync notifications and dropdown refreshes instead of doing them.
 */
function sheetWorld(tabs, opts) {
  opts = opts || {};
  const vm = require('vm');
  const out = { tabs, mails: [], audits: [], formLog: [], notified: [], synced: 0 };
  const colNum = letters => letters.split('').reduce((n, ch) => n * 26 + ch.charCodeAt(0) - 64, 0);
  const guard = name => { if (opts.down === name) throw new Error('sheet unavailable'); };
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
        getValues: () => { guard(name); return tabs[name].slice(r - 1, r - 1 + nr).map(row => Array.from({ length: nc }, (_, j) => row[c - 1 + j] ?? '')); },
        setValues: vals => { guard(name); vals.forEach((v, i) => v.forEach((x, j) => put(i, j, x))); },
        setValue: v => { guard(name); put(0, 0, v); },
        setFontWeight: () => ({}),
      };
    },
    getRangeList: a1s => ({ setValue: v => a1s.forEach(a => {
      const m = /^([A-Z]+)(\d+)$/.exec(a); sheet(name).getRange(+m[2], colNum(m[1])).setValue(v); }) }),
    appendRow: row => { guard(name); tabs[name].push(row.slice()); },
    setFrozenRows: () => {},
  });
  const ctx = vm.createContext({
    console,
    SpreadsheetApp: { getActive: () => ({ getSheetByName: n => (tabs[n] ? sheet(n) : null),
                                           insertSheet: n => { tabs[n] = []; return sheet(n); },
                                           getSpreadsheetTimeZone: () => 'America/New_York' }) },
    PropertiesService: { getScriptProperties: () => ({ getProperty: () => null }) },
    // a failing send names its recipient, as MailApp's "Invalid email: …" does
    MailApp: { sendEmail: o => { if (opts.mailFails) throw new Error('Invalid email: ' + o.to); out.mails.push(o); } },
  });
  vm.runInContext(handlerSrc, ctx);
  ctx.today_ = () => '2026-09-28';
  ctx.now_ = () => '2026-09-28 09:00:00';
  ctx.audit_ = (action, detail) => out.audits.push(action + ': ' + detail);
  ctx.formLogAdd_ = (which, row, key, result) => out.formLog.push([which, row, key, result]);
  ctx.trySyncChoices_ = () => { out.synced++; };
  ctx.tryNotifySync_ = why => out.notified.push(why);
  out.ctx = ctx;
  out.sheet = sheet;
  out.cells = () => Object.keys(tabs).flatMap(t => tabs[t].slice(1).flat().map(String));
  return out;
}
const HQ = fh.Q;
let girlSeq = 0;
/** Roster rows for one club: [girl_id, partner, club, region, full_name, last_name, status, added, removed, source]. */
const rosterRows = (partnerName, clubName, girls, status) => girls.map(g => [
  'T' + (++girlSeq), partnerName, clubName, 'Africa', g, g.split(' ').pop(), status || 'active', '2026-08-26', '', 'Enrollment Responses!2']);
const baseTabs = rows => ({
  Roster: [['girl_id', 'partner', 'club', 'region', 'full_name', 'last_name', 'status', 'added_date', 'removed_date', 'source']].concat(rows || []),
  ClubRegistry: [['club_code', 'partner', 'club', 'created']],
  Partners: [['partner', 'region', 'notes'], ['Fixture Partner Alpha', 'Africa', ''], ['Fundación Demo', 'Latin America', ''],
             ['Test Aid Relief Network', 'Asia', '']],
  ReviewQueue: [['raised', 'issue', 'partner', 'club', 'detail', 'resolved']],
  'SF Pending': [['added', 'partner', 'club', 'region', 'girls', 'mentor_name', 'mentor_email', 'country', 'status', 'notes']],
});
const newClub = (partnerName, clubName, girls, extra) => Object.assign({
  [HQ.ACTION]: HQ.ACTION_NEW, [HQ.PARTNER_NEW]: partnerName, [HQ.CLUB]: clubName, [HQ.ROSTER]: girls.join('\n'),
  [HQ.SAME_NAME]: 'No', [HQ.MENTOR_NAME]: 'Mentor Testperson', [HQ.MENTOR_EMAIL]: 'mentor@example.org' }, extra || {});
const KEY41 = 'ROSTER|w:2026-09-21 10:15:30.250|x|y';

{
  const w = sheetWorld(baseTabs());
  const answers = newClub(fh.OTHER_PARTNER, '=Nova Club', ['=Grace Zibblewick', '+Mary Zibblewick', '1. @Joy Blorptest', 'Grace Zibblewick'],
      { [HQ.NEW_PARTNER]: '@Brand New Org', [HQ.REGION]: 'Africa', [HQ.MENTOR_NAME]: '=Mentor Testperson',
        [HQ.COUNTRY]: '+Kenya', [HQ.SAME_NAME]: 'Yes', [HQ.SAME_NAME_DETAIL]: '=two girls' });
  const result = w.ctx.handleNewClub_(answers, 'Roster Form Responses!41', KEY41);
  const added = w.tabs.Roster.slice(1);
  check('a new club typed with formula characters: imported, every value sheet-safe',
        /^new club Nova Club \(Brand New Org\): 3 girls added/.test(result) && added.length === 3 &&
        added.every(r => r[1] === 'Brand New Org' && r[2] === 'Nova Club') &&
        added.map(r => r[4]).join('|') === 'Grace Zibblewick|Mary Zibblewick|Joy Blorptest', result);
  check('…ClubRegistry, Partners and SF Pending too', w.tabs.ClubRegistry[1][2] === 'Nova Club' &&
        w.tabs.Partners.some(r => r[0] === 'Brand New Org') &&
        w.tabs['SF Pending'][1].slice(1, 3).join('|') === 'Brand New Org|Nova Club' &&
        w.tabs['SF Pending'][1][5] === 'Mentor Testperson' && w.tabs['SF Pending'][1][7] === 'Kenya');
  check('…and the ReviewQueue ("Same name listed twice" starts with the name, stripped)',
        w.tabs.ReviewQueue.some(r => r[1] === 'Same name listed twice' && r[4].startsWith('Grace Zibblewick —')));
  const leaked = w.cells().filter(c => /^[=+\-@]/.test(c));
  check('no cell the handler wrote starts with = + - @', !leaked.length, leaked.join(' | '));

  const club = rosterRows('Fixture Partner Alpha', 'Sunrise Club', ['Grace Zibblewick', 'Mary Zibblewick']);
  const w2 = sheetWorld(baseTabs(club));
  w2.ctx.handleRosterChange_({ [HQ.ACTION]: HQ.ACTION_MOD, [HQ.PARTNER_MOD]: 'Fixture Partner Alpha',
                               [HQ.CLUB_PREFIX + 'Fixture Partner Alpha)']: 'Sunrise Club',
                               [HQ.ADD]: '=Joy Blorptest\n@=Amina Qwertyson Alpha', [HQ.REMOVE]: 'Mary Zibblewick',
                               [HQ.MENTOR_EMAIL_MOD]: 'mentor@example.org' }, 'Roster Form Responses!42');
  check('a roster change: ADD names sheet-safe, REMOVE still matched as typed',
        w2.tabs.Roster.slice(3).map(r => r[4]).join('|') === 'Joy Blorptest|Amina Qwertyson Alpha' &&
        w2.tabs.Roster[2][6] === 'inactive' && !w2.cells().some(c => /^[=+\-@]/.test(c)));

  // a formula after the first word: lastName_ files the last word in last_name
  const w3 = sheetWorld(baseTabs());
  const res3 = w3.ctx.handleNewClub_(newClub('Fixture Partner Alpha', 'Evening Club',
      ['Ivy =1+1', 'Jo +HYPERLINK("x")', 'Hana -A1', 'Uma @=IMAGE("x")', 'Ivy 1+1']), 'Roster Form Responses!43', KEY41);
  const leak3 = w3.cells().filter(c => /^[=+\-@]/.test(c));
  check('a new club with a formula in a later word of a name: no cell starts with = + - @, last_name included',
        /^new club Evening Club/.test(res3) && !leak3.length &&
        w3.tabs.Roster.slice(1).map(r => r[4] + '/' + r[5]).join('|') ===
            'Ivy =1+1/1+1|Jo +HYPERLINK("x")/HYPERLINK("x")|Hana -A1/A1|Uma @=IMAGE("x")/IMAGE("x")|Ivy 1+1/1+1' &&
        !w3.tabs.ReviewQueue.some(r => r[1] === 'Same name listed twice'),
        res3.slice(0, 40) + ' :: ' + leak3.join(' | '));
  const w4 = sheetWorld(baseTabs(rosterRows('Fixture Partner Alpha', 'Sunrise Club', ['Grace Zibblewick'])));
  w4.ctx.handleRosterChange_({ [HQ.ACTION]: HQ.ACTION_MOD, [HQ.PARTNER_MOD]: 'Fixture Partner Alpha',
                               [HQ.CLUB_PREFIX + 'Fixture Partner Alpha)']: 'Sunrise Club',
                               [HQ.ADD]: 'Joy =1+1\nAmina Qwertyson -A1' }, 'Roster Form Responses!44');
  const leak4 = w4.cells().filter(c => /^[=+\-@]/.test(c));
  check('a roster change ADD with a formula in a later word: sheet-safe, last_name included',
        !leak4.length && w4.tabs.Roster.slice(2).map(r => r[4] + '/' + r[5]).join('|') === 'Joy =1+1/1+1|Amina Qwertyson -A1/A1',
        leak4.join(' | '));

  // Review finding (integration, 2026-09-29): a word-by-word strip made an enrolled name with a
  // standalone "-" (or a word starting with "-") differ from its Roster spelling, so listing her
  // again added a second active girl, and a REMOVE typed as enrolled matched no one.
  const A = 'Fixture Partner Alpha', SUN = 'Sunrise Club';
  const sunActive = w => w.tabs.Roster.slice(1).filter(r => r[2] === SUN && r[6] === 'active').length;
  for (const odd of ['Ada Ostrivane - Pellucidor', 'Ada Ostrivane -Pellucidor']) {
    const shape = odd.includes(' - ') ? '" - "' : '" -Word"';
    const list = ['Grace Zibblewick', 'Mary Zibblewick', odd];
    let wa = sheetWorld(baseTabs(rosterRows(A, SUN, list)));
    const addRes = wa.ctx.handleRosterChange_({ [HQ.ACTION]: HQ.ACTION_MOD, [HQ.PARTNER_MOD]: A,
        [HQ.CLUB_PREFIX + A + ')']: SUN, [HQ.ADD]: odd }, 'Roster Form Responses!45', '2026-09-28');
    check('an enrolled name with ' + shape + ', listed in ADD as enrolled: already on the roster, no second row',
          sunActive(wa) === 3 && wa.tabs.Roster.length === 4 && /0 added/.test(addRes), addRes);
    wa = sheetWorld(baseTabs(rosterRows(A, SUN, list)));
    const reRes = wa.ctx.handleNewClub_(newClub(A, SUN, list), 'Roster Form Responses!46', KEY41);
    check('…the club re-sent on "Enroll a NEW club" with its list as enrolled: 0 added, no "Girls missing" item',
          sunActive(wa) === 3 && /0 girls added/.test(reRes) &&
          !wa.tabs.ReviewQueue.some(r => r[1] === 'Girls missing from the latest enrollment'), reRes);
    wa = sheetWorld(baseTabs());
    wa.ctx.handleNewClub_(newClub(A, SUN, list), 'Roster Form Responses!47', KEY41);
    const rmRes = wa.ctx.handleRosterChange_({ [HQ.ACTION]: HQ.ACTION_MOD, [HQ.PARTNER_MOD]: A,
        [HQ.CLUB_PREFIX + A + ')']: SUN, [HQ.REMOVE]: odd }, 'Roster Form Responses!48', '2026-09-28');
    check('…enrolled through the form, then a REMOVE typed the same way: she is removed',
          wa.tabs.Roster.length === 4 && sunActive(wa) === 2 && /1 removed/.test(rmRes) &&
          !wa.tabs.ReviewQueue.some(r => r[1] === 'Removal did not match anyone'), rmRes);
  }
}

console.log('\nA new club that may duplicate one on file is held, then released by staff (BACKLOG 11b)');
{
  const A = 'Fixture Partner Alpha';
  const PET = 'Hope Fennwhistle';   // a fictional girl: must never reach FormLog, Audit, an e-mail or a detail
  const onFile = rosterRows(A, 'BRIGHT GIRLS', ['Ada Marrowgate', 'Bea Marrowgate', 'Cora Marrowgate', 'Dina Marrowgate'])
      .concat(rosterRows(A, 'Sunrise Club', ['Grace Zibblewick', 'Mary Zibblewick', 'Joy Blorptest']));
  const suffixed = () => newClub(A, 'BRIGHT GIRLS (TESTVILLE SEC SCH)', [PET, 'Eva Marrowgate', 'Fay Marrowgate']);
  const KEY = 'ROSTER|w:2026-09-21 10:15:30.250|' + A + '|BRIGHT GIRLS (TESTVILLE SEC SCH)';
  const SRC = 'Roster Form Responses!41';
  const clean = s => !/Fennwhistle|Marrowgate|Zibblewick|example\.org/.test(s);

  console.log('\n  held');
  let w = sheetWorld(baseTabs(onFile));
  const before = JSON.stringify(w.tabs);
  let res = w.ctx.runResponse_('ROSTER', w.sheet('Roster Form Responses'), 41, suffixed(), KEY);
  const item = w.tabs.ReviewQueue[1] || [];
  check('FormLog: HELD, with the reason kind and the ReviewQueue tag',
        res === 'HELD: possible duplicate (club name) — ReviewQueue [#' + SRC + ']' &&
        w.formLog.length === 1 && w.formLog[0][3] === res, res);
  check('nothing imported: Roster, ClubRegistry, Partners and SF Pending unchanged; no dropdown refresh, no Jotform sync',
        JSON.stringify(Object.assign({}, w.tabs, { ReviewQueue: JSON.parse(before).ReviewQueue })) === before &&
        !w.synced && !w.notified.length);
  check('one ReviewQueue item: issue, partner and club as sent, sent time, the club on file, the tag last',
        w.tabs.ReviewQueue.length === 2 && item[1] === 'New club held as a possible duplicate' && item[2] === A &&
        item[3] === 'BRIGHT GIRLS (TESTVILLE SEC SCH)' &&
        item[4].startsWith(SRC + ' (sent 2026-09-21 10:15:30): nothing imported') &&
        item[4].includes('BRIGHT GIRLS (Fixture Partner Alpha), already enrolled') &&
        item[4].endsWith('[#' + SRC + ']') && clean(item[4]), item[4]);
  check('the mentor is told it is being checked — only the club and partner they sent, no girl, no club on file',
        w.mails.length === 1 && w.mails[0].to === 'mentor@example.org' &&
        w.mails[0].subject === 'GLOW enrollment received – BRIGHT GIRLS (TESTVILLE SEC SCH)' &&
        w.mails[0].body.includes('checking it against the clubs already enrolled') &&
        !/Fennwhistle|Marrowgate|already enrolled\)/.test(w.mails[0].body) &&
        w.mails[0].body.split('BRIGHT GIRLS').length === 2);
  check('Audit: the source and the reason kind only',
        w.audits.join() === 'newClubForm: held ' + SRC + ' for review (club name); nothing imported');

  console.log('\n  released');
  w = sheetWorld(baseTabs(onFile));
  res = w.ctx.runResponse_('ROSTER', w.sheet('Roster Form Responses'), 41, suffixed(), KEY, true);
  check('released: imported as sent, the guard skipped, and FormLog says so',
        /^new club BRIGHT GIRLS \(TESTVILLE SEC SCH\) \(Fixture Partner Alpha\): 3 girls added, .*\(released from hold by staff\)$/.test(res) &&
        w.tabs.Roster.length === onFile.length + 4 && w.tabs['SF Pending'].length === 2 &&
        w.notified.join() === 'newClubForm' && !w.mails.length, res);

  console.log('\n  the other reasons, through the handler');
  w = sheetWorld(baseTabs(onFile));
  res = w.ctx.handleNewClub_(newClub(A, 'Sunrise Club', ['Ivy Newperson', 'Jo Newperson', 'Hana Newperson']), SRC, KEY);
  check('an exact re-enrollment with another list: held (re-enrollment list), nothing reactivated or added',
        /^HELD: possible duplicate \(re-enrollment list\)/.test(res) && w.tabs.Roster.length === onFile.length + 1, res);
  w = sheetWorld(baseTabs(onFile));
  res = w.ctx.handleNewClub_(newClub(fh.OTHER_PARTNER, 'Evening Club', ['Grace Zibblewick', 'Mary Zibblewick', 'Ivy Newperson'],
      { [HQ.NEW_PARTNER]: 'fixture partner  alpha.', [HQ.REGION]: 'Africa' }), SRC, KEY);
  check('names on file under a retyped organization: held (names on file, organization name)',
        res.startsWith('HELD: possible duplicate (names on file, organization name)'), res);
  w = sheetWorld(baseTabs(onFile));
  res = w.ctx.handleNewClub_(newClub(A, 'Evening Club', ['Ivy Newperson', 'Jo Newperson']), SRC, KEY);
  check('a genuinely new club of a known partner: imported as before', /^new club Evening Club/.test(res) && !w.mails.length, res);

  console.log('\n  an organization-name hold: released only once the partner is on file as sent (review F2)');
  const typedOrg = extra => newClub(fh.OTHER_PARTNER, 'Evening Club', ['Ivy Newperson', 'Jo Newperson'],
                                    Object.assign({ [HQ.NEW_PARTNER]: 'Fundacion Demo' }, extra || {}));
  const STEP = 'if it is that partner, set the response row\'s "' + HQ.PARTNER_NEW + '" cell to it exactly as the ' +
               'Partners tab spells it; if it is another organization, add it to the Partners tab with its region';
  w = sheetWorld(baseTabs(onFile));
  res = w.ctx.runResponse_('ROSTER', w.sheet('Roster Form Responses'), 41, typedOrg(), KEY);
  const orgDetail = (w.tabs.ReviewQueue[1] || [])[4] || '';
  check('held (organization name); its item says to fix the partner cell (or add the organization) before "release"',
        res.startsWith('HELD: possible duplicate (organization name)') &&
        orgDetail.includes('Really new (or the list is right): first, ' + STEP + '; then resolved "release <date>') &&
        orgDetail.endsWith('[#' + SRC + ']') && !(item[4] || '').includes(STEP), orgDetail.slice(0, 60));
  w = sheetWorld(baseTabs(onFile));
  const untouched = JSON.stringify([w.tabs.Roster, w.tabs.ClubRegistry, w.tabs.Partners, w.tabs['SF Pending']]);
  res = w.ctx.runResponse_('ROSTER', w.sheet('Roster Form Responses'), 41, typedOrg(), KEY, true);
  check('released as typed: refused as ERROR (the menu offers it again), nothing imported — no second Partners row, no SF Pending row',
        res === 'ERROR: release refused: the organization was typed as "Fundacion Demo", close to Fundación Demo on file. ' +
                'First, ' + STEP + '.' &&
        JSON.stringify([w.tabs.Roster, w.tabs.ClubRegistry, w.tabs.Partners, w.tabs['SF Pending']]) === untouched &&
        w.tabs.ReviewQueue.some(r => r[1] === 'Form response could not be processed' &&
                                    r[4].includes('— fix the cause, then run "Process any missed form responses".')) &&
        !w.notified.length && !w.mails.length,
        res.slice(0, 60));
  w = sheetWorld(baseTabs(onFile));
  res = w.ctx.runResponse_('ROSTER', w.sheet('Roster Form Responses'), 41, typedOrg({ [HQ.PARTNER_NEW]: 'Fundación Demo' }), KEY, true);
  check('the response\'s partner cell set to the partner on file, then released: filed under it, with its region',
        /^new club Evening Club \(Fundación Demo\): 2 girls added/.test(res) && w.tabs.Partners.length === 4 &&
        w.tabs['SF Pending'][1].slice(1, 4).join('|') === 'Fundación Demo|Evening Club|Latin America' &&
        !w.tabs.ReviewQueue.some(r => r[1] === 'Partner has no region'), res.slice(0, 60));
  w = sheetWorld(baseTabs(onFile));
  w.tabs.Partners.push(['Fundacion Demo', 'Asia', 'another organization']);
  res = w.ctx.runResponse_('ROSTER', w.sheet('Roster Form Responses'), 41, typedOrg(), KEY, true);
  check('another organization after all, added to the Partners tab: the release imports it under its own name and region',
        /^new club Evening Club \(Fundacion Demo\): 2 girls added/.test(res) &&
        w.tabs['SF Pending'][1].slice(1, 4).join('|') === 'Fundacion Demo|Evening Club|Asia', res.slice(0, 60));

  console.log('\n  failures');
  w = sheetWorld(baseTabs(onFile), { down: 'ReviewQueue' });
  res = w.ctx.runResponse_('ROSTER', w.sheet('Roster Form Responses'), 41, suffixed(), KEY);
  check('the ReviewQueue unavailable: ERROR (retried from the menu), the mentor NOT e-mailed, nothing imported',
        res === 'ERROR: sheet unavailable' && !w.mails.length && w.tabs.Roster.length === onFile.length + 1, res);
  w = sheetWorld(baseTabs(onFile), { mailFails: true });
  res = w.ctx.runResponse_('ROSTER', w.sheet('Roster Form Responses'), 41, suffixed(), KEY);
  check('the e-mail failing: still held; Audit says so without the address',
        res.startsWith('HELD:') && w.tabs.ReviewQueue.length === 2 &&
        w.audits.some(a => a === 'sendHoldNotice_: could not e-mail the mentor about ' + SRC + ': Invalid email: <e-mail>') &&
        clean(w.audits.join('\n')));

  console.log('\n  a repeated trigger does not hold twice');
  w = sheetWorld(baseTabs(onFile));
  const stamp = { wall: '2026-09-21 10:15:30.250', ms: 0 };
  w.ctx.spreadsheetZone_ = () => 'America/New_York';
  w.ctx.readResponseRow_ = () => ({ answers: suffixed(), stamp });
  w.ctx.readFormLogIndex_ = () => w.ctx.indexFormLog_(w.formLog);
  const firstRun = w.ctx.processResponseRow_('ROSTER', w.sheet('Roster Form Responses'), 41);
  const secondRun = w.ctx.processResponseRow_('ROSTER', w.sheet('Roster Form Responses'), 41);
  check('the trigger holds it once; a second trigger for the same row does nothing (one e-mail, one FormLog row)',
        firstRun && !secondRun && w.mails.length === 1 && w.formLog.length === 1 && w.formLog[0][2] === KEY);
}

console.log('\n  FormLog, the ReviewQueue decision and the menu plan');
const hd = loadGs(['Q', 'HOLD_PREFIX', 'HOLD_ISSUE', 'RETRY_PREFIXES', 'REVIEW_ISSUES', 'isHeldResult_', 'isRetryResult_',
                   'heldForReview_', 'indexFormLog_', 'holdDecisions_', 'planMissedRun_', 'missedPreviewText_',
                   'responseKeyOf_', 'responseDone_', 'sentAtOfKey_', 'sentAtOfStamp_', 'releasedBy_',
                   'heldClubReviewItem_', 'reviewDigest_', 'closedHoldsText_'],
                  ['Config.gs', 'Normalize.gs', 'FormHandlers.gs']);
{
  const today = '2026-09-28';
  const tab = 'Roster Form Responses';
  const R = (row, wall, club) => ({ which: 'ROSTER', row, tab, stamp: cellAt(wall, -240), answers: newClubAnswers(club) });
  const keyOf = r => hd.responseKeyOf_('ROSTER', r.stamp, r.answers);
  const HELD = 'HELD: possible duplicate (club name) — ReviewQueue [#…]';
  check('HELD: is its own prefix: not a retry, not done', hd.HOLD_PREFIX === 'HELD:' && hd.isHeldResult_(HELD) &&
        !hd.isRetryResult_(HELD) && !hd.isHeldResult_('ERROR: x') && !hd.isHeldResult_(null) &&
        hd.RETRY_PREFIXES.join() === 'ERROR:');
  // Code without the guard reads HELD: as done, so a release after a rollback imports nothing
  // and closes the item (integration review, rollout-safety F1/F2): the RUNBOOK must say so.
  const rbDoc = fs.readFileSync(path.join(REPO, 'docs', 'RUNBOOK.md'), 'utf8');
  const heldRb = (rbDoc.split('**Held new clubs and a rollback')[1] || '').split('\n\n')[0].replace(/\s+/g, ' ');
  check('RUNBOOK: a rollback below the duplicate-club guard names held new clubs and how to find that code',
        heldRb.includes('`' + hd.HOLD_PREFIX + '`') && heldRb.includes(hd.HOLD_ISSUE) &&
        heldRb.includes('git grep -q HOLD_PREFIX') && heldRb.includes('never write `release`'), heldRb.slice(0, 60));
  const deployRb = (rbDoc.split('\n## Apps Script deploy')[1] || '').split('\n## ')[0].replace(/\s+/g, ' ');
  check('RUNBOOK Apps Script deploy: the rollback names a target that changes something (986a325) and the held caveat',
        deployRb.includes('git checkout 986a325 -- appsscript') && deployRb.includes('held new clubs') &&
        !deployRb.includes("previous commit's"), deployRb.slice(-80));
  const a = R(41, '2026-09-21 10:15:30.250', 'Alpha Club');
  const idx = hd.indexFormLog_([['ROSTER', 41, keyOf(a), 'ERROR: incomplete submission: missing roster'],
                                ['ROSTER', 41, keyOf(a), HELD]]);
  check('a held row: not done, not a processed row, found by its stamp, earlier failures cleared',
        !hd.responseDone_('ROSTER', a.stamp, a.answers, idx) && !idx.okRows['ROSTER|41'] &&
        hd.heldForReview_('ROSTER', a.stamp, keyOf(a), idx) && !idx.errorsByKey[keyOf(a)] && !idx.errorsByRow['ROSTER|41']);
  check('…still found after its club cell is edited (the stamp, not the key)',
        hd.heldForReview_('ROSTER', a.stamp, 'ROSTER|w:2026-09-21 10:15:30.250|x|edited', idx));
  const after = hd.indexFormLog_([['ROSTER', 41, keyOf(a), HELD], ['ROSTER', 41, keyOf(a), 'ERROR: quota']]);
  check('a failure after the hold (a released run failed) is kept', after.errorsByKey[keyOf(a)] === 'ERROR: quota');
  check('the sent time: from a key, from a stamp; "?" when there is none',
        hd.sentAtOfKey_(keyOf(a)) === '2026-09-21 10:15:30' && hd.sentAtOfStamp_(a.stamp) === '2026-09-21 10:15:30' &&
        hd.sentAtOfKey_('ROSTER|1789820138000|x|y') === '?' && hd.sentAtOfStamp_({ text: 'x' }) === '?');

  const item = hd.heldClubReviewItem_('Fixture Partner Alpha', 'Alpha Club', tab + '!41', '2026-09-21 10:15:30',
                                      [{ kind: 'club', text: 'the club name is close to X' }]);
  check('the hold item\'s issue is HOLD_ISSUE, first in REVIEW_ISSUES (a club waiting to be enrolled is the most urgent)',
        item.issue === hd.HOLD_ISSUE && hd.REVIEW_ISSUES[0] === hd.HOLD_ISSUE && item.dedupeKey === tab + '!41');
  const rq = (row, issue, detail, resolved) => ({ row, issue, detail, resolved: resolved || '' });
  const detail = (r, sent) => r + ' (sent ' + sent + '): nothing imported … [#' + r + ']';
  const decisions = hd.holdDecisions_([
    rq(5, hd.HOLD_ISSUE, detail(tab + '!41', '2026-09-21 10:15:30')),
    rq(6, hd.HOLD_ISSUE, detail(tab + '!42', '2026-09-22 09:00:00'), 'release 2026-09-28 by Ryan: a new club'),
    rq(7, hd.HOLD_ISSUE, detail(tab + '!43', '2026-09-22 09:30:00'), 'resolved 2026-09-28 by Ryan: same club, 1 girl added'),
    rq(8, hd.HOLD_ISSUE, detail(tab + '!44', '2026-09-22 10:00:00'), 'released by hand'),
    rq(9, 'Removal did not match anyone', detail(tab + '!45', '2026-09-22 10:30:00'), 'release'),
    rq(10, hd.HOLD_ISSUE, detail(tab + '!46', '2026-09-22 11:00:00') + ' typed after the tag', 'release'),
    rq(11, hd.HOLD_ISSUE, detail(tab + '!47', '2026-09-22 11:30:00'), 'resolved: not a club'),
    rq(12, hd.HOLD_ISSUE, detail(tab + '!47', '2026-09-22 11:30:00'), ' RELEASE: checked with the partner'),
  ]);
  const st = t => decisions[tab + '!' + t] && decisions[tab + '!' + t].state;
  check('holdDecisions_: empty → open; "release …" → release; any other text → closed ("released" is not "release")',
        st(41) === 'open' && st(42) === 'release' && st(43) === 'closed' && st(44) === 'closed');
  check('holdDecisions_: other issues, and an item typed after its tag, are ignored; the last item wins',
        !decisions[tab + '!45'] && !decisions[tab + '!46'] && st(47) === 'release' && decisions[tab + '!47'].row === 12 &&
        decisions[tab + '!41'].sentAt === '2026-09-21 10:15:30');

  const rows = [R(41, '2026-09-21 10:15:30.250', 'Alpha Club'), R(42, '2026-09-22 09:00:00.100', 'Bravo Club'),
                R(43, '2026-09-22 09:30:00.100', 'Charlie Club'), R(44, '2026-09-22 10:00:00.100', 'Delta Club'),
                R(48, '2026-09-22 12:00:00.100', 'Echo Club'), R(49, '2026-09-27 12:00:00.100', 'Foxtrot Club'),
                R(50, '2026-09-10 12:00:00.100', 'Golf Club')];
  const heldLog = rows.slice(0, 5).map(r => ['ROSTER', r.row, keyOf(r), HELD])
      .concat([['ROSTER', 50, keyOf(rows[6]), HELD], ['ROSTER', 50, keyOf(rows[6]), 'ERROR: quota']]);
  const holds = Object.assign({}, decisions, {
    [tab + '!48']: { row: 13, state: 'release', sentAt: '2026-09-20 08:00:00' },   // another response's item: the tab was sorted
    [tab + '!50']: { row: 14, state: 'release', sentAt: '2026-09-10 12:00:00' },
  });
  const plan = hd.planMissedRun_(rows, hd.indexFormLog_(heldLog), today, 7, holds);
  const src = items => items.map(i => i.source.replace(tab + '!', '')).join(',');
  check('released (the item says release, sent time matches): its own group — even when older than 7 days',
        src(plan.released) === '42,50' && plan.released.every(i => i.status === 'released'), src(plan.released));
  check('waiting: open (41) and 48; closed (43, and 44 "released by hand") are never run, only named as closed',
        src(plan.waiting) === '41,48' && !/43|44/.test(src(plan.run.concat(plan.old, plan.held, plan.waiting, plan.released))) &&
        src(plan.closed) === '43,44' && plan.closed.every(i => i.status === 'closed') && plan.closed[1].note === 'ReviewQueue row 8',
        src(plan.waiting) + ' / ' + src(plan.closed));
  const closedLine = hd.closedHoldsText_(plan.closed, 15);
  check('closed: one line with the response and ReviewQueue rows and how to import one — a mistyped release shows, never a name',
        closedLine === 'Not imported — new clubs held for review whose ReviewQueue item was resolved without "release" ' +
                       '(to import one, start that resolved cell with "release" and run this again): ' +
                       'row 43 (ReviewQueue row 7), row 44 (ReviewQueue row 8)' &&
        hd.closedHoldsText_(plan.closed, 1).endsWith(': row 43 (ReviewQueue row 7), … and 1 more'), closedLine.slice(-60));
  check('an item for another response (tab sorted: the sent time differs) never releases this one',
        plan.waiting[1].note === 'no ReviewQueue item for this row and time (docs/RUNBOOK.md)' &&
        plan.waiting[0].note === 'waiting for staff: ReviewQueue row 5' && !plan.waiting[0].lastError);
  check('a released row that failed after its release shows that failure; a new row is run as before',
        plan.released[1].lastError === 'ERROR: quota' && src(plan.run) === '49' && !plan.old.length && !plan.held.length);
  const takenBack = hd.planMissedRun_([rows[6]], hd.indexFormLog_(heldLog), today, 7,
      { [tab + '!50']: { row: 14, state: 'open', sentAt: '2026-09-10 12:00:00' } });
  check('released, failed, then the release taken back: it waits, and is not offered as "retry after ERROR"',
        src(takenBack.waiting) === '50' && takenBack.waiting[0].lastError === '' &&
        !hd.missedPreviewText_('x', takenBack.waiting, 15).includes('retry after'));
  const hotel = R(51, '2026-09-23 08:00:00.100', 'Hotel Club');
  const sortedAway = hd.planMissedRun_([hotel], hd.indexFormLog_([['ROSTER', 51, keyOf(hotel), HELD]]), today, 7,
      { [tab + '!51']: { row: 15, state: 'closed', sentAt: '2026-09-20 08:00:00' } });   // another response's item
  check('a CLOSED item for another response (tab sorted) never takes this held row off the menu: it waits',
        src(sortedAway.waiting) === '51' && !sortedAway.run.length && !sortedAway.released.length &&
        sortedAway.waiting[0].note === 'no ReviewQueue item for this row and time (docs/RUNBOOK.md)', src(sortedAway.waiting));
  const noHolds = hd.planMissedRun_(rows.slice(0, 1), hd.indexFormLog_(heldLog), today, 7);
  check('no decisions given (an old caller): a held row waits', src(noHolds.waiting) === '41' && !noHolds.run.length);
  const text = hd.missedPreviewText_('x', plan.waiting.concat(plan.released), 15);
  check('the preview says why each held row waits or runs, never a name',
        text.includes('• row 41 · sent 2026-09-21 10:15 · new club · Alpha Club (Test Partner Org) · waiting for staff: ReviewQueue row 5') &&
        text.includes('row 42 · sent 2026-09-22 09:00 · new club · Bravo Club (Test Partner Org) · released in ReviewQueue row 6') &&
        !/Zibblewick|@/.test(text), text.split('\n').length + ' lines');
  const digest = hd.reviewDigest_([{ row: 5, raised: '2026-09-22', issue: hd.HOLD_ISSUE, partner: 'Fixture Partner Alpha',
      club: 'Alpha Club', detail: detail(tab + '!41', '2026-09-21 10:15:30'), resolved: '' }], today,
      { partners: { 'fixture partner alpha': 'Fixture Partner Alpha' }, clubs: {} });
  check('the Monday e-mail lists a hold first, with its response row; the new club is not on file so it is masked',
        digest.lines[2] === hd.HOLD_ISSUE + ': 1 open, 1 new, oldest 6 day(s)' &&
        digest.lines[3] === '  - row 5 · raised 2026-09-22 · Fixture Partner Alpha / (club not on file) · ' + tab + '!41', digest.lines[3]);
}

console.log('\n  the menu run with held rows (processMissedResponses, runConfirmed_; Google services stubbed)');
{
  const vm = require('vm');
  const src = ['Config.gs', 'Normalize.gs', 'FormHandlers.gs']
      .map(f => fs.readFileSync(path.join(loadGs.GS_DIR, f), 'utf8')).join('\n');
  const tab = 'Roster Form Responses';
  const R = (row, wall, club) => ({ which: 'ROSTER', row, tab, stamp: cellAt(wall, -240), answers: newClubAnswers(club) });
  const HELD = 'HELD: possible duplicate (club name) — ReviewQueue [#…]';
  const held = [R(41, '2026-09-21 10:15:30.250', 'Alpha Club'), R(42, '2026-09-22 09:00:00.100', 'Bravo Club')];
  const fresh = R(49, '2026-09-27 12:00:00.100', 'Foxtrot Club');
  const world = (responses, holds, replies) => {
    const ran = [], audits = [], dialogs = [];
    const ctx = vm.createContext({
      console,
      SpreadsheetApp: { getUi: () => ({
        alert: (title, text, buttons) => { dialogs.push(text); return buttons === 'YES_NO' ? replies.shift() : 'OK'; },
        Button: { YES: 'YES', NO: 'NO' }, ButtonSet: { YES_NO: 'YES_NO', OK: 'OK' } }) },
      LockService: { getDocumentLock: () => ({ tryLock: () => true, releaseLock: () => {} }) },
      Utilities: { sleep: () => {} },
    });
    vm.runInContext(src, ctx);
    const log = held.map(r => ['ROSTER', r.row, ctx.responseKeyOf_('ROSTER', r.stamp, r.answers), HELD]);
    ctx.readMissedSnapshot_ = () => ({ zone: 'America/New_York', sheets: { ROSTER: {} }, responses,
                                       index: ctx.indexFormLog_(log), today: '2026-09-28', holds });
    ctx.readResponseRow_ = (sheet, row) => responses.find(r => r.row === row);
    ctx.readFormLogIndex_ = () => ctx.indexFormLog_(log);
    ctx.readHoldDecisions_ = () => holds;
    ctx.runResponse_ = (which, sheet, row, answers, key, released) => { ran.push(row + (released ? ' released' : '')); return 'new club ok'; };
    ctx.audit_ = (action, detail) => audits.push(action + ': ' + detail);
    vm.runInContext('processMissedResponses()', ctx);
    return { ran, audits, dialogs, ctx, log };
  };
  const open = { [tab + '!41']: { row: 5, state: 'open', sentAt: '2026-09-21 10:15:30' },
                 [tab + '!42']: { row: 6, state: 'open', sentAt: '2026-09-22 09:00:00' } };
  let m = world(held, open, []);
  check('only held rows: "Nothing to process." lists them as held for review, and nothing runs',
        m.dialogs.length === 1 && m.dialogs[0].startsWith('Nothing to process.') &&
        m.dialogs[0].includes('new clubs held for review') && m.dialogs[0].includes('• row 41') && !m.ran.length);
  m = world(held, Object.assign({}, open, { [tab + '!41']: { row: 5, state: 'closed', sentAt: '2026-09-21 10:15:30' } }), []);
  check('a hold resolved without "release" (e.g. "Released"): not run, but named on the "Nothing to process." dialog',
        m.dialogs.length === 1 && m.dialogs[0].startsWith('Nothing to process.') && !m.ran.length &&
        m.dialogs[0].includes('• row 42') && !m.dialogs[0].includes('• row 41') &&
        m.dialogs[0].endsWith('resolved without "release" (to import one, start that resolved cell with "release" and run ' +
                              'this again): row 41 (ReviewQueue row 5)'), m.dialogs.length + ' dialogs');
  const release42 = Object.assign({}, open, { [tab + '!42']: { row: 6, state: 'release', sentAt: '2026-09-22 09:00:00' } });
  m = world(held.concat([fresh]), release42, ['YES', 'YES']);
  check('a released row is asked on its own, after the new rows; the held one is listed with the result',
        m.dialogs.length === 3 && /^Club Roster Form responses not yet processed \(1\)/.test(m.dialogs[0]) &&
        /^New clubs held for review that staff released in the ReviewQueue \(1\):\n• row 42 .*released in ReviewQueue row 6/.test(m.dialogs[1]) &&
        /^2 processed\./.test(m.dialogs[2]) && m.dialogs[2].includes('new clubs held for review') &&
        m.dialogs[2].includes('• row 41'), m.dialogs.length + ' dialogs');
  check('YES: the new row runs, the released row runs as released, the waiting row never',
        m.ran.join() === '42 released,49' && /held for review: Roster Form Responses!41/.test(m.audits[0]), m.ran.join());
  m = world(held, release42, ['NO']);
  check('NO to the released group: nothing runs; Audit records it as declined and the held-for-review row',
        !m.ran.length && /cancelled at the preview \(would have run Roster Form Responses!42\); held for review: Roster Form Responses!41/.test(m.audits[0]),
        m.audits.join());

  // runConfirmed_ re-reads the decision under the lock
  m = world([], {}, []);
  const snap = { zone: 'America/New_York', sheets: { ROSTER: {} } };
  const item = r => ({ which: 'ROSTER', row: r.row, source: tab + '!' + r.row, key: m.ctx.responseKeyOf_('ROSTER', r.stamp, r.answers) });
  m.ctx.readResponseRow_ = (sheet, row) => held.concat([fresh]).find(r => r.row === row);
  m.ctx.readFormLogIndex_ = () => m.ctx.indexFormLog_(m.log);
  m.ctx.readHoldDecisions_ = () => open;   // staff took the release back after the preview
  const took = m.ctx.runConfirmed_(Object.assign(item(held[1]), { status: 'released' }), snap);
  m.ctx.readHoldDecisions_ = () => release42;
  // released since the preview, but the preview offered it as 'new': the YES was not to "run as sent, check skipped"
  const notAsked = m.ctx.runConfirmed_(Object.assign(item(held[1]), { status: 'new' }), snap);
  check('runConfirmed_: a held row the preview did not offer as released is skipped, even if its item now says release',
        notAsked === tab + '!42 skipped (held for review; its ReviewQueue item does not say release)' && !m.ran.length,
        notAsked + ' | ' + m.ran.join());
  const ok = m.ctx.runConfirmed_(Object.assign(item(held[1]), { status: 'released' }), snap);
  const sneaky = m.ctx.runConfirmed_(Object.assign(item(held[0]), { status: 'new' }), snap);
  m.ctx.runResponse_ = () => 'HELD: possible duplicate (names on file) — ReviewQueue [#' + tab + '!49]';
  const heldNow = m.ctx.runConfirmed_(Object.assign(item(fresh), { status: 'new' }), snap);
  check('runConfirmed_: a release taken back after the preview is skipped; a held row never runs unreleased',
        /skipped \(held for review; its ReviewQueue item does not say release\)$/.test(took) &&
        /skipped \(held for review/.test(sneaky) && m.ran.join() === '42 released', [took, sneaky, m.ran.join()].join(' | '));
  check('runConfirmed_: released → "ok"; a row the guard holds now → "held for review", not "failed again"',
        ok === tab + '!42 ok' && heldNow === tab + '!49 held for review (see ReviewQueue)', [ok, heldNow].join(' | '));
}

console.log('\nBoth guards together: a released new club is replay-guarded too (wf/integration)');
{
  // A re-enrollment held on 09-21, released by staff and run on 09-28. One girl it lists was
  // removed 09-25 (after it was sent): she stays removed. One removed 09-01 comes back.
  const A = 'Fixture Partner Alpha';
  const gone = (id, name, day) => [id, A, 'Sunrise Club', 'Africa', name, name.split(' ').pop(), 'inactive', '2026-08-26', day,
                                   'Roster Form Responses!6'];
  const tabs = () => baseTabs(rosterRows(A, 'Sunrise Club', ['Grace Zibblewick', 'Mary Zibblewick'])
      .concat([gone('T900', 'Joy Blorptest', '2026-09-25'), gone('T901', 'Hana Blorptest', '2026-09-01')]));
  const listed = newClub(A, 'Sunrise Club', ['Grace Zibblewick', 'Mary Zibblewick', 'Joy Blorptest', 'Hana Blorptest']);
  let w = sheetWorld(tabs());
  const res = w.ctx.runResponse_('ROSTER', w.sheet('Roster Form Responses'), 41, listed, KEY41, true);
  const st = (x, n) => x.tabs.Roster.find(r => r[4] === n)[6];
  const kept = w.tabs.ReviewQueue.filter(r => r[1] === 'Removed girls not put back by an older response');
  check('released and run late: removed after it was sent stays removed, removed before comes back; one item, no names',
        res === 'existing club Sunrise Club (' + A + '): 0 girls added, 1 reactivated, 1 kept removed, 1 for review ' +
            '(released from hold by staff)' &&
        st(w, 'Joy Blorptest') === 'inactive' && st(w, 'Hana Blorptest') === 'active' && kept.length === 1 &&
        !/Blorptest|Zibblewick/.test(String(kept[0][4])) && w.formLog.length === 1 && w.formLog[0][3] === res, res);
  w = sheetWorld(tabs());
  const noDay = w.ctx.runResponse_('ROSTER', w.sheet('Roster Form Responses'), 41, listed,
                                   'ROSTER|9/21/2026 10:15:30|' + A + '|Sunrise Club', true);
  check('released, but its Timestamp is not a date: refused before anything is written (no sent day, no replay guard)',
        /^ERROR: its Timestamp cell is not a date/.test(noDay) && st(w, 'Hana Blorptest') === 'inactive' &&
        w.tabs.Roster.length === 5 && !w.mails.length, noDay);
}

console.log('\n  guards');
{
  const all = fs.readdirSync(loadGs.GS_DIR).filter(f => f.endsWith('.gs'))
      .map(f => fs.readFileSync(path.join(loadGs.GS_DIR, f), 'utf8')).join('\n');
  const raised = [...new Set([...all.matchAll(/issue: '([^']+)'/g)].map(m => m[1]))].sort();
  check('every issue the code raises is in REVIEW_ISSUES (' + pr.REVIEW_ISSUES.length + ')',
        raised.join('|') === pr.REVIEW_ISSUES.slice().sort().join('|'), raised.join(' | '));
  const rb = fs.readFileSync(path.join(REPO, 'docs', 'RUNBOOK.md'), 'utf8');
  const section = (rb.split('## Working the ReviewQueue')[1] || '').split('\n## ')[0];
  const missing = pr.REVIEW_ISSUES.filter(i => !section.includes('**' + i + '**'));
  check('docs/RUNBOOK.md "Working the ReviewQueue" has a staff action for each', !missing.length, missing.join(' | '));
  const fhSrc = fs.readFileSync(path.join(loadGs.GS_DIR, 'FormHandlers.gs'), 'utf8');
  check('the weekly trigger calls sendSfPendingDigest by name, and it exists',
        /newTrigger\('sendSfPendingDigest'\)/.test(fhSrc) && /^function sendSfPendingDigest\(\)/m.test(fhSrc));
  const rosterGs = fs.readFileSync(path.join(loadGs.GS_DIR, 'Roster.gs'), 'utf8');
  const rebuild = rosterGs.slice(rosterGs.indexOf('function rebuildRosterLocked_'), rosterGs.indexOf('function noRegionIssue_'));
  const offline = fs.readFileSync(path.join(REPO, 'tools', 'build_roster_offline.js'), 'utf8');
  check('the rebuild and the offline builder pass no submitted: no replay guard there (BACKLOG 39 stays open)',
        rebuild.includes('planClub_(') && !/submitted/.test(rebuild) && offline.includes('planClub_(') && !/submitted/.test(offline));
  check('dates are read in the spreadsheet\'s zone everywhere, never the script\'s', !/getScriptTimeZone/.test(all));
  const used = [...new Set(all.match(/\b(?:[A-Z]\w*App|[A-Z]\w*Service|Session|Utilities|Logger|Browser)\b(?=\s*\.)/g) || [])].sort().join(',');
  check('Google services unchanged (a new one adds an OAuth scope: CLAUDE.md rule 11)',
        used === 'FormApp,LockService,MailApp,PropertiesService,ScriptApp,SpreadsheetApp,UrlFetchApp,Utilities', used);
}

console.log('\n  the offline builder dates in the sheet\'s zone (--tz), never this machine\'s');
{
  const os = require('os');
  const { spawnSync } = require('child_process');
  const builder = path.join(REPO, 'tools', 'build_roster_offline.js');
  const fixture = path.join(REPO, 'test', 'fixtures', 'enrollment_sample.csv');
  // every run gets its own empty --out under a fresh tmpdir: never the default
  // data/roster_build/ (real data), and an --out without Roster.csv means no existing state
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'glow-offline-'));
  let runs = 0;
  const build = (extra, processTz) => {
    const out = path.join(tmp, 'run' + (++runs));
    fs.mkdirSync(out);
    const before = Date.now();
    const r = spawnSync(process.execPath, [builder, fixture, '--out', out, ...extra],
                        { env: Object.assign({}, process.env, { TZ: processTz }), encoding: 'utf8' });
    const files = fs.readdirSync(out);
    const read = name => fs.readFileSync(path.join(out, name + '.csv'), 'utf8');
    return { status: r.status, stderr: r.stderr || '', files, read, before, after: Date.now() };
  };
  const dayIn = (zone, ms) => new Intl.DateTimeFormat('en-CA', { timeZone: zone, year: 'numeric',
                                                                 month: '2-digit', day: '2-digit' }).format(new Date(ms));
  const TABS = ['Roster', 'ClubRegistry', 'Partners', 'ReviewQueue'];
  try {
    for (const [label, extra] of [['no --tz', []], ['--tz as the last argument (no value)', ['--tz']],
                                  ['an unknown zone', ['--tz', 'Mars/Olympus_Mons']]]) {
      const r = build(extra, 'UTC');
      check('refuses ' + label + ', writes nothing, says where to look',
            r.status !== 0 && r.stderr.includes('which zone is the sheet on? pass --tz') &&
            r.stderr.includes('File → Settings → Time zone') && !r.files.length,
            'exit ' + r.status + ', wrote [' + r.files.join(', ') + ']');
    }
    // the two sides of the date line are 25 h apart: their dates always differ, so a
    // builder reading the process's clock (the other zone) cannot pass
    const days = {};
    for (const [zone, processTz] of [['Pacific/Kiritimati', 'Pacific/Pago_Pago'],
                                     ['Pacific/Pago_Pago', 'Pacific/Kiritimati']]) {
      const r = build(['--tz', zone], processTz);
      const want = new Set([dayIn(zone, r.before), dayIn(zone, r.after)]);
      const found = r.status === 0 ? new Set(['Audit', ...TABS].flatMap(t => r.read(t).match(/\d{4}-\d\d-\d\d/g) || [])) : new Set();
      const when = r.status === 0 ? r.read('Audit').split('\n')[1].split(',')[0] : '';
      days[zone] = when.slice(0, 10);
      check('--tz ' + zone + ' under TZ=' + processTz + ': every date written is ' + zone + '\'s',
            r.status === 0 && found.size === 1 && want.has([...found][0]) &&
            /^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$/.test(when) && want.has(days[zone]),
            'exit ' + r.status + ' ' + r.stderr.trim() + ' found ' + [...found].join(',') + ' want ' + [...want].join('|'));
    }
    check('…and the two builds are dated a day or two apart', days['Pacific/Kiritimati'] > days['Pacific/Pago_Pago'],
          JSON.stringify(days));
    // the same --tz, two process zones: the same tabs (unless New York's day turned in between)
    const a = build(['--tz', 'America/New_York'], 'UTC'), b = build(['--tz', 'America/New_York'], 'Asia/Tokyo');
    const sameDay = dayIn('America/New_York', a.before) === dayIn('America/New_York', b.after);
    check('--tz America/New_York under TZ=UTC and TZ=Asia/Tokyo: identical tabs, Audit on the same day',
          a.status === 0 && b.status === 0 && (!sameDay || (TABS.every(t => a.read(t) === b.read(t)) &&
            a.read('Audit').split('\n')[1].slice(0, 10) === b.read('Audit').split('\n')[1].slice(0, 10))));
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

// ------------------------------- the Google Forms' wording (backlog 43)
console.log('\nGoogle Forms wording: the one-time migration and fresh builds (Forms.gs)');
const fw = loadGs(['Q', 'WORDING', 'WORDING_LABELS', 'feedbackDescription_', 'rosterDescription_',
                   'rosterDescription2026_08_', 'planFormWording_', 'formWordingPreviewText_',
                   'formWordingKey_', 'wordingText_'],
                  ['Config.gs', 'Normalize.gs', 'Forms.gs']);
const WQ = fw.Q, W = fw.WORDING, WL = fw.WORDING_LABELS;
const FB_URL = 'https://forms.example.org/problem/viewform';
const RF_URL = 'https://forms.example.org/roster/viewform';
// the problem form as it is live (2026-09-26): the reply-address question removed by hand
const LIVE_FEEDBACK_ITEMS = [['LIST', WQ.FB_FORM], ['PARAGRAPH_TEXT', WQ.FB_DOING],
                             ['PARAGRAPH_TEXT', WQ.FB_WHAT, 'What did you click or type, what did the screen show?'],
                             ['TEXT', WQ.FB_PARTNER], ['TEXT', WQ.FB_CLUB], ['TEXT', WQ.FB_DEVICE]];
const liveState = () => ({
  feedback: { url: FB_URL, description: W.FEEDBACK_INTRO,
              items: LIVE_FEEDBACK_ITEMS.map(([type, title]) => ({ type, title })) },
  roster: { url: RF_URL, description: fw.rosterDescription2026_08_(FB_URL),
            clubHelp: W.CLUB_HELP_2026_08, removeHelp: W.REMOVE_HELP_2026_08 },
});
const wantedState = () => {
  const s = liveState();
  s.feedback.description = fw.feedbackDescription_(RF_URL);
  s.feedback.items.push({ type: 'TEXT', title: WQ.FB_EMAIL });
  s.roster.description = fw.rosterDescription_(FB_URL);
  s.roster.clubHelp = W.CLUB_HELP;
  s.roster.removeHelp = W.REMOVE_HELP;
  return s;
};
const labelsOf = items => items.map(c => c.label).join(' | ');

console.log('\n  the wording');
{
  // what the live forms said on 2026-09-26 (saved public pages): the migration must recognise it
  check('the 2026-08 texts are pinned as the live forms show them',
        W.FEEDBACK_INTRO === 'Did a form do something odd, refuse to submit, show the wrong club, or take forever to load? ' +
            'Tell us here — it takes a minute and helps us fix it quickly. Please do not include girls\' names unless ' +
            'the problem is about a specific name.' &&
        fw.rosterDescription2026_08_('<link>') === 'Enroll a new club, or add and remove girls in a club that is already ' +
            'enrolled. Changes reach the attendance form within the hour. Removed girls stop appearing on the attendance ' +
            'form; their history is kept.\n\nSomething not working? <link>' &&
        W.CLUB_HELP_2026_08 === 'The name mentors will type on the attendance form.' &&
        W.REMOVE_HELP_2026_08 === 'Leave empty if nobody is leaving. Spell names as they were enrolled; we match ignoring capitals.');
  const fd = fw.feedbackDescription_(RF_URL), rd = fw.rosterDescription_(FB_URL);
  check('problem form: the intro kept, then roster changes sent to the Club Roster Form\'s real branch, its link last',
        fd.startsWith(W.FEEDBACK_INTRO + '\n\n') && fd.includes('"' + WQ.ACTION_MOD + '"') &&
        WQ.ACTION_MOD === 'Add or remove girls in a club that is already enrolled' && fd.endsWith(': ' + RF_URL));
  const lastLine = rd.split('\n').pop();
  check('Club Roster Form: the intro kept; its last line sends roster changes to the branch, problems to the link',
        rd.startsWith(W.ROSTER_INTRO + '\n\n') && lastLine.startsWith('Something not working?') &&
        lastLine.includes('"' + WQ.ACTION_MOD + '"') && lastLine.endsWith(': ' + FB_URL), lastLine);
  check('"Club name" help: the club\'s own name, not the mentor\'s', /club's own name/.test(W.CLUB_HELP) &&
        /not the mentor's name/.test(W.CLUB_HELP) && !/mentors will type/i.test(W.CLUB_HELP));
  check('REMOVE help: copy the spelling from the club\'s attendance form', /exactly as it is spelled on the club's attendance form/.test(W.REMOVE_HELP));
  // the RUNBOOK's rollback names where each 2026-08 text lives: the planner's own "before" texts
  const formsSrc = fs.readFileSync(path.join(loadGs.GS_DIR, 'Forms.gs'), 'utf8');
  const planSrc = formsSrc.slice(formsSrc.indexOf('function planFormWording_'), formsSrc.indexOf('function wordingText_'));
  const before = [...planSrc.matchAll(/\[(WORDING\.\w+|rosterDescription2026_08_)\b/g)]
      .map(m => m[1] + (m[1].startsWith('WORDING.') ? '' : '()'));
  const wordingRb = (fs.readFileSync(path.join(REPO, 'docs', 'RUNBOOK.md'), 'utf8')
      .split('## Google Forms wording')[1] || '').split('\n## ')[0];
  const rollback = (wordingRb.split('\n- ').find(b => b.startsWith('Rollback:')) || '').replace(/\s+/g, ' ');
  check('RUNBOOK rollback: names all four 2026-08 texts where they are, and the two-column read (986a325)',
        before.length === 4 && before.every(x => rollback.includes('`' + x + '`')) &&
        rollback.includes('986a325') && /two reply columns/.test(rollback) && !/only removes the menu item/.test(rollback),
        before.filter(x => !rollback.includes('`' + x + '`')).join(', ') || rollback.slice(0, 80));
}

console.log('\n  the plan (pure)');
{
  const live = fw.planFormWording_(liveState());
  check('the live forms: five changes, in order, nothing left as is',
        labelsOf(live.changes) === [WL.FEEDBACK_DESCRIPTION, WL.FEEDBACK_EMAIL, WL.ROSTER_DESCRIPTION, WL.CLUB_HELP,
                                    WL.REMOVE_HELP].join(' | ') && !live.skipped.length, labelsOf(live.changes));
  check('…only texts and one added question: never a title',
        live.changes.every(c => ['description', 'help', 'add-email'].includes(c.what)) &&
        live.changes.filter(c => c.what === 'add-email').length === 1);
  const email = live.changes.find(c => c.what === 'add-email');
  check('the reply-address question: exactly Q.FB_EMAIL, after the device question',
        email.title === WQ.FB_EMAIL && email.after === WQ.FB_DEVICE);
  check('the wanted wording: nothing to change (a second run is a no-op)',
        !fw.planFormWording_(wantedState()).changes.length && !fw.planFormWording_(wantedState()).skipped.length);

  let s = wantedState();
  s.roster.description = s.roster.description.replace(/\n/g, '\r\n') + '  ';
  s.roster.removeHelp = '  ' + W.REMOVE_HELP.replace(/ /g, '  ');
  check('only spacing or CRLF differs: nothing to change', !fw.planFormWording_(s).changes.length && !fw.planFormWording_(s).skipped.length);

  s = liveState();
  s.feedback.description = 'Tell us about problems with the forms.';
  s.roster.clubHelp = 'Your club name please';
  let p = fw.planFormWording_(s);
  check('a text edited by hand is left as is, listed with the suggested text',
        labelsOf(p.skipped) === WL.FEEDBACK_DESCRIPTION + ' | ' + WL.CLUB_HELP &&
        p.skipped[0].to === fw.feedbackDescription_(RF_URL) && /edited by hand/.test(p.skipped[0].reason) &&
        p.changes.length === 3, labelsOf(p.changes));

  s = liveState();
  s.roster.clubHelp = ''; s.roster.removeHelp = '   '; s.feedback.description = '';
  p = fw.planFormWording_(s);
  check('an empty text is ours to fill', p.changes.length === 5 && !p.skipped.length);

  s = wantedState();
  s.feedback.description = fw.feedbackDescription_('https://forms.example.org/old-roster/viewform');
  s.roster.description = fw.rosterDescription2026_08_('https://forms.example.org/old-problem/viewform');
  p = fw.planFormWording_(s);
  check('another form link (the wanted or the 2026-08 text): changed, not "edited by hand"',
        labelsOf(p.changes) === WL.FEEDBACK_DESCRIPTION + ' | ' + WL.ROSTER_DESCRIPTION && !p.skipped.length &&
        p.changes[0].to.endsWith(RF_URL) && p.changes[1].to.endsWith(FB_URL));

  s = liveState();
  s.feedback.items.push({ type: 'PARAGRAPH_TEXT', title: WQ.FB_EMAIL.toUpperCase() });
  p = fw.planFormWording_(s);
  check('a question under the reply title that is not a short answer: nothing added, a note',
        !p.changes.some(c => c.what === 'add-email') && labelsOf(p.skipped) === WL.FEEDBACK_EMAIL &&
        /not a short-answer question/.test(p.skipped[0].reason));
  s = liveState();
  s.feedback.items.push({ type: 'TEXT', title: 'Contact e-mail' });
  p = fw.planFormWording_(s);
  check('an e-mail question under another title: never a second one, "rename it" instead',
        !p.changes.some(c => c.what === 'add-email') && p.skipped.length === 1 &&
        p.skipped[0].reason.includes('"Contact e-mail"') && p.skipped[0].reason.includes('"' + WQ.FB_EMAIL + '"'));
  s = liveState();
  s.feedback.items = s.feedback.items.filter(it => it.title !== WQ.FB_DEVICE);
  check('no device question: the reply question goes at the end',
        fw.planFormWording_(s).changes.find(c => c.what === 'add-email').after === '');
  s = wantedState();
  s.feedback.items.splice(1, 0, s.feedback.items.pop());   // the reply question, not after the device one
  p = fw.planFormWording_(s);
  check('the reply question there but not right after the device question: left as is, "check its place"',
        !p.changes.length && labelsOf(p.skipped) === WL.FEEDBACK_EMAIL &&
        /not right after "/.test(p.skipped[0].reason) && /check its place/.test(p.skipped[0].reason), p.skipped.map(x => x.reason).join());
  s = wantedState();
  s.feedback.items = s.feedback.items.filter(it => it.title !== WQ.FB_DEVICE);
  check('…no device question: its place is not checked', !fw.planFormWording_(s).skipped.length);
  s = liveState();
  s.feedback.items.push({ type: 'TEXT', title: '' });   // a run that stopped before the title was set
  p = fw.planFormWording_(s);
  check('an untitled short-answer question and no reply question: nothing added, "give it the title … or delete it"',
        !p.changes.some(c => c.what === 'add-email') && labelsOf(p.skipped) === WL.FEEDBACK_EMAIL &&
        /untitled short-answer question/.test(p.skipped[0].reason) && p.skipped[0].reason.includes('"' + WQ.FB_EMAIL + '"'),
        labelsOf(p.changes));
  s = liveState();
  s.roster.clubHelp = null;
  p = fw.planFormWording_(s);
  check('a missing "Club name" question: left as is ("is it ours?"), nothing thrown',
        labelsOf(p.skipped) === WL.CLUB_HELP && /not on the form/.test(p.skipped[0].reason) && p.changes.length === 4);

  const text = fw.formWordingPreviewText_(live);
  check('the preview: numbered changes as now → new, the added question and its new column, the promise',
        /^Would change \(5\):/.test(text) && text.includes('1. ' + WL.FEEDBACK_DESCRIPTION) &&
        text.includes('   now: "' + W.CLUB_HELP_2026_08 + '"') && text.includes('   new: "' + W.CLUB_HELP + '"') &&
        text.includes('add the question "' + WQ.FB_EMAIL + '"') && text.includes('after "' + WQ.FB_DEVICE + '"') &&
        text.includes('The Feedback tab gets a new column') &&
        text.endsWith('No question title or answer is changed; the response tabs get no edit except the new reply ' +
                      'column noted above.') && !text.includes('the response tabs are not changed'),
        text.split('\n').pop());
  const noAdd = fw.planFormWording_(Object.assign(liveState(), { feedback: wantedState().feedback }));
  check('…without the added question: "Question titles, answers and the response tabs are not changed."',
        !noAdd.changes.some(c => c.what === 'add-email') && noAdd.changes.length === 3 &&
        fw.formWordingPreviewText_(noAdd).endsWith('\n\nQuestion titles, answers and the response tabs are not changed.'));
  s = liveState();
  s.roster.removeHelp = 'Names please';
  const skippedText = fw.formWordingPreviewText_(fw.planFormWording_(s));
  check('…and what is left as is, with the suggested text',
        skippedText.includes('Left as is (1):\n- ' + WL.REMOVE_HELP + ': edited by hand, so left as is.') &&
        skippedText.includes('Suggested text: "' + W.REMOVE_HELP + '"'));
  check('the preview key: the same plan matches, a changed "now" text does not',
        fw.formWordingKey_(live) === fw.formWordingKey_(fw.planFormWording_(liveState())) &&
        fw.formWordingKey_(live) !== fw.formWordingKey_(fw.planFormWording_(Object.assign(liveState(),
            { roster: Object.assign(liveState().roster, { clubHelp: '' }) }))));
}

console.log('\n  the menu run and a fresh build (FormApp, the UI, the lock and Audit stubbed)');
{
  const vm = require('vm');
  const src = ['Config.gs', 'Normalize.gs', 'Forms.gs']
      .map(f => fs.readFileSync(path.join(loadGs.GS_DIR, f), 'utf8')).join('\n');
  const ItemType = { TEXT: 'TEXT', PARAGRAPH_TEXT: 'PARAGRAPH_TEXT', LIST: 'LIST',
                     MULTIPLE_CHOICE: 'MULTIPLE_CHOICE', PAGE_BREAK: 'PAGE_BREAK' };
  // A fake form exposes only what the generators and the migration may call:
  // there is no deleteItem, deleteAllResponses, setDestination, setTitle on the
  // form, setAcceptingResponses… so calling one fails the run. `calls` records
  // every change made to a form, in order.
  const world = (opts) => {
    opts = opts || {};
    const calls = [], audits = [], dialogs = [], forms = {}, props = Object.assign({}, opts.props);
    let locks = 0;
    const makeForm = (id, description, items) => {
      const form = { id, description: description || '', items: [] };
      const note = what => {
        calls.push(id + '.' + what);
        if (opts.failOn === id + '.' + what) throw new Error('Forms service unavailable');
      };
      const makeItem = (type, title, help) => {
        const it = { type, title: title || '', help: help || '', validation: null };
        const api = {
          _it: it,
          getType: () => type, getTitle: () => it.title, getHelpText: () => it.help,
          getIndex: () => form.items.indexOf(api),
          setTitle: t => { note('setTitle'); it.title = t; return api; },
          setHelpText: h => { note('setHelpText'); it.help = h; return api; },
          setRequired: () => api, setChoiceValues: () => api, setChoices: () => api,
          setValidation: v => { note('setValidation'); it.validation = v; return api; },
          createChoice: (value, page) => ({ value, page }), setGoToPage: () => api,
          asListItem: () => api, asPageBreakItem: () => api,
        };
        return api;
      };
      const add = type => () => { note('add ' + type); const i = makeItem(type); form.items.push(i); return i; };
      form.api = {
        getId: () => id, getPublishedUrl: () => 'https://forms.example.org/' + id + '/viewform',
        getEditUrl: () => 'https://forms.example.org/' + id + '/edit',
        getDescription: () => form.description,
        setDescription: d => { note('setDescription'); form.description = d; return form.api; },
        getItems: t => form.items.filter(i => !t || i.getType() === t),
        addTextItem: add('TEXT'), addParagraphTextItem: add('PARAGRAPH_TEXT'), addListItem: add('LIST'),
        addMultipleChoiceItem: add('MULTIPLE_CHOICE'), addPageBreakItem: add('PAGE_BREAK'),
        moveItem: (from, to) => { note('moveItem'); const [x] = form.items.splice(from, 1); form.items.splice(to, 0, x); return x; },
        setCollectEmail: () => form.api, setLimitOneResponsePerUser: () => form.api,
        setAllowResponseEdits: () => form.api, setShowLinkToRespondAgain: () => form.api,
        setConfirmationMessage: () => form.api, setRequireLogin: () => form.api,
      };
      (items || []).forEach(([type, title, help]) => form.items.push(makeItem(type, title, help)));
      forms[id] = form;
      return form;
    };
    const ctx = vm.createContext({
      console,
      FormApp: {
        ItemType, PageNavigationType: { SUBMIT: 'SUBMIT', CONTINUE: 'CONTINUE' },
        createTextValidation: () => {
          const v = { requireTextIsEmail: () => { v.kind = 'email'; return v; },
                      requireNumber: () => { v.kind = 'number'; return v; }, build: () => ({ kind: v.kind }) };
          return v;
        },
        create: title => makeForm('new' + Object.keys(forms).length, '', []).api,
        openById: id => { if (!forms[id]) throw new Error('no form ' + id); return forms[id].api; },
      },
      PropertiesService: { getScriptProperties: () => ({ getProperty: k => props[k] || null,
                                                         setProperty: (k, v) => { props[k] = v; } }) },
      SpreadsheetApp: {
        getActive: () => ({}),
        getUi: () => ({
          alert: (title, text, buttons) => {
            dialogs.push(text);
            if (buttons !== 'YES_NO') return 'OK';
            const reply = (opts.replies || []).shift();
            return typeof reply === 'function' ? reply(forms) : reply;
          },
          Button: { YES: 'YES', NO: 'NO' }, ButtonSet: { YES_NO: 'YES_NO', OK: 'OK' } }),
      },
      LockService: { getDocumentLock: () => ({ tryLock: () => !opts.lockBusy, releaseLock: () => { locks++; } }) },
    });
    vm.runInContext(src, ctx);
    ctx.audit_ = (action, detail) => audits.push(action + ': ' + detail);
    return { ctx, calls, audits, dialogs, forms, props, locks: () => locks, makeForm };
  };
  // the two live forms as they are (2026-09-26 saved pages; the Club Roster Form shortened)
  const liveForms = (w, rosterEdits) => {
    w.makeForm('FEEDBACK', W.FEEDBACK_INTRO, LIVE_FEEDBACK_ITEMS);
    w.makeForm('ROSTER', fw.rosterDescription2026_08_('https://forms.example.org/FEEDBACK/viewform'), [
      ['MULTIPLE_CHOICE', WQ.ACTION], ['PAGE_BREAK', 'New club', 'One submission per club.'], ['LIST', WQ.PARTNER_NEW],
      ['PAGE_BREAK', 'The club'], ['TEXT', WQ.CLUB, (rosterEdits || {}).clubHelp || W.CLUB_HELP_2026_08],
      ['TEXT', WQ.MENTOR_EMAIL], ['PAGE_BREAK', 'Existing club'], ['LIST', WQ.PARTNER_MOD],
      ['PAGE_BREAK', 'The change'], ['PARAGRAPH_TEXT', WQ.ADD, 'Leave empty if nobody is joining.'],
      ['PARAGRAPH_TEXT', WQ.REMOVE, (rosterEdits || {}).removeHelp || W.REMOVE_HELP_2026_08],
      ['TEXT', WQ.MENTOR_EMAIL_MOD], ['PARAGRAPH_TEXT', WQ.NOTES]]);
  };
  const PROPS = { FORM_FEEDBACK_ID: 'FEEDBACK', FORM_ROSTER_ID: 'ROSTER' };
  const titles = f => f.items.map(i => i.getTitle());
  const ALLOWED = /^(FEEDBACK|ROSTER)\.(setDescription|setHelpText|add TEXT|setTitle|setValidation|moveItem)$/;

  let w = world({ props: PROPS, replies: ['YES'] });
  liveForms(w);
  const fbBefore = titles(w.forms.FEEDBACK), rfBefore = titles(w.forms.ROSTER);
  const made = w.ctx.migrateFormWording();
  const fbAfter = titles(w.forms.FEEDBACK);
  const added = w.forms.FEEDBACK.items[fbAfter.length - 1]._it;
  check('YES: five changes; the preview, then "Done … up to date"',
        made === 5 && w.dialogs.length === 2 && /^Would change \(5\):/.test(w.dialogs[0]) &&
        /^Done — 5 change\(s\); re-read: up to date\./.test(w.dialogs[1]), w.dialogs[1].split('\n')[0]);
  check('problem form: every earlier question kept, in order, same titles; the reply question after the device one',
        fbAfter.length === fbBefore.length + 1 && fbBefore.every((t, i) => fbAfter[i] === t) &&
        fbAfter[fbAfter.length - 1] === WQ.FB_EMAIL && fbAfter[fbAfter.length - 2] === WQ.FB_DEVICE &&
        added.type === 'TEXT' && added.validation && added.validation.kind === 'email');
  check('Club Roster Form: no question added or retitled; the two help texts and both descriptions are the new ones',
        titles(w.forms.ROSTER).join('|') === rfBefore.join('|') &&
        w.forms.ROSTER.items[4]._it.help === W.CLUB_HELP && w.forms.ROSTER.items[10]._it.help === W.REMOVE_HELP &&
        w.forms.ROSTER.description === fw.rosterDescription_('https://forms.example.org/FEEDBACK/viewform') &&
        w.forms.FEEDBACK.description === fw.feedbackDescription_('https://forms.example.org/ROSTER/viewform') &&
        w.forms.ROSTER.items[9]._it.help === 'Leave empty if nobody is joining.');
  check('only texts and one question were written (no delete, no destination, no response call exists)',
        w.calls.every(c => ALLOWED.test(c)) && w.calls.filter(c => c === 'FEEDBACK.setTitle').length === 1 &&
        !w.calls.some(c => c.startsWith('ROSTER.setTitle')), w.calls.join(', '));
  check('one Audit row naming the changes (labels only) and the re-read; the lock released',
        w.audits.length === 1 && w.audits[0] === 'migrateFormWording: changed: ' +
            [WL.FEEDBACK_DESCRIPTION, WL.FEEDBACK_EMAIL, WL.ROSTER_DESCRIPTION, WL.CLUB_HELP, WL.REMOVE_HELP].join('; ') +
            '; re-read: up to date' && w.locks() === 1, w.audits[0]);

  w.calls.length = 0; w.audits.length = 0; w.dialogs.length = 0;
  check('a second run: "Nothing to change", no write, no Audit row',
        w.ctx.migrateFormWording() === 0 && !w.calls.length && !w.audits.length &&
        w.dialogs.length === 1 && /^Nothing to change/.test(w.dialogs[0]));

  w = world({ props: PROPS, replies: ['NO'] });
  liveForms(w);
  w.ctx.migrateFormWording();
  check('NO: nothing written; one Audit row "cancelled at the preview"',
        !w.calls.length && w.audits.length === 1 &&
        w.audits[0].startsWith('migrateFormWording: cancelled at the preview (would have changed: ' + WL.FEEDBACK_DESCRIPTION));

  w = world({ props: PROPS, replies: [forms => { forms.ROSTER.items[4]._it.help = 'Typed in the editor meanwhile'; return 'YES'; }] });
  liveForms(w);
  w.ctx.migrateFormWording();
  check('the forms changed while the preview was open: nothing written, "run it again", Audit says so',
        !w.calls.length && /^Nothing was changed: the forms changed since the preview/.test(w.dialogs[1]) &&
        w.audits.join() === 'migrateFormWording: nothing changed: the forms changed since the preview' && w.locks() === 1);

  w = world({ props: PROPS, replies: ['YES'], lockBusy: true });
  liveForms(w);
  w.ctx.migrateFormWording();
  check('the lock busy: nothing written, no Audit row, "try again"',
        !w.calls.length && !w.audits.length && /Another GLOW operation is still running/.test(w.dialogs[1]));

  const flaky = { props: PROPS, replies: ['YES'], failOn: 'ROSTER.setDescription' };
  w = world(flaky);
  liveForms(w);
  w.ctx.migrateFormWording();
  check('a failure part-way: stops, says what landed, Audit "stopped after 2 of 5"; the lock released',
        /^Stopped after 2 of 5 change\(s\): Forms service unavailable/.test(w.dialogs[1]) &&
        w.audits.join() === 'migrateFormWording: stopped after 2 of 5 change(s) (done: ' + WL.FEEDBACK_DESCRIPTION +
            '; ' + WL.FEEDBACK_EMAIL + '): Forms service unavailable' && w.locks() === 1, w.audits.join());
  flaky.failOn = null; flaky.replies.push('YES');   // the service is back; run it again
  w.audits.length = 0; w.dialogs.length = 0;
  w.ctx.migrateFormWording();
  check('…run again: only the three still missing, no second reply question',
        /^Would change \(3\):/.test(w.dialogs[0]) && /re-read: up to date$/.test(w.audits.join()) &&
        titles(w.forms.FEEDBACK).filter(t => t === WQ.FB_EMAIL).length === 1, w.dialogs[0].split('\n')[0]);

  // a failure INSIDE the reply question's add (addTextItem, setTitle, setValidation, moveItem):
  // the question is on the form, maybe untitled, unvalidated or misplaced; no re-read sees a validation
  const partlyRun = (failOn, deviceMovedUp) => {
    const o = { props: PROPS, replies: ['YES'], failOn };
    const x = world(o);
    liveForms(x);
    if (deviceMovedUp) x.forms.FEEDBACK.items.splice(1, 0, x.forms.FEEDBACK.items.splice(5, 1)[0]);
    x.ctx.migrateFormWording();
    return { x, o };
  };
  const partlyAudit = 'migrateFormWording: stopped after 2 of 5 change(s) (done: ' + WL.FEEDBACK_DESCRIPTION + '; ' +
      WL.FEEDBACK_EMAIL_PARTLY + '): Forms service unavailable';
  const saysPartly = x => x.audits.join() === partlyAudit && x.dialogs[1].includes(WL.FEEDBACK_EMAIL_PARTLY) &&
      x.dialogs[1].includes('Response validation') && !x.dialogs[1].includes('it makes only the changes still missing');
  let pr1 = partlyRun('FEEDBACK.setTitle');
  check('setTitle fails: dialog and Audit say the reply question is PARTLY added (not "1 of 5 … run it again")',
        /PARTLY added/.test(WL.FEEDBACK_EMAIL_PARTLY) && saysPartly(pr1.x), pr1.x.audits.join());
  pr1.o.failOn = null; pr1.o.replies.push('YES');
  pr1.x.dialogs.length = 0;
  pr1.x.ctx.migrateFormWording();
  const fbItems = pr1.x.forms.FEEDBACK.items.map(i => i._it);
  check('…run again: no second question beside the untitled one; it is listed as left as is',
        fbItems.length === LIVE_FEEDBACK_ITEMS.length + 1 && !fbItems.some(i => i.title === WQ.FB_EMAIL) &&
        /^Would change \(3\):/.test(pr1.x.dialogs[0]) && pr1.x.dialogs[0].includes('untitled short-answer question'),
        pr1.x.dialogs[0].split('\n')[0] + ' / ' + fbItems.length + ' items');
  pr1 = partlyRun('FEEDBACK.setValidation');
  check('setValidation fails (the title is there): still PARTLY, so the missing validation is not taken for done',
        saysPartly(pr1.x), pr1.x.audits.join());
  pr1 = partlyRun('FEEDBACK.moveItem', true);
  check('moveItem fails: PARTLY added', saysPartly(pr1.x), pr1.x.audits.join());
  pr1.o.failOn = null; pr1.o.replies.push('YES');
  pr1.x.dialogs.length = 0; pr1.x.audits.length = 0;
  pr1.x.ctx.migrateFormWording();
  check('…run again: the misplaced question is listed as left as is ("check its place"), not taken for up to date',
        /Left as is \(1\):\n- /.test(pr1.x.dialogs[0]) && pr1.x.dialogs[0].includes('check its place') &&
        pr1.x.audits.join().includes('left as is: ' + WL.FEEDBACK_EMAIL), pr1.x.audits.join());
  pr1 = partlyRun('FEEDBACK.add TEXT');
  check('addTextItem itself fails: nothing landed, so not PARTLY; "run it again" as before',
        pr1.x.audits.join() === 'migrateFormWording: stopped after 1 of 5 change(s) (done: ' + WL.FEEDBACK_DESCRIPTION +
            '): Forms service unavailable' && pr1.x.dialogs[1].includes('it makes only the changes still missing'),
        pr1.x.audits.join());

  w = world({ props: PROPS, replies: ['YES'] });
  liveForms(w);
  const dev = w.forms.FEEDBACK.items.splice(5, 1)[0];
  w.forms.FEEDBACK.items.splice(1, 0, dev);   // the device question moved up by hand
  w.ctx.migrateFormWording();
  const order = titles(w.forms.FEEDBACK);
  check('the device question moved by hand: the reply question is placed right after it',
        order[1] === WQ.FB_DEVICE && order[2] === WQ.FB_EMAIL && w.calls.includes('FEEDBACK.moveItem'), order.join(' / '));

  w = world({ props: PROPS, replies: ['YES'] });
  liveForms(w, { removeHelp: 'Our own REMOVE wording' });
  w.ctx.migrateFormWording();
  check('a help text edited by hand: listed as left as is, kept, and named in the Audit row',
        /Left as is \(1\):/.test(w.dialogs[0]) && w.forms.ROSTER.items[10]._it.help === 'Our own REMOVE wording' &&
        w.audits[0].endsWith('; left as is: ' + WL.REMOVE_HELP + '; re-read: up to date'), w.audits[0]);

  w = world({ props: { FORM_FEEDBACK_ID: 'FEEDBACK' } });
  w.makeForm('FEEDBACK', W.FEEDBACK_INTRO, LIVE_FEEDBACK_ITEMS);
  w.ctx.migrateFormWording();
  check('a form missing: "run Create the Google Forms", nothing written, no Audit row',
        !w.calls.length && !w.audits.length && /do not exist yet/.test(w.dialogs[0]));

  // a saved form id that does not open (another Google account, a Forms outage) is not "no form yet"
  const noAccess = x => { x.ctx.FormApp.openById = () => { throw new Error('You do not have permission'); }; };
  w = world({ props: PROPS, replies: ['YES'] });
  liveForms(w);
  noAccess(w);
  w.ctx.migrateFormWording();
  check('the saved forms do not open: "could not open", "Do NOT run Create", nothing written, no Audit row',
        w.dialogs.length === 1 && w.dialogs[0].startsWith('Could not open the problem form and the Club Roster Form ' +
            'saved in Script Properties (FORM_FEEDBACK_ID, FORM_ROSTER_ID). Run this from the Google account that owns') &&
        w.dialogs[0].includes('Do NOT run "Create the Google Forms"') && !/do not exist yet/.test(w.dialogs[0]) &&
        !w.calls.length && !w.audits.length, w.dialogs[0]);
  w = world({ props: { FORM_ROSTER_ID: 'ROSTER' } });
  liveForms(w);
  const openRoster = w.ctx.FormApp.openById;
  w.ctx.FormApp.openById = id => { if (id === 'ROSTER') throw new Error('Forms service unavailable'); return openRoster(id); };
  w.ctx.migrateFormWording();
  check('…one saved form that does not open, the other never saved: the unopened one is named, not "Create"',
        /^Could not open the Club Roster Form saved in Script Properties \(FORM_ROSTER_ID\)/.test(w.dialogs[0]) &&
        w.dialogs[0].includes('Do NOT run'), w.dialogs[0]);
  w = world({ props: PROPS });
  liveForms(w);
  noAccess(w);
  w.ctx.showFormLinks();
  check('…"Show form links" says the same', /^Could not open the problem form and the Club Roster Form/.test(w.dialogs[0]) &&
        w.dialogs[0].includes('Do NOT run "Create the Google Forms"'), w.dialogs[0]);
  w = world({ props: PROPS });
  liveForms(w);
  noAccess(w);
  let createCalled = false;
  const create = w.ctx.FormApp.create;
  w.ctx.FormApp.create = t => { createCalled = true; return create(t); };
  w.ctx.syncFormChoices = () => 0;
  w.ctx.installTriggers = () => {};
  w.ctx.linkFormToSheet_ = () => null;
  w.ctx.createGlowForms();
  check('…and "Create the Google Forms" refuses: no new form, the saved ids kept, "Nothing was created"',
        !createCalled && w.props.FORM_FEEDBACK_ID === 'FEEDBACK' && w.props.FORM_ROSTER_ID === 'ROSTER' &&
        /^Nothing was created\. Could not open the problem form and the Club Roster Form/.test(w.dialogs[0]) &&
        !w.audits.length, w.dialogs[0]);

  w = world({ props: PROPS });
  liveForms(w);
  w.ctx.SpreadsheetApp.getUi = () => { throw new Error('no UI here'); };
  let refused = false;
  try { w.ctx.migrateFormWording(); } catch (e) { refused = /Run this from the sheet/.test(e.message); }
  check('from the script editor (no dialogs): refuses, nothing written', refused && !w.calls.length);

  // a fresh build says the same as a migrated form
  w = world({ props: {} });
  w.ctx.syncFormChoices = () => 0;
  w.ctx.installTriggers = () => {};
  w.ctx.linkFormToSheet_ = () => null;
  w.ctx.createGlowForms();
  const fb = w.ctx.FormApp.openById(w.props.FORM_FEEDBACK_ID), rf = w.ctx.FormApp.openById(w.props.FORM_ROSTER_ID);
  const fresh = w.ctx.planFormWording_(w.ctx.readFormWording_(fb, rf));
  const fbTitles = titles(w.forms[w.props.FORM_FEEDBACK_ID]);
  check('"Create the Google Forms": the migration finds nothing to change on a fresh build',
        !fresh.changes.length && !fresh.skipped.length, labelsOf(fresh.changes.concat(fresh.skipped)));
  check('…its problem form ends with the device question, then the reply question (e-mail validated)',
        fbTitles.slice(-2).join('|') === WQ.FB_DEVICE + '|' + WQ.FB_EMAIL &&
        w.forms[w.props.FORM_FEEDBACK_ID].items[fbTitles.length - 1]._it.validation.kind === 'email');
}

console.log('\n  the handler reads the filled-in one of two same-titled columns (FormHandlers.gs)');
{
  const rh = loadGs(['Q', 'responseFromValues_', 'responseKeyOf_'], ['Config.gs', 'Normalize.gs', 'FormHandlers.gs']);
  const HQ = rh.Q;
  const header = ['Timestamp', HQ.FB_FORM, HQ.FB_DEVICE, HQ.FB_EMAIL, HQ.FB_EMAIL + ' '];
  const row = (oldCol, newCol) => rh.responseFromValues_(header, ['2026-09-30 10:00:00', 'Africa Attendance Form', 'phone', oldCol, newCol], 'UTC');
  check('the re-added question\'s column to the right of the old one: its answer is read',
        row('', 'mentor@example.org').answers[HQ.FB_EMAIL] === 'mentor@example.org');
  check('…to the left of it: still read (a blank cell never replaces an answer)',
        rh.responseFromValues_([header[0], header[1], header[2], header[4], header[3]],
                               ['2026-09-30 10:00:00', 'Africa Attendance Form', 'phone', 'mentor@example.org', ''], 'UTC')
            .answers[HQ.FB_EMAIL] === 'mentor@example.org');
  check('an old row (answer in the old column): read too; both blank: blank',
        row('mentor@example.org', '').answers[HQ.FB_EMAIL] === 'mentor@example.org' && row('', '').answers[HQ.FB_EMAIL] === '');
  check('the FormLog key does not change with the second column',
        rh.responseKeyOf_('FEEDBACK', { text: 'x' }, row('', 'mentor@example.org').answers) ===
        rh.responseKeyOf_('FEEDBACK', { text: 'x' }, rh.responseFromValues_(header.slice(0, 4),
            ['2026-09-30 10:00:00', 'Africa Attendance Form', 'phone', 'mentor@example.org'], 'UTC').answers));
  const plainRow = rh.responseFromValues_(['Timestamp', 'a', 'b'], ['t', 'x', ''], 'UTC').answers;
  check('distinct titles: read as before', plainRow.a === 'x' && plainRow.b === '' && plainRow.Timestamp === 't');
}

// --------------------------------------------- real data, if available
const csvPath = process.env.CSV || path.join(REPO, 'data', 'enrollment_2026-08-24.csv');
if (fs.existsSync(csvPath) && path.basename(csvPath) === 'enrollment_2026-08-24.csv') {
  console.log('\nreal CSV — planClub_ over every club matches a fresh mint');
  const text = fs.readFileSync(csvPath, 'utf8').replace(/^﻿/, '');
  const rows = [];
  { let row = [], field = '', q = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (q) { if (c === '"' && text[i + 1] === '"') { field += '"'; i++; } else if (c === '"') q = false; else field += c; }
      else if (c === '"') q = true;
      else if (c === ',') { row.push(field); field = ''; }
      else if (c === '\n') { row.push(field); rows.push(row); row = []; field = ''; }
      else if (c !== '\r') field += c;
    }
    if (field || row.length) { row.push(field); rows.push(row); } }
  const hdr = rows[0].map(h => h.toLowerCase());
  const iP = hdr.findIndex(h => h.includes('partner organization name')),
        iC = hdr.findIndex(h => h.includes('club name')),
        iR = hdr.findIndex(h => h.includes('please list the full name'));
  const byId = {};
  for (let r = 1; r < rows.length; r++) {
    const row = rows[r];
    if (!row || row.length <= Math.max(iP, iC, iR)) continue;
    const p = gs.tidy_(row[iP]), c = gs.tidy_(row[iC]);
    if (!p || !c) continue;
    const parsed = gs.parseRoster_(row[iR]);
    if (!parsed.names.length) continue;
    byId[gs.key_(p) + '||' + gs.key_(c)] = { partner: p, club: c, names: parsed.names, duplicates: parsed.duplicates };
  }
  const st = freshState();
  let total = 0, allIds = new Set(), dupIssues = 0;
  for (const e of Object.values(byId)) {
    const p = gs.planClub_(e, [], st, 'X', '2026-08-26');
    total += p.toAppend.length;
    p.toAppend.forEach(r => allIds.add(r[col('girl_id')]));
    if (p.issues.some(i => i.issue === 'Same name listed twice')) dupIssues++;
  }
  check('6210 girls, all ids unique', total === 6210 && allIds.size === 6210, total + ' / ' + allIds.size);
  check('16 duplicate-name clubs flagged', dupIssues === 16, String(dupIssues));
}

console.log('\n' + (failures ? failures + ' FAILURES' : 'ALL CHECKS PASSED'));
process.exit(failures ? 1 : 0);
