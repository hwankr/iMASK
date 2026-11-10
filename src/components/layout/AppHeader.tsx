'use client';

import Link from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import { Suspense } from 'react';
import { activeNav, listHomeHref, listNavHref, reviewNeededHref, useRememberedListQuery, type NavKey } from '@/components/list/listReturn';
import { cx } from '@/components/ui/cx';
import { Icon } from '@/components/ui/Icon';
import { RSTATUS } from '@/display/rules';
import { SETTINGS_HREF, type RouteBase } from '@/lib/routes';
import { useBuildMode, useRouteBase, useServiceMode } from '@/services/react';
import { DemoBadge } from './DemoBadge';
import { modeSwitchLink } from './modeSwitch';
import styles from './AppHeader.module.css';

export interface AppHeaderProps {
  /** 브랜드명(① 설정값) */
  brandName: string;
  /**
   * '검토 대기' 건수 — 0보다 크면 배지가 어둡게 채워진다. null 이면 아직 모름(불러오는 중):
   * 배지 자리(회색 빈 알약)만 두어 숫자가 들어와도 메뉴가 밀리지 않게 한다.
   * 앱에서는 AppShell 의 ServiceAppHeader 가 서비스 데이터로 넘긴다.
   */
  reviewNeededCount: number | null;
}

/** 실제 분석 모드(주소 기준 모드 'api')의 헤더 표시 — 데모 모드는 DemoBadge 기본값('데모 데이터') */
const LIVE_BADGE = { label: '실제 분석', title: 'Upstage 워크플로우로 실제 분석합니다. 합성 자료만 올려 주세요.' } as const;

/** 옆에 전환 링크가 있는 데모 배지(실제 모드 빌드의 `/demo`)의 좁은 폭 글자 — 헤더가 넘치지 않게 */
const DEMO_BADGE_SHORT = '데모';

/**
 * 메뉴 이동 주소는 그 기준 경로(루트 · `/demo`)에서 마지막으로 본 목록(listReturn)으로 만든다 — 프로토타입 nav:
 * '문서 분석'은 '검토 대기' 필터만 풀고, '검토 대기'는 검색·위험·상태를 풀고 검토 대기만 건다(정렬은 둘 다 유지).
 */
function NavItems({ active, count, base }: { active: NavKey | null; count: number | null; base: RouteBase }) {
  const query = useRememberedListQuery(base);
  const live = useServiceMode() === 'api'; // 받는 쪽(이 기준 경로의 목록) 모드 — 위험등급 'review' 는 실제 분석만
  return (
    <>
      <Link href={listNavHref(base, query, live)} aria-current={active === 'analyses' ? 'page' : undefined} className={cx(styles.navItem, active === 'analyses' && styles.navOn)}>
        문서 분석
        <span aria-hidden="true" className={styles.bar} />
      </Link>
      <Link href={reviewNeededHref(base, query, live)} aria-current={active === 'review' ? 'page' : undefined} className={cx(styles.navItem, active === 'review' && styles.navOn)}>
        {RSTATUS.needed.label}
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
function NavFromUrl({ count, base }: { count: number | null; base: RouteBase }) {
  const pathname = usePathname();
  const params = useSearchParams();
  return <NavItems active={activeNav(pathname, params.get('review'))} count={count} base={base} />;
}

/** 정적 렌더(쿼리를 모를 때)의 자리 — 경로만으로 계산한다(설정 화면 말고는 '문서 분석'을 켠다) */
function NavFallback({ count, base }: { count: number | null; base: RouteBase }) {
  return <NavItems active={activeNav(usePathname(), null)} count={count} base={base} />;
}

/**
 * 헤더 — Main 98–112. 로고 버튼(첫 화면), 브랜드 글자(폭 480 이상), 주 메뉴(문서 분석 · 검토 대기 + 건수),
 * 오른쪽 '설정' 링크(실제 분석 화면 · 폭 768 이상만 — 휴대폰은 헤더 자리가 없어 주소로 연다),
 * 모드 전환 링크(modeSwitch.ts — 실제 분석 화면은 '데모 체험하기', 실제 모드 빌드의 `/demo` 는 '실제 분석으로')와
 * 모드 표시(배지 '실제 분석' · '데모 데이터').
 * 모드 · 기준 경로는 주소 기준(useServiceMode · useRouteBase) — `/demo` 아래는 빌드 모드와 상관없이 데모 표시이고
 * 링크도 `/demo` 기준이다. 데모 빌드(useBuildMode 'demo')에는 전환 링크가 없다. 선택 밑줄은 scaleX 로 움직인다(.32s).
 */
export function AppHeader({ brandName, reviewNeededCount }: AppHeaderProps) {
  const count = reviewNeededCount === null ? null : Math.max(0, Math.floor(reviewNeededCount));
  const mode = useServiceMode();
  const base = useRouteBase();
  const switchLink = modeSwitchLink(mode, useBuildMode());
  // 로고 = 프로토타입 goHome: 검색·필터를 모두 풀고 정렬만 둔다
  const homeHref = listHomeHref(base, useRememberedListQuery(base), mode === 'api');
  return (
    <header className={styles.header}>
      <Link href={homeHref} aria-label={`${brandName} 첫 화면으로 이동`} className={styles.home}>
        <Icon name="dg-logo" size={28} className={styles.logo} />
        <span className={styles.brand}>{brandName}</span>
      </Link>
      <nav aria-label="주 메뉴" className={styles.nav}>
        <Suspense fallback={<NavFallback count={count} base={base} />}>
          <NavFromUrl count={count} base={base} />
        </Suspense>
      </nav>
      <div className={cx(styles.right, switchLink && styles.rightSwitch)}>
        {mode === 'api' ? (
          <Link href={SETTINGS_HREF} prefetch={false} className={cx(styles.modeLink, styles.settingsLink)}>
            설정
          </Link>
        ) : null}
        {switchLink ? (
          /* 미리 받지 않는다(prefetch={false}) — 한쪽 화면을 열 때 다른 쪽 화면을 받지 않게(요청 목록 그대로) */
          <Link href={switchLink.href} prefetch={false} aria-label={switchLink.label} title={switchLink.title} className={styles.modeLink}>
            <span className={styles.modeLinkLong}>{switchLink.label}</span>
            <span aria-hidden="true" className={styles.modeLinkShort}>
              {switchLink.short}
            </span>
          </Link>
        ) : null}
        {mode === 'api' ? (
          <DemoBadge label={LIVE_BADGE.label} title={LIVE_BADGE.title} />
        ) : (
          <DemoBadge shortLabel={switchLink ? DEMO_BADGE_SHORT : undefined} />
        )}
      </div>
    </header>
  );
}
