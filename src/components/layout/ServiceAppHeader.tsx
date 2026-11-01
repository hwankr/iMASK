'use client';

import type { ReviewStatus } from '@/display/rules';
import { useAnalyses } from '@/services/react';
import { AppHeader, type AppHeaderProps } from './AppHeader';

/** 헤더 '검토 필요' 배지가 세는 검토 상태(② RSTATUS 의 키) — 프로토타입 2566줄 `a.review === 'needed'` */
const REVIEW_NEEDED: ReviewStatus = 'needed';

/**
 * 헤더 + '검토 필요' 건수 연결 — 서비스의 분석 목록(`useAnalyses()`)에서 검토 상태가 '검토 필요'인 건수를 센다.
 * - 서버 렌더와 하이드레이션 첫 렌더에는 서비스가 없어 '불러오는 중'이다 → 숫자 자리만 비워 둔다(null).
 *   서버와 첫 클라이언트 렌더가 같은 모양이라 하이드레이션 불일치가 없다.
 * - 서비스 변경 알림(검토 완료·다시 열기·새 분석 등)이 오면 useAnalyses 가 다시 불러와 숫자가 바로 바뀐다.
 * - 다시 불러오는 동안·실패했을 때는 마지막으로 받은 숫자를 그대로 보여 준다.
 */
export function ServiceAppHeader(props: Omit<AppHeaderProps, 'reviewNeededCount'>) {
  const { data } = useAnalyses();
  const count = data ? data.filter((a) => a.review === REVIEW_NEEDED).length : null;
  return <AppHeader {...props} reviewNeededCount={count} />;
}
