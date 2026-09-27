'use strict';
/**
 * Run the pure-logic Apps Script files in Node, with no Google APIs.
 *
 * The .gs files are plain V8 JavaScript with top-level `const`s and function
 * declarations and no top-level side effects, so they can be concatenated and
 * evaluated in a vm context. Top-level `const`s are not properties of the
 * context's global object, but the completion value of the script is returned,
 * so appending `({a, b})` exports exactly the symbols asked for. No temp file
 * is written.
 *
 *   const loadGs = require('./load_gs');
 *   const gs = loadGs(['tidy_', 'parseRoster_', 'PARTNER_REGIONS']);
 *   const gs2 = loadGs(['buildDispatchRequest_'], ['Config.gs', 'Dispatch.gs']);
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const GS_DIR = path.join(__dirname, '..', 'appsscript');

/**
 * The pure-logic files (Roster.gs/Menu.gs/Forms.gs/FormHandlers.gs are mostly Google API calls;
 * forms_logic_test.js loads FormHandlers.gs by name for its pure FormLog helpers).
 */
const PURE = ['Config.gs', 'Normalize.gs', 'Ids.gs', 'Regions.gs', 'RosterOps.gs', 'Dispatch.gs'];

function loadGs(names, files) {
  const src = (files || PURE)
    .map(f => fs.readFileSync(path.join(GS_DIR, f), 'utf8'))
    .join('\n');
  const context = vm.createContext({ console });
  return vm.runInContext(src + '\n;({' + names.join(',') + '});', context,
                         { filename: 'appsscript-bundle.gs' });
}

module.exports = loadGs;
module.exports.PURE = PURE;
module.exports.GS_DIR = GS_DIR;
