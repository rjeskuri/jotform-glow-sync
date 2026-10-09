/**
 * Permanent identifiers for girls.
 *
 * Format: CLUBCODE-LASTCODE-NNN   e.g. DEMOCLUB-SAMPLE-001
 *
 * The ID is opaque and permanent. Once a girl has one it never changes — not
 * when her club is renamed, not when the club splits, not when she leaves and
 * returns. A club code that no longer matches the club's current name is
 * expected and harmless; the ClubRegistry, not the club's name, is what makes
 * the code authoritative.
 *
 * Numbers are never reused: if a girl is removed, her number stays retired so
 * historical Salesforce records can never point at the wrong person.
 */

/**
 * Look up (or mint) the permanent code for a club.
 *
 * Matching is by (partner, club) case-insensitively. A club renamed or moved
 * with tools/rename_club.py keeps its original code: the tool rewrites its
 * ClubRegistry row together with its Roster rows.
 */
function clubCode_(registry, partner, club) {
  const k = clubKey_(partner, club);
  if (registry.byKey[k]) return registry.byKey[k].code;

  let base = asciiCode_(club).slice(0, 8);
  if (!base) base = 'CLUB';
  let code = base, n = 1;
  while (registry.byCode[code]) { n += 1; code = base.slice(0, 7) + n; }

  const entry = { code: code, partner: partner, club: club };
  registry.byKey[k] = entry;
  registry.byCode[code] = entry;
  registry.added.push(entry);
  return code;
}

/**
 * Mint the next unused girl ID for a club + surname.
 *
 * `sequence` maps "CLUBCODE-LASTCODE" to the highest number handed out so
 * far, including numbers belonging to girls who have since left.
 */
function mintGirlId_(sequence, clubCodeValue, fullName) {
  const lastCode = asciiCode_(lastName_(fullName)).slice(0, 12) || 'X';
  const stem = clubCodeValue + '-' + lastCode;
  const next = (sequence[stem] || 0) + 1;
  sequence[stem] = next;
  return stem + '-' + ('00' + next).slice(-3);
}

/**
 * Rebuild the registry and the sequence high-water marks from existing data,
 * so a re-run never re-issues an ID that is already in use.
 */
function loadIdState_() {
  const ss = SpreadsheetApp.getActive();
  const registry = { byKey: {}, byCode: {}, added: [] };
  const sequence = {};

  const clubSheet = ss.getSheetByName(TAB.CLUBS);
  if (clubSheet && clubSheet.getLastRow() > 1) {
    clubSheet.getRange(2, 1, clubSheet.getLastRow() - 1, 3).getValues()
        .forEach(function (row) {
          const code = tidy_(row[0]), partner = tidy_(row[1]), club = tidy_(row[2]);
          if (!code) return;
          const entry = { code: code, partner: partner, club: club };
          registry.byKey[clubKey_(partner, club)] = entry;
          registry.byCode[code] = entry;
        });
  }

  const rosterSheet = ss.getSheetByName(TAB.ROSTER);
  if (rosterSheet && rosterSheet.getLastRow() > 1) {
    rosterSheet.getRange(2, 1, rosterSheet.getLastRow() - 1, 1).getValues()
        .forEach(function (row) {
          const id = tidy_(row[0]);
          const m = id.match(/^(.*)-(\d+)$/);
          if (!m) return;
          const stem = m[1], n = parseInt(m[2], 10);
          if (!sequence[stem] || n > sequence[stem]) sequence[stem] = n;
        });
  }
  return { registry: registry, sequence: sequence };
}
