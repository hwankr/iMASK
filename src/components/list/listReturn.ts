'use client';

import { useSyncExternalStore } from 'react';
import { DEFAULT_FILTERS, filtersToQuery, parseFilters, type ListFilters } from './listModel';

/* ==========================================================================
   목록으로 돌아가기 — 마지막으로 본 목록의 검색·필터·정렬을 기억해 다른 화면의 '목록으로' 이동에 쓴다.
   필터는 URL(q · risk · status · review · sort)에 있고, 목록 화면(useUrlListFilters)이 바뀔 때마다 여기에 적는다.
   기억은 탭 하나의 sessionStorage(새로 고침해도 남고, 탭을 닫으면 사라짐)라 실제 저장과 무관하다.

   프로토타입 동작(Main 1655 goHome · 2589 goList · 2569 nav):
   - 상세의 '목록으로'(goList) · 새 분석 '취소' — 필터·정렬을 그대로 둔다
   - 헤더 '문서 분석'(nav.a) — '검토 필요' 필터만 푼다
   - 헤더 '검토 필요'(nav.b) — 검색·위험·상태를 풀고 '검토 필요'만 건다(정렬은 그대로)
   - 로고(goHome) — 검색·필터를 모두 푼다(정렬은 그대로)
   ========================================================================== */

const KEY = 'imask:list-query';

/** 저장소를 못 쓰는 환경(사생활 보호 모드 등)에서도 이 탭 안에서는 기억한다 */
let memory = '';
const listeners = new Set<() => void>();

function read(): string {
  try {
    const v = window.sessionStorage.getItem(KEY);
    if (v !== null) memory = v;
  } catch {
    /* 저장소 없음 — memory 를 쓴다 */
  }
  return memory;
}

/** 목록 화면이 지금 필터를 적는다(정규형 검색 문자열, 물음표 없음) */
export function rememberListQuery(query: string): void {
  const next = filtersToQuery(parseFilters(new URLSearchParams(query)));
  if (next === read()) return;
  memory = next;
  try {
    window.sessionStorage.setItem(KEY, next);
  } catch {
    /* 저장소 없음 — memory 만 */
  }
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  const onStorage = (e: StorageEvent) => {
    if (e.key === KEY) listener();
  };
  window.addEventListener('storage', onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener('storage', onStorage);
  };
}

/** 서버 렌더·하이드레이션 첫 렌더는 '' — 링크가 `/` 로 그려졌다가 기억한 값으로 바뀐다(불일치 없음) */
const serverSnapshot = () => '';

/** 기억한 목록 검색 문자열 */
export function useRememberedListQuery(): string {
  return useSyncExternalStore(subscribe, read, serverSnapshot);
}

/* ---------- 이동할 주소(순수) ---------- */

function href(f: ListFilters): string {
  const q = filtersToQuery(f);
  return q ? '/?' + q : '/';
}

/** 상세 '목록으로' · 새 분석 '취소' — 마지막 목록 그대로 */
export function listReturnHref(query: string): string {
  return href(parseFilters(new URLSearchParams(query)));
}

/** 헤더 '문서 분석' — '검토 필요' 필터만 푼다 */
export function listNavHref(query: string): string {
  const f = parseFilters(new URLSearchParams(query));
  return href({ ...f, review: f.review === 'needed' ? 'all' : f.review });
}

/** 헤더 '검토 필요' — 검색·위험·상태를 풀고 검토 필요만(정렬 유지) */
export function reviewNeededHref(query: string): string {
  const f = parseFilters(new URLSearchParams(query));
  return href({ ...DEFAULT_FILTERS, review: 'needed', sort: f.sort });
}

/** 로고 — 검색·필터를 모두 푼다(정렬 유지) */
export function listHomeHref(query: string): string {
  const f = parseFilters(new URLSearchParams(query));
  return href({ ...DEFAULT_FILTERS, sort: f.sort });
}
