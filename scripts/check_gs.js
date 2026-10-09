#!/usr/bin/env node
'use strict';
/**
 * Guard `clasp push`, offline and dependency-free:
 *
 *  - every Apps Script file parses with V8 (a broken file breaks EVERY form handler), and the
 *    pure-logic files load together (a symbol renamed in another file);
 *  - the Google services the .gs files use are exactly the pinned ones: a new service adds an
 *    OAuth scope, and until the owner re-authorizes, the form-submit trigger FAILS HARD
 *    (CLAUDE.md rule 11). A name ending in App or Service, a scope-bearing global (Session, the
 *    advanced services) and, in appsscript.json, enabledAdvancedServices or oauthScopes all count;
 *  - every bare call `name(...)`, and every function a menu item or trigger names as a string,
 *    resolves to a top-level function or constant of some .gs file, a parameter or local of the
 *    code around it, or a JavaScript built-in - a renamed or deleted function would otherwise
 *    only fail live, inside the trigger.
 *
 * The scan works on tokens with comments, strings and regular expressions taken out; it does
 * not model scopes exactly (a local anywhere in a top-level function counts for all of it), so
 * it can miss a bad call but does not report a good one. A `/` after the `)` of an if, while or
 * for head starts a regular expression; `name(...) {` is a method only in an object literal or a
 * class body (an object literal is a `{` where an expression goes).
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const loadGs = require('../test/load_gs');

// The services in use (appsscript/*.gs, 2026-10-09). Adding one is a re-authorization: see
// CLAUDE.md rule 11 and docs/RUNBOOK.md, "Missed form responses", before pinning it here.
const SERVICES = ['FormApp', 'LockService', 'MailApp', 'PropertiesService', 'ScriptApp',
                  'SpreadsheetApp', 'UrlFetchApp', 'Utilities'];
const SERVICE_RX = /^[A-Z][A-Za-z]*(App|Service)$/;
// globals that bring a scope without that suffix: Session (userinfo.email) and the advanced services
const SCOPED = new Set(['Session', 'Drive', 'Sheets', 'Gmail', 'Calendar', 'Docs', 'Slides', 'People',
                        'AdminDirectory', 'Jdbc', 'Maps', 'Charts', 'Forms', 'Tasks', 'YouTube', 'Analytics',
                        'BigQuery']);
const BUILTINS = new Set([
  'Array', 'ArrayBuffer', 'BigInt', 'Boolean', 'DataView', 'Date', 'Error', 'EvalError',
  'Function', 'Map', 'Number', 'Object', 'Promise', 'Proxy', 'RangeError', 'ReferenceError',
  'RegExp', 'Set', 'String', 'Symbol', 'SyntaxError', 'TypeError', 'URIError', 'WeakMap',
  'WeakSet', 'decodeURI', 'decodeURIComponent', 'encodeURI', 'encodeURIComponent', 'escape',
  'unescape', 'isFinite', 'isNaN', 'parseFloat', 'parseInt',
]);
const KEYWORDS = new Set([
  'async', 'await', 'break', 'case', 'catch', 'class', 'const', 'continue', 'debugger', 'default',
  'delete', 'do', 'else', 'export', 'extends', 'false', 'finally', 'for', 'function', 'if',
  'import', 'in', 'instanceof', 'let', 'new', 'null', 'of', 'return', 'super', 'switch', 'this',
  'throw', 'true', 'try', 'typeof', 'undefined', 'var', 'void', 'while', 'with', 'yield',
]);
// after these a `/` starts a regular expression, not a division
const BEFORE_REGEX = new Set(['return', 'typeof', 'case', 'in', 'of', 'new', 'delete', 'void',
                              'throw', 'else', 'do', 'instanceof', 'yield', 'await']);
const PUNCT = ['...', '===', '!==', '**=', '<<=', '>>=', '>>>', '=>', '==', '!=', '<=', '>=',
               '&&', '||', '??', '?.', '++', '--', '+=', '-=', '*=', '/=', '%=', '&=', '|=',
               '^=', '<<', '>>', '**'];

/** Tokens of a .gs source: {t: 'id' | 'num' | 'str' | 'p', v, line}; comments and regular
 * expressions are dropped, a template literal is one 'str' (its ${...} parts are tokenized). */
