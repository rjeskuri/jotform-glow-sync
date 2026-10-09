'use strict';
/**
 * Run the Apps Script files in Node, with no Google APIs.
 *
 * The .gs files are plain V8 JavaScript with top-level `const`s and function
 * declarations and no top-level side effects, so they can be concatenated and
 * evaluated in a vm context. Top-level `const`s are not properties of the
 * context's global object, but the completion value of the script is returned,
 * so appending `({a, b})` exports exactly the symbols asked for - with no
 * names, every top-level `function NAME(` / `const NAME =` / `let NAME =` of
 * the files. No temp file is written.
 *
 *   const loadGs = require('./load_gs');
 *   const gs = loadGs(['tidy_', 'parseRoster_', 'PARTNER_REGIONS']);   // from the pure files
 *   const fh = loadGs(null, ['Config.gs', 'Normalize.gs', 'FormHandlers.gs'], { strict: true });
 *   const ctx = loadGs.sandbox(['Config.gs', 'Roster.gs'], { SpreadsheetApp: stub });
 *
 * Implicit globals. Apps Script runs the files in sloppy mode, where assigning
 * to a name nobody declared (`total = 0` meant as `let total = 0`) quietly
 * makes a global that every later run of the code shares. A sandbox, and a
 * load with { strict: true }, is watched: strayGlobals() lists each global it
 * has that is neither a declaration of its files nor a global the caller
 * passed in - made while loading, or later by a function a test ran. A strict
 * load also throws at once if loading itself made one. A test that stubs a
 * function after loading assigns a declared name, which is never stray; one
 * the files do not declare goes in the sandbox's globals instead.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const GS_DIR = path.join(__dirname, '..', 'appsscript');
const FILENAME = 'appsscript-bundle.gs';

/**
 * The pure-logic files (Roster.gs/Menu.gs/Forms.gs/FormHandlers.gs are mostly Google API calls;
 * the tests load them by name, with stubs, where they need them).
 */
const PURE = ['Config.gs', 'Normalize.gs', 'Ids.gs', 'Regions.gs', 'RosterOps.gs', 'Dispatch.gs'];

/** A top-level declaration: the .gs files declare at column 0 and nest everything else. */
const DECLARATION = /^(?:function\s+([A-Za-z_$][\w$]*)\s*\(|(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=)/gm;

const watched = [];   // {context, allowed, label}

function bundle(files) {
  return (files || PURE).map(f => fs.readFileSync(path.resolve(GS_DIR, f), 'utf8')).join('\n');
}

/** Every name a bundle declares at the top level, in order, once. */
function declarations(src) {
  return [...new Set([...src.matchAll(DECLARATION)].map(m => m[1] || m[2]))];
}

function watch(context, src, files) {
  const entry = { context, allowed: new Set(Object.keys(context).concat(declarations(src))),
                  label: (files || PURE).map(f => path.basename(f)).join('+') };
  watched.push(entry);
  return entry;
}

function strayIn(entry) {
  return Object.keys(entry.context).filter(k => !entry.allowed.has(k))
      .map(k => k + ' (' + entry.label + ')');
}

/**
 * The undeclared globals of every watched context ('name (files)'), or of the
 * one `context` given.
 */
function strayGlobals(context) {
  return watched.filter(e => !context || e.context === context).flatMap(strayIn);
}

function loadGs(names, files, opts) {
  const src = bundle(files);
  const context = vm.createContext({ console });
  const entry = opts && opts.strict ? watch(context, src, files) : null;
  const out = vm.runInContext(src + '\n;({' + (names || declarations(src)).join(',') + '});', context,
                              { filename: FILENAME });
  const stray = entry ? strayIn(entry) : [];
  if (stray.length) {
    throw new Error('loading the Apps Script made undeclared globals: ' + stray.join(', ') +
                    ' (an assignment without const/let? Apps Script would not complain)');
  }
  return out;
}

/**
 * A vm context holding `globals` (stubbed Google services and the like) with
 * the files run in it, watched for implicit globals. Its top-level functions
 * are properties of the context: a test replaces one by assigning it.
 */
function sandbox(files, globals) {
  const src = bundle(files);
  const context = vm.createContext(Object.assign({ console }, globals));
  watch(context, src, files);
  vm.runInContext(src, context, { filename: FILENAME });
  return context;
}

module.exports = loadGs;
module.exports.PURE = PURE;
module.exports.GS_DIR = GS_DIR;
module.exports.declarations = declarations;
module.exports.sandbox = sandbox;
module.exports.strayGlobals = strayGlobals;
