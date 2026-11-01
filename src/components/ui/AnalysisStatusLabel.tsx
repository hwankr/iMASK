import type { CSSProperties } from 'react';
import { analysisStatusView } from '@/display/rules';
import { cx } from './cx';
import { Icon, type IconSize, type IconStroke } from './Icon';
import { Spinner, type SpinnerSize } from './Spinner';
import styles from './AnalysisStatusLabel.module.css';

/**
 * 크기 — 디자인에 나온 모양 그대로(글자 / 아이콘)
 * - xs 12.5/14(문서 목록) · sm 13.5/15(휴대폰 카드) · md 14/16(목록 행·상세 머리)
 * - lg 14.5/17(보드 01) · xl 15/17(보고서 머리)
 */
export type AnalysisStatusSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl';

export interface AnalysisStatusLabelProps {
  /** 서비스 값(queued·running·done·partial·failed). 모르는 값은 ② 규칙대로 '대기'. */
  status: string | null | undefined;
  size?: AnalysisStatusSize;
  /** md 크기에서 굵은 글자(800) — 상세 머리 */
  strong?: boolean;
  className?: string;
}

const ICON: Record<AnalysisStatusSize, { icon: IconSize; stroke: IconStroke; ring: SpinnerSize }> = {
  xs: { icon: 14, stroke: 2.1, ring: 12 },
  sm: { icon: 15, stroke: 2, ring: 13 },
  md: { icon: 16, stroke: 2, ring: 14 },
  lg: { icon: 17, stroke: 2.1, ring: 15 },
  xl: { icon: 17, stroke: 2.1, ring: 15 },
};

/**
 * 분석 상태 — 배경 없이 아이콘 + 글자. '분석 중'(② spin)은 아이콘 자리에서 돌림 표시가 돈다(dg-spin).
 * 라벨·색·아이콘은 ② analysisStatusView 에서만 가져온다. '완료'는 안전하다는 뜻이 아니라 중립색이다.
 */
export function AnalysisStatusLabel({ status, size = 'md', strong = false, className }: AnalysisStatusLabelProps) {
  const s = analysisStatusView(status);
  const spec = ICON[size];
  const stroke: IconStroke = size === 'md' && strong ? 2.1 : spec.stroke;
  const style = { '--as-fg': s.fg } as CSSProperties;
  return (
    <span className={cx(styles.label, styles[size], strong && styles.strong, className)} style={style}>
      {s.spin ? (
        <Spinner size={spec.ring} weight={size === 'lg' ? 'medium' : 'auto'} />
      ) : (
        <Icon name={s.icon} size={spec.icon} strokeWidth={stroke} />
      )}
      {s.label}
    </span>
  );
}
