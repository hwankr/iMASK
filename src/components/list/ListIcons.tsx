/*
 * 목록 화면 전용 크기의 스프라이트 아이콘 — 공통 Icon 의 크기 목록에 없는 21·22·26px 를 쓰는 곳(위험 타일 · 검색 결과 없음).
 * 크기는 className(토큰)으로 준다. 모양은 공통 스프라이트(dg-i-*) 그대로.
 */

interface SpriteIconProps {
  className?: string;
}

/** 위험 타일의 겹친 문서 아이콘 — stroke-width 1.9 (Main 175 · 183) */
export function LayersIcon({ className }: SpriteIconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <use href="#dg-i-layers" />
    </svg>
  );
}

/** 검색 결과 없음의 돋보기 — stroke-width 2 (Main 175 noResults) */
export function SearchIcon({ className }: SpriteIconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <use href="#dg-i-search" />
    </svg>
  );
}
