'use client';

import { Button } from '@/components/ui';
import { detailHref } from '@/lib/routes';
import { useRouteBase } from '@/services/react';
import styles from './LiveDetailScreen.module.css';

/** 실제 분석 보고서 안내 — 대기 · 분석 중 */
export const REPORT_WAITING_TITLE = '분석이 끝나면 보고서를 볼 수 있습니다';
/** 실제 분석 보고서 안내 — 실패 · 일부 실패 · 옛 형식(공통 계약 결과가 아님) */
export const REPORT_UNAVAILABLE_TITLE = '보고서를 만들 수 없는 분석입니다';

export type LiveReportNoticeKind = 'waiting' | 'unavailable';

/**
 * /analyses/[id]/report — 보고서를 그릴 수 없는 실제 분석(reportGate 'waiting' · 'unavailable')의 짧은 안내.
 * 제목과 상세로 가는 길만 둔다(설명 문단 없음 · 주기 조회 없음).
 * 상세 주소는 기준 경로 함수(useRouteBase — 실제 분석은 `/demo` 밖에서만 그려져 기준 '')로 만든다.
 */
export function LiveReportNotice({ id, kind }: { id: string; kind: LiveReportNoticeKind }) {
  const base = useRouteBase();
  return (
    <div className={styles.screen}>
      <div className={`${styles.page} ${styles.narrow}`}>
        <h1 className={styles.title}>{kind === 'waiting' ? REPORT_WAITING_TITLE : REPORT_UNAVAILABLE_TITLE}</h1>
        <div className={styles.actions}>
          <Button href={detailHref(base, id)} variant="primary">
            상세로 가기
          </Button>
        </div>
      </div>
    </div>
  );
}
