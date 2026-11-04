-- 2026-11-04 적용 완료 (imask 프로젝트). 이미 적용된 파일이므로 내용을 고치지 말고, 바꿀 것은 새 마이그레이션 파일로 추가한다.

-- 다시 분석: 분석을 마지막으로 시작한 시각을 담는 열을 더한다.
-- 서버가 시작할 때마다 넣는다 — 새 분석은 시작 선점(queued → running) 때, 실패한 분석의 다시 분석은 되돌릴 때(failed → queued)와 선점할 때.
-- 화면의 경과·걸린 시간은 이 값(없으면 created_at)부터 잰다. 요청 시각·분석 번호·목록 순서는 created_at 그대로다.
-- null 허용 열 하나만 더한다. 기존 행은 고치지 않는다(행을 갱신하지 않으므로 analyses_set_updated_at 트리거도 돌지 않는다).
-- 권한은 바꾸지 않는다(service_role 의 테이블 권한이 새 열에도 그대로 적용된다).

alter table public.analyses add column started_at timestamptz;

comment on column public.analyses.started_at is '분석을 마지막으로 시작한 시각(시작 선점·다시 분석 때 서버가 넣는다). 화면의 경과·걸린 시간 기준이고, 없으면 created_at 을 쓴다';
