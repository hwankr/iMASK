'use client';

/* ==========================================================================
   상세 검토 동작 — 원본 Main.dc.html 상세 동작(1801–1807: retry · confirmFinding · unconfirmFinding · reopenItem)과
   화면 모델의 행동 부분(findingVM fp · restore · edit · memoAct, itemVM resolve · reopen · retry, linkVM yes · no,
   detailVM complete · reopen · editMemo · retryAll).
   - 모달을 여는 동작은 모달 자리(DetailUiState.modal)에 원본 openModal 과 같은 값을 넣는다.
     모달을 그리고 저장하는 것은 ReviewModal(src/components/modals) 이 한다.
   - 바로 바꾸는 동작(확인 · 확인 취소 · 검토사항 다시 열기 · 다시 분석)은 서비스를 부르고 토스트를 띄운다.
     실패하면 SAVE_FAILED, 분석이 이미 지워졌으면(404) '이미 지워진 분석입니다.'(서비스가 알려 화면이 다시 불러온다).
     다시 분석은 목록과 같은 처리(useRetryAnalysis — 결과 토스트 · 요청 한 번)를 쓴다.
   - 화면은 서비스 변경 알림으로 새 데이터를 받아 다시 그려진다(헤더 · 목록 숫자도 같은 서비스에서 온다).
   - 위험등급 · 최초 탐지 결과는 화면에서 바꾸거나 계산하지 않는다(서비스가 지킨다).
   ========================================================================== */

import { FP_REASONS } from '@/display/rules';
import { useToast } from '@/components/ui';
import { GONE_TEXT, isGoneError } from '@/components/modals/analysisActionModel';
import { SAVE_FAILED, confirmedText, itemReopenedText, unconfirmedText } from '@/components/modals/reviewModalModel';
import { useRetryAnalysis } from '@/components/modals/useRetryAnalysis';
import type { AnalysisService } from '@/services/analysis-service';
import { useService } from '@/services/react';
import type { Analysis, LinkDecision } from '@/services/types';
import { rememberFocus, rescueFocus } from './focusRescue';
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
  /**
   * '다시 분석' · '실패 문서 다시 분석' · '이 문서 다시 분석' · '다시 시도' — 원본 retry(aid, docId).
   * 서비스가 곧바로 '다시 분석하는 중'(retrying)으로 바꾸고, 끝나면 실패 이유를 돌려준다 → 오류 토스트.
   */
  retry: (docId?: string) => void;
}

/** 상세 검토 동작 처리기 */
export function useDetailActions(a: Analysis, ui: DetailUi): DetailActions {
  const service = useService();
  const toast = useToast();
  const runRetry = useRetryAnalysis();
  const findFinding = (fid: string) => a.findings.find((f) => f.id === fid);

  /** 바로 바꾸는 동작 — 서비스 호출 뒤 토스트. 누른 버튼이 바뀌어 없어지면 같은 자리의 새 버튼으로 포커스 */
  const direct = (call: (svc: AnalysisService) => Promise<unknown>, text: string) => {
    if (!service) return;
    const spot = rememberFocus();
    void call(service).then(
      () => {
        toast(text);
        rescueFocus(spot);
      },
      (err: unknown) => toast(isGoneError(err) ? GONE_TEXT : SAVE_FAILED, { kind: 'error' }),
    );
  };

  return {
    confirmFinding: (fid) => direct((svc) => svc.setStatus(a.id, fid, 'confirmed'), confirmedText(fid)),
    unconfirmFinding: (fid) => direct((svc) => svc.setStatus(a.id, fid, 'open'), unconfirmedText(fid)),
    markFalsePositive: (fid) => ui.openModal({ type: 'fp', fid, reason: FP_REASONS[0], note: '', error: '' }),
    restoreFinding: (fid) => ui.openModal({ type: 'restore', fid, note: '', error: '' }),
    reclassify: (fid) => {
      const f = findFinding(fid);
      if (f) ui.openModal({ type: 'edit', fid, cat: f.cat, subject: f.subject, exposure: f.exposure, note: '', error: '' });
    },
    editFindingMemo: (fid) => ui.openModal({ type: 'fmemo', fid, note: findFinding(fid)?.memo || '', error: '' }),
    resolveItem: (rid) => ui.openModal({ type: 'resolve', rid, note: '', error: '' }),
    reopenItem: (rid) => direct((svc) => svc.reopenItem(a.id, rid), itemReopenedText(rid)),
    decideLink: (lid, decision) => ui.openModal({ type: 'link', lid, decision, note: '', error: '' }),
    editMemo: () => ui.openModal({ type: 'memo', note: a.memo || '', error: '' }),
    completeReview: () => ui.openModal({ type: 'complete', note: '', error: '' }),
    reopenReview: () => ui.openModal({ type: 'reopen', note: '', error: '' }),
    retry: (docId) => {
      if (!service) return;
      /* 원본: svc.retry(aid, docId).then(r => r.message 이면 오류 토스트) — 화면을 떠나도 토스트는 뜬다(useRetryAnalysis).
         다시 분석하는 동안 누른 버튼은 막히므로(포커스가 빠질 수 있음) 끝나면 그 버튼으로 포커스를 돌려준다. */
      const spot = rememberFocus();
      void runRetry(a.id, docId).then(() => rescueFocus(spot));
    },
  };
}

const noop = () => {};

/**
 * 검토 기록을 불러오지 못한 실제 분석(raw.reviewable false) 상세의 동작 — 모두 아무것도 하지 않는다
 * (서비스 호출 · 모달 · 토스트 없음). 화면은 그 버튼을 막는다.
 */
export const READ_ONLY_ACTIONS: DetailActions = {
  confirmFinding: noop,
  unconfirmFinding: noop,
  markFalsePositive: noop,
  restoreFinding: noop,
  reclassify: noop,
  editFindingMemo: noop,
  resolveItem: noop,
  reopenItem: noop,
  decideLink: noop,
  editMemo: noop,
  completeReview: noop,
  reopenReview: noop,
  retry: noop,
};
