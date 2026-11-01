import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // cacheComponents·partialPrefetching(create-next-app 기본값)은 끈다.
  // 이번 단계는 데이터가 모두 클라이언트 데모 서비스라 끔. 실제 API 단계에서 서버 데이터를 쓰게 되면 다시 검토.
  // (켜 두면 'use client' 페이지의 React.use(params)가 Suspense 없이 빌드되지 않는다.)
  cacheComponents: false,
  partialPrefetching: false,
  // next dev 가 AI 에이전트를 감지하면 저장소 루트에 AGENTS.md 를 만든다. 작업 범위 밖 파일이 생기지 않게 끈다.
  agentRules: false,
  // 개발 화면 왼쪽 아래의 경로 표시(N)를 숨긴다 — 디자인 비교 스크린샷을 가리지 않게. 컴파일·실행 오류는 그대로 보인다.
  devIndicators: false,
};

export default nextConfig;
