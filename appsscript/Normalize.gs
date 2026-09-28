/**
 * Turning what partners actually type into something a computer can match on.
 *
 * Ported from sync_attendance_form.py (parse_roster / read_sheet) so both
 * tools agree exactly — the parity harness depends on this.
 */

/** Invisible characters that survive copy/paste from Word, WhatsApp, PDFs. */
const INVISIBLE = /[\u200B\u200C\u200D\u200E\u200F\u2060\uFEFF]/g;

/** Collapse runs of whitespace and trim. */
function tidy_(s) {
  return String(s == null ? '' : s).replace(INVISIBLE, '').trim()
      .replace(/\s+/g, ' ');
}

/** Case-insensitive comparison key. */
function key_(s) {
  return tidy_(s).toLowerCase();
}

/**
 * Strip diacritics and punctuation for ID codes: "Sánchez" → "SANCHEZ".
 * Names keep their accents in the Roster; only the ID code is folded.
 */
function asciiCode_(s) {
  return tidy_(s).normalize('NFKD').replace(/[\u0300-\u036F]/g, '')
      .toUpperCase().replace(/[^A-Z0-9]/g, '');
}

/**
 * Parse one roster cell into girls' names.
 *
 * Handles: one name per line, optional "1." / "1)" numbering, stray bullets
 * and trailing punctuation, invisible characters, blank lines.
 *
 * Returns {names, duplicates}. A duplicate means the same full name was
 * listed twice — usually two different girls who need distinguishing in the
 * sheet, so the caller must not silently merge them.
 */
function parseRoster_(cell) {
  const names = [];
  String(cell == null ? '' : cell).split(/\r?\n/).forEach(function (line) {
    const cleaned = tidy_(line.replace(INVISIBLE, ''))
        .replace(/^\s*\d+[.)]?\s*/, '')      // leading "1." / "12)"
        .replace(/^[-•*]\s*/, '')            // bullets
        .replace(/^[\s,.\-]+|[\s,.\-]+$/g, '');
    if (cleaned) names.push(tidy_(cleaned));
  });

  const seen = {}, unique = [], duplicates = [];
  names.forEach(function (n) {
    const k = n.toLowerCase();
    if (seen[k]) duplicates.push(n);
    else { seen[k] = true; unique.push(n); }
  });
  return { names: unique, duplicates: duplicates };
}

/** Last whitespace-separated token; single-token names use the whole name. */
function lastName_(fullName) {
  const parts = tidy_(fullName).split(' ');
  return parts[parts.length - 1] || tidy_(fullName);
}

/**
 * Read the raw responses tab into one entry per club.
 *
 * Club identity is (partner, club) compared case-insensitively, so a partner
 * re-submitting "GLOW Club" after "Glow Club" updates the same club rather
 * than creating a second one. The LAST submission wins and its spelling is
 * the one kept.
 */
function readResponses_() {
  const sheet = SpreadsheetApp.getActive().getSheetByName(TAB.RESPONSES);
  if (!sheet) throw new Error('No tab named "' + TAB.RESPONSES + '"');
  const values = sheet.getDataRange().getValues();
  if (values.length < 2) return [];

  const header = values[0].map(function (h) { return String(h).toLowerCase(); });
  function col(fragment) {
    for (let i = 0; i < header.length; i++) {
      if (header[i].indexOf(fragment) !== -1) return i;
    }
    throw new Error('No column containing "' + fragment + '" in ' +
                    TAB.RESPONSES);
  }
  const iPartner = col(RESPONSE_COLS.partner);
  const iClub = col(RESPONSE_COLS.club);
  const iRoster = col(RESPONSE_COLS.roster);

  const byIdentity = {};
  for (let r = 1; r < values.length; r++) {
    const row = values[r];
    const partner = tidy_(row[iPartner]);
    const club = tidy_(row[iClub]);
    // a row without a partner or a club cannot be placed anywhere (and a
    // blank partner would otherwise seed a nameless Partners row)
    if (!partner || !club) continue;
    const parsed = parseRoster_(row[iRoster]);
    if (!parsed.names.length) continue;
    byIdentity[key_(partner) + '||' + key_(club)] = {
      partner: partner,
      club: club,
      names: parsed.names,
      duplicates: parsed.duplicates,
      sourceRow: r + 1,
    };
  }
  return Object.keys(byIdentity).map(function (k) { return byIdentity[k]; });
}

// ------------------------------------------ Google Form text (not in Python)
// The Club Roster Form and the problem form are public: what they carry is
// written to the sheet as typed, and setValues reads a leading = (or + - @)
// as a formula. The enrollment import keeps parseRoster_ as it is (parity
// with sync_attendance_form.py); these apply to Google Form answers only.

/** tidy_, then without the leading run of = + - @ and spaces: never a formula in the sheet. */
function sheetText_(s) {
  return tidy_(s).replace(/^[\s=+\-@]+/, '');
}

/**
 * parseRoster_ for a Google Form answer: every name (and every repeat) also
 * passes sheetText_, and names the strip makes equal count as repeats.
 */
function parseFormRoster_(cell) {
  const parsed = parseRoster_(cell);
  const seen = {}, names = [];
  const duplicates = parsed.duplicates.map(sheetText_).filter(String);
  parsed.names.forEach(function (n) {
    const safe = sheetText_(n);
    if (!safe) return;
    if (seen[safe.toLowerCase()]) duplicates.push(safe);
    else { seen[safe.toLowerCase()] = true; names.push(safe); }
  });
  return { names: names, duplicates: duplicates };
}

/** key_ with accents removed ("Lucía" → "lucia"): for spotting near-duplicates, never for identity. */
function foldKey_(s) {
  return key_(s).normalize('NFKD').replace(/[\u0300-\u036F]/g, '');
}
