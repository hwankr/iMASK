'use client';

import { Dropdown, SearchField, type DropdownOption } from '@/components/ui';
import type { Analysis } from '@/services/types';
import { LIST_CONTROL_IDS } from './listFocus';
import { dropdownModels, type ListFilters, type ReviewFilter, type RiskFilter, type SortKey, type StatusFilter } from './listModel';
import type { SetListFilters } from './useListFilters';
import styles from './ListToolbar.module.css';

/**
 * 도구 줄 — 검색 + 드롭다운 4개(위험등급 · 분석 상태 · 검토 상태 필터, 정렬). Main 142–163.
 * - 필터 드롭다운은 '전체'가 아니면 초록, 메뉴 항목에 타일 아이콘과 건수(전체 목록 기준).
 * - 검색칸 · 필터 트리거에 고정 id(LIST_CONTROL_IDS) — 오류 모달이 닫힐 때 행이 필터에서 빠졌으면 이리로 돌아온다.
 * - 정렬은 데스크톱에서 오른쪽 끝(margin-left:auto). 휴대폰에서는 줄바꿈 흐름 그대로 두고,
 *   메뉴가 화면 밖으로 나가지 않게 오른쪽에 오는 분석 상태·정렬 메뉴를 오른쪽에 맞춘다(listVM `right`).
 */
export function ListToolbar({
  all,
  filters,
  setFilters,
  mobile,
  live = false,
}: {
  all: readonly Analysis[];
  filters: ListFilters;
  setFilters: SetListFilters;
  mobile: boolean;
  /** 실제 분석 목록 — 위험등급 필터에 '검토 필요' 선택지 */
  live?: boolean;
}) {
  const [risk, status, review, sort] = dropdownModels(all, live);
  const opts = <V extends string>(m: typeof risk) =>
    m.options.map((o): DropdownOption<V> => ({ value: o.value as V, label: o.label, icon: o.icon, iconColor: o.iconColor, tileColor: o.tileColor, count: o.count }));

  return (
    <div className={styles.toolbar}>
      <SearchField
        id={LIST_CONTROL_IDS.search}
        className={styles.search}
        value={filters.q}
        onChange={(e) => setFilters({ q: e.target.value })}
        placeholder="분석명 또는 파일명 검색"
      />
      <Dropdown<RiskFilter> id={LIST_CONTROL_IDS.risk} variant="filter" title={risk.title} value={filters.risk} options={opts<RiskFilter>(risk)} onChange={(v) => setFilters({ risk: v })} />
      <Dropdown<StatusFilter>
        id={LIST_CONTROL_IDS.status}
        variant="filter"
        title={status.title}
        value={filters.status}
        options={opts<StatusFilter>(status)}
        onChange={(v) => setFilters({ status: v })}
        align={mobile ? 'end' : 'start'}
      />
      <Dropdown<ReviewFilter> id={LIST_CONTROL_IDS.review} variant="filter" title={review.title} value={filters.review} options={opts<ReviewFilter>(review)} onChange={(v) => setFilters({ review: v })} />
      <Dropdown<SortKey>
        variant="sort"
        title={sort.title}
        value={filters.sort}
        options={opts<SortKey>(sort)}
        onChange={(v) => setFilters({ sort: v })}
        align="end"
        className={styles.sort}
      />
    </div>
  );
}
