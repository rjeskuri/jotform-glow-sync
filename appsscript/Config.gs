/**
 * Shared configuration for the GLOW enrollment → attendance pipeline.
 *
 * This script is bound to the enrollment spreadsheet and never talks to
 * Jotform: the Python sync does, and Dispatch.gs only asks GitHub to run it.
 * Settings and the one secret (the dispatch token) live in Script Properties
 * (PROP below; File → Project Settings → Script Properties), never in code.
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
  ROSTER_FORM: 'Roster Form Responses',   // new clubs AND roster changes, one form
  FEEDBACK: 'Feedback',
  SF_PENDING: 'SF Pending',       // new clubs waiting to become Salesforce Accounts
  FORM_LOG: 'FormLog',            // which form responses have been processed
  SYNC_LOG: 'SyncLog',            // every run of the Jotform auto-sync (written by tools/auto_sync.py)
};

/** Titles of the generated Google Forms. */
const FORM_TITLES = {
  ROSTER: 'GLOW – Club Roster Form',          // enroll a new club, or change a roster
  FEEDBACK: "GLOW – Something isn't working?",
};

/**
 * Question titles. They double as the column headers of the response tab,
 * so the handlers look answers up by these exact strings — change one here
 * and both the form generator and the handler follow. Titles must be unique
 * within a form (both branches ask for a partner and a mentor email, hence
 * the suffixes).
 */
const Q = {
  ACTION: 'What would you like to do?',
  ACTION_NEW: 'Enroll a NEW club',
  ACTION_MOD: 'Add or remove girls in a club that is already enrolled',
  PARTNER_NEW: 'Partner organization',
  PARTNER_MOD: 'Partner organization (existing club)',
  NEW_PARTNER: 'If your organization is not in the list, type its name here',
  COUNTRY: 'Country where this club meets',   // legacy (replaced by REGION 2026-09; still read from old response rows)
  REGION: 'Region where this club meets',     // required list picker, choices = REGIONS
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
  MENTOR_EMAIL_MOD: 'Mentor email (we send a short confirmation of the change)',
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

/**
 * Canonical region names = the four regional attendance forms. The spelling
 * is load-bearing ('U.S': one dot, no trailing dot) — glow/forms.py REGIONS,
 * the Partners tab and the Jotform sync all use these exact strings;
 * test/gs_parity_test.py fails if the two sides drift.
 */
const REGIONS = ['Africa', 'Asia', 'Latin America', 'U.S'];

/** Script Properties keys (File → Project Settings → Script Properties). */
const PROP = {
  ROSTER_FORM: 'FORM_ROSTER_ID',
  FEEDBACK_FORM: 'FORM_FEEDBACK_ID',
  STAFF_EMAIL: 'STAFF_NOTIFY_EMAIL',   // gets problem reports + the Monday e-mail (ReviewQueue + SF Pending)
  // Automatic Jotform sync (Dispatch.gs): unset = no notification is sent
  SYNC_DISPATCH_REPO: 'SYNC_DISPATCH_REPO',     // owner/name of the GitHub repo
  SYNC_DISPATCH_TOKEN: 'SYNC_DISPATCH_TOKEN',   // fine-grained token scoped to that repo
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

const STATUS = { ACTIVE: 'active', INACTIVE: 'inactive' };

/**
 * Between club and partner in the Salesforce account name of a club whose
 * name another partner's club also has: "<club> - <partner>" (ASCII space,
 * hyphen-minus, space). It is also what that club's entry in the attendance
 * forms' club list says and what question 5 sends, so the same constant is
 * in glow/sync.py (SF_NAME_SEP) — change both, never one
 * (docs/plans/2026-09-30-same-name-clubs.md). Club names may contain it
 * themselves: never split a name on it.
 */
const SF_NAME_SEP = ' - ';
