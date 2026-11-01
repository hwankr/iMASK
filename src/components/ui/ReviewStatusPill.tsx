import type { CSSProperties } from 'react';
import { reviewStatusView } from '@/display/rules';
import { cx } from './cx';
import { Icon, type IconSize } from './Icon';
import styles from './ReviewStatusPill.module.css';

/**
 * 크기 — 디자인에 나온 모양 그대로
 * - xs 26px·12.5(휴대폰 카드) · sm 26px·13(목록 행) · md 28px·13.5(보드 01) · lg 30px·14(보고서 머리)
 */
export type ReviewStatusSize = 'xs' | 'sm' | 'md' | 'lg';

export interface ReviewStatusPillProps {
  /** 서비스 값(none·needed·done). 모르는 값은 ② 규칙대로 '미검토'. */
  status: string | null | undefined;
  size?: ReviewStatusSize;
  /** sm 크기에서 굵은 글자(800)·아이콘 14px·색 전환 — 상세 머리 */
  strong?: boolean;
  className?: string;
}

const ICON: Record<ReviewStatusSize, IconSize> = { xs: 12, sm: 13, md: 14, lg: 14 };

/**
 * 검토 상태 — 둥근 알약. '검토 필요'만 어둡게 채운다(② RSTATUS 의 bg·fg).
 * 라벨·색·아이콘은 ② reviewStatusView 에서만 가져온다.
 */
export function ReviewStatusPill({ status, size = 'sm', strong = false, className }: ReviewStatusPillProps) {
  const r = reviewStatusView(status);
  const style = { '--rv-fg': r.fg, '--rv-bg': r.bg, '--rv-line': r.line } as CSSProperties;
  return (
    <span className={cx(styles.pill, styles[size], strong && styles.strong, className)} style={style}>
      <Icon name={r.icon} size={size === 'sm' && strong ? 14 : ICON[size]} strokeWidth={2.3} />
      {r.label}
    </span>
  );
}
