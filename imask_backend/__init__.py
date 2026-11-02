# ==========================================================================
#  imask_backend — iMASK 서버 쪽 공용 Python 코드
#  - config.py    : 환경변수 읽기(값은 출력하지 않는다)
#  - redaction.py : 비밀값·인증 문구 가림(오류 문구·로그·저장 전 공용 경계)
#  - upstage.py   : Upstage Agent API 호출(파일 올리기·작업 만들기·조회·파일 지우기), 실패 이유 문구
#  - results.py   : Upstage 응답(output[]) 파싱과 요약
#  - settings.py  : FastAPI 백엔드 전체 환경 설정(요청 때 읽음, 빠져도 import 는 실패하지 않음)
#  - files.py     : 파일 이름·형식 검사, Storage 용 안전한 이름, 내용 첫 바이트 검사
#  - store.py     : Supabase 테이블(analyses·documents)·Storage(documents 버킷) 접근, 조건부 갱신
#  - analyses.py  : 분석 만들기·시작·조회 업무 로직(FastAPI 와 무관). HTTP 층은 api/index.py
#  Vercel 은 api/ 안의 .py 파일마다 함수를 만들기 때문에 공용 코드는 api/ 밖 이 패키지에 둔다.
# ==========================================================================
