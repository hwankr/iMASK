/* 훅과 레이아웃이 함께 쓰는 DOM 표시(React 없이 — 서버 컴포넌트에서도 가져올 수 있다) */

/** AppShell 의 화면 루트에 붙는 표시 — 모달이 열리면 이 요소를 inert 로 막는다 */
export const APP_ROOT_ATTR = 'data-dg-app-root';

/** <html> 에 붙이는 스크롤 잠금 표시 — AppShell 의 <main> 스크롤도 이 표시로 멈춘다 */
export const SCROLL_LOCK_ATTR = 'data-dg-scroll-lock';
