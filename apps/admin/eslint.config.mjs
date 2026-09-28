import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Convenciones de interfaz (documento de la verdad §4.1, spec 003).
  {
    rules: {
      "react/forbid-dom-props": [
        "error",
        { forbid: [{ propName: "style", message: "Sin estilos en línea (§4.1)." }] },
      ],
      "react/forbid-component-props": [
        "error",
        { forbid: [{ propName: "style", message: "Sin estilos en línea (§4.1)." }] },
      ],
    },
  },
  {
    files: ["src/**/*.{ts,tsx,js,jsx}"],
    ignores: ["src/components/ui/**"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXAttribute[name.name='className'] :matches(Literal, TemplateLiteral)",
          message:
            "Tailwind solo en src/components/ui/: compón desde la ui y usa props/variantes (§4.1).",
        },
      ],
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
