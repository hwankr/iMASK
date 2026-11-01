'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { VisuallyHidden } from '@/components/ui';
import type { StateId } from '@/services/analysis-service';
import { useDemoControls } from '@/services/react';

export interface PreparedResult {
  /** 준비한 상태 */
  stateId: StateId;
  /** 상세·보고서 상태면 열 분석 ID — prepare 가 돌려준 값을 그대로 쓴다(순번을 이어 쓰므로 고정 ID를 가정하지 않는다) */
  analysisId?: string;
}

/**
 * 데모 서비스를 그 상태로 맞춘 뒤에만 화면을 그린다(/dev/states 전용).
 * - useDemoControls() 는 서버 렌더와 하이드레이션 첫 렌더에서 null 이다 → 효과 안에서, 값이 있을 때 prepare 를 부른다.
 * - 준비가 끝나기 전(상태를 바꾼 직후 포함)에는 아무것도 그리지 않아 이전 상태의 화면이 잠깐 보이지 않는다.
 * - 효과가 정리되면(상태 이동 · 언마운트 · Strict Mode 재실행) 늦게 온 응답은 버린다.
 */
export function PreparedState({ stateId, children }: { stateId: StateId; children: (result: PreparedResult) => ReactNode }) {
  const demo = useDemoControls();
  const [ready, setReady] = useState<PreparedResult | null>(null);

  useEffect(() => {
    if (!demo) return;
    let alive = true;
    void demo.prepare(stateId).then((r) => {
      if (alive) setReady({ stateId, analysisId: r.analysisId });
    });
    return () => {
      alive = false;
    };
  }, [demo, stateId]);

  if (!ready || ready.stateId !== stateId) {
    return (
      <VisuallyHidden>
        <span role="status">상태를 준비하는 중입니다.</span>
      </VisuallyHidden>
    );
  }
  return <>{children(ready)}</>;
}
