/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        sage: "var(--bg-sage)",
        mist: "var(--surface-mist)",
        lime: "var(--accent-lime)",
        "lime-ink": "var(--accent-lime-ink)",
        orange: "var(--accent-orange)",
        ink: "var(--text-ink)",
        stone: "var(--text-stone)",
        success: "var(--success-ink)",
        "success-soft": "var(--success-soft)",
        warning: "var(--warning-ink)",
        "warning-soft": "var(--warning-soft)",
        danger: "var(--danger-ink)",
        "danger-soft": "var(--danger-soft)",
      },
      fontFamily: {
        sans: ["var(--font-urbanist)", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      borderRadius: {
        xl: "32px",
        "2xl": "40px",
      },
    },
  },
  plugins: [],
};
