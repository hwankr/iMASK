'use client';

import Link from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import { Suspense } from 'react';
import { listHomeHref, listNavHref, reviewNeededHref, useRememberedListQuery } from '@/components/list/listReturn';
import { cx } from '@/components/ui/cx';
import { Icon } from '@/components/ui/Icon';
import { SERVICE_MODE } from '@/services/mode';
import { DemoBadge } from './DemoBadge';
import styles from './AppHeader.module.css';

export interface AppHeaderProps {
  /** 브랜드명(① 설정값) */
  brandName: string;
  /** 담당자(① 설정값) */
  user: { readonly name: string; readonly team: string };
  /**
   * '검토 필요' 건수 — 0보다 크면 배지가 어둡게 채워진다. null 이면 아직 모름(불러오는 중):
   * 배지 자리(회색 빈 알약)만 두어 숫자가 들어와도 메뉴가 밀리지 않게 한다.
   * 앱에서는 AppShell 의 ServiceAppHeader 가 서비스 데이터로 넘긴다.
   */
  reviewNeededCount: number | null;
}

type NavKey = 'analyses' | 'review';

/** 실제 분석 모드(NEXT_PUBLIC_IMASK_SERVICE=api)의 헤더 표시 — 데모 모드는 DemoBadge 기본값('데모 데이터') */
const LIVE_BADGE = { label: '실제 분석', title: 'Upstage 워크플로우로 실제 분석합니다. 합성 자료만 올려 주세요.' } as const;

/** 주 메뉴 활성 — `/` 이고 `review=needed` 면 '검토 필요', 그 밖에는 '문서 분석' */
export function activeNav(pathname: string | null, review: string | null): NavKey {
  return pathname === '/' && review === 'needed' ? 'review' : 'analyses';
}

/**
 * 메뉴 이동 주소는 마지막으로 본 목록(listReturn)에서 만든다 — 프로토타입 nav:
 * '문서 분석'은 '검토 필요' 필터만 풀고, '검토 필요'는 검색·위험·상태를 풀고 검토 필요만 건다(정렬은 둘 다 유지).
 */
function NavItems({ active, count }: { active: NavKey; count: number | null }) {
  const query = useRememberedListQuery();
  return (
    <>
      <Link href={listNavHref(query)} aria-current={active === 'analyses' ? 'page' : undefined} className={cx(styles.navItem, active === 'analyses' && styles.navOn)}>
        문서 분석
        <span aria-hidden="true" className={styles.bar} />
      </Link>
      <Link href={reviewNeededHref(query)} aria-current={active === 'review' ? 'page' : undefined} className={cx(styles.navItem, active === 'review' && styles.navOn)}>
        검토 필요
        {count === null ? (
          <span aria-hidden="true" className={cx(styles.count, styles.countPending)} />
        ) : (
          <span className={cx(styles.count, count > 0 && styles.countOn)}>{count}</span>
        )}
        <span aria-hidden="true" className={styles.bar} />
      </Link>
    </>
  );
}

/** URL(경로 + ?review)로 활성 메뉴를 계산한다. useSearchParams 는 Suspense 안에서만 쓴다. */
function NavFromUrl({ count }: { count: number | null }) {
  const pathname = usePathname();
  const params = useSearchParams();
  return <NavItems active={activeNav(pathname, params.get('review'))} count={count} />;
}

/** 정적 렌더(쿼리를 모를 때)의 자리 — 경로만으로 계산해 '문서 분석'을 켠다 */
function NavFallback({ count }: { count: number | null }) {
  return <NavItems active="analyses" count={count} />;
}

/**
 * 헤더 — Main 98–112. 로고 버튼(첫 화면), 브랜드 글자(폭 480 이상), 주 메뉴(문서 분석 · 검토 필요 + 건수),
 * 오른쪽 데모 표시(실제 분석 모드면 '실제 분석')와 사용자 칩(폭 960 이상: 첫 글자 동그라미 · 이름 · 팀).
 * 선택 밑줄은 scaleX 로 움직인다(.32s).
 */
export function AppHeader({ brandName, user, reviewNeededCount }: AppHeaderProps) {
  const count = reviewNeededCount === null ? null : Math.max(0, Math.floor(reviewNeededCount));
  // 로고 = 프로토타입 goHome: 검색·필터를 모두 풀고 정렬만 둔다
  const homeHref = listHomeHref(useRememberedListQuery());
  return (
    <header className={styles.header}>
      <Link href={homeHref} aria-label={`${brandName} 첫 화면으로 이동`} className={styles.home}>
        <Icon name="dg-logo" size={28} className={styles.logo} />
        <span className={styles.brand}>{brandName}</span>
      </Link>
      <nav aria-label="주 메뉴" className={styles.nav}>
        <Suspense fallback={<NavFallback count={count} />}>
          <NavFromUrl count={count} />
        </Suspense>
      </nav>
      <div className={styles.right}>
        {SERVICE_MODE === 'api' ? <DemoBadge label={LIVE_BADGE.label} title={LIVE_BADGE.title} /> : <DemoBadge />}
        <div className={styles.user}>
          <span aria-hidden="true" className={styles.avatar}>
            {user.name.slice(0, 1)}
          </span>
          <div className={styles.userText}>
            <span className={styles.userName}>{user.name}</span>
            <span className={styles.userTeam}>{user.team}</span>
          </div>
        </div>
      </div>
    </header>
  );
}
