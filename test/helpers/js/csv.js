'use strict';
/**
 * The CSV reader of the JS tests and tools/build_roster_offline.js: quoted
 * fields with embedded commas, quotes ("") and newlines, as the enrollment
 * export and the sheet exports write them; a \r is dropped.
 */
const fs = require('fs');

function parseCsv(text) {
  const rows = [];
  let row = [], field = '', inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') inQuotes = false;
      else field += c;
    } else if (c === '"') inQuotes = true;
    else if (c === ',') { row.push(field); field = ''; }
    else if (c === '\n') { row.push(field); rows.push(row); row = []; field = ''; }
    else if (c !== '\r') field += c;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  return rows;
}

/** A CSV file's rows, a leading byte-order mark dropped. */
function readCsv(file) {
  return parseCsv(fs.readFileSync(file, 'utf8').replace(/^﻿/, ''));
}

module.exports = { parseCsv, readCsv };
