'use client';

/* ==========================================================================
   상세 검토 동작 — T7 이 붙이는 자리.
   T6 은 버튼을 디자인대로 그 자리에 그리고, 누르면 아래 처리기를 부른다.
   - 모달을 여는 동작은 모달 자리(DetailUiState.modal)에 프로토타입 openModal 과 같은 값을 넣는다.
     모달을 그리고 제출하는 것(서비스 변경 메서드 호출 · 토스트)은 T7 이 한다.
   - 데이터를 바로 바꾸는 동작(확인 · 확인 취소 · 다시 열기 · 다시 분석)은 지금은 아무 일도 하지 않는다(TODO(T7)).
   T6 은 서비스의 변경 메서드를 부르지 않는다(조회와 구독만).
   ========================================================================== */

import { FP_REASONS } from '@/display/rules';
import type { Analysis, LinkDecision } from '@/services/types';
import type { DetailUi } from './useDetailUi';

export interface DetailActions {
  /** '탐지 내용 확인' — 원본 confirmFinding: setStatus(confirmed) + 토스트 '탐지 내용을 확인했습니다 · F-xx' */
  confirmFinding: (fid: string) => void;
  /** '확인 취소' — 원본 unconfirmFinding: setStatus(open) + 토스트 '확인을 취소했습니다 · F-xx' */
  unconfirmFinding: (fid: string) => void;
  /** '오탐으로 표시' — 모달 fp */
  markFalsePositive: (fid: string) => void;
  /** '오탐 취소' — 모달 restore */
  restoreFinding: (fid: string) => void;
  /** '분류 수정' — 모달 edit */
  reclassify: (fid: string) => void;
  /** '메모' · '메모 수정' — 모달 fmemo */
  editFindingMemo: (fid: string) => void;
  /** '해결로 표시' — 모달 resolve */
  resolveItem: (rid: string) => void;
  /** 검토사항 '다시 열기' — 원본 reopenItem: reopenItem + 토스트 */
  reopenItem: (rid: string) => void;
  /** '같은 사람·같은 건 맞음' · '연결 아님' — 모달 link */
  decideLink: (lid: string, decision: LinkDecision) => void;
  /** 검토 메모 '작성' · '수정' — 모달 memo */
  editMemo: () => void;
  /** 머리글 '검토 완료' — 모달 complete */
  completeReview: () => void;
  /** 머리글 '검토 다시 열기' — 모달 reopen */
  reopenReview: () => void;
  /** '다시 분석' · '실패 문서 다시 분석' · '이 문서 다시 분석' · '다시 시도' — 원본 retry(aid, docId): service.retry + 실패 토스트 */
  retry: (docId?: string) => void;
}

/** 상세 검토 동작 처리기 — T7 이 서비스 호출 · 모달 · 토스트를 붙인다 */
export function useDetailActions(a: Analysis, ui: DetailUi): DetailActions {
  const findFinding = (fid: string) => a.findings.find((f) => f.id === fid);
  return {
    confirmFinding: () => {
      // TODO(T7): service.setStatus(a.id, fid, 'confirmed') → 토스트
    },
    unconfirmFinding: () => {
      // TODO(T7): service.setStatus(a.id, fid, 'open') → 토스트
    },
    markFalsePositive: (fid) => ui.openModal({ type: 'fp', fid, reason: FP_REASONS[0], note: '', error: '' }),
    restoreFinding: (fid) => ui.openModal({ type: 'restore', fid, note: '', error: '' }),
    reclassify: (fid) => {
      const f = findFinding(fid);
      if (f) ui.openModal({ type: 'edit', fid, cat: f.cat, subject: f.subject, exposure: f.exposure, note: '', error: '' });
    },
    editFindingMemo: (fid) => ui.openModal({ type: 'fmemo', fid, note: findFinding(fid)?.memo || '', error: '' }),
    resolveItem: (rid) => ui.openModal({ type: 'resolve', rid, note: '', error: '' }),
    reopenItem: () => {
      // TODO(T7): service.reopenItem(a.id, rid) → 토스트 '검토사항을 다시 열었습니다 · R-xx'
    },
    decideLink: (lid, decision) => ui.openModal({ type: 'link', lid, decision, note: '', error: '' }),
    editMemo: () => ui.openModal({ type: 'memo', note: a.memo || '', error: '' }),
    completeReview: () => ui.openModal({ type: 'complete', note: '', error: '' }),
    reopenReview: () => ui.openModal({ type: 'reopen', note: '', error: '' }),
    retry: () => {
      // TODO(T7): service.retry(a.id, docId) → 실패 메시지면 토스트 '다시 분석했지만 실패했습니다 · …'(error)
    },
  };
}
