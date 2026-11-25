import React, { useEffect, useRef, useState } from 'react';
import { CheckCircle2, ListChecks, PenLine, Plus, Send, Sparkles, Trash2, AlignLeft, FileText, Layers, Eye, X } from 'lucide-react';
import { api } from '../lib/api.js';
import { lintLatex } from '../lib/math.js';
import MathText from '../components/MathText.jsx';
import { Alert, Badge, Card, Empty, ErrorBox, Issues, PageHeader, Segmented, useToast } from '../components/ui.jsx';

const BLOOM = [
  ['remember', 'Remember', 'Recall facts and terms'], ['understand', 'Understand', 'Explain ideas in your own words'],
  ['apply', 'Apply', 'Use a method in a new situation'], ['analyze', 'Analyze', 'Break down and draw connections'],
  ['evaluate', 'Evaluate', 'Justify a decision or judgement'], ['create', 'Create', 'Produce something new'],
];
const LETTERS = 'ABCDEF';
const DEFAULT_MARKS = { mcq: 1, short: 2, long: 5 };
const SNIPPETS = [
  ['Fraction', '$\\frac{a}{b}$'], ['Power', '$x^{2}$'], ['Root', '$\\sqrt{x}$'], ['Sum', '$\\sum_{i=1}^{n} a_i$'],
  ['Integral', '$\\int_{a}^{b} f(x)\\,dx$'], ['Matrix', '$\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}$'],
];

const blank = (meta = {}) => ({
  qtype: 'mcq', stem: '', options: ['', '', '', ''], correct: 0, solution: '',
  subject: meta.subject || '', unit: meta.unit || 1, bloom: meta.bloom || 'understand',
  difficulty: meta.difficulty ?? 0.5, marks: meta.marks || 1,
});

export function toPayload(q) {
  const mcq = q.qtype === 'mcq';
  return {
    qtype: q.qtype, stem: q.stem.trim(),
    options: mcq ? q.options.map((o) => o.trim()) : null,
    correct_option: mcq ? q.correct : null,
    solution_latex: q.solution.trim() || null,
    subject: q.subject.trim(), unit: Number(q.unit), bloom: q.bloom,
    difficulty: Number(q.difficulty), marks: Number(q.marks),
  };
}

export function validate(q) {
  const problems = [];
  if (q.stem.trim().length < 10) problems.push('The question text needs at least 10 characters.');
  if (q.subject.trim().length < 2) problems.push('Enter the subject.');
  if (!(Number(q.unit) >= 1)) problems.push('Unit must be 1 or higher.');
  if (!(Number(q.marks) >= 1)) problems.push('Marks must be 1 or higher.');
  if (q.qtype === 'mcq') {
    if (q.options.length < 2) problems.push('An MCQ needs at least 2 options.');
    if (q.options.some((o) => !o.trim())) problems.push('Fill in every option (or remove the empty ones).');
    if (new Set(q.options.map((o) => o.trim().toLowerCase())).size !== q.options.length) problems.push('Options must be different from each other.');
  }
  const fields = [q.stem, q.solution, ...(q.qtype === 'mcq' ? q.options : [])];
  const codes = [...new Set(fields.flatMap(lintLatex))];
  return { problems, codes };
}

const SAMPLE = {
  qtype: 'mcq', stem: 'If $f(x)=x^2$ and $g(x)=\\sin x$, what is $\\frac{d}{dx} f(g(x))$?',
  options: ['$2\\sin x\\cos x$', '$\\cos x^2$', '$2x\\sin x$', '$\\sin 2x^2$'], correct: 0,
  solution: 'By the chain rule, $f\'(g(x))\\,g\'(x)=2\\sin x\\cos x$.',
  subject: 'Engineering Mathematics', unit: 1, bloom: 'apply', difficulty: 0.4, marks: 1,
};

