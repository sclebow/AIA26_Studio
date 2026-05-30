/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["'Inter'", 'sans-serif'],
      },
      colors: {
        'canvas-gray': '#EDEDED',
        'border-gray': '#D9D9D9',
        'error': '#ef4444', // Tailwind red-500
        'error-light': '#fee2e2', // Tailwind red-100
        'success': '#22c55e', // Tailwind green-500
        'success-light': '#dcfce7', // Tailwind green-100
        'warning': '#f59e42', // Custom orange
        'warning-light': '#fef3c7', // Tailwind orange-100
        'primary-btn-from': '#00E0CD', // mint
        'primary-btn-to': '#0067B5', // blue
      },
    },
  },
  plugins: [],
}