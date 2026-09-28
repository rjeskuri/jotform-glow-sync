/**
 * The GLOW menu that appears in the spreadsheet toolbar.
 */

function onOpen() {
  SpreadsheetApp.getUi().createMenu('GLOW')
      .addItem('Set up tabs', 'setUpTabs')
      .addItem('Rebuild roster from enrollment responses',
               'rebuildRosterFromResponses')
      .addItem('Refresh regions from the Partners tab', 'refreshRosterRegions')
      .addSeparator()
      .addItem('Show roster summary', 'showRosterSummary')
      .addSeparator()
      .addSubMenu(SpreadsheetApp.getUi().createMenu('Google Forms')
          .addItem('Create the Google Forms', 'createGlowForms')
          .addItem('Show form links', 'showFormLinks')
          .addItem('Update form dropdowns from the Roster', 'syncFormChoices')
          .addItem('Replace the Country question with the Region picker (one-time)',
                   'migrateCountryToRegion')
          .addItem('Update the forms\' wording (one-time; shows the changes first)',
                   'migrateFormWording')
          .addItem('Process any missed form responses', 'processMissedResponses')
          .addItem('Install triggers', 'installTriggers')
          .addSeparator()
          .addItem('Request Jotform sync now', 'requestJotformSync')
          .addSeparator()
          .addItem('Retire the old enrollment form', 'retireOldEnrollmentForm'))
      .addToUi();
}

/** A quick count of what the Roster currently holds. */
function showRosterSummary() {
  const roster = loadRoster_();
  const clubs = {}, partners = {}, regions = {};
  let active = 0, inactive = 0, noRegion = 0;

  roster.rows.forEach(function (row) {
    if (row.status === STATUS.INACTIVE) { inactive++; return; }
    active++;
    clubs[row._ck] = true;
    partners[key_(row.partner)] = true;
    const region = tidy_(row.region);
    if (region) regions[region] = (regions[region] || 0) + 1;
    else noRegion++;
  });

  const lines = [
    Object.keys(partners).length + ' partners',
    Object.keys(clubs).length + ' clubs',
    active + ' active girls (' + inactive + ' inactive, kept for history)',
    '',
    'By region:',
  ];
  Object.keys(regions).sort().forEach(function (r) {
    lines.push('   ' + r + ': ' + regions[r]);
  });
  if (noRegion) {
    lines.push('   (no region set): ' + noRegion +
               ' — fill in the Partners tab so these reach a form');
  }

  SpreadsheetApp.getUi().alert('GLOW roster', lines.join('\n'),
                               SpreadsheetApp.getUi().ButtonSet.OK);
}
