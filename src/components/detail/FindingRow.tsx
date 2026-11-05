'use client';

import { Button, FindingStatusLabel, Icon, RiskBadge, cx } from '@/components/ui';
import type { DetailActions } from './detailActions';
import type { FindingModel } from './detailModel';
import { Tip } from './Tip';
import styles from './FindingRow.module.css';

export interface FindingRowProps {
  f: FindingModel;
  /** 검토 완료 — 검토 동작을 막는다 */
  locked: boolean;
  /** 검토 기록을 불러오지 못한 실제 분석 — 검토 동작 버튼만 막는다. '원문 확인'은 그대로 */
  readOnly?: boolean;
  /** 행 머리 — 펼치기 · 접기(같은 항목을 고르고 그 위치로 이동) */
  onToggle: (fid: string) => void;
  /** '원문 확인' — 휴대폰이면 원문 탭으로 */
  onReveal: (fid: string) => void;
  actions: DetailActions;
  /** 마스킹 미리보기 중 — 행 왼쪽 가림 버튼(누르면 이 항목의 가림을 켜고 끈다). 없으면 버튼이 없다 */
  onMaskPick?: (fid: string) => void;
}

/**
 * 탐지 항목 행(Main 472–510 · 디자인 기준 04) — 위험 · 정보 종류 · 확인 상태, 세부 항목, 마스킹 값, 메타 줄.
 * 누르면 같은 자리에서 펼쳐 근거 · 적용 규칙 · 원문 위치 · 근거 문구 · 바뀐 분류 · 오탐/수정 사유 · 메모와 행동 버튼을 보인다.
 * 위치가 없는 항목은 '위치 확인 필요'(강조 대신 근거 문구와 쪽 번호).
 * 실제 분석은 적용 규칙이 없으면 그 줄을 빼고, 분류 확인 필요 · 인식 신뢰도 낮음 안내를 보인다.
 * readOnly(검토 기록을 불러오지 못한 실제 분석)면 검토 동작 버튼만 막는다(안내 문구는 없다).
 * 마스킹 미리보기 중(onMaskPick)에는 행 왼쪽에 가림 버튼이 붙는다 — 가림이면 검은 칸(원문의 검은 상자와 같은 색)에 가린 눈.
 * 화면 상태만 바꾸므로 검토 완료 · 읽기 전용이어도 쓸 수 있다.
 */
