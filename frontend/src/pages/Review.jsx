import React, { useCallback, useEffect, useState } from 'react';
import { Check, ClipboardCheck, History, Pencil, RefreshCw, ShieldCheck, ThumbsDown, ThumbsUp, EyeOff } from 'lucide-react';
import { api } from '../lib/api.js';
import { lintLatex } from '../lib/math.js';
import MathText from '../components/MathText.jsx';
import { Alert, Badge, Card, Empty, ErrorBox, Issues, PageHeader, Skeleton, useToast } from '../components/ui.jsx';

const LETTERS = 'ABCDEF';
const QUALITY = ['Poor', 'Weak', 'Fair', 'Good', 'Excellent'];

function QuestionView({ item }) {
  return (
    <div className="paper">
      <div className="paper-label">
        <span className="row" style={{ gap: 6 }}><Badge value={item.qtype} />
          {item.near_duplicate && <Badge tone="warn">Possible near-duplicate</Badge>}</span>
        <span>{item.subject} · unit {item.unit} · {item.bloom} · {item.marks} mark{item.marks === 1 ? '' : 's'}</span>
      </div>
      <p className="stem"><MathText text={item.stem} /></p>
      {item.options && (
        <ol className="opts">
          {item.options.map((o, i) => (
            <li key={i} className={item.correct_option === i ? 'correct' : ''}>
              <span><MathText text={o} /></span>
              {item.correct_option === i && <span className="tick"><Check size={13} />marked correct</span>}
            </li>
          ))}
        </ol>
      )}
      {item.solution_latex && <div className="solution"><b>Author’s solution:</b> <MathText text={item.solution_latex} /></div>}
    </div>
  );
}

function Correction({ item, onSaved }) {
  const [stem, setStem] = useState(item.stem);
  const [options, setOptions] = useState(item.options || []);
  const [correct, setCorrect] = useState(item.correct_option ?? 0);
  const [solution, setSolution] = useState(item.solution_latex || '');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const body = {};
  if (stem !== item.stem) body.stem = stem;
  if (item.options && (JSON.stringify(options) !== JSON.stringify(item.options) || correct !== item.correct_option)) {
    body.options = options;
    body.correct_option = correct;
  }
  if (solution !== (item.solution_latex || '')) body.solution_latex = solution;
  const codes = [...new Set([stem, solution, ...options].flatMap(lintLatex))];

  async function save() {
    setError(null);
    setBusy(true);
    try {
      await api(`/review/${item.question_id}/correction`, { method: 'POST', body });
      onSaved({ ...item, stem, options: item.options ? options : null, correct_option: item.options ? correct : null, solution_latex: solution || null });
    } catch (e) { setError(e); } finally { setBusy(false); }
  }

  return (
    <div className="stack" style={{ background: 'var(--surface-2)', border: '1px dashed var(--line-2)', borderRadius: 14, padding: 16 }}>
      <label className="field"><span className="lab">Question text</span><textarea rows={3} value={stem} onChange={(e) => setStem(e.target.value)} /></label>
      {item.options && options.map((o, i) => (
        <div className="opt-row" key={i}>
          <label className={`correct-pick${correct === i ? ' on' : ''}`}>
            <input type="radio" name="fix-correct" checked={correct === i} onChange={() => setCorrect(i)} aria-label={`Mark option ${LETTERS[i]} as correct`} />Correct
          </label>
          <label className="field"><span className="lab">Option {LETTERS[i]}</span>
            <input value={o} onChange={(e) => setOptions(options.map((x, k) => (k === i ? e.target.value : x)))} /></label>
        </div>
      ))}
      <label className="field"><span className="lab">Solution</span><textarea rows={2} value={solution} onChange={(e) => setSolution(e.target.value)} /></label>
      <div className="small muted">Preview: <MathText text={stem} /></div>
      <Issues codes={codes} />
      <ErrorBox error={error} />
      <div><button className="btn btn-primary btn-sm" onClick={save} disabled={busy || !Object.keys(body).length || codes.length > 0}>Save correction</button></div>
    </div>
  );
}

