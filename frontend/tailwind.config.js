/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'Helvetica Neue', 'sans-serif'],
        display: ['Playfair Display', 'Times New Roman', 'serif'],
        serif: ['Playfair Display', 'Times New Roman', 'serif'],
        body: ['Lora', 'Georgia', 'serif'],
        mono: ['JetBrains Mono', 'Courier New', 'monospace'],
      },
      colors: {
        brand: {
          50:  '#fceaea',
          100: '#f4cccc',
          200: '#e99a9a',
          300: '#dc6666',
          400: '#cc0000',
          500: '#cc0000',
          600: '#b30000',
          700: '#990000',
          800: '#800000',
          900: '#660000',
          950: '#400000',
        },
        surface: {
          DEFAULT: '#f9f9f7',
          card:    '#f9f9f7',
          hover:   '#f5f5f5',
          border:  '#111111',
        },
        primary: '#111111',
        secondary: '#525252',
        slate: {
          400: '#525252',
          500: '#737373',
          600: '#737373',
          700: '#404040',
        },
      },
      borderRadius: {
        none: '0px',
        sm: '0px',
        DEFAULT: '0px',
        md: '0px',
        lg: '0px',
        xl: '0px',
        '2xl': '0px',
        full: '0px',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'float': 'float 3s ease-in-out infinite',
        'confetti': 'confetti 1s ease-out forwards',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%':      { transform: 'translateY(-10px)' },
        }
      }
    },
  },
  plugins: [],
}
