/**
 * Shared configuration for the GLOW enrollment → attendance pipeline.
 *
 * This script is bound to the enrollment spreadsheet. Nothing here talks to
 * Jotform; Phase 1 is Sheet-only.
 *
 * Secrets live in Script Properties (File → Project Settings → Script
 * Properties), never in code:
 *   JOTFORM_API_KEY   - used from Phase 2 onward
 */

/**
 * Tab names. This script is bound to the "master enrollment" spreadsheet:
 * the original enrollment responses were imported into it once (tab
 * RESPONSES) and everything after that arrives through the generated forms.
 */
const TAB = {
  RESPONSES: 'Enrollment Responses',  // the original form's responses, imported once (read-only to us)
  ROSTER: 'Roster',               // canonical: one row per girl
  PARTNERS: 'Partners',           // partner → region, filled in by staff
  CLUBS: 'ClubRegistry',          // club → immutable club code
  REVIEW: 'ReviewQueue',          // anything needing a human decision
  AUDIT: 'Audit',                 // what the scripts did, and when
  // Phase 3: the generated Google Forms write here (renamed from the
  // "Form Responses N" Google creates), and the handlers read from here
  NEW_CLUB: 'New Club Responses',
  ROSTER_MOD: 'Roster Changes',
  FEEDBACK: 'Feedback',
  SF_PENDING: 'SF Pending',       // new clubs waiting to become Salesforce Accounts
  FORM_LOG: 'FormLog',            // which form responses have been processed
};

/** Titles of the generated Google Forms. */
const FORM_TITLES = {
  NEW_CLUB: 'GLOW – New Club Enrollment',
  ROSTER_MOD: 'GLOW – Roster Modification',
  FEEDBACK: "GLOW – Something isn't working?",
};

/**
 * Question titles. They double as the column headers of the response tabs,
 * so the handlers look answers up by these exact strings — change one here
 * and both the form generator and the handler follow.
 */
const Q = {
  PARTNER: 'Partner organization',
  NEW_PARTNER: 'If your organization is not in the list, type its name here',
  COUNTRY: 'Country where this club meets',
  CLUB: 'Club name',
  COUNT: 'Number of girls enrolled in this club',
  ROSTER: 'Full name of every enrolled girl (First, Middle and Last Name/Surname) – one name per line',
  SAME_NAME: 'Are any two girls in this club listed with exactly the same name?',
  SAME_NAME_DETAIL: 'If yes: list those names and how to tell the girls apart (e.g. a middle name)',
  MENTOR_NAME: 'Mentor name',
  MENTOR_EMAIL: 'Mentor email',
  ENGLISH: 'Does the mentor who will submit attendance speak English?',
  LANGUAGE: "If not, the mentor's primary language",
  CLUB_PREFIX: 'Club (',            // per-partner dropdown: 'Club (<partner>)'
  ADD: 'Girls to ADD to this club – one full name per line',
  REMOVE: 'Girls to REMOVE from this club – one full name per line, spelled as enrolled',
  NOTES: 'Anything else we should know?',
  FB_FORM: 'Which form were you using?',
  FB_DOING: 'What were you trying to do?',
  FB_WHAT: 'What happened, and what did you expect instead?',
  FB_PARTNER: 'Your partner organization (optional)',
  FB_CLUB: 'Club name (optional)',
  FB_DEVICE: 'Phone or computer, and which browser? (optional)',
  FB_EMAIL: 'Your email, if you would like a reply (optional)',
};

/** The partner-dropdown escape hatch on the New Club form. */
const OTHER_PARTNER = 'My organization is not in this list';

/** Script Properties keys (File → Project Settings → Script Properties). */
const PROP = {
  NEW_CLUB_FORM: 'FORM_NEW_CLUB_ID',
  ROSTER_MOD_FORM: 'FORM_ROSTER_MOD_ID',
  FEEDBACK_FORM: 'FORM_FEEDBACK_ID',
  STAFF_EMAIL: 'STAFF_NOTIFY_EMAIL',   // gets feedback reports + the weekly SF digest
};

/** Columns of the Roster tab, in order. */
const ROSTER_COLS = [
  'girl_id', 'partner', 'club', 'region', 'full_name', 'last_name',
  'status', 'added_date', 'removed_date', 'source',
];

/** Columns of the enrollment responses tab, matched loosely (lowercased). */
const RESPONSE_COLS = {
  partner: 'partner organization name',
  club: 'club name',
  roster: 'please list the full name',
};

/** Jotform forms this pipeline manages (Phase 2+). */
const FORMS = {
  TEMPLATE: '262352490535154',      // every sync-logic change lands here first
  AFRICA: '262382821971058',        // live regionals, cloned from the template 2026-08-27
  ASIA: '262383129464057',
  LATIN_AMERICA: '262383455778067',
  US: '262382706852058',
  // defunct (kept as archives, labelled "(defunct)" in Jotform):
  // master 260555608160556, Africa 260703905772560, Asia 260704198384564,
  // Latin America 260704170003542, U.S 260703912140547
};

/**
 * Structural question IDs. Verified identical on all six forms (2026-08-24),
 * and the Salesforce integration maps to these numbers — changing them breaks
 * the integration.
 */
const QID = {
  CLUB_NAME: '5',
  DATE: '17',
  PARTNER: '331',
  PHOTO: '19',
  YEAR: '94',
  MODULE: { '1': '14', '2': '92', '3': '93' },   // GLOW year → module dropdown
  SESSIONS: { 8: '15', 10: '95', 14: '96', 15: '97' },  // length → dropdown
  CONTACT_IDS: '18',
  MODULE_ID: '98',
  WEEK_ID: '100',
  YEAR_ID: '102',
  CREATOR: '105',
  ENABLE_FUZZY: '109',
  MENTOR_EMAIL: '332',            // working copy only; clones inherit it
};

/**
 * Sessions per module. Modules not listed run 8 sessions.
 * EDIT HERE when the curriculum changes.
 */
const SESSION_OVERRIDES = {
  'Elective - Healthy GLOW': 14,
  'Elective - Girl Boss Basics': 10,
  'Elective - Girl Boss Pro': 15,
};

const STATUS = { ACTIVE: 'active', INACTIVE: 'inactive' };

function getApiKey_() {
  const key = PropertiesService.getScriptProperties()
      .getProperty('JOTFORM_API_KEY');
  if (!key) {
    throw new Error('JOTFORM_API_KEY is not set. Add it in File → Project ' +
                    'Settings → Script Properties.');
  }
  return key;
}
