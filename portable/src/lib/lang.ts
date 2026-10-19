/**
 * The assistant answers in the language the person uses — detected per message:
 *   "ur"    Urdu in Urdu script        (مجھے لاہور میں گھر چاہیے)
 *   "roman" Urdu in English letters    (mujhe lahore mein ghar chahiye)
 *   "en"    English
 * plus every built-in reply in those three languages.
 */
import type { Intent } from "./intent";

export type Lang = "en" | "ur" | "roman";

const URDU_SCRIPT = /[؀-ۿ]/g;
const LATIN = /[a-z]/gi;
// Words (and common spellings) that are not English, so they mark Roman Urdu.
const ROMAN_STRONG = new Set(
  (
    // pronouns & people
    "mujhe mujhay mujhy mujy muje mjhe mjy mjhy hamein humein hame aap aapko apko apka apki apke apna apni apne mera meri mere " +
    "hamara hamari hamare tum tumhe tumhara bhai bhaijan sahab sahib janab baji yaar yar " +
    // verbs & auxiliaries
    "chahiye chahye chahie chaiye chaye chahiay chahiae chahta chahti chahte chahiyay batao btao bataen batayen btayen bataiye btaen " +
    "dikhao dikhaen dikhayen dikhaye dikhain dikhaiye dekhao dekhna dekhein dekhen dekhain bechna bechni baichna bechna bechne bikna " +
    "khareedna kharidna khareedni kharidni khareedna lena leni lene dena deni dene karein karen krna karna karo krdo kardo kijiye " +
    "kariye hain hai hy hay hn hen tha thi thay hoga hogi honge raha rahi rahe sakta sakti sakte milega milegi mil " +
    // question words & particles
    "kya kia kiya kitne kitna kitni kitny kitnay kahan kahaan kidhar kaise kaisa kaisi kese kesa kon kaun konsa kaunsa kab kyun kyon " +
    "nahi nahin nai nhi haan han jee ji acha achha accha achi theek thik bilkul zaroor shukriya shukria meharbani salam assalam " +
    "alaikum walaikum aoa abhi phir sirf bhi wala wali wale walay sab sabse zyada ziada thora thoda bohat bahut buhat bht " +
    // real-estate words
    "ghar ghr makan makaan mkan dukaan dukan zameen zamin kiraye kiraya kiray qeemat keemat kimat sasta sasti mehnga mehenga " +
    "kamre kamray kamra qareeb nazdeek ilaqa ilaqay sheher shehar"
  ).split(/\s+/),
);
// Short Roman Urdu words that also look like English or names; they only count next to a strong one.
const ROMAN_WEAK = new Set(["se", "ka", "ki", "ke", "ko", "mai", "mein", "me", "main", "mn", "ho", "na", "to", "ya", "aur", "tak", "kam", "par", "pe"]);
// Words that show the message is English.
const ENGLISH = new Set(
  (
    "the is are am was were i you we they it this that these those want need looking show find search give tell list sell selling " +
    "buy buying rent renting for with in under over near between my me our your please what which where when how why can could " +
    "would should do does have has hello hi hey thanks thank yes house houses home apartment apartments flat flats plot plots shop " +
    "office price budget best cheap and or of a an to from listing listings property properties invest investment about any some"
  ).split(/\s+/),
);

/**
 * Which language a message is written in, or null when it gives no clue (e.g. "ok",
 * "5 crore", a place name). Mixed Urdu-script / English text follows the dominant script.
 */
export function detectLangOrNull(text: string): Lang | null {
  const urdu = (text.match(URDU_SCRIPT) ?? []).length;
  const latin = (text.match(LATIN) ?? []).length;
  if (urdu > 0 && urdu >= latin * 0.5) return "ur";
  const words = text.toLowerCase().match(/[a-z]+/g) ?? [];
  let strong = 0;
  let weak = 0;
  let english = 0;
  for (const w of words) {
    if (ROMAN_STRONG.has(w)) strong += 1;
    else if (ROMAN_WEAK.has(w)) weak += 1;
    if (ENGLISH.has(w)) english += 1;
  }
  if (strong >= 2 || (strong >= 1 && (weak >= 1 || english <= strong))) return "roman";
  if (english >= 1) return "en";
  return null;
}

