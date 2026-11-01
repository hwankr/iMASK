/** 키보드로 갈 수 있는 요소 선택자 */
const FOCUSABLE = [
  'a[href]',
  'area[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  'summary',
  'iframe',
  '[contenteditable="true"]',
  '[tabindex]',
].join(',');

/** 컨테이너 안에서 Tab 으로 갈 수 있는 요소(보이는 것만, tabindex=-1 제외) */
export function getFocusable(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => {
    if (el.tabIndex < 0) return false;
    if (el.closest('[inert]')) return false;
    if (el instanceof HTMLInputElement && el.type === 'radio' && !el.checked) {
      // 같은 이름의 라디오 묶음은 고른 것(없으면 첫 번째)만 Tab 순서에 든다
      const group = el.name ? container.querySelectorAll<HTMLInputElement>(`input[type="radio"][name="${CSS.escape(el.name)}"]`) : [];
      const anyChecked = Array.from(group).some((r) => r.checked);
      if (anyChecked || group[0] !== el) return false;
    }
    return el.getClientRects().length > 0;
  });
}

/** 요소에 포커스를 옮긴다(스크롤 튐 없이). 실패해도 조용히 넘어간다. */
export function focusElement(el: HTMLElement | null | undefined): boolean {
  if (!el || typeof el.focus !== 'function') return false;
  el.focus({ preventScroll: false });
  return document.activeElement === el;
}

/**
 * 누르면(마우스·터치) 포커스를 가져갈 수 있는 요소의 종류 — 입력칸·버튼·링크·tabindex 요소·편집 영역.
 * 지금 실제로 받을 수 있는지(비활성·숨김)는 takesPressFocus 가 따로 본다 — `[tabindex]` 가 붙어 있어도
 * 비활성 컨트롤은 포커스를 받지 않는다.
 * `<label>` 은 넣지 않는다. 라벨 자체는 포커스를 받지 않고 연결된 컨트롤로 넘길 뿐이라 isPressFocusable 이 따로 본다.
 */
const PRESS_FOCUSABLE = [
  'a[href]',
  'area[href]',
  'button',
  'input:not([type="hidden"])',
  'select',
  'textarea',
  'summary',
  'iframe',
  'audio[controls]',
  'video[controls]',
  '[contenteditable]:not([contenteditable="false"])',
  '[tabindex]',
].join(',');

/**
 * 지금 누르면 실제로 포커스를 받는 요소인가 — 위 종류이고, 비활성(`:disabled`, 비활성 fieldset 안 포함)이 아니고,
 * inert 안이 아니고, 숨김(그려지지 않음 — display:none·hidden 속성, visibility:hidden)이 아닐 때만.
 */
function takesPressFocus(el: Element): boolean {
  if (!el.matches(PRESS_FOCUSABLE) || el.matches(':disabled') || el.closest('[inert]') !== null) return false;
  if (el.localName === 'area') return true; // 이미지 맵 영역은 자기 상자가 없다(그림이 그려진다)
  return el.getClientRects().length > 0 && getComputedStyle(el).visibility === 'visible';
}

/**
 * 누른 곳이 포커스를 가져가는가 — 그러면 바깥 누름으로 닫을 때 포커스를 빼앗지 않는다.
 * 1) 누른 곳(또는 조상) 가운데 지금 포커스를 받는 요소가 있으면 — 브라우저가 mousedown 때 그 요소에 포커스를 준다.
 *    비활성·숨김 요소는 건너뛰고 더 위를 본다(브라우저도 그렇게 찾는다).
 * 2) 아니면, 누른 곳이 `<label>` 안이고 그 라벨의 연결 컨트롤(`HTMLLabelElement.control`)이 지금 포커스를 받을 때 —
 *    click 때 그 컨트롤로 포커스가 넘어간다. 연결 대상이 없거나(for 가 틀림·안에 컨트롤 없음) 비활성·숨김이면
 *    포커스가 아무 데도 가지 않으므로(body) false — 드롭다운은 트리거로 돌려준다.
 */
export function isPressFocusable(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  for (let el: Element | null = target; el; el = el.parentElement) {
    if (takesPressFocus(el)) return true;
  }
  const control = target.closest('label')?.control;
  return control != null && takesPressFocus(control);
}

/**
 * 이번 누름(pointerdown)에 이어지는 mousedown 의 기본 동작 — 포커스 이동·해제 — 을 한 번만 막는다.
 * 포커스를 받지 않는 곳을 눌러도 브라우저는 mousedown 때 지금 포커스를 풀어(body 로) 버리므로,
 * 누름 처리기에서 옮겨 둔 포커스를 지키려면 필요하다. 터치는 손을 뗀 뒤 mousedown 이 오므로
 * 시간이 아니라 '같은 대상의 mousedown 이 오거나, 다음 pointerdown 이 시작될 때'까지만 기다린다
 * (키 입력·pointercancel 이 와도 끝낸다). 그 누름으로는 글자 끌어 고르기가 시작되지 않는다.
 *
 * 비활성 컨트롤(과 비활성 버튼 안)을 누르면 Chrome 은 mousedown·mouseup·click 을 보내지 않으면서 포커스는 푼다
 * (마우스는 누를 때, 터치는 손을 뗀 뒤). 막을 mousedown 이 없으므로, 기다리는 동안 포커스가 아무 데도 아닌 곳
 * (`relatedTarget` 없음 → body)으로 풀리면 그 일이 끝난 뒤 풀린 요소로 한 번 되돌린다(스크롤 없이).
 * 다른 요소로 옮겨 간 포커스와, 이미 다른 곳에 포커스가 있을 때는 건드리지 않는다.
 */
export function keepFocusThroughPress(pointerDown: PointerEvent): void {
  if (typeof document === 'undefined') return;
  const target = pointerDown.target;
  let armed = true;
  const cleanup = () => {
    armed = false;
    document.removeEventListener('mousedown', onMouseDown, true);
    document.removeEventListener('focusout', onFocusOut, true);
    document.removeEventListener('pointerdown', cleanup, true);
    document.removeEventListener('pointercancel', cleanup, true);
    document.removeEventListener('keydown', cleanup, true);
  };
  function onMouseDown(e: MouseEvent) {
    cleanup();
    if (e.target === target) e.preventDefault();
  }
  function onFocusOut(e: FocusEvent) {
    const lost = e.target;
    if (e.relatedTarget !== null || !(lost instanceof HTMLElement)) return;
    // 포커스를 푸는 브라우저 처리가 끝난 뒤에 본다. 떼어 낸 요소(닫힌 목록의 항목 등)가 풀린 것이면 그대로 둔다
    setTimeout(() => {
      const now = document.activeElement;
      if (!armed || !lost.isConnected || (now !== null && now !== document.body)) return;
      cleanup();
      lost.focus({ preventScroll: true });
    }, 0);
  }
  // 지금 처리 중인 pointerdown 에는 새 처리기가 불리지 않는다(DOM 은 처리기 목록을 복사해 부른다)
  document.addEventListener('mousedown', onMouseDown, true);
  document.addEventListener('focusout', onFocusOut, true);
  document.addEventListener('pointerdown', cleanup, true);
  document.addEventListener('pointercancel', cleanup, true);
  document.addEventListener('keydown', cleanup, true);
}
