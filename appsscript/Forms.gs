/**
 * The Google Forms, generated and kept current from the spreadsheet.
 *
 *   Club Roster Form   ONE form for both jobs. Page 1 asks what you want to
 *                      do and jumps to the right branch:
 *                        - Enroll a NEW club: partner (a "not listed" choice
 *                          branches to a page that requires the organization's
 *                          name and its region), then club, roster, mentor details → the
 *                          handler creates the club, mints IDs, queues it for
 *                          Salesforce
 *                        - Add/remove girls: partner → that partner's own club
 *                          list (no 300-item dropdown) → ADD / REMOVE lists →
 *                          the handler adds, reactivates or retires girls;
 *                          nothing is ever deleted
 *   Something isn't working?   a one-minute problem report → staff email
 *
 * Run `createGlowForms` once from the GLOW menu (it is idempotent: forms
 * that already exist are reused). Run `syncFormChoices` after roster changes
 * so the dropdowns stay current — the rebuild and the handlers call it.
 *
 * The forms are owned by whoever runs this, live in their Drive, and can be
 * edited in the normal Forms UI — but question TITLES must stay as in
 * Config.gs (Q), because the handlers find answers by title. Descriptions and
 * help texts live in WORDING; `migrateFormWording` (one-time, previews first)
 * brings forms built before 2026-09-28 up to it.
 *
 * NAVIGATION — read before touching setGoToPage. In FormApp a page break's
 * setGoToPage(x) sets where the form goes after completing the page BEFORE
 * that break (i.e. what happens when the respondent presses Next at the end
 * of the previous section). A choice created with createChoice(value,
 * pageBreak) overrides that for the page the question is on. The Club Roster
 * Form's pages, in order, and what each break's goToPage means:
 *
 *   page 1        "What would you like to do?"      choices jump to (2) or (5)
 *   (2) NEW: partner dropdown                        choices jump to (3) or (4)
 *   (3) "Your organization" (new partners only)      → CONTINUE into (4)
 *   (4) "The club"                                   break (5) = SUBMIT, so
 *                                                    finishing (4) submits
 *   (5) MOD: partner dropdown                        choices jump to a section
 *   (6…) one section per partner, its club list      each break → (7)
 *   (7) "The change"                                 break = CONTINUE; last page
 */

const CHANGES_PAGE_TITLE = 'The change';
const NEW_PARTNER_PAGE_TITLE = 'Your organization';
const CLUB_PAGE_TITLE = 'The club';
const NEW_BRANCH_PAGE_TITLE = 'New club';
const MOD_BRANCH_PAGE_TITLE = 'Existing club';

/** Under the Region picker on the "Your organization" page. */
const REGION_HELP = 'This decides which regional attendance form your clubs ' +
    'will use. Not sure which region fits? Choose the closest one — our team ' +
    'can correct it later.';

/**
 * The forms' wording (backlog 43, 2026-09-28). The generators below and the
 * one-time menu migration (migrateFormWording) both use it, so a fresh build
 * and a migrated live form say the same thing. *_2026_08 is what the
 * generator wrote before: the migration replaces a text only when it is one
 * the generator wrote, never one edited by hand. Question TITLES are not
 * wording: they are Config.gs Q, and the handlers read answers by them.
 * (Literals only: a top-level constant must not read another file's.)
 */
const WORDING = {
  FEEDBACK_INTRO: 'Did a form do something odd, refuse to submit, show the wrong club, or ' +
      'take forever to load? Tell us here — it takes a minute and helps us fix ' +
      'it quickly. Please do not include girls\' names unless the problem is ' +
      'about a specific name.',
  ROSTER_INTRO: 'Enroll a new club, or add and remove girls in a club that is already ' +
      'enrolled. Changes reach the attendance form within the hour. Removed ' +
      'girls stop appearing on the attendance form; their history is kept.',
  CLUB_HELP: 'The club\'s own name — not the mentor\'s name or a girl\'s name. Mentors ' +
      'will choose it from a list on the attendance form, spelled exactly as you ' +
      'type it here.',
  CLUB_HELP_2026_08: 'The name mentors will type on the attendance form.',
  REMOVE_HELP: 'Leave empty if nobody is leaving. Copy each name exactly as it is spelled ' +
      'on the club\'s attendance form (capitals do not matter). A name spelled ' +
      'differently is not removed — our team will check it with you.',
  REMOVE_HELP_2026_08: 'Leave empty if nobody is leaving. Spell names as they were ' +
      'enrolled; we match ignoring capitals.',
};

/** The problem form's description: roster changes belong on the Club Roster Form. */
function feedbackDescription_(rosterUrl) {
  return WORDING.FEEDBACK_INTRO + '\n\nTo add a girl or remove one who left, please use ' +
      'the Club Roster Form instead and choose "' + Q.ACTION_MOD + '" — the attendance ' +
      'form updates within the hour: ' + rosterUrl;
}

/** The Club Roster Form's description; its last line sends only real problems to the problem form. */
function rosterDescription_(feedbackUrl) {
  return WORDING.ROSTER_INTRO + '\n\nSomething not working? To add or remove girls, choose "' +
      Q.ACTION_MOD + '" below; for anything else, tell us here: ' + feedbackUrl;
}

/** What rosterDescription_ said before 2026-09-28 (the migration recognises it). */
function rosterDescription2026_08_(feedbackUrl) {
  return WORDING.ROSTER_INTRO + '\n\nSomething not working? ' + feedbackUrl;
}