/** Language of a message; ambiguous messages keep `fallback` (the conversation's language). */
export function detectLang(text: string, fallback: Lang = "en"): Lang {
  return detectLangOrNull(text) ?? fallback;
}

/** BCP-47 tag to speak a reply in. */
export function speechTag(lang: Lang): string {
  return lang === "en" ? "en-US" : "ur-PK";
}

// ------------------------------------------------------------------ formatting

const CRORE = 10_000_000;
const LAKH = 100_000;
const trim = (n: number) => (n >= 100 ? Math.round(n).toString() : n.toFixed(2).replace(/\.?0+$/, ""));

/** "PKR 4.5 Crore" / "4.5 کروڑ روپے" / "4.5 crore rupay". */
export function money(v: number | undefined | null, lang: Lang): string {
  if (!v) return "—";
  const [n, unit] = v >= CRORE ? [v / CRORE, "crore"] : v >= LAKH ? [v / LAKH, "lakh"] : [v, ""];
  if (lang === "ur") return `${trim(n)}${unit ? ` ${unit === "crore" ? "کروڑ" : "لاکھ"}` : ""} روپے`;
  if (lang === "roman") return `${trim(n)}${unit ? ` ${unit}` : ""} rupay`;
  return `PKR ${unit ? `${trim(n)} ${unit === "crore" ? "Crore" : "Lakh"}` : Math.round(v).toLocaleString("en-PK")}`;
}

const CATEGORY: Record<string, [string, string]> = {
  house: ["گھر", "ghar"],
  apartment: ["فلیٹ", "flat"],
  plot: ["پلاٹ", "plot"],
  shop: ["دکان", "dukaan"],
  office: ["دفتر", "office"],
  building: ["عمارت", "building"],
  floor: ["پورشن", "portion"],
};
const CITY_UR: Record<string, string> = { Lahore: "لاہور", Karachi: "کراچی", Islamabad: "اسلام آباد", Rawalpindi: "راولپنڈی", Faisalabad: "فیصل آباد", Multan: "ملتان", Peshawar: "پشاور", Quetta: "کوئٹہ" };

function category(cat: string, lang: Lang): string {
  if (lang === "en") return cat;
  return CATEGORY[cat]?.[lang === "ur" ? 0 : 1] ?? cat;
}
export function city(name: string | undefined, lang: Lang): string {
  if (!name) return "";
  return lang === "ur" ? (CITY_UR[name] ?? name) : name;
}
function size(marla: number, lang: Lang): string {
  const kanal = marla >= 20 && marla % 20 === 0;
  const n = kanal ? marla / 20 : marla;
  if (lang === "ur") return `${n} ${kanal ? "کنال" : "مرلہ"}`;
  if (lang === "roman") return `${n} ${kanal ? "kanal" : "marla"}`;
  return `${n} ${kanal ? "Kanal" : "Marla"}`;
}

/** "3+ bed · 10 Marla · house · Lahore · under PKR 5 Crore", in the person's language. */
export function describe(i: Intent, lang: Lang): string {
  const bits: string[] = [];
  if (i.bedrooms) bits.push(lang === "ur" ? `${i.bedrooms}+ کمرے` : lang === "roman" ? `${i.bedrooms}+ kamre` : `${i.bedrooms}+ bed`);
  if (i.marla) bits.push(size(i.marla, lang));
  if (i.category) bits.push(category(i.category, lang));
  if (i.area_hint) bits.push(i.area_hint);
  if (i.city) bits.push(city(i.city, lang));
  const lo = i.min_price ? money(i.min_price, lang) : "";
  const hi = i.max_price ? money(i.max_price, lang) : "";
  if (lo && hi) bits.push(`${lo} – ${hi}`);
  else if (hi) bits.push(lang === "ur" ? `${hi} تک` : lang === "roman" ? `${hi} tak` : `under ${hi}`);
  else if (lo) bits.push(lang === "ur" ? `${lo} سے زیادہ` : lang === "roman" ? `${lo} se zyada` : `over ${lo}`);
  return bits.join(" · ");
}

// ------------------------------------------------------------------ phrases

