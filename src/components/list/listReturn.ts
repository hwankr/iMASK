'use client';

import { useSyncExternalStore } from 'react';
import { DEMO_BASE, listHref, routeBaseFor, type RouteBase } from '@/lib/routes';
import { DEFAULT_FILTERS, filtersToQuery, parseFilters, type ListFilters } from './listModel';

/* ==========================================================================
   목록으로 돌아가기 — 마지막으로 본 목록의 검색·필터·정렬을 기억해 다른 화면의 '목록으로' 이동에 쓴다.
   필터는 URL(q · risk · status · review · sort)에 있고, 목록 화면(useUrlListFilters)이 바뀔 때마다 여기에 적는다.
   기억은 탭 하나의 sessionStorage(새로 고침해도 남고, 탭을 닫으면 사라짐)라 실제 저장과 무관하다.

   기준 경로(src/lib/routes.ts)마다 따로 기억한다 — 루트('') 는 `imask:list-query`, 데모 `/demo` 는
   `imask:demo:list-query`. `/demo` 에서 건 필터가 실제 분석 화면의 헤더 · '목록으로' 링크로 새지 않게(그 반대도).
   이동 주소 함수는 기준 경로를 꼭 받아 그 기준의 목록 주소를 만든다(루트 기준 결과는 예전과 같다).

   프로토타입 동작(Main 1655 goHome · 2589 goList · 2569 nav):
   - 상세의 '목록으로'(goList) · 새 분석 '취소' — 필터·정렬을 그대로 둔다
   - 헤더 '문서 분석'(nav.a) — '검토 필요' 필터만 푼다
   - 헤더 '검토 필요'(nav.b) — 검색·위험·상태를 풀고 '검토 필요'만 건다(정렬은 그대로)
   - 로고(goHome) — 검색·필터를 모두 푼다(정렬은 그대로)
   ========================================================================== */

/** 기준 경로별 sessionStorage 키 */
const KEYS: Record<RouteBase, string> = { '': 'imask:list-query', [DEMO_BASE]: 'imask:demo:list-query' };

/** 기준 경로 하나의 기억 — subscribe · read 는 기준마다 한 번 만든 안정된 함수(렌더마다 다시 구독하지 않게) */
interface ListMemory {
  read: () => string;
  write: (query: string) => void;
  subscribe: (listener: () => void) => () => void;
}

function createListMemory(key: string): ListMemory {
  /** 저장소를 못 쓰는 환경(사생활 보호 모드 등)에서도 이 탭 안에서는 기억한다 */
  let memory = '';
  const listeners = new Set<() => void>();

  const read = (): string => {
    try {
      const v = window.sessionStorage.getItem(key);
      if (v !== null) memory = v;
    } catch {
      /* 저장소 없음 — memory 를 쓴다 */
    }
    return memory;
  };

  const write = (next: string): void => {
    if (next === read()) return;
    memory = next;
    try {
      window.sessionStorage.setItem(key, next);
    } catch {
      /* 저장소 없음 — memory 만 */
    }
    listeners.forEach((l) => l());
  };

  const subscribe = (listener: () => void): (() => void) => {
    listeners.add(listener);
    const onStorage = (e: StorageEvent) => {
      if (e.key === key) listener();
    };
    window.addEventListener('storage', onStorage);
    return () => {
      listeners.delete(listener);
      window.removeEventListener('storage', onStorage);
    };
  };

  return { read, write, subscribe };
}

const memories: Record<RouteBase, ListMemory> = { '': createListMemory(KEYS['']), [DEMO_BASE]: createListMemory(KEYS[DEMO_BASE]) };

/** 목록 화면이 지금 필터를 적는다(정규형 검색 문자열, 물음표 없음) — 그 기준 경로의 기억에 */
export function rememberListQuery(base: RouteBase, query: string): void {
  memories[base].write(filtersToQuery(parseFilters(new URLSearchParams(query))));
}

/** 서버 렌더·하이드레이션 첫 렌더는 '' — 링크가 목록 첫 화면으로 그려졌다가 기억한 값으로 바뀐다(불일치 없음) */
const serverSnapshot = () => '';

/** 그 기준 경로에서 기억한 목록 검색 문자열 */
export function useRememberedListQuery(base: RouteBase): string {
  const m = memories[base];
  return useSyncExternalStore(m.subscribe, m.read, serverSnapshot);
}

/* ---------- 이동할 주소(순수) ---------- */

function href(base: RouteBase, f: ListFilters): string {
  return listHref(base, filtersToQuery(f));
}

/** 상세 '목록으로' · 새 분석 '취소' — 마지막 목록 그대로 */
export function listReturnHref(base: RouteBase, query: string): string {
  return href(base, parseFilters(new URLSearchParams(query)));
}

/** 헤더 '문서 분석' — '검토 필요' 필터만 푼다 */
export function listNavHref(base: RouteBase, query: string): string {
  const f = parseFilters(new URLSearchParams(query));
  return href(base, { ...f, review: f.review === 'needed' ? 'all' : f.review });
}

/** 헤더 '검토 필요' — 검색·위험·상태를 풀고 검토 필요만(정렬 유지) */
export function reviewNeededHref(base: RouteBase, query: string): string {
  const f = parseFilters(new URLSearchParams(query));
  return href(base, { ...DEFAULT_FILTERS, review: 'needed', sort: f.sort });
}

/** 로고 — 검색·필터를 모두 푼다(정렬 유지) */
export function listHomeHref(base: RouteBase, query: string): string {
  const f = parseFilters(new URLSearchParams(query));
  return href(base, { ...DEFAULT_FILTERS, sort: f.sort });
}

/** 헤더 주 메뉴 */
export type NavKey = 'analyses' | 'review';

/** 주 메뉴 활성 — 목록 경로(`/` 또는 `/demo`)이고 `review=needed` 면 '검토 필요', 그 밖에는 '문서 분석' */
export function activeNav(pathname: string | null, review: string | null): NavKey {
  const onList = pathname !== null && pathname === listHref(routeBaseFor(pathname));
  return onList && review === 'needed' ? 'review' : 'analyses';
}
