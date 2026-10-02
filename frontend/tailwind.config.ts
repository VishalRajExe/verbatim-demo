import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./features/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef4ff",
          100: "#d9e6ff",
          500: "#2f6fed",
          600: "#1f57c9",
          700: "#1a46a3",
          900: "#0f2547",
        },
      },
    },
  },
  plugins: [],
};

export default config;
