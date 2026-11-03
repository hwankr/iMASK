'use client';

/* ==========================================================================
   상세 검토 모달 — 원본 Main.dc.html 703–755 · modalVM · submitModal.
   상세 화면 상태의 모달 자리(ui.state.modal)를 그린다. 모양은 공통 Modal(T2), 값은 reviewModalModel.
   - 저장: 입력 검사(오류 문구는 붉은 글자, 입력칸은 붉은 바탕) → 서비스 호출(그동안 저장 버튼 돌림 표시)
     → 모달 닫기 → 토스트. 화면은 서비스 변경 알림으로 새 데이터를 받아 다시 그려진다.
     검토 완료 토스트의 '보고서 보기'는 지금 기준 경로(useRouteBase — `/demo` 아래면 /demo/…)의 보고서로 간다.
   - 사유 · 메모 입력칸에 처음 포커스(원본 autoFocus), Esc · 닫기 · 배경 누름으로 닫힘, 닫히면 연 버튼으로 포커스.
   - 휴대폰(< 768px)에서는 아래에서 올라오는 시트(공통 Modal).
   ========================================================================== */

import { useRouter } from 'next/navigation';
import { useId, useLayoutEffect, useRef, useState } from 'react';
import { Dropdown, Icon, Modal, RadioList, RiskBadge, TextField, useToast, type ModalButton } from '@/components/ui';
import { reportHref as reportHrefFor } from '@/lib/routes';
import type { Pending } from '@/services/analysis-service';
import { usePending, useRouteBase, useService } from '@/services/react';
import type { Analysis } from '@/services/types';
import { planPickFinding, type DetailModal } from '@/components/detail/detailState';
import type { DetailUi } from '@/components/detail/useDetailUi';
import { rememberFocus, rescueFocus, type FocusSpot } from '@/components/detail/focusRescue';
import {
  NOTE_MAX,
  SAVE_FAILED,
  applyReviewModal,
  reviewModalError,
  reviewModalModel,
  type EditFieldModel,
  type EditKey,
  type EditValue,
  type ModalTargetModel,
  type PendingGo,
  type ReviewModalModel,
} from './reviewModalModel';
import styles from './ReviewModal.module.css';

export interface ReviewModalProps {
  /** 지금 분석 건(서비스가 준 최신 값) */
  analysis: Analysis;
  ui: DetailUi;
}

/** 상세 화면의 모달 자리 — 열린 모달이 없으면 아무것도 그리지 않는다 */
export function ReviewModal({ analysis, ui }: ReviewModalProps) {
  const m = ui.state.modal;
  if (!m) return null;
  if (m.type === 'complete') return <CompleteReviewModal analysis={analysis} ui={ui} modal={m} />;
  return <ReviewModalView analysis={analysis} ui={ui} modal={m} pending={null} />;
}

/** 검토 완료 — 남은 항목(서비스 pending)을 받은 뒤 연다 */
function CompleteReviewModal({ analysis, ui, modal }: ReviewModalProps & { modal: DetailModal }) {
  const { data } = usePending(analysis.id);
  if (!data) return null;
  return <ReviewModalView analysis={analysis} ui={ui} modal={modal} pending={data} />;
}

interface ViewProps {
  analysis: Analysis;
  ui: DetailUi;
  modal: DetailModal;
  pending: Pending | null;
}

