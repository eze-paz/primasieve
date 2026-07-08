// modules/streamdiff.js — Minimal DOM diff/patch for preserving selection during streaming
//
// Receives a live DOM element and a new HTML string. Parses the HTML string into
// a temporary fragment, then walks both trees to apply only the minimal set of
// attribute/child mutations needed to make the live tree match the new string.
// Text nodes that haven't changed are left untouched, so any active user text
// selection inside them survives across updates.
//
// USAGE:
//   streamDiff(containerElement, htmlString);
//
// The container element itself is never replaced; only its children are patched.

const _DIV = document.createElement('div');

function _patchAttrs(el, ref) {
  const keep = new Set();
  for (const a of ref.attributes || []) {
    keep.add(a.name);
    if (el.getAttribute(a.name) !== a.value) el.setAttribute(a.name, a.value);
  }
  for (const a of Array.from(el.attributes)) {
    if (!keep.has(a.name)) el.removeAttribute(a.name);
  }
}

function _patchKids(el, ref) {
  const oldN = el.childNodes.length;
  const newN = ref.childNodes.length;
  const min = Math.min(oldN, newN);

  for (let i = 0; i < min; i++) {
    const o = el.childNodes[i];
    const n = ref.childNodes[i];
    const sameType = o.nodeType === n.nodeType;

    if (sameType && o.nodeType === Node.TEXT_NODE) {
      if (o.nodeValue !== n.nodeValue) o.nodeValue = n.nodeValue;
      continue;
    }

    if (sameType && o.nodeType === Node.ELEMENT_NODE && o.tagName === n.tagName) {
      _patchAttrs(o, n);
      _patchKids(o, n);
      continue;
    }

    el.replaceChild(n.cloneNode(true), o);
  }

  while (el.childNodes.length > min) el.removeChild(el.lastChild);

  for (let i = min; i < newN; i++) {
    el.appendChild(ref.childNodes[i].cloneNode(true));
  }
}

/**
 * Diff-patch `rootEl` against `html`.
 * `html` should be the full inner-HTML string. The element itself is treated
 * as the container; its children are diffed against the parsed result.
 */
export function streamDiff(rootEl, html) {
  _DIV.innerHTML = html;
  _patchKids(rootEl, _DIV);
}
