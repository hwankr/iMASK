import { ListScreen } from '@/components/list/ListScreen';

/**
 * /demo 분석 목록(데모) — 실제 모드 빌드에서도 `/demo` 아래는 데모 서비스다(주소 기준 모드, src/services/mode.ts).
 * 화면은 `/` 와 같은 목록이고, 필터는 URL 검색 파라미터(q · risk · status · review · sort)와 이어지며
 * 이동 주소는 모두 `/demo` 기준이다(목록 기억도 `/demo` 따로).
 */
export default function DemoListPage() {
  return <ListScreen />;
}
