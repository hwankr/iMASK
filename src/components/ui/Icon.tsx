import type { IconName } from '@/display/icon-names';
import { cx } from './cx';
import styles from './Icon.module.css';

/** 아이콘 크기(px) — 디자인에 쓰인 값. 실제 크기는 --size-* 토큰. 로고는 높이 기준(28 → 24×28, 24 → 21×24, 그 밖의 값은 28). */
export type IconSize = 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 22 | 24 | 28;

/** 선 굵기 — 디자인에 쓰인 값(viewBox 24 기준). */
export type IconStroke = 1.9 | 2 | 2.1 | 2.2 | 2.3 | 2.4 | 2.6;

export interface IconProps {
  name: IconName;
  /** 기본 16 */
  size?: IconSize;
  /** 선 아이콘(dg-i-*)의 선 굵기. 기본 2. 위험 막대·로고는 채움 도형이라 쓰지 않는다. */
  strokeWidth?: IconStroke;
  /** 뜻이 있는 아이콘이면 이름을 준다(role="img"). 없으면 장식(aria-hidden). */
  title?: string;
  className?: string;
}

type IconKind = 'line' | 'glyph' | 'logo';

function kindOf(name: IconName): IconKind {
  if (name === 'dg-logo') return 'logo';
  if (name.startsWith('dg-r')) return 'glyph';
  return 'line';
}

const VIEWBOX: Record<IconKind, string> = {
  line: '0 0 24 24',
  glyph: '0 0 12 12',
  logo: '0 0 28 32',
};

/**
 * 스프라이트 아이콘 — `<svg><use href="#name" /></svg>`.
 * IconSprite 가 화면에 한 번 있어야 한다(AppShell).
 */
export function Icon({ name, size = 16, strokeWidth = 2, title, className }: IconProps) {
  const kind = kindOf(name);
  const line = kind === 'line';
  return (
    <svg
      className={cx(styles.icon, kind === 'logo' ? (size === 24 ? styles.logo24 : styles.logo28) : styles[`s${size}`], className)}
      viewBox={VIEWBOX[kind]}
      fill={line ? 'none' : undefined}
      stroke={line ? 'currentColor' : undefined}
      strokeWidth={line ? strokeWidth : undefined}
      strokeLinecap={line ? 'round' : undefined}
      strokeLinejoin={line ? 'round' : undefined}
      role={title ? 'img' : undefined}
      aria-label={title || undefined}
      aria-hidden={title ? undefined : true}
      focusable="false"
    >
      {title ? <title>{title}</title> : null}
      <use href={`#${name}`} />
    </svg>
  );
}
