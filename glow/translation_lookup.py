"""Jotform's translation-dictionary lookup, emulated (docs/plans/2026-10-02-names-and-modules.md).

The calculation that fills question 18 (the girls Salesforce stores as present)
reads each ticked box's data-calcvalue, else FormTranslation.translate(value),
else the value - never the label (.claude/skills/jotform-api). translate() looks
the text up in a dictionary the runtime builds, in the browser, from the form's
translation store (GET /form/{id}/translations: {language: {md5 key: text}}).
Building it collapses whitespace in every key, so a stale `base`/`en` entry that
spells a girl's name with a double space, a tab or a non-breaking space lands on
her exact name, and question 18 sends the stale spelling: a second Contact in
Salesforce. This module rebuilds that dictionary as the runtime does and runs its
lookup, so the tools can count the roster options it alters and name the store
entries responsible (tools/fix_name_translations.py, tools/form_status.py). It
never prints anything: callers report counts and club names, never a girl's name.

Read from Jotform's formTranslation.v2.js (the builds served on 2026-10-02,
62a8b57dd95 on the regional forms and fc726a121d4 on the template, are byte-
identical; the runtime investigation of 2026-09-30 read build 9e75d6f1d83):

- setDictionary: the original language is `base` (isBaseTranslationEnabled()
  returns true). dictionary.base maps each entry's `en` text to its `base` text;
  every other language L (its code trimmed) maps the entry's `base` text, trimmed,
  to L's text, trimmed - or, when the `en` text starts with `text_`/`FITB_` (an
  element id), that id. An entry missing in `en` (for dictionary.base) or in
  `base` (for the others) is skipped by the 2026-10-02 builds and filed under the
  key "undefined" by 9e75d6f1d83 (`skip_missing`; the audits run both).
  setSimplifiedDictionary then keeps simplifyfWord() of every value, keyed as
  the dictionary is at that moment.
- trimMultiSpaces, then sanitizeKeys: every key whose whitespace runs collapse
  to one space (and, in sanitizeKeys, whose &gt; &lt; <br> <br /> are replaced)
  is moved to the new key, OVERWRITING an entry already there: the stale
  spelling wins over the exact one, whatever their order. Both walk a snapshot
  of each language (Prototype's $H clones), assigning the snapshot's values.
- translateUncached(word): simplifyfWord(word); the `to` language's entry for it
  when truthy; else, when the word holds a no-break space (U+00A0, U+202F),
  translate() of the word with those replaced; else the first language, in the
  order of the runtime's own languages map (`RUNTIME_LANGUAGE_ORDER`), other
  than `to` with an entry - by the dictionary's current keys - whose simplified
  value (looked up under the key as it was BEFORE the renames), no-break spaces
  replaced, equals the word and for whose key `to` has a truthy entry: that
  entry; else the word unchanged.

JavaScript's whitespace (\\s, String.prototype.trim, Prototype's strip) is not
Python's: no U+001C-U+001F or U+0085, but U+FEFF. U+200E (left-to-right mark)
is no whitespace on either side: a key holding one is never collapsed. Object
keys iterate integer-like keys first, ascending, then the rest in insertion
order (`js_order`). A store entry that is not text is refused (`check_store`):
the runtime would throw on it, which this module does not emulate.
"""
import re

# the runtime's \s / trim(): ECMAScript WhiteSpace + LineTerminator
JS_WS = ("\t\n\v\f\r             "
         "     　﻿")
_WS_RUN = re.compile("[" + re.escape(JS_WS) + "]+")
_NBSP = re.compile("[  ]")
_INDEX = re.compile(r"^(?:0|[1-9][0-9]*)$")
# simplifyfWord's replaceMap, in its order; each one replaced until none is left
_SIMPLIFY = (("&gt;", ">"), ("&lt;", "<"), ("&emsp;", " "), ("&nbsp;", " "), ("<br>", " "),
             ("&amp;", "&"), ("\n", " "), ("\t", " "), ("  ", " "), ("　", " "))

