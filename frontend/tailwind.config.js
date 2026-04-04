/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          900: '#0a0a0f',
          800: '#111118',
          700: '#1a1a24',
          600: '#24243a',
          500: '#2e2e44',
        },
        accent: {
          green: '#22c55e',
          red: '#ef4444',
          blue: '#3b82f6',
          amber: '#f59e0b',
          purple: '#a855f7',
        },
        text: {
          primary: '#f1f5f9',
          secondary: '#94a3b8',
          muted: '#64748b',
        },
        border: '#1e293b',
      },
    },
  },
  plugins: [],
}
