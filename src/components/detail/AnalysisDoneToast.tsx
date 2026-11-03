'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useToast } from '@/components/ui';
import { detailHref } from '@/lib/routes';
import type { ServiceEvent } from '@/services/analysis-service';
import { useRouteBase, useServiceEvent } from '@/services/react';

/** 분석 완료 토스트 문구(원본 onServiceEvent 1604줄) */
export function analysisDoneText(ev: ServiceEvent): string {
  return '분석이 끝났습니다 · ' + ev.name + ' — 탐지 ' + ev.findings + '건, 검토사항 ' + ev.items + '건';
}

/**
 * 분석 완료 알림 — 서비스의 done 이벤트가 오면 어느 화면에 있든 토스트를 띄운다.
 * 그 분석의 상세 화면이 아니면 '결과 보기'(→ 그 상세, 지금 기준 경로 — `/demo` 아래면 `/demo/analyses/…`) 행동을 붙인다.
 * AppShell 이 한 번 그린다(구독도 한 번 — 주소 기준 서비스가 바뀌면 새 서비스를 구독한다).
 */
export function AnalysisDoneToast() {
  const toast = useToast();
  const router = useRouter();
  const pathname = usePathname();
  const base = useRouteBase();

  useServiceEvent((ev) => {
    if (ev.type !== 'done') return;
    const href = detailHref(base, ev.id);
    const here = pathname === href;
    toast(analysisDoneText(ev), here ? {} : { action: { label: '결과 보기', onClick: () => router.push(href) } });
  });

  return null;
}
