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

console.log('\n  guards');
{
  const all = fs.readdirSync(loadGs.GS_DIR).filter(f => f.endsWith('.gs'))
      .map(f => fs.readFileSync(path.join(loadGs.GS_DIR, f), 'utf8')).join('\n');
  const raised = [...new Set([...all.matchAll(/issue: '([^']+)'/g)].map(m => m[1]))].sort();
  check('every issue the code raises is in REVIEW_ISSUES (8)',
        raised.join('|') === pr.REVIEW_ISSUES.slice().sort().join('|'), raised.join(' | '));
  const rb = fs.readFileSync(path.join(REPO, 'docs', 'RUNBOOK.md'), 'utf8');
  const section = (rb.split('## Working the ReviewQueue')[1] || '').split('\n## ')[0];
  const missing = pr.REVIEW_ISSUES.filter(i => !section.includes('**' + i + '**'));
  check('docs/RUNBOOK.md "Working the ReviewQueue" has a staff action for each', !missing.length, missing.join(' | '));
  const fhSrc = fs.readFileSync(path.join(loadGs.GS_DIR, 'FormHandlers.gs'), 'utf8');
  check('the weekly trigger calls sendSfPendingDigest by name, and it exists',
        /newTrigger\('sendSfPendingDigest'\)/.test(fhSrc) && /^function sendSfPendingDigest\(\)/m.test(fhSrc));
  const used = [...new Set(all.match(/\b(?:[A-Z]\w*App|[A-Z]\w*Service|Session|Utilities|Logger|Browser)\b(?=\s*\.)/g) || [])].sort().join(',');
  check('Google services unchanged (a new one adds an OAuth scope: CLAUDE.md rule 11)',
        used === 'FormApp,LockService,MailApp,PropertiesService,ScriptApp,SpreadsheetApp,UrlFetchApp,Utilities', used);
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
        text.endsWith('Question titles, answers and the response tabs are not changed.'));
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
