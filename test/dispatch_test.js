#!/usr/bin/env node
/**
 * Offline test for appsscript/Dispatch.gs: the request the sheet sends to
 * GitHub when the Roster changes. Only the pure builder is exercised; the
 * UrlFetchApp call itself is exercised by the "Request Jotform sync now"
 * menu item (docs/RUNBOOK.md, "Automatic sync").
 */
const fs = require('fs');
const path = require('path');
const loadGs = require('./load_gs');

const gs = loadGs(['buildDispatchRequest_', 'DISPATCH_EVENT', 'PROP', 'TAB'], ['Config.gs', 'Dispatch.gs']);
const workflow = fs.readFileSync(path.join(__dirname, '..', '.github', 'workflows', 'auto-sync.yml'), 'utf8');

let failures = 0;
function check(label, cond, detail) {
  console.log((cond ? '  ok   ' : '  FAIL ') + label + (detail ? ' :: ' + detail : ''));
  if (!cond) failures++;
}

const req = gs.buildDispatchRequest_('example-org/jotform-glow-sync', 'TOKEN-VALUE', 'rosterChangeForm',
                                     '2026-09-01 10:15:00');
check('posts to the repository_dispatch endpoint',
      req.url === 'https://api.github.com/repos/example-org/jotform-glow-sync/dispatches', req.url);
check('method is post, JSON body', req.options.method === 'post' && req.options.contentType === 'application/json');
check('bearer token in the Authorization header', req.options.headers.Authorization === 'Bearer TOKEN-VALUE');
check('GitHub Accept + API version headers',
      req.options.headers.Accept === 'application/vnd.github+json' &&
      req.options.headers['X-GitHub-Api-Version'] === '2022-11-28');
check('HTTP errors are muted (a failure must never throw into a form handler)',
      req.options.muteHttpExceptions === true);

const payload = JSON.parse(req.options.payload);
check('event_type is the one the workflow listens for', payload.event_type === 'roster-changed' &&
      gs.DISPATCH_EVENT === 'roster-changed', payload.event_type);
check('client_payload carries reason and time only',
      payload.client_payload.reason === 'rosterChangeForm' && payload.client_payload.at === '2026-09-01 10:15:00' &&
      Object.keys(payload.client_payload).sort().join(',') === 'at,reason');
check('token never appears in the payload', !req.options.payload.includes('TOKEN-VALUE'));
check('Script Property names are declared in Config.gs',
      gs.PROP.SYNC_DISPATCH_REPO === 'SYNC_DISPATCH_REPO' && gs.PROP.SYNC_DISPATCH_TOKEN === 'SYNC_DISPATCH_TOKEN');
check('SyncLog tab is declared in Config.gs', gs.TAB.SYNC_LOG === 'SyncLog');
check('the workflow listens for exactly this event type',
      workflow.includes('types: [' + gs.DISPATCH_EVENT + ']'));
check('the workflow reads the reason from the payload the sheet sends',
      workflow.includes('github.event.client_payload.reason'));

console.log('\n' + (failures ? failures + ' FAILURES' : 'ALL CHECKS PASSED'));
process.exit(failures ? 1 : 0);
