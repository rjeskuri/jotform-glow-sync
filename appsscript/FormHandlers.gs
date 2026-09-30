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
 * retry soon after a failure, not safe to replay weeks later. An old
 * submission replayed today put back 20 girls removed since (2026-09-13);
 * it no longer can — each handler passes the day the response was sent and
 * RosterOps.gs keeps anyone removed after that day removed (the replay
 * guard, docs/plans/2026-09-28-replay-guard.md; a response with no readable
 * sent day is refused, see runResponse_) — but its removals and new names
 * still apply to today's roster. So the menu item shows what it would
 * run and asks first, never runs a row FormLog already records as processed
 * under another key, and asks again before running Club Roster Form
 * responses more than a week old (docs/RUNBOOK.md, "Missed form responses").
 *
 * A new-club response that may duplicate a club on file is HELD instead
 * (FormLog "HELD: …", a ReviewQueue item, nothing imported): not done, never
 * offered by the menu item until staff start that item's resolved cell with
 * "release" (docs/plans/2026-09-28-duplicate-club-guard.md). So is a new
 * club whose name another partner's club already has (SAME_NAME_ISSUE): a
 * release of that one is refused until the response row's club name is one
 * nobody else has (docs/plans/2026-09-30-same-name-intake.md).
 */

const FORM_LOG_COLS = ['when', 'form', 'sheet_row', 'response_key', 'result'];
const SF_PENDING_COLS = ['added', 'partner', 'club', 'region', 'girls', 'mentor_name',
                         'mentor_email', 'country', 'status', 'notes'];
const RETRY_PREFIXES = ['ERROR:'];   // FormLog results that mean "not done: try again"
const HOLD_PREFIX = 'HELD:';         // "not done: held for staff" — offered only once released
const HOLD_ISSUE = 'New club held as a possible duplicate';   // its ReviewQueue issue
/** …or, when its name is another partner's club's: a new club may not take a name in use. */
const SAME_NAME_ISSUE = 'Club name already used by another partner — ask for a different name';
const HOLD_ISSUES = [HOLD_ISSUE, SAME_NAME_ISSUE];   // the items a held response is released by
/**
 * An issue as holdDecisions_ compares it: capitals and spacing ignored, and
 * any dash (a hyphen, two hyphens, an en or em dash) is one dash — an item
 * added back by hand is typed on a keyboard that has no long dash.
 */
function issueKey_(s) {
  return key_(s).replace(/\s*[-\u2010-\u2015\u2212]+\s*/g, ' - ');
}
/** Why runResponse_ refuses a Club Roster Form response with no sent day (FormLog ERROR, queued). */
const NO_SENT_DAY_ERROR = 'its Timestamp cell is not a date, so the day it was sent is unknown ' +
    'and the replay guard cannot run: enter the change fresh on the Club Roster Form instead ' +
    '(docs/RUNBOOK.md, "Form response could not be processed")';
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
  audit_('installTriggers', 'form-submit router + Monday e-mail (ReviewQueue + SF Pending)');
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
 * a different key is never run from here ("held"; docs/RUNBOOK.md), nor is
 * a new club held for review until staff release it in the ReviewQueue —
 * released ones get a YES/NO of their own; one resolved another way is only
 * named (closedHoldsText_). The
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
  const plan = planMissedRun_(snap.responses, snap.index, snap.today, MISSED.OLD_AFTER_DAYS, snap.holds);
  const heldText = (plan.held.length ? '\n\n' + missedPreviewText_(
      'Not run — FormLog already has these as processed under a different key ' +
      '(docs/RUNBOOK.md, "Missed form responses"):', plan.held, MISSED.MAX_LISTED) : '') +
      (plan.waiting.length ? '\n\n' + missedPreviewText_(
      'Not run — new clubs held for review (a possible duplicate, or a club name another ' +
      'partner\'s club has), until staff start the ReviewQueue item\'s resolved cell with ' +
      '"release" (docs/RUNBOOK.md, "Working the ReviewQueue"):', plan.waiting, MISSED.MAX_LISTED) : '') +
      (plan.closed.length ? '\n\n' + closedHoldsText_(plan.closed, MISSED.MAX_LISTED) : '');
  const sources = function (items) {
    return items.map(function (it) { return it.source; }).join(', ') || 'none';
  };
  const heldNote = (plan.held.length ? '; held: ' + sources(plan.held) : '') +
      (plan.waiting.length ? '; held for review: ' + sources(plan.waiting) : '');
  if (!plan.run.length && !plan.old.length && !plan.released.length) {
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
  ask(byForm('FEEDBACK'), 'Problem reports not yet sent to staff',
      'Send them to staff now? (Any that ask for a roster change also go to the ReviewQueue.)');
  ask(byForm('ROSTER'), 'Club Roster Form responses not yet processed', 'Process them now?');
  ask(plan.released, 'New clubs held for review that staff released in the ReviewQueue',
      'Run them now, as sent? Each runs against TODAY\'s roster (girls removed since it was ' +
      'sent stay removed); the duplicate check is skipped (an organization typed close to a ' +
      'partner on file, or a club name another partner\'s club has, is still refused).');
  ask(plan.old, 'Club Roster Form responses sent more than ' + MISSED.OLD_AFTER_DAYS +
          ' days ago and never processed',
      'Running one now applies it to TODAY\'s roster: girls removed since it was sent stay ' +
      'removed (the ReviewQueue lists them), but its removals and new names still apply. ' +
      'Run them anyway?');
  confirmed.sort(missedOrder_);   // asked in groups, run in sheet order: a change needs its enrollment

  if (!confirmed.length) {
    audit_('processMissedResponses', 'cancelled at the preview (would have run ' +
           sources(plan.run.concat(plan.released, plan.old)) + ')' + heldNote);
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
    const wait = Math.max(0, Math.min(MISSED.LOCK_WAIT_MS, MISSED.BUDGET_MS - (Date.now() - started)));
    if (!lock.tryLock(wait)) break;   // a submission is being processed, or out of time
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
  const index = readFormLogIndex_();
  if (responseDone_(item.which, r.stamp, r.answers, index)) {
    return item.source + ' skipped (processed meanwhile)';
  }
  // a held response runs only as released, and only while its item still says so
  const held = heldForReview_(item.which, r.stamp, item.key, index);
  if (held && !(item.status === 'released' &&
                releasedBy_(readHoldDecisions_(snap.zone)[item.source], r.stamp))) {
    return item.source + ' skipped (held for review; its ReviewQueue item does not say release)';
  }
  const result = runResponse_(item.which, sheet, item.row, r.answers, item.key, held);
  return item.source + (isRetryResult_(result) ? ' failed again (see FormLog)'
      : isHeldResult_(result) ? ' held for review (see ReviewQueue)' : ' ok');
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
           index: readFormLogIndex_(), today: today_(), holds: readHoldDecisions_(zone) };
}

