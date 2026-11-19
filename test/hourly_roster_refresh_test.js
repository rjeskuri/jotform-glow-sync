#!/usr/bin/env node
/**
 * Offline tests for the hourly Club Roster Form dropdown refresh (ticket #228): installTriggers
 * (appsscript/FormHandlers.gs) installs a time-driven trigger for syncFormChoicesHourly, which runs
 * syncFormChoices (appsscript/Forms.gs) under the document lock, skips quietly when the lock is busy
 * and writes an Audit row only when a dropdown changed. Runs the real .gs files against a fake
 * ScriptApp, Forms service, spreadsheet and lock (the same stubs as the menu tests in
 * forms_logic_test.js); the fake form is in step with the sheet after one real syncFormChoices run.
 *
 *   node test/hourly_roster_refresh_test.js
 */
const vm = require('vm');
const loadGs = require('./load_gs');
const { check, finish } = require('./helpers/js/check');

const HANDLER = 'syncFormChoicesHourly';
const GS = ['Config.gs', 'Normalize.gs', 'Roster.gs', 'Forms.gs', 'FormHandlers.gs'];

// ------------------------------------------------------------ installTriggers
console.log('installTriggers: the hourly trigger beside the form-submit and Monday ones');
const installWorld = (existing) => {
  const store = (existing || []).map(t => Object.assign({}, t));
  const audits = [];
  const ScriptApp = {
    WeekDay: { MONDAY: 'MONDAY' },
    getProjectTriggers: () => store.map(t => ({ _t: t, getHandlerFunction: () => t.fn })),
    deleteTrigger: h => { const i = store.indexOf(h._t); if (i >= 0) store.splice(i, 1); },
    newTrigger: fn => {
      const t = { fn };
      const b = {
        forSpreadsheet: () => b, onFormSubmit: () => { t.kind = 'form-submit'; return b; },
        timeBased: () => { t.kind = 'time'; return b; },
        everyHours: n => { t.everyHours = n; return b; },
        onWeekDay: d => { t.weekday = d; return b; }, atHour: h => { t.atHour = h; return b; },
        nearMinute: m => { t.nearMinute = m; return b; },
        create: () => { store.push(t); return {}; },
      };
      return b;
    },
  };
  const ctx = loadGs.sandbox(GS, { ScriptApp, SpreadsheetApp: { getActive: () => ({}) } });
  ctx.audit_ = (a, d) => audits.push(a + ': ' + d);
  return { ctx, store, audits };
};
const named = (store, fn) => store.filter(t => t.fn === fn);

let iw = installWorld();
iw.ctx.installTriggers();
const hourly = named(iw.store, HANDLER);
check('a fresh project: one time-driven trigger for ' + HANDLER + ', every 1 hour (not a weekday or an hour of the day)',
      hourly.length === 1 && hourly[0].kind === 'time' && hourly[0].everyHours === 1 &&
      hourly[0].weekday === undefined && hourly[0].atHour === undefined, JSON.stringify(hourly));
check('…the form-submit router and the Monday 8:00 e-mail are still installed, once each',
      named(iw.store, 'onAnyFormSubmit').length === 1 && named(iw.store, 'onAnyFormSubmit')[0].kind === 'form-submit' &&
      named(iw.store, 'sendSfPendingDigest').length === 1 &&
      named(iw.store, 'sendSfPendingDigest')[0].weekday === 'MONDAY' && named(iw.store, 'sendSfPendingDigest')[0].atHour === 8 &&
      iw.store.length === 3, JSON.stringify(iw.store));
check('…and the Audit row says it ran', iw.audits.length === 1 && iw.audits[0].startsWith('installTriggers: '), iw.audits.join());

iw.ctx.installTriggers();
iw.ctx.installTriggers();
check('installed again (twice more): still exactly one of each, no duplicate hourly trigger',
      iw.store.length === 3 && named(iw.store, HANDLER).length === 1 &&
      named(iw.store, 'onAnyFormSubmit').length === 1 && named(iw.store, 'sendSfPendingDigest').length === 1,
      iw.store.map(t => t.fn).join());

iw = installWorld([
  { fn: HANDLER, kind: 'time', everyHours: 6 },            // an older install with another period
  { fn: HANDLER, kind: 'time', everyHours: 1 },            // …and a stray second copy
  { fn: 'unrelatedTrigger', kind: 'time', everyHours: 12 },
]);
iw.ctx.installTriggers();
check('an older or duplicated hourly trigger is replaced by the one every-1-hour trigger; a trigger of another function is left alone',
      named(iw.store, HANDLER).length === 1 && named(iw.store, HANDLER)[0].everyHours === 1 &&
      named(iw.store, 'unrelatedTrigger').length === 1 && named(iw.store, 'unrelatedTrigger')[0].everyHours === 12,
      JSON.stringify(iw.store));

// ------------------------------------------------------------ the timed handler
console.log('\n' + HANDLER + ': the real syncFormChoices under the document lock (fake Forms service, sheet, lock)');
const ROSTER_COLS = ['girl_id', 'partner', 'club', 'region', 'full_name', 'last_name',
                     'status', 'added_date', 'removed_date', 'source'];