function createGlowForms() {
  const ss = SpreadsheetApp.getActive();
  const ui = SpreadsheetApp.getUi();
  const made = [];

  // a stored form that does not open is not "no form yet": new forms would
  // take over its Script Property, and the live form's responses would be
  // ignored from then on (formKeyForSheet_)
  const stored = storedGlowForms_();
  const unopened = unopenedFormsText_(stored);
  if (unopened) {
    ui.alert('GLOW forms', 'Nothing was created. ' + unopened + ' New forms would replace ' +
        'the live ones, and the live forms\' responses would no longer be processed. If a ' +
        'form was deleted on purpose, delete its Script Property first.', ui.ButtonSet.OK);
    return;
  }
  const feedback = stored[0].form || createFeedbackForm_(ss, made);
  const roster = stored[1].form || createRosterForm_(ss, feedback, made);
  // each description links to the other form: the problem form's gets its
  // link once the Club Roster Form exists (existing forms: migrateFormWording)
  if (made.indexOf('feedback') !== -1) {
    feedback.setDescription(feedbackDescription_(roster.getPublishedUrl()));
  }

  syncFormChoices();
  installTriggers();
  audit_('createGlowForms', made.length ? 'created: ' + made.join(', ') : 'both forms already existed');

  ui.alert('GLOW forms', formLinksText_(roster, feedback) +
      '\n\nResponses land in the tabs "' + TAB.ROSTER_FORM + '" and "' + TAB.FEEDBACK +
      '". Set STAFF_NOTIFY_EMAIL in Script Properties to receive problem reports ' +
      'and the Monday e-mail (open ReviewQueue items, clubs pending in Salesforce).',
      ui.ButtonSet.OK);
}

/** The form a Script Property names, or null: none saved, or saved but not opening (storedForm_). */
function existingForm_(propKey) {
  return storedForm_(propKey).form;
}

/**
 * The form a Script Property names: {form, stored}. `stored` with no `form`
 * means an id is saved but does not open (the sheet opened from a Google
 * account without edit access to the forms, a Forms outage) — never "no form
 * yet", so never advice to run "Create the Google Forms".
 */
function storedForm_(propKey) {
  const id = PropertiesService.getScriptProperties().getProperty(propKey);
  if (!id) return { form: null, stored: false };
  try { return { form: FormApp.openById(id), stored: true }; } catch (err) { return { form: null, stored: true }; }
}

/** Both forms: [{label, prop, form, stored}] — the problem form first. */
function storedGlowForms_() {
  return [['problem form', PROP.FEEDBACK_FORM], ['Club Roster Form', PROP.ROSTER_FORM]]
      .map(function (n) { return Object.assign({ label: n[0], prop: n[1] }, storedForm_(n[1])); });
}

/** '' when every saved form opened; else which did not, and what to do (not "Create"). */
function unopenedFormsText_(stored) {
  const bad = stored.filter(function (s) { return s.stored && !s.form; });
  if (!bad.length) return '';
  return 'Could not open the ' + bad.map(function (s) { return s.label; }).join(' and the ') +
      ' saved in Script Properties (' + bad.map(function (s) { return s.prop; }).join(', ') +
      '). Run this from the Google account that owns the forms, or try again later.';
}

/** The ending for a dialog that could not open a saved form. */
const DO_NOT_CREATE = 'Do NOT run "Create the Google Forms": it would replace the live forms, ' +
    'and their responses would no longer be processed.';

function commonSettings_(form, description, confirmation) {
  form.setDescription(description);
  form.setCollectEmail(false);
  form.setLimitOneResponsePerUser(false);
  form.setAllowResponseEdits(false);
  form.setShowLinkToRespondAgain(true);
  form.setConfirmationMessage(confirmation);
  try { form.setRequireLogin(false); } catch (err) { /* consumer accounts have no domain */ }
}

// ------------------------------------------------------------ Feedback
function createFeedbackForm_(ss, made) {
  const form = FormApp.create(FORM_TITLES.FEEDBACK);
  // createGlowForms adds the Club Roster Form paragraph once that form exists
  commonSettings_(form, WORDING.FEEDBACK_INTRO,
      'Thank you — we have received your report and will look into it.');
  const forms = ['Africa Attendance Form', 'Asia Attendance Form',
                 'Latin America Attendance Form', 'U.S Attendance Form',
                 FORM_TITLES.ROSTER, 'The enrollment spreadsheet', 'Something else'];
  form.addListItem().setTitle(Q.FB_FORM).setChoiceValues(forms).setRequired(true);
  form.addParagraphTextItem().setTitle(Q.FB_DOING);
  form.addParagraphTextItem().setTitle(Q.FB_WHAT).setRequired(true)
      .setHelpText('What did you click or type, what did the screen show, and ' +
                   'what should have happened?');
  form.addTextItem().setTitle(Q.FB_PARTNER);
  form.addTextItem().setTitle(Q.FB_CLUB);
  form.addTextItem().setTitle(Q.FB_DEVICE);
  addReplyEmailItem_(form);
  linkFormToSheet_(form, ss, TAB.FEEDBACK);
  PropertiesService.getScriptProperties().setProperty(PROP.FEEDBACK_FORM, form.getId());
  made.push('feedback');
  return form;
}

