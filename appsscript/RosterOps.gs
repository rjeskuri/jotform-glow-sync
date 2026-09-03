/**
 * The decisions behind every roster change, with no spreadsheet access.
 *
 * Both the rebuild (Roster.gs) and the form handlers (FormHandlers.gs) call
 * these, and so do the offline builder (tools/build_roster_offline.js) and
 * the tests — so what a change *means* is defined exactly once. Callers apply
 * the returned plan to the sheet.
 *
 * A "row" here is an object keyed by ROSTER_COLS (plus whatever the caller
 * attaches, e.g. _sheetRow). Status compares against STATUS.* strings.
 * Every plan has the same shape: {toAppend, reactivate, deactivate, issues}.
 * Issues may carry `dedupeKey` so the ReviewQueue can tell two different
 * questions about the same club apart.
 */

function duplicateNamesIssue_(entry) {
  return {
    issue: 'Same name listed twice',
    partner: entry.partner, club: entry.club,
    detail: entry.duplicates.join(', ') +
        ' — if these are different girls, add something to tell them ' +
        'apart (e.g. "Jane Doe (A)" and "Jane Doe (B)"), then submit again.',
    dedupeKey: entry.duplicates.map(key_).join('|'),
  };
}

/**
 * Plan what a club's full roster submission does to the Roster.
 *
 * Girls already on file keep their row and ID; inactive ones are
 * reactivated; new names are minted; girls on file but absent from this
 * submission are only REPORTED (a partner re-submitting a short list must
 * not silently retire two thirds of a club).
 *
 * entry:   {partner, club, names, duplicates, source}
 * current: this club's existing rows (any status)
 * state:   from loadIdState_ (registry + sequence), mutated as IDs are minted
 */
function planClub_(entry, current, state, region, today) {
  const issues = [], toAppend = [], reactivate = [];

  if (entry.duplicates && entry.duplicates.length) issues.push(duplicateNamesIssue_(entry));

  const code = clubCode_(state.registry, entry.partner, entry.club);
  const byName = {};
  current.forEach(function (row) { byName[key_(row.full_name)] = row; });

  entry.names.forEach(function (name) {
    const found = byName[key_(name)];
    if (found) {
      if (found.status === STATUS.INACTIVE) reactivate.push(found);
      return;
    }
    toAppend.push(newRosterRow_(state, code, entry, region, name, today));
  });

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

  return { code: code, toAppend: toAppend, reactivate: reactivate, deactivate: [],
           issues: issues, vanished: vanished };
}

/**
 * Plan a Roster Modification submission: names to add and names to remove.
 *
 * Adds: on file and active → noted as already there; on file and inactive →
 * reactivated (same ID); unknown → minted. Removes: matched case-
 * insensitively against the club's ACTIVE girls → deactivated; already
 * inactive → noted, nothing to do; anything that matches nobody is returned
 * with the closest candidates (for staff, via the ReviewQueue — never for the
 * mentor email). Nothing is ever deleted.
 *
 * entry: {partner, club, adds, removes, duplicates, source}
 */
function planModification_(entry, current, state, region, today) {
  const plan = { toAppend: [], reactivate: [], deactivate: [], issues: [],
                 alreadyActive: [], alreadyInactive: [], keptBoth: [], unmatched: [] };
  if (entry.duplicates && entry.duplicates.length) plan.issues.push(duplicateNamesIssue_(entry));

  const code = clubCode_(state.registry, entry.partner, entry.club);
  const byName = {};
  current.forEach(function (row) { byName[key_(row.full_name)] = row; });
  const added = {};

  (entry.adds || []).forEach(function (name) {
    const found = byName[key_(name)];
    added[key_(name)] = true;
    if (found) {
      if (found.status === STATUS.INACTIVE) plan.reactivate.push(found);
      else plan.alreadyActive.push(name);
      return;
    }
    plan.toAppend.push(newRosterRow_(state, code, entry, region, name, today));
  });

  const activeNames = current.filter(function (r) { return r.status === STATUS.ACTIVE; })
      .map(function (r) { return r.full_name; });
  (entry.removes || []).forEach(function (name) {
    const found = byName[key_(name)];
    if (added[key_(name)]) { plan.keptBoth.push(name); return; }
    if (found && found.status === STATUS.ACTIVE) { plan.deactivate.push(found); return; }
    if (found) { plan.alreadyInactive.push(name); return; }   // already removed earlier
    plan.unmatched.push({ name: name, candidates: closestNames_(name, activeNames) });
  });

  plan.unmatched.forEach(function (u) {
    plan.issues.push({
      issue: 'Removal did not match anyone',
      partner: entry.partner, club: entry.club,
      detail: '"' + u.name + '" is not on this club\'s active roster' +
          (u.candidates.length ? '. Closest names on file: ' + u.candidates.join('; ') : '') +
          '. Nobody was removed; the mentor was told we would check.',
      dedupeKey: key_(u.name),
    });
  });
  plan.code = code;
  return plan;
}

/** One new Roster row, ID minted now. */
function newRosterRow_(state, code, entry, region, name, today) {
  return [
    mintGirlId_(state.sequence, code, name), entry.partner, entry.club,
    region, name, lastName_(name), STATUS.ACTIVE, today, '',
    entry.source || '',
  ];
}

/**
 * Up to three names sharing the most words with `name` (for "did you mean").
 * Word overlap is enough here: a mentor typing "Amina Hassan" when the
 * roster says "Amina Hassan Ali" should get that suggestion.
 */
function closestNames_(name, names) {
  const want = key_(name).split(' ').filter(String);
  if (!want.length) return [];
  const scored = names.map(function (n) {
    const have = key_(n).split(' ');
    const shared = want.filter(function (w) { return have.indexOf(w) !== -1; }).length;
    return { n: n, score: shared / Math.max(want.length, have.length) };
  }).filter(function (s) { return s.score > 0; });
  scored.sort(function (a, b) { return b.score - a.score || a.n.localeCompare(b.n); });
  return scored.slice(0, 3).map(function (s) { return s.n; });
}

// -------------------------------------------------------------- regions
/** The canonical spelling for a region answer, or '' if it is not one of REGIONS. */
function canonicalRegion_(answer) {
  const k = key_(answer);
  if (!k) return '';
  for (let i = 0; i < REGIONS.length; i++) {
    if (key_(REGIONS[i]) === k) return REGIONS[i];
  }
  return '';
}

/**
 * The region a new-club submission lands with. Precedence: the Partners tab
 * (staff-typed, used verbatim) > the form's Region answer (validated against
 * REGIONS, canonical spelling stored) > the derived Regions.gs map > ''
 * (which callers turn into noRegionIssue_).
 */
function chooseRegion_(tabRegion, formAnswer, derivedRegion) {
  return tidy_(tabRegion) || canonicalRegion_(formAnswer) || tidy_(derivedRegion) || '';
}

/** key_(partner) → derived region (Regions.gs only; the Partners tab is read separately). */
function derivedPartnerRegions_() {
  const regions = {};
  Object.keys(PARTNER_REGIONS).forEach(function (p) {
    if (PARTNER_REGIONS[p]) regions[key_(p)] = PARTNER_REGIONS[p];
  });
  return regions;
}
