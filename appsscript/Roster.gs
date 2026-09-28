/**
 * The canonical roster: one row per girl, with a permanent ID.
 *
 * Everything downstream (the attendance forms, and eventually Salesforce)
 * reads this tab rather than the raw form responses. Girls are never deleted
 * here — leaving a club sets status to inactive and stamps removed_date, so
 * history stays intact.
 *
 * Dates are written as plain text ('yyyy-MM-dd', timestamps
 * 'yyyy-MM-dd HH:mm:ss') in the spreadsheet's time zone, on purpose: the
 * offline builder (tools/build_roster_offline.js) writes the same text, so
 * the columns never mix real Date cells with strings, and they sort
 * correctly as text.
 */

const REVIEW_COLS = ['raised', 'issue', 'partner', 'club', 'detail', 'resolved'];
const PARTNER_COLS = ['partner', 'region', 'notes'];
const CLUB_COLS = ['club_code', 'partner', 'club', 'created'];
const AUDIT_COLS = ['when', 'action', 'detail'];
// Appended by tools/auto_sync.py (keep in step with SYNC_LOG_COLS there)
const SYNC_LOG_COLS = ['when', 'trigger', 'region', 'mode', 'creates', 'updates',
                       'rules', 'result', 'detail', 'run_url'];

function today_() {
  return Utilities.formatDate(new Date(),
      SpreadsheetApp.getActive().getSpreadsheetTimeZone(), 'yyyy-MM-dd');
}

function now_() {
  return Utilities.formatDate(new Date(),
      SpreadsheetApp.getActive().getSpreadsheetTimeZone(), 'yyyy-MM-dd HH:mm:ss');
}

function setUpTabs() {
  const ss = SpreadsheetApp.getActive();
  ensureTab_(ss, TAB.ROSTER, ROSTER_COLS);
  ensureTab_(ss, TAB.PARTNERS, PARTNER_COLS);
  ensureTab_(ss, TAB.CLUBS, CLUB_COLS);
  ensureTab_(ss, TAB.REVIEW, REVIEW_COLS);
  ensureTab_(ss, TAB.AUDIT, AUDIT_COLS);
  ensureTab_(ss, TAB.SYNC_LOG, SYNC_LOG_COLS);
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
  ensureTab_(SpreadsheetApp.getActive(), TAB.AUDIT, AUDIT_COLS)
      .appendRow([now_(), action, detail]);
}

/**
 * Add issues to the ReviewQueue, skipping any that are already there and
 * still unresolved. Re-running the rebuild must not fill the tab with copies
 * of the same open question — but two different questions about the same
 * club (two unmatched names, two failed responses) must both appear, so an
 * issue may carry `dedupeKey` to tell them apart. The key is stored as a
 * short tag at the end of the detail column.
 */
