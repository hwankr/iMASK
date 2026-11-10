import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { devPagesEnabled } from '@/dev/devPages';
import { ComponentsBoard } from './ComponentsBoard';

// 운영 빌드(개발용 경로가 닫힘)에서는 개발용 제목을 내보내지 않는다 — 404 화면과 같은 제목
export const metadata: Metadata = devPagesEnabled()
  ? { title: '개발용 · 공통 컴포넌트', robots: { index: false, follow: false } }
  : { title: '페이지를 찾을 수 없습니다' };

/** /dev/components — Components.dc.html 보드(구역 01~08)를 실제 컴포넌트로 다시 그린 개발용 페이지 */
export default function DevComponentsPage() {
  if (!devPagesEnabled()) notFound();
  return <ComponentsBoard />;
}
