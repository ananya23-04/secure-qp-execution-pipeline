import React, { useMemo } from 'react';
import katex from 'katex';
import 'katex/dist/katex.min.css';
import { splitMath } from '../lib/math.js';

function renderMath(src) {
  try {
    return katex.renderToString(src, { throwOnError: false, strict: 'ignore' });
  } catch {
    return '';
  }
}

// Renders text with $inline math$ typeset by KaTeX. KaTeX runs with trust off (no \href etc.).
export default function MathText({ text, className }) {
  const parts = useMemo(() => splitMath(text || ''), [text]);
  return (
    <span className={className}>
      {parts.map((p, i) =>
        p.type === 'math'
          ? <span key={i} dangerouslySetInnerHTML={{ __html: renderMath(p.value) }} />
          : <span key={i}>{p.value}</span>)}
    </span>
  );
}
