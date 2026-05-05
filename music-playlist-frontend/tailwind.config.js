/** @type {import('tailwindcss') .Config} */
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
        plum: {
          50:  '#f5f0ff',
          100: '#ede5ff',
          200: '#ddd0ff',
          400: '#a855f7',
          600: '#7c3aed',
          700: '#6d28d9',
          900: '#3b0764',
        },
        blush: '#fde8e8',
        lavender: '#e8d5f5',
      },
    },
  },
  plugins: [],
}
