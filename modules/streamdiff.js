// modules/streamdiff.js — Minimal DOM diff/patch for preserving selection during streaming
//
// Receives a live DOM element and a new HTML string. Parses the HTML string into
// a temporary fragment, then walks both trees to apply only the minimal set of
// attribute/child mutations needed to make the live tree match the new string.
// Text nodes that haven't changed are left untouched, so any active user text
// selection inside them survives across updates.

const _DIV = document.createElement('div');

function _patchAttrs(el, ref) {
  const keep = new Set();
  if (ref.attributes) {
    for (const a of ref.attributes) {
      keep.add(a.name);
      if (el.getAttribute(a.name) !== a.value) el.setAttribute(a.name, a.value);
    }
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

    // Different types/tags — swap (selection inside this subtree will be lost, but
    // the rest of the tree stays intact).
    el.replaceChild(n.cloneNode(true), o);
  }

  // Remove excess old children
  while (el.childNodes.length > min) el.removeChild(el.lastChild);

  // Append remaining new children
  for (let i = min; i < newN; i++) {
    el.appendChild(ref.childNodes[i].cloneNode(true));
  }
}

/**
 * Diff-patch `rootEl` against `html`.
 *
 * `html` should be a complete sibling-free innerHTML string (the same as you
 * would previously have assigned to `rootEl.innerHTML`).
 */
export function streamDiff(rootEl, html) {
  _DIV.innerHTML = html;
  const ref = _DIV.firstChild;
  if (!ref) return;

  if (rootEl.nodeType !== Node.ELEMENT_NODE || ref.nodeType !== Node.ELEMENT_NODE) {
    rootEl.innerHTML = html;
    return;
  }

  if (rootEl.tagName !== ref.tagName) {
    rootEl.innerHTML = html;
    return;
  }

  _patchAttrs(rootEl, ref);
  _patchKids(rootEl, ref);
}
