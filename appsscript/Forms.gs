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
 * Config.gs (Q), because the handlers find answers by title.
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

function createGlowForms() {
  const ss = SpreadsheetApp.getActive();
  const ui = SpreadsheetApp.getUi();
  const made = [];

  const feedback = existingForm_(PROP.FEEDBACK_FORM) || createFeedbackForm_(ss, made);
  const roster = existingForm_(PROP.ROSTER_FORM) || createRosterForm_(ss, feedback, made);

  syncFormChoices();
  installTriggers();
  audit_('createGlowForms', made.length ? 'created: ' + made.join(', ') : 'both forms already existed');

  ui.alert('GLOW forms', formLinksText_(roster, feedback) +
      '\n\nResponses land in the tabs "' + TAB.ROSTER_FORM + '" and "' + TAB.FEEDBACK +
      '". Set STAFF_NOTIFY_EMAIL in Script Properties to receive problem reports ' +
      'and the weekly Salesforce digest.',
      ui.ButtonSet.OK);
}

function existingForm_(propKey) {
  const id = PropertiesService.getScriptProperties().getProperty(propKey);
  if (!id) return null;
  try { return FormApp.openById(id); } catch (err) { return null; }
}

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
  commonSettings_(form,
      'Did a form do something odd, refuse to submit, show the wrong club, or ' +
      'take forever to load? Tell us here — it takes a minute and helps us fix ' +
      'it quickly. Please do not include girls\' names unless the problem is ' +
      'about a specific name.',
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
  form.addTextItem().setTitle(Q.FB_EMAIL)
      .setValidation(FormApp.createTextValidation().requireTextIsEmail().build());
  linkFormToSheet_(form, ss, TAB.FEEDBACK);
  PropertiesService.getScriptProperties().setProperty(PROP.FEEDBACK_FORM, form.getId());
  made.push('feedback');
  return form;
}

// ------------------------------------------------------ Club Roster Form
function createRosterForm_(ss, feedback, made) {
  const form = FormApp.create(FORM_TITLES.ROSTER);
  commonSettings_(form,
      'Enroll a new club, or add and remove girls in a club that is already ' +
      'enrolled. Changes reach the attendance form within the hour. Removed ' +
      'girls stop appearing on the attendance form; their history is kept.' +
      '\n\nSomething not working? ' + feedback.getPublishedUrl(),
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
  form.addTextItem().setTitle(Q.CLUB).setRequired(true)
      .setHelpText('The name mentors will type on the attendance form.');
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
  form.addParagraphTextItem().setTitle(Q.REMOVE)
      .setHelpText('Leave empty if nobody is leaving. Spell names as they were ' +
                   'enrolled; we match ignoring capitals.');
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
  const a = existingForm_(PROP.ROSTER_FORM), c = existingForm_(PROP.FEEDBACK_FORM);
  if (!a || !c) {
    ui.alert('GLOW forms', 'The forms do not exist yet — run "Create the Google Forms".',
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
