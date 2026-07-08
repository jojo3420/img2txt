/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Pretendard",
          "-apple-system",
          "BlinkMacSystemFont",
          "Malgun Gothic",
          "Apple SD Gothic Neo",
          "system-ui",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      colors: {
        accent: {
          50: "#eef4ff",
          100: "#dfe9ff",
          400: "#5b8cff",
          500: "#3b6fee",
          600: "#2c56cf",
          700: "#2445a6",
        },
      },
    },
  },
  plugins: [],
};