function tokenize(src) {
  const out = [];
  const stack = [];                         // per open {: 'obj', 'class' or 'block'; '${' in a template
  const parens = [];                        // per open (: true when it is an if / while / for head
  let i = 0, line = 1;
  const prev = () => out[out.length - 1];
  const regexAllowed = () => {
    const p = prev();
    if (!p) return true;
    if (p.t === 'id') return KEYWORDS.has(p.v) && BEFORE_REGEX.has(p.v);
    if (p.t === 'num' || p.t === 'str') return false;
    return !((p.v === ')' && !p.ctrl) || p.v === ']' || p.v === '}');
  };
  const braceKind = () => {                 // what the { about to open is
    const p = prev();
    for (let k = out.length - 1; k >= 0 && !['{', '}', ';', '(', ')'].includes(out[k].v); k--) {
      if (out[k].t === 'id' && out[k].v === 'class') return 'class';      // class X extends a.B {
    }
    if (p && p.t === 'p' && !['=>', ')', ']', '}', ';', '{'].includes(p.v)) return 'obj';   // where a value goes
    if (p && p.t === 'id' && BEFORE_REGEX.has(p.v) && !['else', 'do'].includes(p.v)) return 'obj';
    return 'block';
  };
  const template = () => {                  // i is just after a backtick or a closing }
    while (i < src.length) {
      const c = src[i];
      if (c === '\\') { i += 2; continue; }
      if (c === '\n') line++;
      if (c === '`') { i++; out.push({ t: 'str', v: '`', line }); return; }
      if (c === '$' && src[i + 1] === '{') { i += 2; stack.push('${'); return; }
      i++;
    }
    throw new Error('unterminated template literal');
  };
  while (i < src.length) {
    const c = src[i];
    if (c === '\n') { line++; i++; continue; }
    if (/\s/.test(c)) { i++; continue; }
    if (c === '/' && src[i + 1] === '/') { while (i < src.length && src[i] !== '\n') i++; continue; }
    if (c === '/' && src[i + 1] === '*') {
      const end = src.indexOf('*/', i + 2);
      if (end < 0) throw new Error('unterminated comment');
      line += (src.slice(i, end).match(/\n/g) || []).length;
      i = end + 2;
      continue;
    }
    if (c === '"' || c === "'") {
      let j = i + 1, v = '';
      while (j < src.length && src[j] !== c) {
        if (src[j] === '\\') { v += src[j + 1]; j += 2; continue; }
        if (src[j] === '\n') throw new Error('unterminated string, line ' + line);
        v += src[j++];
      }
      out.push({ t: 'str', v, line });
      i = j + 1;
      continue;
    }
    if (c === '`') { i++; template(); continue; }
    if (c === '/' && regexAllowed()) {
      let j = i + 1, cls = false;
      while (j < src.length && (cls || src[j] !== '/')) {
        if (src[j] === '\\') j++;
        else if (src[j] === '[') cls = true;
        else if (src[j] === ']') cls = false;
        else if (src[j] === '\n') throw new Error('unterminated regular expression, line ' + line);
        j++;
      }
      j++;
      while (/[a-z]/i.test(src[j] || '')) j++;
      out.push({ t: 'str', v: '/re/', line });
      i = j;
      continue;
    }
    if (/[A-Za-z_$]/.test(c)) {
      let j = i + 1;
      while (/[\w$]/.test(src[j] || '')) j++;
      out.push({ t: 'id', v: src.slice(i, j), line, brace: stack[stack.length - 1] });
      i = j;
      continue;
    }
    if (/[0-9]/.test(c) || (c === '.' && /[0-9]/.test(src[i + 1] || ''))) {
      let j = i + 1;
      while (/[\w.]/.test(src[j] || '') || (/[eE]/.test(src[j - 1]) && /[+-]/.test(src[j]))) j++;
      out.push({ t: 'num', v: src.slice(i, j), line });
      i = j;
      continue;
    }
    if (c === '{') stack.push(braceKind());
    if (c === '}') {
      if (stack.pop() === '${') { i++; template(); continue; }
    }
    const op = PUNCT.find(p => src.startsWith(p, i)) || c;
    const tok = { t: 'p', v: op, line };
    if (op === '(') parens.push(!!prev() && prev().t === 'id' && ['if', 'while', 'for'].includes(prev().v));
    if (op === ')') tok.ctrl = parens.pop() === true;
    out.push(tok);
    i += op.length;
  }
  return out;
}

