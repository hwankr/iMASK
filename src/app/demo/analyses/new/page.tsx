import type { Metadata } from 'next';
import { UploadScreen } from '@/components/upload/UploadScreen';

export const metadata: Metadata = { title: '새 분석' };

/**
 * /demo/analyses/new 새 분석(데모) — 실제 모드 빌드에서도 `/demo` 아래는 데모 서비스다(주소 기준 모드).
 * 실제 분석 화면을 거치지 않고 데모 화면을 바로 그린다. `?sample=1` 이면 샘플 문서 3개를 담아 시작한다.
 */
export default function DemoNewAnalysisPage() {
  return <UploadScreen sampleFromQuery />;
}