type Phrasebook = {
  found: (n: number, label: string) => string;
  relaxed: (label: string, cityName: string) => string;
  none: (label: string) => string;
  investHint: string;
  bestMatch: (title: string, price: string) => string;
  seeAll: (n: number) => string;
  browseAll: string;
  drafted: (summary: string, missing: string[], signedIn: boolean) => string;
  missingCity: string;
  missingSize: string;
  missingPrice: string;
  createListing: string;
  myListings: string;
  signIn: string;
  createAccount: string;
  profile: string;
  manageListings: string;
  openListing: string;
  requestCall: string;
  addListing: string;
  openExplore: string;
  listingsNeedSignIn: string;
  listingsCount: (count: number, active: number, worth: string) => string;
  listingsNone: string;
  signedInAs: (name: string) => string;
  signInHelp: string;
  ragMatches: (places: string[]) => string;
  ragPlaces: (places: string[]) => string;
  ragNone: string;
  help: (name?: string) => string;
  welcome: (name: string | undefined, role: string | undefined) => string;
  suggestions: (role?: string) => string[];
  replyInstruction: string;
};

const roleLine = {
  en: (role?: string) =>
    role === "seller" || role === "landlord"
      ? "Tell me about the property you want to sell or rent out and I’ll draft the listing for you."
      : role === "agent"
        ? "I can draft listings for your clients, find matching properties and price-check deals."
        : role === "investor"
          ? "Ask me for investment picks, price trends or yields in any city."
          : "Tell me what you’re looking for — city, budget, size or purpose — and I’ll search live listings for you.",
  ur: (role?: string) =>
    role === "seller" || role === "landlord"
      ? "جو پراپرٹی آپ بیچنا یا کرائے پر دینا چاہتے ہیں، اس کے بارے میں بتائیں — میں اس کی لسٹنگ تیار کر دوں گا۔"
      : role === "agent"
        ? "میں آپ کے کلائنٹس کے لیے لسٹنگ تیار کر سکتا ہوں، مناسب پراپرٹیز ڈھونڈ سکتا ہوں اور قیمت جانچ سکتا ہوں۔"
        : role === "investor"
          ? "کسی بھی شہر میں سرمایہ کاری کے بہترین مواقع، قیمتوں کے رجحان یا منافع کے بارے میں پوچھیں۔"
          : "بتائیں آپ کیا ڈھونڈ رہے ہیں — شہر، بجٹ، سائز یا مقصد — میں آپ کے لیے لسٹنگز تلاش کروں گا۔",
};

