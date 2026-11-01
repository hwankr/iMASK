'use client';

import type { ReactNode } from 'react';
import { ServiceProvider } from '@/services/react';

/** 앱 전역 Provider — 데이터 서비스(브라우저 싱글턴)를 모든 화면에 연결한다. */
export function Providers({ children }: { children: ReactNode }) {
  return <ServiceProvider>{children}</ServiceProvider>;
}