/** Index of the token that closes the bracket at `open`. */
function closing(toks, open) {
  const pair = { '(': ')', '[': ']', '{': '}' }[toks[open].v];
  let depth = 0;
  for (let k = open; k < toks.length; k++) {
    if (toks[k].t !== 'p') continue;
    if (toks[k].v === toks[open].v) depth++;
    else if (toks[k].v === pair && --depth === 0) return k;
  }
  return toks.length - 1;
}

/** Identifiers between two token indexes (a parameter list or a destructuring pattern). */
function idsIn(toks, from, to) {
  const ids = [];
  for (let k = from; k <= to; k++) if (toks[k].t === 'id' && !KEYWORDS.has(toks[k].v)) ids.push(toks[k].v);
  return ids;
}

/** Split a file's tokens into units: runs of tokens between the points where the brace depth
 * is back at 0 (after a `}`) or a `;` ends a statement at depth 0. */
function units(toks) {
  const out = [];
  let start = 0, depth = 0;
  toks.forEach((tok, k) => {
    if (tok.t !== 'p') return;
    if (tok.v === '{') depth++;
    else if (tok.v === '}') depth--;
    if (depth === 0 && (tok.v === '}' || tok.v === ';')) { out.push([start, k]); start = k + 1; }
  });
  if (start < toks.length) out.push([start, toks.length - 1]);
  return out;
}

/** Whether `name(...) {` at k is a method in an object literal or a class body, not a call. */
function shorthand(toks, k) {
  return ['obj', 'class'].includes(toks[k].brace) && (toks[closing(toks, k + 1) + 1] || {}).v === '{';
}

function scan(file, toks, globals) {
  const services = new Set(), calls = [], handlers = [], badServices = [];
  for (const [from, to] of units(toks)) {
    const locals = new Set();
    for (let k = from; k <= to; k++) {
      const tok = toks[k], next = toks[k + 1] || {};
      if (tok.t === 'id' && ['const', 'let', 'var'].includes(tok.v)) {
        if (next.t === 'id') locals.add(next.v);
        else if (next.v === '{' || next.v === '[') idsIn(toks, k + 1, closing(toks, k + 1)).forEach(v => locals.add(v));
      } else if (tok.t === 'id' && (tok.v === 'function' || tok.v === 'catch')) {
        let open = k + 1;
        if (toks[open] && toks[open].t === 'id') locals.add(toks[open++].v);
        if (toks[open] && toks[open].v === '(') idsIn(toks, open, closing(toks, open)).forEach(v => locals.add(v));
      } else if (tok.v === '=>') {
        const p = toks[k - 1];
        if (p.t === 'id') locals.add(p.v);
        else if (p.v === ')') {
          let open = k - 1;
          for (let d = 0; open > from; open--) {
            if (toks[open].v === ')') d++;
            else if (toks[open].v === '(' && --d === 0) break;
          }
          idsIn(toks, open, k - 1).forEach(v => locals.add(v));
        }
      } else if (tok.t === 'id' && next.v === '(' && !KEYWORDS.has(tok.v) && shorthand(toks, k)) {
        idsIn(toks, k + 1, closing(toks, k + 1)).forEach(v => locals.add(v));
      }
    }
    for (let k = from; k <= to; k++) {
      const tok = toks[k], before = toks[k - 1] || {}, next = toks[k + 1] || {};
      if (tok.t !== 'id' || KEYWORDS.has(tok.v)) continue;
      const member = before.v === '.' || before.v === '?.';
      const key = next.v === ':' && tok.brace === 'obj';      // { Forms: ... } names no service
      if (!member && SERVICES.includes(tok.v)) services.add(tok.v);
      else if (!member && !key && (SERVICE_RX.test(tok.v) || SCOPED.has(tok.v)) && !globals.has(tok.v) &&
               !locals.has(tok.v)) badServices.push({ file, line: tok.line, name: tok.v });
      if (next.v !== '(') continue;
      if (member) {                             // addItem('Label', 'fn') and newTrigger('fn')
        const args = toks.slice(k + 2, closing(toks, k + 1));
        let named = null;
        if (tok.v === 'newTrigger' && args.length === 1 && args[0].t === 'str') named = args[0];
        if (tok.v === 'addItem' && args.length >= 3 && args[args.length - 2].v === ',' &&
            args[args.length - 1].t === 'str') named = args[args.length - 1];
        if (named) handlers.push({ file, line: named.line, name: named.v, ok: globals.has(named.v) });
        continue;
      }
      if (before.v === 'function') continue;       // a declaration's name
      if (shorthand(toks, k)) continue;              // a method: name(params) { ... }
      calls.push({ file, line: tok.line, name: tok.v,
                   ok: locals.has(tok.v) || globals.has(tok.v) || BUILTINS.has(tok.v) });
    }
  }
  return { services, calls, handlers, badServices };
}

