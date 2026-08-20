/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./app/static/js/**/*.js",
  ],
  theme: {
    extend: {
      // Same theme.extend the old in-browser `tailwind.config = {...}`
      // script (base.html / auth/login.html) defined — kept identical so
      // switching from the CDN's runtime JIT compiler to this ahead-of-time
      // build doesn't change a single class's rendered color/font.
      fontFamily: {
        medieval: ["MedievalSharp", "cursive"],
        cinzel: ["Cinzel", "serif"],
      },
      colors: {
        parchment: { 100: "#fdf6e3", 200: "#f4e8c1", 300: "#e0c99a", 900: "#4a3b22" },
        blood: "#8b0000",
        gold: "#d4af37",
        mystic: "#4b0082",
      },
    },
  },
  // Guardian/class/math-area colors (app/services/guardians.py,
  // app/services/classes.py, app/services/math_areas.py) are plain Tailwind
  // color tokens ("purple-400", "stone-300", ...) picked from Python data
  // and spliced into class="" via Jinja (e.g. `border-{{ g.color }}` in
  // mathematics/index.html). The content scanner above only ever sees the
  // literal template source — never the rendered HTML — so a class built
  // from a variable at render time is invisible to it and would silently
  // get purged. Safelisting every (family × shade) combination actually in
  // use keeps the ahead-of-time build behaving exactly like the old
  // in-browser JIT, which compiled from the live DOM and never had this
  // problem. Add new tokens here if a future guardian/class/area picks a
  // color outside this family/shade set — see the module docstrings above
  // for exactly where these come from.
  safelist: [
    {
      pattern:
        /^(border|text)-(slate|stone|red|orange|yellow|green|emerald|cyan|blue|indigo|violet|purple|rose)-(300|400)$/,
    },
  ],
  plugins: [],
};
