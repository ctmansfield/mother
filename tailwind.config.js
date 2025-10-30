/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        tile: {
          correct: "#6aaa64",
          present: "#c9b458",
          absent: "#3a3a3c",
          empty: "#121212",
          border: "#3a3a3c",
        },
        key: {
          base: "#818384",
          correct: "#6aaa64",
          present: "#c9b458",
          absent: "#3a3a3c",
        },
      },
      boxShadow: {
        soft: "0 10px 30px rgba(0,0,0,0.25)",
      },
    },
  },
  plugins: [],
};
