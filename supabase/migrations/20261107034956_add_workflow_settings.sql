-- 2026-11-07 적용 완료 (imask 프로젝트). 이미 적용된 파일이므로 내용을 고치지 말고, 바꿀 것은 새 마이그레이션 파일로 추가한다.

-- 웹 설정 화면(/settings)에서 바꾸는 워크플로우 설정: Upstage 에이전트 id 와 설정 번호를 담는 한 행짜리 테이블을 더한다.
-- 행이 있으면 분석을 시작할 때 이 값을 쓰고, 없으면 지금처럼 환경 변수(UPSTAGE_AGENT_ID·UPSTAGE_CONFIG_ID)를 쓴다.
-- 재배포 없이 바꾸려는 것이다(환경 변수는 바꾸면 다시 배포해야 한다).
-- analyses.config_id: 그 분석을 시작할 때 쓴 설정 번호. 실행 도중에 설정을 바꿔도 결과 기록이 틀어지지 않게 시작할 때 남긴다.
-- 새 테이블·트리거·RLS·권한과 null 허용 열 하나만 더한다. 기존 행은 고치지 않는다(행을 갱신하지 않으므로 analyses_set_updated_at 트리거도 돌지 않는다).

create table public.workflow_settings (
  id smallint primary key default 1
    check (id = 1),
  agent_id text not null,
  config_id text not null,
  updated_at timestamptz not null default now()
);

comment on table public.workflow_settings is '웹 설정 화면에서 바꾸는 워크플로우 설정. 행은 하나뿐(id = 1)이고, 없으면 환경 변수 값을 쓴다.';
comment on column public.workflow_settings.agent_id is 'Upstage 에이전트 id(agt_…). 분석을 시작할 때 쓴다';
comment on column public.workflow_settings.config_id is 'Upstage 워크플로우 설정 번호(숫자 문자열)';

-- updated_at 자동 갱신(기존 함수, 이 테이블에만)
create trigger workflow_settings_set_updated_at
  before update on public.workflow_settings
  for each row execute function public.set_updated_at();

-- 브라우저가 DB에 직접 접근하지 못하게 RLS를 켜고 정책은 두지 않는다 (서버의 비밀 키로만 읽고 쓴다)
alter table public.workflow_settings enable row level security;

-- 서버(FastAPI)가 비밀 키(service_role)로 읽고 저장할 수 있도록 권한을 직접 적는다(README 'DB 변경 기록'). 행을 지우는 경로는 없다
grant select, insert, update on table public.workflow_settings to service_role;

alter table public.analyses add column config_id text;

comment on column public.analyses.config_id is '이 분석을 시작할 때 쓴 Upstage 설정 번호. 이 열을 더하기 전에 시작한 분석은 null';