# The 2026-10-02 builds skip an entry missing in `en` or `base`; 9e75d6f1d83 filed it
# under "undefined". The audits run both (BUILDS): a form can be served either.
SKIP_MISSING = True
BUILDS = (True, False)

# The order translateUncached's fall-back walks the languages in: the distinct codes of
# FormTranslation.languages (formTranslation.v2.js, build 62a8b57dd95, read 2026-10-02)
# in order of first appearance. Only the languages a store holds take part.
RUNTIME_LANGUAGE_ORDER = (
    "en", "en-UK", "es", "fr", "it", "pt", "de", "tr", "ca", "nl", "sv", "hu", "no", "da", "ro",
    "fi", "pl", "ru", "zh", "af", "sq", "am", "ar", "hy", "az", "eu", "be", "bn", "bh", "bs", "br",
    "bg", "zh-CN", "zh-TW", "co", "hr", "cs", "en-AU", "en-CA", "en-NZ", "en-ZA", "eo", "et", "fo",
    "fil", "fr-CA", "fr-FR", "fr-CH", "gl", "ka", "de-AT", "de-DE", "de-CH", "el", "gn", "gu", "ht",
    "ha", "haw", "he", "hi", "is", "id", "ia", "ga", "it-CH", "ja", "jw", "kn", "kk", "km", "ky",
    "ko", "ku", "lo", "la", "lv", "ln", "lt", "mk", "ms", "ml", "mt", "mr", "mo", "mn", "ne", "nb",
    "nn", "oc", "or", "om", "ps", "fa", "pt-BR", "pt-PT", "pa", "qu", "rm", "gd", "sr", "sh", "sn",
    "sd", "si", "sk", "sl", "so", "st", "es-419", "su", "sw", "tg", "ta", "tt", "te", "th", "ti",
    "to", "tk", "tw", "ug", "uk", "ur", "uz", "vi", "cy", "fy", "xh", "yi", "yo", "zu", "ar-EG",
    "ar-SA", "ar-AE", "as", "bzj", "my", "ceb", "dag", "prs", "dv", "nl-BE", "en-IN", "en-PH", "ff",
    "fr-BE", "hmn", "ig", "kar", "rw", "kri", "kea", "lb", "mai", "mg", "jam", "pa-IN", "pa-PK",
    "sm", "es-AR", "es-CO", "es-MX", "es-US", "tl", "tet", "zh-HK", "wo")

SOURCE = "base"      # the original language (isBaseTranslationEnabled)
PRIMARY = "en"       # the forms' primaryLanguage (the `language` property, read 2026-10-02)
_MISSING = object()


def js_trim(s):
    """String.prototype.trim / Prototype's strip()."""
    return s.strip(JS_WS)


def simplify(word):
    """FormTranslation.simplifyfWord."""
    for find, repl in _SIMPLIFY:
        while find in word:
            word = word.replace(find, repl, 1)
    return js_trim(word)


def replace_nbsp(word):
    """FormTranslation.replaceNbsp."""
    return _NBSP.sub(" ", word)


def js_order(obj):
    """The keys of a JavaScript object in its iteration order: integer-like keys
    (array indices) first, ascending, then the others in insertion order."""
    keys = list(obj)
    index = sorted((k for k in keys if _INDEX.match(k) and int(k) < 4294967295), key=int)
    return index + [k for k in keys if k not in set(index)]


def _js_key(value):
    """A value used as an object key, as JavaScript turns it into one."""
    if isinstance(value, str):
        return value
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _collapse(key):
    """trimMultiSpaces' new key."""
    return js_trim(_WS_RUN.sub(" ", key))


def _sanitize(key):
    """sanitizeKeys' new key."""
    key = js_trim(js_trim(key))
    for find, repl in (("&gt;", ">"), ("&lt;", "<"), ("<br>", " "), ("<br />", " ")):
        key = js_trim(key.replace(find, repl))
    return js_trim(_WS_RUN.sub(" ", key))


