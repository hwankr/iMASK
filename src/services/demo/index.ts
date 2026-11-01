/* ④ 데모 서비스 — 바깥에는 비동기 겉면과 판별 함수만 내보낸다(동기 코어 · 샘플은 안에서만 쓴다). */

export { createDemoService, isDemoService } from './service';
export type { DemoService } from './service';
