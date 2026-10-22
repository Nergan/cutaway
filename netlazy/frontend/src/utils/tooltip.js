export function installTooltips() {
  const tip = document.createElement('div');
  tip.className = 'floating-tooltip site-tip';
  tip.hidden = true;
  document.body.appendChild(tip);

  let anchor = null;

  function hide() {
    anchor = null;
    tip.hidden = true;
    tip.textContent = '';
  }

  function read(el) {
    const stored = el.getAttribute('data-tooltip');
    if (stored) return stored;
    const native = el.getAttribute('title');
    if (!native) return '';
    el.setAttribute('data-tooltip', native);
    el.removeAttribute('title');
    return native;
  }

  function place(el) {
    const rect = el.getBoundingClientRect();
    const box = tip.getBoundingClientRect();
    const half = box.width / 2;
    const left = Math.min(Math.max(rect.left + rect.width / 2, half + 8), window.innerWidth - half - 8);
    let top = rect.bottom + 8;
    let above = false;
    if (top + box.height > window.innerHeight - 8) {
      top = rect.top - 8;
      above = true;
    }
    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;
    tip.style.transform = above ? 'translate(-50%, -100%)' : 'translate(-50%, 0)';
  }

  function show(el) {
    const text = read(el);
    if (!text) return;
    anchor = el;
    tip.hidden = false;
    tip.textContent = text;
    place(el);
    requestAnimationFrame(() => {
      if (anchor === el) place(el);
    });
  }

  document.addEventListener('mouseover', (event) => {
    const el = event.target.closest && event.target.closest('[data-tooltip], [title]');
    if (el === anchor) return;
    hide();
    if (el) show(el);
  });

  document.addEventListener('mouseout', (event) => {
    if (!anchor) return;
    if (event.relatedTarget && anchor.contains(event.relatedTarget)) return;
    hide();
  });

  document.addEventListener('focusin', (event) => {
    const el = event.target.closest && event.target.closest('[data-tooltip], [title]');
    hide();
    if (el) show(el);
  });

  document.addEventListener('focusout', hide);
  window.addEventListener('scroll', hide, true);
}