/** holdDecisions_ over the ReviewQueue. */
function readHoldDecisions_(zone) {
  return holdDecisions_(readReviewRows_(zone));
}

/** Trigger path: process one new response unless FormLog says it was already done. */
function processResponseRow_(which, sheet, row) {
  const r = readResponseRow_(sheet, row, spreadsheetZone_());
  if (!r) return false;
  const index = readFormLogIndex_();
  const key = responseKeyOf_(which, r.stamp, r.answers);
  // held for staff counts too: a repeated trigger must not hold (and e-mail) twice
  if (responseDone_(which, r.stamp, r.answers, index) || heldForReview_(which, r.stamp, key, index)) {
    return false;
  }
  runResponse_(which, sheet, row, r.answers, key);
  return true;
}

/**
 * Run the handler for one response and record the outcome in FormLog. The
 * Club Roster Form handlers get the day the response was sent (its
 * Timestamp's wall-clock day, from the key), so a retry or a late run never
 * puts back girls removed since. A Club Roster Form response whose Timestamp
 * is not a date has no such day and is refused (ERROR, queued): run without
 * the guard it could put them back, and the menu's warning for old rows
 * promises it cannot (the rule submittedDay_ follows).
 * released: staff released this held new-club response (the duplicate check
 * is skipped, except a typed organization close to a partner on file and a
 * club name another partner's club has: see handleNewClub_); the replay
 * guard still applies.
 */
