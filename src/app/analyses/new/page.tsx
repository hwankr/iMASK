import type { Metadata } from 'next';
import { UploadScreen } from '@/components/upload/UploadScreen';

export const metadata: Metadata = { title: '새 분석' };

/**
 * /analyses/new 새 분석. `<main>` 은 AppShell 이 그린다.
 * `?sample=1` 이면 샘플 문서 3개를 담아 시작한다(상세 화면의 '샘플로 체험하기').
 */
export default function NewAnalysisPage() {
  return <UploadScreen sampleFromQuery />;
}
