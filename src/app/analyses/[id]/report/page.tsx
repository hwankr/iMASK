import type { Metadata } from 'next';
import { ReportScreen } from '@/components/report/ReportScreen';

export const metadata: Metadata = { title: '검토 결과 보고서' };

/**
 * /analyses/[id]/report 검토 결과 보고서. `<main>` 은 AppShell 이 그린다. Next 16: params 는 Promise.
 * 분석 ID 가 바뀌면 화면 상태(내보내기 모달 등)를 새로 시작한다(key).
 * 두 모드(주소 기준 서비스 모드 — 이 주소는 빌드 모드) 모두 같은 보고서 화면이다. 실제 분석은 화면이 불러온 분석으로
 * 가른다(reportGate — 보고서 대상만 본문, 대기 · 분석 중 · 실패 · 옛 형식은 짧은 안내와 상세로 가는 링크).
 */
export default async function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ReportScreen key={id} id={id} />;
}
