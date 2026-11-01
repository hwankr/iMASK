import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { DEV_STATES, findState } from '@/dev/states';
import { StatePreview } from '@/dev/StatePreview';

export const metadata: Metadata = {
  title: '개발용 · 상태 미리보기',
  robots: { index: false, follow: false },
};

/** 상태 25개(휴대폰 전용 포함)를 미리 만든다. 목록에 없는 id 는 요청 때 notFound(). */
export function generateStaticParams() {
  return DEV_STATES.map((s) => ({ state: s.id }));
}

export default async function DevStatePage({ params }: { params: Promise<{ state: string }> }) {
  const { state } = await params;
  const found = findState(state);
  if (!found) notFound();
  return <StatePreview stateId={found.id} />;
}
