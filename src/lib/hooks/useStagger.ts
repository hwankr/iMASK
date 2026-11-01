import { useState, type CSSProperties } from 'react';

/** 순차 등장 — 목록 행 0.04초 간격(디자인 기준 07), 10번째 행부터는 같은 지연(프로토타입 Math.min(i, 9)) */
export const STAGGER_MAX_INDEX = 9;

/** i 번째 행의 등장 지연(CSS 값) — `calc(var(--dur-40) * i)` */
export function staggerDelay(index: number, maxIndex: number = STAGGER_MAX_INDEX): string {
  const i = Math.max(0, Math.min(Math.floor(index), maxIndex));
  return `calc(var(--dur-40) * ${i})`;
}

/** i 번째 행의 인라인 style — `{ animationDelay }` */
export function staggerStyle(index: number, maxIndex: number = STAGGER_MAX_INDEX): CSSProperties {
  return { animationDelay: staggerDelay(index, maxIndex) };
}

/**
 * 다시 재생 신호 — `signature`(필터·정렬 값 등)가 바뀔 때마다 true/false 가 뒤집힌다.
 * 같은 모양의 keyframes 두 개(dg-in / dg-in-b)를 번갈아 쓰면 행을 다시 그리지 않고도 등장 움직임이 다시 돈다.
 * (프로토타입 listSeq % 2)
 */
export function useReplayToggle(signature: string): boolean {
  const [state, setState] = useState({ signature, flip: false });
  if (state.signature !== signature) {
    const next = { signature, flip: !state.flip };
    setState(next);
    return next.flip;
  }
  return state.flip;
}
