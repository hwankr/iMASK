-- 2026-11-07 적용 완료 (imask 프로젝트). 이미 적용된 파일이므로 내용을 고치지 말고, 바꿀 것은 새 마이그레이션 파일로 추가한다.

-- 웹 설정 화면의 워크플로우 목록: 이름을 붙여 등록해 두고 골라서 적용한다.
-- 적용은 고른 항목의 에이전트 id·설정 번호를 workflow_settings(지금 적용 중인 값, 한 행)에 복사하는 것이다. 분석을 시작하는 쪽은 이 테이블을 읽지 않는다.
-- 그래서 항목을 지워도 지금 적용 중인 값은 그대로다. 항목은 고치지 않고 지운 뒤 다시 등록한다(update 경로 없음).
-- 새 테이블·RLS·권한만 더한다. 기존 테이블과 데이터는 바꾸지 않는다.

create table public.workflow_presets (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  agent_id text not null,
  config_id text not null,
  created_at timestamptz not null default now()
);

comment on table public.workflow_presets is '웹 설정 화면에 등록해 둔 워크플로우 목록. 고르면 값을 workflow_settings 로 복사한다.';
comment on column public.workflow_presets.name is '화면에 보이는 이름(겹치지 않음)';
comment on column public.workflow_presets.agent_id is 'Upstage 에이전트 id(agt_…)';
comment on column public.workflow_presets.config_id is 'Upstage 워크플로우 설정 번호(숫자 문자열)';

-- 브라우저가 DB에 직접 접근하지 못하게 RLS를 켜고 정책은 두지 않는다 (서버의 비밀 키로만 읽고 쓴다)
alter table public.workflow_presets enable row level security;

-- 서버(FastAPI)가 비밀 키(service_role)로 읽고 쓸 수 있도록 권한을 직접 적는다(README 'DB 변경 기록')
grant select, insert, delete on table public.workflow_presets to service_role;
