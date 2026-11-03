import type { Metadata } from 'next';
import { ByServiceMode } from '@/components/layout/ByServiceMode';
import { LiveUploadScreen } from '@/components/live/LiveUploadScreen';
import { UploadScreen } from '@/components/upload/UploadScreen';

export const metadata: Metadata = { title: '새 분석' };

/**
 * /analyses/new 새 분석. `<main>` 은 AppShell 이 그린다. 화면은 주소 기준 서비스 모드(useServiceMode)로 고른다 —
 * 이 주소는 `/demo` 밖이라 빌드 모드를 따른다.
 * - 데모(기본): `?sample=1` 이면 샘플 문서 3개를 담아 시작한다(상세 화면의 '샘플로 체험하기').
 * - 실제 분석(실제 모드 빌드): 파일 1개로 Upstage 워크플로우 분석을 시작한다.
 */
export default function NewAnalysisPage() {
  return <ByServiceMode demo={<UploadScreen sampleFromQuery />} api={<LiveUploadScreen />} />;
}