// ------------------------------------------------------ Club Roster Form
function createRosterForm_(ss, feedback, made) {
  const form = FormApp.create(FORM_TITLES.ROSTER);
  commonSettings_(form, rosterDescription_(feedback.getPublishedUrl()),
      'Thank you — received. It will reach the attendance form within the hour. ' +
      'If we have a question about any name we will contact the mentor by email ' +
      'rather than guess.');

  // page 1: which job? (choices wired below, once the pages exist)
  const action = form.addMultipleChoiceItem().setTitle(Q.ACTION).setRequired(true);

  // ---- branch A: new club
  const newBranch = form.addPageBreakItem().setTitle(NEW_BRANCH_PAGE_TITLE)
      .setHelpText('One submission per club.');
  form.addListItem().setTitle(Q.PARTNER_NEW).setRequired(true);   // choices: syncFormChoices

  form.addPageBreakItem().setTitle(NEW_PARTNER_PAGE_TITLE)
      .setHelpText('Your organization is not enrolled yet — tell us who you are.');
  form.addTextItem().setTitle(Q.NEW_PARTNER).setRequired(true);
  form.addListItem().setTitle(Q.REGION).setRequired(true)
      .setChoiceValues(REGIONS).setHelpText(REGION_HELP);

  form.addPageBreakItem().setTitle(CLUB_PAGE_TITLE);
  form.addTextItem().setTitle(Q.CLUB).setRequired(true).setHelpText(WORDING.CLUB_HELP);
  form.addTextItem().setTitle(Q.COUNT)
      .setValidation(FormApp.createTextValidation().requireNumber().build());
  form.addParagraphTextItem().setTitle(Q.ROSTER).setRequired(true)
      .setHelpText('One girl per line, first name, middle name(s) and surname, ' +
                   'for example:\nFirst Middle Surname\nFirst Surname\n\nNo numbering ' +
                   'needed. If two girls have exactly the same name, add something ' +
                   'that tells them apart.');
  form.addMultipleChoiceItem().setTitle(Q.SAME_NAME).setChoiceValues(['No', 'Yes'])
      .setRequired(true);
  form.addParagraphTextItem().setTitle(Q.SAME_NAME_DETAIL);
  form.addTextItem().setTitle(Q.MENTOR_NAME).setRequired(true);
  form.addTextItem().setTitle(Q.MENTOR_EMAIL).setRequired(true)
      .setValidation(FormApp.createTextValidation().requireTextIsEmail().build());
  form.addMultipleChoiceItem().setTitle(Q.ENGLISH).setChoiceValues(['Yes', 'No']);
  form.addTextItem().setTitle(Q.LANGUAGE);

  // ---- branch B: existing club
  const modBranch = form.addPageBreakItem().setTitle(MOD_BRANCH_PAGE_TITLE)
      .setHelpText('Not listed? Your organization has no enrolled clubs yet — go ' +
                   'back and choose "' + Q.ACTION_NEW + '".');
  form.addListItem().setTitle(Q.PARTNER_MOD).setRequired(true);   // choices: syncFormChoices
  // one section per partner is inserted here by syncFormChoices()
  form.addPageBreakItem().setTitle(CHANGES_PAGE_TITLE);
  form.addParagraphTextItem().setTitle(Q.ADD)
      .setHelpText('Leave empty if nobody is joining. Girls who were on this ' +
                   'roster before and left are simply reactivated.');
  form.addParagraphTextItem().setTitle(Q.REMOVE).setHelpText(WORDING.REMOVE_HELP);
  form.addTextItem().setTitle(Q.MENTOR_EMAIL_MOD).setRequired(true)
      .setValidation(FormApp.createTextValidation().requireTextIsEmail().build());
  form.addParagraphTextItem().setTitle(Q.NOTES);

  // page-1 choices jump to the branches; finishing branch A submits
  action.setChoices([action.createChoice(Q.ACTION_NEW, newBranch),
                     action.createChoice(Q.ACTION_MOD, modBranch)]);
  modBranch.setGoToPage(FormApp.PageNavigationType.SUBMIT);

  linkFormToSheet_(form, ss, TAB.ROSTER_FORM);
  PropertiesService.getScriptProperties().setProperty(PROP.ROSTER_FORM, form.getId());
  made.push('club roster');
  return form;
}

// ------------------------------------------------- keeping choices current
/**
 * Make the form's dropdowns match the spreadsheet: both partner lists, and
 * one section per partner holding only that partner's active clubs. New
 * partners get a new section; nothing is removed (a partner whose clubs all
 * went inactive keeps a section, which the dropdown still routes to).
 */