export default function Submit() {
  const toast = useToast();
  const [q, setQ] = useState(blank());
  const [batch, setBatch] = useState([]);
  const [rights, setRights] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const timer = useRef(null);
  const area = useRef(null);

  useEffect(() => () => clearTimeout(timer.current), []);

  const set = (patch) => setQ((p) => ({ ...p, ...patch }));
  const { problems, codes } = validate(q);
  const touched = q.stem.length > 0;
  const blocked = problems.length > 0 || codes.length > 0;

  function insert(snippet) {
    const el = area.current;
    const a = el ? el.selectionStart : q.stem.length;
    const b = el ? el.selectionEnd : a;
    set({ stem: q.stem.slice(0, a) + snippet + q.stem.slice(b) });
    requestAnimationFrame(() => { if (el) { el.focus(); const pos = a + snippet.length; el.setSelectionRange(pos, pos); } });
  }
  const setOption = (i, v) => set({ options: q.options.map((o, k) => (k === i ? v : o)) });
  const addOption = () => q.options.length < 6 && set({ options: [...q.options, ''] });
  function removeOption(i) {
    if (q.options.length <= 2) return;
    set({ options: q.options.filter((_, k) => k !== i), correct: q.correct === i ? 0 : q.correct > i ? q.correct - 1 : q.correct });
  }

  function addToBatch() {
    if (blocked) return;
    setBatch((b) => [...b, toPayload(q)]);
    setQ(blank(q));
    toast('Added to your batch.');
  }

  async function poll(id, tries = 0) {
    try {
      const rep = await api(`/submissions/${id}/report`);
      setResult(rep);
      if (rep.submission_status !== 'deduplicated' && tries < 40) timer.current = setTimeout(() => poll(id, tries + 1), 1000);
      else toast('Your questions were processed.');
    } catch (e) { setError(e); }
  }

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      const r = await api('/submissions', { method: 'POST', body: { questions: batch, rights_declared: rights } });
      setBatch([]);
      setRights(false);
      setResult({ submission_status: 'raw_ingested', summary: {}, questions: [] });
      poll(r.id);
    } catch (e) { setError(e); } finally { setBusy(false); }
  }

  const mcq = q.qtype === 'mcq';
  return (
    <>
      <PageHeader eyebrow="Contribute" title="Write questions"
                  subtitle="Type naturally and use $…$ for maths. You see exactly how it will be typeset, and problems are flagged before you submit."
                  actions={<button type="button" className="btn btn-secondary" onClick={() => setQ(SAMPLE)}><Sparkles size={16} />Load example</button>} />
      <div className="cols-main">
        <div className="stack">
          <Card title="Question details" icon={ListChecks}>
            <div className="stack">
              <Segmented name="qtype" label="Question type" value={q.qtype}
                         onChange={(v) => set({ qtype: v, marks: DEFAULT_MARKS[v] })}
                         options={[{ value: 'mcq', label: 'Multiple choice', icon: <ListChecks size={15} /> },
                                   { value: 'short', label: 'Short answer', icon: <AlignLeft size={15} /> },
                                   { value: 'long', label: 'Long answer', icon: <FileText size={15} /> }]} />
              <div className="grid-3">
                <label className="field" style={{ gridColumn: 'span 2' }}><span className="lab">Subject</span>
                  <input value={q.subject} onChange={(e) => set({ subject: e.target.value })} placeholder="Engineering Mathematics" /></label>
                <label className="field"><span className="lab">Unit</span>
                  <input type="number" min="1" value={q.unit} onChange={(e) => set({ unit: e.target.value })} /></label>
                <label className="field"><span className="lab">Marks</span>
                  <input type="number" min="1" value={q.marks} onChange={(e) => set({ marks: e.target.value })} /></label>
                <div className="field">
                  <label htmlFor="bloom" className="lab">Bloom level</label>
                  <select id="bloom" aria-describedby="bloom-hint" value={q.bloom} onChange={(e) => set({ bloom: e.target.value })}>{BLOOM.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select>
                  <span className="hint" id="bloom-hint">{BLOOM.find((b) => b[0] === q.bloom)?.[2]}</span>
                </div>
                <label className="field"><span className="lab">Difficulty<span className="val-pill">{Number(q.difficulty).toFixed(2)}</span></span>
                  <div className="range-wrap"><input type="range" min="0" max="1" step="0.05" value={q.difficulty} onChange={(e) => set({ difficulty: e.target.value })} />
                    <div className="range-ends"><span>Easy</span><span>Hard</span></div></div></label>
              </div>
            </div>
          </Card>

          <Card title="The question" icon={PenLine}>
            <div className="stack">
              <div>
                <div className="toolbar" aria-label="Insert maths">
                  {SNIPPETS.map(([n, s]) => <button key={n} type="button" className="chipbtn" onClick={() => insert(s)}>{n}</button>)}
                </div>
                <label className="field"><span className="lab">Question text</span>
                  <textarea ref={area} rows={4} value={q.stem} onChange={(e) => set({ stem: e.target.value })}
                            placeholder="Write the question. Use $...$ for maths, e.g. $x^2 + 1$" /></label>
              </div>

              {mcq && (
                <div className="options-box">
                  <div className="row between"><span className="lab" style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink-2)' }}>Options</span>
                    <span className="hint">Select the correct answer</span></div>
                  {q.options.map((o, i) => (
                    <div className="opt-row" key={i}>
                      <label className={`correct-pick${q.correct === i ? ' on' : ''}`}>
                        <input type="radio" name="correct" checked={q.correct === i} onChange={() => set({ correct: i })} aria-label={`Mark option ${LETTERS[i]} as correct`} />
                        Correct
                      </label>
                      <label className="field"><span className="lab">Option {LETTERS[i]}</span>
                        <input value={o} onChange={(e) => setOption(i, e.target.value)} /></label>
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => removeOption(i)} disabled={q.options.length <= 2}
                              aria-label={`Remove option ${LETTERS[i]}`} style={{ height: 42 }}><X size={16} /></button>
                    </div>
                  ))}
                  <div><button type="button" className="btn btn-secondary btn-sm" onClick={addOption} disabled={q.options.length >= 6}><Plus size={15} />Add option</button></div>
                </div>
              )}

              <label className="field"><span className="lab">Model solution (optional, never printed on the paper)</span>
                <textarea rows={2} value={q.solution} onChange={(e) => set({ solution: e.target.value })} /></label>

              <Issues codes={codes} />
              {touched && problems.length > 0 && (
                <ul className="issues">{problems.map((p) => <li key={p}><span>•</span>{p}</li>)}</ul>
              )}
              <div className="row wrap">
                <button type="button" className="btn btn-primary" onClick={addToBatch} disabled={blocked}><Plus size={16} />Add to batch</button>
                <span className="hint">Add as many questions as you like, then submit the batch once.</span>
              </div>
            </div>
          </Card>
        </div>

        <div className="stack sticky">
          <Card title="Live preview" icon={Eye} iconTone="navy" subtitle="How it will look on the paper">
            <div className="paper">
              <div className="paper-label"><span>Preview</span><span>{q.marks || 0} mark{Number(q.marks) === 1 ? '' : 's'}</span></div>
              {q.stem.trim() ? (
                <div className="preview">
                  <p className="stem"><MathText text={q.stem} /></p>
                  {mcq && <ol className="opts">{q.options.map((o, i) => <li key={i} className={q.correct === i ? 'correct' : ''}><MathText text={o} /></li>)}</ol>}
                  {q.solution.trim() && <div className="solution"><b>Solution:</b> <MathText text={q.solution} /></div>}
                </div>
              ) : <p className="paper-empty">Start typing and your question appears here, typeset.</p>}
            </div>
          </Card>

          <Card title="Your batch" icon={Layers} subtitle={<>{batch.length} question{batch.length === 1 ? '' : 's'} in batch</>}>
            <div className="stack">
              {batch.length === 0 && <Empty icon={Layers}>Questions you add appear here until you submit them.</Empty>}
              {batch.length > 0 && (
                <ol className="batch-list">
                  {batch.map((b, i) => (
                    <li key={i}>
                      <span className="n">{i + 1}</span>
                      <div className="grow">
                        <div className="row wrap" style={{ gap: 6 }}><Badge value={b.qtype} /><span className="tiny muted">{b.subject} · unit {b.unit} · {b.marks} mark{b.marks === 1 ? '' : 's'}</span></div>
                        <div className="small" style={{ marginTop: 4 }}><MathText text={b.stem} /></div>
                      </div>
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => setBatch(batch.filter((_, k) => k !== i))} aria-label={`Remove question ${i + 1}`}><Trash2 size={15} /></button>
                    </li>
                  ))}
                </ol>
              )}
              <label className="check">
                <input type="checkbox" checked={rights} onChange={(e) => setRights(e.target.checked)} />
                <span>I confirm these questions are my own work or I hold the rights to submit them.</span>
              </label>
              <ErrorBox error={error} />
              <button className="btn btn-primary btn-block" onClick={submit} disabled={!batch.length || !rights || busy} style={{ minHeight: 44 }}>
                <Send size={16} />{busy ? 'Submitting…' : 'Submit batch'}
              </button>
            </div>
          </Card>

          {result && (
            <Card title="Processing result" icon={CheckCircle2} iconTone="good">
              <div className="stack">
                <div className="row"><span className="muted small">Status</span><Badge value={result.submission_status} />
                  {result.submission_status !== 'deduplicated' && <span className="hint">checking…</span>}</div>
                {result.questions.length > 0 && (
                  <div className="table-wrap"><table className="table">
                    <thead><tr><th>#</th><th>Outcome</th><th>Details</th></tr></thead>
                    <tbody>{result.questions.map((r) => (
                      <tr key={r.index}><td>{r.index + 1}</td><td><Badge value={r.status} /></td><td><Issues codes={r.issues} /></td></tr>))}</tbody>
                  </table></div>
                )}
                <Alert>Reviewers never see who wrote a question, and you are never told which other question matched.</Alert>
              </div>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
