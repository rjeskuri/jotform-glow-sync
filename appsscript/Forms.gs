/**
 * The three Google Forms, generated and kept current from the spreadsheet.
 *
 *   New Club Enrollment   partner dropdown; a "not listed" choice branches to
 *                         a short page that requires the new organization's
 *                         name; then club, roster, mentor details → handler
 *                         creates the club, mints IDs, queues it for Salesforce
 *   Roster Modification   partner-branched: page 1 is the partner dropdown,
 *                         each partner has its own section listing only its
 *                         clubs, then one shared "the change" page with
 *                         ADD / REMOVE lists → handler adds, reactivates or
 *                         retires girls; nothing is ever deleted
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
 * that break (i.e. what happens when the respondent reaches the break by
 * pressing Next). A dropdown choice created with createChoice(value, pageBreak)
 * overrides that for the page the dropdown is on. So:
 *   - page-1 dropdown choices jump to a partner's section;
 *   - every partner section's break carries setGoToPage(changesPage), which
 *     wires "after the PREVIOUS partner's section → the change page";
 *   - the change page's break is CONTINUE, so the last partner's section
 *     flows into it too. Nothing carries SUBMIT — the last page submits.
 */

const CHANGES_PAGE_TITLE = 'The change';
const NEW_PARTNER_PAGE_TITLE = 'Your organization';
const CLUB_PAGE_TITLE = 'The club';