const BOOKS: Record<Lang, Phrasebook> = {
  en: {
    found: (n, label) => `I found **${n}** ${n === 1 ? "listing" : "listings"} for **${label}**.`,
    relaxed: (label, c) => `Nothing matched **${label}** exactly, so here are the closest options${c ? ` in ${c}` : ""}:`,
    none: (label) => `I couldn’t find any listings for **${label || "that"}** yet. Try another city, type or budget.`,
    investHint: " For investment, look at featured and newly launched societies — ask me about returns in any city.",
    bestMatch: (title, price) => ` The best match is ${title}, for ${price}.`,
    seeAll: (n) => `See all ${n}`,
    browseAll: "Browse all listings",
    drafted: (summary, missing, signedIn) =>
      `Great — I’ve drafted a listing${summary ? ` for **${summary}**` : ""}. ${missing.length ? `I still need the ${missing.join(", ")} — you can add ${missing.length > 1 ? "them" : "it"} on the form. ` : ""}Tap **Create listing** to add photos and publish.${signedIn ? "" : " You’ll need to sign in first — it only takes a one-time code."}`,
    missingCity: "city",
    missingSize: "size",
    missingPrice: "asking price",
    createListing: "Create listing",
    myListings: "My listings",
    signIn: "Sign in",
    createAccount: "Create account",
    profile: "Profile",
    manageListings: "Manage listings",
    openListing: "Open listing",
    requestCall: "Request a call",
    addListing: "Add a listing",
    openExplore: "Open Explore",
    listingsNeedSignIn: "Sign in to see and manage your listings — I’ll send you a one-time code, no password needed.",
    listingsCount: (count, active, worth) => `You have **${count}** ${count === 1 ? "listing" : "listings"} (${active} active, worth ${worth}).`,
    listingsNone: "You haven’t listed anything yet. Tell me about your property — e.g. “10 marla house in Lahore for 4 crore” — and I’ll draft it.",
    signedInAs: (name) => `You’re signed in as **${name}**.`,
    signInHelp: "You can sign up or sign in with just your mobile number or e-mail — I’ll send a 6-digit code.",
    ragMatches: (places) => `Here are the closest matches I found${places.length ? ` (related: ${places.slice(0, 3).join(", ")})` : ""}:`,
    ragPlaces: (places) => `I found these related places: **${places.slice(0, 4).join(", ")}**. Tell me a budget or property type and I’ll find listings there.`,
    ragNone: "I couldn’t find a match for that. Try a city (Lahore, Karachi, Islamabad), a type (house, plot, apartment, shop) and a budget.",
    help: (name) =>
      [
        `Here’s what I can do${name ? `, ${name}` : ""}:`,
        "- **Find property** — “3 bed house in Lahore under 5 crore”",
        "- **List your property** — “I want to sell my 1 kanal plot in DHA Islamabad for 3.5 crore”",
        "- **Your listings** — “Show my listings”",
        "- **Ask anything** — areas, societies, prices and buying tips",
        "",
        "Type, send a voice note, or start a voice conversation — in English or Urdu.",
      ].join("\n"),
    welcome: (name, role) =>
      `Assalam-o-Alaikum${name ? ` ${name}` : ""}! I’m **Arz-e-Pak AI**. ${roleLine.en(role)}\n\nType a message, send a voice note, or start a voice conversation — English, اردو or Roman Urdu.`,
    suggestions: (role) =>
      role === "seller" || role === "landlord"
        ? ["I want to sell my 10 marla house in Lahore for 4.5 crore", "میری لسٹنگز دکھائیں", "How do I sell faster?"]
        : role === "agent"
          ? ["List a 1 kanal house in DHA Lahore for 9.5 crore", "3 bed apartments in Karachi under 2 crore", "Show my listings"]
          : role === "investor"
            ? ["Best investment plots in Islamabad", "لاہور میں کمرشل پراپرٹی 10 کروڑ تک", "Featured listings"]
            : ["10 marla house in Lahore under 5 crore", "کراچی میں فلیٹ دکھائیں", "islamabad mein plot chahiye", "I want to sell my house"],
    replyInstruction: "Reply in English.",
  },
  ur: {
    found: (n, label) => `**${label}** کے لیے مجھے **${n}** ${n === 1 ? "پراپرٹی ملی ہے" : "پراپرٹیز ملی ہیں"}۔`,
    relaxed: (label, c) => `**${label}** سے بالکل ملتی پراپرٹی نہیں ملی، اس لیے${c ? ` ${c} میں` : ""} قریب ترین آپشنز یہ ہیں:`,
    none: (label) => `**${label || "اس"}** کے لیے ابھی کوئی لسٹنگ نہیں ملی۔ کوئی اور شہر، قسم یا بجٹ آزما کر دیکھیں۔`,
    investHint: " سرمایہ کاری کے لیے نمایاں اور نئی سکیموں پر نظر رکھیں — کسی بھی شہر میں منافع کے بارے میں پوچھیں۔",
    bestMatch: (title, price) => ` سب سے بہتر آپشن ${title} ہے، قیمت ${price}۔`,
    seeAll: (n) => `تمام ${n} دیکھیں`,
    browseAll: "تمام لسٹنگز دیکھیں",
    drafted: (summary, missing, signedIn) =>
      `بہت خوب — میں نے${summary ? ` **${summary}**` : ""} کی لسٹنگ تیار کر دی ہے۔ ${missing.length ? `ابھی ${missing.join("، ")} درکار ہے — آپ فارم میں شامل کر سکتے ہیں۔ ` : ""}تصاویر شامل کرنے اور شائع کرنے کے لیے **لسٹنگ بنائیں** پر ٹیپ کریں۔${signedIn ? "" : " پہلے سائن اِن کرنا ہوگا — صرف ایک کوڈ درکار ہے۔"}`,
    missingCity: "شہر",
    missingSize: "رقبہ",
    missingPrice: "قیمت",
    createListing: "لسٹنگ بنائیں",
    myListings: "میری لسٹنگز",
    signIn: "سائن اِن",
    createAccount: "اکاؤنٹ بنائیں",
    profile: "پروفائل",
    manageListings: "لسٹنگز سنبھالیں",
    openListing: "لسٹنگ کھولیں",
    requestCall: "کال کی درخواست",
    addListing: "نئی لسٹنگ",
    openExplore: "تلاش کھولیں",
    listingsNeedSignIn: "اپنی لسٹنگز دیکھنے کے لیے سائن اِن کریں — میں آپ کو ایک کوڈ بھیجوں گا، پاس ورڈ کی ضرورت نہیں۔",
    listingsCount: (count, active, worth) => `آپ کی **${count}** ${count === 1 ? "لسٹنگ ہے" : "لسٹنگز ہیں"} (${active} فعال، کل مالیت ${worth})۔`,
    listingsNone: "آپ نے ابھی کوئی پراپرٹی لسٹ نہیں کی۔ اپنی پراپرٹی کے بارے میں بتائیں — مثلاً “لاہور میں 10 مرلہ گھر 4 کروڑ میں” — میں لسٹنگ تیار کر دوں گا۔",
    signedInAs: (name) => `آپ **${name}** کے طور پر سائن اِن ہیں۔`,
    signInHelp: "آپ صرف اپنے موبائل نمبر یا ای میل سے سائن اَپ یا سائن اِن کر سکتے ہیں — میں 6 ہندسوں کا کوڈ بھیجوں گا۔",
    ragMatches: (places) => `مجھے یہ قریب ترین نتائج ملے ہیں${places.length ? ` (متعلقہ: ${places.slice(0, 3).join("، ")})` : ""}:`,
    ragPlaces: (places) => `مجھے یہ متعلقہ جگہیں ملیں: **${places.slice(0, 4).join("، ")}**۔ بجٹ یا پراپرٹی کی قسم بتائیں تو میں وہاں لسٹنگز ڈھونڈ دوں۔`,
    ragNone: "اس سے ملتی کوئی چیز نہیں ملی۔ شہر (لاہور، کراچی، اسلام آباد)، قسم (گھر، پلاٹ، فلیٹ، دکان) اور بجٹ بتا کر دیکھیں۔",
    help: (name) =>
      [
        `${name ? `${name}، ` : ""}میں یہ سب کر سکتا ہوں:`,
        "- **پراپرٹی تلاش** — “لاہور میں 3 کمروں کا گھر 5 کروڑ تک”",
        "- **اپنی پراپرٹی لسٹ کریں** — “میں اسلام آباد میں اپنا 1 کنال پلاٹ 3.5 کروڑ میں بیچنا چاہتا ہوں”",
        "- **آپ کی لسٹنگز** — “میری لسٹنگز دکھائیں”",
        "- **کچھ بھی پوچھیں** — علاقے، سکیمیں، قیمتیں اور خریداری کے مشورے",
        "",
        "لکھیں، وائس نوٹ بھیجیں یا آواز میں بات شروع کریں — اردو یا انگریزی میں۔",
      ].join("\n"),
    welcome: (name, role) =>
      `السلام علیکم${name ? ` ${name}` : ""}! میں **ارضِ پاک اے آئی** ہوں۔ ${roleLine.ur(role)}\n\nپیغام لکھیں، وائس نوٹ بھیجیں یا آواز میں بات شروع کریں — اردو، رومن اردو یا انگریزی میں۔`,
    suggestions: (role) =>
      role === "seller" || role === "landlord"
        ? ["میں لاہور میں اپنا 10 مرلہ گھر 4.5 کروڑ میں بیچنا چاہتا ہوں", "میری لسٹنگز دکھائیں", "پراپرٹی جلدی کیسے بکے؟"]
        : role === "investor"
          ? ["اسلام آباد میں سرمایہ کاری کے لیے پلاٹ", "لاہور میں کمرشل پراپرٹی 10 کروڑ تک", "نمایاں لسٹنگز"]
          : ["لاہور میں 10 مرلہ گھر 5 کروڑ تک", "کراچی میں فلیٹ دکھائیں", "اسلام آباد میں پلاٹ", "میں اپنا گھر بیچنا چاہتا ہوں"],
    replyInstruction: "Reply in Urdu, written in Urdu script, because the user wrote or spoke in Urdu.",
  },
  roman: {
    found: (n, label) => `**${label}** ke liye mujhe **${n}** ${n === 1 ? "listing mili hai" : "listings mili hain"}.`,
    relaxed: (label, c) => `**${label}** se bilkul milti listing nahi mili, is liye${c ? ` ${c} mein` : ""} qareeb tareen options ye hain:`,
    none: (label) => `**${label || "is"}** ke liye abhi koi listing nahi mili. Koi aur shehar, type ya budget try karein.`,
    investHint: " Investment ke liye featured aur nayi societies dekhein — kisi bhi shehar mein return ke baare mein poochein.",
    bestMatch: (title, price) => ` Sab se behtar option ${title} hai, qeemat ${price}.`,
    seeAll: (n) => `Sab ${n} dekhein`,
    browseAll: "Sari listings dekhein",
    drafted: (summary, missing, signedIn) =>
      `Zabardast — maine${summary ? ` **${summary}**` : ""} ki listing tayyar kar di hai. ${missing.length ? `Abhi ${missing.join(", ")} chahiye — aap form mein add kar sakte hain. ` : ""}Photos lagane aur publish karne ke liye **Create listing** par tap karein.${signedIn ? "" : " Pehle sign in karna hoga — sirf ek code chahiye."}`,
    missingCity: "shehar",
    missingSize: "size",
    missingPrice: "qeemat",
    createListing: "Create listing",
    myListings: "Meri listings",
    signIn: "Sign in",
    createAccount: "Account banayein",
    profile: "Profile",
    manageListings: "Listings manage karein",
    openListing: "Listing kholein",
    requestCall: "Call ki darkhwast",
    addListing: "Nayi listing",
    openExplore: "Explore kholein",
    listingsNeedSignIn: "Apni listings dekhne ke liye sign in karein — main aap ko ek code bhejunga, password ki zaroorat nahi.",
    listingsCount: (count, active, worth) => `Aap ki **${count}** listings hain (${active} active, kul value ${worth}).`,
    listingsNone: "Aap ne abhi koi property list nahi ki. Apni property ke baare mein batayein — jaise “Lahore mein 10 marla ghar 4 crore mein” — main listing bana dunga.",
    signedInAs: (name) => `Aap **${name}** ke taur par sign in hain.`,
    signInHelp: "Aap sirf apne mobile number ya email se sign up ya sign in kar sakte hain — main 6 digit ka code bhejunga.",
    ragMatches: (places) => `Mujhe ye qareeb tareen results mile hain${places.length ? ` (related: ${places.slice(0, 3).join(", ")})` : ""}:`,
    ragPlaces: (places) => `Mujhe ye related jagahen mili: **${places.slice(0, 4).join(", ")}**. Budget ya property type batayein to main wahan listings dhoond dun.`,
    ragNone: "Is se milti koi cheez nahi mili. Shehar (Lahore, Karachi, Islamabad), type (ghar, plot, flat, dukaan) aur budget bata kar dekhein.",
    help: (name) =>
      [
        `${name ? `${name}, ` : ""}main ye sab kar sakta hun:`,
        "- **Property dhoondna** — “Lahore mein 3 bed ghar 5 crore tak”",
        "- **Apni property list karna** — “Main Islamabad mein apna 1 kanal plot 3.5 crore mein bechna chahta hun”",
        "- **Aap ki listings** — “Meri listings dikhao”",
        "- **Kuch bhi poochein** — ilaqay, societies, qeematein aur khareedne ke mashwaray",
        "",
        "Likhein, voice note bhejein ya awaaz mein baat shuru karein — Urdu ya English mein.",
      ].join("\n"),
    welcome: (name, role) => `Assalam-o-Alaikum${name ? ` ${name}` : ""}! Main **Arz-e-Pak AI** hun. ${roleLine.en(role)}`,
    suggestions: () => ["Lahore mein 10 marla ghar 5 crore tak", "Karachi mein flat dikhao", "Meri listings dikhao"],
    replyInstruction: "Reply in Roman Urdu (Urdu written in English letters), the way the user writes.",
  },
};

export function t(lang: Lang): Phrasebook {
  return BOOKS[lang];
}
