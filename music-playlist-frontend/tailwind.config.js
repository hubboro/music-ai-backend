/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        display: ['Cormorant Garamond', 'serif'],
        body: ['Plus Jakarta Sans', 'sans-serif'],
      },
      colors: {
        sage: {
          50:  '#f4f7f2',
          100: '#e6ede3',
          200: '#cdddc8',
          300: '#a9c4a2',
          400: '#7a9e72',
          500: '#5e8356',
          600: '#4a6b43',
          700: '#3a5434',
          800: '#2d4129',
          900: '#1e2d1b',
        },
        cream: '#faf8f3',
        parchment: '#f0ede6',
      },
    },
  },
  plugins: [],
}