function createGlowForms() {
  const ss = SpreadsheetApp.getActive();
  const ui = SpreadsheetApp.getUi();
  const made = [];

  const feedback = existingForm_(PROP.FEEDBACK_FORM) || createFeedbackForm_(ss, made);
  const newClub = existingForm_(PROP.NEW_CLUB_FORM) || createNewClubForm_(ss, feedback, made);
  const rosterMod = existingForm_(PROP.ROSTER_MOD_FORM) ||
      createRosterModificationForm_(ss, feedback, newClub, made);

  syncFormChoices();
  installTriggers();
  audit_('createGlowForms', made.length ? 'created: ' + made.join(', ') : 'all three already existed');

  ui.alert('GLOW forms', formLinksText_(newClub, rosterMod, feedback) +
      '\n\nResponses land in the tabs "' + TAB.NEW_CLUB + '", "' + TAB.ROSTER_MOD +
      '" and "' + TAB.FEEDBACK + '". Set STAFF_NOTIFY_EMAIL in Script Properties ' +
      'to receive problem reports and the weekly Salesforce digest.',
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

// ------------------------------------------------------------ Form 3
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
                 FORM_TITLES.NEW_CLUB, FORM_TITLES.ROSTER_MOD,
                 'The enrollment spreadsheet', 'Something else'];
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

// ------------------------------------------------------------ Form 1
function createNewClubForm_(ss, feedback, made) {
  const form = FormApp.create(FORM_TITLES.NEW_CLUB);
  commonSettings_(form,
      'Use this form to enroll a NEW club. One submission per club. To add or ' +
      'remove girls from a club that is already enrolled, use the Roster ' +
      'Modification form instead.\n\nSomething not working? ' + feedback.getPublishedUrl(),
      'Thank you — the club has been received. Its roster will appear on the ' +
      'attendance form within the hour. If we have a question about any of the ' +
      'names we will contact the mentor by email.');
  // page 1: the partner. Choices are wired in syncFormChoices(): known
  // partners jump straight to "The club", the "not listed" choice goes
  // through "Your organization" first, where the name is required.
  form.addListItem().setTitle(Q.PARTNER).setRequired(true);

  form.addPageBreakItem().setTitle(NEW_PARTNER_PAGE_TITLE)
      .setHelpText('Your organization is not enrolled yet — tell us who you are.');
  form.addTextItem().setTitle(Q.NEW_PARTNER).setRequired(true);
  form.addTextItem().setTitle(Q.COUNTRY).setRequired(true);

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
  linkFormToSheet_(form, ss, TAB.NEW_CLUB);
  PropertiesService.getScriptProperties().setProperty(PROP.NEW_CLUB_FORM, form.getId());
  made.push('new club');
  return form;
}

// ------------------------------------------------------------ Form 2
function createRosterModificationForm_(ss, feedback, newClub, made) {
  const form = FormApp.create(FORM_TITLES.ROSTER_MOD);
  commonSettings_(form,
      'Use this form to ADD girls to, or REMOVE girls from, a club that is ' +
      'already enrolled. Pick your organization, then your club, then list the ' +
      'changes. Removed girls stop appearing on the attendance form; their ' +
      'history is kept.\n\nEnrolling a brand-new club? Use ' + newClub.getPublishedUrl() +
      '\nSomething not working? ' + feedback.getPublishedUrl(),
      'Thank you — the change has been received and will reach the attendance ' +
      'form within the hour. If a name to remove did not match anyone on the ' +
      'roster we will check with you by email rather than guess.');
  form.addListItem().setTitle(Q.PARTNER).setRequired(true)
      .setHelpText('Not listed? Your organization has no enrolled clubs yet — ' +
                   'use the New Club Enrollment form.');
  // partner sections are inserted before this page by syncFormChoices()
  form.addPageBreakItem().setTitle(CHANGES_PAGE_TITLE);
  form.addParagraphTextItem().setTitle(Q.ADD)
      .setHelpText('Leave empty if nobody is joining. Girls who were on this ' +
                   'roster before and left are simply reactivated.');
  form.addParagraphTextItem().setTitle(Q.REMOVE)
      .setHelpText('Leave empty if nobody is leaving. Spell names as they were ' +
                   'enrolled; we match ignoring capitals.');
  form.addTextItem().setTitle(Q.MENTOR_EMAIL).setRequired(true)
      .setHelpText('We send a short confirmation of what changed.')
      .setValidation(FormApp.createTextValidation().requireTextIsEmail().build());
  form.addParagraphTextItem().setTitle(Q.NOTES);
  linkFormToSheet_(form, ss, TAB.ROSTER_MOD);
  PropertiesService.getScriptProperties().setProperty(PROP.ROSTER_MOD_FORM, form.getId());
  made.push('roster modification');
  return form;
}

// ------------------------------------------------- keeping choices current
/**
 * Make the forms' dropdowns match the spreadsheet: the partner lists, and on
 * the Roster Modification form one section per partner holding only that
 * partner's active clubs. New partners get a new section; nothing is removed
 * (a partner whose clubs all went inactive keeps a section, which the
 * dropdown still routes to — harmless).
 */
function syncFormChoices() {
  const partners = partnerChoices_();
  const clubsByPartner = activeClubsByPartner_();
  let changed = 0;

  const newClub = existingForm_(PROP.NEW_CLUB_FORM);
  if (newClub) {
    const partnerItem = findListItem_(newClub, Q.PARTNER);
    const newPartnerPage = findPageBreak_(newClub, NEW_PARTNER_PAGE_TITLE);
    const clubPage = findPageBreak_(newClub, CLUB_PAGE_TITLE);
    if (!partnerItem || !newPartnerPage || !clubPage) {
      throw new Error('New Club form is missing its partner dropdown or its "' +
                      NEW_PARTNER_PAGE_TITLE + '" / "' + CLUB_PAGE_TITLE + '" pages');
    }
    const wanted = partners.concat([OTHER_PARTNER]);
    if (!sameValues_(partnerItem, wanted)) {
      partnerItem.setChoices(partners.map(function (p) {
        return partnerItem.createChoice(p, clubPage);
      }).concat([partnerItem.createChoice(OTHER_PARTNER, newPartnerPage)]));
      changed++;
    }
    clubPage.setGoToPage(FormApp.PageNavigationType.CONTINUE);   // after "Your organization"
  }

  const mod = existingForm_(PROP.ROSTER_MOD_FORM);
  if (mod) {
    const changesPage = findPageBreak_(mod, CHANGES_PAGE_TITLE);
    if (!changesPage) throw new Error('Roster Modification form has no "' + CHANGES_PAGE_TITLE + '" page');
    const sections = {};
    mod.getItems(FormApp.ItemType.PAGE_BREAK).forEach(function (pb) {
      sections[key_(pb.getTitle())] = pb.asPageBreakItem();
    });
    const lists = {};
    mod.getItems(FormApp.ItemType.LIST).forEach(function (li) {
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
        // new partner: section + club dropdown, placed just before the change page
        const at = changesPage.getIndex();
        pb = mod.addPageBreakItem().setTitle(partner);
        mod.moveItem(pb.getIndex(), at);
        list = mod.addListItem().setTitle(clubQuestionTitle_(partner)).setRequired(true);
        mod.moveItem(list.getIndex(), at + 1);
        sections[key_(partner)] = pb;
        lists[key_(list.getTitle())] = list;
        changed++;
      } else if (!list) {
        list = mod.addListItem().setTitle(clubQuestionTitle_(partner)).setRequired(true);
        mod.moveItem(list.getIndex(), pb.getIndex() + 1);
        lists[key_(list.getTitle())] = list;
        changed++;
      }
      // "after the section before this break → the change page" (see header)
      pb.setGoToPage(changesPage);
      if (!sameValues_(list, clubs.length ? clubs : ['(no active clubs)'])) {
        list.setChoiceValues(clubs.length ? clubs : ['(no active clubs)']);
        changed++;
      }
    });
    changesPage.setGoToPage(FormApp.PageNavigationType.CONTINUE);   // last section → change page

    const partnerItem = findListItem_(mod, Q.PARTNER);
    partnerItem.setChoices(allPartners.map(function (p) {
      return partnerItem.createChoice(p, sections[key_(p)]);
    }));
  }
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

function formLinksText_(newClub, rosterMod, feedback) {
  const line = function (label, f) {
    return label + '\n  fill in: ' + f.getPublishedUrl() + '\n  edit:    ' + f.getEditUrl();
  };
  return [line('New Club Enrollment', newClub), line('Roster Modification', rosterMod),
          line("Something isn't working?", feedback)].join('\n\n');
}

function showFormLinks() {
  const ui = SpreadsheetApp.getUi();
  const a = existingForm_(PROP.NEW_CLUB_FORM), b = existingForm_(PROP.ROSTER_MOD_FORM),
        c = existingForm_(PROP.FEEDBACK_FORM);
  if (!a || !b || !c) {
    ui.alert('GLOW forms', 'Not all forms exist yet — run "Create the three Google Forms".',
             ui.ButtonSet.OK);
    return;
  }
  ui.alert('GLOW forms', formLinksText_(a, b, c), ui.ButtonSet.OK);
}

/**
 * Close the original enrollment form (the one feeding the RESPONSES tab)
 * with a message pointing at the new forms. Only works when that form feeds
 * THIS spreadsheet; asks first; reversible in the form's own settings.
 */
function retireOldEnrollmentForm() {
  const ui = SpreadsheetApp.getUi();
  const sheet = SpreadsheetApp.getActive().getSheetByName(TAB.RESPONSES);
  const url = sheet && sheet.getFormUrl();
  if (!url) {
    ui.alert('GLOW', 'No form feeds "' + TAB.RESPONSES + '" in this spreadsheet — ask the ' +
             'old form\'s owner to close it and point people at the new forms.', ui.ButtonSet.OK);
    return;
  }
  const newClub = existingForm_(PROP.NEW_CLUB_FORM), mod = existingForm_(PROP.ROSTER_MOD_FORM);
  if (!newClub || !mod) {
    ui.alert('GLOW', 'Create the new forms first.', ui.ButtonSet.OK);
    return;
  }
  const old = FormApp.openByUrl(url);
  const answer = ui.alert('Retire the old enrollment form?',
      '"' + old.getTitle() + '" will stop accepting responses and show a message ' +
      'with links to the two new forms. Existing responses are kept.',
      ui.ButtonSet.YES_NO);
  if (answer !== ui.Button.YES) return;
  old.setCustomClosedFormMessage(
      'This form has been replaced.\n\nEnroll a NEW club: ' + newClub.getPublishedUrl() +
      '\nAdd or remove girls in an existing club: ' + mod.getPublishedUrl());
  old.setAcceptingResponses(false);
  audit_('retireOldEnrollmentForm', old.getTitle() + ' closed with redirect message');
  ui.alert('GLOW', 'Done — the old form now redirects to the new ones.', ui.ButtonSet.OK);
}
