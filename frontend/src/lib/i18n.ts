import { usePrefs, type Lang } from "@/store/prefs";

/** UI strings. Keys are English; Urdu falls back to English when missing. */
const UR: Record<string, string> = {
  Home: "ہوم",
  Properties: "جائیدادیں",
  Schemes: "ہاؤسنگ اسکیمیں",
  Map: "نقشہ",
  Insights: "مارکیٹ بصیرت",
  News: "خبریں",
  Tools: "ٹولز",
  "AI Hub": "اے آئی مرکز",
  Projects: "منصوبے",
  Dashboard: "ڈیش بورڈ",
  "Sign in": "سائن ان",
  "Sign out": "سائن آؤٹ",
  "List Property": "جائیداد درج کریں",
  Buy: "خریدیں",
  Rent: "کرایہ",
  Plot: "پلاٹ",
  Commercial: "کمرشل",
  "Search Properties": "جائیداد تلاش کریں",
  "Find the Perfect": "بہترین",
  "Property with AI": "جائیداد اے آئی کے ساتھ",
  "Featured Properties": "نمایاں جائیدادیں",
  "View all": "سب دیکھیں",
  "Ask AI": "اے آئی سے پوچھیں",
  "AI Property Assistant": "اے آئی پراپرٹی اسسٹنٹ",
  "Your Land": "آپ کی زمین",
  "Our Intelligence": "ہماری ذہانت",
  "A Brighter Pakistan": "روشن پاکستان",
  "Live Market": "لائیو مارکیٹ",
  Compare: "موازنہ",
  Favorites: "پسندیدہ",
  About: "ہمارے بارے میں",
};

export function translate(lang: Lang, key: string): string {
  return lang === "ur" ? UR[key] ?? key : key;
}

export function useT() {
  const lang = usePrefs((s) => s.lang);
  return (key: string) => translate(lang, key);
}