function review_(rows) {
  if (!rows.length) return;
  const sheet = ensureTab_(SpreadsheetApp.getActive(), TAB.REVIEW, REVIEW_COLS);
  const identity = function (issue, partner, club, detail) {
    const m = String(detail || '').match(/\[#([^\]]*)\]\s*$/);
    return key_(issue) + '||' + key_(partner) + '||' + key_(club) + '||' + (m ? m[1] : '');
  };
  const open = {};
  if (sheet.getLastRow() > 1) {
    sheet.getRange(2, 1, sheet.getLastRow() - 1, REVIEW_COLS.length).getValues()
        .forEach(function (r) {
          if (!tidy_(r[5])) open[identity(r[1], r[2], r[3], r[4])] = true;
        });
  }
  rows.forEach(function (r) {
    if (r.dedupeKey) r.detail = (r.detail || '') + ' [#' + r.dedupeKey + ']';
  });
  const fresh = rows.filter(function (r) {
    return !open[identity(r.issue, r.partner, r.club, r.detail)];
  });
  if (!fresh.length) return;
  const stamp = today_();
  sheet.getRange(sheet.getLastRow() + 1, 1, fresh.length, REVIEW_COLS.length)
      .setValues(fresh.map(function (r) {
        return [stamp, r.issue, r.partner || '', r.club || '', r.detail || '', ''];
      }));
}

/** Partner → region from the Partners tab ONLY (staff-authoritative; no derived fallback). */
function loadPartnerTabRegions_() {
  const regions = {};
  const sheet = SpreadsheetApp.getActive().getSheetByName(TAB.PARTNERS);
  if (!sheet || sheet.getLastRow() < 2) return regions;
  sheet.getRange(2, 1, sheet.getLastRow() - 1, 2).getValues()
      .forEach(function (row) {
        const partner = tidy_(row[0]), region = tidy_(row[1]);
        if (partner && region) regions[key_(partner)] = region;
      });
  return regions;
}

/** Every partner name on the Partners tab (column A), as typed, blanks left out. */
function loadPartnerNames_() {
  const sheet = SpreadsheetApp.getActive().getSheetByName(TAB.PARTNERS);
  if (!sheet || sheet.getLastRow() < 2) return [];
  return sheet.getRange(2, 1, sheet.getLastRow() - 1, 1).getValues()
      .map(function (row) { return tidy_(row[0]); }).filter(String);
}

/**
 * Partner → region.
 *
 * The Partners tab is authoritative; PARTNER_REGIONS (Regions.gs, derived
 * from the regional attendance forms) fills in only where the tab is blank,
 * so a staff correction in the tab always sticks.
 */
function loadPartnerRegions_() {
  const regions = derivedPartnerRegions_();
  const tab = loadPartnerTabRegions_();
  Object.keys(tab).forEach(function (k) { regions[k] = tab[k]; });
  return regions;
}

/**
 * Re-stamp the region column of every Roster row from the current
 * partner → region mapping. Run after correcting a region in the Partners
 * tab; the rebuild only sets region on rows it creates.
 */
function refreshRosterRegions() {
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getSheetByName(TAB.ROSTER);
  if (!sheet || sheet.getLastRow() < 2) {
    ss.toast('The Roster tab is empty.', 'GLOW', 5);
    return;
  }
  const regions = loadPartnerRegions_();
  const iPartner = ROSTER_COLS.indexOf('partner') + 1;
  const iRegion = ROSTER_COLS.indexOf('region') + 1;
  const n = sheet.getLastRow() - 1;
  const partners = sheet.getRange(2, iPartner, n, 1).getValues();
  const current = sheet.getRange(2, iRegion, n, 1).getValues();
  let changed = 0, missing = 0;
  const updated = partners.map(function (row, i) {
    const region = regions[key_(row[0])] || '';
    if (!region) missing++;
    if (region !== tidy_(current[i][0])) changed++;
    return [region];
  });
  sheet.getRange(2, iRegion, n, 1).setValues(updated);
  const summary = changed + ' of ' + n + ' rows changed' +
      (missing ? ', ' + missing + ' rows still have no region' : '');
  audit_('refreshRosterRegions', summary);
  if (changed) tryNotifySync_('refreshRosterRegions');
  ss.toast(summary, 'GLOW regions', 10);
}

/**
 * Existing roster rows, indexed for lookup.
 *
 * added_date / removed_date are written as 'yyyy-MM-dd' text, but Sheets may
 * store such text as a Date cell; a Date cell comes back here as that day in
 * the SPREADSHEET's time zone (the zone today_() writes in — never the
 * script's), so the replay guard (RosterOps.gs staysRemoved_) compares days.
 * Text cells are left as they are.
 */
function loadRoster_() {
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getSheetByName(TAB.ROSTER);
  const rows = [];
  if (!sheet || sheet.getLastRow() < 2) return { rows: rows, byClub: {} };
  const values = sheet.getRange(2, 1, sheet.getLastRow() - 1,
                                ROSTER_COLS.length).getValues();
  const zone = ss.getSpreadsheetTimeZone();
  const byClub = {};
  values.forEach(function (v, i) {
    const row = {};
    ROSTER_COLS.forEach(function (c, j) { row[c] = v[j]; });
    ['added_date', 'removed_date'].forEach(function (c) {
      const cell = row[c];
      if (cell instanceof Date && !isNaN(cell.getTime())) {
        row[c] = Utilities.formatDate(cell, zone, 'yyyy-MM-dd');
      }
    });
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
  const ss = SpreadsheetApp.getActive();
  // IDs are minted here; two overlapping runs would hand out the same numbers
  const lock = LockService.getDocumentLock();
  if (!lock.tryLock(30000)) {
    ss.toast('Another rebuild is still running - try again in a minute.', 'GLOW', 8);
    return;
  }
  try {
    return rebuildRosterLocked_(ss);
  } finally {
    lock.releaseLock();
  }
}

function rebuildRosterLocked_(ss) {
  setUpTabs();
  const clubs = readResponses_();
  const regions = loadPartnerRegions_();
  const existing = loadRoster_();
  const state = loadIdState_();
  const today = today_();

  const toAppend = [], reactivate = [], issues = [], partnersSeen = {};
  const noRegion = {};

  clubs.forEach(function (entry) {
    partnersSeen[key_(entry.partner)] = entry.partner;
    const ck = key_(entry.partner) + '||' + key_(entry.club);
    const region = regions[key_(entry.partner)] || '';
    if (!region) noRegion[key_(entry.partner)] = entry.partner;
    entry.source = TAB.RESPONSES + '!' + entry.sourceRow;

    const plan = planClub_(entry, existing.byClub[ck] || [], state, region, today);
    Array.prototype.push.apply(toAppend, plan.toAppend);
    Array.prototype.push.apply(reactivate, plan.reactivate);
    Array.prototype.push.apply(issues, plan.issues);
  });

  Object.keys(noRegion).forEach(function (k) {
    issues.push(noRegionIssue_(noRegion[k]));
  });

  applyRosterPlan_(ss, { toAppend: toAppend, reactivate: reactivate, deactivate: [] }, today);
  saveClubRegistry_(state.registry);
  seedPartners_(partnersSeen);
  review_(issues);

  const missingRegion = Object.keys(noRegion).length;
  const summary = clubs.length + ' clubs, ' + toAppend.length + ' new girls, ' +
      reactivate.length + ' reactivated, ' + issues.length + ' for review' +
      (missingRegion ? ', ' + missingRegion + ' partner(s) missing a region' : '');
  audit_('rebuildRosterFromResponses', summary);
  if (toAppend.length || reactivate.length) tryNotifySync_('rebuildRosterFromResponses');
  ss.toast(summary, 'GLOW roster', 10);
  return summary;
}

function noRegionIssue_(partner) {
  return {
    issue: 'Partner has no region', partner: partner, club: '',
    detail: 'Girls were added without a region, so they will not reach any ' +
        'regional attendance form. Fill in the region on the Partners tab, ' +
        'then run GLOW → Refresh regions.',
  };
}

/**
 * Write a plan from RosterOps.gs to the Roster tab: append new rows, flip
 * reactivated rows back to active, retire deactivated rows (removed_date =
 * plan.removedOn — the day a Club Roster Form removal was sent — else today).
 * Rows in `reactivate` / `deactivate` carry _sheetRow from loadRoster_.
 */
function applyRosterPlan_(ss, plan, today) {
  const sheet = ensureTab_(ss, TAB.ROSTER, ROSTER_COLS);
  setRowsStatus_(sheet, plan.reactivate, STATUS.ACTIVE, '');
  setRowsStatus_(sheet, plan.deactivate, STATUS.INACTIVE, plan.removedOn || today);
  if (plan.toAppend.length) {
    sheet.getRange(sheet.getLastRow() + 1, 1, plan.toAppend.length,
                   ROSTER_COLS.length).setValues(plan.toAppend);
  }
}

function setRowsStatus_(sheet, rows, status, removedDate) {
  if (!rows.length) return;
  const iStatus = ROSTER_COLS.indexOf('status') + 1;
  const iRemoved = ROSTER_COLS.indexOf('removed_date') + 1;
  const col = function (i) { return String.fromCharCode(64 + i); };
  sheet.getRangeList(rows.map(function (r) { return col(iStatus) + r._sheetRow; }))
      .setValue(status);
  sheet.getRangeList(rows.map(function (r) { return col(iRemoved) + r._sheetRow; }))
      .setValue(removedDate);
}

function saveClubRegistry_(registry) {
  if (!registry.added.length) return;
  const sheet = ensureTab_(SpreadsheetApp.getActive(), TAB.CLUBS, CLUB_COLS);
  const stamp = today_();
  sheet.getRange(sheet.getLastRow() + 1, 1, registry.added.length, CLUB_COLS.length)
      .setValues(registry.added.map(function (e) {
        return [e.code, e.partner, e.club, stamp];
      }));
  registry.added.length = 0;
}

/**
 * Add any partner we have seen to the Partners tab. Region for a new row or
 * a BLANK region cell: the region chosen on the Club Roster Form
 * (formRegions, already validated against REGIONS) first, else the map
 * derived from the regional attendance forms (Regions.gs); a blank note is
 * explained either way. Anything staff have typed stays.
 * formRegions: optional {key_(partner): canonical region}.
 */
function seedPartners_(partnersSeen, formRegions) {
  formRegions = formRegions || {};
  const sheet = ensureTab_(SpreadsheetApp.getActive(), TAB.PARTNERS, PARTNER_COLS);
  const derived = derivedPartnerRegions_(), notes = {};
  Object.keys(PARTNER_REGIONS).forEach(function (p) {
    notes[key_(p)] = PARTNER_REGION_NOTES[p] || '';
  });
  const regionFor = function (k) { return formRegions[k] || derived[k] || ''; };
  const noteFor = function (k) {
    return formRegions[k] ? 'region chosen on the Club Roster Form' : (notes[k] || '');
  };

  const known = {};
  if (sheet.getLastRow() > 1) {
    const n = sheet.getLastRow() - 1;
    const rows = sheet.getRange(2, 1, n, PARTNER_COLS.length).getValues();
    rows.forEach(function (r, i) {
      const k = key_(r[0]);
      if (!k) return;
      known[k] = true;
      if (!tidy_(r[1]) && regionFor(k)) {
        sheet.getRange(i + 2, 2).setValue(regionFor(k));
        if (!tidy_(r[2])) sheet.getRange(i + 2, 3).setValue(noteFor(k));
      }
    });
  }
  const missing = Object.keys(partnersSeen)
      .filter(function (k) { return k && !known[k]; })
      .map(function (k) {
        return [partnersSeen[k], regionFor(k),
                regionFor(k) ? noteFor(k) : 'region needed'];
      });
  if (missing.length) {
    sheet.getRange(sheet.getLastRow() + 1, 1, missing.length, PARTNER_COLS.length)
        .setValues(missing);
  }
}
