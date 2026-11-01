import { cx } from '@/components/ui/cx';
import styles from './DemoBadge.module.css';

export interface DemoBadgeProps {
  /** md: 헤더(28px · 12.5) · lg: 디자인 보드 머리(30px · 13) */
  size?: 'md' | 'lg';
  /** 글자 — 기본 '데모 데이터' */
  label?: string;
  className?: string;
}

/** 데모 데이터 표시 — 점 + 글자(Main 109). 샘플 데이터로 동작하는 환경임을 늘 보여 준다. */
export function DemoBadge({ size = 'md', label = '데모 데이터', className }: DemoBadgeProps) {
  return (
    <span title="샘플 데이터로 동작하는 데모 환경입니다" className={cx(styles.badge, styles[size], className)}>
      <span aria-hidden="true" className={styles.dot} />
      {label}
    </span>
  );
}
