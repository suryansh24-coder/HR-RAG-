/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // A single slate ramp. Every surface, border and text colour in the app
        // comes from here, so the UI reads as one system rather than a pile of
        // components that each picked their own grey.
        canvas: "#0b1120",
        surface: {
          DEFAULT: "#111a2e",
          raised: "#16223a",
          sunken: "#0d1526",
        },
        edge: {
          DEFAULT: "#22304d",
          strong: "#31426a",
        },
        ink: {
          DEFAULT: "#e8eefb",
          muted: "#94a6c8",
          faint: "#64769b",
        },
        accent: {
          DEFAULT: "#4f8cff",
          soft: "#8ab4ff",
          deep: "#1f4fbf",
        },
        success: "#34d399",
        warning: "#fbbf24",
        danger: "#f87171",
      },
      fontFamily: {
        sans: [
          "Inter var",
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      boxShadow: {
        panel: "0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.6)",
        glow: "0 0 0 1px rgba(79,140,255,.35), 0 8px 32px -12px rgba(79,140,255,.45)",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "fade-up": "fade-up .28s cubic-bezier(.22,1,.36,1) both",
        shimmer: "shimmer 1.6s infinite",
      },
    },
  },
  plugins: [],
};