def check_store(store):
    """Why this store's dictionary cannot be emulated here, or None: not a
    {language: {key: text}} store, no `base` (the runtime would then guess the
    original language from the page's labels), or an entry that is not text."""
    if not isinstance(store, dict) or not all(isinstance(v, dict) for v in store.values()):
        return "not a translation store ({language: {key: text}})"
    if SOURCE not in store:
        return f"the store has no {SOURCE!r} dictionary"
    bad = sum(1 for d in store.values() for v in d.values() if not isinstance(v, str))
    if bad:
        return f"{bad} entr{'y is' if bad == 1 else 'ies are'} not text"
    return None


class Lookup:
    """The runtime's dictionary for one store, and its lookup (see the module doc)."""

    def __init__(self, store, primary=PRIMARY, skip_missing=SKIP_MISSING, codes=RUNTIME_LANGUAGE_ORDER):
        why = check_store(store)
        if why:
            raise ValueError(why)
        self.primary = primary
        d, origin = {}, {}
        if primary in store:                 # else setDictionary leaves the dictionary empty
            base, prim = store[SOURCE], store[primary]
            d[SOURCE], origin[SOURCE] = {}, {}
            for k in js_order(base):
                pv = prim.get(k, _MISSING)
                if pv is _MISSING:
                    if skip_missing:
                        continue
                    pv = "undefined"
                key = _js_key(pv)
                d[SOURCE][key], origin[SOURCE][key] = base[k], k
            for lang in store:
                code = js_trim(lang)
                if code == SOURCE:
                    continue
                d[code], origin[code] = {}, {}
                for k in js_order(store[lang]):
                    kv = base.get(k, _MISSING)
                    key = js_trim(kv) if isinstance(kv, str) and kv else kv
                    pe = prim.get(k)
                    if isinstance(pe, str) and pe.startswith(("text_", "FITB_")):
                        key = pe
                    if key is _MISSING:
                        if skip_missing:
                            continue
                        key = "undefined"
                    value = store[lang][k]
                    d[code][_js_key(key)] = js_trim(value) if value else value
                    origin[code][_js_key(key)] = k
        # setSimplifiedDictionary, before the keys move
        self.simplified = {lang: {k: simplify(v) for k, v in dd.items()} for lang, dd in d.items()}
        self._origin_before = {lang: dict(o) for lang, o in origin.items()}
        for rename in (_collapse, _sanitize):         # trimMultiSpaces, then sanitizeKeys
            for lang in list(d):
                snapshot = [(k, d[lang][k], origin[lang].get(k)) for k in js_order(d[lang])]
                for k, value, src in snapshot:
                    new = rename(k)
                    if new != k:
                        d[lang][new], origin[lang][new] = value, src
                        d[lang].pop(k, None)
                        origin[lang].pop(k, None)
        self.dictionary, self._origin = d, origin
        # the fall-back's walk: per language, the simplified value (under the key as it was
        # before the renames) with no-break spaces replaced -> the keys it is found under, in order
        self._codes = [c for c in dict.fromkeys(codes) if c in d]
        self._reverse = {}
        for c in self._codes:
            rev = {}
            for key in js_order(d[c]):
                compare = self.simplified[c].get(key)
                if compare:
                    rev.setdefault(replace_nbsp(compare), []).append(key)
            self._reverse[c] = rev

    def trace(self, word, to):
        """(what translate(word) returns while the form shows language `to`, the
        dictionary entries that decided it: [(role, language, key)], [] when none
        did). role "value": the entry whose text is returned; "match": the entry of
        the fall-back's language whose simplified text equalled the word."""
        if not isinstance(word, str):
            return None, []
        tmp = simplify(word)
        if not tmp:
            return "", []
        target = self.dictionary.get(to)
        if target is not None and target.get(tmp):
            return target[tmp], [("value", to, tmp)]
        nbsp = replace_nbsp(tmp)
        if nbsp != tmp:
            return self.trace(nbsp, to)
        if target is not None:
            for c in self._codes:
                if c == to:
                    continue
                for key in self._reverse[c].get(tmp, ()):
                    if target.get(key):
                        return target[key], [("match", c, key), ("value", to, key)]
        return word, []

    def translate(self, word, to):
        return self.trace(word, to)[0]

    def sources(self, hits):
        """The store keys (md5) behind the dictionary entries of a trace: a value's
        entry as the dictionary holds it after the renames, a match's as it was when
        the simplified texts were taken (and the one now under its key)."""
        out = set()
        for role, lang, key in hits:
            origins = (self._origin,) if role == "value" else (self._origin_before, self._origin)
            for origin in origins:
                k = origin.get(lang, {}).get(key)
                if k is not None:
                    out.add(k)
        return out


