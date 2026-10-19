/**
 * Lightweight, on-device understanding of what the person asked the assistant —
 * English, Roman Urdu and a few Urdu keywords. It turns
 *   "3 bed 10 marla house in Lahore under 5 crore"
 * into structured /search filters, and
 *   "I want to sell my 1 kanal plot in DHA Islamabad for 3.5 crore"
 * into a pre-filled listing draft — so the assistant can act, not only chat.
 */

export type Action = "search" | "sell" | "my_listings" | "signin" | "chat";

export interface Intent {
  action: Action;
  city?: string;
  category?: string;
  use_type?: "residential" | "commercial";
  bedrooms?: number;
  marla?: number;
  min_price?: number;
  max_price?: number;
  price?: number;
  purpose?: "buy" | "rent" | "invest";
  /** Words that look like a society name, e.g. "DHA", "Bahria Town". */
  area_hint?: string;
}

export interface ListingDraft {
  title?: string;
  description?: string;
  category?: string;
  use_type?: string;
  city?: string;
  marla?: number;
  bedrooms?: number;
  bathrooms?: number;
  price?: number;
}

const CRORE = 10_000_000;
const LAKH = 100_000;

const CITY_ALIASES: Record<string, string> = {
  lahore: "Lahore", "لاہور": "Lahore",
  karachi: "Karachi", "کراچی": "Karachi",
  islamabad: "Islamabad", isb: "Islamabad", "اسلام آباد": "Islamabad",
  rawalpindi: "Rawalpindi", pindi: "Rawalpindi", "راولپنڈی": "Rawalpindi",
  faisalabad: "Faisalabad", multan: "Multan", peshawar: "Peshawar", quetta: "Quetta",
};

const CATEGORY_WORDS: [RegExp, string, ("residential" | "commercial")?][] = [
  [/\b(apartments?|flats?)\b|فلیٹ/, "apartment"],
  [/\b(plots?|land|zameen)\b|پلاٹ|زمین/, "plot"],
  [/\b(shops?|dukaan|dukan|store)\b|دکان/, "shop", "commercial"],
  [/\b(offices?)\b|دفتر/, "office", "commercial"],
  [/\b(buildings?|plaza)\b/, "building"],
  [/\b(portion|floor)\b/, "floor"],
  [/\b(houses?|homes?|villas?|bungalows?|ghar|makaan|makan)\b|گھر|مکان/, "house"],
];

const SCHEME_HINTS = /\b(dha|bahria(?: town)?|gulberg|johar town|model town|smart city|blue world|park view|e-?\d{1,2}|f-?\d{1,2}|g-?\d{1,2}|clifton|defence)\b/i;

function amount(numStr: string, unit?: string): number {
  const n = parseFloat(numStr.replace(/,/g, ""));
  const u = (unit ?? "").toLowerCase();
  if (/^(crore|cr|کروڑ)/.test(u)) return n * CRORE;
  if (/^(lakh|lac|lacs|lakhs|l|لاکھ)$/.test(u)) return n * LAKH;
  if (/^(million|m|mn)$/.test(u)) return n * 1_000_000;
  if (/^(k|thousand|ہزار)$/.test(u)) return n * 1000;
  return n;
}

// `(?![a-z])` instead of `\b`: JavaScript's \b doesn't see Urdu letters as word characters.
const MONEY = String.raw`(\d+(?:[.,]\d+)?)\s*(crore|cr|lakh|lakhs|lac|lacs|million|mn|m|k|thousand|کروڑ|لاکھ|ہزار)(?![a-z])`;

/** Eastern Arabic / Urdu digits (۰-۹, ٠-٩) → ASCII so numbers parse the same way. */
function asciiDigits(s: string): string {
  return s.replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06f0)).replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660));
}

