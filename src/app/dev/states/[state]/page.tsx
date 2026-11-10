import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { devPagesEnabled } from '@/dev/devPages';
import { DEV_STATES, findState } from '@/dev/states';
import { StatePreview } from '@/dev/StatePreview';

// 운영 빌드(개발용 경로가 닫힘)에서는 개발용 제목을 내보내지 않는다 — 404 화면과 같은 제목
export const metadata: Metadata = devPagesEnabled()
  ? { title: '개발용 · 상태 미리보기', robots: { index: false, follow: false } }
  : { title: '페이지를 찾을 수 없습니다' };

/** 상태 25개(휴대폰 전용 포함)를 미리 만든다(개발용 경로가 닫힌 운영 빌드는 미리 만들지 않는다). 목록에 없는 id 는 요청 때 notFound(). */
export function generateStaticParams() {
  return devPagesEnabled() ? DEV_STATES.map((s) => ({ state: s.id })) : [];
}

export default async function DevStatePage({ params }: { params: Promise<{ state: string }> }) {
  if (!devPagesEnabled()) notFound();
  const { state } = await params;
  const found = findState(state);
  if (!found) notFound();
  return <StatePreview stateId={found.id} />;
}
