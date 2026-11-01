'use client';

import { useEffect, useState } from 'react';
import { VisuallyHidden } from '@/components/ui';
import { UploadScreen } from '@/components/upload/UploadScreen';
import type { UploadState } from '@/components/upload/uploadModel';
import { useService } from '@/services/react';
import { uploadScenario, type UploadStateId } from './uploadScenarios';

/**
 * 업로드 상태 미리보기 — 시작 조건(샘플 파일은 서비스에서)을 만든 뒤 새 분석 화면을 그 상태로 연다.
 * PreparedState 가 데모 서비스를 먼저 그 상태로 맞춘다.
 */
export function UploadStatePreview({ stateId }: { stateId: UploadStateId }) {
  const service = useService();
  const [ready, setReady] = useState<{ stateId: UploadStateId; initial: Partial<UploadState> } | null>(null);

  useEffect(() => {
    if (!service) return;
    let alive = true;
    void uploadScenario(stateId, service).then((initial) => {
      if (alive) setReady({ stateId, initial });
    });
    return () => {
      alive = false;
    };
  }, [service, stateId]);

  if (!ready || ready.stateId !== stateId) {
    return (
      <VisuallyHidden>
        <span role="status">상태를 준비하는 중입니다.</span>
      </VisuallyHidden>
    );
  }
  return <UploadScreen initial={ready.initial} />;
}
