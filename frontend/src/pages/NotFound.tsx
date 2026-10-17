import { Link } from "react-router-dom";
import { Compass, Home, Sparkles } from "lucide-react";
import { HERO } from "@/lib/images";

export default function NotFound() {
  return (
    <div className="container py-12">
      <div className="relative overflow-hidden rounded-[2rem] bg-brand-950 px-6 py-20 text-center text-white">
        <img src={HERO.landscape} alt="" className="absolute inset-0 h-full w-full object-cover opacity-25" />
        <div className="relative">
          <Compass className="mx-auto h-14 w-14 text-gold-300" />
          <p className="mt-6 font-display text-7xl font-extrabold text-gradient">404</p>
          <h1 className="mt-2 font-display text-2xl font-bold">This plot hasn’t been developed yet</h1>
          <p className="mx-auto mt-2 max-w-md text-white/70">The page you’re looking for doesn’t exist or has moved.</p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link to="/" className="btn btn-gold">
              <Home className="h-4 w-4" /> Back home
            </Link>
            <Link to="/ai" className="btn border border-white/20 bg-white/10 text-white hover:bg-white/20">
              <Sparkles className="h-4 w-4" /> Ask the AI
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
