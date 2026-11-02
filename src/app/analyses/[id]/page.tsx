import type { Metadata } from 'next';
import { DetailScreen } from '@/components/detail/DetailScreen';
import { LiveDetailScreen } from '@/components/live/LiveDetailScreen';
import { SERVICE_MODE } from '@/services/mode';

export const metadata: Metadata = { title: '상세 검토' };

/**
 * /analyses/[id] 상세 검토. `<main>` 은 AppShell 이 그린다. Next 16: params 는 Promise.
 * 분석 ID 가 바뀌면 화면 상태를 새로 시작한다(key).
 * 실제 분석 모드(NEXT_PUBLIC_IMASK_SERVICE=api)면 진행 상태 · 결과 JSON 을 보여 주는 화면을 쓴다.
 */
export default async function DetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return SERVICE_MODE === 'api' ? <LiveDetailScreen key={id} id={id} /> : <DetailScreen key={id} id={id} />;
}
