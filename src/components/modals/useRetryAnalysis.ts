'use client';

/* ==========================================================================
   다시 분석 처리 — 목록 '재시도' · 오류 확인 창 '다시 시도' · 실제 분석 실패 띠 '다시 분석'(· 데모 상세의 다시 분석)이 같이 쓴다.
   - service.retry(id, docId) 를 부르고 결과 토스트를 띄운다(문구 고르기는 analysisActionModel retryToast).
   - 같은 분석의 요청이 끝나기 전에 다시 부르면 요청하지 않고 null 을 돌려준다(두 번 눌러도 요청은 한 번).
     버튼을 막아 보이는 것은 화면이 한다(목록은 '재시도 중…', 실패 띠는 버튼 막힘).
   - 결과(RetryResult)를 돌려준다 — 실제 분석에서 started 면 화면이 오류 확인 창을 닫는다.
   ========================================================================== */

import { useCallback, useRef } from 'react';
import { useToast } from '@/components/ui';
import type { RetryResult } from '@/services/analysis-service';
import { useService } from '@/services/react';
import { retryToast } from './analysisActionModel';

/** 다시 분석 하나 — 이미 요청 중이거나 서비스가 없으면 null */
export type RunRetry = (id: string, docId?: string) => Promise<RetryResult | null>;

export function useRetryAnalysis(): RunRetry {
  const service = useService();
  const toast = useToast();
  const running = useRef(new Set<string>());

  return useCallback<RunRetry>(
    async (id, docId) => {
      if (!service || running.current.has(id)) return null;
      running.current.add(id);
      let r: RetryResult;
      try {
        r = await service.retry(id, docId);
      } catch {
        return null; // 서비스는 거절하지 않는다(만일을 위해 — 처리되지 않은 거절이 되지 않게)
      } finally {
        running.current.delete(id);
      }
      const t = retryToast(r);
      if (t) toast(t.text, t.kind === 'error' ? { kind: 'error' } : {});
      return r;
    },
    [service, toast],
  );
}