/** Top-level names a .gs file declares: function, const, let, var, class (depth 0). */
function topLevel(toks) {
  const names = new Set();
  let depth = 0;
  toks.forEach((tok, k) => {
    if (tok.t === 'p' && tok.v === '{') depth++;
    if (tok.t === 'p' && tok.v === '}') depth--;
    if (depth !== 0 || tok.t !== 'id') return;
    const next = toks[k + 1] || {};
    if (['function', 'class', 'const', 'let', 'var'].includes(tok.v) && next.t === 'id') names.add(next.v);
    if (['const', 'let', 'var'].includes(tok.v) && (next.v === '{' || next.v === '[')) {
      idsIn(toks, k + 1, closing(toks, k + 1)).forEach(v => names.add(v));
    }
  });
  return names;
}

const dir = loadGs.GS_DIR;
const files = fs.readdirSync(dir).filter(f => f.endsWith('.gs')).sort();
let failures = 0;
const fail = msg => { failures++; console.log('  FAIL ' + msg); };
const sources = {};
for (const f of files) {
  sources[f] = fs.readFileSync(path.join(dir, f), 'utf8');
  try {
    new vm.Script(sources[f], { filename: f });
  } catch (err) {
    fail(f + ' :: ' + err.message);
  }
}
try {
  loadGs(['TAB', 'ROSTER_COLS', 'parseRoster_', 'planClub_', 'buildDispatchRequest_']);
} catch (err) {
  fail('pure files do not load together :: ' + err.message);
}

// the manifest: an advanced service or a pinned scope list is a scope change too (none today)
const manifest = JSON.parse(fs.readFileSync(path.join(dir, 'appsscript.json'), 'utf8'));
const advanced = ((manifest.dependencies || {}).enabledAdvancedServices || []).map(s => s.userSymbol || s.serviceId);
if (advanced.length || 'oauthScopes' in manifest) {
  fail(`appsscript.json ${advanced.length ? 'enables advanced services (' + advanced.join(', ') + ')' : 'pins oauthScopes'}: ` +
       'a scope change, and until the owner re-authorizes the form-submit trigger fails hard (CLAUDE.md rule 11) - ' +
       'pin it in scripts/check_gs.js only with that plan');
}

const tokens = {}, globals = new Set();
for (const f of files) {
  try {
    tokens[f] = tokenize(sources[f]);
    topLevel(tokens[f]).forEach(n => globals.add(n));
  } catch (err) {
    fail(f + ' :: the call scan cannot read it: ' + err.message);
  }
}
const used = new Set();
let checked = 0, handlerCount = 0, unknown = 0;
for (const f of Object.keys(tokens)) {
  const r = scan(f, tokens[f], globals);
  r.services.forEach(s => used.add(s));
  for (const b of r.badServices) {
    fail(`${b.file}:${b.line}: ${b.name} is not one of the pinned Google services (${SERVICES.join(', ')}). ` +
         'A new service adds an OAuth scope, and until the owner re-authorizes, the form-submit ' +
         'trigger fails hard (CLAUDE.md rule 11): pin it in scripts/check_gs.js only with that plan.');
  }
  for (const c of r.calls.concat(r.handlers)) {
    checked++;
    if (r.handlers.includes(c)) handlerCount++;
    if (!c.ok) {
      unknown++;
      fail(`${c.file}:${c.line}: ${c.name} is not a function of any .gs file, a local or a ` +
           'JavaScript built-in (renamed or deleted? it would fail only live, in the trigger)');
    }
  }
}
if (failures) {
  console.log('gs: ' + failures + ' FAILURE(S)');
  process.exit(1);
}
console.log(`gs: ${files.length} files parse, ${used.size} services, ${unknown} unknown calls ` +
            `(${checked} checked, ${handlerCount} of them menu or trigger handlers)`);
