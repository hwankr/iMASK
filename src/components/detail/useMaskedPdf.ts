'use client';

/* ==========================================================================
   '가린 PDF 내려받기' — 실제 분석 상세(원문 뷰어 '마스킹 미리보기' 공지의 버튼).
   - 누른 순간의 선택(maskPick)과 이미 받아 연 원본 파일로 가림 계획을 만들고(maskPdf.ts), 쪽마다 그림으로 그려 칠한 그림 PDF 를
     만든다(maskPdfBuild.ts — 누를 때 동적 import, 첫 화면 묶음에 넣지 않음). 원본 파일 · 서버 데이터는 바꾸지 않는다.
   - 만드는 동안 다시 눌러도 두 번 만들지 않는다(진행 중 작업이 있으면 무시 · 버튼은 loading).
   - 화면을 떠나거나(언마운트) 분석 · 원본 파일이 바뀌면 만들던 것을 멈추고(그리기 cancel) 내려받지 않는다 — 토스트도 없음.
   - 끝나면 브라우저 다운로드 + 토스트: 모두 가림 · 위치 없는 n건은 못 가림(error) · 만들기 실패(error) · 다운로드 넘기기 실패(error).
     문구에 원문 값 · 기술적 오류 내용을 담지 않는다(콘솔에도 남기지 않음).
   - 검토 이력(내보내기 기록)에는 남기지 않는다.
   ========================================================================== */

import { useEffect, useRef, useState } from 'react';
import { useToast } from '@/components/ui';
import { downloadFile } from '@/lib/download';
import type { Analysis } from '@/services/types';
import type { DetailUiState } from './detailState';
import type { LiveFileState } from './liveFile';
import { MASK_PDF_DONE, MASK_PDF_FAILED, maskPdfMissedText, maskPdfName, maskSourceOf } from './maskPdf';

export interface MaskedPdfHandle {
  /** 원본 파일이 준비됐다(받는 중 · 실패 · 쪽 수가 양의 정수가 아닌 PDF 면 false — 버튼을 막는다) */
  ready: boolean;
  /** 만드는 중 */
  busy: boolean;
  /** 만들어 내려받는다(만드는 중 · 준비 전이면 아무것도 하지 않음) */
  run: () => void;
}

/**
 * file = 실제 분석 원본 파일 상태(데모는 null — 버튼이 없다).
 */
export function useMaskedPdf(a: Analysis, maskPick: DetailUiState['maskPick'], file: LiveFileState | null): MaskedPdfHandle {
  const toast = useToast();
  const src = maskSourceOf(file);
  /** 이 원본 파일을 알아보는 값(PDF 문서 · 이미지 주소) — 바뀌면 만들던 것을 멈춘다 */
  const fileKey: unknown = src ? (src.kind === 'pdf' ? src.pdf : src.url) : null;
  /** 만드는 중인 작업 — 어느 분석 · 파일의 것인지 함께 둔다(바뀐 뒤에는 busy 로 보지 않음) */
  const [working, setWorking] = useState<{ id: string; file: unknown } | null>(null);
  const job = useRef<{ cancel: () => void } | null>(null);

  // 언마운트 · 분석 바뀜 · 원본 파일 바뀜 — 만들던 것을 멈춘다(내려받지 않음)
  useEffect(
    () => () => {
      job.current?.cancel();
      job.current = null;
    },
    [a.id, fileKey],
  );

  const run = () => {
    if (job.current || !src) return;
    // 누른 순간의 선택 · 분석 · 파일(snapshot) — 만드는 동안 바뀌어도 이 값으로 만든다
    const snap = { id: a.id, code: a.code, docs: a.docs, findings: a.findings, pick: maskPick, src, fileKey };
    let cancelled = false;
    let inner: { cancel: () => void } | null = null;
    const mine = {
      cancel: () => {
        cancelled = true;
        inner?.cancel();
      },
    };
    job.current = mine;
    setWorking({ id: snap.id, file: snap.fileKey });

    import('./maskPdfBuild')
      .then((m) => {
        if (cancelled) return null;
        const pageCount = snap.src.kind === 'pdf' ? snap.src.pageCount : 1;
        const plan = m.maskPlan({ docs: snap.docs, findings: snap.findings }, snap.pick, pageCount);
        const built = m.buildMaskedPdf(snap.src, plan);
        inner = built;
        return built.promise;
      })
      .then(
        (made) => {
          if (cancelled || !made) return;
          const res = downloadFile({ name: maskPdfName(snap.code), mime: 'application/pdf', data: made.bytes });
          if (res.state === 'failed') toast(res.message, { kind: 'error' });
          else if (made.missed > 0) toast(maskPdfMissedText(made.missed), { kind: 'error' });
          else toast(MASK_PDF_DONE);
        },
        () => {
          if (!cancelled) toast(MASK_PDF_FAILED, { kind: 'error' });
        },
      )
      .finally(() => {
        if (job.current === mine) job.current = null;
        setWorking((w) => (w && w.id === snap.id && w.file === snap.fileKey ? null : w));
      });
  };

  const busy = !!working && working.id === a.id && working.file === fileKey && fileKey !== null;
  return { ready: !!src, busy, run };
}
