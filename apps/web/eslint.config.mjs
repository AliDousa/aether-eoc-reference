// ESLint 10 flat config.
//
// eslint-config-next 16 exports flat-config arrays directly, so they are spread
// in as-is. The @eslint/eslintrc FlatCompat bridge is NOT used: it crashes when
// normalising this config, and it is unnecessary now that the config is native.
import coreWebVitals from "eslint-config-next/core-web-vitals";
import typescript from "eslint-config-next/typescript";

export default [
  {
    ignores: [".next/**", "node_modules/**", "next-env.d.ts", "coverage/**", "*.config.mjs"],
  },
  ...coreWebVitals,
  ...typescript,
  {
    rules: {
      // `any` is allowed only with a comment explaining why. There are none
      // today and this keeps it that way.
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
];