function runResponse_(which, sheet, row, answers, responseKey, released) {
  const source = sheet.getName() + '!' + row;
  const sent = sentDayOfKey_(responseKey);
  let result;
  try {
    if (which === 'FEEDBACK') result = handleFeedback_(answers, source, responseKey);
    else if (!sent) throw new Error(NO_SENT_DAY_ERROR);
    else if (isNewClubResponse_(answers)) {
      result = handleNewClub_(answers, source, responseKey, !!released, sent);
    } else result = handleRosterChange_(answers, source, sent);
  } catch (err) {
    result = 'ERROR: ' + err.message;
    // a text Timestamp fails the same way on every retry: the change is entered fresh instead
    tryReview_([{ issue: 'Form response could not be processed', partner: '', club: '',
                  detail: source + ': ' + err.message + (err.message === NO_SENT_DAY_ERROR
                      ? ' — then set its FormLog result to "resolved by hand by <name> <date>" ' +
                        'so the menu stops offering it.'
                      : ' — fix the cause, then run "Process any missed form responses".'),
                  dedupeKey: source }], source);
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
  header.forEach(function (h, i) {
    const title = tidy_(h);
    // A question deleted and re-added under the same title leaves two columns
    // with one header (the problem form's reply e-mail, 2026-09-28): the
    // filled-in cell wins, whichever column Google put first.
    if (!Object.prototype.hasOwnProperty.call(answers, title) || tidy_(values[i])) {
      answers[title] = values[i];
    }
  });
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
const QUARTER_HOUR_MS = 15 * 60 * 1000;          // every UTC offset is whole quarter-hours
const MAX_ZONE_SHIFT_MS = 26 * 60 * 60 * 1000;   // UTC-12 … UTC+14
const WALL_KEY = /^([A-Z]+)\|(w:[^|]*)\|/;       // which|w:<wall>|…
const LEGACY_KEY = /^([A-Z]+)\|(\d+)\|([\s\S]*)$/;   // which|<ms>|partner|club (before 2026-09-27)

/** True if a FormLog result means "not done: try again". */
function isRetryResult_(result) {
  const text = String(result == null ? '' : result);
  return RETRY_PREFIXES.some(function (p) { return text.indexOf(p) === 0; });
}

/** True if a FormLog result means "not done: held for staff" (a possible duplicate, or a name in use). */
function isHeldResult_(result) {
  return String(result == null ? '' : result).indexOf(HOLD_PREFIX) === 0;
}

/**
 * True if FormLog has this response held for staff: by its Timestamp text
 * (a later edit of its club cell does not lose it), or its whole key for a
 * stamp that is not a date.
 */
function heldForReview_(which, stamp, key, index) {
  return stamp.wall != null ? !!index.heldStamps[which + '|w:' + stamp.wall] : !!index.heldByKey[key];
}

/** 'yyyy-MM-dd HH:mm:ss' a response was sent — what a hold's ReviewQueue item records. */
function sentAtOfStamp_(stamp) {
  return (stamp.wall || '').slice(0, 19) || '?';
}

/** The same, from a FormLog key ('?' for a key that carries no wall time). */
function sentAtOfKey_(responseKey) {
  const m = WALL_KEY.exec(String(responseKey || ''));
  return m ? m[2].slice(2, 21) : '?';
}

/** True if a hold decision (holdDecisions_) releases the response sent at `stamp`. */
function releasedBy_(decision, stamp) {
  return !!decision && decision.state === 'release' && decision.sentAt === sentAtOfStamp_(stamp);
}

/** partner|club as the key spells them; a problem report puts its form there. */
function responseTail_(answers) {
  const partner = answers[Q.PARTNER_NEW] || answers[Q.PARTNER_MOD] || answers[Q.FB_FORM];
  return tidy_(partner) + '|' + tidy_(answers[Q.CLUB] || clubFromSections_(answers));
}

/**
 * The FormLog key for one response: form | w:<the Timestamp cell's own text,
 * to the millisecond, in the spreadsheet's zone> | partner | club.
 *
 * The cell stores wall-clock time, so its text survives a change of the
 * spreadsheet's time zone. Its getTime() does not: it moved by 4 h when the
 * zone changed on 2026-09-02, and keys built from it made 11 old responses
 * look new on 2026-09-13. Keys written before this change (which|<ms>|…)
 * still count — see responseDone_.
 */
function responseKeyOf_(which, stamp, answers) {
  const at = stamp.wall != null ? 'w:' + stamp.wall : stamp.text;
  return which + '|' + at + '|' + responseTail_(answers);
}

/**
 * True if two getTime() readings can be one Timestamp cell read under two
 * time zones: they differ by whole quarter-hours, by at most 26 h.
 */
function sameCellAcrossZones_(msNow, msLogged) {
  const d = Math.abs(msNow - msLogged);
  return d <= MAX_ZONE_SHIFT_MS && d % QUARTER_HOUR_MS === 0;
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
 * done = keys that succeeded; stamps = 'which|w:<wall>' that succeeded;
 * legacy = 'which|partner|club' → the milliseconds of old keys that
 * succeeded; okRows = 'form|sheet_row' that succeeded under any key;
 * errorsByKey / errorsByRow = the last failure text since any hold;
 * heldByKey / heldStamps = responses held for staff (HELD:), by key and by
 * 'which|w:<wall>'.
 */
function indexFormLog_(rows) {
  const index = { done: {}, stamps: {}, legacy: {}, okRows: {}, errorsByKey: {}, errorsByRow: {},
                  heldByKey: {}, heldStamps: {} };
  rows.forEach(function (r) {
    const key = String(r[2] == null ? '' : r[2]);
    if (!key) return;
    const rowKey = tidy_(r[0]) + '|' + tidy_(r[1]);
    if (isHeldResult_(r[3])) {
      index.heldByKey[key] = String(r[3]);
      const w = key.match(WALL_KEY);
      if (w) index.heldStamps[w[1] + '|' + w[2]] = String(r[3]);
      delete index.errorsByKey[key];     // failures before the hold are over
      delete index.errorsByRow[rowKey];
      return;
    }
    if (isRetryResult_(r[3])) {
      index.errorsByKey[key] = index.errorsByRow[rowKey] = String(r[3]);
      return;
    }
    index.done[key] = true;
    index.okRows[rowKey] = true;
    let m = key.match(WALL_KEY);
    if (m) {
      index.stamps[m[1] + '|' + m[2]] = true;
    } else if ((m = key.match(LEGACY_KEY))) {
      const tail = m[1] + '|' + m[3];
      (index.legacy[tail] = index.legacy[tail] || []).push(Number(m[2]));
    }
  });
  return index;
}

/**
 * True if FormLog records this response as processed (a failure does not
 * count): a key with the same form and Timestamp text — the stamp alone, so
 * editing a partner or club cell later cannot make it look new — or a key
 * from before 2026-09-27 with the same form, partner and club whose
 * milliseconds are this cell's under some other time zone.
 */
function responseDone_(which, stamp, answers, index) {
  if (stamp.wall == null) return !!index.done[responseKeyOf_(which, stamp, answers)];
  if (index.stamps[which + '|w:' + stamp.wall]) return true;
  return (index.legacy[which + '|' + responseTail_(answers)] || []).some(function (ms) {
    return sameCellAcrossZones_(stamp.ms, ms);
  });
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
 * A new club FormLog has as held for review (HELD:) goes by its ReviewQueue
 * item — holds: holdDecisions_, the item's sent time must be this row's:
 *   released — the item's resolved cell says "release": asked on its own;
 *   waiting  — open, or no item for this row and time: listed, never run;
 *   closed   — resolved any other way: never run, only named on one line
 *              (closedHoldsText_), so a release typed another way shows.
 * Problem reports come first, then by sheet row.
 */
function planMissedRun_(responses, index, today, oldAfterDays, holds) {
  holds = holds || {};
  const plan = { run: [], old: [], held: [], waiting: [], released: [], closed: [] };
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
    if (heldForReview_(r.which, r.stamp, item.key, index)) {
      const d = holds[item.source];
      const mine = !!d && d.sentAt === sentAtOfStamp_(r.stamp);
      if (mine && d.state === 'closed') {
        item.status = 'closed';
        item.note = 'ReviewQueue row ' + d.row;
        plan.closed.push(item);
        return;
      }
      if (releasedBy_(d, r.stamp)) {
        item.status = 'released';
        item.note = 'released in ReviewQueue row ' + d.row;
        plan.released.push(item);
      } else {
        item.status = 'waiting';
        item.lastError = '';
        item.note = mine ? 'waiting for staff: ReviewQueue row ' + d.row
                         : 'no ReviewQueue item for this row and time (docs/RUNBOOK.md)';
        plan.waiting.push(item);
      }
      return;
    }
    item.status = item.lastError ? 'retry' : 'new';
    if (r.which === 'ROSTER' && !(daysBetween_(item.day, today) <= oldAfterDays)) {
      plan.old.push(item);
    } else {
      plan.run.push(item);
    }
  });
  [plan.run, plan.old, plan.held, plan.waiting, plan.released, plan.closed].forEach(function (list) {
    list.sort(missedOrder_);
  });
  return plan;
}

/** Problem reports first, then by sheet row (a roster change must run after its enrollment). */
function missedOrder_(a, b) {
  return (a.which === b.which ? 0 : a.which === 'FEEDBACK' ? -1 : 1) || a.row - b.row;
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
               (it.lastError ? ' · retry after ' + previewError_(it.lastError) : '') +
               (it.note ? ' · ' + it.note : ''));
  });
  if (items.length > maxListed) lines.push('… and ' + (items.length - maxListed) + ' more');
  return lines.join('\n');
}

/**
 * The preview's one line for held new clubs whose ReviewQueue item was
 * resolved without "release" (plan.closed): never run, but named, so a
 * release typed another way ("Released", "ok release") cannot silently
 * leave a club out. Response rows and ReviewQueue rows only.
 */
