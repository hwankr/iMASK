/* ==========================================================================
   /dev/states 상태 정의 — 디자인 states.md · Tweaks '시작 상태' 25개, 순서 그대로.
   목록 화면(/dev/states)에는 휴대폰 전용 2개를 뺀 23개만 보인다.
   ========================================================================== */

import type { StateId } from '@/services/analysis-service';

export type StateGroupId = 'list' | 'upload' | 'detail' | 'report';

export interface StateGroup {
  id: StateGroupId;
  title: string;
  /** 이 그룹의 상태가 여는 실제 화면 경로(상세·보고서의 [id] 는 prepare 가 고른 분석 건) */
  path: string;
}

export interface DevState {
  id: StateId;
  group: StateGroupId;
  title: string;
  /** 휴대폰 전용 — 목록에서 빼고 번호 없이 표시한다 */
  phoneOnly: boolean;
}

export const STATE_GROUPS: readonly StateGroup[] = [
  { id: 'list', title: '분석 목록', path: '/' },
  { id: 'upload', title: '새 분석', path: '/analyses/new' },
  { id: 'detail', title: '상세 검토', path: '/analyses/[id]' },
  { id: 'report', title: '보고서', path: '/analyses/[id]/report' },
];

export const DEV_STATES: readonly DevState[] = [
  { id: 'list', group: 'list', title: '분석 목록', phoneOnly: false },
  { id: 'list-empty', group: 'list', title: '분석 이력 없음', phoneOnly: false },
  { id: 'list-noresults', group: 'list', title: '검색 결과 없음', phoneOnly: false },
  { id: 'upload', group: 'upload', title: '파일 선택 전', phoneOnly: false },
  { id: 'upload-selected', group: 'upload', title: '파일 선택 완료', phoneOnly: false },
  { id: 'upload-unsupported', group: 'upload', title: '지원하지 않는 형식', phoneOnly: false },
  { id: 'upload-limit', group: 'upload', title: '제한 초과', phoneOnly: false },
  { id: 'upload-failed', group: 'upload', title: '업로드 실패', phoneOnly: false },
  { id: 'upload-requesting', group: 'upload', title: '분석 요청 중', phoneOnly: false },
  { id: 'detail', group: 'detail', title: '탐지 항목 선택', phoneOnly: false },
  { id: 'detail-queued', group: 'detail', title: '분석 대기', phoneOnly: false },
  { id: 'detail-running', group: 'detail', title: '분석 중', phoneOnly: false },
  { id: 'detail-partial', group: 'detail', title: '일부 문서 처리 실패', phoneOnly: false },
  { id: 'detail-failed', group: 'detail', title: '전체 분석 실패', phoneOnly: false },
  { id: 'detail-completed', group: 'detail', title: '검토 완료', phoneOnly: false },
  { id: 'detail-nolocation', group: 'detail', title: '원문 위치 정보 없음', phoneOnly: false },
  { id: 'detail-review', group: 'detail', title: '검토사항 탭', phoneOnly: false },
  { id: 'detail-links', group: 'detail', title: '문서 간 연결', phoneOnly: false },
  { id: 'detail-edit', group: 'detail', title: '분류 수정', phoneOnly: false },
  { id: 'detail-complete', group: 'detail', title: '검토 완료 확인 (남은 항목 있음)', phoneOnly: false },
  { id: 'detail-docs', group: 'detail', title: '휴대폰 · 문서 탭', phoneOnly: true },
  { id: 'detail-results', group: 'detail', title: '휴대폰 · 탐지 결과 탭', phoneOnly: true },
  { id: 'report', group: 'report', title: '검토 결과 보고서', phoneOnly: false },
  { id: 'report-saved', group: 'report', title: '내보내기 완료', phoneOnly: false },
  { id: 'report-failed', group: 'report', title: '내보내기 실패', phoneOnly: false },
];

/** /dev/states 목록에 보이는 상태(휴대폰 전용 제외, 23개) */
export const LISTED_STATES: readonly DevState[] = DEV_STATES.filter((s) => !s.phoneOnly);

export function findGroup(id: StateGroupId): StateGroup {
  const group = STATE_GROUPS.find((g) => g.id === id);
  if (!group) throw new Error('알 수 없는 상태 그룹: ' + id);
  return group;
}

export function findState(id: string): DevState | undefined {
  return DEV_STATES.find((s) => s.id === id);
}

export function isStateId(id: string): id is StateId {
  return findState(id) !== undefined;
}

export interface StatePosition {
  state: DevState;
  /** 목록 번호(1부터). 휴대폰 전용이면 null */
  number: number | null;
  total: number;
  /** 목록 안의 이전·다음 상태(휴대폰 전용 상태에서는 앞뒤의 가장 가까운 목록 상태) */
  prev: DevState | null;
  next: DevState | null;
}

export function statePosition(id: StateId): StatePosition | null {
  const state = findState(id);
  if (!state) return null;
  const all = DEV_STATES.indexOf(state);
  const before = DEV_STATES.slice(0, all).filter((s) => !s.phoneOnly);
  const after = DEV_STATES.slice(all + 1).filter((s) => !s.phoneOnly);
  return {
    state,
    number: state.phoneOnly ? null : LISTED_STATES.indexOf(state) + 1,
    total: LISTED_STATES.length,
    prev: before.length ? before[before.length - 1] : null,
    next: after.length ? after[0] : null,
  };
}
