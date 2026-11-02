-- 2026-11-02 적용 완료 (imask 프로젝트). 이미 적용된 파일이므로 내용을 고치지 말고, 바꿀 것은 새 마이그레이션 파일로 추가한다.

-- 서버(FastAPI)가 비밀 키(service_role)로 두 테이블을 읽고 쓸 수 있도록 권한을 직접 적는다.
-- imask 프로젝트에는 예전 기본 권한이 남아 있어 이미 같은 권한이 있다. 이 마이그레이션은 그 상태를 명시할 뿐 지금 권한을 바꾸지 않는다.
-- 새 환경에서는 새 public 테이블에 API 역할 권한이 자동으로 붙지 않을 수 있으므로(Supabase 변경 공지 2026-04-28), 어디에 적용해도 같은 상태가 되게 한다.
grant usage on schema public to service_role;
grant select, insert, update, delete on table public.analyses, public.documents to service_role;
