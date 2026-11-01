/* ==========================================================================
   아이콘 이름 — Main.dc.html 아이콘 스프라이트(45–97줄)의 심볼 ID 전부, 순서 그대로.
   아이콘 모양(SVG 경로)은 공통 컴포넌트(T2)가 만든다. 여기서는 이름만 정한다.
   ========================================================================== */

export const ICON_NAMES = [
  'dg-i-brand',
  'dg-i-file',
  'dg-i-report',
  'dg-i-layers',
  'dg-i-search',
  'dg-i-plus',
  'dg-i-upload',
  'dg-i-download',
  'dg-i-folder',
  'dg-i-chev-left',
  'dg-i-chev-right',
  'dg-i-chev-down',
  'dg-i-arrow-left',
  'dg-i-x',
  'dg-i-check',
  'dg-i-check-circle',
  'dg-i-alert',
  'dg-i-x-circle',
  'dg-i-clock',
  'dg-i-flag',
  'dg-i-circle',
  'dg-i-circle-dashed',
  'dg-i-check-badge',
  'dg-i-ban',
  'dg-i-pencil',
  'dg-i-memo',
  'dg-i-eye',
  'dg-i-eye-off',
  'dg-i-eye-half',
  'dg-i-zoom-in',
  'dg-i-zoom-out',
  'dg-i-fit',
  'dg-i-link',
  'dg-i-link-off',
  'dg-i-help',
  'dg-i-history',
  'dg-i-refresh',
  'dg-i-trash',
  'dg-i-info',
  'dg-i-pin-q',
  'dg-i-scissors',
  'dg-i-neq',
  'dg-i-panel',
  'dg-i-play',
  'dg-i-copy',
  /* 위험 막대(채운 칸 수 = 등급) */
  'dg-r3',
  'dg-r2',
  'dg-r1',
  'dg-r0',
  /* 로고 */
  'dg-logo',
] as const;

export type IconName = (typeof ICON_NAMES)[number];

export function isIconName(value: string): value is IconName {
  return (ICON_NAMES as readonly string[]).includes(value);
}
