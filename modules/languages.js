// sandpie /modules/languages.js — SandpieLanguage: the language sandpie replies in.
//
// One source of truth for the reply language:
//  - a COMPLETE ISO 639-1 list (184 languages; native + English names) plus the
//    script/region variants that matter for LLM output: zh-Hans/zh-Hant, pt-BR/pt-PT,
//  - automatic detection of the browser/OS language on first run ('auto'),
//  - a system-message directive that forces the LLM to reply in the chosen
//    language unless the user explicitly asks otherwise (translation, etc.),
//    regardless of the language of materials read via tool calls.
//
// The directive is consumed by:
//  - conversations.js buildSystemPrompt() → appended to the per-turn system
//    message (covers every provider and the Ralph loop, which shares it),
//  - conversations.js buildAgentConfig() → shipped as config.languageRule so
//    sandpie-worker.js can also append it to subagent system prompts.
//
// Storage: SandpieConfig namespace 'language' when available, else plain
// localStorage 'sandpie-language'. Values: 'auto' | code ('es', 'zh-Hans', …).
//
// CLASSIC script (global window.SandpieLanguage). Load after config.js and
// before account.js (the Account settings panel hosts the picker).

const SandpieLanguage = (() => {
  'use strict';

  // ISO 639-1 (184) — generated from iso-codes; native names from CLDR
  // (Intl.DisplayNames); sorted by native name.
  const LANGUAGES = [
    { code: "ab", name: "Abkhazian", native: "Abkhazian" },
    { code: "aa", name: "Afar", native: "Afar" },
    { code: "af", name: "Afrikaans", native: "Afrikaans" },
    { code: "ak", name: "Akan", native: "Akan" },
    { code: "tw", name: "Akan", native: "Akan" },
    { code: "an", name: "Aragonese", native: "Aragonese" },
    { code: "av", name: "Avaric", native: "Avaric" },
    { code: "ae", name: "Avestan", native: "Avestan" },
    { code: "ay", name: "Aymara", native: "Aymara" },
    { code: "az", name: "Azerbaijani", native: "azərbaycan" },
    { code: "bm", name: "Bambara", native: "bamanakan" },
    { code: "su", name: "Sundanese", native: "Basa Sunda" },
    { code: "bh", name: "Bhojpuri", native: "Bhojpuri" },
    { code: "bi", name: "Bislama", native: "Bislama" },
    { code: "bs", name: "Bosnian", native: "bosanski" },
    { code: "br", name: "Breton", native: "brezhoneg" },
    { code: "ca", name: "Catalan", native: "català" },
    { code: "cs", name: "Czech", native: "čeština" },
    { code: "ch", name: "Chamorro", native: "Chamorro" },
    { code: "sn", name: "Shona", native: "chiShona" },
    { code: "cu", name: "Church Slavic", native: "Church Slavic" },
    { code: "co", name: "Corsican", native: "Corsican" },
    { code: "cr", name: "Cree", native: "Cree" },
    { code: "cy", name: "Welsh", native: "Cymraeg" },
    { code: "da", name: "Danish", native: "dansk" },
    { code: "se", name: "Northern Sami", native: "davvisámegiella" },
    { code: "de", name: "German", native: "Deutsch" },
    { code: "dv", name: "Divehi", native: "Divehi" },
    { code: "yo", name: "Yoruba", native: "Èdè Yorùbá" },
    { code: "et", name: "Estonian", native: "eesti" },
    { code: "en", name: "English", native: "English" },
    { code: "es", name: "Spanish", native: "español" },
    { code: "eo", name: "Esperanto", native: "Esperanto" },
    { code: "eu", name: "Basque", native: "euskara" },
    { code: "ee", name: "Ewe", native: "eʋegbe" },
    { code: "fj", name: "Fijian", native: "Fijian" },
    { code: "tl", name: "Filipino", native: "Filipino" },
    { code: "fo", name: "Faroese", native: "føroyskt" },
    { code: "fr", name: "French", native: "français" },
    { code: "fy", name: "Western Frisian", native: "Frysk" },
    { code: "ga", name: "Irish", native: "Gaeilge" },
    { code: "gv", name: "Manx", native: "Gaelg" },
    { code: "gd", name: "Scottish Gaelic", native: "Gàidhlig" },
    { code: "gl", name: "Galician", native: "galego" },
    { code: "ki", name: "Kikuyu", native: "Gikuyu" },
    { code: "gn", name: "Guarani", native: "Guarani" },
    { code: "ht", name: "Haitian Creole", native: "Haitian Creole" },
    { code: "ha", name: "Hausa", native: "Hausa" },
    { code: "hz", name: "Herero", native: "Herero" },
    { code: "ho", name: "Hiri Motu", native: "Hiri Motu" },
    { code: "hr", name: "Croatian", native: "hrvatski" },
    { code: "io", name: "Ido", native: "Ido" },
    { code: "ig", name: "Igbo", native: "Igbo" },
    { code: "rw", name: "Kinyarwanda", native: "Ikinyarwanda" },
    { code: "rn", name: "Rundi", native: "Ikirundi" },
    { code: "id", name: "Indonesian", native: "Indonesia" },
    { code: "ia", name: "Interlingua", native: "interlingua" },
    { code: "ie", name: "Interlingue", native: "Interlingue" },
    { code: "iu", name: "Inuktitut", native: "Inuktitut" },
    { code: "ik", name: "Inupiaq", native: "Inupiaq" },
    { code: "nd", name: "North Ndebele", native: "isiNdebele" },
    { code: "xh", name: "Xhosa", native: "IsiXhosa" },
    { code: "zu", name: "Zulu", native: "isiZulu" },
    { code: "is", name: "Icelandic", native: "íslenska" },
    { code: "it", name: "Italian", native: "italiano" },
    { code: "jv", name: "Javanese", native: "Jawa" },
    { code: "kl", name: "Kalaallisut", native: "kalaallisut" },
    { code: "kr", name: "Kanuri", native: "Kanuri" },
    { code: "kw", name: "Cornish", native: "kernewek" },
    { code: "sw", name: "Swahili", native: "Kiswahili" },
    { code: "kv", name: "Komi", native: "Komi" },
    { code: "kg", name: "Kongo", native: "Kongo" },
    { code: "kj", name: "Kuanyama", native: "Kuanyama" },
    { code: "ku", name: "Kurdish", native: "kurdî (kurmancî)" },
    { code: "la", name: "Latin", native: "Latin" },
    { code: "lv", name: "Latvian", native: "latviešu" },
    { code: "to", name: "Tongan", native: "lea fakatonga" },
    { code: "lb", name: "Luxembourgish", native: "Lëtzebuergesch" },
    { code: "lt", name: "Lithuanian", native: "lietuvių" },
    { code: "li", name: "Limburgish", native: "Limburgish" },
    { code: "ln", name: "Lingala", native: "lingála" },
    { code: "lg", name: "Ganda", native: "Luganda" },
    { code: "hu", name: "Hungarian", native: "magyar" },
    { code: "mg", name: "Malagasy", native: "Malagasy" },
    { code: "mt", name: "Maltese", native: "Malti" },
    { code: "mi", name: "Māori", native: "Māori" },
    { code: "mh", name: "Marshallese", native: "Marshallese" },
    { code: "ms", name: "Malay", native: "Melayu" },
    { code: "na", name: "Nauru", native: "Nauru" },
    { code: "nv", name: "Navajo", native: "Navajo" },
    { code: "ng", name: "Ndonga", native: "Ndonga" },
    { code: "nl", name: "Dutch", native: "Nederlands" },
    { code: "no", name: "Norwegian", native: "norsk" },
    { code: "nb", name: "Norwegian Bokmål", native: "norsk bokmål" },
    { code: "nn", name: "Norwegian Nynorsk", native: "norsk nynorsk" },
    { code: "ny", name: "Nyanja", native: "Nyanja" },
    { code: "uz", name: "Uzbek", native: "o‘zbek" },
    { code: "oc", name: "Occitan", native: "occitan" },
    { code: "oj", name: "Ojibwa", native: "Ojibwa" },
    { code: "om", name: "Oromo", native: "Oromoo" },
    { code: "pi", name: "Pali", native: "Pali" },
    { code: "pl", name: "Polish", native: "polski" },
    { code: "pt", name: "Portuguese", native: "português" },
    { code: "ff", name: "Fula", native: "Pulaar" },
    { code: "ro", name: "Romanian", native: "română" },
    { code: "rm", name: "Romansh", native: "rumantsch" },
    { code: "qu", name: "Quechua", native: "Runasimi" },
    { code: "sm", name: "Samoan", native: "Samoan" },
    { code: "sg", name: "Sango", native: "Sängö" },
    { code: "sc", name: "Sardinian", native: "sardu" },
    { code: "st", name: "Southern Sotho", native: "Sesotho" },
    { code: "tn", name: "Tswana", native: "Setswana" },
    { code: "sq", name: "Albanian", native: "shqip" },
    { code: "sk", name: "Slovak", native: "slovenčina" },
    { code: "sl", name: "Slovenian", native: "slovenščina" },
    { code: "so", name: "Somali", native: "Soomaali" },
    { code: "nr", name: "South Ndebele", native: "South Ndebele" },
    { code: "fi", name: "Finnish", native: "suomi" },
    { code: "sv", name: "Swedish", native: "svenska" },
    { code: "ss", name: "Swati", native: "Swati" },
    { code: "ty", name: "Tahitian", native: "Tahitian" },
    { code: "vi", name: "Vietnamese", native: "Tiếng Việt" },
    { code: "lu", name: "Luba-Katanga", native: "Tshiluba" },
    { code: "ts", name: "Tsonga", native: "Tsonga" },
    { code: "tr", name: "Turkish", native: "Türkçe" },
    { code: "tk", name: "Turkmen", native: "türkmen dili" },
    { code: "za", name: "Zhuang", native: "Vahcuengh" },
    { code: "ve", name: "Venda", native: "Venda" },
    { code: "vo", name: "Volapük", native: "Volapük" },
    { code: "wa", name: "Walloon", native: "Walloon" },
    { code: "wo", name: "Wolof", native: "Wolof" },
    { code: "el", name: "Greek", native: "Ελληνικά" },
    { code: "ba", name: "Bashkir", native: "башҡорт" },
    { code: "be", name: "Belarusian", native: "беларуская" },
    { code: "bg", name: "Bulgarian", native: "български" },
    { code: "os", name: "Ossetic", native: "ирон" },
    { code: "ky", name: "Kyrgyz", native: "кыргызча" },
    { code: "kk", name: "Kazakh", native: "қазақ тілі" },
    { code: "mk", name: "Macedonian", native: "македонски" },
    { code: "mn", name: "Mongolian", native: "монгол" },
    { code: "ce", name: "Chechen", native: "нохчийн" },
    { code: "ru", name: "Russian", native: "русский" },
    { code: "sr", name: "Serbian", native: "српски" },
    { code: "tt", name: "Tatar", native: "татар" },
    { code: "tg", name: "Tajik", native: "тоҷикӣ" },
    { code: "uk", name: "Ukrainian", native: "українська" },
    { code: "cv", name: "Chuvash", native: "чӑваш чӗлхи" },
    { code: "ka", name: "Georgian", native: "ქართული" },
    { code: "hy", name: "Armenian", native: "հայերեն" },
    { code: "yi", name: "Yiddish", native: "ייִדיש" },
    { code: "he", name: "Hebrew", native: "עברית" },
    { code: "ug", name: "Uyghur", native: "ئۇيغۇرچە" },
    { code: "ur", name: "Urdu", native: "اردو" },
    { code: "ar", name: "Arabic", native: "العربية" },
    { code: "ps", name: "Pashto", native: "پښتو" },
    { code: "sd", name: "Sindhi", native: "سنڌي" },
    { code: "fa", name: "Persian", native: "فارسی" },
    { code: "ks", name: "Kashmiri", native: "کٲشُر" },
    { code: "ti", name: "Tigrinya", native: "ትግርኛ" },
    { code: "am", name: "Amharic", native: "አማርኛ" },
    { code: "ne", name: "Nepali", native: "नेपाली" },
    { code: "mr", name: "Marathi", native: "मराठी" },
    { code: "sa", name: "Sanskrit", native: "संस्कृत भाषा" },
    { code: "hi", name: "Hindi", native: "हिन्दी" },
    { code: "as", name: "Assamese", native: "অসমীয়া" },
    { code: "bn", name: "Bangla", native: "বাংলা" },
    { code: "pa", name: "Punjabi", native: "ਪੰਜਾਬੀ" },
    { code: "gu", name: "Gujarati", native: "ગુજરાતી" },
    { code: "or", name: "Odia", native: "ଓଡ଼ିଆ" },
    { code: "ta", name: "Tamil", native: "தமிழ்" },
    { code: "te", name: "Telugu", native: "తెలుగు" },
    { code: "kn", name: "Kannada", native: "ಕನ್ನಡ" },
    { code: "ml", name: "Malayalam", native: "മലയാളം" },
    { code: "si", name: "Sinhala", native: "සිංහල" },
    { code: "th", name: "Thai", native: "ไทย" },
    { code: "lo", name: "Lao", native: "ລາວ" },
    { code: "bo", name: "Tibetan", native: "བོད་སྐད་" },
    { code: "dz", name: "Dzongkha", native: "རྫོང་ཁ" },
    { code: "my", name: "Burmese", native: "မြန်မာ" },
    { code: "km", name: "Khmer", native: "ខ្មែរ" },
    { code: "ko", name: "Korean", native: "한국어" },
    { code: "ii", name: "Sichuan Yi", native: "ꆈꌠꉙ" },
    { code: "zh", name: "Chinese", native: "中文" },
    { code: "ja", name: "Japanese", native: "日本語" },
  ];

  // Script/region variants worth distinguishing in LLM output. `match` maps a
  // base language to the BCP-47 regions that select this variant.
  const VARIANTS = [
    { code: 'zh-Hans', name: 'Chinese (Simplified)', native: '简体中文', match: { zh: ['CN', 'SG'] } },
    { code: 'zh-Hant', name: 'Chinese (Traditional)', native: '繁體中文', match: { zh: ['TW', 'HK', 'MO'] } },
    { code: 'pt-BR',   name: 'Portuguese (Brazil)',   native: 'Português (Brasil)',   match: { pt: ['BR'] } },
    { code: 'pt-PT',   name: 'Portuguese (Portugal)', native: 'Português (Portugal)', match: { pt: ['PT'] } },
  ];

  const LS_KEY = 'sandpie-language';
  const CONFIG_NS = 'language';

  function stored() {
    let v = null;
    try {
      if (typeof SandpieConfig !== 'undefined' && SandpieConfig.get) {
        const c = SandpieConfig.get(CONFIG_NS, undefined);
        if (c !== undefined && c !== null) return c === 'auto' ? 'auto' : String(c);
      }
      v = localStorage.getItem(LS_KEY);
    } catch (_) {}
    return v || 'auto';
  }
  function set(v) {
    const val = (v == null || v === '' || v === 'auto') ? 'auto' : String(v);
    try {
      if (typeof SandpieConfig !== 'undefined' && SandpieConfig.set) SandpieConfig.set(CONFIG_NS, val);
      localStorage.setItem(LS_KEY, val);
    } catch (_) {}
  }

  function browserTags() {
    try { if (navigator.languages && navigator.languages.length) return navigator.languages; } catch (_) {}
    try { if (navigator.language) return [navigator.language]; } catch (_) {}
    return [];
  }

  // Map a BCP-47 tag (e.g. 'es-ES', 'zh-CN', 'pt') to a code in our list:
  // script/region variant first, then the ISO 639-1 base code. '' = unmappable.
  function mapTag(tag) {
    const t = String(tag || '').trim().toLowerCase();
    if (!t) return '';
    const parts = t.split(/[-_]/);
    const base = parts[0];
    const region = (parts.slice(1).find(p => p.length === 2) || '').toUpperCase();
    for (const v of VARIANTS) {
      const regions = (v.match || {})[base];
      if (regions && regions.includes(region)) return v.code;
    }
    if (base === 'pt') return 'pt-PT';     // unqualified pt → Portugal (the ISO default)
    if (base === 'zh') return 'zh-Hans';   // unqualified zh → Simplified (most common)
    return LANGUAGES.some(l => l.code === base) ? base : '';
  }

  function detect() {
    for (const tag of browserTags()) {
      const m = mapTag(tag);
      if (m) return m;
    }
    return 'en';   // universal fallback
  }

  // The language actually in force: explicit pick, or the detected one under 'auto'.
  function effective() {
    const s = stored();
    if (s && s !== 'auto' && (LANGUAGES.some(l => l.code === s) || VARIANTS.some(v => v.code === s))) return s;
    return detect();
  }
  function isAuto() { const s = stored(); return !s || s === 'auto'; }

  function entry(code) {
    return VARIANTS.find(v => v.code === code) || LANGUAGES.find(l => l.code === code) || null;
  }
  function name(code) { const e = entry(code); return e ? e.name : String(code || ''); }
  function nativeName(code) { const e = entry(code); return e ? (e.native || e.name) : String(code || ''); }

  // The sentence injected into the system message (and subagent prompts):
  // MUST reply in X unless the user explicitly asks otherwise, regardless of
  // the language of tool results / materials read.
  function directive() {
    const nm = name(effective()) || 'English';
    return 'IMPORTANT LANGUAGE RULE: You MUST write all of your replies in ' + nm +
      '. This overrides the language of any tool results, files, or reference material you read, and any other language cues in the conversation. ' +
      'The only exception is when the user explicitly asks you to write in a different language (for example, a translation task).';
  }

  // Picker data: the 'auto' entry (label shows the detected language) + all
  // languages, interleaved, sorted by native name.
  function options() {
    const det = detect();
    const all = [...VARIANTS, ...LANGUAGES].sort((a, b) =>
      String(a.native || a.name).localeCompare(String(b.native || b.name), undefined, { sensitivity: 'base' }));
    return { auto: { value: 'auto', label: 'System default — ' + nativeName(det) }, items: all, detected: det };
  }

  return { detect, effective, isAuto, stored, set, name, nativeName, directive, options, LANGUAGES, VARIANTS };
})();
window.SandpieLanguage = SandpieLanguage;
