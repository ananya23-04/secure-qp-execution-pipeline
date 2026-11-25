// Split text into plain and $inline math$ segments. "\$" is a literal dollar in text.
export function splitMath(text) {
  const out = [];
  let buf = '';
  let math = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '\\' && i + 1 < text.length) {
      const n = text[i + 1];
      if (!math && '$%&#_'.includes(n)) { buf += n; i++; continue; }
      buf += c + n; i++; continue;
    }
    if (c === '$') {
      if (buf) out.push({ type: math ? 'math' : 'text', value: buf });
      buf = '';
      math = !math;
      continue;
    }
    buf += c;
  }
  if (buf) out.push({ type: math ? 'math' : 'text', value: buf });
  return out;
}

// Client-side mirror of the server's LaTeX checks, so authors see problems while typing.
// The server stays the authority; this is only early feedback.
const FORBIDDEN = /\\(input|include|includeonly|write|openin|openout|read|immediate|catcode|usepackage|documentclass|csname|directlua|verbatiminput|special|def|edef|gdef|xdef|let|newcommand|renewcommand|providecommand)(?![A-Za-z])/;
const ENV = /\\(begin|end)\{([^}]*)\}/g;

export const ISSUE_TEXT = {
  FORBIDDEN_LATEX: 'Uses a LaTeX command that is not allowed (file access / macro definitions).',
  UNBALANCED_MATH: 'A $ is not closed - math must be written as $...$.',
  UNBALANCED_BRACES: 'Curly braces { } are not balanced.',
  MISMATCHED_ENV: '\\begin{...} and \\end{...} do not match.',
};

export function lintLatex(text) {
  const issues = [];
  if (!text) return issues;
  if (FORBIDDEN.test(text)) issues.push('FORBIDDEN_LATEX');
  let dollars = 0;
  for (let i = 0; i < text.length; i++) {
    if (text[i] === '\\') { i++; continue; }
    if (text[i] === '$') dollars++;
  }
  if (dollars % 2) issues.push('UNBALANCED_MATH');
  let depth = 0;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '\\') { i++; continue; }
    if (c === '{') depth++;
    else if (c === '}') { depth--; if (depth < 0) break; }
  }
  if (depth !== 0) issues.push('UNBALANCED_BRACES');
  const stack = [];
  let bad = false;
  for (const m of text.matchAll(ENV)) {
    if (m[1] === 'begin') stack.push(m[2]);
    else if (!stack.length || stack.pop() !== m[2]) { bad = true; break; }
  }
  if (bad || stack.length) issues.push('MISMATCHED_ENV');
  return issues;
}
