/**
 * The canonical roster: one row per girl, with a permanent ID.
 *
 * Everything downstream (the attendance forms, and eventually Salesforce)
 * reads this tab rather than the raw form responses. Girls are never deleted
 * here — leaving a club sets status to inactive and stamps removed_date, so
 * history stays intact.
 */

function setUpTabs() {
  const ss = SpreadsheetApp.getActive();
  ensureTab_(ss, TAB.ROSTER, ROSTER_COLS);
  ensureTab_(ss, TAB.PARTNERS, ['partner', 'region', 'notes']);
  ensureTab_(ss, TAB.CLUBS, ['club_code', 'partner', 'club', 'created']);
  ensureTab_(ss, TAB.REVIEW,
             ['raised', 'issue', 'partner', 'club', 'detail', 'resolved']);
  ensureTab_(ss, TAB.AUDIT, ['when', 'action', 'detail']);
  SpreadsheetApp.getActive().toast('Tabs are ready.', 'GLOW', 5);
}

function ensureTab_(ss, name, headers) {
  let sheet = ss.getSheetByName(name);
  if (!sheet) sheet = ss.insertSheet(name);
  if (sheet.getLastRow() === 0) {
    sheet.getRange(1, 1, 1, headers.length).setValues([headers])
        .setFontWeight('bold');
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function audit_(action, detail) {
  ensureTab_(SpreadsheetApp.getActive(), TAB.AUDIT, ['when', 'action', 'detail'])
      .appendRow([new Date(), action, detail]);
}

function review_(rows) {
  if (!rows.length) return;
  const sheet = ensureTab_(SpreadsheetApp.getActive(), TAB.REVIEW,
      ['raised', 'issue', 'partner', 'club', 'detail', 'resolved']);
  const now = new Date();
  sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, 6).setValues(
      rows.map(function (r) {
        return [now, r.issue, r.partner || '', r.club || '', r.detail || '', ''];
      }));
}

/** Partner → region, from the Partners tab. */
function loadPartnerRegions_() {
  const sheet = SpreadsheetApp.getActive().getSheetByName(TAB.PARTNERS);
  const regions = {};
  if (!sheet || sheet.getLastRow() < 2) return regions;
  sheet.getRange(2, 1, sheet.getLastRow() - 1, 2).getValues()
      .forEach(function (row) {
        const partner = tidy_(row[0]);
        if (partner) regions[key_(partner)] = tidy_(row[1]);
      });
  return regions;
}

/** Existing roster rows, indexed for lookup. */
function loadRoster_() {
  const sheet = SpreadsheetApp.getActive().getSheetByName(TAB.ROSTER);
  const rows = [];
  if (!sheet || sheet.getLastRow() < 2) return { rows: rows, byClub: {} };
  const values = sheet.getRange(2, 1, sheet.getLastRow() - 1,
                                ROSTER_COLS.length).getValues();
  const byClub = {};
  values.forEach(function (v, i) {
    const row = {};
    ROSTER_COLS.forEach(function (c, j) { row[c] = v[j]; });
    row._sheetRow = i + 2;
    row._ck = key_(row.partner) + '||' + key_(row.club);
    rows.push(row);
    if (!byClub[row._ck]) byClub[row._ck] = [];
    byClub[row._ck].push(row);
  });
  return { rows: rows, byClub: byClub };
}

/**
 * Rebuild the Roster tab from the raw enrollment responses.
 *
 * Safe to re-run: existing girls keep their IDs, new girls are appended, and
 * girls who have disappeared from a club's latest submission are reported for
 * review rather than removed automatically (a partner re-submitting a short
 * roster must not silently retire two thirds of a club).
 */
function rebuildRosterFromResponses() {
  setUpTabs();
  const ss = SpreadsheetApp.getActive();
  const clubs = readResponses_();
  const regions = loadPartnerRegions_();
  const existing = loadRoster_();
  const state = loadIdState_();
  const today = new Date();

  const toAppend = [], issues = [], partnersSeen = {};
  let newGirls = 0, reactivated = 0, missingRegion = 0;

  clubs.forEach(function (entry) {
    partnersSeen[key_(entry.partner)] = entry.partner;
    const ck = key_(entry.partner) + '||' + key_(entry.club);
    const region = regions[key_(entry.partner)] || '';
    if (!region) missingRegion++;

    if (entry.duplicates.length) {
      issues.push({
        issue: 'Same name listed twice',
        partner: entry.partner, club: entry.club,
        detail: entry.duplicates.join(', ') +
            ' — if these are different girls, add something to tell them ' +
            'apart in the sheet (e.g. "Anh Nguyen (A)"), then re-run.',
      });
    }

    const code = clubCode_(state.registry, entry.partner, entry.club);
    const current = existing.byClub[ck] || [];
    const byName = {};
    current.forEach(function (row) { byName[key_(row.full_name)] = row; });

    entry.names.forEach(function (name) {
      const found = byName[key_(name)];
      if (found) {
        if (found.status === STATUS.INACTIVE) {
          // she came back: same girl, same ID
          const sheet = ss.getSheetByName(TAB.ROSTER);
          sheet.getRange(found._sheetRow, ROSTER_COLS.indexOf('status') + 1)
              .setValue(STATUS.ACTIVE);
          sheet.getRange(found._sheetRow,
                         ROSTER_COLS.indexOf('removed_date') + 1).setValue('');
          reactivated++;
        }
        return;
      }
      toAppend.push([
        mintGirlId_(state.sequence, code, name), entry.partner, entry.club,
        region, name, lastName_(name), STATUS.ACTIVE, today, '',
        TAB.RESPONSES + '!' + entry.sourceRow,
      ]);
      newGirls++;
    });

    // girls on file but absent from the newest submission
    const submitted = {};
    entry.names.forEach(function (n) { submitted[key_(n)] = true; });
    const vanished = current.filter(function (row) {
      return row.status === STATUS.ACTIVE && !submitted[key_(row.full_name)];
    });
    if (vanished.length) {
      issues.push({
        issue: 'Girls missing from the latest enrollment',
        partner: entry.partner, club: entry.club,
        detail: vanished.length + ' girl(s) on file are not in the newest ' +
            'submission. They are still active — use the Roster Modification ' +
            'form to remove anyone who has actually left.',
      });
    }
  });

  if (toAppend.length) {
    const sheet = ss.getSheetByName(TAB.ROSTER);
    sheet.getRange(sheet.getLastRow() + 1, 1, toAppend.length,
                   ROSTER_COLS.length).setValues(toAppend);
  }
  saveClubRegistry_(state.registry);
  seedPartners_(partnersSeen);
  review_(issues);

  const summary = clubs.length + ' clubs, ' + newGirls + ' new girls, ' +
      reactivated + ' reactivated, ' + issues.length + ' for review' +
      (missingRegion ? ', ' + missingRegion + ' clubs missing a region' : '');
  audit_('rebuildRosterFromResponses', summary);
  ss.toast(summary, 'GLOW roster', 10);
  return summary;
}

function saveClubRegistry_(registry) {
  if (!registry.added.length) return;
  const sheet = ensureTab_(SpreadsheetApp.getActive(), TAB.CLUBS,
      ['club_code', 'partner', 'club', 'created']);
  const now = new Date();
  sheet.getRange(sheet.getLastRow() + 1, 1, registry.added.length, 4).setValues(
      registry.added.map(function (e) {
        return [e.code, e.partner, e.club, now];
      }));
  registry.added.length = 0;
}

/** Add any partner we have seen to the Partners tab so staff can set regions. */
function seedPartners_(partnersSeen) {
  const sheet = ensureTab_(SpreadsheetApp.getActive(), TAB.PARTNERS,
      ['partner', 'region', 'notes']);
  const known = {};
  if (sheet.getLastRow() > 1) {
    sheet.getRange(2, 1, sheet.getLastRow() - 1, 1).getValues()
        .forEach(function (r) { known[key_(r[0])] = true; });
  }
  const missing = Object.keys(partnersSeen)
      .filter(function (k) { return !known[k]; })
      .map(function (k) { return [partnersSeen[k], '', 'region needed']; });
  if (missing.length) {
    sheet.getRange(sheet.getLastRow() + 1, 1, missing.length, 3)
        .setValues(missing);
  }
}
