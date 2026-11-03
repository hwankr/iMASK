-- 2026-11-03 적용 완료 (imask 프로젝트). 이미 적용된 파일이므로 내용을 고치지 말고, 바꿀 것은 새 마이그레이션 파일로 추가한다.

-- 검토 동작 저장: 실제 분석의 탐지 항목 검토(확인·오탐·분류 수정·메모·검토 완료/다시 열기)를 분석 1건당 1행으로 담는다.
-- 서버(FastAPI)가 비밀 키(service_role)로만 읽고 쓴다. 동작 하나 = 이 행 하나를 version 조건으로 갱신한다
-- (행이 없으면 insert … on conflict do nothing 으로 version 1, 있으면 update … where version = 읽은 값 으로 version + 1).
-- analyses 행은 검토 동작에서 쓰지 않는다(analyses_set_updated_at 트리거가 updated_at 을 바꾸고 화면의 분석 시각이 그 값을 쓴다).
-- 새 테이블·트리거·RLS·권한만 더한다. 기존 테이블과 데이터는 바꾸지 않는다.

create table public.analysis_reviews (
  analysis_id uuid primary key references public.analyses (id) on delete cascade,
  status text not null default 'needed'
    check (status in ('needed', 'done')),
  memo text not null default '',
  memo_at timestamptz,
  reviewer text not null default '',
  reviewed_at timestamptz,
  completion_note text not null default '',
  findings jsonb not null default '{}'::jsonb
    check (jsonb_typeof(findings) = 'object'),
  history jsonb not null default '[]'::jsonb
    check (jsonb_typeof(history) = 'array'),
  version integer not null
    check (version >= 1),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.analysis_reviews is '분석 건의 검토 기록. 분석 1건당 1행이고, 검토 동작 하나가 이 행을 version 조건으로 한 번 갱신한다. 최초 AI 결과(analyses.result)는 바꾸지 않고 그 위에 덧씌운다.';
comment on column public.analysis_reviews.status is '검토 상태: needed 검토 필요, done 검토 완료(잠김 — 다시 열기 전까지 항목 변경 불가)';
comment on column public.analysis_reviews.memo is '검토 메모(빈 문자열이면 없음)';
comment on column public.analysis_reviews.memo_at is '검토 메모를 마지막으로 저장(삭제 포함)한 시각';
comment on column public.analysis_reviews.reviewer is '검토를 완료한 처리자 이름(화면이 보낸 이름). 다시 열어도 남긴다';
comment on column public.analysis_reviews.reviewed_at is '검토 완료 시각. 다시 열면 null';
comment on column public.analysis_reviews.completion_note is '검토 완료 메모. 다시 열어도 남긴다';
comment on column public.analysis_reviews.findings is '탐지 항목별 검토 값. 키는 계약 id(<서류 index>:<추출 원래 키>)를 JSON 문자열 escape 한 ASCII 문자열, 값은 status·category·subject·exposure·fp_type·fp_note·reclass_note·memo·updated_at';
comment on column public.analysis_reviews.history is '검토 이력(배열, 저장 순서 = 시간 순서). 한 줄은 id(H<version>)·at·actor·kind·target·change·reason';
comment on column public.analysis_reviews.version is '낙관적 잠금 번호. 처음 만들 때 1, 검토 동작이 쓸 때마다 1씩 늘어난다';

-- updated_at 자동 갱신(기존 함수, 이 테이블에만)
create trigger analysis_reviews_set_updated_at
  before update on public.analysis_reviews
  for each row execute function public.set_updated_at();

-- 브라우저가 DB에 직접 접근하지 못하게 RLS를 켜고 정책은 두지 않는다 (서버의 비밀 키로만 접근)
alter table public.analysis_reviews enable row level security;

-- 서버(FastAPI)가 비밀 키(service_role)로 읽고 쓸 수 있도록 권한을 직접 적는다(README 'DB 변경 기록' 규칙)
grant select, insert, update, delete on table public.analysis_reviews to service_role;
