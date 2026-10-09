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
 * back, as always (removed_date has no time of day). No readable removal day,
 * or one after today (a hand edit, e.g. 12/09 read as December: the forms
 * never date a removal after today) → she stays removed only if the response
 * was sent before today, so a fresh ADD always puts her back. No sentDay →
 * never (today's behaviour).
 */
function staysRemoved_(row, sentDay, today) {
  if (!sentDay) return false;
  const removed = dayOf_(row.removed_date);
  if (removed && removed <= today) return removed > sentDay;
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
 * True if a new-club response's club is new for it (so it goes to SF Pending).
 * current: the club's Roster rows; mine: those whose source is this response.
 * New = nothing on file - or, on a retry after an attempt that wrote the Roster
 * and then failed, nothing on file from before that attempt: rows another
 * response added since (the club sent again, an ADD on the change form) do
 * not make it an existing club. The attempt's day is the earliest added_date
 * of its rows, and days are all the Roster records: another response's row
 * added that same day counts as later (if that response enrolled the club
 * first, it queued it already and sfPendingAdd_ finds its row). A row with no
 * readable added_date counts as earlier.
 */
function isNewClubFor_(current, mine) {
  if (!mine.length) return !current.length;
  const first = mine.map(function (r) { return dayOf_(r.added_date); }).filter(String).sort()[0];
  return current.every(function (r) {
    return mine.indexOf(r) !== -1 || (!!first && dayOf_(r.added_date) >= first);
  });
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

/**
 * One new Roster row, ID minted now. last_name is her last word without a
 * leading = + - @ ("Jane =1+1" files "1+1"): a cell of its own, so it must not
 * read as a formula. The ID is unchanged (asciiCode_ drops those anyway), and
 * Python has no last_name.
 */
function newRosterRow_(state, code, entry, region, name, today) {
  return [
    mintGirlId_(state.sequence, code, name), entry.partner, entry.club,
    region, name, sheetText_(lastName_(name)), STATUS.ACTIVE, today, '',
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

// ------------------------------------------------- duplicate-club guard
// A new-club response that may be a club we already have is HELD for staff
// instead of imported (BACKLOG 11b, docs/intent/2026-09-01-duplicate-club-guards.md,
// docs/plans/2026-09-28-duplicate-club-guard.md). The thresholds start where
// the intent put them; tune them here.

const DUP_GUARD = {
  NAME_SHARE: 0.5,       // hold when this share of the names sent is active in ONE existing club…
  MIN_SHARED: 2,         // …and at least this many names are
  SIMILAR: 0.8,          // similarity_ of two names' distinctive words at which they may be one
  REENROLL_SHARE: 0.5,   // an exact re-enrollment is held below this share, both ways
  MAX_LISTED: 3,         // candidates named per reason
};

/** Words that say nothing about WHICH club, or which partner, it is. */
const CLUB_FILLER = /^(?:glow|global|clubs?|girls?|gc|the|of|and|y|de|del|la|las|los|el|group|sec|secondary|sch|school|pri|primary|primaria|secundaria|escuela|colegio)$/;
const PARTNER_FILLER = /^(?:foundation|fundacion|organi[sz]ation|org|initiative|network|trust|society|association|asociacion|ngo|inc|ltd|the|of|for|and|y|de|del|la|las|los|el|international|community|project|program(?:me)?|group|girls?|glow|club)$/;
const ROMAN_NUMERALS = ['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x'];
const SCHOOL_LEVELS = { pri: 'primary', primary: 'primary', primaria: 'primary',
                        sec: 'secondary', secondary: 'secondary', secundaria: 'secondary' };

/**
 * Why a new-club response should be held for staff instead of imported, as
 * [{kind, text}] — [] means import it. Texts name clubs, partners and counts,
 * never a girl.
 *
 *   reenroll  the (partner, club) is on file, but fewer than half of the names
 *             sent are on its roster AND fewer than half of its active girls
 *             are in the list (the 2026-08-31 case: another club's list). The
 *             only other check for a club on file is samename, and only when
 *             it has no active girl.
 *   names     at least half of the names sent, and at least MIN_SHARED, are
 *             active in ONE existing club — of any partner
 *   club      the club name is close to a club of the same partner, or of a
 *             partner the typed organization is close to (clubNamesClose_)
 *   partner   "My organization is not in this list" was chosen and the name
 *             typed is not a partner on file but is close to one (partnersClose_)
 *   samename  the club name is one ANOTHER partner's club already has — any
 *             status, any region (compared with key_) — or is the
 *             "<club> - <partner>" of a club on file (sfLongName_). A new club
 *             may not take a name in use: the attendance forms and Salesforce
 *             tell clubs apart by name (docs/plans/2026-09-30-same-name-clubs.md).
 *             A partner the typed organization is close to is not "another":
 *             that case is the club + partner reasons. Listed first; a
 *             release never skips it (handleNewClub_).
 *             The partner's OWN club on file is not a new club and is never
 *             held for its name — unless it has no active girl and another
 *             partner's club has the name: a retired club sent again (the
 *             2026-09-30 duplicates) has no roster on the forms any more, so
 *             the sync would treat it as a new club and refuse to add it.
 *             Held with its own text, alone; a release is refused like any
 *             samename (docs/RUNBOOK.md has the one false hold this makes).
 *             Who "has the name" is every Roster row with a partner and a
 *             club, a girl's name or not — Python's roster_pairs, which the
 *             sync's own check goes by; the other reasons count only rows
 *             with a girl's name, as before.
 *
 * entry:    {partner, club, names, typedPartner} as the handler would file it
 * rows:     the Roster (loadRoster_().rows): {partner, club, full_name, status}
 * partners: partner names on file (the Partners tab); the Roster's are added
 */
function newClubHoldReasons_(entry, rows, partners) {
  const clubs = Object.create(null), activeIn = Object.create(null);
  const holders = Object.create(null);   // every (partner, club) the Roster has: who has a club name
  rows.forEach(function (r) {
    const p = tidy_(r.partner), c = tidy_(r.club), n = foldKey_(r.full_name);
    if (!p || !c) return;
    const ck = clubKey_(p, c);
    if (!holders[ck]) holders[ck] = { partner: p, club: c };
    if (!n) return;
    const club = clubs[ck] ||
        (clubs[ck] = { partner: p, club: c, all: Object.create(null), active: Object.create(null) });
    club.all[n] = true;
    if (r.status === STATUS.ACTIVE && !club.active[n]) {
      club.active[n] = true;
      (activeIn[n] = activeIn[n] || []).push(ck);
    }
  });
  const sent = Object.create(null);
  entry.names.forEach(function (n) { if (foldKey_(n)) sent[foldKey_(n)] = true; });
  const names = Object.keys(sent);
  const count = function (list, set) { return list.filter(function (n) { return set[n]; }).length; };
  const listed = function (items) {
    return items.slice(0, DUP_GUARD.MAX_LISTED).join('; ') +
        (items.length > DUP_GUARD.MAX_LISTED ? ' and ' + (items.length - DUP_GUARD.MAX_LISTED) + ' more' : '');
  };
  const pk = key_(entry.partner), name = key_(entry.club);
  // a club as the hold texts name it: the spelling of its rows with a girl's name, if it has any
  const named = function (ck) { const x = clubs[ck] || holders[ck]; return x.club + ' (' + x.partner + ')'; };

  const own = clubs[clubKey_(entry.partner, entry.club)];
  if (own) {
    const onFile = count(names, own.all), active = Object.keys(own.active);
    if (!active.length) {
      // retired, and the name is another partner's club's: on the forms it would be a new club
      const others = Object.keys(holders).sort().filter(function (ck) {
        return key_(holders[ck].club) === name && key_(holders[ck].partner) !== pk;
      });
      if (others.length) {
        return [{ kind: 'samename', text: 'this club is on file with no active girl, and the club name ' +
                  'is already used by ' + listed(others.map(named)) }];
      }
    }
    const kept = count(active, sent);
    if (onFile < names.length * DUP_GUARD.REENROLL_SHARE && kept < active.length * DUP_GUARD.REENROLL_SHARE) {
      return [{ kind: 'reenroll', text: 'this club is already enrolled, but only ' + onFile + ' of the ' +
                names.length + ' names sent are on its roster, and ' + kept + ' of its ' + active.length +
                ' active girls are in the list' }];
    }
    return [];
  }

  const onFile = Object.create(null);   // key_(partner) → its spelling on file
  (partners || []).concat(Object.keys(clubs).map(function (ck) { return clubs[ck].partner; }))
      .forEach(function (p) { if (tidy_(p) && !onFile[key_(p)]) onFile[key_(p)] = tidy_(p); });
  const related = entry.typedPartner && !onFile[pk]
      ? Object.keys(onFile).sort().filter(function (k) { return partnersClose_(entry.partner, onFile[k]); })
      : [];

  const reasons = [];
  const taken = Object.keys(holders).sort().filter(function (ck) {
    const k = key_(holders[ck].partner);
    return key_(holders[ck].club) === name && k !== pk && related.indexOf(k) === -1;
  });
  const listedAs = Object.keys(holders).sort().filter(function (ck) {
    return key_(sfLongName_(holders[ck].club, holders[ck].partner)) === name;
  });
  if (taken.length || listedAs.length) {
    reasons.push({ kind: 'samename', text: [
      taken.length ? 'the club name is already used by ' + listed(taken.map(named)) : '',
      listedAs.length ? 'the club name reads as ' + listed(listedAs.map(named)) + ' ("<club>' + SF_NAME_SEP +
          '<partner>" is how a club whose name two partners share is listed)' : '',
    ].filter(String).join('; ') });
  }

  const shared = Object.create(null);
  names.forEach(function (n) {
    (activeIn[n] || []).forEach(function (ck) { shared[ck] = (shared[ck] || 0) + 1; });
  });
  const best = Object.keys(shared).sort(function (x, y) { return shared[y] - shared[x] || x.localeCompare(y); })[0];
  if (best && shared[best] >= DUP_GUARD.MIN_SHARED && shared[best] >= names.length * DUP_GUARD.NAME_SHARE) {
    reasons.push({ kind: 'names', text: shared[best] + ' of the ' + names.length + ' names sent are active in ' +
                   named(best) });
  }

  const near = Object.keys(clubs).sort().filter(function (ck) {
    const k = key_(clubs[ck].partner);
    return (k === pk || related.indexOf(k) !== -1) && clubNamesClose_(entry.club, clubs[ck].club);
  });
  if (near.length) {
    reasons.push({ kind: 'club', text: 'the club name is close to ' + listed(near.map(named)) +
                   ', already enrolled' });
  }
  if (related.length) {
    reasons.push({ kind: 'partner', text: 'the organization was typed as "' + entry.partner +
                   '", close to ' + listed(related.map(function (k) { return onFile[k]; })) + ' on file' });
  }
  return reasons;
}

/**
 * A name as words to compare: case and accents folded, dots and apostrophes
 * dropped (so "G.L.O.W" is "glow", "Bishop's" is "bishops"), split on
 * anything that is not a letter, mark or digit, letters split from digits
 * ("GC-2", "Club2" → …, "2").
 */
function matchWords_(s) {
  return foldKey_(s).replace(/[.'\u2019`]/g, '')
      .replace(/(\p{L})(?=\p{N})|(\p{N})(?=\p{L})/gu, '$1$2 ')
      .split(/[^\p{L}\p{M}\p{N}]+/u).filter(String);
}

/** The numbers in a name's words ("2", "II" → 2), sorted: '' if none. */
function numberTag_(words) {
  return words.map(function (w) {
    if (/^\d+$/.test(w)) return String(parseInt(w, 10));
    const roman = ROMAN_NUMERALS.indexOf(w);
    return roman === -1 ? '' : String(roman + 1);
  }).filter(String).sort().join(' ');
}

/** The one-letter words of a name — section marks such as "(A)", "Club B" — sorted: '' if none. */
function letterTag_(words) {
  const seen = {};
  words.forEach(function (w) { if (w.length === 1 && /\p{L}/u.test(w)) seen[w] = true; });
  return Object.keys(seen).sort().join(' ');
}

/** The school levels in a name's words ("PRI SCH", "primaria" → primary), sorted: '' if none. */
function levelTag_(words) {
  const seen = {};
  words.forEach(function (w) {
    if (Object.prototype.hasOwnProperty.call(SCHOOL_LEVELS, w)) seen[SCHOOL_LEVELS[w]] = true;
  });
  return Object.keys(seen).sort().join(' ');
}

/**
 * True if two club names may be one club: the same words; or, without the
 * filler words (CLUB_FILLER), one's words all in the other's ("BRIGHT GIRLS"
 * in "BRIGHT GIRLS (TESTVILLE SEC SCH)") or similarity_ ≥ SIMILAR (a typo) —
 * also with what is in parentheses left out, so a typo AND an added school
 * ("BRAVEHAERT GIRLS (TESTVILLE SEC SCH)") is caught. Names whose numbers,
 * section letters or school levels differ ("Harbor Club 1" / "Harbor Club
 * (2)", "Orbit (A)" / "Orbit (B)", "Las Lomitas primaria" / "Las Lomitas
 * secundaria") never are.
 */
function clubNamesClose_(a, b) {
  const wa = matchWords_(a), wb = matchWords_(b);
  const differ = function (tag) { const x = tag(wa), y = tag(wb); return x && y && x !== y; };
  if (differ(numberTag_) || differ(letterTag_) || differ(levelTag_)) return false;
  if (wordsClose_(wa, wb, CLUB_FILLER)) return true;
  const bare = function (s) { return matchWords_(String(s == null ? '' : s).replace(/\([^)]*\)/g, ' ')); };
  const ba = bare(a), bb = bare(b);
  return (ba.length < wa.length || bb.length < wb.length) && wordsClose_(ba, bb, CLUB_FILLER);
}

/**
 * True if a typed organization may be a partner on file: the same words
 * (accents, punctuation, spacing), an acronym of the other ("TARN" / "Test
 * Aid Relief Network", either way round), or close as club names are, with
 * PARTNER_FILLER as the filler words.
 */
function partnersClose_(typed, known) {
  const wt = matchWords_(typed), wk = matchWords_(known);
  if (!wt.length || !wk.length) return false;
  const acronym = function (short, long) {
    return short.length === 1 && short[0].length >= 3 && long.length === short[0].length &&
        long.map(function (w) { return w.charAt(0); }).join('') === short[0];
  };
  return acronym(wt, wk) || acronym(wk, wt) || wordsClose_(wt, wk, PARTNER_FILLER);
}

function wordsClose_(wa, wb, filler) {
  if (!wa.length || !wb.length) return false;
  if (wa.join(' ') === wb.join(' ')) return true;
  const keep = function (w) { return !filler.test(w); };
  const da = wa.filter(keep), db = wb.filter(keep);
  if (!da.length || !db.length) return false;
  const short = da.length <= db.length ? da : db, long = short === da ? db : da;
  if (short.every(function (w) { return long.indexOf(w) !== -1; })) return true;
  return similarity_(da.join(' '), db.join(' ')) >= DUP_GUARD.SIMILAR;
}

/**
 * How alike two strings are, 0..1 — Python's
 * difflib.SequenceMatcher(None, a, b).ratio() (test/gs_parity_test.py compares
 * them): twice the characters in matching blocks (Ratcliff/Obershelp) over the
 * total length.
 */
function similarity_(a, b) {
  a = String(a); b = String(b);
  if (!a.length && !b.length) return 1;
  return 2 * matchingChars_(a, b) / (a.length + b.length);
}

/** Characters in the matching blocks: the longest common run, then the same left and right of it. */
function matchingChars_(a, b) {
  if (!a.length || !b.length) return 0;
  let best = 0, endA = 0, endB = 0, prev = new Array(b.length + 1).fill(0);
  for (let i = 1; i <= a.length; i++) {
    const cur = new Array(b.length + 1).fill(0);
    for (let j = 1; j <= b.length; j++) {
      if (a[i - 1] !== b[j - 1]) continue;
      cur[j] = prev[j - 1] + 1;
      if (cur[j] > best) { best = cur[j]; endA = i; endB = j; }   // earliest in a, then in b: difflib's tie-break
    }
    prev = cur;
  }
  if (!best) return 0;
  return best + matchingChars_(a.slice(0, endA - best), b.slice(0, endB - best)) +
      matchingChars_(a.slice(endA), b.slice(endB));
}

// ------------------------------------------ clubs that share a name
// Salesforce finds a club by its name alone (question 5 of the attendance
// form, exact apart from case) and creates an account when none matches. So
// a club whose name another partner's club also has is "<club> - <partner>"
// in Salesforce, in the forms' club list and in question 5
// (docs/plans/2026-09-30-same-name-clubs.md). The forms are switched by
// sync_attendance_form.py --same-name-switch (glow/sync.py shared_club_names
// / sf_club_name); these mirror that rule for the Monday e-mail, and
// newClubHoldReasons_ keeps the set from growing (kind 'samename').
//
// Known divergences from the Python side (CLAUDE.md rule 10: documented here
// and in docs/ARCHITECTURE.md, not fixed on one side):
//  - key_ also drops invisible characters (Normalize.gs INVISIBLE), which
//    glow.text.key keeps: a name with a zero-width character inside is the
//    same name here and a different one there (BACKLOG 28). Cells the form
//    handlers write never hold one; a cell typed or pasted by hand can.
//  - On a form the long or plain name is sticky: once switched, a club keeps
//    "<club> - <partner>" when its namesake goes inactive, and keeps its
//    plain name when a namesake turns up later (the sync refuses to add
//    that one). Nothing here can see the form, so these follow today's
//    ACTIVE rows (the switch's rule), and the Monday e-mail asks staff to
//    check a shared name against the form's club list (sfPendingLines_).

/**
 * The club names that ACTIVE clubs of two or more partners have, in any
 * region: {key_(club): true}. rows: the Roster (loadRoster_().rows). A row
 * with no partner, no club or no girl's name reaches no form and is ignored
 * (a club is active when it has an active girl: Python's roster_pairs);
 * status compares as the Python reader does (spacing and case ignored).
 */
function sharedClubNames_(rows) {
  const partnersOf = Object.create(null);
  rows.forEach(function (r) {
    if (key_(r.status) !== STATUS.ACTIVE) return;
    const p = key_(r.partner), c = key_(r.club);
    if (!p || !c || !tidy_(r.full_name)) return;
    (partnersOf[c] = partnersOf[c] || Object.create(null))[p] = true;
  });
  const shared = Object.create(null);
  Object.keys(partnersOf).forEach(function (c) {
    if (Object.keys(partnersOf[c]).length > 1) shared[c] = true;
  });
  return shared;
}

/** "<club> - <partner>", both as spelled (tidied): no case change, no accent folding. */
function sfLongName_(club, partner) {
  return tidy_(club) + SF_NAME_SEP + tidy_(partner);
}

/**
 * The name a club's Salesforce account must have — what the attendance form
 * sends as its Club Name: the club's own name, or "<club> - <partner>" when
 * `shared` (sharedClubNames_) has the name. A shared name with no partner
 * is refused, never guessed.
 */
function sfClubName_(club, partner, shared) {
  if (!tidy_(club)) throw new Error('sfClubName_: no club name');
  if (shared[key_(club)] !== true) return tidy_(club);   // === true: a club called "constructor" is no member of {}
  if (!tidy_(partner)) {
    throw new Error('sfClubName_: "' + tidy_(club) + '" is a name two partners share, so it needs its partner');
  }
  return sfLongName_(club, partner);
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