function closedHoldsText_(items, maxListed) {
  const rows = items.slice(0, maxListed).map(function (it) { return 'row ' + it.row + ' (' + it.note + ')'; });
  if (items.length > maxListed) rows.push('… and ' + (items.length - maxListed) + ' more');
  return 'Not imported — new clubs held for review whose ReviewQueue item was resolved without ' +
      '"release" (to import one, start that resolved cell with "release" and run this again): ' +
      rows.join(', ');
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

/**
 * ', N kept removed' for a summary, or '' (counts only: summaries reach FormLog
 * and Audit). No reason given: a girl whose removal day is blank is kept too.
 */
function keptRemovedNote_(plan) {
  const n = (plan.keptRemoved || []).length;
  return n ? ', ' + n + ' kept removed' : '';
}

// ------------------------------------------------------------ New club
// Typed answers pass sheetText_ / parseFormRoster_ before they reach the
// sheet (a leading = would be a formula); the partner dropdown's value is
// ours and is used as chosen. A response that may duplicate a club on file
// is held for staff (newClubHoldReasons_) unless they released it; a release
// still refuses (ERROR) a typed organization close to a partner on file, and
// a club name another partner's club has (a new club may not take a name in
// use: docs/plans/2026-09-30-same-name-clubs.md, Ryan's decision 2).
/** submitted: 'yyyy-MM-dd' the response was sent ('' = no guard: runResponse_ refuses first). */
function handleNewClub_(a, source, responseKey, released, submitted) {
  const ss = SpreadsheetApp.getActive();
  let partner = tidy_(a[Q.PARTNER_NEW]);
  const typed = sheetText_(a[Q.NEW_PARTNER]);
  const typedPartner = !partner || partner === OTHER_PARTNER;
  if (typedPartner) partner = typed;
  const club = sheetText_(a[Q.CLUB]);
  const parsed = parseFormRoster_(a[Q.ROSTER]);
  if (!partner || !club || !parsed.names.length) {
    // logged as ERROR so it is retried once staff fill in the response row
    throw new Error('incomplete submission: missing ' +
        (!partner ? 'partner' : !club ? 'club name' : 'roster'));
  }

  const existing = loadRoster_();
  const reasons = newClubHoldReasons_({ partner: partner, club: club, names: parsed.names,
                                        typedPartner: typedPartner },
                                      existing.rows, loadPartnerNames_());
  if (!released) {
    if (reasons.length) return holdNewClub_(a, source, responseKey, partner, club, reasons);
  } else {
    // a release skips the check, except the typed organization: run as typed
    // it would file the club under a second spelling of a partner on file
    // (no region, a second form section — the "ion bu" case, 2026-09-24) —
    // and except a name another partner's club has: imported, the Jotform
    // sync would refuse to add the club and the forms would never show it
    const blocking = reasons.filter(function (r) { return !!RELEASE_STEPS[r.kind]; });
    if (blocking.length) {
      throw new Error('release refused: ' + blocking.map(function (r) { return r.text; }).join('; ') +
          '. First, ' + blocking.map(function (r) { return RELEASE_STEPS[r.kind](); }).join('; and ') + '.');
    }
  }

  const formRegion = canonicalRegion_(a[Q.REGION]);   // '' unless exactly one of REGIONS
  const region = chooseRegion_(loadPartnerTabRegions_()[key_(partner)], formRegion,
                               derivedPartnerRegions_()[key_(partner)]);
  const state = loadIdState_();
  const today = today_();
  const current = existing.byClub[key_(partner) + '||' + key_(club)] || [];
  const isNew = !current.length;

  const plan = planClub_({ partner: partner, club: club, names: parsed.names,
                           duplicates: parsed.duplicates, source: source,
                           submitted: submitted },
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
      today, partner, club, region, plan.toAppend.length, sheetText_(a[Q.MENTOR_NAME]),
      sheetText_(a[Q.MENTOR_EMAIL]), sheetText_(a[Q.COUNTRY]), 'pending', '']);
  }
  trySyncChoices_();

  const summary = (isNew ? 'new club ' : 'existing club ') + club + ' (' + partner + '): ' +
      plan.toAppend.length + ' girls added, ' + plan.reactivate.length + ' reactivated' +
      keptRemovedNote_(plan) + ', ' + issues.length + ' for review' +
      (released ? ' (released from hold by staff)' : '');
  audit_('newClubForm', summary);
  if (plan.toAppend.length || plan.reactivate.length) tryNotifySync_('newClubForm');
  return summary;
}

/** How a hold reason reads in Audit, and (all but samename) in FormLog: holdSummary_. */
const HOLD_KINDS = { reenroll: 're-enrollment list', names: 'names on file', club: 'club name',
                     partner: 'organization name', samename: 'another partner\'s club name' };
/** What staff do before releasing an 'organization name' hold (its item, and a refused release). */
function orgHoldStep_() {
  return 'if it is that partner, set the response row\'s "' + Q.PARTNER_NEW + '" cell to it ' +
      'exactly as the Partners tab spells it; if it is another organization, add it to the ' +
      'Partners tab with its region';
}
/** What staff do before releasing a same-name hold (its item, and a refused release). */
function sameNameHoldStep_() {
  return 'ask the partner for a different name and set the response row\'s "' + Q.CLUB +
      '" cell to it';
}
/** The reasons a release never skips → what staff do first. */
const RELEASE_STEPS = { partner: orgHoldStep_, samename: sameNameHoldStep_ };
/** True if a hold is (also) for a club name another partner's club has. */
function isSameNameHold_(reasons) {
  return reasons.some(function (r) { return r.kind === 'samename'; });
}
/**
 * A hold in FormLog, after HOLD_PREFIX: 'possible duplicate (<kinds>)',
 * 'club name already used by another partner', or both — never a name.
 */
function holdSummary_(reasons) {
  const kinds = reasons.filter(function (r) { return r.kind !== 'samename'; })
      .map(function (r) { return HOLD_KINDS[r.kind] || r.kind; }).join(', ');
  return [isSameNameHold_(reasons) ? 'club name already used by another partner' : '',
          kinds ? 'possible duplicate (' + kinds + ')' : ''].filter(String).join('; ');
}

/**
 * Hold a new-club response for staff: one ReviewQueue item, then a short
 * e-mail to the mentor, then Audit — nothing else is written, no dropdown
 * refresh, no Jotform sync. If the ReviewQueue write fails this throws: the
 * response is logged ERROR, retried from the menu, and the mentor has not
 * been e-mailed yet. Returns the FormLog result ('HELD: …').
 */
function holdNewClub_(a, source, responseKey, partner, club, reasons) {
  review_([heldClubReviewItem_(partner, club, source, sentAtOfKey_(responseKey), reasons)]);
  const to = sheetText_(a[Q.MENTOR_EMAIL]);
  if (to) sendHoldNotice_(to, club, partner, source);
  const kinds = reasons.map(function (r) { return HOLD_KINDS[r.kind] || r.kind; }).join(', ');
  audit_('newClubForm', 'held ' + source + ' for review (' + kinds + '); nothing imported');
  return HOLD_PREFIX + ' ' + holdSummary_(reasons) + ' — ReviewQueue [#' + source + ']';
}

