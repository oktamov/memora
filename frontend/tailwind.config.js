/** @type {import('tailwindcss').Config} */
// Palette and type roles come straight from SPEC §10 "Design direction".
export default {
  darkMode: ['class', '[data-mode="dark"]'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: 'rgb(var(--ink) / <alpha-value>)',
        paper: 'rgb(var(--paper) / <alpha-value>)',
        indigo: 'rgb(var(--indigo) / <alpha-value>)',
        madder: 'rgb(var(--madder) / <alpha-value>)',
        saffron: 'rgb(var(--saffron) / <alpha-value>)',
        sage: 'rgb(var(--sage) / <alpha-value>)',

        ground: 'rgb(var(--ground) / <alpha-value>)',
        surface: 'rgb(var(--surface) / <alpha-value>)',
        raised: 'rgb(var(--raised) / <alpha-value>)',
        line: 'rgb(var(--line) / <alpha-value>)',
        body: 'rgb(var(--text) / <alpha-value>)',
        muted: 'rgb(var(--text-muted) / <alpha-value>)',
        faint: 'rgb(var(--text-faint) / <alpha-value>)',
      },
      fontFamily: {
        display: ['"Bricolage Grotesque"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        sans: ['"Source Sans 3"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      fontSize: {
        term: ['2.75rem', { lineHeight: '1.04', letterSpacing: '-0.035em' }],
        'term-lg': ['3.5rem', { lineHeight: '1.02', letterSpacing: '-0.04em' }],
      },
      borderRadius: {
        card: '1.125rem',
      },
      boxShadow: {
        card: '0 1px 2px rgb(22 26 43 / 0.06), 0 8px 24px -12px rgb(22 26 43 / 0.18)',
        lamp: '0 0 0 1px rgb(255 255 255 / 0.05), 0 24px 60px -20px rgb(0 0 0 / 0.7)',
      },
      keyframes: {
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to: { opacity: '1', transform: 'none' },
        },
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
      },
      animation: {
        'fade-up': 'fade-up 220ms cubic-bezier(0.22, 1, 0.36, 1) both',
        'fade-in': 'fade-in 180ms ease-out both',
      },
    },
  },
  plugins: [],
};
