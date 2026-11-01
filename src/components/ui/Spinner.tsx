import { cx } from './cx';
import styles from './Spinner.module.css';

/** 돌림 표시 크기(px) — 디자인에 쓰인 값 */
export type SpinnerSize = 12 | 13 | 14 | 15 | 16 | 22 | 24;

/** 테두리 굵기 — 기본은 크기에 따라(15 이하 2px · 16 2.2px · 22 이상 3px). 'medium' 2.2px, 'heavy' 2.5px(버튼) */
export type SpinnerWeight = 'auto' | 'medium' | 'heavy';

export interface SpinnerProps {
  size?: SpinnerSize;
  weight?: SpinnerWeight;
  className?: string;
}

/**
 * 돌림 표시(dg-spin) — 테두리 한쪽이 빈 원이 돈다. 원본:
 * `border-radius:50%; border:2px solid currentColor; border-right-color:transparent; animation:dg-spin .75s linear infinite`
 * 22px 이상은 3px 테두리·0.8초. 색은 글자색(currentColor)을 따른다. 장식이라 aria-hidden.
 * 동작 줄이기에서는 globals.css 전역 규칙으로 한 번만(즉시) 돌고 멈춘다.
 */
export function Spinner({ size = 16, weight = 'auto', className }: SpinnerProps) {
  return <span aria-hidden="true" className={cx(styles.spinner, styles[`s${size}`], weight !== 'auto' && styles[weight], className)} />;
}
