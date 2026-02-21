import type { Config } from "tailwindcss"

// TailwindCSS v4 - minimal config file
// Most configuration is now in globals.css using @theme directive
// This file is kept for darkMode setting which must be JS-configured
const config = {
  darkMode: ["class", "[data-theme='dark']"],
  content: [
    './pages/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './app/**/*.{ts,tsx}',
  ],
} satisfies Config

export default config
