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

/** Tab names. The raw responses tab is whatever Google Forms created. */
const TAB = {
  RESPONSES: 'Form Responses 1',  // raw enrollment responses (read-only to us)
  ROSTER: 'Roster',               // canonical: one row per girl
  PARTNERS: 'Partners',           // partner → region, filled in by staff
  CLUBS: 'ClubRegistry',          // club → immutable club code
  REVIEW: 'ReviewQueue',          // anything needing a human decision
  AUDIT: 'Audit',                 // what the scripts did, and when
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
  WORKING_COPY: '262352490535154',  // upgraded; template for regional clones
  MASTER: '260555608160556',        // old architecture, being retired
  AFRICA: '260703905772560',
  ASIA: '260704198384564',
  LATIN_AMERICA: '260704170003542',
  US: '260703912140547',
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
