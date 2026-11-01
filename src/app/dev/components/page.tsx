import type { Metadata } from 'next';
import { ComponentsBoard } from './ComponentsBoard';

export const metadata: Metadata = {
  title: '개발용 · 공통 컴포넌트',
  robots: { index: false, follow: false },
};

/** /dev/components — Components.dc.html 보드(구역 01~08)를 실제 컴포넌트로 다시 그린 개발용 페이지 */
export default function DevComponentsPage() {
  return <ComponentsBoard />;
}
