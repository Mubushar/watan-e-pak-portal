/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: { center: true, padding: { DEFAULT: "1rem", lg: "2rem" }, screens: { "2xl": "1400px" } },
    extend: {
      colors: {
        brand: {
          50: "#ecf8f1", 100: "#d2eedf", 200: "#a6dcbf", 300: "#6fc497", 400: "#3da772",
          500: "#1f8a57", 600: "#146f45", 700: "#0f5a39", 800: "#0c472e", 900: "#093a26", 950: "#042016",
        },
        gold: {
          50: "#fdf9ec", 100: "#f9efc9", 200: "#f2dd8f", 300: "#e9c75a", 400: "#dcb13a",
          500: "#c99a22", 600: "#a87a19", 700: "#865b18", 800: "#6f4a1b", 900: "#5e3e1b",
        },
        ink: { DEFAULT: "#0f1f17", soft: "#3b4a42", mute: "#6b7a72" },
      },
      fontFamily: {
        sans: ["Plus Jakarta Sans", "Inter", "system-ui", "sans-serif"],
        display: ["Outfit", "Plus Jakarta Sans", "system-ui", "sans-serif"],
        urdu: ["Noto Nastaliq Urdu", "serif"],
      },
      boxShadow: {
        soft: "0 10px 30px -12px rgba(9, 58, 38, 0.25)",
        glow: "0 0 0 1px rgba(201,154,34,.35), 0 12px 40px -12px rgba(201,154,34,.45)",
        card: "0 1px 2px rgba(16,24,20,.06), 0 8px 24px -8px rgba(16,24,20,.12)",
      },
      backgroundImage: {
        "brand-gradient": "linear-gradient(135deg, #093a26 0%, #0f5a39 45%, #146f45 100%)",
        "gold-gradient": "linear-gradient(135deg, #f2dd8f 0%, #c99a22 55%, #a87a19 100%)",
        "mesh": "radial-gradient(at 20% 20%, rgba(31,138,87,.25) 0, transparent 50%), radial-gradient(at 80% 0%, rgba(201,154,34,.22) 0, transparent 45%), radial-gradient(at 50% 100%, rgba(15,90,57,.2) 0, transparent 50%)",
      },
      keyframes: {
        marquee: { from: { transform: "translateX(0)" }, to: { transform: "translateX(-50%)" } },
        "fade-up": { from: { opacity: 0, transform: "translateY(12px)" }, to: { opacity: 1, transform: "none" } },
        shimmer: { "100%": { transform: "translateX(100%)" } },
        float: { "0%,100%": { transform: "translateY(0)" }, "50%": { transform: "translateY(-8px)" } },
        pulseRing: { "0%": { transform: "scale(.8)", opacity: .8 }, "100%": { transform: "scale(2.2)", opacity: 0 } },
      },
      animation: {
        marquee: "marquee var(--marquee-duration, 60s) linear infinite",
        "fade-up": "fade-up .5s ease-out both",
        shimmer: "shimmer 1.6s infinite",
        float: "float 6s ease-in-out infinite",
        "pulse-ring": "pulseRing 1.8s cubic-bezier(.2,.6,.4,1) infinite",
      },
    },
  },
  plugins: [],
};
