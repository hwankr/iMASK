import type { Metadata } from 'next';
import { NotFoundScreen } from '@/components/live/NotFoundScreen';

export const metadata: Metadata = {
  title: '페이지를 찾을 수 없습니다',
};

/**
 * 없는 주소(`/없는주소` · `/analyses/없는/주소` · `/demo/없는주소` · 운영 빌드의 `/dev/**`) — 응답 코드 404.
 * 없는 분석 화면과 같은 모양(NotFoundScreen): 제목 + '목록으로'(지금 모드의 목록 — `/demo` 아래면 `/demo`). 설명 문장은 없다.
 * `/demo` 아래는 src/app/demo/[...rest]/page.tsx 가 요청 때 notFound() 를 불러 이 화면을 그린다(헤더 모드가 주소와 맞게 — 그 파일의 주석).
 */
export default function NotFound() {
  return <NotFoundScreen title="페이지를 찾을 수 없습니다" />;
}
