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
 * Every plan has the same shape: {toAppend, reactivate, deactivate,
 * keptRemoved, issues}. Issues may carry `dedupeKey` so the ReviewQueue can
 * tell two different questions about the same club apart.
 *
 * The replay guard (BACKLOG 41, docs/plans/2026-09-28-replay-guard.md): an
 * entry may carry `submitted`, the day its form response was sent
 * ('yyyy-MM-dd'). A girl removed AFTER that day is never put back by it (the
 * 2026-09-13 replay of an 08-31 response reactivated 20 girls removed on
 * 09-12). No `submitted` (the rebuild, the offline builder) = no guard.
 */

function duplicateNamesIssue_(entry) {
  return {
    issue: 'Same name listed twice',
    partner: entry.partner, club: entry.club,
    detail: entry.duplicates.join(', ') +
        ' — listed more than once, so only one girl is on the Roster. If they are ' +
        'different girls, add the other on the Club Roster Form ("' + Q.ACTION_MOD +
        '") with something that tells them apart, e.g. "Jane Doe (B)".',
    dedupeKey: entry.duplicates.map(key_).join('|'),
  };
}

/** 'yyyy-MM-dd' at the start of a cell's text ('2026-09-12', '2026-09-12 10:00:00'), else ''. */
function dayOf_(v) {
  const m = /^(\d{4}-\d{2}-\d{2})(?!\d)/.exec(tidy_(v));
  return m ? m[1] : '';
}

/**
 * entry.submitted as a day, or '' when it is missing or blank (= no guard).
 * Anything else that is not exactly 'yyyy-MM-dd' is refused: a guard that
 * silently switched itself off would be worse than a failed response (which
 * is logged as ERROR and can be retried).
 */
function submittedDay_(entry) {
  const raw = entry.submitted;
  if (raw == null || tidy_(raw) === '') return '';
  const day = dayOf_(raw);
  if (!day || tidy_(raw) !== day) {
    throw new Error('submitted must be yyyy-MM-dd, got "' + tidy_(raw).slice(0, 40) + '"');
  }
  return day;
}

/**
 * True if an inactive girl named by a response sent on `sentDay` must stay
 * removed: her removed_date is a later day. Same day or earlier → she comes
 * back, as always (removed_date has no time of day). No readable removal day
 * → she stays removed only if the response was sent before today. No
 * sentDay → never (today's behaviour).
 */
function staysRemoved_(row, sentDay, today) {
  if (!sentDay) return false;
  const removed = dayOf_(row.removed_date);
  if (removed) return removed > sentDay;
  return sentDay < today;
}

/**
 * The removed_date a response's removals are stamped with: the day it was
 * SENT (never after today), so both sides of staysRemoved_ are sent days. If
 * it were the day it ran, a REMOVE and a later ADD for the same girl, both
 * run late (a trigger outage, then the menu), would keep her removed. A
 * response processed on time is sent today, so this is today, as before.
 */
function removedOnDay_(sentDay, today) {
  return sentDay && sentDay < today ? sentDay : today;
}

/**
 * The ReviewQueue item for one response that named girls removed after it
 * was sent: Roster row numbers, never names; tagged with the response row,
 * so a retry adds no second item and the Monday e-mail can show the tag.
 */
function keptRemovedIssue_(entry, sentDay, kept) {
  const rows = kept.map(function (k) { return k.row._sheetRow; }).filter(Boolean);
  return {
    issue: 'Removed girls not put back by an older response',
    partner: entry.partner, club: entry.club,
    detail: (entry.source ? entry.source + ' ' : '') + '(sent ' + sentDay + '): ' +
        kept.length + ' girl(s) it lists were removed after it was sent (or on a day the ' +
        'Roster does not record), so they stay removed' +
        (rows.length ? ' — Roster rows ' + rows.join(', ') : '') +
        '. If one has really rejoined, ADD her on the Club Roster Form ("' + Q.ACTION_MOD +
        '"); otherwise mark resolved.',
    dedupeKey: entry.source || '',
  };
}