export function parseIntent(raw: string, knownCities: string[] = []): Intent {
  const text = asciiDigits(raw).toLowerCase().replace(/\s+/g, " ").trim();
  const intent: Intent = { action: "chat" };

  // ---- action
  if (/\b(my (listings?|properties|ads?)|meri (listings?|propert(y|ies)|ads?))\b|میری (لسٹنگ|پراپرٹ|اشتہار)|میرے (اشتہار|پلاٹ)/.test(text)) intent.action = "my_listings";
  else if (/\b(sell|selling|list my|post (an? )?(ad|listing)|add (a |my )?(listing|property)|bechna|baichna|farokht)\b|بیچ|فروخت/.test(text)) intent.action = "sell";
  else if (/\b(sign ?in|log ?in|sign ?up|register|create (an )?account)\b/.test(text)) intent.action = "signin";

  if (/\b(rent|rental|kiraye|kiraya|lease)\b|کرای/.test(text)) intent.purpose = "rent";
  else if (/\b(invest|investment|roi|return)\b|سرمایہ/.test(text)) intent.purpose = "invest";
  else if (/\b(buy|purchase|khareed|kharid)\b|خرید/.test(text)) intent.purpose = "buy";

  // ---- city
  for (const c of knownCities) if (text.includes(c.toLowerCase())) intent.city = c;
  if (!intent.city) for (const [alias, name] of Object.entries(CITY_ALIASES)) if (text.includes(alias)) intent.city = name;

  // ---- category
  for (const [re, cat, use] of CATEGORY_WORDS)
    if (re.test(text)) {
      intent.category = cat;
      if (use) intent.use_type = use;
      break;
    }
  if (/\bcommercial\b|کمرشل/.test(text)) intent.use_type = "commercial";

  // ---- size
  const kanal = text.match(/(\d+(?:\.\d+)?)\s*(kanal|کنال)/);
  const marla = text.match(/(\d+(?:\.\d+)?)\s*(marla|مرلہ|مرلے)/);
  if (kanal) intent.marla = parseFloat(kanal[1]!) * 20;
  else if (marla) intent.marla = parseFloat(marla[1]!);

  const beds = text.match(/(\d+)\s*(?:-|\s)?(bed(room)?s?|bhk|br|kamr[ae]y?)\b/) ?? text.match(/(\d+)\s*(کمرے|کمروں|کمرہ|بیڈ)/);
  if (beds) intent.bedrooms = parseInt(beds[1]!, 10);

  // ---- price
  const between = text.match(new RegExp(String.raw`between\s+(\d+(?:\.\d+)?)\s*(?:(crore|cr|lakh|lac|million|m)\s*)?(?:and|to|-)\s*` + MONEY));
  if (between) {
    intent.min_price = amount(between[1]!, between[2] ?? between[4]);
    intent.max_price = amount(between[3]!, between[4]);
  } else {
    const under = text.match(new RegExp(String.raw`(?:under|below|less than|upto|up to|within|max(?:imum)?|budget(?: of| is)?|تک)\s*(?:pkr|rs\.?)?\s*` + MONEY));
    const over = text.match(new RegExp(String.raw`(?:over|above|more than|min(?:imum)?|starting)\s*(?:pkr|rs\.?)?\s*` + MONEY));
    // Urdu puts the limit after the amount: "5 کروڑ تک", "2 کروڑ سے زیادہ".
    const underUr = text.match(new RegExp(MONEY + String.raw`\s*(?:تک|سے کم|کے اندر|tak|se kam)`));
    const overUr = text.match(new RegExp(MONEY + String.raw`\s*(?:سے زیادہ|سے اوپر|se zyada|se upar)`));
    if (under ?? underUr) intent.max_price = amount((under ?? underUr)![1]!, (under ?? underUr)![2]);
    if (over ?? overUr) intent.min_price = amount((over ?? overUr)![1]!, (over ?? overUr)![2]);
    const any = text.match(new RegExp(MONEY));
    if (!under && !over && !underUr && !overUr && any) {
      const v = amount(any[1]!, any[2]);
      if (intent.action === "sell") intent.price = v;
      else intent.max_price = v;
    }
  }

  const scheme = raw.match(SCHEME_HINTS);
  if (scheme) intent.area_hint = scheme[0].toUpperCase() === "DHA" ? "DHA" : scheme[0].replace(/\b\w/g, (c) => c.toUpperCase());

  const hasFilters = !!(intent.city || intent.category || intent.marla || intent.bedrooms || intent.max_price || intent.min_price);
  if (intent.action === "chat" && hasFilters) intent.action = "search";
  return intent;
}

/** /search query parameters for a search intent (size gets a ±15% window). */
export function searchQuery(i: Intent): Record<string, string | number | undefined> {
  return {
    city: i.city,
    category: i.category,
    use_type: i.use_type,
    bedrooms: i.bedrooms,
    min_marla: i.marla ? Math.floor(i.marla * 0.85) : undefined,
    max_marla: i.marla ? Math.ceil(i.marla * 1.15) : undefined,
    min_price: i.min_price,
    max_price: i.max_price,
  };
}

/** A human summary of the filters, e.g. "3+ bed · 10 Marla · house · Lahore · under 5 Crore". */
export function describeIntent(i: Intent, fmt: (n: number) => string): string {
  const bits: string[] = [];
  if (i.bedrooms) bits.push(`${i.bedrooms}+ bed`);
  if (i.marla) bits.push(i.marla >= 20 && i.marla % 20 === 0 ? `${i.marla / 20} Kanal` : `${i.marla} Marla`);
  if (i.category) bits.push(i.category);
  if (i.area_hint) bits.push(i.area_hint);
  if (i.city) bits.push(i.city);
  if (i.min_price && i.max_price) bits.push(`${fmt(i.min_price)} – ${fmt(i.max_price)}`);
  else if (i.max_price) bits.push(`under ${fmt(i.max_price)}`);
  else if (i.min_price) bits.push(`over ${fmt(i.min_price)}`);
  return bits.join(" · ");
}

/** Turn a sell intent into a listing draft the create-listing form can open with. */
export function draftFromIntent(i: Intent, said: string): ListingDraft {
  const cat = i.category ?? "house";
  const size = i.marla ? (i.marla >= 20 && i.marla % 20 === 0 ? `${i.marla / 20} Kanal` : `${i.marla} Marla`) : "";
  const label = cat.charAt(0).toUpperCase() + cat.slice(1);
  const where = [i.area_hint, i.city].filter(Boolean).join(", ");
  return {
    title: [size, label, where && `in ${where}`].filter(Boolean).join(" ") || undefined,
    description: said.trim(),
    category: cat,
    use_type: i.use_type ?? (["shop", "office"].includes(cat) ? "commercial" : "residential"),
    city: i.city,
    marla: i.marla,
    bedrooms: i.bedrooms,
    price: i.price ?? i.max_price,
  };
}