export function FindingRow({ f, locked, readOnly = false, onToggle, onReveal, actions, onMaskPick }: FindingRowProps) {
  const off = locked || readOnly;
  return (
    <article data-card={f.id} className={cx(styles.row, f.open && styles.open, onMaskPick && styles.picking)}>
      {onMaskPick ? (
        <Tip label={f.maskPicked ? '가림 해제' : '가리기'} side="right" className={styles.pickTip}>
          <button
            type="button"
            aria-pressed={f.maskPicked}
            aria-label={f.id + ' 가리기'}
            onClick={() => onMaskPick(f.id)}
            className={cx(styles.pick, f.maskPicked && styles.pickOn)}
            data-slot="mask-pick"
          >
            <Icon name={f.maskPicked ? 'dg-i-eye-off' : 'dg-i-eye'} size={16} strokeWidth={2.2} />
          </button>
        </Tip>
      ) : null}
      <button type="button" aria-expanded={f.open} aria-label={f.aria} onClick={() => onToggle(f.id)} className={styles.toggle}>
        <span className={styles.body}>
          <span className={styles.line1}>
            <RiskBadge level={f.risk.key} size="xs" />
            <span className={styles.cat}>{f.cat}</span>
            <FindingStatusLabel status={f.statusKey} className={styles.status} />
          </span>
          <span className={styles.label}>{f.label}</span>
          <span className={cx(styles.masked, f.fp && styles.maskedFp)}>{f.masked}</span>
          <span className={styles.metaLine}>
            <span className={styles.id}>{f.id}</span>
            <span>· {f.subject}</span>
            <span>· {f.where}</span>
            <span>· {f.exposure}</span>
            {f.noLoc ? (
              <span className={styles.noLoc}>
                <Icon name="dg-i-pin-q" size={13} strokeWidth={2.2} />
                위치 확인 필요
              </span>
            ) : null}
          </span>
        </span>
        <span aria-hidden="true" className={styles.chev}>
          <Icon name="dg-i-chev-down" size={18} strokeWidth={2.2} />
        </span>
      </button>
      {f.open ? (
        <div className={styles.detail}>
          <dl className={styles.dl}>
            <dt className={styles.dt}>판단 근거</dt>
            <dd className={styles.dd}>{f.reason}</dd>
            {f.hasRule ? (
              <>
                <dt className={styles.dt}>적용 규칙</dt>
                <dd className={styles.dd}>
                  <span className={styles.rule}>{f.rule}</span> <span className={styles.ruleName}>{f.ruleName}</span>
                </dd>
              </>
            ) : null}
            <dt className={styles.dt}>원문 위치</dt>
            <dd className={cx(styles.dd, f.noLoc && styles.ddWarn)}>{f.locText}</dd>
            {f.notes.length ? (
              <>
                <dt className={styles.dt}>확인할 점</dt>
                <dd className={cx(styles.dd, styles.notes)}>
                  {f.notes.map((n) => (
                    <span key={n} className={styles.note}>
                      <Icon name="dg-i-alert" size={13} strokeWidth={2.2} />
                      {n}
                    </span>
                  ))}
                </dd>
              </>
            ) : null}
            {f.hasEvidence ? (
              <>
                <dt className={styles.dt}>근거 문구</dt>
                <dd className={styles.dd}>“{f.evidence}”</dd>
              </>
            ) : null}
            {f.changed ? (
              <>
                <dt className={styles.dt}>최초 AI 결과</dt>
                <dd className={cx(styles.dd, styles.dd2)}>{f.aiText}</dd>
              </>
            ) : null}
            {f.note ? (
              <>
                <dt className={styles.dt}>{f.noteLabel}</dt>
                <dd className={styles.dd}>{f.note}</dd>
              </>
            ) : null}
            {f.memo ? (
              <>
                <dt className={styles.dt}>메모</dt>
                <dd className={styles.dd}>{f.memo}</dd>
              </>
            ) : null}
          </dl>
          <div className={styles.actions}>
            {f.canConfirm ? (
              <Button size="item" variant="primary" icon="dg-i-check" disabled={off} onClick={() => actions.confirmFinding(f.id)} data-slot="confirm">
                탐지 내용 확인
              </Button>
            ) : null}
            {f.canUnconfirm ? (
              <Button size="item" variant="outline" disabled={off} onClick={() => actions.unconfirmFinding(f.id)} data-slot="confirm">
                확인 취소
              </Button>
            ) : null}
            <Button size="item" variant="outline" icon="dg-i-file" onClick={() => onReveal(f.id)}>
              원문 확인
            </Button>
            {f.canFp ? (
              <Button size="item" variant="outline" icon="dg-i-ban" disabled={off} onClick={() => actions.markFalsePositive(f.id)} data-slot="fp">
                오탐으로 표시
              </Button>
            ) : null}
            {f.canRestore ? (
              <Button size="item" variant="outline" icon="dg-i-refresh" disabled={off} onClick={() => actions.restoreFinding(f.id)} data-slot="fp">
                오탐 취소
              </Button>
            ) : null}
            <Button size="item" variant="outline" icon="dg-i-pencil" disabled={off} onClick={() => actions.reclassify(f.id)}>
              분류 수정
            </Button>
            <Button size="item" variant="ghost" icon="dg-i-memo" disabled={off} onClick={() => actions.editFindingMemo(f.id)}>
              {f.memoLabel}
            </Button>
          </div>
          {locked ? <p className={styles.locked}>검토 완료된 건은 수정할 수 없습니다. 수정하려면 상단의 ‘검토 다시 열기’를 사용하세요.</p> : null}
        </div>
      ) : null}
    </article>
  );
}