const world = (opts) => {
  opts = opts || {};
  const partners = (opts.partners || ['Alpha Org', 'Beta Org']).slice();
  const roster = (opts.roster || []).map(r => r.slice());
  const touches = [], audits = [];
  const lock = { held: false, busy: false, releases: 0 };
  const props = opts.props || { FORM_ROSTER_ID: 'ROSTER' };

  // the Club Roster Form: the four fixed pages and the two partner dropdowns, nothing per partner yet
  const items = [];
  const note = what => touches.push({ what, lockHeld: lock.held });
  const makeItem = (type, title) => {
    const it = { type, title, choices: [] };
    const api = {
      getType: () => type, getTitle: () => it.title, getIndex: () => items.indexOf(api),
      setTitle: t => { it.title = t; return api; }, setRequired: () => api,
      asListItem: () => api, asPageBreakItem: () => api, setGoToPage: () => api,
      getChoices: () => it.choices.map(c => ({ getValue: () => c.value })),
      createChoice: (value, page) => ({ value, page }),
      setChoices: cs => { note('setChoices'); it.choices = cs.map(c => ({ value: c.value })); return api; },
      setChoiceValues: vs => { note('setChoiceValues'); it.choices = vs.map(v => ({ value: v })); return api; },
      _it: it,
    };
    return api;
  };
  ['Your organization', 'The club', 'Existing club'].forEach(t => items.push(makeItem('PAGE_BREAK', t)));
  items.push(makeItem('LIST', 'Partner organization'));
  items.push(makeItem('LIST', 'Partner organization (existing club)'));
  items.push(makeItem('PAGE_BREAK', 'The change'));
  const addTo = type => () => { note('add ' + type); const i = makeItem(type, ''); items.push(i); return i; };
  const form = {
    getItems: t => items.filter(i => !t || i.getType() === t),
    addPageBreakItem: addTo('PAGE_BREAK'), addListItem: addTo('LIST'),
    moveItem: (from, to) => { note('moveItem'); const [x] = items.splice(from, 1); items.splice(to, 0, x); return x; },
  };

  const sheetOf = (rows, width) => ({
    getLastRow: () => rows.length + 1,
    getRange: (r, c, n, m) => ({ getValues: () => rows.slice(r - 2, r - 2 + n).map(row => row.slice(c - 1, c - 1 + m)) }),
  });
  const SpreadsheetApp = {
    getActive: () => ({
      getSheetByName: name => name === 'Partners' ? sheetOf(partners.map(p => [p, 'Africa']))
          : name === 'Roster' ? sheetOf(roster) : null,
      getSpreadsheetTimeZone: () => 'UTC',
      toast: () => {},
    }),
    getUi: () => { throw new Error('a timed run has no dialogs'); },
  };
  const LockService = { getDocumentLock: () => ({
    tryLock: () => { if (lock.busy) return false; lock.held = true; return true; },
    waitLock: () => { if (lock.busy) throw new Error('Could not obtain lock'); lock.held = true; },
    hasLock: () => lock.held,
    releaseLock: () => { lock.held = false; lock.releases++; },
  }) };
  const ctx = loadGs.sandbox(GS, {
    SpreadsheetApp, LockService,
    FormApp: { ItemType: { PAGE_BREAK: 'PAGE_BREAK', LIST: 'LIST' },
               PageNavigationType: { SUBMIT: 'SUBMIT', CONTINUE: 'CONTINUE' },
               openById: id => { if (id !== 'ROSTER') throw new Error('no form ' + id); return form; } },
    PropertiesService: { getScriptProperties: () => ({ getProperty: k => props[k] || null }) },
  });
  ctx.audit_ = (a, d) => audits.push(a + ': ' + d);
  const Q = vm.runInContext('Q', ctx);
  const listOf = title => { const l = items.find(i => i.getType() === 'LIST' && i.getTitle() === title); return l && l._it.choices.map(c => c.value); };
  const clubList = partner => listOf(Q.CLUB_PREFIX + partner + ')');
  return { ctx, roster, partners, touches, audits, lock, listOf, clubList, Q, items };
};

const row = (partner, club, status, id) =>
    [id, partner, club, 'Africa', 'Girl ' + id, 'Test', status || 'active', '2026-09-01', '', 'test'];
const BASE = () => [
  row('Alpha Org', 'Sunrise Club', 'active', 'A1'), row('Alpha Org', 'Sunrise Club', 'active', 'A2'),
  row('Alpha Org', 'Moon Club', 'active', 'A3'), row('Beta Org', 'Star Club', 'active', 'B1'),
];
// a world whose form was already brought in step by the real syncFormChoices (the manual run)
const synced = () => {
  const w = world({ roster: BASE() });
  w.ctx.syncFormChoices();
  w.audits.length = 0; w.touches.length = 0;
  return w;
};

