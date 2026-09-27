/**
 * What happens when one of the generated Google Forms is submitted.
 *
 * One installable trigger on the spreadsheet (installTriggers) routes every
 * form submission by the form it came from — never by tab name, so renaming
 * a tab cannot break it. Each response is processed once: FormLog records
 * what was done under a key for the response, and "Process any missed form
 * responses" catches anything a failed trigger left behind. A response whose
 * handler threw is logged as ERROR and can be retried from that menu item.
 *
 * Handlers re-derive what to do from the sheet's CURRENT state: safe to
 * retry soon after a failure, not safe to replay weeks later — an old
 * submission replayed today can put back girls removed since (2026-09-13).
 * So the menu item shows what it would run and asks first, never runs a row
 * FormLog already records as processed under another key, and asks again
 * before running Club Roster Form responses more than a week old
 * (docs/RUNBOOK.md, "Missed form responses").
 */

const FORM_LOG_COLS = ['when', 'form', 'sheet_row', 'response_key', 'result'];
const SF_PENDING_COLS = ['added', 'partner', 'club', 'region', 'girls', 'mentor_name',
                         'mentor_email', 'country', 'status', 'notes'];
const RETRY_PREFIXES = ['ERROR:'];   // FormLog results that mean "not done: try again"
const MISSED = {
  BUDGET_MS: 240000,     // stop STARTING rows this long after the menu item began (limit: 6 min)
  LOCK_WAIT_MS: 30000,   // per row; a form-submit trigger waits up to 120 s for the same lock
  PAUSE_MS: 500,         // between rows, so a waiting trigger can take the lock
  OLD_AFTER_DAYS: 7,     // older Club Roster Form responses need a second YES
  MAX_LISTED: 15,        // rows listed per preview
};

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

/**
 * Menu: run the responses that were never processed, or that failed.
 *
 * Reads everything first and changes nothing until confirmed: one YES/NO per
 * group — problem reports, then Club Roster Form responses, then (asked
 * separately, with a warning) Club Roster Form responses sent more than
 * MISSED.OLD_AFTER_DAYS ago. A row FormLog already records as processed under
 * a different key is never run from here ("held"; docs/RUNBOOK.md). The
 * document lock is taken one row at a time and never while a dialog is open,
 * so form submissions keep flowing; no row is started after MISSED.BUDGET_MS,
 * so the run ends inside Apps Script's 6-minute limit ("N left — run again").
 */
function processMissedResponses() {
  const started = Date.now();   // dialog time counts toward the 6-minute limit
  let ui = null;
  try { ui = SpreadsheetApp.getUi(); } catch (err) { /* script editor: no dialogs */ }
  if (!ui) {
    throw new Error('Run this from the sheet (GLOW → Google Forms → Process any missed ' +
                    'form responses): it shows what it would run and asks first.');
  }
  const snap = readMissedSnapshot_();
  const plan = planMissedRun_(snap.responses, snap.index, snap.today, MISSED.OLD_AFTER_DAYS);
  const heldText = plan.held.length ? '\n\n' + missedPreviewText_(
      'Not run — FormLog already has these as processed under a different key ' +
      '(docs/RUNBOOK.md, "Missed form responses"):', plan.held, MISSED.MAX_LISTED) : '';
  const sources = function (items) {
    return items.map(function (it) { return it.source; }).join(', ') || 'none';
  };
  const heldNote = plan.held.length ? '; held: ' + sources(plan.held) : '';
  if (!plan.run.length && !plan.old.length) {
    ui.alert('GLOW forms', 'Nothing to process.' + heldText, ui.ButtonSet.OK);
    return 0;
  }

  const confirmed = [], declined = [];
  const ask = function (items, title, question) {
    if (!items.length) return;
    const answer = ui.alert('GLOW forms', missedPreviewText_(title + ' (' + items.length + '):',
        items, MISSED.MAX_LISTED) + '\n\n' + question, ui.ButtonSet.YES_NO);
    Array.prototype.push.apply(answer === ui.Button.YES ? confirmed : declined, items);
  };
  const byForm = function (which) {
    return plan.run.filter(function (it) { return it.which === which; });
  };
  ask(byForm('FEEDBACK'), 'Problem reports not yet sent to staff', 'Send them to staff now?');
  ask(byForm('ROSTER'), 'Club Roster Form responses not yet processed', 'Process them now?');
  ask(plan.old, 'Club Roster Form responses sent more than ' + MISSED.OLD_AFTER_DAYS +
          ' days ago and never processed',
      'Running one now applies it to TODAY\'s roster: it can put back girls removed since ' +
      'it was sent. Run them anyway?');

  if (!confirmed.length) {
    audit_('processMissedResponses', 'cancelled at the preview (would have run ' +
           sources(plan.run.concat(plan.old)) + ')' + heldNote);
    if (heldText) ui.alert('GLOW forms', 'Nothing was run.' + heldText, ui.ButtonSet.OK);
    return 0;
  }
  if (Date.now() - started > MISSED.BUDGET_MS) {
    audit_('processMissedResponses', 'nothing run: the preview was open too long (' +
           sources(confirmed) + ')');
    ui.alert('GLOW forms', 'Nothing was run: the preview was open too long. Run it again.',
             ui.ButtonSet.OK);
    return 0;
  }
  audit_('processMissedResponses', 'started: ' + sources(confirmed) +
         (declined.length ? '; declined: ' + sources(declined) : '') + heldNote);

  const outcomes = [];
  for (let i = 0; i < confirmed.length; i++) {
    if (Date.now() - started > MISSED.BUDGET_MS) break;
    const lock = LockService.getDocumentLock();
    if (!lock.tryLock(MISSED.LOCK_WAIT_MS)) break;   // a submission is being processed
    try {
      outcomes.push(runConfirmed_(confirmed[i], snap));
    } finally {
      lock.releaseLock();
    }
    Utilities.sleep(MISSED.PAUSE_MS);
  }
  const left = confirmed.length - outcomes.length;
  audit_('processMissedResponses', 'finished: ' + (outcomes.join('; ') || 'nothing') +
         '; ' + left + ' left');
  ui.alert('GLOW forms', outcomes.length + ' processed' +
           (left ? ', ' + left + ' not started yet — run it again for the rest.' : '.') +
           '\n\n' + outcomes.join('\n') + heldText, ui.ButtonSet.OK);
  return outcomes.length;
}

