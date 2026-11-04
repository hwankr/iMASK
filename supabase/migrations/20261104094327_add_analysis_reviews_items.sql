-- 2026-11-04 적용 완료 (imask 프로젝트). 이미 적용된 파일이므로 내용을 고치지 말고, 바꿀 것은 새 마이그레이션 파일로 추가한다.

-- 검토사항 해결 기록: 실제 분석의 검토사항(서버가 조회할 때 결과에서 계산한다 — 필수 항목 없음·위치 확인 필요·
-- 인식 확인 필요·기타 서류)을 담당자가 해결·다시 열기 한 값을 검토 행에 담는 열을 더한다.
-- 검토 동작 resolve_item·reopen_item 이 다른 검토 동작과 같은 version 조건부 쓰기로 이 열과 이력을 쓴다.
-- 키는 검토사항 계약 id(예: lowconf:<서류 index>)를 JSON 문자열 escape 한 ASCII 문자열, 값은 resolved·note·resolved_at·resolved_by.
-- 지금 결과에 없는 id(다시 분석으로 결과가 바뀐 경우 등)의 값은 지우지 않고 조회할 때 무시한다.
-- 열 하나(기본값 빈 객체 + 객체 검사)만 더한다. 기존 행은 기본값을 갖는다(행을 갱신하지 않으므로 updated_at 트리거도 돌지 않는다).
-- 권한은 바꾸지 않는다(service_role 의 테이블 권한이 새 열에도 그대로 적용된다).

alter table public.analysis_reviews
  add column items jsonb not null default '{}'::jsonb
    check (jsonb_typeof(items) = 'object');

comment on column public.analysis_reviews.items is '검토사항별 해결 기록. 키는 검토사항 계약 id 를 JSON 문자열 escape 한 ASCII 문자열, 값은 resolved·note·resolved_at·resolved_by. 지금 결과에 없는 id 는 조회할 때 무시한다';
