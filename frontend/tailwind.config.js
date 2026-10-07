/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['Archivo Black', 'Inter', 'sans-serif'],
      },
      colors: {
        brand: {
          50:  '#fff0f0',
          100: '#ffd6d6',
          200: '#ffb0b0',
          300: '#ff7777',
          400: '#ff3b30',
          500: '#e60000',
          600: '#c40000',
          700: '#a30000',
          800: '#820000',
          900: '#610000',
          950: '#400000',
        },
        surface: {
          DEFAULT: '#f4f4f4',
          card:    '#ffffff',
          hover:   '#eeeeee',
          border:  '#d0d0d0',
        },
        primary: '#0d0d0d',
        secondary: '#6d6d6d',
        slate: {
          400: '#6d6d6d',
          500: '#6d6d6d',
          600: '#6d6d6d',
          700: '#0d0d0d',
        },
      },
      borderRadius: {
        sm: '2px',
        md: '4px',
        lg: '6px',
        xl: '6px',
        '2xl': '6px',
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
