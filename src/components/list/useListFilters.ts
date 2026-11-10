'use client';

import { useSearchParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { useRouteBase, useServiceMode } from '@/services/react';
import { DEFAULT_FILTERS, filtersToQuery, parseFilters, type ListFilters } from './listModel';
import { rememberListQuery } from './listReturn';

/** 필터 바꾸기 — 바꿀 값만 넘긴다 */
export type SetListFilters = (patch: Partial<ListFilters>) => void;

/** 컴포넌트 상태로만 다루는 필터(/dev/states 미리보기 — syncWithUrl=false) */
export function useLocalListFilters(initial?: Partial<ListFilters>): [ListFilters, SetListFilters] {
  const [filters, setFilters] = useState<ListFilters>(() => ({ ...DEFAULT_FILTERS, ...initial }));
  const update: SetListFilters = (patch) => setFilters((prev) => ({ ...prev, ...patch }));
  return [filters, update];
}

interface UrlFilterState {
  /** 화면이 쓰는 필터(입력 즉시 바뀐다) */
  filters: ListFilters;
  /** 마지막으로 본 URL 검색 문자열(정규형) */
  seen: string;
  /** 이 화면이 URL 에 써 넣었지만 아직 useSearchParams 로 돌아오지 않은 값들(쓴 순서) */
  pending: string[];
}

/**
 * URL 검색 파라미터(q · risk · status · review · sort)와 이어진 필터. useSearchParams 를 쓰므로 Suspense 안에서 부른다.
 *
 * - 바꿀 때마다 `history.replaceState` 로 URL 만 바꾼다(기록을 쌓지 않음, 서버 요청 없음). Next 는 이 호출을
 *   useSearchParams 에 반영하지만 전환(transition)으로 늦게 오므로, 화면은 컴포넌트 상태를 바로 쓰고
 *   URL 은 뒤따라오게 한다(빠르게 입력해도 글자가 사라지지 않게).
 * - URL 이 이 화면이 쓴 값이 아닌 값으로 바뀌면(헤더 '검토 필요' 링크, 로고 → `/`, 뒤로 가기) URL 을 따른다.
 *   쓴 값이 늦게 돌아오는 것은 pending 목록으로 알아본다.
 * - `initial` 은 처음 그릴 때 URL 에 없는 값의 기본값이다(URL 값이 이긴다). URL 에는 사용자가 바꿀 때 함께 들어간다.
 * - 지금 필터를 listReturn 에 기억해 두어, 다른 화면의 '목록으로' 이동(상세 뒤로 · 헤더 메뉴 · 새 분석 취소)이
 *   프로토타입처럼 목록 상태를 이어 가게 한다. 기억은 기준 경로(useRouteBase — 루트 / `/demo`)마다 따로다.
 */
export function useUrlListFilters(initial?: Partial<ListFilters>): [ListFilters, SetListFilters] {
  const params = useSearchParams();
  const base = useRouteBase();
  // 위험등급 'review' 는 실제 분석 목록만 받는다(데모는 모르는 값과 같게 '전체')
  const live = useServiceMode() === 'api';
  const urlQuery = filtersToQuery(parseFilters(params, { live }));
  const [state, setState] = useState<UrlFilterState>(() => ({
    filters: { ...DEFAULT_FILTERS, ...initial, ...fromUrlOnly(params, live) },
    seen: urlQuery,
    pending: [],
  }));

  // 이전 렌더 정보로 상태 맞추기(렌더 중 setState — React 의 '이전 값 저장' 방식)
  let current = state;
  if (urlQuery !== state.seen) {
    const mine = state.pending.indexOf(urlQuery);
    current =
      mine >= 0
        ? { ...state, seen: urlQuery, pending: state.pending.slice(mine + 1) } // 내가 쓴 값이 돌아옴
        : { filters: parseFilters(params, { live }), seen: urlQuery, pending: [] }; // 바깥에서 바뀜 → URL 을 따른다
    setState(current);
  } else if (state.pending.length > 0 && urlQuery === filtersToQuery(state.filters)) {
    current = { ...state, pending: [] }; // URL 과 화면이 같아졌다 — 남은 기록은 필요 없다
    setState(current);
  }

  const shownQuery = filtersToQuery(current.filters);
  useEffect(() => {
    rememberListQuery(base, shownQuery, live);
  }, [base, shownQuery, live]);

  const update: SetListFilters = (patch) => {
    const next = { ...current.filters, ...patch };
    const query = filtersToQuery(next);
    setState((prev) => ({ ...prev, filters: next, pending: [...prev.pending, query] }));
    const url = window.location.pathname + (query ? '?' + query : '') + window.location.hash;
    window.history.replaceState(null, '', url);
  };

  return [current.filters, update];
}

/** URL 에 실제로 있는 필터 값만(없는 키는 빼서 initial 이 채우게) */
function fromUrlOnly(params: ReturnType<typeof useSearchParams>, live: boolean): Partial<ListFilters> {
  const parsed = parseFilters(params, { live });
  const out: Partial<ListFilters> = {};
  if (params.get('q') !== null) out.q = parsed.q;
  if (params.get('risk') !== null) out.risk = parsed.risk;
  if (params.get('status') !== null) out.status = parsed.status;
  if (params.get('review') !== null) out.review = parsed.review;
  if (params.get('sort') !== null) out.sort = parsed.sort;
  return out;
}
