import type { CSSProperties } from 'react';
import { riskView } from '@/display/rules';
import { cx } from './cx';
import { Icon } from './Icon';
import styles from './RiskBadge.module.css';

/**
 * 크기 — 디자인에 나온 모양 그대로
 * - xs: 24px(탐지 항목 행·모달 대상) · sm: 26px(목록 행) · md: 28px(보드 01) · lg: 30px(보고서 머리)
 */
export type RiskBadgeSize = 'xs' | 'sm' | 'md' | 'lg';

export interface RiskBadgeProps {
  /** 서비스 값(high·medium·low·unrated). 모르는 값은 ② 규칙대로 '미평가'. */
  level: string | null | undefined;
  size?: RiskBadgeSize;
  /** sm 크기에서 굵은 글자(800)·막대 12px — 상세 머리 */
  strong?: boolean;
  className?: string;
}

/**
 * 위험등급 — 채운 사각 + 막대 수(dg-r*) + 라벨. 라벨·색·막대는 ② riskView 에서만 가져온다.
 */
export function RiskBadge({ level, size = 'sm', strong = false, className }: RiskBadgeProps) {
  const r = riskView(level);
  const glyph = size === 'lg' ? 13 : size === 'md' || (size === 'sm' && strong) ? 12 : 11;
  const style = { '--rb-fg': r.fg, '--rb-bg': r.bg } as CSSProperties;
  return (
    <span className={cx(styles.badge, styles[size], strong && styles.strong, className)} style={style} data-risk={r.key}>
      <Icon name={r.glyph} size={glyph} />
      {r.label}
    </span>
  );
}