def target_languages(store):
    """Every language a form can be shown in that has a dictionary: the store's
    languages but `base` (a language without one alters nothing - the lookup
    needs its entries). A superset of the offered languages that matter."""
    return [c for c in dict.fromkeys(js_trim(lang) for lang in store) if c != SOURCE]


def is_altered(option, result):
    """Whether the checkbox reader sends something else than the option: it takes
    translate(value) when that is not empty."""
    return bool(result) and result != option


def altered(store, options, primary=PRIMARY, builds=BUILDS, codes=RUNTIME_LANGUAGE_ORDER):
    """{option: sorted languages under which the lookup changes it} for every option
    some language alters in any of the runtime builds. The changed texts are not
    returned: they are girls' names."""
    out = {}
    langs = target_languages(store)
    for skip in builds:
        lookup = Lookup(store, primary, skip, codes)
        for option in options:
            for to in langs:
                if is_altered(option, lookup.translate(option, to)):
                    out.setdefault(option, set()).add(to)
    return {o: sorted(v) for o, v in out.items()}


def without(store, keys, languages=(SOURCE, PRIMARY)):
    """The store with `keys` taken out of `languages` (the other languages as they are)."""
    keys = set(keys)
    return {lang: ({k: v for k, v in d.items() if k not in keys} if js_trim(lang) in languages else d)
            for lang, d in store.items()}


def removal(store, options, primary=PRIMARY, builds=BUILDS, codes=RUNTIME_LANGUAGE_ORDER, max_rounds=50):
    """The `base`/`primary` entries to remove so that no option is altered in any
    language or build: (keys, None), or (None, why not). Each round takes out the
    entries behind every remaining alteration - only those - and looks again:
    removing one can uncover an older spelling of the same name, which the next
    round finds. It cannot be done by removal, and says so, when an alteration
    comes from another language (a translation of the name in it, or a key to
    remove that another language translates: never removed, its translation
    would be orphaned) or from no entry at all (a no-break space in the option)."""
    others = {lang: set(d) for lang, d in store.items() if js_trim(lang) not in (SOURCE, primary)}
    removed = set()
    langs = target_languages(store)
    for _ in range(max_rounds):
        current = without(store, removed, (SOURCE, primary))
        culprits, foreign, unexplained = set(), {}, 0
        for skip in builds:
            lookup = Lookup(current, primary, skip, codes)
            for option in options:
                for to in langs:
                    result, hits = lookup.trace(option, to)
                    if not is_altered(option, result):
                        continue
                    keys = lookup.sources(hits)
                    if not keys:
                        unexplained += 1
                    involved = {js_trim(lang) for lang, held in others.items() if keys & held}
                    involved |= {lang for _, lang, _ in hits if lang not in (SOURCE, primary)}
                    for lang in involved:
                        foreign[lang] = foreign.get(lang, 0) + 1
                    culprits |= keys
        if foreign:
            return None, ("an alteration involves another language's entries ("
                          + ", ".join(f"{lang}: {n}" for lang, n in sorted(foreign.items()))
                          + "): removing base/en entries cannot fix it, and a key another "
                          "language translates is never removed")
        if unexplained:
            return None, (f"{unexplained} alteration(s) come from no dictionary entry (a no-break "
                          "space in the option itself?)")
        if not culprits:
            return removed, None
        removed |= culprits
    return None, f"no end after {max_rounds} rounds of removal"