export default function Review() {
  const toast = useToast();
  const [items, setItems] = useState(null);
  const [history, setHistory] = useState([]);
  const [decision, setDecision] = useState('approve');
  const [quality, setQuality] = useState(4);
  const [difficulty, setDifficulty] = useState(0.5);
  const [comment, setComment] = useState('');
  const [fixing, setFixing] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setItems(await api('/review/queue?limit=5'));
      setHistory(await api('/review/mine/history'));
    } catch (e) { setError(e); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const item = items && items[0];
  const reset = () => { setDecision('approve'); setQuality(4); setDifficulty(0.5); setComment(''); setFixing(false); };

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const r = await api(`/review/${item.question_id}`, {
        method: 'POST', body: { decision, quality: Number(quality), difficulty: Number(difficulty), comment },
      });
      toast(r.status === 'in_pool' ? 'Review recorded. Waiting for another reviewer.' : `Review recorded. The question is now ${r.status.replace('_', ' ')}.`);
      reset();
      const rest = items.slice(1);
      if (rest.length) setItems(rest); else await load();
      setHistory(await api('/review/mine/history'));
    } catch (e) { setError(e); } finally { setBusy(false); }
  }

  return (
    <>
      <PageHeader eyebrow="Peer review" title="Blind review"
                  subtitle="Judge each question on its merits. You cannot see the author, and nobody sees your name."
                  actions={<button className="btn btn-secondary" onClick={load}><RefreshCw size={15} />Refresh queue</button>} />
      <div className="cols-main">
        <Card title="Question to review" icon={ClipboardCheck}
              subtitle={items && item ? <>{items.length} in your queue · author and author’s difficulty rating are hidden from you.</> : undefined}>
          <div className="stack">
            <ErrorBox error={error} />
            {items === null && !error && <Skeleton lines={5} />}
            {items && !item && <Empty icon={ShieldCheck} title="You are all caught up">Nothing to review right now. New questions appear when an admin builds a review pool.</Empty>}
            {item && (
              <>
                <QuestionView item={item} />
                <hr className="sep" />
                <div className="stack-s"><span className="lab" style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink-2)' }}>Your decision</span>
                  <div className="decide" role="radiogroup" aria-label="Decision">
                    <label className={decision === 'approve' ? 'on-good' : ''}>
                      <input type="radio" name="decision" checked={decision === 'approve'} onChange={() => setDecision('approve')} />
                      <ThumbsUp size={20} /><span>Approve<small>Clear, correct and fair</small></span></label>
                    <label className={decision === 'reject' ? 'on-bad' : ''}>
                      <input type="radio" name="decision" checked={decision === 'reject'} onChange={() => setDecision('reject')} />
                      <ThumbsDown size={20} /><span>Reject<small>Unclear, wrong or unsuitable</small></span></label>
                  </div></div>
                <div className="stack-s"><span className="lab" style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink-2)' }}>Quality <span className="muted" style={{ fontWeight: 400 }}>· {QUALITY[quality - 1]}</span></span>
                  <div className="rate" role="radiogroup" aria-label="Quality">
                    {[1, 2, 3, 4, 5].map((n) => (
                      <button key={n} type="button" role="radio" aria-checked={quality === n} aria-label={`Quality ${n}`} onClick={() => setQuality(n)}>{n}</button>))}
                  </div></div>
                <label className="field"><span className="lab">Your difficulty rating<span className="val-pill">{Number(difficulty).toFixed(2)}</span></span>
                  <div className="range-wrap"><input type="range" min="0" max="1" step="0.05" value={difficulty} onChange={(e) => setDifficulty(e.target.value)} />
                    <div className="range-ends"><span>Easy</span><span>Medium</span><span>Hard</span></div></div></label>
                <label className="field"><span className="lab">Comment <span className="muted" style={{ fontWeight: 400 }}>(shown to the moderator, anonymously)</span></span>
                  <textarea rows={2} maxLength={1000} value={comment} onChange={(e) => setComment(e.target.value)} /></label>
                <div className="row wrap">
                  <button className="btn btn-primary" onClick={submit} disabled={busy} style={{ minHeight: 44 }}><Check size={16} />Submit review</button>
                  <button className="btn btn-secondary" onClick={() => setFixing(!fixing)}><Pencil size={15} />{fixing ? 'Close editor' : 'Fix typo / solution'}</button>
                </div>
                {fixing && <Correction key={item.question_id} item={item} onSaved={(n) => { setItems([n, ...items.slice(1)]); setFixing(false); toast('Correction saved and re-validated.'); }} />}
              </>
            )}
          </div>
        </Card>

        <div className="stack">
          <Card title="How blind review works" icon={EyeOff} iconTone="navy">
            <div className="stack-s small muted">
              <p>Each question needs <b style={{ color: 'var(--ink)' }}>two independent reviews</b>. If you both approve with good scores it is accepted; if you disagree it goes to a moderator.</p>
              <p>Your own difficulty rating replaces the author’s estimate, so set it independently.</p>
            </div>
          </Card>
          <Card title="My review history" icon={History} flush>
            <div style={{ padding: '0 22px 22px' }}>
              {history.length === 0 ? <Empty icon={History}>No reviews yet.</Empty> : (
                <div className="table-wrap" style={{ maxHeight: 360, overflowY: 'auto' }}><table className="table">
                  <thead><tr><th>Question</th><th>Decision</th><th>Quality</th></tr></thead>
                  <tbody>{history.map((h) => <tr key={h.question_id}><td className="mono">{h.question_id.slice(0, 8)}</td><td><Badge value={h.decision} /></td><td>{h.quality}</td></tr>)}</tbody>
                </table></div>
              )}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
