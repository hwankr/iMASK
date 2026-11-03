import type { Metadata } from 'next';
import type { ReactNode } from 'react';

/** `/demo` 아래는 언제나 데모 서비스(샘플 데이터)라 설명에 그 사실을 붙인다. 화면 틀은 루트 layout(AppShell) 그대로. */
export const metadata: Metadata = {
  description: '금융문서 민감정보 검토 (데모 데이터)',
};

export default function DemoLayout({ children }: { children: ReactNode }) {
  return children;
}
