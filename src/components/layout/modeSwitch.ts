/* ==========================================================================
   헤더의 모드 전환 링크 — 실제 분석이 있는 빌드(운영)에서 실제 분석 ↔ 데모를 오가는 작은 링크 하나.
   - 실제 분석 화면(주소 기준 모드 'api')에서는 데모(`/demo`)로 간다.
   - 실제 모드 빌드의 `/demo` 아래(모드 'demo', 빌드 모드 'api')에서는 실제 분석 목록(`/`)으로 돌아간다.
   - 데모 빌드(실제 분석이 없음)에는 없다.
   순수 함수(React · CSS 없음)라 node 테스트로 확인한다(modeSwitch.test.ts). 그리는 곳은 AppHeader.tsx.
   ========================================================================== */

import { DEMO_BASE, listHref } from '@/lib/routes';
import type { ServiceMode } from '@/services/mode';

export interface ModeSwitchLink {
  /** 갈 곳 */
  href: string;
  /** 보이는 글자(폭 768 이상)이자 접근 가능한 이름 */
  label: string;
  /** 좁은 폭(768 미만)의 짧은 글자 */
  short: string;
  /** 마우스를 올리면 보이는 설명 */
  title: string;
}

/** 실제 분석 화면 → 데모 */
export const TO_DEMO: ModeSwitchLink = { href: DEMO_BASE, label: '데모 체험하기', short: '데모', title: '샘플 데이터로 동작하는 데모 화면으로 이동합니다' };

/** 데모(`/demo`) → 실제 분석 */
export const TO_LIVE: ModeSwitchLink = { href: listHref(''), label: '실제 분석으로', short: '실제', title: '실제 분석 화면으로 돌아갑니다' };

/**
 * 지금 화면의 모드(주소 기준)와 이 빌드의 모드로 헤더의 전환 링크를 고른다. 없으면 null.
 * - 'api' 화면 → 데모로(실제 분석 화면은 실제 모드 빌드에만 있다)
 * - 'demo' 화면 + 빌드 'api' → 실제 분석으로(`/demo` 아래)
 * - 'demo' 화면 + 빌드 'demo' → 없음(루트도 데모라 돌아갈 실제 분석이 없다)
 */
export function modeSwitchLink(mode: ServiceMode, buildMode: ServiceMode): ModeSwitchLink | null {
  if (mode === 'api') return TO_DEMO;
  if (buildMode === 'api') return TO_LIVE;
  return null;
}