function syncFormChoices() {
  const form = existingForm_(PROP.ROSTER_FORM);
  if (!form) return 0;
  const partners = partnerChoices_();
  const clubsByPartner = activeClubsByPartner_();
  let changed = 0;

  const need = function (item, what) {
    if (!item) throw new Error('Club Roster Form is missing ' + what);
    return item;
  };
  const newPartnerPage = need(findPageBreak_(form, NEW_PARTNER_PAGE_TITLE), '"' + NEW_PARTNER_PAGE_TITLE + '"');
  const clubPage = need(findPageBreak_(form, CLUB_PAGE_TITLE), '"' + CLUB_PAGE_TITLE + '"');
  const modBranch = need(findPageBreak_(form, MOD_BRANCH_PAGE_TITLE), '"' + MOD_BRANCH_PAGE_TITLE + '"');
  const changesPage = need(findPageBreak_(form, CHANGES_PAGE_TITLE), '"' + CHANGES_PAGE_TITLE + '"');
  const partnerNew = need(findListItem_(form, Q.PARTNER_NEW), 'the new-club partner dropdown');
  const partnerMod = need(findListItem_(form, Q.PARTNER_MOD), 'the existing-club partner dropdown');

  // branch A: known partners skip straight to "The club"
  const wantedNew = partners.concat([OTHER_PARTNER]);
  if (!sameValues_(partnerNew, wantedNew)) {
    partnerNew.setChoices(partners.map(function (p) {
      return partnerNew.createChoice(p, clubPage);
    }).concat([partnerNew.createChoice(OTHER_PARTNER, newPartnerPage)]));
    changed++;
  }
  clubPage.setGoToPage(FormApp.PageNavigationType.CONTINUE);      // after "Your organization"
  modBranch.setGoToPage(FormApp.PageNavigationType.SUBMIT);       // after "The club"

  // branch B: one section per partner, before "The change"
  const sections = {};
  form.getItems(FormApp.ItemType.PAGE_BREAK).forEach(function (pb) {
    sections[key_(pb.getTitle())] = pb.asPageBreakItem();
  });
  const lists = {};
  form.getItems(FormApp.ItemType.LIST).forEach(function (li) {
    lists[key_(li.getTitle())] = li.asListItem();
  });
  const allPartners = partners.slice();
  Object.keys(clubsByPartner).forEach(function (k) {
    if (!partners.some(function (p) { return key_(p) === k; })) allPartners.push(clubsByPartner[k].partner);
  });
  allPartners.sort(function (a, b) { return a.localeCompare(b); });

  allPartners.forEach(function (partner) {
    const clubs = (clubsByPartner[key_(partner)] || { clubs: [] }).clubs;
    let pb = sections[key_(partner)];
    let list = lists[key_(clubQuestionTitle_(partner))];
    if (!pb) {
      const at = changesPage.getIndex();
      pb = form.addPageBreakItem().setTitle(partner);
      form.moveItem(pb.getIndex(), at);
      list = form.addListItem().setTitle(clubQuestionTitle_(partner)).setRequired(true);
      form.moveItem(list.getIndex(), at + 1);
      sections[key_(partner)] = pb;
      lists[key_(list.getTitle())] = list;
      changed++;
    } else if (!list) {
      list = form.addListItem().setTitle(clubQuestionTitle_(partner)).setRequired(true);
      form.moveItem(list.getIndex(), pb.getIndex() + 1);
      lists[key_(list.getTitle())] = list;
      changed++;
    }
    pb.setGoToPage(changesPage);   // "after the section before this break → the change page"
    const values = clubs.length ? clubs : ['(no active clubs)'];
    if (!sameValues_(list, values)) { list.setChoiceValues(values); changed++; }
  });
  changesPage.setGoToPage(FormApp.PageNavigationType.CONTINUE);   // last section → change page

  partnerMod.setChoices(allPartners.map(function (p) {
    return partnerMod.createChoice(p, sections[key_(p)]);
  }));

  audit_('syncFormChoices', changed + ' dropdown(s) updated');
  return changed;
}

function clubQuestionTitle_(partner) {
  return Q.CLUB_PREFIX + partner + ')';
}

function findItem_(form, type, title) {
  const items = form.getItems(type);
  for (let i = 0; i < items.length; i++) {
    if (key_(items[i].getTitle()) === key_(title)) return items[i];
  }
  return null;
}

function findPageBreak_(form, title) {
  const item = findItem_(form, FormApp.ItemType.PAGE_BREAK, title);
  return item ? item.asPageBreakItem() : null;
}

function findListItem_(form, title) {
  const item = findItem_(form, FormApp.ItemType.LIST, title);
  return item ? item.asListItem() : null;
}

/** Dropdown values are the Partners tab, sorted (a form choice must be non-empty). */
function partnerChoices_() {
  const sheet = SpreadsheetApp.getActive().getSheetByName(TAB.PARTNERS);
  const out = [], seen = {};
  if (sheet && sheet.getLastRow() > 1) {
    sheet.getRange(2, 1, sheet.getLastRow() - 1, 1).getValues().forEach(function (r) {
      const p = tidy_(r[0]);
      if (p && !seen[key_(p)]) { seen[key_(p)] = true; out.push(p); }
    });
  }
  out.sort(function (a, b) { return a.localeCompare(b); });
  return out;
}

/** key(partner) → {partner, clubs: [names of clubs with at least one active girl]} */
function activeClubsByPartner_() {
  const out = {};
  loadRoster_().rows.forEach(function (row) {
    if (row.status !== STATUS.ACTIVE) return;
    const partner = tidy_(row.partner), club = tidy_(row.club);
    if (!partner || !club) return;   // a half-typed row must not become a blank choice
    const pk = key_(partner);
    if (!out[pk]) out[pk] = { partner: partner, clubs: [], seen: {} };
    const ck = key_(club);
    if (!out[pk].seen[ck]) { out[pk].seen[ck] = true; out[pk].clubs.push(club); }
  });
  Object.keys(out).forEach(function (k) {
    out[k].clubs.sort(function (a, b) { return a.localeCompare(b); });
  });
  return out;
}

function sameValues_(listItem, values) {
  const current = listItem.getChoices().map(function (c) { return c.getValue(); });
  return current.length === values.length &&
      current.every(function (v, i) { return v === values[i]; });
}

