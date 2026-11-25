import React from 'react';
import { render } from '@testing-library/react';
import { splitMath, lintLatex } from '../lib/math.js';
import MathText from '../components/MathText.jsx';

describe('splitMath', () => {
  it('separates text and inline math', () => {
    expect(splitMath('Find $x^2$ now')).toEqual([
      { type: 'text', value: 'Find ' }, { type: 'math', value: 'x^2' }, { type: 'text', value: ' now' }]);
  });
  it('treats \\$ and \\% as literal text outside math', () => {
    expect(splitMath('costs \\$5 or 50\\%')).toEqual([{ type: 'text', value: 'costs $5 or 50%' }]);
  });
});

describe('lintLatex mirrors the server checks', () => {
  it('accepts normal maths', () => {
    expect(lintLatex('Find $\\frac{a}{b}$ and \\textbf{note}')).toEqual([]);
    expect(lintLatex('Cost is \\$5 and set \\{1,2\\}')).toEqual([]);
  });
  it('flags unbalanced math, braces and environments', () => {
    expect(lintLatex('Evaluate $\\int_0^1 x dx')).toContain('UNBALANCED_MATH');
    expect(lintLatex('\\frac{a}{b')).toContain('UNBALANCED_BRACES');
    expect(lintLatex('\\begin{tabular} x \\end{array}')).toContain('MISMATCHED_ENV');
    expect(lintLatex('\\begin{tabular} x')).toContain('MISMATCHED_ENV');
  });
  it('flags forbidden commands but not look-alikes', () => {
    for (const bad of ['\\input{/etc/passwd}', '\\write18{ls}', '\\def\\x{y}', '\\usepackage{x}']) {
      expect(lintLatex(bad)).toContain('FORBIDDEN_LATEX');
    }
    expect(lintLatex('\\define is not a primitive')).toEqual([]);
  });
});

describe('MathText', () => {
  it('typesets math with KaTeX and keeps plain text', () => {
    const { container } = render(<MathText text={'Derive $e^x$ please'} />);
    expect(container.querySelector('.katex')).not.toBeNull();
    expect(container.textContent).toContain('Derive');
  });
  it('does not execute html in plain text', () => {
    const { container } = render(<MathText text={'<img src=x onerror=alert(1)> hi'} />);
    expect(container.querySelector('img')).toBeNull();
    expect(container.textContent).toContain('<img');
  });
});
