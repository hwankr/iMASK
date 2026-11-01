'use client';

import type { ReactNode } from 'react';

/** 앱 전역 Provider 자리 — T3가 ServiceProvider(데이터 서비스 연결)를 넣는다. */
export function Providers({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
