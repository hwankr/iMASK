import type { Metadata } from 'next';
import { notFound } from 'next/navigation';

/** 없는 주소 화면(app/not-found.tsx)과 같은 제목 */
export const metadata: Metadata = { title: '페이지를 찾을 수 없습니다' };

/**
 * /demo 아래의 없는 주소(예: /demo/x/y) — 요청 때 이 경로에서 notFound() 를 불러 404 를 낸다.
 * - 왜 필요한가: 이 페이지가 없으면 Next 는 미리 만든 /_not-found HTML 을 내보낸다. 그 HTML 의 헤더는 빌드 때 `/demo` 밖
 *   경로로 그려져 있어(실제 모드 빌드면 '실제 분석' 배지 · `/` 링크 · 데모 링크) 브라우저 경로(`/demo/…` → 데모)와 어긋나고,
 *   하이드레이션 오류(React #418)가 난 뒤에야 클라이언트가 데모 헤더로 다시 그렸다.
 * - 지금 보장하는 것: 응답은 HTTP 404 이고, 서버 HTML 에는 헤더가 없다. 헤더는 클라이언트가 현재 경로로 그리므로
 *   하이드레이션 뒤 '데모 데이터' 배지 · `/demo` 기준 링크이며 하이드레이션 불일치 · 앱 오류가 없다.
 *   404 의 서버 HTML 에 헤더까지 그리는 것은 보장하지 않는다.
 */
export default function DemoNotFoundPage() {
  notFound();
}
