import type { Metadata } from 'next';
import { DetailScreen } from '@/components/detail/DetailScreen';

export const metadata: Metadata = { title: '상세 검토' };

/**
 * /demo/analyses/[id] 상세 검토(데모) — 실제 모드 빌드에서도 `/demo` 아래는 데모 서비스다(주소 기준 모드).
 * 실제 분석 화면을 거치지 않고 데모 화면을 바로 그린다. Next 16: params 는 Promise. 분석 ID 가 바뀌면 화면 상태를 새로 시작한다(key).
 */
export default async function DemoDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <DetailScreen key={id} id={id} />;
}
