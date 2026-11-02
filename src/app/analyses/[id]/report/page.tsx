import type { Metadata } from 'next';
import { LiveReportNotice } from '@/components/live/LiveReportNotice';
import { ReportScreen } from '@/components/report/ReportScreen';
import { SERVICE_MODE } from '@/services/mode';

export const metadata: Metadata = { title: '검토 결과 보고서' };

/**
 * /analyses/[id]/report 검토 결과 보고서. `<main>` 은 AppShell 이 그린다. Next 16: params 는 Promise.
 * 분석 ID 가 바뀌면 화면 상태(내보내기 모달 등)를 새로 시작한다(key).
 * 실제 분석 모드(NEXT_PUBLIC_IMASK_SERVICE=api)에는 보고서가 아직 없어 짧은 안내와 상세로 가는 링크만 둔다.
 */
export default async function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return SERVICE_MODE === 'api' ? <LiveReportNotice id={id} /> : <ReportScreen key={id} id={id} />;
}
