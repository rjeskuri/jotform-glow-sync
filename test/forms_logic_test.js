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
        w.formLog[0] === 'Sunrise Club (' + ORG + '): 0 added, 2 reactivated, 1 removed, 1 kept removed (removed after it was sent)' &&
        w.audits.length === 1 && w.audits[0] === 'rosterChangeForm: ' + result && noGirls(w.audits.join('\n')), w.formLog[0]);
  const body = (w.mails[0] || { body: '' }).body;
  const kept = body.split('\n').indexOf('Not added back — they were removed from the roster after you sent this form. ' +
                                        'If one of them has rejoined the club, send the form again to add her:');
  check('the mentor e-mail lists her as the mentor typed her, under "Not added back"',
        w.mails.length === 1 && kept !== -1 && body.split('\n')[kept + 1] === '  - GRACE ZIBBLEWICK' &&
        !body.includes('Grace Zibblewick'), body);

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
  check('a Timestamp that is not a date: no sent day, so today\'s behaviour (the menu asks twice for such rows)',
        status(w, 2) === 'active|' && status(w, 4) === 'inactive|2026-09-28' && w.tabs.ReviewQueue.length === 1, result);

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
        result === 'existing club Sunrise Club (' + ORG + '): 0 girls added, 1 reactivated, 2 kept removed (removed after it was sent), 1 for review',
        result);
}

console.log('\n  guards');
{
  const all = fs.readdirSync(loadGs.GS_DIR).filter(f => f.endsWith('.gs'))
      .map(f => fs.readFileSync(path.join(loadGs.GS_DIR, f), 'utf8')).join('\n');
  const raised = [...new Set([...all.matchAll(/issue: '([^']+)'/g)].map(m => m[1]))].sort();
  check('every issue the code raises is in REVIEW_ISSUES (9)',
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
