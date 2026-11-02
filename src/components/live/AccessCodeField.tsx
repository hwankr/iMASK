'use client';

import type { Ref } from 'react';
import { TextField } from '@/components/ui';
import { saveAccessCode } from '@/services';
import { useAccessCode } from './liveHooks';

export interface AccessCodeFieldProps {
  /** 오류 문구(예: '접근 코드가 맞지 않습니다.') */
  error?: string;
  disabled?: boolean;
  inputRef?: Ref<HTMLInputElement | HTMLTextAreaElement>;
  /** 값을 고칠 때(오류 지우기 등) */
  onEdit?: () => void;
  className?: string;
}

/**
 * 접근 코드 입력칸 — 값을 가리고(password), 바뀔 때마다 이 탭의 sessionStorage 에만 저장한다.
 * 백엔드 /api/py/analyses 요청의 X-Demo-Code 헤더로 쓰인다.
 */
export function AccessCodeField({ error, disabled, inputRef, onEdit, className }: AccessCodeFieldProps) {
  const code = useAccessCode();
  return (
    <TextField
      className={className}
      label="접근 코드"
      type="password"
      required
      name="imask-access-code"
      autoComplete="off"
      value={code}
      onChange={(e) => {
        saveAccessCode(e.target.value);
        onEdit?.();
      }}
      disabled={disabled}
      inputRef={inputRef}
      help="이 탭을 닫으면 지워집니다. 팀에서 받은 코드를 넣으세요."
      error={error}
    />
  );
}
