/* i18n.js — tiny client-side message resolver, mirroring the server (v2/i18n.py).
 *
 * Reads the message island `window.wpMessages` = { locale, dir, messages } that base.html
 * emits, and exposes `window.wpI18n.msg(key, ...params)`:
 *   - $1..$n parameter substitution
 *   - {{PLURAL:$n|a|b}} expansion (English/Germanic rule for now)
 *   - missing key -> ⧼key⧽ (loud), matching the server
 * The banana JSON message format is shared with translatewiki.net. Swapping this shim for
 * the full banana-i18n library (CLDR plural/gender for non-English) is a later follow-up;
 * for the English source locale the rule below is exact.
 */
(function (global) {
  'use strict';
  var data = global.wpMessages || { messages: {}, locale: 'en', dir: 'ltr' };
  var messages = data.messages || {};

  function pluralIndex(n) { return n === 1 ? 0 : 1; }   // English rule (v1)

  function expand(text, params) {
    text = text.replace(/\{\{PLURAL:\$(\d+)\|([^}]*)\}\}/g, function (_m, idx, forms) {
      var n = parseInt(params[parseInt(idx, 10) - 1], 10);
      if (isNaN(n)) { n = 0; }
      var parts = forms.split('|');
      var i = pluralIndex(n);
      return parts[i] !== undefined ? parts[i] : (parts.length ? parts[parts.length - 1] : '');
    });
    for (var i = params.length; i >= 1; i--) {   // high indices first: $10 before $1
      text = text.split('$' + i).join(String(params[i - 1]));
    }
    return text;
  }

  function msg(key) {
    var params = Array.prototype.slice.call(arguments, 1);
    var text = messages[key];
    if (text === undefined || text === null) { return '⧼' + key + '⧽'; }
    return expand(text, params);
  }

  global.wpI18n = { msg: msg, locale: data.locale, dir: data.dir };
})(window);
