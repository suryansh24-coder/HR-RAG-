/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // One ramp, two themes. Every surface, border and text colour in the app
        // comes from the CSS custom properties declared in `src/index.css`, so the
        // UI reads as a single system rather than a pile of components that each
        // picked their own grey — and the light/dark toggle swaps the whole
        // palette without a single component changing.
        //
        // The `rgb(var(--token) / <alpha-value>)` form is what keeps Tailwind's
        // opacity modifiers (`bg-accent/12`, `border-edge/40`) working.
        canvas: "rgb(var(--color-canvas) / <alpha-value>)",
        surface: {
          DEFAULT: "rgb(var(--color-surface) / <alpha-value>)",
          raised: "rgb(var(--color-surface-raised) / <alpha-value>)",
          sunken: "rgb(var(--color-surface-sunken) / <alpha-value>)",
        },
        edge: {
          DEFAULT: "rgb(var(--color-edge) / <alpha-value>)",
          strong: "rgb(var(--color-edge-strong) / <alpha-value>)",
        },
        ink: {
          DEFAULT: "rgb(var(--color-ink) / <alpha-value>)",
          muted: "rgb(var(--color-ink-muted) / <alpha-value>)",
          faint: "rgb(var(--color-ink-faint) / <alpha-value>)",
        },
        accent: {
          DEFAULT: "rgb(var(--color-accent) / <alpha-value>)",
          soft: "rgb(var(--color-accent-soft) / <alpha-value>)",
          deep: "rgb(var(--color-accent-deep) / <alpha-value>)",
        },
        success: "rgb(var(--color-success) / <alpha-value>)",
        warning: "rgb(var(--color-warning) / <alpha-value>)",
        danger: "rgb(var(--color-danger) / <alpha-value>)",
      },
      fontFamily: {
        // No webfont is fetched at runtime: the app must work offline, behind an
        // air-gapped proxy and inside the nginx image without an outbound call.
        // "Inter" is used when it is installed locally, otherwise the platform
        // UI font applies. To pin Inter, drop the woff2 files in
        // `public/fonts/`, add @font-face rules to `src/index.css` and nothing
        // else changes.
        sans: [
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
        // Theme-aware surfaces use the `--shadow-panel` custom property (see
        // index.css) instead of a static value, because a dark-mode drop shadow
        // on a white surface reads as a smudge rather than as depth.
        panel: "var(--shadow-panel)",
        lift: "var(--shadow-lift)",
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