// -------------------------------------------------------- plumbing
/**
 * Send a form's responses to this spreadsheet and name the tab. Google
 * creates "Form Responses N"; we find it through the sheet's form URL and
 * rename it, retrying briefly because the link can take a moment to appear.
 */
function linkFormToSheet_(form, ss, tabName) {
  form.setDestination(FormApp.DestinationType.SPREADSHEET, ss.getId());
  SpreadsheetApp.flush();
  for (let attempt = 0; attempt < 10; attempt++) {
    const sheet = responseSheetFor_(form.getId());
    if (sheet) {
      if (sheet.getName() !== tabName && !SpreadsheetApp.getActive().getSheetByName(tabName)) {
        sheet.setName(tabName);
      }
      return sheet;
    }
    Utilities.sleep(1500);
  }
  return null;   // handlers route by form URL, so an unrenamed tab still works
}

/** The form id a sheet's form URL points at, or null if it has none. */
function formIdOfSheet_(sheet) {
  const url = sheet.getFormUrl();
  if (!url) return null;
  try { return FormApp.openByUrl(url).getId(); } catch (err) { /* fall through */ }
  const m = url.match(/\/forms\/d\/(?:e\/)?([^/?#]+)/);
  return m ? m[1] : null;
}

/** The response sheet linked to a form, found by its form URL (not by name). */
function responseSheetFor_(formId) {
  const ss = SpreadsheetApp.openById(SpreadsheetApp.getActive().getId());
  const sheets = ss.getSheets();
  for (let i = 0; i < sheets.length; i++) {
    if (formIdOfSheet_(sheets[i]) === formId) return sheets[i];
  }
  return null;
}

function formLinksText_(roster, feedback) {
  const line = function (label, f) {
    return label + '\n  fill in: ' + f.getPublishedUrl() + '\n  edit:    ' + f.getEditUrl();
  };
  return [line('Club Roster Form (new clubs + roster changes)', roster),
          line("Something isn't working?", feedback)].join('\n\n');
}

function showFormLinks() {
  const ui = SpreadsheetApp.getUi();
  const stored = storedGlowForms_();
  const c = stored[0].form, a = stored[1].form;
  if (!a || !c) {
    const unopened = unopenedFormsText_(stored);
    ui.alert('GLOW forms', unopened ? unopened + ' ' + DO_NOT_CREATE
                                    : 'The forms do not exist yet — run "Create the Google Forms".',
             ui.ButtonSet.OK);
    return;
  }
  ui.alert('GLOW forms', formLinksText_(a, c), ui.ButtonSet.OK);
}

/**
 * One-shot (2026-09, backlog 38): replace the free-text Country question on
 * the "Your organization" page with the required Region picker. Idempotent —
 * a second run re-asserts the picker's properties and says so. The response
 * tab keeps the old Country column and its historical answers; the handler
 * reads Q.COUNTRY only as a legacy detail. List items carry no navigation,
 * so the page flow (see NAVIGATION above) is untouched.
 */
function migrateCountryToRegion() {
  const ss = SpreadsheetApp.getActive();
  const ui = SpreadsheetApp.getUi();
  // the document lock every mutating entry point takes: two concurrent runs
  // would BOTH pass the "is the picker there yet?" check and insert twice
  const lock = LockService.getDocumentLock();
  if (!lock.tryLock(30000)) {
    ss.toast('Another GLOW operation is still running - try again in a minute.', 'GLOW', 8);
    return;
  }
  try {
    migrateCountryToRegionLocked_(ui);
  } finally {
    lock.releaseLock();
  }
}

function migrateCountryToRegionLocked_(ui) {
  const form = existingForm_(PROP.ROSTER_FORM);
  if (!form) {
    ui.alert('GLOW', 'The Club Roster Form does not exist yet — run "Create the ' +
        'Google Forms" instead; a freshly created form already has the Region picker.',
        ui.ButtonSet.OK);
    return;
  }
  const country = findItem_(form, FormApp.ItemType.TEXT, Q.COUNTRY);
  let region = findListItem_(form, Q.REGION);
  let note;
  if (region) {
    region.setRequired(true).setChoiceValues(REGIONS).setHelpText(REGION_HELP);
    note = 'already migrated; picker re-asserted';
    if (country) {
      // a run that crashed between insert and move left the picker at the
      // form's END (a required question on the wrong page) - put it in place
      form.moveItem(region.getIndex(), country.getIndex());
      note = 'picker re-asserted and moved into the Country question\'s place';
    }
  } else {
    let at;
    if (country) {
      at = country.getIndex();
    } else {
      const nameBox = findItem_(form, FormApp.ItemType.TEXT, Q.NEW_PARTNER);
      if (!nameBox) {
        ui.alert('GLOW', 'Neither "' + Q.COUNTRY + '" nor "' + Q.NEW_PARTNER + '" is on ' +
            'the form — it does not look like ours. Nothing was changed; check the form ' +
            'in the Forms editor.', ui.ButtonSet.OK);
        return;
      }
      at = nameBox.getIndex() + 1;
    }
    const added = form.addListItem().setTitle(Q.REGION).setRequired(true)
        .setChoiceValues(REGIONS).setHelpText(REGION_HELP);
    form.moveItem(added.getIndex(), at);
    note = 'Region picker inserted';
  }
  if (country) {
    form.deleteItem(country);
    note += '; Country question removed';
  }
  audit_('migrateCountryToRegion', note);
  ui.alert('GLOW', 'Done — ' + note + '.\n\nPreview the fill-in form (do NOT submit a ' +
      'test response): ' + form.getPublishedUrl(), ui.ButtonSet.OK);
}

// ------------------------------------------- the forms' wording (backlog 43)
/**
 * One-shot (2026-09-28): give the two live Google Forms the WORDING above.
 * The problem form's description sends roster changes to the Club Roster
 * Form, and its reply-address question comes back (it was removed by hand;
 * the handler reads it by its title, Q.FB_EMAIL). The Club Roster Form's
 * last line and its "Club name" and REMOVE help texts change.
 *
 * Shows every change and asks first. Takes the document lock only after the
 * answer (never while a dialog is open), re-reads, and applies only what it
 * showed; re-reads again and records the outcome in Audit. Changes texts
 * and adds one question — never a title, never deletes an item, never
 * touches a response, a response tab or FormLog. A text edited by hand is
 * left as is and listed with the suggested text. A second run finds nothing
 * to change (docs/RUNBOOK.md, "Google Forms wording").
 */
function migrateFormWording() {
  const started = Date.now();   // dialog time counts toward Apps Script's 6-minute limit
  let ui = null;
  try { ui = SpreadsheetApp.getUi(); } catch (err) { /* script editor: no dialogs */ }
  if (!ui) {
    throw new Error('Run this from the sheet (GLOW → Google Forms → Update the forms\' ' +
                    'wording): it shows what it would change and asks first.');
  }
  const stored = storedGlowForms_();
  const forms = { FEEDBACK: stored[0].form, ROSTER: stored[1].form };
  if (!forms.FEEDBACK || !forms.ROSTER) {
    const unopened = unopenedFormsText_(stored);
    ui.alert('GLOW forms', unopened ? unopened + ' Nothing was changed. ' + DO_NOT_CREATE
        : 'The forms do not exist yet — run "Create the Google Forms"; a fresh build already ' +
          'has this wording.', ui.ButtonSet.OK);
    return 0;
  }
  const plan = planFormWording_(readFormWording_(forms.FEEDBACK, forms.ROSTER));
  if (!plan.changes.length) {
    ui.alert('GLOW forms', 'Nothing to change: the forms already have this wording.' +
             (plan.skipped.length ? '\n\n' + formWordingPreviewText_(plan) : ''), ui.ButtonSet.OK);
    return 0;
  }
  const answer = ui.alert('GLOW forms', formWordingPreviewText_(plan) + '\n\nMake these ' +
                          'changes now?', ui.ButtonSet.YES_NO);
  if (answer !== ui.Button.YES) {
    audit_('migrateFormWording', 'cancelled at the preview (would have changed: ' +
           wordingLabels_(plan.changes) + ')');
    return 0;
  }
  if (Date.now() - started > WORDING_BUDGET_MS) {
    audit_('migrateFormWording', 'nothing changed: the preview was open too long');
    ui.alert('GLOW forms', 'Nothing was changed: the preview was open too long. Run it again.',
             ui.ButtonSet.OK);
    return 0;
  }
  const lock = LockService.getDocumentLock();
  if (!lock.tryLock(30000)) {
    ui.alert('GLOW forms', 'Another GLOW operation is still running — nothing was changed. ' +
             'Try again in a minute.', ui.ButtonSet.OK);
    return 0;
  }
  const done = [];
  let message;
  try {
    message = migrateFormWordingLocked_(forms, plan, done);
  } finally {
    lock.releaseLock();
  }
  ui.alert('GLOW forms', message, ui.ButtonSet.OK);
  return done.length;
}

/** Under the lock: re-read, apply exactly the previewed changes, re-read; the message for Ryan. */
function migrateFormWordingLocked_(forms, plan, done) {
  const again = planFormWording_(readFormWording_(forms.FEEDBACK, forms.ROSTER));
  if (formWordingKey_(again) !== formWordingKey_(plan)) {
    audit_('migrateFormWording', 'nothing changed: the forms changed since the preview');
    return 'Nothing was changed: the forms changed since the preview. Run it again to see ' +
        'the new preview.';
  }
  try {
    applyFormWording_(forms, again.changes, done);
  } catch (err) {
    audit_('migrateFormWording', 'stopped after ' + done.length + ' of ' + again.changes.length +
           ' change(s) (done: ' + (done.join('; ') || 'nothing') + '): ' + err.message);
    return 'Stopped after ' + done.length + ' of ' + again.changes.length + ' change(s): ' +
        err.message + '\n\nRun it again: it makes only the changes still missing.';
  }
  const after = planFormWording_(readFormWording_(forms.FEEDBACK, forms.ROSTER));
  const verdict = after.changes.length ? 'STILL DIFFERENT: ' + wordingLabels_(after.changes)
                                       : 'up to date';
  audit_('migrateFormWording', 'changed: ' + done.join('; ') +
         (plan.skipped.length ? '; left as is: ' + wordingLabels_(plan.skipped) : '') +
         '; re-read: ' + verdict);
  return (after.changes.length
      ? 'Changed ' + done.length + ', but a re-read still differs: ' + wordingLabels_(after.changes) +
        ' — check it in the Forms editor.'
      : 'Done — ' + done.length + ' change(s); re-read: up to date.') +
      '\n\nPreview the fill-in forms (do NOT submit a test response):\n  ' +
      forms.ROSTER.getPublishedUrl() + '\n  ' + forms.FEEDBACK.getPublishedUrl();
}

/** What the forms say now, as planFormWording_ reads it (a plain snapshot). */
function readFormWording_(feedback, roster) {
  const help = function (type, title) {
    const item = findItem_(roster, type, title);
    return item ? item.getHelpText() : null;
  };
  return {
    feedback: {
      url: feedback.getPublishedUrl(),
      description: feedback.getDescription(),
      items: feedback.getItems().map(function (it) {
        return { title: it.getTitle(), type: itemKind_(it) };
      }),
    },
    roster: {
      url: roster.getPublishedUrl(),
      description: roster.getDescription(),
      clubHelp: help(FormApp.ItemType.TEXT, Q.CLUB),
      removeHelp: help(FormApp.ItemType.PARAGRAPH_TEXT, Q.REMOVE),
    },
  };
}

/** 'TEXT' | 'PARAGRAPH_TEXT' | the type's own name. */
function itemKind_(item) {
  const t = item.getType();
  if (t == FormApp.ItemType.TEXT) return 'TEXT';
  if (t == FormApp.ItemType.PARAGRAPH_TEXT) return 'PARAGRAPH_TEXT';
  return String(t);
}

/** Make the planned changes; `done` collects each label as it lands (a failure part-way keeps them). */
function applyFormWording_(forms, changes, done) {
  changes.forEach(function (c) {
    const form = forms[c.form];
    if (c.what === 'description') {
      form.setDescription(c.to);
    } else if (c.what === 'help') {
      const item = findItem_(form, FormApp.ItemType[c.itemType], c.title);
      if (!item) throw new Error('the question "' + c.title + '" is not on the form');
      item.setHelpText(c.to);
    } else if (c.what === 'add-email') {
      addReplyEmailItem_(form);
    } else {
      throw new Error('unknown change "' + c.what + '"');
    }
    done.push(c.label);
  });
}

/** The problem form's optional reply-address question, placed after the device question. */
function addReplyEmailItem_(form) {
  const item = form.addTextItem().setTitle(Q.FB_EMAIL)
      .setValidation(FormApp.createTextValidation().requireTextIsEmail().build());
  const device = findItem_(form, FormApp.ItemType.TEXT, Q.FB_DEVICE);
  if (device && item.getIndex() !== device.getIndex() + 1) {
    form.moveItem(item.getIndex(), device.getIndex() + 1);
  }
  return item;
}

// From here to the end of the section: plain logic on the snapshot
// readFormWording_ builds, no Google services; tested offline in
// test/forms_logic_test.js.

const WORDING_BUDGET_MS = 240000;   // no change is started after this (Apps Script stops at 6 min)
const WORDING_LABELS = {            // how the preview, the alerts and Audit name each change
  FEEDBACK_DESCRIPTION: 'Problem form: description',
  FEEDBACK_EMAIL: 'Problem form: reply-email question',
  ROSTER_DESCRIPTION: 'Club Roster Form: description',
  CLUB_HELP: 'Club Roster Form: "Club name" help text',
  REMOVE_HELP: 'Club Roster Form: REMOVE help text',
};

/**
 * What migrateFormWording would do: {changes, skipped}. A text equal to the
 * wanted one needs nothing. One the generator wrote — the 2026-08 wording,
 * an empty text, or the wanted text with another form link — is changed.
 * Anything else was edited by hand: left as is, listed with the suggested
 * text (skipped). The reply-address question is added only when no question
 * has its title and none looks like it under another title.
 */
function planFormWording_(s) {
  const plan = { changes: [], skipped: [] };
  wordingStep_(plan, { form: 'FEEDBACK', what: 'description', label: WORDING_LABELS.FEEDBACK_DESCRIPTION },
               s.feedback.description, feedbackDescription_(s.roster.url), [WORDING.FEEDBACK_INTRO]);
  replyEmailStep_(plan, s.feedback.items);
  wordingStep_(plan, { form: 'ROSTER', what: 'description', label: WORDING_LABELS.ROSTER_DESCRIPTION },
               s.roster.description, rosterDescription_(s.feedback.url),
               [rosterDescription2026_08_(s.feedback.url)]);
  helpStep_(plan, WORDING_LABELS.CLUB_HELP, 'TEXT', Q.CLUB, s.roster.clubHelp,
            WORDING.CLUB_HELP, [WORDING.CLUB_HELP_2026_08]);
  helpStep_(plan, WORDING_LABELS.REMOVE_HELP, 'PARAGRAPH_TEXT', Q.REMOVE, s.roster.removeHelp,
            WORDING.REMOVE_HELP, [WORDING.REMOVE_HELP_2026_08]);
  return plan;
}

/** A text as a reader sees it: line breaks kept, other spacing and invisible characters not. */
function wordingText_(s) {
  return String(s == null ? '' : s).replace(/\r\n?/g, '\n').split('\n')
      .map(function (line) { return tidy_(line); }).join('\n').trim();
}

/** The same, with every link replaced: a moved form link does not make a text "edited by hand". */
function wordingLoose_(s) {
  return wordingText_(s).replace(/https?:\/\/\S+/g, '<link>');
}

function wordingStep_(plan, step, current, wanted, before) {
  if (wordingText_(current) === wordingText_(wanted)) return;
  const ours = before.concat(['', wanted]).some(function (t) {
    return wordingLoose_(t) === wordingLoose_(current);
  });
  const entry = Object.assign({ from: current == null ? '' : String(current), to: wanted }, step);
  if (ours) plan.changes.push(entry);
  else plan.skipped.push(Object.assign(entry, { reason: 'edited by hand, so left as is' }));
}

function helpStep_(plan, label, itemType, title, current, wanted, before) {
  const step = { form: 'ROSTER', what: 'help', label: label, itemType: itemType, title: title };
  if (current == null) {
    plan.skipped.push(Object.assign({ to: wanted, reason: 'the question "' + title +
        '" is not on the form (is it ours?)' }, step));
    return;
  }
  wordingStep_(plan, step, current, wanted, before);
}

function replyEmailStep_(plan, items) {
  const step = { form: 'FEEDBACK', what: 'add-email', label: WORDING_LABELS.FEEDBACK_EMAIL,
                 title: Q.FB_EMAIL };
  const same = items.filter(function (it) { return key_(it.title) === key_(Q.FB_EMAIL); });
  if (same.length) {
    if (same[0].type !== 'TEXT') {
      plan.skipped.push(Object.assign({ reason: 'a question with this title is there but is ' +
          'not a short-answer question; check it in the Forms editor' }, step));
    }
    return;
  }
  const lookalike = items.filter(function (it) {
    return (it.type === 'TEXT' || it.type === 'PARAGRAPH_TEXT') && /e-?mail/i.test(it.title);
  });
  if (lookalike.length) {
    plan.skipped.push(Object.assign({ reason: '"' + lookalike[0].title + '" looks like it under ' +
        'another title. Rename it to exactly "' + Q.FB_EMAIL + '" in the Forms editor (the ' +
        'handler reads that title); nothing is added' }, step));
    return;
  }
  const device = items.some(function (it) { return key_(it.title) === key_(Q.FB_DEVICE); });
  plan.changes.push(Object.assign({ after: device ? Q.FB_DEVICE : '' }, step));
}

/** The preview (and the "left as is" list): every change as now → new. */
function formWordingPreviewText_(plan) {
  const quote = function (t) { return wordingText_(t) ? '"' + t + '"' : '(empty)'; };
  const lines = [];
  if (plan.changes.length) {
    lines.push('Would change (' + plan.changes.length + '):');
    plan.changes.forEach(function (c, i) {
      lines.push('', (i + 1) + '. ' + c.label);
      if (c.what === 'add-email') {
        lines.push('   add the question ' + quote(c.title) + ': short answer, optional, must be ' +
                   'an e-mail address, ' + (c.after ? 'after ' + quote(c.after) : 'at the end') + '.',
                   '   The Feedback tab gets a new column with this title; leave the old one ' +
                   'in place.');
      } else {
        lines.push('   now: ' + quote(c.from), '   new: ' + quote(c.to));
      }
    });
  }
  if (plan.skipped.length) {
    lines.push('', 'Left as is (' + plan.skipped.length + '):');
    plan.skipped.forEach(function (sk) {
      lines.push('- ' + sk.label + ': ' + sk.reason + '.' +
                 (sk.to ? '\n  Suggested text: ' + quote(sk.to) : ''));
    });
  }
  lines.push('', 'Question titles, answers and the response tabs are not changed.');
  return lines.join('\n');
}

function wordingLabels_(items) {
  return items.map(function (c) { return c.label; }).join('; ') || 'nothing';
}

/** Two plans are the same change set (the preview vs the re-read under the lock). */
function formWordingKey_(plan) {
  return JSON.stringify(plan.changes.map(function (c) {
    return [c.form, c.what, c.label, c.from || '', c.to || '', c.after || ''];
  }));
}

/**
 * Close the original enrollment form (the one feeding the RESPONSES tab)
 * with a message pointing at the new form. Only works when that form feeds
 * THIS spreadsheet; asks first; reversible in the form's own settings.
 */
function retireOldEnrollmentForm() {
  const ui = SpreadsheetApp.getUi();
  const sheet = SpreadsheetApp.getActive().getSheetByName(TAB.RESPONSES);
  const url = sheet && sheet.getFormUrl();
  if (!url) {
    ui.alert('GLOW', 'No form feeds "' + TAB.RESPONSES + '" in this spreadsheet — ask the ' +
             'old form\'s owner to close it and point people at the new form.', ui.ButtonSet.OK);
    return;
  }
  const roster = existingForm_(PROP.ROSTER_FORM);
  if (!roster) {
    ui.alert('GLOW', 'Create the new form first.', ui.ButtonSet.OK);
    return;
  }
  const old = FormApp.openByUrl(url);
  const answer = ui.alert('Retire the old enrollment form?',
      '"' + old.getTitle() + '" will stop accepting responses and show a message ' +
      'with a link to the new form. Existing responses are kept.',
      ui.ButtonSet.YES_NO);
  if (answer !== ui.Button.YES) return;
  old.setCustomClosedFormMessage(
      'This form has been replaced. Enroll a new club, or add and remove girls ' +
      'in an existing club, here: ' + roster.getPublishedUrl());
  old.setAcceptingResponses(false);
  audit_('retireOldEnrollmentForm', old.getTitle() + ' closed with redirect message');
  ui.alert('GLOW', 'Done — the old form now redirects to the new one.', ui.ButtonSet.OK);
}
