/**
 * 개발용 경로(/dev/components · /dev/states · /dev/states/<상태>)를 여는지 — `next dev` 이거나 `IMASK_DEV_PAGES=1` 로 빌드했을 때만.
 * 운영 빌드(그 밖)에서는 세 페이지가 notFound() 를 불러 404(app/not-found.tsx)다. IMASK_DEV_PAGES 는 next.config.ts env 로
 * 빌드 때 글자로 들어간다(next start 때 값을 바꿔도 빌드한 대로다).
 */
export function devPagesEnabled(): boolean {
  return process.env.NODE_ENV !== 'production' || process.env.IMASK_DEV_PAGES === '1';
}
