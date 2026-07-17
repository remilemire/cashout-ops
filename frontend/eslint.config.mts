// frontend/eslint.config.mts

import js from "@eslint/js";
import eslintConfigPrettier from "eslint-config-prettier";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import { defineConfig, globalIgnores } from "eslint/config";
import globals from "globals";
import { dirname } from "path";
import tseslint from "typescript-eslint";
import { fileURLToPath } from "url";

export default defineConfig([
  globalIgnores(["dist", "node_modules"]),

  js.configs.recommended,
  ...tseslint.configs.recommended,

  eslintConfigPrettier,

  reactHooks.configs.flat.recommended,
  reactRefresh.configs.recommended,

  {
    files: ["**/*.{ts,tsx,mts}"],
    languageOptions: {
      globals: globals.browser,
      parserOptions: {
        tsconfigRootDir: dirname(fileURLToPath(import.meta.url)),
      },
    },
  },
]);
