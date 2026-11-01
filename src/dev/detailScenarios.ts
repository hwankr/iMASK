/* ==========================================================================
   /dev/states 상세 상태 11개 + 휴대폰 전용 2개의 화면 쪽 시작 조건 — 원본 initScenario(Main.dc.html 1553–1570)
   - 데모 서비스 상태(분석 건 · 대기 분석 만들기)는 PreparedState 의 prepare(state) 가 먼저 맞추고,
     열 분석 ID 를 돌려준다(detail-queued 는 그때 만든 ID).
   - 여기서는 상세 화면 조건(탭 · 고른 항목 · 문서 · 휴대폰 탭 · 모달)만 만든다(DetailScreen 의 initial).
     initial 을 주면 원본 initScenario 처럼 저절로 항목을 고르지 않는다.
   - detail-edit 의 정보 종류 · 노출 상태는 서비스가 준 F-20 값 그대로다(정보주체만 '기타'로 바꾼 상태).
   ========================================================================== */

import type { DetailUiState } from '@/components/detail/detailState';
import type { AnalysisService, StateId } from '@/services/analysis-service';

export type DetailStateId = Extract<
  StateId,
  | 'detail'
  | 'detail-queued'
  | 'detail-running'
  | 'detail-partial'
  | 'detail-failed'
  | 'detail-completed'
  | 'detail-nolocation'
  | 'detail-review'
  | 'detail-links'
  | 'detail-edit'
  | 'detail-complete'
  | 'detail-docs'
  | 'detail-results'
>;

/** detail-edit 의 수정 사유(원본 그대로) */
export const DETAIL_EDIT_NOTE = '거래내역서 연락처가 신청서 번호와 달라 신청인 번호로 단정할 수 없음';

/** 상태별 상세 화면 처음 값 */
export async function detailScenario(id: DetailStateId, service: AnalysisService, analysisId: string): Promise<Partial<DetailUiState>> {
  switch (id) {
    case 'detail':
      return { focus: { kind: 'finding', id: 'F-01' } };
    case 'detail-results':
      return { focus: { kind: 'finding', id: 'F-01' }, mTab: 'results' };
    case 'detail-docs':
      return { mTab: 'docs' };
    case 'detail-queued':
    case 'detail-running':
    case 'detail-failed':
      return {};
    case 'detail-partial':
      return { docId: 't2', tab: 'review' };
    case 'detail-completed':
      return { focus: { kind: 'finding', id: 'P-03' } };
    case 'detail-nolocation':
      return { focus: { kind: 'finding', id: 'F-23' } };
    /* 원본 focusItem: 검토사항의 첫 근거(pickItem 과 같은 위치) */
    case 'detail-review':
      return { tab: 'review', focus: { kind: 'item', id: 'R-01', idx: 0 } };
    /* 원본 focusLink: ['L-01', 1] — 연결의 두 번째 문서 */
    case 'detail-links':
      return { tab: 'links', focus: { kind: 'link', id: 'L-01', idx: 1 } };
    case 'detail-edit': {
      const a = await service.get(analysisId);
      const f = a?.findings.find((x) => x.id === 'F-20');
      const initial: Partial<DetailUiState> = { focus: { kind: 'finding', id: 'F-20' } };
      if (f) initial.modal = { type: 'edit', fid: 'F-20', cat: f.cat, subject: '기타', exposure: f.exposure, note: DETAIL_EDIT_NOTE, error: '' };
      return initial;
    }
    case 'detail-complete':
      return { modal: { type: 'complete', note: '', error: '' } };
    default: {
      const unknownState: never = id;
      throw new Error('알 수 없는 상세 상태: ' + String(unknownState));
    }
  }
}
