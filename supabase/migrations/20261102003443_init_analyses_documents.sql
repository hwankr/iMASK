-- 2026-11-02 적용 완료 (imask 프로젝트). 이미 적용된 파일이므로 내용을 고치지 말고, 바꿀 것은 새 마이그레이션 파일로 추가한다.

-- 분석 건: 한 번에 올린 서류 묶음 = 분석 1건 = Upstage 작업 1개
create table public.analyses (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  status text not null default 'queued'
    check (status in ('queued', 'running', 'done', 'partial', 'failed')),
  agent_id text,
  upstage_job_id text,
  result jsonb,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.analyses is '분석 건. 한 번에 올린 서류 묶음 하나가 분석 1건이고 Upstage 작업 1개와 연결된다.';
comment on column public.analyses.status is '처리 상태: queued 대기, running 분석 중, done 완료, partial 일부 실패, failed 실패 (프로토타입 표기와 같은 값)';
comment on column public.analyses.agent_id is '실행에 쓴 Upstage Studio 에이전트 ID';
comment on column public.analyses.upstage_job_id is 'Upstage 작업 번호';
comment on column public.analyses.result is 'Upstage 원본 결과 JSON. 출력 스키마 확정 후 탐지 항목 테이블로 정리한다.';

-- 문서: 분석 건에 속한 원본 파일
create table public.documents (
  id uuid primary key default gen_random_uuid(),
  analysis_id uuid not null references public.analyses (id) on delete cascade,
  filename text not null,
  storage_path text not null unique,
  size_bytes bigint,
  mime_type text,
  upstage_file_id text,
  created_at timestamptz not null default now()
);

create index documents_analysis_id_idx on public.documents (analysis_id);

comment on table public.documents is '분석 건에 속한 원본 파일. 파일 자체는 documents 비공개 버킷에 있다.';
comment on column public.documents.storage_path is 'documents 버킷 안의 파일 경로';
comment on column public.documents.upstage_file_id is 'Upstage Files API에 올린 파일 ID';

-- updated_at 자동 갱신
create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger analyses_set_updated_at
  before update on public.analyses
  for each row execute function public.set_updated_at();

-- 브라우저가 DB에 직접 접근하지 못하게 RLS를 켜고 정책은 두지 않는다 (서버의 비밀 키로만 접근)
alter table public.analyses enable row level security;
alter table public.documents enable row level security;

-- 원본 파일 버킷: 비공개, 파일당 20MB, PDF·PNG·JPG만
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('documents', 'documents', false, 20971520, array['application/pdf', 'image/png', 'image/jpeg']);
