// Tests for the getCharOffset bug fix.
// The bug: .ann-clf-badge text was counted in character offsets, inflating
// stored annotation end positions when classified order_action spans preceded
// the selection endpoint.

const { JSDOM } = require('jsdom');

function makeDOM(html) {
  const dom = new JSDOM(`<!DOCTYPE html><body>${html}</body>`);
  const { document } = dom.window;

  // Replicate the fixed getCharOffset function
  function getCharOffset(root, targetNode, targetOff) {
    var r = document.createRange();
    r.setStart(root, 0);
    r.setEnd(targetNode, targetOff);
    var frag = r.cloneContents();
    frag.querySelectorAll('.ann-tag, .ann-clf-badge').forEach(function(el) { el.remove(); });
    return frag.textContent.length;
  }

  return { document, getCharOffset };
}

function makeBuggyDOM(html) {
  const dom = new JSDOM(`<!DOCTYPE html><body>${html}</body>`);
  const { document } = dom.window;

  // Replicate the buggy getCharOffset (only strips .ann-tag, not .ann-clf-badge)
  function getCharOffset(root, targetNode, targetOff) {
    var r = document.createRange();
    r.setStart(root, 0);
    r.setEnd(targetNode, targetOff);
    var frag = r.cloneContents();
    frag.querySelectorAll('.ann-tag').forEach(function(el) { el.remove(); });
    return frag.textContent.length;
  }

  return { document, getCharOffset };
}

let passed = 0, failed = 0;

function assert(description, actual, expected) {
  if (actual === expected) {
    console.log(`  PASS  ${description}`);
    passed++;
  } else {
    console.log(`  FAIL  ${description}`);
    console.log(`        expected ${expected}, got ${actual}`);
    failed++;
  }
}

// ── Test 1: No existing annotations — baseline ──────────────────────────────
{
  // Plain text: "Hello world"
  // Select up to character 5 ("Hello")
  const { document, getCharOffset } = makeDOM(
    '<div class="annot-text">Hello world</div>'
  );
  const root = document.querySelector('.annot-text');
  const textNode = root.firstChild; // "Hello world"
  const offset = getCharOffset(root, textNode, 5);
  assert('plain text: offset at position 5', offset, 5);
}

// ── Test 2: Existing ann-tag (label) is excluded from count ─────────────────
{
  // Rendered: [ann-span "foo"<sup ann-tag>order_action</sup>] " bar baz"
  // Selecting to end of " bar" (4 chars after span) should return 3 + 4 = 7
  const { document, getCharOffset } = makeDOM(
    '<div class="annot-text">' +
      '<span class="ann-span">foo<sup class="ann-tag">order_action</sup></span>' +
      ' bar baz' +
    '</div>'
  );
  const root = document.querySelector('.annot-text');
  // Target: the text node " bar baz", offset 4 (" bar")
  const textNode = root.lastChild; // " bar baz"
  const offset = getCharOffset(root, textNode, 4);
  assert('ann-tag excluded: "foo" + " bar" = 7', offset, 7);
}

// ── Test 3 (THE BUG): clf-badge text must NOT be counted ────────────────────
{
  // Rendered: [ann-span "foo"<sup ann-tag>order_action</sup><span ann-clf-badge>Pol · Legal</span>] " bar"
  // "Pol · Legal" is 11 chars. Without the fix, offset for " bar" = 3 + 11 + 4 = 18.
  // With the fix it should be 3 + 4 = 7.
  const badgeText = 'Pol · Legal';
  const html =
    '<div class="annot-text">' +
      '<span class="ann-span">foo' +
        '<sup class="ann-tag">order_action</sup>' +
        '<span class="ann-clf-badge">' + badgeText + '</span>' +
      '</span>' +
      ' bar' +
    '</div>';

  const fixed  = makeDOM(html);
  const buggy  = makeBuggyDOM(html);

  const rootFixed = fixed.document.querySelector('.annot-text');
  const rootBuggy = buggy.document.querySelector('.annot-text');

  const textNodeFixed = rootFixed.lastChild; // " bar"
  const textNodeBuggy = rootBuggy.lastChild;

  const offsetFixed = fixed.getCharOffset(rootFixed, textNodeFixed, 4);
  const offsetBuggy = buggy.getCharOffset(rootBuggy, textNodeBuggy, 4);

  assert('fixed: clf-badge excluded — "foo" + " bar" = 7', offsetFixed, 7);
  assert('buggy: clf-badge counted — inflated to 7 + badge length', offsetBuggy, 7 + badgeText.length);
}

// ── Test 4: Multiple classified spans before selection ──────────────────────
{
  // Two classified order_action spans, each with a badge ("AB" = 2 chars each)
  // then " end" (4 chars). True offset = 3 + 3 + 4 = 10.
  const html =
    '<div class="annot-text">' +
      '<span class="ann-span">foo' +
        '<sup class="ann-tag">order_action</sup>' +
        '<span class="ann-clf-badge">AB</span>' +
      '</span>' +
      '<span class="ann-span">bar' +
        '<sup class="ann-tag">order_action</sup>' +
        '<span class="ann-clf-badge">AB</span>' +
      '</span>' +
      ' end' +
    '</div>';

  const { document, getCharOffset } = makeDOM(html);
  const root = document.querySelector('.annot-text');
  const textNode = root.lastChild; // " end"
  const offset = getCharOffset(root, textNode, 4);
  assert('multiple clf-badges excluded: "foo"+"bar"+" end" = 10', offset, 10);
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
