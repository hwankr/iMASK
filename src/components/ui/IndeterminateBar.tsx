import { cx } from './cx';
import styles from './IndeterminateBar.module.css';

/**
 * 흐르는 막대 — 진행률을 모를 때 숫자 대신 '진행 중'만 알린다(dg-indet). 장식이라 aria-hidden.
 * - edge: 부모(position:relative; overflow:hidden) 아래 가장자리 2px 막대(상세 상태 띠 363, 보드 06)
 * - track: 회색 길 위를 흐르는 막대 — size sm 64×4(파일 올리는 중 301), md 꽉 찬 폭×6(결과 기다리는 중 568)
 */
export type IndeterminateBarVariant = 'edge' | 'track';

/** 색 — run(파랑, 분석 중) · accent(초록, 업로드) · warn(주황) */
export type IndeterminateBarTone = 'run' | 'accent' | 'warn';

export interface IndeterminateBarProps {
  variant?: IndeterminateBarVariant;
  tone?: IndeterminateBarTone;
  /** track 크기 */
  size?: 'sm' | 'md';
  className?: string;
}

export function IndeterminateBar({ variant = 'edge', tone = 'run', size = 'md', className }: IndeterminateBarProps) {
  if (variant === 'edge') {
    return <span aria-hidden="true" className={cx(styles.edge, styles[tone], className)} />;
  }
  return (
    <span aria-hidden="true" className={cx(styles.track, styles[`track-${size}`], styles[tone], className)}>
      <span className={styles.bar} />
    </span>
  );
}
