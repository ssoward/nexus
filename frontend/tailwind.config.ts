import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      colors: {
        terminal: {
          bg: '#0d1117',
          fg: '#c9d1d9',
          border: '#30363d',
          active: '#388bfd',
        },
      },
      keyframes: {
        'slide-in': {
          from: { opacity: '0', transform: 'translateX(1rem)' },
          to:   { opacity: '1', transform: 'translateX(0)' },
        },
        'idle-pulse': {
          '0%, 100%': { borderColor: 'rgb(245 158 11 / 0.5)' },
          '50%': { borderColor: 'rgb(245 158 11 / 0.2)' },
        },
      },
      animation: {
        'slide-in': 'slide-in 0.18s ease-out',
        'idle-pulse': 'idle-pulse 2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
} satisfies Config