/** One confirmed row, under the lock: re-checked against the sheet and FormLog first. */
function runConfirmed_(item, snap) {
  const sheet = snap.sheets[item.which];
  const r = readResponseRow_(sheet, item.row, snap.zone);
  if (!r || responseKeyOf_(item.which, r.stamp, r.answers) !== item.key) {
    return item.source + ' skipped (the row changed since the preview)';
  }
  if (responseDone_(item.which, r.stamp, r.answers, readFormLogIndex_())) {
    return item.source + ' skipped (processed meanwhile)';
  }
  const result = runResponse_(item.which, sheet, item.row, r.answers, item.key);
  return item.source + (isRetryResult_(result) ? ' failed again (see FormLog)' : ' ok');
}

/** Everything the menu item needs, read once: both response tabs and FormLog. */
function readMissedSnapshot_() {
  const zone = spreadsheetZone_();
  const sheets = {}, responses = [];
  ['FEEDBACK', 'ROSTER'].forEach(function (which) {
    const id = PropertiesService.getScriptProperties().getProperty(PROP[which + '_FORM']);
    const sheet = id && responseSheetFor_(id);
    if (!sheet || sheet.getLastRow() < 2) return;
    sheets[which] = sheet;
    const values = sheet.getRange(1, 1, sheet.getLastRow(), sheet.getLastColumn()).getValues();
    for (let i = 1; i < values.length; i++) {
      const r = responseFromValues_(values[0], values[i], zone);
      if (r) {
        responses.push({ which: which, row: i + 1, tab: sheet.getName(),
                         stamp: r.stamp, answers: r.answers });
      }
    }
  });
  return { zone: zone, sheets: sheets, responses: responses,
           index: readFormLogIndex_(), today: today_() };
}

/** Trigger path: process one new response unless FormLog says it was already done. */
function processResponseRow_(which, sheet, row) {
  const r = readResponseRow_(sheet, row, spreadsheetZone_());
  if (!r) return false;
  if (responseDone_(which, r.stamp, r.answers, readFormLogIndex_())) return false;
  runResponse_(which, sheet, row, r.answers, responseKeyOf_(which, r.stamp, r.answers));
  return true;
}

/** Run the handler for one response and record the outcome in FormLog. */
function runResponse_(which, sheet, row, answers, responseKey) {
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
  return result;
}

/** One response row as the handlers see it ({answers, stamp}), or null if the row is blank. */
function readResponseRow_(sheet, row, zone) {
  const width = sheet.getLastColumn();
  const header = sheet.getRange(1, 1, 1, width).getValues()[0];
  const values = sheet.getRange(row, 1, 1, width).getValues()[0];
  return responseFromValues_(header, values, zone);
}

