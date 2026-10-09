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
const { check, finish } = require('./helpers/js/check');

const gs = loadGs(null, ['Config.gs', 'Dispatch.gs'], { strict: true });
// the repository_dispatch event a sheet sent before the switch to workflow_dispatch; the
// workflow still takes it (no .gs code sends it any more)
const OLD_DISPATCH_EVENT = 'roster-changed';
const workflow = fs.readFileSync(path.join(__dirname, '..', '.github', 'workflows', 'auto-sync.yml'), 'utf8');

const req = gs.buildDispatchRequest_('example-org/jotform-glow-sync', 'TOKEN-VALUE', 'rosterChangeForm',
                                     '2026-09-01 10:15:00');
check('posts to the workflow_dispatch endpoint of auto-sync.yml (Actions: write, never Contents)',
      req.url === 'https://api.github.com/repos/example-org/jotform-glow-sync/actions/workflows/auto-sync.yml/dispatches',
      req.url);
check('method is post, JSON body', req.options.method === 'post' && req.options.contentType === 'application/json');
check('bearer token in the Authorization header', req.options.headers.Authorization === 'Bearer TOKEN-VALUE');
check('GitHub Accept + API version headers',
      req.options.headers.Accept === 'application/vnd.github+json' &&
      req.options.headers['X-GitHub-Api-Version'] === '2022-11-28');
check('HTTP errors are muted (a failure must never throw into a form handler)',
      req.options.muteHttpExceptions === true);

const payload = JSON.parse(req.options.payload);
check('runs main, every region, applied, from the sheet', payload.ref === 'main' &&
      payload.inputs.region === 'all' && payload.inputs.apply === 'true' && payload.inputs.source === 'sheet');
check('inputs carry the reason and the time only, besides those',
      payload.inputs.reason === 'rosterChangeForm 2026-09-01 10:15:00' &&
      Object.keys(payload.inputs).sort().join(',') === 'apply,reason,region,source');
check('token never appears in the payload', !req.options.payload.includes('TOKEN-VALUE'));
check('Script Property names are declared in Config.gs',
      gs.PROP.SYNC_DISPATCH_REPO === 'SYNC_DISPATCH_REPO' && gs.PROP.SYNC_DISPATCH_TOKEN === 'SYNC_DISPATCH_TOKEN');
check('SyncLog tab is declared in Config.gs', gs.TAB.SYNC_LOG === 'SyncLog');
check('the workflow still takes the old event (until the token is switched)',
      workflow.includes('types: [' + OLD_DISPATCH_EVENT + ']'));
for (const input of ['region', 'apply', 'source', 'reason']) {
  check('the workflow declares the input ' + input,
        new RegExp('\\n      ' + input + ':\\n').test(workflow));
}
check('the workflow reads the reason from either event',
      workflow.includes('github.event.client_payload.reason') && workflow.includes('inputs.reason'));
check('the workflow file is the one the sheet starts', gs.DISPATCH_WORKFLOW === 'auto-sync.yml' &&
      fs.existsSync(path.join(__dirname, '..', '.github', 'workflows', gs.DISPATCH_WORKFLOW)));

// the Salesforce side of the workflow (docs/plans/2026-10-06-sf-new-club-accounts.md)
check('the workflow token reads the repository contents only',
      /\npermissions:\n  contents: read\n(?![ \t])/.test(workflow) && workflow.split('permissions:').length === 2);
check('only main\'s code runs (an Actions-only token picks the ref of a workflow_dispatch)',
      workflow.includes("    if: github.ref == 'refs/heads/main'\n"));
const syncAt = workflow.indexOf('      - name: Sync\n');
const sync = workflow.slice(syncAt, workflow.indexOf('      - name:', syncAt + 1));
for (const s of ['secrets.SF_CLIENT_ID', 'secrets.SF_CLIENT_SECRET']) {
  check('the workflow gives ' + s + ' to the Sync step only', workflow.split(s).length === 2 && sync.includes(s));
}
check('--apply-salesforce only with --apply and SF_SYNC=apply',
      workflow.split('--apply-salesforce').length === 2 &&
      /\n {14}args\+=\(--apply\)\n {14}if \[ "\$SF_SYNC" = "apply" \]; then args\+=\(--apply-salesforce\); fi\n {12}fi\n {10}fi\n/.test(workflow));

check('no Apps Script code made an undeclared global', !loadGs.strayGlobals().length, loadGs.strayGlobals().join(', '));
finish();
