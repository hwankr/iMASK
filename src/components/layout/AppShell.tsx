import type { ReactNode } from 'react';
import { IconSprite } from '@/components/ui/IconSprite';
import { LiveRegionProvider } from '@/components/ui/LiveRegion';
import { ToastProvider } from '@/components/ui/Toast';
import { CONFIG } from '@/config/app';
import { APP_ROOT_ATTR } from '@/lib/hooks/dom-attrs';
import styles from './AppShell.module.css';
import { ServiceAppHeader } from './ServiceAppHeader';

export interface AppShellProps {
  children: ReactNode;
}

/**
 * 화면 껍데기 — 프로토타입 루트 구조(Main 44·98·113): 화면 높이에 맞춘 세로 flex, 헤더 고정,
 * <main> 이 남은 높이에서 스크롤. 아이콘 스프라이트, 토스트, 알림 영역(LiveRegion)을 한 번씩 둔다.
 * 브랜드명·사용자는 ① 설정값에서. 헤더 '검토 필요' 건수는 ServiceAppHeader 가 데이터 서비스에서 센다
 * (ServiceProvider 는 layout 에서 AppShell 바깥을 감싼다).
 *
 * 구조: LiveRegionProvider > ToastProvider > [화면 루트(헤더 + main)] + 토스트 + 알림 영역
 * 모달은 document.body 로 포털되고, 열린 동안 화면 루트만 inert 로 막는다(토스트·알림 영역은 막히지 않음).
 */
export function AppShell({ children }: AppShellProps) {
  const rootAttr = { [APP_ROOT_ATTR]: '' };
  return (
    <LiveRegionProvider>
      <ToastProvider>
        <div className={styles.root} {...rootAttr}>
          <IconSprite />
          <ServiceAppHeader brandName={CONFIG.brandName} user={CONFIG.user} />
          <main id="main" className={styles.main}>
            {children}
          </main>
        </div>
      </ToastProvider>
    </LiveRegionProvider>
  );
}
