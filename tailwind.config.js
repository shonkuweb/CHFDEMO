/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./*.html", "./assets/**/*.js"],
  darkMode: "class",
  theme: {
      extend: {
          colors: {
              "primary": "#4a5d4e",
              "primary-hover": "#5d7362",
              "accent-bronze": "#a68b6a",
              "background-dark": "#000000",
              "background-darker": "#000000",
              "surface-dark": "#141414",
              "ivory": "#e8e4db",
              "ivory-dim": "#b5b1a6",
              "charcoal": "#121212",
          },
          fontFamily: {
              "display": ["Manrope", "sans-serif"],
              "serif": ["Noto Serif", "serif"],
          },
          borderRadius: { "DEFAULT": "0rem", "lg": "0rem", "xl": "0rem", "full": "9999px" },
          animation: {
              'pulse-slow': 'pulse-slow 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
              'spin-slow': 'spin-slow 12s linear infinite',
          },
          keyframes: {
              'pulse-slow': {
                  '0%, 100%': { opacity: '0.3', transform: 'translateY(0)' },
                  '50%': { opacity: '0.8', transform: 'translateY(5px)' },
              },
              'spin-slow': {
                  'from': { transform: 'rotate(0deg)' },
                  'to': { transform: 'rotate(360deg)' },
              }
          }
      },
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/container-queries')
  ],
}
