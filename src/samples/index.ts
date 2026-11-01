/**
 * ③ 샘플 데이터 — 가상의 서류 · 탐지 결과 · 검토사항 · 문서 간 연결.
 * 이름·주민등록번호·전화번호·계좌번호·주소·금액은 모두 가상의 데모 데이터다(실제 인물·거래와 관계없음).
 * 순수 데이터만 둔다. 서비스를 조작하는 seedReviewActions · demoProgressA1 은 src/services/demo/seed.ts 에 있다.
 * 이 폴더는 src/services/demo/** 만 import한다(ESLint no-restricted-imports 로 강제).
 */

export { F, H, I, Lk, TX_ALIGN, TX_HEAD } from './builders';
export type { FindingExtra, ReviewItemExtra } from './builders';
export { loanDocs } from './documents';
export { brokenSet, incomeSet, loanResults, maskedSet, newSet, scanSet } from './sets';
export type { ResultSet, SampleSet } from './sets';
export { mkA, rawSamples, summaryText } from './analyses';
export type { MkAInput } from './analyses';
