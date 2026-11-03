import type { Metadata } from 'next';
import { DetailScreen } from '@/components/detail/DetailScreen';
import { ByServiceMode } from '@/components/layout/ByServiceMode';
import { LiveDetailScreen } from '@/components/live/LiveDetailScreen';

export const metadata: Metadata = { title: '상세 검토' };

/**
 * /analyses/[id] 상세 검토. `<main>` 은 AppShell 이 그린다. Next 16: params 는 Promise.
 * 분석 ID 가 바뀌면 화면 상태를 새로 시작한다(key).
 * 화면은 주소 기준 서비스 모드(useServiceMode — 이 주소는 빌드 모드)로 고른다. 실제 분석 모드(실제 모드 빌드)면
 * 진행 상태 · 결과를 보여 주는 화면을 쓴다.
 */
export default async function DetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ByServiceMode demo={<DetailScreen key={id} id={id} />} api={<LiveDetailScreen key={id} id={id} />} />;
}
