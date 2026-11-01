import type { IconName } from '@/display/icon-names';

/**
 * 상세 화면 전용 크기의 스프라이트 아이콘 — 공통 Icon 의 크기 목록에 없는 26px(빈 상태 · 전체 실패)를 쓰는 곳.
 * 크기는 className(토큰)으로 준다. 모양은 공통 스프라이트(dg-i-*) 그대로, 장식(aria-hidden).
 */
export function SpriteIcon({ name, className, strokeWidth = 2 }: { name: IconName; className?: string; strokeWidth?: number }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <use href={`#${name}`} />
    </svg>
  );
}
