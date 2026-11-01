import localFont from 'next/font/local';
import { IBM_Plex_Mono } from 'next/font/google';

/** 한글 글꼴 — npm `pretendard` 패키지의 가변 woff2 (굵기 45–920). */
export const pretendard = localFont({
  src: '../../node_modules/pretendard/dist/web/variable/woff2/PretendardVariable.woff2',
  weight: '45 920',
  style: 'normal',
  display: 'swap',
  variable: '--font-pretendard',
});

/** 고정폭 글꼴 — 규칙 ID · 마스킹 값 · 분석 ID. */
export const plexMono = IBM_Plex_Mono({
  weight: ['400', '500', '600'],
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-plex-mono',
});

/** `<html>` 에 붙이는 글꼴 변수 클래스. */
export const fontVariables = `${pretendard.variable} ${plexMono.variable}`;
