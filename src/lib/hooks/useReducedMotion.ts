import { useMediaQuery } from './useMediaQuery';

/** 시스템의 '동작 줄이기' 설정 */
export const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';

/**
 * '동작 줄이기'가 켜져 있는지. CSS 움직임은 globals.css 전역 규칙이 즉시 끝내므로,
 * 이 훅은 JS 로 하는 움직임(부드러운 스크롤 등)을 바꿀 때 쓴다.
 */
export function useReducedMotion(): boolean {
  return useMediaQuery(REDUCED_MOTION_QUERY);
}

/** 이벤트 처리기 안에서 바로 읽는 버전(렌더 중에는 useReducedMotion 을 쓴다) */
export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia(REDUCED_MOTION_QUERY).matches;
}

/** JS 스크롤 동작 — 동작 줄이기면 'auto'(즉시), 아니면 'smooth' */
export function scrollBehavior(reduced: boolean = prefersReducedMotion()): ScrollBehavior {
  return reduced ? 'auto' : 'smooth';
}