/**
 * Tell the mentor the enrollment arrived and is being checked. Echoes only
 * the club and partner they sent — never a club or a girl from the Roster
 * (the address is whatever was typed into a public form). Never fails the
 * handler; a failure goes to Audit without the address.
 */
function sendHoldNotice_(to, club, partner, source) {
  const body = [
    'Thank you. We received the enrollment of ' + club + ' (' + partner + ').', '',
    'Before adding the girls, our team is checking it against the clubs already enrolled. ' +
        'You do not need to do anything, and please do not send it again: we will add the ' +
        'club, or contact you if we have a question.', '',
    'The girls appear on the attendance form once the club is added.',
  ].join('\n');
  try {
    MailApp.sendEmail({ to: to, subject: 'GLOW enrollment received – ' + club, body: body });
  } catch (err) {
    audit_('sendHoldNotice_', 'could not e-mail the mentor about ' + source + ': ' + previewError_(err.message));
  }
}

// ------------------------------------------------------ Roster change
/** submitted: 'yyyy-MM-dd' the response was sent ('' = no guard: runResponse_ refuses first). */
function handleRosterChange_(a, source, submitted) {
  const ss = SpreadsheetApp.getActive();
  const partner = tidy_(a[Q.PARTNER_MOD]);
  const club = clubFromSections_(a);
  const adds = parseFormRoster_(a[Q.ADD]);        // written to the Roster: sheet-safe
  const removes = parseRoster_(a[Q.REMOVE]);      // only matched against it
  const mentorEmail = tidy_(a[Q.MENTOR_EMAIL_MOD]);
  if (!partner || !club) throw new Error('incomplete submission: no partner/club chosen');
  if (!adds.names.length && !removes.names.length) return 'nothing to do (no names given)';

  const existing = loadRoster_();
  const current = existing.byClub[key_(partner) + '||' + key_(club)] || [];
  if (!current.length) {
    review_([{ issue: 'Roster change for a club not on file', partner: partner, club: club,
               detail: source + ': no girls are enrolled under this partner + club, so nothing ' +
                   'changed and the mentor got no confirmation. Look for the club under another ' +
                   'name or partner (renamed or moved?); a new club needs "' + Q.ACTION_NEW + '".',
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
                                   source: source, submitted: submitted },
                                 current, state, region, today);
  applyRosterPlan_(ss, plan, today);
  saveClubRegistry_(state.registry);
  if (plan.toAppend.length && !region) plan.issues.push(noRegionIssue_(partner));
  review_(plan.issues);
  trySyncChoices_();

  const summary = club + ' (' + partner + '): ' + plan.toAppend.length + ' added, ' +
      plan.reactivate.length + ' reactivated, ' + plan.deactivate.length + ' removed' +
      keptRemovedNote_(plan) +
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
  // the names as the mentor typed them, never the Roster's spelling; no claim about WHEN she
  // was removed (the Roster may not record the day)
  section('Not added back — they are marked removed on the roster. ' +
          'If one of them has rejoined the club, send the form again to add her:',
          (plan.keptRemoved || []).map(function (k) { return k.name; }));
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
/**
 * E-mail staff a problem report. One that looks like a roster change also
 * becomes a ReviewQueue item ("Roster change sent as a problem report"),
 * because an e-mail alone was never followed up (2026-09-27 review).
 */
function handleFeedback_(a, source, responseKey) {
  const staff = PropertiesService.getScriptProperties().getProperty(PROP.STAFF_EMAIL);
  if (!staff) {
    // thrown on purpose: logged as ERROR, so the report is sent once the
    // address is configured and "Process any missed form responses" runs
    throw new Error('STAFF_NOTIFY_EMAIL is not set in Script Properties');
  }
  // Queued BEFORE the e-mail: review_ skips an item already open under the
  // same tag, so a retry after a failed send adds no second row — the e-mail
  // is the one step that must not repeat.
  const reason = looksLikeRosterChange_(a);
  const replyTo = replyAddress_(a[Q.FB_EMAIL]);
  const queued = !!reason &&
      tryReview_([feedbackReviewItem_(a, source, sentDayOfKey_(responseKey), reason)], source);
  const note = !reason ? '' : queued
      ? 'Staff note: looks like a roster change; on the ReviewQueue as ' + source + '.'
      : 'Staff note: looks like a roster change, but it could NOT be added to the ' +
        'ReviewQueue (see Audit) — add it by hand.';
  const body = [
    'A problem report arrived via "' + FORM_TITLES.FEEDBACK + '" (' + source + ').', '',
    'Form:        ' + tidy_(a[Q.FB_FORM]),
    'Partner:     ' + tidy_(a[Q.FB_PARTNER]),
    'Club:        ' + tidy_(a[Q.FB_CLUB]),
    'Device:      ' + tidy_(a[Q.FB_DEVICE]),
    'Reply to:    ' + tidy_(a[Q.FB_EMAIL]) + (tidy_(a[Q.FB_EMAIL]) && !replyTo
        ? ' (not an e-mail address, so not set as Reply-To)' : ''), '',
    'Trying to do:', tidy_(a[Q.FB_DOING]) || '(not given)', '',
    'What happened:', tidy_(a[Q.FB_WHAT]),
  ].concat(note ? ['', note] : []).join('\n');
  const opts = { to: staff, subject: 'GLOW form problem: ' + tidy_(a[Q.FB_FORM]), body: body };
  if (replyTo) opts.replyTo = replyTo;
  MailApp.sendEmail(opts);   // a quota/send failure throws → ERROR → retried later
  audit_('feedbackForm', 'emailed ' + staff + ' about ' + tidy_(a[Q.FB_FORM]) +
         (!reason ? '' : queued ? '; ReviewQueue [#' + source + ']'
                                : '; roster change, ReviewQueue write FAILED'));
  return 'emailed staff' +
      (!reason ? '' : queued ? '; roster change queued' : '; roster change NOT queued (see Audit)');
}

/**
 * The typed reply address, or '' when it does not look like one. The box's
 * e-mail validation can be missing (a wording run that stopped part-way,
 * docs/RUNBOOK.md "Google Forms wording"), and a non-address as Reply-To
 * could fail the staff e-mail on every retry.
 */
function replyAddress_(v) {
  const t = tidy_(v);
  return /^[^\s@<>(),;:"]+@[^\s@<>(),;:"]+\.[^\s@<>(),;:".]+$/.test(t) ? t : '';
}

/** review_ that never fails its caller: true if the items are on the ReviewQueue. */
function tryReview_(items, source) {
  try {
    review_(items);
    return true;
  } catch (err) {
    // issue names and the source only — never partner, club or detail
    audit_('tryReview_', 'could not add ' + items.length + ' item(s) (' +
           items.map(function (i) { return i.issue; }).join('; ') + ') for ' + source + ': ' +
           err.message);
    return false;
  }
}

// ------------------------------------ problem reports and the ReviewQueue (pure)
// Tested offline in test/forms_logic_test.js; the back-fill tool
// (tools/backfill_feedback_review.py) runs these same functions.

/** Every issue the ReviewQueue can hold, in the order the weekly e-mail lists them. */
const REVIEW_ISSUES = [
  HOLD_ISSUE, SAME_NAME_ISSUE, 'Roster change sent as a problem report', 'Removal did not match anyone',
  'Removed girls not put back by an older response',
  'Same name listed twice', 'Partner says two girls share a name',
  'Girls missing from the latest enrollment', 'Roster change for a club not on file',
  'Partner has no region', 'Form response could not be processed',
];
const OTHER_ISSUE = 'Other (added by hand)';
const DIGEST = { MAX_PER_ISSUE: 10, NEW_DAYS: 7 };

// "Is this report a roster change?" — a keyword heuristic, checked against the
// 11 reports of 2026-09 (docs/plans/2026-09-28-problem-report-followup.md).
// Singular "name", "missing", "moved", "leave" are left out on purpose: they
// flag page and club problems ("my club is missing from the list").
const RC_PEOPLE = /\b(?:girls?|members?|students?|names|roster|list|(?:to|from) (?:our|the|my|this) (?:club|group)|ninas?|chicas?|integrantes|participantes|nombres|lista)\b/;
const RC_CHANGE = /\b(?:add(?:ed|ing)?|remov(?:e|ed|ing|al)|join(?:ed|ing|s)?|left|chang(?:e|ed|es|ing)|reduc(?:e|ed|es|ing|tion)|updated|up to date|agreg\w*|anadi\w*|quitar\w*|elimin\w*|se fue(?:ron)?|cambi\w*|actualizad[ao]s?)\b/;
const RC_NEW = /\bnew (?:girls?|members?|students?|names)\b|\bnuev[ao]s? (?:ninas?|chicas?|integrantes|participantes)\b|\b(?:ninas?|chicas?|integrantes|participantes) nuev[ao]s?\b/;

/** Report text as the patterns read it: lower case, accents folded (so \b sees "anadio"). */
function foldText_(s) {
  return foldKey_(s);
}

/**
 * Why a problem report looks like a roster change: 'form' (it names the Club
 * Roster Form), 'text' (its words ask to add or remove girls) or '' (it does
 * not). A miss still reaches staff by e-mail; a false alarm is resolved
 * "not a roster change" (docs/RUNBOOK.md, "Working the ReviewQueue").
 */
function looksLikeRosterChange_(a) {
  if (key_(a[Q.FB_FORM]).indexOf('roster form') !== -1) return 'form';
  let text = foldText_(tidy_(a[Q.FB_DOING]) + ' ' + tidy_(a[Q.FB_WHAT]));
  const club = foldText_(a[Q.FB_CLUB]);
  if (club.length >= 4) text = text.split(club).join(' ');   // "<X> Girls Club" is no roster word
  return RC_NEW.test(text) || (RC_PEOPLE.test(text) && RC_CHANGE.test(text)) ? 'text' : '';
}

/**
 * The ReviewQueue item for a roster change sent as a problem report. It points
 * at the report (source) and never copies its text or reply address: reports
 * name girls. Partner and club are what the mentor typed, capped, with any
 * leading run of = + - @ and spaces stripped (sheetText_) so the sheet never reads a formula.
 */
function feedbackReviewItem_(a, source, sentDay, reason) {
  const typed = function (v) { return sheetText_(v).slice(0, 80); };
  return {
    issue: 'Roster change sent as a problem report',
    partner: typed(a[Q.FB_PARTNER]), club: typed(a[Q.FB_CLUB]),
    detail: source + ' (sent ' + (sentDay || '?') + '; ' +
        (reason === 'form' ? 'Club Roster Form chosen' : 'report text') + '): enter it on ' +
        'the Club Roster Form → "' + Q.ACTION_MOD + '", removals spelled exactly as on the ' +
        'Roster — or ask the partner to. Then mark resolved.',
    dedupeKey: source,
  };
}

/**
 * The ReviewQueue item for a held new-club response (holdNewClub_). Partner
 * and club are as filed (sheet-safe); the reasons name clubs, partners and
 * counts, never a girl. "(sent …)" and the tag are how holdDecisions_ finds
 * it again — staff must not edit them. An 'organization name' hold also says
 * what to fix before a release (orgHoldStep_; handleNewClub_ refuses until then).
 * A hold for a name another partner's club has (alone or with other reasons)
 * is SAME_NAME_ISSUE: it may still be that club sent under the wrong partner,
 * so the item says that first — and that a club on file under the wrong
 * partner is moved, then released with its name unchanged (the response
 * then runs as that existing club) — then the new name a release needs.
 */
function heldClubReviewItem_(partner, club, source, sentAt, reasons) {
  const org = reasons.some(function (r) { return r.kind === 'partner'; });
  const head = source + ' (sent ' + (sentAt || '?') + '): nothing imported; the mentor was told it ' +
      'is being checked. Why: ' + reasons.map(function (r) { return r.text; }).join('; ') + '. ';
  const release = 'resolved "release <date> by <name>: …"';
  if (isSameNameHold_(reasons)) {
    return {
      issue: 'Club name already used by another partner — ask for a different name',
      partner: partner, club: club,
      detail: head + 'That club, sent under the wrong partner (or another club on file): enter ' +
          'only its new girls on "' + Q.ACTION_MOD + '" for the club on file, then resolve. ' +
          'That club, and the Roster has it under the wrong partner (or it has moved to this ' +
          'one): move the club on file first (docs/RUNBOOK.md, "Moving a club to another ' +
          'partner"), then ' + release + ' with the name unchanged and run "Process any ' +
          'missed form responses". ' +
          'A new club: it may not take a name another partner\'s club has (the attendance form ' +
          'and Salesforce tell clubs apart by name) — ' +
          (org ? 'first, ' + orgHoldStep_() + '; then ' : '') + sameNameHoldStep_() + ', then ' +
          release + ' and run "Process any missed form responses" (a release under the old ' +
          'name is refused).',
      dedupeKey: source,
    };
  }
  return {
    issue: 'New club held as a possible duplicate',
    partner: partner, club: club,
    detail: head + 'Same club: enter only its new girls on "' + Q.ACTION_MOD + '" for the club on file, ' +
        'then resolve. Really new (or the list is right): ' +
        (org ? 'first, ' + orgHoldStep_() + '; then ' : '') +
        release + ', then run "Process any missed form responses".',
    dedupeKey: source,
  };
}

/**
 * What staff decided about each held new-club response. rows: ReviewQueue
 * rows {row, issue, detail, resolved}. Returns {'<tab>!<row>': {row, state,
 * sentAt}} from the LAST hold item (HOLD_ISSUES) tagged with that response row:
 * state 'open' (resolved empty), 'release' (resolved starts with the word
 * "release") or 'closed' (any other text); sentAt from its "(sent …)".
 * The issue is matched as issueKey_ reads it (an item restored by hand); the
 * tag and the sent time stay exact.
 */
function holdDecisions_(rows) {
  const out = {}, issues = HOLD_ISSUES.map(issueKey_);
  rows.forEach(function (r) {
    if (issues.indexOf(issueKey_(r.issue)) === -1) return;
    const detail = String(r.detail == null ? '' : r.detail);
    const tag = detail.match(/\[#([^\]]*)\]\s*$/), sent = detail.match(/\(sent ([^)]*)\)/);
    if (!tag) return;
    const resolved = tidy_(r.resolved);
    out[tag[1]] = { row: r.row, sentAt: sent ? sent[1] : '',
                    state: !resolved ? 'open' : /^release\b/i.test(resolved) ? 'release' : 'closed' };
  });
  return out;
}

/** 'yyyy-MM-dd' the response was sent, from its FormLog key ('' for an older key). */
function sentDayOfKey_(responseKey) {
  const m = WALL_KEY.exec(String(responseKey || ''));
  return m ? m[2].slice(2, 12) : '';
}

/**
 * The tag a weekly e-mail may show: a response-row reference such as
 * 'Feedback!7'. Other tags ARE girls' names (a duplicated or unmatched name).
 */
function responseRowTag_(detail) {
  const m = String(detail || '').match(/\[#([^\]]*)\]\s*$/);
  if (!m) return '';
  const bang = m[1].lastIndexOf('!');
  const tab = m[1].slice(0, bang), row = m[1].slice(bang + 1);
  return bang > 0 && /^\d+$/.test(row) &&
      [TAB.FEEDBACK, TAB.ROSTER_FORM, TAB.RESPONSES].indexOf(tab) !== -1 ? m[1] : '';
}

/** "partner / club" for the weekly e-mail: only names on file are shown. */
function digestWho_(r, known) {
  const p = tidy_(r.partner), c = tidy_(r.club);
  if (!p && !c) return '(no partner or club)';
  return (!p ? '(partner not given)' : known.partners[key_(p)] || '(partner not on file)') + ' / ' +
         (!c ? '(club not given)' : known.clubs[key_(c)] || '(club not on file)');
}

/**
 * The weekly e-mail's ReviewQueue section. rows: [{row, raised ('yyyy-MM-dd'),
 * issue, partner, club, detail, resolved}]; known: {partners, clubs} from
 * ClubRegistry, keyed by key_. Never prints the detail column, a name tag, a
 * partner/club that is not on file, or a raised cell that is not a date.
 * Returns {open, fresh, lines}.
 */
function reviewDigest_(rows, today, known) {
  const open = rows.filter(function (r) { return tidy_(r.issue) && !tidy_(r.resolved); });
  // raised is shown and aged only when it is a date: the cell is free text
  const day = function (r) { const t = tidy_(r.raised); return /^\d{4}-\d{2}-\d{2}$/.test(t) ? t : ''; };
  const age = function (r) { return daysBetween_(day(r), today); };   // NaN if unknown
  // "new" = raised since the previous Monday e-mail (1-7 days ago): each day is
  // counted in exactly one e-mail; an item raised today counts next week
  const isNew = function (r) { return age(r) > 0 && age(r) <= DIGEST.NEW_DAYS; };
  const groups = {};
  open.forEach(function (r) {
    const issue = REVIEW_ISSUES.indexOf(tidy_(r.issue)) !== -1 ? tidy_(r.issue) : OTHER_ISSUE;
    (groups[issue] = groups[issue] || []).push(r);
  });
  const fresh = open.filter(isNew).length;
  if (!open.length) return { open: 0, fresh: 0, lines: [] };
  const lines = [open.length + ' open ReviewQueue item(s)' + (fresh ? ', ' + fresh + ' new this week' : '') +
                 ' — tab "' + TAB.REVIEW + '"; how to work each one: docs/RUNBOOK.md, ' +
                 '"Working the ReviewQueue".', ''];
  REVIEW_ISSUES.concat([OTHER_ISSUE]).forEach(function (issue) {
    const list = groups[issue];
    if (!list) return;
    const ages = list.map(age).filter(function (d) { return !isNaN(d); });
    const n = list.filter(isNew).length;
    lines.push(issue + ': ' + list.length + ' open' + (n ? ', ' + n + ' new' : '') +
               (ages.length ? ', oldest ' + Math.max.apply(null, ages) + ' day(s)' : ''));
    // this week's items first (the cap must never hide them), then the backlog oldest first
    const shown = list.filter(isNew).concat(list.filter(function (r) { return !isNew(r); }));
    shown.slice(0, DIGEST.MAX_PER_ISSUE).forEach(function (r) {
      const tag = responseRowTag_(r.detail);
      lines.push('  - row ' + r.row + ' · raised ' + (day(r) || '?') + ' · ' + digestWho_(r, known) +
                 (tag ? ' · ' + tag : ''));
    });
    if (list.length > DIGEST.MAX_PER_ISSUE) {
      lines.push('  … and ' + (list.length - DIGEST.MAX_PER_ISSUE) + ' more');
    }
    lines.push('');
  });
  return { open: open.length, fresh: fresh, lines: lines };
}

/**
 * The weekly e-mail's Salesforce section. rows: pending SF Pending rows
 * ('added' as yyyy-MM-dd); shared: sharedClubNames_ over the Roster. Each
 * line starts with the exact name the club's Salesforce account must have
 * (sfClubName_): the club name, or "<club> - <partner>" for a name two
 * partners' active clubs share — worked out now, never stored, so a renamed
 * club or partner cannot leave it stale. A row with no club name, or a
 * shared name with no partner, says so instead of guessing (sfClubName_
 * would refuse). A shared name also says to check the form:
 * there the long or plain name is sticky (RosterOps.gs, "clubs that share a
 * name"), and an account named otherwise than the form sends gets a stray
 * twin in Salesforce at the club's first attendance.
 */
function sfPendingLines_(rows, shared) {
  if (!rows.length) return [];
  shared = shared || Object.create(null);
  const lines = [rows.length + ' new club(s) are waiting to be created in Salesforce ' +
                 '(tab "' + TAB.SF_PENDING + '"). Each line starts with the exact Salesforce ' +
                 'account name: create it character for character (the attendance form sends ' +
                 'that name; a club whose name another partner\'s club also has is "<club>' +
                 SF_NAME_SEP + '<partner>"). Set status to "done" once created.', ''];
  rows.forEach(function (r) {
    const club = tidy_(r[2]), isShared = !!club && shared[key_(club)] === true;
    const name = !club ? '(no club name in this row: fix it first)'
        : isShared && !tidy_(r[1]) ? '(a shared club name, and no partner in this row: fix it first)'
        : sfClubName_(club, r[1], shared);
    lines.push('- ' + name + ' | ' + r[1] + ' | ' + (r[3] || 'region?') + ' | ' + r[4] +
               ' girls | mentor ' + r[5] + ' <' + r[6] + '> | added ' + r[0] +
               (isShared ? ' | ' + SF_SHARED_NOTE : ''));
  });
  return lines;
}
/** Ends the Salesforce line of a club whose name another partner's active club has. */
const SF_SHARED_NOTE = 'NAME SHARED with another partner\'s club: before creating the account, find ' +
    'this club in the attendance form\'s club list and use exactly that text';

// ------------------------------------------------------- the weekly e-mail
/**
 * Weekly (Monday 08:00): the open ReviewQueue items, then the clubs still
 * waiting to become Salesforce Accounts — each with the exact account name
 * (sfPendingLines_) — in one e-mail to STAFF_NOTIFY_EMAIL.
 * Nothing open and nothing pending → no e-mail. The installed trigger calls
 * this BY NAME (installTriggers): renaming it stops the e-mail until
 * "Install triggers" is run again.
 */
function sendSfPendingDigest() {
  const zone = spreadsheetZone_();
  const review = reviewDigest_(readReviewRows_(zone), today_(), readKnownNames_());
  const pending = readSfPending_(zone);
  if (!review.open && !pending.length) return;
  const counts = review.open + ' open ReviewQueue item(s) (' + review.fresh + ' new this week), ' +
      pending.length + ' club(s) pending in Salesforce';
  const staff = PropertiesService.getScriptProperties().getProperty(PROP.STAFF_EMAIL);
  if (!staff) {
    audit_('sendSfPendingDigest', counts + ' but STAFF_NOTIFY_EMAIL is not set');
    return;
  }
  const subject = [review.open ? review.open + ' open ReviewQueue item(s)' : '',
                   pending.length ? pending.length + ' club(s) pending in Salesforce' : '']
      .filter(String).join(' · ');
  // the Roster is read only when a club is pending: its names decide the account names
  const shared = pending.length ? sharedClubNames_(loadRoster_().rows) : Object.create(null);
  MailApp.sendEmail({ to: staff, subject: 'GLOW weekly: ' + subject,
                      body: review.lines.concat(sfPendingLines_(pending, shared)).join('\n') });
  audit_('sendSfPendingDigest', 'emailed ' + staff + ': ' + counts);
}

/** The ReviewQueue for the weekly e-mail, `raised` as 'yyyy-MM-dd' whether a date cell or text. */
function readReviewRows_(zone) {
  const sheet = SpreadsheetApp.getActive().getSheetByName(TAB.REVIEW);
  if (!sheet || sheet.getLastRow() < 2) return [];
  return sheet.getRange(2, 1, sheet.getLastRow() - 1, REVIEW_COLS.length).getValues()
      .map(function (v, i) {
        return { row: i + 2, raised: dayText_(v[0], zone), issue: v[1], partner: v[2],
                 club: v[3], detail: v[4], resolved: v[5] };
      });
}

/** Partner and club names on file (ClubRegistry), keyed by key_: the only ones the e-mail prints. */
function readKnownNames_() {
  const known = { partners: {}, clubs: {} };
  const sheet = SpreadsheetApp.getActive().getSheetByName(TAB.CLUBS);
  if (!sheet || sheet.getLastRow() < 2) return known;
  sheet.getRange(2, 2, sheet.getLastRow() - 1, 2).getValues().forEach(function (r) {
    if (tidy_(r[0])) known.partners[key_(r[0])] = tidy_(r[0]);
    if (tidy_(r[1])) known.clubs[key_(r[1])] = tidy_(r[1]);
  });
  return known;
}

/** SF Pending rows still 'pending', the 'added' date as text. */
function readSfPending_(zone) {
  const sheet = SpreadsheetApp.getActive().getSheetByName(TAB.SF_PENDING);
  if (!sheet || sheet.getLastRow() < 2) return [];
  return sheet.getRange(2, 1, sheet.getLastRow() - 1, SF_PENDING_COLS.length).getValues()
      .filter(function (r) { return key_(r[SF_PENDING_COLS.indexOf('status')]) === 'pending'; })
      .map(function (r) { r[0] = dayText_(r[0], zone); return r; });
}

/** 'yyyy-MM-dd' from a date cell (read in the sheet's zone) or from text. */
function dayText_(cell, zone) {
  return cell instanceof Date && !isNaN(cell.getTime())
      ? Utilities.formatDate(cell, zone, 'yyyy-MM-dd') : tidy_(cell).slice(0, 10);
}

/** Keep the dropdowns current after a change; never let it fail a submission. */
function trySyncChoices_() {
  try { syncFormChoices(); } catch (err) { audit_('syncFormChoices', 'failed: ' + err.message); }
}