// the handler's run, its exception (or "not defined") returned instead of thrown, so one failure does not hide the rest
const run = x => {
  if (typeof x.ctx[HANDLER] !== 'function') return HANDLER + ' is not defined';
  try { x.ctx[HANDLER](); return ''; } catch (e) { return String(e.message); }
};

let w = synced();
check('setup: the first sync built one section per partner (Alpha Org: two clubs sorted, Beta Org: one)',
      JSON.stringify(w.clubList('Alpha Org')) === '["Moon Club","Sunrise Club"]' &&
      JSON.stringify(w.clubList('Beta Org')) === '["Star Club"]');

const err = run(w);
check('nothing changed since the last sync: no Audit row (and no throw)', !err && w.audits.length === 0, err || w.audits.join(' | '));
check('…the lock was taken and released, and is not held afterwards', !err && w.lock.releases === 1 && !w.lock.held);

// Each scenario changes the sheet the way a tool does, then the hourly run brings the form in step.
const scenarios = [
  ['a new club in a partner', x => x.roster.push(row('Alpha Org', 'Comet Club', 'active', 'A4')),
   { 'Alpha Org': ['Comet Club', 'Moon Club', 'Sunrise Club'], 'Beta Org': ['Star Club'] }],
  ['a club renamed (tools/rename_club.py: every row of it)', x => x.roster.forEach(r => { if (r[2] === 'Moon Club') r[2] = 'Lunar Club'; }),
   { 'Alpha Org': ['Lunar Club', 'Sunrise Club'], 'Beta Org': ['Star Club'] }],
  ['a club deactivated (tools/deactivate_clubs.py: all its rows inactive)', x => x.roster.forEach(r => { if (r[2] === 'Sunrise Club') r[6] = 'inactive'; }),
   { 'Alpha Org': ['Moon Club'], 'Beta Org': ['Star Club'] }],
  ['a partner whose last club went inactive keeps its section with the placeholder', x => x.roster.forEach(r => { if (r[1] === 'Beta Org') r[6] = 'inactive'; }),
   { 'Alpha Org': ['Moon Club', 'Sunrise Club'], 'Beta Org': ['(no active clubs)'] }],
  ['a new partner with a club (a new section)', x => { x.partners.push('Gamma Org'); x.roster.push(row('Gamma Org', 'Dawn Club', 'active', 'G1')); },
   { 'Alpha Org': ['Moon Club', 'Sunrise Club'], 'Beta Org': ['Star Club'], 'Gamma Org': ['Dawn Club'] }],
];
for (const [what, change, expected] of scenarios) {
  w = synced();
  change(w);
  const threw = run(w);
  const got = {};
  Object.keys(expected).forEach(p => { got[p] = w.clubList(p); });
  check(what + ': the dropdowns follow the sheet', !threw && JSON.stringify(got) === JSON.stringify(expected), threw || JSON.stringify(got));
  check('…one Audit row, and every form write happened under the lock, which is released',
        w.audits.length === 1 && w.touches.length > 0 && w.touches.every(t => t.lockHeld) &&
        w.lock.releases === 1 && !w.lock.held, w.audits.join(' | '));
  const partnerChoices = w.listOf('Partner organization (existing club)');
  check('…the existing-club partner dropdown lists every partner',
        !threw && JSON.stringify(partnerChoices) === JSON.stringify(Object.keys(expected).sort()), JSON.stringify(partnerChoices));
  w.audits.length = 0;
  const again = run(w);
  check('…and the next hourly run finds nothing to do: no Audit row', !again && w.audits.length === 0, again || w.audits.join(' | '));
}

// the lock busy: a manual run, a form submission or a rebuild holds it
w = synced();
w.roster.push(row('Alpha Org', 'Comet Club', 'active', 'A4'));
w.lock.busy = true;
const busyThrew = run(w);
check('the lock busy: no exception, no form change at all, no Audit row, nothing to release',
      !busyThrew && w.touches.length === 0 && w.audits.length === 0 && w.lock.releases === 0 &&
      JSON.stringify(w.clubList('Alpha Org')) === '["Moon Club","Sunrise Club"]', busyThrew || w.audits.join(' | '));
w.lock.busy = false;
const later = run(w);
check('…the next run, the lock free, picks the change up (one Audit row)',
      !later && JSON.stringify(w.clubList('Alpha Org')) === '["Comet Club","Moon Club","Sunrise Club"]' && w.audits.length === 1 &&
      w.lock.releases === 1);

// no form saved yet, or the saved one does not open: nothing to refresh, and nothing to say every hour
w = world({ roster: BASE(), props: {} });
const noFormThrew = run(w);
check('no Club Roster Form saved: no exception, no Audit row, no form write',
      !noFormThrew && w.audits.length === 0 && w.touches.length === 0, noFormThrew);

// the manual menu item is unchanged: it still writes its Audit row when nothing changed (guards the refactor)
w = synced();
w.ctx.syncFormChoicesFromMenu();
check('guard: the menu run (syncFormChoicesFromMenu) still writes its Audit row when nothing changed',
      w.audits.length === 1 && w.audits[0] === 'syncFormChoices: 0 dropdown(s) updated', w.audits.join(' | '));

finish();
