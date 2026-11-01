import type { ReactNode } from 'react';

/** 화면 껍데기 자리 — T2가 헤더·화면 높이 고정·내부 스크롤·토스트 영역을 만든다. */
export function AppShell({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
