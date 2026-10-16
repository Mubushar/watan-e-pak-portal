import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Bot, Building2, Mic, Search } from "lucide-react";
import { HERO } from "@/lib/images";
import { usePrefs } from "@/store/prefs";
import { Logo } from "@/components/ui";

const FEATURES = [
  { icon: Search, title: "Find", text: "Homes, plots & shops across Pakistan" },
  { icon: Building2, title: "List", text: "Publish your property in minutes" },
  { icon: Mic, title: "Talk", text: "Ask the AI by voice — English or Urdu" },
];

/** First-launch screen: brand hero + sign up / sign in / browse as guest. */
export default function Welcome() {
  const nav = useNavigate();
  const setOnboarded = usePrefs((s) => s.setOnboarded);
  const guest = () => {
    setOnboarded(true);
    nav("/", { replace: true });
  };
  return (
    <div className="relative flex min-h-full flex-col overflow-hidden bg-brand-950 text-white">
      <img src={HERO.panorama} alt="" className="absolute inset-0 h-full w-full object-cover opacity-45" />
      <div className="absolute inset-0 bg-gradient-to-t from-brand-950 via-brand-950/75 to-brand-950/10" />
      <div className="absolute inset-0 bg-mesh opacity-70" />

      <div className="pt-safe drag relative px-6 pt-6">
        <Logo light />
      </div>

      <div className="pb-safe relative mx-auto mt-auto w-full max-w-md px-6 pb-8">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
          <span className="chip bg-white/10 text-gold-200 ring-1 ring-white/15">
            <Bot className="h-3.5 w-3.5" /> AI Real Estate Portal
          </span>
          <h1 className="mt-4 font-display text-4xl font-bold leading-[1.1]">
            Your land.
            <br />
            Our intelligence.
            <br />
            <span className="text-gradient">A brighter Pakistan.</span>
          </h1>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15, duration: 0.5 }} className="mt-7 grid grid-cols-3 gap-2.5">
          {FEATURES.map((f) => (
            <div key={f.title} className="glass-dark rounded-2xl p-3">
              <f.icon className="h-5 w-5 text-gold-300" />
              <p className="mt-2 text-sm font-bold">{f.title}</p>
              <p className="mt-0.5 text-[11px] leading-snug text-white/70">{f.text}</p>
            </div>
          ))}
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3, duration: 0.5 }} className="mt-8 space-y-3">
          <Link to="/signup" className="btn btn-gold btn-lg w-full">
            Create free account
          </Link>
          <Link to="/signin" className="btn btn-lg w-full border border-white/25 bg-white/10 text-white backdrop-blur hover:bg-white/15">
            I already have an account
          </Link>
          <button onClick={guest} className="w-full py-2 text-sm font-semibold text-white/75 hover:text-white">
            Browse as guest
          </button>
        </motion.div>
      </div>
    </div>
  );
}