function responseFromValues_(header, values, zone) {
  if (!values.some(function (v) { return tidy_(v); })) return null;
  const answers = {};
  header.forEach(function (h, i) { answers[tidy_(h)] = values[i]; });
  return { answers: answers, stamp: responseStamp_(values[0], zone) };
}

/**
 * The Timestamp cell as {wall, ms} — wall is its text in the SPREADSHEET's
 * time zone (the zone the cell's Date is read in), never the script's — or
 * {text} for anything that is not a date.
 */
function responseStamp_(timestamp, zone) {
  if (timestamp instanceof Date && !isNaN(timestamp.getTime())) {
    return { wall: Utilities.formatDate(timestamp, zone, RESPONSE_STAMP_FORMAT),
             ms: timestamp.getTime() };
  }
  return { text: tidy_(timestamp) };
}

function spreadsheetZone_() {
  return SpreadsheetApp.getActive().getSpreadsheetTimeZone();
}

/** FormLog, indexed (see indexFormLog_). */
function readFormLogIndex_() {
  const sheet = SpreadsheetApp.getActive().getSheetByName(TAB.FORM_LOG);
  if (!sheet || sheet.getLastRow() < 2) return indexFormLog_([]);
  // columns B-E: form, sheet_row, response_key, result
  return indexFormLog_(sheet.getRange(2, 2, sheet.getLastRow() - 1, 4).getValues());
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

// ------------------------------------------ response identity (pure)
// From here to formLogAdd_: plain logic, no Google services, tested offline
// in test/forms_logic_test.js. A stamp arrives as responseStamp_ built it,
// {wall, ms} or {text}; these functions never see a Date.

const RESPONSE_STAMP_FORMAT = 'yyyy-MM-dd HH:mm:ss.SSS';

/** True if a FormLog result means "not done: try again". */
function isRetryResult_(result) {
  const text = String(result == null ? '' : result);
  return RETRY_PREFIXES.some(function (p) { return text.indexOf(p) === 0; });
}

/** partner|club as the key spells them; a problem report puts its form there. */
function responseTail_(answers) {
  const partner = answers[Q.PARTNER_NEW] || answers[Q.PARTNER_MOD] || answers[Q.FB_FORM];
  return tidy_(partner) + '|' + tidy_(answers[Q.CLUB] || clubFromSections_(answers));
}

/**
 * The FormLog key for one response: form | the Timestamp in milliseconds |
 * partner | club. The milliseconds move when the spreadsheet's time zone
 * changes, so a changed key must never be taken to mean a new response:
 * planMissedRun_ holds any row FormLog already has as processed.
 */
function responseKeyOf_(which, stamp, answers) {
  const at = stamp.ms != null ? String(stamp.ms) : stamp.text;
  return which + '|' + at + '|' + responseTail_(answers);
}

/** The one 'Club (<partner>)' column that was answered on the Modification form. */
function clubFromSections_(answers) {
  let club = '';
  Object.keys(answers).forEach(function (title) {
    if (title.indexOf(Q.CLUB_PREFIX) === 0 && tidy_(answers[title])) club = tidy_(answers[title]);
  });
  return club;
}

/**
 * FormLog rows [form, sheet_row, response_key, result] (columns B-E), indexed:
 * done = keys that succeeded; okRows = 'form|sheet_row' that succeeded under
 * any key; errorsByKey / errorsByRow = the last failure text.
 */
function indexFormLog_(rows) {
  const index = { done: {}, okRows: {}, errorsByKey: {}, errorsByRow: {} };
  rows.forEach(function (r) {
    const key = String(r[2] == null ? '' : r[2]);
    if (!key) return;
    const rowKey = tidy_(r[0]) + '|' + tidy_(r[1]);
    if (isRetryResult_(r[3])) {
      index.errorsByKey[key] = index.errorsByRow[rowKey] = String(r[3]);
      return;
    }
    index.done[key] = true;
    index.okRows[rowKey] = true;
  });
  return index;
}

/** True if FormLog records this response as processed (a failure does not count). */
function responseDone_(which, stamp, answers, index) {
  return !!index.done[responseKeyOf_(which, stamp, answers)];
}

/**
 * What the menu item would do. responses: [{which, row, tab, stamp, answers}];
 * today: 'yyyy-MM-dd' in the spreadsheet's zone. Every response not done is
 *   held — FormLog has its form + sheet row as processed under another key
 *          (something re-keyed it, as the 2026-09-02 time-zone change did);
 *          never run from the menu;
 *   old  — a Club Roster Form response sent more than oldAfterDays ago (or
 *          with no readable date): needs its own YES;
 *   run  — the rest, status 'retry' (only failures logged) or 'new'.
 * Problem reports come first, then by sheet row.
 */
function planMissedRun_(responses, index, today, oldAfterDays) {
  const plan = { run: [], old: [], held: [] };
  responses.forEach(function (r) {
    if (responseDone_(r.which, r.stamp, r.answers, index)) return;
    const item = describeResponse_(r);
    const rowKey = r.which + '|' + r.row;
    item.key = responseKeyOf_(r.which, r.stamp, r.answers);
    if (index.okRows[rowKey]) {
      item.status = 'held';
      plan.held.push(item);
      return;
    }
    item.lastError = index.errorsByKey[item.key] || index.errorsByRow[rowKey] || '';
    item.status = item.lastError ? 'retry' : 'new';
    if (r.which === 'ROSTER' && !(daysBetween_(item.day, today) <= oldAfterDays)) {
      plan.old.push(item);
    } else {
      plan.run.push(item);
    }
  });
  const order = function (a, b) {
    return (a.which === b.which ? 0 : a.which === 'FEEDBACK' ? -1 : 1) || a.row - b.row;
  };
  plan.run.sort(order);
  plan.old.sort(order);
  plan.held.sort(order);
  return plan;
}

/**
 * What a preview may show about a response: when, which kind, and the club
 * (partner) — or, for a problem report, only the form it names. Never the
 * names in a roster or the free text of a report.
 */
function describeResponse_(r) {
  const a = r.answers;
  let kind, what;
  if (r.which === 'FEEDBACK') {
    kind = 'problem report';
    what = 'about the ' + (tidy_(a[Q.FB_FORM]) || '?');
  } else {
    const isNew = isNewClubResponse_(a);
    let partner = tidy_(isNew ? a[Q.PARTNER_NEW] : a[Q.PARTNER_MOD]);
    if (isNew && (!partner || partner === OTHER_PARTNER)) partner = tidy_(a[Q.NEW_PARTNER]);
    kind = isNew ? 'new club' : 'roster change';
    what = (tidy_(isNew ? a[Q.CLUB] : clubFromSections_(a)) || '?') + ' (' + (partner || '?') + ')';
  }
  const wall = r.stamp.wall || '';
  return { which: r.which, row: r.row, source: r.tab + '!' + r.row, kind: kind, what: what,
           day: wall.slice(0, 10), sent: wall ? wall.slice(0, 16) : (r.stamp.text || '?') };
}

/** A preview block: title, one line per row (at most maxListed), then "… and N more". */
function missedPreviewText_(title, items, maxListed) {
  const lines = [title];
  items.slice(0, maxListed).forEach(function (it) {
    lines.push('• row ' + it.row + ' · sent ' + it.sent + ' · ' + it.kind + ' · ' + it.what +
               (it.lastError ? ' · retry after ' + previewError_(it.lastError) : ''));
  });
  if (items.length > maxListed) lines.push('… and ' + (items.length - maxListed) + ' more');
  return lines.join('\n');
}

/** A failure text short enough for a dialog, with e-mail addresses blanked. */
function previewError_(text) {
  const t = tidy_(text).replace(/\S+@\S+/g, '<e-mail>');
  return t.length > 80 ? t.slice(0, 79) + '…' : t;
}

/** Whole days from one 'yyyy-MM-dd' to another; NaN if either is not a date. */
function daysBetween_(fromDay, toDay) {
  const utc = function (d) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(d || ''));
    return m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) : NaN;
  };
  return (utc(toDay) - utc(fromDay)) / 86400000;
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

  const formRegion = canonicalRegion_(a[Q.REGION]);   // '' unless exactly one of REGIONS
  const region = chooseRegion_(loadPartnerTabRegions_()[key_(partner)], formRegion,
                               derivedPartnerRegions_()[key_(partner)]);
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
  const formRegions = {};
  if (formRegion) formRegions[key_(partner)] = formRegion;
  seedPartners_(seen, formRegions);

  const issues = plan.issues;
  if (!region) {
    const issue = noRegionIssue_(partner);
    if (tidy_(a[Q.REGION])) {
      issue.detail += ' (Region answer ignored: "' + tidy_(a[Q.REGION]) +
          '" is not one of ' + REGIONS.join(', ') + ')';
    } else if (tidy_(a[Q.COUNTRY])) {
      issue.detail += ' (Country given: ' + tidy_(a[Q.COUNTRY]) + ')';
    }
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
  if (plan.toAppend.length || plan.reactivate.length) tryNotifySync_('newClubForm');
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
  if (plan.toAppend.length || plan.reactivate.length || plan.deactivate.length) {
    tryNotifySync_('rosterChangeForm');
  }
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