function ReviewModalView({ analysis: a, ui, modal: m, pending }: ViewProps) {
  const service = useService();
  const toast = useToast();
  const router = useRouter();
  const base = useRouteBase();
  const ids = useId();
  const noteId = `${ids}-note`;
  const errId = `${ids}-err`;
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  /** 모달을 연 자리 — 저장 뒤 그 버튼이 바뀌어 없어졌으면 같은 자리의 새 버튼으로 포커스(focusRescue) */
  const [opener] = useState<FocusSpot | null>(() => rememberFocus());
  /** 저장(비동기) 중에 데이터가 바뀌어도 최신 값으로 검사한다 */
  const latest = useRef({ a, m });
  useLayoutEffect(() => {
    latest.current = { a, m };
  });

  const model = reviewModalModel(a, m, pending);
  if (!model) return null;

  const close = () => ui.closeModal();

  const submit = async () => {
    if (!service || busyRef.current) return;
    busyRef.current = true;
    try {
      const cur = latest.current;
      /* 원본 submitModal: 검토 완료는 저장할 때 남은 항목을 다시 센다 */
      const p = cur.m.type === 'complete' ? await service.pending(cur.a.id) : null;
      const error = reviewModalError(cur.a, cur.m, p);
      if (error) {
        ui.patchModal({ error });
        return;
      }
      setBusy(true);
      const done = await applyReviewModal(service, cur.a, cur.m);
      ui.closeModal();
      const reportHref = reportHrefFor(base, cur.a.id);
      toast(done.text, done.openReport ? { action: { label: '보고서 보기', onClick: () => router.push(reportHref) } } : {});
      rescueFocus(opener);
    } catch {
      ui.patchModal({ error: SAVE_FAILED });
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  /** 남은 항목 바로가기 — 모달을 닫고 그 항목으로(원본 complete items[].go) */
  const go = (g: PendingGo) => {
    ui.closeModal();
    if (g.kind === 'item') ui.pickItem(g.id);
    else if (g.kind === 'link') ui.openLink(g.id);
    else {
      const plan = planPickFinding(ui.state, a, g.id, { tab: 'findings' }, ui.mobile);
      ui.run(plan ? { ...plan, card: g.id } : null);
    }
  };

  const act = (x: ReviewModalModel['buttons'][number]['act']) => {
    if (x === 'close') return close;
    if (x === 'goPending') return ui.goPending;
    return () => void submit();
  };
  const buttons: ModalButton[] = model.buttons.map((b) => ({
    label: b.label,
    variant: b.variant,
    onClick: act(b.act),
    loading: b.act === 'submit' && busy,
  }));

  const error = m.error || '';

  return (
    <Modal open onClose={close} title={model.title} subtitle={model.sub} width={model.width} buttons={buttons} dismissible={!busy}>
      {model.target ? <TargetCard t={model.target} /> : null}

      {model.reasons && m.type === 'fp' ? (
        <RadioList
          legend="오탐으로 판단한 이유"
          name={`${ids}-fp-reason`}
          options={model.reasons.map((r) => ({ value: r, label: r }))}
          value={m.reason}
          onChange={(reason) => ui.patchModal({ reason })}
        />
      ) : null}

      {model.edit ? (
        <>
          <div className={styles.editGrid}>
            <EditField field={model.edit.fields[0]} idPrefix={ids} alignEnd={false} onPick={(cat) => ui.patchModal({ cat, error: '' })} />
            <EditField field={model.edit.fields[1]} idPrefix={ids} alignEnd={false} onPick={(subject) => ui.patchModal({ subject, error: '' })} />
            {/* 노출 상태 메뉴는 데스크톱 · 태블릿에서 오른쪽에 맞춘다(원본 rightAl) */}
            <EditField field={model.edit.fields[2]} idPrefix={ids} alignEnd={!ui.mobile} onPick={(exposure) => ui.patchModal({ exposure, error: '' })} />
          </div>
          <div className={styles.aiText}>
            <strong className={styles.aiStrong}>최초 AI 결과</strong> · {model.edit.aiText}
          </div>
        </>
      ) : null}

      {model.complete ? (
        <>
          {model.complete.any ? (
            <>
              <div className={styles.pendingBox}>
                <strong className={styles.pendingTitle}>
                  <Icon name="dg-i-alert" size={18} strokeWidth={2.1} />
                  아직 확인하지 않은 내용이 있습니다
                </strong>
                <ul className={styles.pendingLines}>
                  {model.complete.lines.map((l) => (
                    <li key={l}>{l}</li>
                  ))}
                </ul>
                <div className={styles.pendingItems}>
                  {model.complete.items.map((it) => (
                    <button key={it.id} type="button" className={styles.pendingItem} onClick={() => go(it.go)}>
                      <span className={styles.pendingId}>{it.id}</span>
                      <span className={styles.pendingLabel}>{it.label}</span>
                      <span className={styles.pendingGo}>
                        확인하기
                        <Icon name="dg-i-chev-right" size={15} strokeWidth={2.4} />
                      </span>
                    </button>
                  ))}
                </div>
              </div>
              <p className={styles.pendingNote}>남은 항목을 먼저 확인하거나, 남은 이유를 적고 검토를 완료할 수 있습니다. 완료 후에도 보고서의 ‘남아 있는 검토사항’에 그대로 표시됩니다.</p>
            </>
          ) : (
            <div className={styles.allDone}>
              <Icon name="dg-i-check-circle" size={18} strokeWidth={2.1} />
              모든 탐지 항목과 검토사항을 확인했습니다.
            </div>
          )}
          <div className={styles.keepRisk}>
            <span className={styles.keepIcon}>
              <Icon name="dg-i-info" size={16} strokeWidth={2} />
            </span>
            <span>검토를 완료하면 검토 상태만 ‘검토 완료’로 바뀝니다. 위험등급({model.complete.riskLabel})과 최초 탐지 결과는 그대로 유지됩니다.</span>
          </div>
        </>
      ) : null}

      <TextField
        id={noteId}
        label={model.note.label}
        labelNote={model.note.req}
        multiline
        rows={model.note.rows}
        maxLength={NOTE_MAX}
        showCount
        autoFocus
        placeholder={model.note.placeholder}
        value={m.note}
        onChange={(e) => ui.patchModal({ note: e.target.value, error: '' })}
        invalid={!!error}
        describedBy={error ? errId : undefined}
        className={styles.note}
      />
      {model.info ? <p className={styles.info}>{model.info}</p> : null}
      {error ? (
        <p id={errId} role="alert" className={styles.error}>
          <Icon name="dg-i-alert" size={16} strokeWidth={2.1} />
          {error}
        </p>
      ) : null}
    </Modal>
  );
}

/** 대상 카드(Main 713) — 위험 · 정보 종류 · 세부 항목 · ID, 마스킹 값, 설명 줄 */
function TargetCard({ t }: { t: ModalTargetModel }) {
  return (
    <div className={styles.target}>
      <div className={styles.targetRow}>
        {t.risk ? <RiskBadge level={t.risk} size="xs" /> : null}
        <strong className={styles.targetTitle}>{t.title}</strong>
        <span className={styles.targetId}>{t.id}</span>
      </div>
      {t.value ? <span className={styles.targetValue}>{t.value}</span> : null}
      <span className={styles.targetMeta}>{t.meta}</span>
    </div>
  );
}

/** 분류 수정 드롭다운(Main 718–722) — 바깥 라벨 + 선택칸, 최초 AI 값에 '최초 AI' */
function EditField<K extends EditKey>({
  field: f,
  idPrefix,
  alignEnd,
  onPick,
}: {
  field: EditFieldModel<K>;
  idPrefix: string;
  alignEnd: boolean;
  onPick: (value: EditValue[K]) => void;
}) {
  const labelId = `${idPrefix}-${f.key}-l`;
  return (
    <div className={styles.editField}>
      <span id={labelId} className={styles.editLabel}>
        {f.title}
      </span>
      <Dropdown
        variant="field"
        title={f.title}
        value={f.value}
        options={f.options.map((o) => ({ value: o.value, label: o.label, aiOriginal: o.ai }))}
        onChange={onPick}
        changed={f.changed}
        labelledBy={labelId}
        align={alignEnd ? 'end' : 'start'}
        id={`${idPrefix}-${f.key}`}
      />
    </div>
  );
}
