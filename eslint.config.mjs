import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

/* ③ 샘플 데이터는 데모 서비스만 import한다(BRIEF §3 다섯 구역 규칙). */
const SAMPLES_MESSAGE = (label) =>
  `③ 샘플 데이터(${label})는 src/services/demo/** 만 import합니다. 화면은 services/react.tsx 의 훅(useService)을 쓰세요.`;

/** 샘플 경로 패턴 — 별칭(@/samples…)과 상대 경로(…/samples…) */
const SAMPLES_PATHS = [
  { label: "@/samples", regex: "^@/samples(/.*)?$" },
  { label: "samples", regex: "^\\.{1,2}/(.*/)?samples(/.*)?$" },
];

/** 정적 import·export … from (no-restricted-imports) */
const SAMPLES_IMPORT_RULE = [
  "error",
  {
    patterns: SAMPLES_PATHS.map((p) => ({ regex: p.regex, message: SAMPLES_MESSAGE(p.label) })),
  },
];

/**
 * no-restricted-imports 가 보지 않는 경로 문자열(no-restricted-syntax):
 * 동적 import(문자열·템플릿), require(), TS 의 import x = require(), 타입 위치의 import('…').
 * esquery 정규식 안의 `/` 는 `\/` 로 쓴다.
 */
const SAMPLES_SYNTAX_RULE = [
  "error",
  ...SAMPLES_PATHS.flatMap(({ label, regex }) => {
    const re = `/${regex.replaceAll("/", "\\/")}/`;
    const message = SAMPLES_MESSAGE(label);
    return [
      { selector: `ImportExpression[source.value=${re}]`, message },
      { selector: `ImportExpression[source.type="TemplateLiteral"][source.quasis.0.value.cooked=${re}]`, message },
      { selector: `CallExpression[callee.type="Identifier"][callee.name="require"][arguments.0.value=${re}]`, message },
      { selector: `TSExternalModuleReference[expression.value=${re}]`, message },
      { selector: `TSImportType[source.value=${re}]`, message },
    ];
  }),
];

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    files: ["**/*.{js,jsx,mjs,cjs,ts,tsx,mts,cts}"],
    rules: {
      "no-restricted-imports": SAMPLES_IMPORT_RULE,
      "no-restricted-syntax": SAMPLES_SYNTAX_RULE,
    },
  },
  {
    // 예외: 데모 서비스와 샘플 데이터 자신
    files: ["src/services/demo/**", "src/samples/**"],
    rules: {
      "no-restricted-imports": "off",
      "no-restricted-syntax": "off",
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // 오케스트레이션 자료(디자인 원본·보고서)
    ".orchestration/**",
    "coverage/**",
  ]),
]);

export default eslintConfig;
