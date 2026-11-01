import type { CSSProperties, ReactNode } from 'react';
import { cx } from './cx';
import styles from './Skeleton.module.css';

export interface SkeletonProps {
  /** 폭(%) — 기본 100 */
  width?: number;
  /** title 12px · text 9px(디자인 값) */
  size?: 'title' | 'text';
  className?: string;
}

/** 뼈대 막대 한 줄 — 반짝임이 왼쪽으로 흐른다(dg-shimmer 1.5초). 장식이라 aria-hidden. */
export function Skeleton({ width = 100, size = 'text', className }: SkeletonProps) {
  const style = { '--sk-w': `${width}%` } as CSSProperties;
  return <span aria-hidden="true" className={cx(styles.line, styles[size], className)} style={style} />;
}

export interface SkeletonCardProps {
  /** 줄 폭(%) 목록 — 첫 줄은 제목 굵기. 기본은 보드 06 의 [46, 88, 72] */
  lines?: readonly number[];
  /** 카드 위 작은 설명(예: '뼈대 화면 · 원문 준비 중') */
  label?: ReactNode;
  /** board: 보드 06(안쪽 여백 20 · 선) · viewer: 원문 준비 중(Main 430, 여백 24 · 최대 380) */
  look?: 'board' | 'viewer';
  className?: string;
}

/** 뼈대 카드 — 흰 판 위에 뼈대 막대 여러 줄 */
export function SkeletonCard({ lines = [46, 88, 72], label, look = 'board', className }: SkeletonCardProps) {
  return (
    <div className={cx(styles.card, styles[look], className)}>
      {label ? <span className={styles.label}>{label}</span> : null}
      {lines.map((w, i) => (
        <Skeleton key={i} width={w} size={i === 0 ? 'title' : 'text'} />
      ))}
    </div>
  );
}
