import type { CSSProperties } from 'react';
import { FSTATUS, type FindingStatus } from '@/display/rules';
import { cx } from './cx';
import { Icon } from './Icon';
import styles from './FindingStatusLabel.module.css';

export interface FindingStatusLabelProps {
  /** 탐지 확인 상태(open·confirmed·false_positive·reclassified) */
  status: FindingStatus;
  className?: string;
}

/**
 * 탐지 확인 상태 — 아이콘 + 글자(Main 478: gap 4 · 12.5px · 800 · 아이콘 13 · 선 2.4).
 * 라벨·색·아이콘은 ② FSTATUS 에서만 가져온다. 모르는 값은 '미확인'.
 */
export function FindingStatusLabel({ status, className }: FindingStatusLabelProps) {
  const f = Object.prototype.hasOwnProperty.call(FSTATUS, status) ? FSTATUS[status] : FSTATUS.open;
  const style = { '--fst-fg': f.fg } as CSSProperties;
  return (
    <span className={cx(styles.label, className)} style={style}>
      <Icon name={f.icon} size={13} strokeWidth={2.4} />
      {f.label}
    </span>
  );
}
