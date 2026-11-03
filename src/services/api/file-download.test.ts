import { describe, expect, it } from 'vitest';
import { ApiError, MSG_NETWORK, MSG_NOT_FOUND, MSG_TIMEOUT, MSG_UNAUTHORIZED } from './client';
import { MSG_FILE_BAD_URL, MSG_FILE_NOT_FOUND, fileInfoError, isSafeDetail } from './file-download';

/* 키 · 토큰 모양 문자열은 GitGuardian 이 보지 않게 실행 중에 조립한다(모두 가짜) */
const HOST = ['storage', 'example', 'test'].join('.');
const SIGNED = `https://${HOST}/storage/v1/object/sign/a.pdf?${['to', 'ken'].join('')}=${['fixture', 'marker'].join('-')}`;
const JWT_LIKE = ['ey' + 'JhbGciOiJub25lIn0', 'ey' + 'JzdWIiOiJ4In0', 'c2ln'].join('.');
const SB_KEY = ['sb', 'secret', 'fixture'].join('_');

describe('isSafeDetail — 백엔드 detail 을 그대로 보여도 되는가(순수 함수)', () => {
  it('평범한 한국어 문장은 안전', () => {
    for (const d of ['접근 코드가 맞지 않습니다.', '분석 건을 찾을 수 없습니다.', '원본 파일을 찾을 수 없습니다.', '서버 설정이 빠졌습니다: UPSTAGE_CONFIG_ID', 'a'.repeat(20) + ' 끝']) {
      expect(isSafeDetail(d)).toBe(true);
    }
  });

  it('주소 · www. · 서명 표지(token · sig= · signature) · JWT 모양 · sb_ 키 모양 · 20자 넘는 덩어리 · 빈 값 · 문자열 아님은 안전하지 않음', () => {
    const unsafe: unknown[] = [
      `다운로드 실패: ${SIGNED}`,
      'see ftp://x',
      '주소 www.example.test 참고',
      '토큰(token) 만료',
      'TOKEN expired',
      'sig=abc',
      'Signature 가 맞지 않습니다',
      `인증 실패 ${JWT_LIKE}`,
      `키 ${SB_KEY} 확인`,
      '식별자 ' + 'a'.repeat(21),
      '분석 8f14e45f-ceea-467f-a0e6-0123456789ab 없음',
      '',
      '   ',
      null,
      undefined,
      42,
      {},
    ];
    for (const d of unsafe) expect(isSafeDetail(d)).toBe(false);
  });
});

describe('fileInfoError — /file 요청 오류 → 새 ApiError(순수 함수)', () => {
  it('늘 새 객체 · cause 없음 · 원래 스택을 넘기지 않음', () => {
    const original = new ApiError(500, 'server', `실패 ${SIGNED}`);
    const out = fileInfoError(original);
    expect(out).toBeInstanceOf(ApiError);
    expect(out).not.toBe(original);
    expect(out.cause).toBeUndefined();
    expect(out.stack ?? '').not.toContain(HOST);
    expect(out.analysisId).toBeNull();
  });

  it('401 · 404 — 안전한 detail 은 그대로, 주소 · 토큰이 섞이면 고정 문구(code · status 유지)', () => {
    expect(fileInfoError(new ApiError(401, 'unauthorized', '접근 코드가 맞지 않습니다.'))).toMatchObject({ status: 401, code: 'unauthorized', message: '접근 코드가 맞지 않습니다.' });
    expect(fileInfoError(new ApiError(404, 'not_found', '분석 건을 찾을 수 없습니다.'))).toMatchObject({ status: 404, code: 'not_found', message: MSG_NOT_FOUND });
    expect(fileInfoError(new ApiError(401, 'unauthorized', `코드 오류 ${SIGNED}`))).toMatchObject({ status: 401, code: 'unauthorized', message: MSG_UNAUTHORIZED });
    expect(fileInfoError(new ApiError(404, 'not_found', `없음 ${JWT_LIKE}`))).toMatchObject({ status: 404, code: 'not_found', message: MSG_FILE_NOT_FOUND });
  });

  it('5xx · 다른 4xx · 응답 읽기 실패는 detail 을 쓰지 않고 고정 문구', () => {
    for (const [status, code] of [
      [500, 'server'],
      [502, 'server'],
      [400, 'bad_request'],
      [409, 'conflict'],
      [200, 'server'], // 응답 JSON 을 읽지 못함
    ] as const) {
      expect(fileInfoError(new ApiError(status, code, `상세 ${SIGNED}`))).toMatchObject({ status, code, message: MSG_FILE_BAD_URL });
      expect(fileInfoError(new ApiError(status, code, '평범한 문장'))).toMatchObject({ message: MSG_FILE_BAD_URL });
    }
  });

  it('네트워크 · 시간 초과는 클라이언트의 고정 문구, ApiError 가 아니면 server · 0', () => {
    expect(fileInfoError(new ApiError(0, 'network', MSG_TIMEOUT))).toMatchObject({ status: 0, code: 'network', message: MSG_TIMEOUT });
    expect(fileInfoError(new ApiError(0, 'network', `연결 실패 ${SIGNED}`))).toMatchObject({ status: 0, code: 'network', message: MSG_NETWORK });
    for (const e of [new TypeError(SIGNED), SIGNED, null, undefined, { message: SIGNED }]) {
      expect(fileInfoError(e)).toMatchObject({ status: 0, code: 'server', message: MSG_FILE_BAD_URL });
    }
  });
});
