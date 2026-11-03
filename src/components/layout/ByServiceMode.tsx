'use client';

import type { ReactNode } from 'react';
import { useServiceMode } from '@/services/react';

export interface ByServiceModeProps {
  /** 데모 모드 화면 */
  demo: ReactNode;
  /** 실제 분석 모드 화면 */
  api: ReactNode;
}

/**
 * 주소 기준 서비스 모드(useServiceMode)로 두 화면 중 하나를 그린다. 루트 라우트 페이지(서버 컴포넌트라 훅을 못 쓴다)가
 * 두 화면을 넘긴다. 모드는 서버에서도 주소로 정해지므로 서버 렌더와 첫 클라이언트 렌더가 같은 화면이다.
 */
export function ByServiceMode({ demo, api }: ByServiceModeProps) {
  return useServiceMode() === 'api' ? api : demo;
}
