/**
 * What happens when one of the generated Google Forms is submitted.
 *
 * One installable trigger on the spreadsheet (installTriggers) routes every
 * form submission by the form it came from — never by tab name, so renaming
 * a tab cannot break it. Each response is processed once: FormLog records
 * what was done, and "Process any missed form responses" catches anything a
 * failed trigger left behind. A response whose handler threw is logged as
 * ERROR and is retried by that menu item (every handler is safe to re-run:
 * it re-derives what to do from the sheet's current state).
 */

const FORM_LOG_COLS = ['when', 'form', 'sheet_row', 'response_key', 'result'];
const SF_PENDING_COLS = ['added', 'partner', 'club', 'region', 'girls', 'mentor_name',
                         'mentor_email', 'country', 'status', 'notes'];

function installTriggers() {
  const ss = SpreadsheetApp.getActive();
  ScriptApp.getProjectTriggers().forEach(function (t) {
    const fn = t.getHandlerFunction();
    if (fn === 'onAnyFormSubmit' || fn === 'sendSfPendingDigest') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('onAnyFormSubmit').forSpreadsheet(ss).onFormSubmit().create();
  ScriptApp.newTrigger('sendSfPendingDigest').timeBased()
      .onWeekDay(ScriptApp.WeekDay.MONDAY).atHour(8).create();
  audit_('installTriggers', 'form-submit router + weekly SF digest');
}

/** Installable on-form-submit trigger for the whole spreadsheet. */
function onAnyFormSubmit(e) {
  const lock = LockService.getDocumentLock();
  lock.waitLock(120000);
  try {
    const sheet = e.range.getSheet();
    const which = formKeyForSheet_(sheet);
    if (!which) {
      if (sheet.getFormUrl()) {
        audit_('onAnyFormSubmit', 'ignored a submission on "' + sheet.getName() +
               '": its form is not one of ours (or could not be opened by the trigger owner)');
      }
      return;
    }
    processResponseRow_(which, sheet, e.range.getRow());
  } finally {
    lock.releaseLock();
  }
}

/** 'ROSTER' | 'FEEDBACK' | null, by the sheet's linked form. */
function formKeyForSheet_(sheet) {
  const id = formIdOfSheet_(sheet);
  if (!id) return null;
  const props = PropertiesService.getScriptProperties();
  const keys = { ROSTER: PROP.ROSTER_FORM, FEEDBACK: PROP.FEEDBACK_FORM };
  for (const k in keys) if (props.getProperty(keys[k]) === id) return k;
  return null;
}

/** Menu: run every unprocessed (or failed) response of both forms. */
function processMissedResponses() {
  const lock = LockService.getDocumentLock();
  lock.waitLock(120000);
  let done = 0;
  try {
    ['ROSTER', 'FEEDBACK'].forEach(function (which) {
      const id = PropertiesService.getScriptProperties().getProperty(PROP[which + '_FORM']);
      const sheet = id && responseSheetFor_(id);
      if (!sheet || sheet.getLastRow() < 2) return;
      for (let row = 2; row <= sheet.getLastRow(); row++) {
        if (processResponseRow_(which, sheet, row)) done++;
      }
    });
  } finally {
    lock.releaseLock();
  }
  SpreadsheetApp.getActive().toast(done + ' response(s) processed', 'GLOW forms', 8);
  return done;
}

/** Process one response row unless FormLog says it was already done. */
function processResponseRow_(which, sheet, row) {
  const width = sheet.getLastColumn();
  const header = sheet.getRange(1, 1, 1, width).getValues()[0];
  const values = sheet.getRange(row, 1, 1, width).getValues()[0];
  if (!values.some(function (v) { return tidy_(v); })) return false;
  const answers = {};
  header.forEach(function (h, i) { answers[tidy_(h)] = values[i]; });
  const responseKey = responseKey_(which, values[0], answers);
  if (formLogHas_(responseKey)) return false;

  const source = sheet.getName() + '!' + row;
  let result;
  try {
    if (which === 'FEEDBACK') result = handleFeedback_(answers, source);
    else if (isNewClubResponse_(answers)) result = handleNewClub_(answers, source);
    else result = handleRosterChange_(answers, source);
  } catch (err) {
    result = 'ERROR: ' + err.message;
    review_([{ issue: 'Form response could not be processed', partner: '', club: '',
               detail: source + ': ' + err.message + ' — fix the cause, then run ' +
                   '"Process any missed form responses".', dedupeKey: source }]);
  }
  formLogAdd_(which, row, responseKey, result);
  return true;
}

/**
 * Which branch of the Club Roster Form was used. The page-1 answer decides;
 * if it is somehow blank, a filled-in club name means the new-club branch.
 */
function isNewClubResponse_(answers) {
  const action = tidy_(answers[Q.ACTION]);
  if (action) return key_(action) === key_(Q.ACTION_NEW);
  return !!tidy_(answers[Q.CLUB]);
}

/**
 * A stable identity for one response: form + the timestamp in milliseconds
 * (not its text, which depends on the time zone) + partner + club.
 */
function responseKey_(which, timestamp, answers) {
  const stamp = (timestamp instanceof Date) ? String(timestamp.getTime()) : tidy_(timestamp);
  const partner = answers[Q.PARTNER_NEW] || answers[Q.PARTNER_MOD] || answers[Q.FB_FORM];
  return which + '|' + stamp + '|' + tidy_(partner) +
      '|' + tidy_(answers[Q.CLUB] || clubFromSections_(answers));
}

/** The one 'Club (<partner>)' column that was answered on the Modification form. */
function clubFromSections_(answers) {
  let club = '';
  Object.keys(answers).forEach(function (title) {
    if (title.indexOf(Q.CLUB_PREFIX) === 0 && tidy_(answers[title])) club = tidy_(answers[title]);
  });
  return club;
}

/** True if this response was processed successfully before (errors are retried). */
function formLogHas_(responseKey) {
  const sheet = SpreadsheetApp.getActive().getSheetByName(TAB.FORM_LOG);
  if (!sheet || sheet.getLastRow() < 2) return false;
  const rows = sheet.getRange(2, 4, sheet.getLastRow() - 1, 2).getValues();
  return rows.some(function (r) {
    return r[0] === responseKey && String(r[1]).indexOf('ERROR:') !== 0;
  });
}

function formLogAdd_(which, row, responseKey, result) {
  ensureTab_(SpreadsheetApp.getActive(), TAB.FORM_LOG, FORM_LOG_COLS)
      .appendRow([now_(), which, row, responseKey, result]);
}

// ------------------------------------------------------------ New club
function handleNewClub_(a, source) {
  const ss = SpreadsheetApp.getActive();
  let partner = tidy_(a[Q.PARTNER_NEW]);
  const typed = tidy_(a[Q.NEW_PARTNER]);
  if (!partner || partner === OTHER_PARTNER) partner = typed;
  const club = tidy_(a[Q.CLUB]);
  const parsed = parseRoster_(a[Q.ROSTER]);
  if (!partner || !club || !parsed.names.length) {
    // logged as ERROR so it is retried once staff fill in the response row
    throw new Error('incomplete submission: missing ' +
        (!partner ? 'partner' : !club ? 'club name' : 'roster'));
  }

  const regions = loadPartnerRegions_();
  const region = regions[key_(partner)] || '';
  const existing = loadRoster_();
  const state = loadIdState_();
  const today = today_();
  const current = existing.byClub[key_(partner) + '||' + key_(club)] || [];
  const isNew = !current.length;

  const plan = planClub_({ partner: partner, club: club, names: parsed.names,
                           duplicates: parsed.duplicates, source: source },
                         current, state, region, today);
  applyRosterPlan_(ss, plan, today);
  saveClubRegistry_(state.registry);
  const seen = {}; seen[key_(partner)] = partner;
  seedPartners_(seen);

  const issues = plan.issues;
  if (!region) {
    const issue = noRegionIssue_(partner);
    if (tidy_(a[Q.COUNTRY])) issue.detail += ' (Country given: ' + tidy_(a[Q.COUNTRY]) + ')';
    issues.push(issue);
  }
  if (String(a[Q.SAME_NAME]).toLowerCase().indexOf('y') === 0 && !parsed.duplicates.length) {
    issues.push({ issue: 'Partner says two girls share a name', partner: partner, club: club,
                  detail: 'Their note: ' + tidy_(a[Q.SAME_NAME_DETAIL]) +
                      ' — the roster has no repeated name, so check the girls are listed distinctly.' });
  }
  review_(issues);

  if (isNew) {
    ensureTab_(ss, TAB.SF_PENDING, SF_PENDING_COLS).appendRow([
      today, partner, club, region, plan.toAppend.length, tidy_(a[Q.MENTOR_NAME]),
      tidy_(a[Q.MENTOR_EMAIL]), tidy_(a[Q.COUNTRY]), 'pending', '']);
  }
  trySyncChoices_();

  const summary = (isNew ? 'new club ' : 'existing club ') + club + ' (' + partner + '): ' +
      plan.toAppend.length + ' girls added, ' + plan.reactivate.length + ' reactivated, ' +
      issues.length + ' for review';
  audit_('newClubForm', summary);
  return summary;
}

// ------------------------------------------------------ Roster change
function handleRosterChange_(a, source) {
  const ss = SpreadsheetApp.getActive();
  const partner = tidy_(a[Q.PARTNER_MOD]);
  const club = clubFromSections_(a);
  const adds = parseRoster_(a[Q.ADD]);
  const removes = parseRoster_(a[Q.REMOVE]);
  const mentorEmail = tidy_(a[Q.MENTOR_EMAIL_MOD]);
  if (!partner || !club) throw new Error('incomplete submission: no partner/club chosen');
  if (!adds.names.length && !removes.names.length) return 'nothing to do (no names given)';

  const existing = loadRoster_();
  const current = existing.byClub[key_(partner) + '||' + key_(club)] || [];
  if (!current.length) {
    review_([{ issue: 'Roster change for a club not on file', partner: partner, club: club,
               detail: source + ': no girls are enrolled under this partner + club. ' +
                   'If it is a new club, it needs the New Club Enrollment form.',
               dedupeKey: source }]);
    return 'skipped: club not on file';
  }
  const state = loadIdState_();
  const today = today_();
  const activeRow = current.filter(function (r) { return r.status === STATUS.ACTIVE; })[0];
  const region = loadPartnerRegions_()[key_(partner)] ||
      (activeRow ? tidy_(activeRow.region) : '') || '';

  const plan = planModification_({ partner: partner, club: club, adds: adds.names,
                                   removes: removes.names, duplicates: adds.duplicates,
                                   source: source },
                                 current, state, region, today);
  applyRosterPlan_(ss, plan, today);
  saveClubRegistry_(state.registry);
  if (plan.toAppend.length && !region) plan.issues.push(noRegionIssue_(partner));
  review_(plan.issues);
  trySyncChoices_();

  const summary = club + ' (' + partner + '): ' + plan.toAppend.length + ' added, ' +
      plan.reactivate.length + ' reactivated, ' + plan.deactivate.length + ' removed' +
      (plan.alreadyActive.length ? ', ' + plan.alreadyActive.length + ' already on the roster' : '') +
      (plan.alreadyInactive.length ? ', ' + plan.alreadyInactive.length + ' already removed' : '') +
      (plan.unmatched.length ? ', ' + plan.unmatched.length + ' removal(s) did not match' : '');
  audit_('rosterChangeForm', summary);
  if (mentorEmail) sendChangeConfirmation_(mentorEmail, club, partner, plan);
  return summary;
}

/**
 * Tell the mentor what happened. Only names THEY typed are echoed back —
 * never other girls from the roster (the address is whatever was typed into
 * a public form, so "did you mean" suggestions stay in the staff-only
 * ReviewQueue).
 */
function sendChangeConfirmation_(to, club, partner, plan) {
  const names = function (rows) { return rows.map(function (r) { return r.full_name; }); };
  const section = function (title, list) {
    if (!list.length) return;
    lines.push(title);
    list.forEach(function (n) { lines.push('  - ' + n); });
  };
  const lines = ['Thank you. Here is what changed for ' + club + ' (' + partner + '):', ''];
  section('Added:', plan.toAppend.map(function (r) { return r[ROSTER_COLS.indexOf('full_name')]; }));
  section('Back on the roster:', names(plan.reactivate));
  section('Removed:', names(plan.deactivate));
  section('Already on the roster (no change):', plan.alreadyActive);
  section('Already removed earlier (no change):', plan.alreadyInactive);
  section('Listed under both ADD and REMOVE — kept on the roster:', plan.keptBoth);
  if (plan.unmatched.length) {
    lines.push('', 'We could NOT find these names on the roster, so nobody was removed for them:');
    plan.unmatched.forEach(function (u) { lines.push('  - ' + u.name); });
    lines.push('Our team will check these with you. If you know the enrolled spelling, ' +
               'you can simply submit the form again.');
  }
  lines.push('', 'The attendance form updates within the hour.');
  try {
    MailApp.sendEmail({ to: to, subject: 'GLOW roster change received – ' + club,
                        body: lines.join('\n') });
  } catch (err) {
    audit_('sendChangeConfirmation_', 'could not email ' + to + ': ' + err.message);
  }
}

// ------------------------------------------------------------- Feedback
function handleFeedback_(a, source) {
  const staff = PropertiesService.getScriptProperties().getProperty(PROP.STAFF_EMAIL);
  if (!staff) {
    // thrown on purpose: logged as ERROR, so the report is sent once the
    // address is configured and "Process any missed form responses" runs
    throw new Error('STAFF_NOTIFY_EMAIL is not set in Script Properties');
  }
  const body = [
    'A problem report arrived via "' + FORM_TITLES.FEEDBACK + '" (' + source + ').', '',
    'Form:        ' + tidy_(a[Q.FB_FORM]),
    'Partner:     ' + tidy_(a[Q.FB_PARTNER]),
    'Club:        ' + tidy_(a[Q.FB_CLUB]),
    'Device:      ' + tidy_(a[Q.FB_DEVICE]),
    'Reply to:    ' + tidy_(a[Q.FB_EMAIL]), '',
    'Trying to do:', tidy_(a[Q.FB_DOING]) || '(not given)', '',
    'What happened:', tidy_(a[Q.FB_WHAT]),
  ].join('\n');
  const opts = { to: staff, subject: 'GLOW form problem: ' + tidy_(a[Q.FB_FORM]), body: body };
  if (tidy_(a[Q.FB_EMAIL])) opts.replyTo = tidy_(a[Q.FB_EMAIL]);
  MailApp.sendEmail(opts);   // a quota/send failure throws → ERROR → retried later
  audit_('feedbackForm', 'emailed ' + staff + ' about ' + tidy_(a[Q.FB_FORM]));
  return 'emailed staff';
}

// ---------------------------------------------------- Salesforce digest
/** Weekly: list clubs still waiting to become Salesforce Accounts. */
function sendSfPendingDigest() {
  const sheet = SpreadsheetApp.getActive().getSheetByName(TAB.SF_PENDING);
  if (!sheet || sheet.getLastRow() < 2) return;
  const rows = sheet.getRange(2, 1, sheet.getLastRow() - 1, SF_PENDING_COLS.length).getValues()
      .filter(function (r) { return key_(r[SF_PENDING_COLS.indexOf('status')]) === 'pending'; });
  if (!rows.length) return;
  const staff = PropertiesService.getScriptProperties().getProperty(PROP.STAFF_EMAIL);
  if (!staff) {
    audit_('sendSfPendingDigest', rows.length + ' pending but STAFF_NOTIFY_EMAIL is not set');
    return;
  }
  const lines = [rows.length + ' new club(s) are waiting to be created in Salesforce ' +
                 '(tab "' + TAB.SF_PENDING + '"). Set status to "done" once created.', ''];
  rows.forEach(function (r) {
    lines.push('- ' + r[2] + ' | ' + r[1] + ' | ' + (r[3] || 'region?') + ' | ' + r[4] +
               ' girls | mentor ' + r[5] + ' <' + r[6] + '> | added ' + r[0]);
  });
  MailApp.sendEmail({ to: staff, subject: 'GLOW: ' + rows.length + ' club(s) pending in Salesforce',
                      body: lines.join('\n') });
  audit_('sendSfPendingDigest', 'emailed ' + staff + ' about ' + rows.length + ' club(s)');
}

/** Keep the dropdowns current after a change; never let it fail a submission. */
function trySyncChoices_() {
  try { syncFormChoices(); } catch (err) { audit_('syncFormChoices', 'failed: ' + err.message); }
}
