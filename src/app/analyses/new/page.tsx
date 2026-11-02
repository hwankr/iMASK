import type { Metadata } from 'next';
import { LiveUploadScreen } from '@/components/live/LiveUploadScreen';
import { UploadScreen } from '@/components/upload/UploadScreen';
import { SERVICE_MODE } from '@/services/mode';

export const metadata: Metadata = { title: '새 분석' };

/**
 * /analyses/new 새 분석. `<main>` 은 AppShell 이 그린다.
 * - 데모(기본): `?sample=1` 이면 샘플 문서 3개를 담아 시작한다(상세 화면의 '샘플로 체험하기').
 * - 실제 분석(NEXT_PUBLIC_IMASK_SERVICE=api): 접근 코드 · 파일 1개로 Upstage 워크플로우 분석을 시작한다.
 */
export default function NewAnalysisPage() {
  return SERVICE_MODE === 'api' ? <LiveUploadScreen /> : <UploadScreen sampleFromQuery />;
}
