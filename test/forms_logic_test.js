#!/usr/bin/env node
/**
 * Offline tests for the roster-change decisions in appsscript/RosterOps.gs —
 * the code behind the New Club Enrollment and Roster Modification forms —
 * and for FormHandlers.gs's FormLog keys and "Process any missed form
 * responses" plan. Runs the real .gs files in Node against a real club from
 * the enrollment CSV plus synthetic edge cases. No Google APIs involved.
 *
 *   node test/forms_logic_test.js   (the real-CSV section runs only if data/enrollment_2026-08-24.csv exists)
 */
const fs = require('fs');
const path = require('path');
const loadGs = require('./load_gs');

const REPO = path.resolve(__dirname, '..');
const gs = loadGs(['ROSTER_COLS', 'STATUS', 'tidy_', 'key_', 'parseRoster_', 'lastName_', 'clubCode_',
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
