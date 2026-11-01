import type { Metadata } from 'next';
import type { CSSProperties, ReactNode } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { CONFIG } from '@/config/app';
import { fontVariables } from './fonts';
import { Providers } from './providers';
import './globals.css';

export const metadata: Metadata = {
  title: { default: CONFIG.brandName, template: `%s · ${CONFIG.brandName}` },
  description: '금융문서 민감정보 검토 (데모 데이터)',
};

/** 강조색은 ① 설정값에서 <html> 의 --accent 로 넣는다. 파생 색은 tokens.css 가 만든다. */
const rootStyle = { '--accent': CONFIG.accent } as CSSProperties;

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="ko" className={fontVariables} style={rootStyle}>
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
