/**
 * Tell the sync runner that the Roster changed.
 *
 * Every handler that changes the Roster tab calls tryNotifySync_(), which
 * starts the repo's auto-sync workflow (GitHub's workflow_dispatch); it then
 * exports the Roster and runs the Jotform sync (docs/RUNBOOK.md, "Automatic
 * sync"). workflow_dispatch needs only Actions: write, so the token kept here
 * cannot change the repository's code - which, since the workflow also holds
 * the Salesforce secret, it must not; it can pick a branch, and the workflow
 * runs only on main (docs/plans/2026-10-06-sf-new-club-accounts.md). Nothing
 * here can fail a form submission: the call is wrapped like trySyncChoices_,
 * and when the two Script Properties are not set it returns without doing
 * anything.
 *
 * Script Properties (File → Project Settings → Script Properties):
 *   SYNC_DISPATCH_REPO   owner/name of the GitHub repository
 *   SYNC_DISPATCH_TOKEN  a fine-grained token for that one repo (Actions: read/write only)
 */

const DISPATCH_EVENT = 'roster-changed';     // the old repository_dispatch event; the workflow still takes it
const DISPATCH_WORKFLOW = 'auto-sync.yml';

/** Pure: the request UrlFetchApp will send. Tested offline in test/dispatch_test.js. */
function buildDispatchRequest_(repo, token, reason, at) {
  return {
    url: 'https://api.github.com/repos/' + repo + '/actions/workflows/' + DISPATCH_WORKFLOW + '/dispatches',
    options: {
      method: 'post',
      contentType: 'application/json',
      headers: {
        Authorization: 'Bearer ' + token,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
      },
      // the inputs the workflow declares: every region, applied (AUTO_SYNC_APPLY still decides),
      // and where the run came from - an action name and a time, never a girl's name
      payload: JSON.stringify({
        ref: 'main',
        inputs: { region: 'all', apply: 'true', source: 'sheet', reason: reason + ' ' + at },
      }),
      muteHttpExceptions: true,
    },
  };
}

/** True when both Script Properties are set. */
function syncDispatchConfigured_() {
  const props = PropertiesService.getScriptProperties();
  return !!(props.getProperty(PROP.SYNC_DISPATCH_REPO) &&
            props.getProperty(PROP.SYNC_DISPATCH_TOKEN));
}

/**
 * Send the event and record the outcome in the Audit tab. Returns the HTTP
 * status (204 = accepted), or null when automatic sync is not configured.
 * `reason` is an action name only — never a girl's name.
 */
function notifySync_(reason) {
  const props = PropertiesService.getScriptProperties();
  const repo = props.getProperty(PROP.SYNC_DISPATCH_REPO);
  const token = props.getProperty(PROP.SYNC_DISPATCH_TOKEN);
  if (!repo || !token) return null;
  const req = buildDispatchRequest_(repo, token, reason, now_());
  const resp = UrlFetchApp.fetch(req.url, req.options);
  const code = resp.getResponseCode();
  audit_('syncRequested', reason + ' → HTTP ' + code +
      (code === 204 ? '' : ': ' + String(resp.getContentText()).slice(0, 200)));
  return code;
}

/** Never let the notification fail the submission that triggered it. */
function tryNotifySync_(reason) {
  try { notifySync_(reason); } catch (err) { audit_('syncRequested', reason + ' failed: ' + err.message); }
}

/** Menu: GLOW → Google Forms → Request Jotform sync now. */
function requestJotformSync() {
  const ui = SpreadsheetApp.getUi();
  if (!syncDispatchConfigured_()) {
    ui.alert('GLOW', 'Automatic sync is not configured yet: set SYNC_DISPATCH_REPO and ' +
             'SYNC_DISPATCH_TOKEN in File → Project Settings → Script Properties ' +
             '(see docs/RUNBOOK.md, "Automatic sync").', ui.ButtonSet.OK);
    return;
  }
  const code = notifySync_('manual');
  SpreadsheetApp.getActive().toast(
      code === 204 ? 'Sync requested — the SyncLog tab shows the result within a few minutes.'
                   : 'GitHub answered HTTP ' + code + ' — see the Audit tab.',
      'GLOW', 10);
}
