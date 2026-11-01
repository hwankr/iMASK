import type { Metadata } from 'next';
import { ReportScreen } from '@/components/report/ReportScreen';

export const metadata: Metadata = { title: '검토 결과 보고서' };

/**
 * /analyses/[id]/report 검토 결과 보고서. `<main>` 은 AppShell 이 그린다. Next 16: params 는 Promise.
 * 분석 ID 가 바뀌면 화면 상태(내보내기 모달 등)를 새로 시작한다(key).
 */
export default async function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ReportScreen key={id} id={id} />;
}
