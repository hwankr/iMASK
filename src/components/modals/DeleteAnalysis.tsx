'use client';

/* ==========================================================================
   분석 건 삭제 — 확인 창(공통 Modal) + 처리(useDeleteAnalysis). 목록 표 · 상세 머리글(데모 · 실제) · 실제 분석 진행 · 실패
   화면이 같이 쓴다(문구는 analysisActionModel 한 곳).
   - ask({ id, returnFocus }) 로 창을 연다. 바닥 버튼 '취소' · '삭제'(위험 모양, 열릴 때 '취소'에 포커스).
   - '삭제'를 누르면 service.deleteAnalysis(id) 한 번 — 지우는 동안 삭제 버튼 돌림 표시, 창을 닫을 수 없다(Esc · 배경 · 닫기 ·
     취소 모두 막힘). 두 번 눌러도 요청은 한 번(busy 참조로 막는다).
   - 성공: 창을 닫고 토스트 '분석을 지웠습니다.' → onRemoved(id, 'deleted')(상세는 목록으로, 목록은 그 행을 바로 뺀다).
     실패: 창을 닫고 오류 토스트 — 404 는 '이미 지워진 분석입니다.' → onRemoved(id, 'gone')(서비스가 알려 목록 · 상세가 다시 불러온다),
     그 밖은 '분석을 지우지 못했습니다. 잠시 후 다시 시도해 주세요.'.
   - leaving = 지우는 중 · 지운 뒤 떠나는 분석 id(실패하면 null) — 상세가 그동안 '찾을 수 없음' 화면을 그리지 않게 쓴다.
   - 창이 닫힐 때 포커스는 연 버튼으로 돌아가고, 그 버튼이 사라졌으면(지운 행) returnFocus 가 고른 자리로 간다(공통 Modal).
   ========================================================================== */

import { useCallback, useRef, useState, type ReactNode } from 'react';
import { Modal, useToast } from '@/components/ui';
import { useService } from '@/services/react';
import { DELETE_BODY, DELETE_CANCEL, DELETE_LABEL, DELETE_TITLE, DELETED_TEXT, deleteFailedText, isGoneError } from './analysisActionModel';

/** 지우기 요청 — 창을 연 분석과, 닫힐 때 연 버튼이 사라졌으면 대신 포커스할 자리 */
export interface DeleteRequest {
  id: string;
  returnFocus?: () => HTMLElement | null;
}

/** 지운 결과 — deleted 지움 / gone 이미 없었음(404) */
export type DeleteOutcome = 'deleted' | 'gone';

export interface DeleteAnalysisFlow {
  /** 확인 창을 연다(지우는 중이면 무시) */
  ask: (request: DeleteRequest) => void;
  /** 확인 창 — 화면에 한 번 그린다 */
  modal: ReactNode;
  /** 지우는 중 · 지운 뒤 떠나는 분석 id(실패하면 null) */
  leaving: string | null;
}

export interface UseDeleteAnalysisOptions {
  /** 지운 뒤(성공 · 404) */
  onRemoved?: (id: string, outcome: DeleteOutcome) => void;
}

/** 분석 건 삭제 처리 — 확인 창 · 요청 한 번 · 토스트 */
export function useDeleteAnalysis({ onRemoved }: UseDeleteAnalysisOptions = {}): DeleteAnalysisFlow {
  const service = useService();
  const toast = useToast();
  const [target, setTarget] = useState<DeleteRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const [leaving, setLeaving] = useState<string | null>(null);
  const busyRef = useRef(false);

  const ask = useCallback((request: DeleteRequest) => {
    if (busyRef.current) return;
    setTarget(request);
  }, []);

  const close = () => {
    if (!busyRef.current) setTarget(null);
  };

  const confirm = () => {
    if (!service || !target || busyRef.current) return;
    const id = target.id;
    busyRef.current = true;
    setBusy(true);
    setLeaving(id);
    void service.deleteAnalysis(id).then(
      () => {
        busyRef.current = false;
        setBusy(false);
        setTarget(null);
        toast(DELETED_TEXT);
        onRemoved?.(id, 'deleted');
      },
      (err: unknown) => {
        busyRef.current = false;
        setBusy(false);
        setTarget(null);
        setLeaving(null);
        toast(deleteFailedText(err), { kind: 'error' });
        if (isGoneError(err)) onRemoved?.(id, 'gone');
      },
    );
  };

  const modal = (
    <Modal
      open={target !== null}
      onClose={close}
      title={DELETE_TITLE}
      subtitle={DELETE_BODY}
      width="sm"
      dismissible={!busy}
      returnFocus={target?.returnFocus}
      buttons={[
        { label: DELETE_CANCEL, onClick: close, variant: 'ghost', disabled: busy, autoFocus: true },
        { label: DELETE_LABEL, onClick: confirm, variant: 'danger', loading: busy },
      ]}
    />
  );

  return { ask, modal, leaving };
}