/**
 * Plan what a club's full roster submission does to the Roster.
 *
 * Girls already on file keep their row and ID; inactive ones are
 * reactivated — unless removed after the response was sent (keptRemoved,
 * see staysRemoved_); new names are minted; girls on file but absent from
 * this submission are only REPORTED (a partner re-submitting a short list
 * must not silently retire two thirds of a club).
 *
 * entry:   {partner, club, names, duplicates, source, submitted (optional)}
 * current: this club's existing rows (any status)
 * state:   from loadIdState_ (registry + sequence), mutated as IDs are minted
 */
function planClub_(entry, current, state, region, today) {
  const issues = [], toAppend = [], reactivate = [], keptRemoved = [];
  const sentDay = submittedDay_(entry);

  if (entry.duplicates && entry.duplicates.length) issues.push(duplicateNamesIssue_(entry));

  const code = clubCode_(state.registry, entry.partner, entry.club);
  const byName = {};
  current.forEach(function (row) { byName[key_(row.full_name)] = row; });

  entry.names.forEach(function (name) {
    const found = byName[key_(name)];
    if (found) {
      if (found.status !== STATUS.INACTIVE) return;
      if (staysRemoved_(found, sentDay, today)) keptRemoved.push({ name: name, row: found });
      else reactivate.push(found);
      return;
    }
    toAppend.push(newRosterRow_(state, code, entry, region, name, today));
  });
  if (keptRemoved.length) issues.push(keptRemovedIssue_(entry, sentDay, keptRemoved));

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
          'submission. They are still active — remove anyone who has left on the ' +
          'Club Roster Form ("' + Q.ACTION_MOD + '"), spelled as on the Roster.',
    });
  }

  return { code: code, toAppend: toAppend, reactivate: reactivate, deactivate: [],
           keptRemoved: keptRemoved, issues: issues, vanished: vanished };
}

/**
 * Plan a Roster Modification submission: names to add and names to remove.
 *
 * Adds: on file and active → noted as already there; on file and inactive →
 * reactivated (same ID), unless removed after the response was sent
 * (keptRemoved: she stays removed, and a REMOVE of the same name is then
 * "already removed"); unknown → minted. Removes: matched case-
 * insensitively against the club's ACTIVE girls → deactivated; already
 * inactive → noted, nothing to do; anything that matches nobody is returned
 * with the closest candidates (for staff, via the ReviewQueue — never for the
 * mentor email). Nothing is ever deleted. plan.removedOn is the removed_date
 * the deactivated rows get (removedOnDay_).
 *
 * entry: {partner, club, adds, removes, duplicates, source, submitted (optional)}
 */
function planModification_(entry, current, state, region, today) {
  const plan = { toAppend: [], reactivate: [], deactivate: [], keptRemoved: [], issues: [],
                 alreadyActive: [], alreadyInactive: [], keptBoth: [], unmatched: [] };
  const sentDay = submittedDay_(entry);
  plan.removedOn = removedOnDay_(sentDay, today);
  if (entry.duplicates && entry.duplicates.length) plan.issues.push(duplicateNamesIssue_(entry));

  const code = clubCode_(state.registry, entry.partner, entry.club);
  const byName = {};
  current.forEach(function (row) { byName[key_(row.full_name)] = row; });
  const added = {};

  (entry.adds || []).forEach(function (name) {
    const found = byName[key_(name)];
    if (found && found.status === STATUS.INACTIVE && staysRemoved_(found, sentDay, today)) {
      plan.keptRemoved.push({ name: name, row: found });   // not "added": a REMOVE of her is a no-op
      return;
    }
    added[key_(name)] = true;
    if (found) {
      if (found.status === STATUS.INACTIVE) plan.reactivate.push(found);
      else plan.alreadyActive.push(name);
      return;
    }
    plan.toAppend.push(newRosterRow_(state, code, entry, region, name, today));
  });
  if (plan.keptRemoved.length) plan.issues.push(keptRemovedIssue_(entry, sentDay, plan.keptRemoved));

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
      detail: (entry.source ? entry.source + ': ' : '') +
          '"' + u.name + '" is not on this club\'s active roster' +
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
