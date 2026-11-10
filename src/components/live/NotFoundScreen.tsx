'use client';

/* ==========================================================================
   찾을 수 없음 화면 — 없는 분석('분석 건을 찾을 수 없습니다' — LiveDetailScreen)과 없는 주소(app/not-found.tsx)가 같이 쓴다.
   제목 + (있으면) 한 줄 + 버튼('새 분석'은 고를 때만, '목록으로'는 늘 — 지금 모드의 목록: `/demo` 아래면 `/demo`).
   ========================================================================== */

import { Button, cx } from '@/components/ui';
import { listHref, newAnalysisHref } from '@/lib/routes';
import { useRouteBase } from '@/services/react';
import styles from './LiveDetailScreen.module.css';

export function NotFoundScreen({ title, lead, withNew = false }: { title: string; lead?: string; withNew?: boolean }) {
  const base = useRouteBase();
  return (
    <div className={styles.screen}>
      <div className={cx(styles.page, styles.narrow)}>
        <h1 className={styles.title}>{title}</h1>
        {lead ? <p className={styles.lead}>{lead}</p> : null}
        <div className={styles.actions}>
          {withNew ? (
            <Button href={newAnalysisHref(base)} variant="primary" icon="dg-i-plus">
              새 분석
            </Button>
          ) : null}
          <Button href={listHref(base)} variant="secondary">
            목록으로
          </Button>
        </div>
      </div>
    </div>
  );
}
