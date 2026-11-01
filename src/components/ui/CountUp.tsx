import type { CSSProperties } from 'react';
import { cx } from './cx';
import { VisuallyHidden } from './VisuallyHidden';
import styles from './CountUp.module.css';

export interface CountUpProps {
  /** 보여 줄 정수(0 이상). 값이 바뀌면 이전 값에서 새 값까지 이어서 변한다. */
  value: number;
  /**
   * 처음 세어 올라가는 시간 — normal 1.1초(--dur-count, 보고서) · fast 1초(--dur-1000, 목록 요약)
   * 값이 바뀔 때는 0.7초(--dur-count-change).
   */
  speed?: 'normal' | 'fast';
  /** 숫자 모양(글자 크기·굵기 등)은 쓰는 쪽이 준다 */
  className?: string;
}

/**
 * 요약 숫자 — 0에서 세어 올라가고(dg-count), 값이 바뀌면 이어서 변한다(@property --dg-n 의 transition).
 * 프로토타입과 같이 CSS 카운터로 그린다: `--dg-n` → `counter-reset: dgn var(--dg-n)` → `::after { content: counter(dgn) }`.
 * - 동작 줄이기: globals.css 전역 규칙이 움직임을 즉시 끝내므로 바로 최종 값이 보인다.
 * - 화면 낭독기: 움직이는 숫자는 aria-hidden, 최종 값만 숨김 글자로 읽힌다.
 */
export function CountUp({ value, speed = 'normal', className }: CountUpProps) {
  const n = Number.isFinite(value) ? Math.max(0, Math.round(value)) : 0;
  const style = { '--dg-n': n } as CSSProperties;
  return (
    <>
      <span aria-hidden="true" className={cx(styles.num, speed === 'fast' && styles.fast, className)} style={style} />
      <VisuallyHidden>{n}</VisuallyHidden>
    </>
  );
}
