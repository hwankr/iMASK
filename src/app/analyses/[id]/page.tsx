import type { Metadata } from 'next';
import { DetailScreen } from '@/components/detail/DetailScreen';

export const metadata: Metadata = { title: '상세 검토' };

/**
 * /analyses/[id] 상세 검토. `<main>` 은 AppShell 이 그린다. Next 16: params 는 Promise.
 * 분석 ID 가 바뀌면 화면 상태를 새로 시작한다(key).
 */
export default async function DetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <DetailScreen key={id} id={id} />;
}
