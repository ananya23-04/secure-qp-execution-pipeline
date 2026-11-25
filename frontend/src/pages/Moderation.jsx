import React, { useCallback, useEffect, useState } from 'react';
import { Boxes, Copy, Dices, Fingerprint, Gavel, ShieldCheck, ThumbsDown, ThumbsUp } from 'lucide-react';
import { api } from '../lib/api.js';
import MathText from '../components/MathText.jsx';
import { Alert, Badge, Card, Empty, ErrorBox, PageHeader, Skeleton, useToast } from '../components/ui.jsx';

export function parseUnits(text) {
  const out = {};
  for (const part of text.split(',').map((s) => s.trim()).filter(Boolean)) {
    const [u, n] = part.split(':').map((s) => s.trim());
    if (!/^\d+$/.test(u || '') || !/^\d+$/.test(n || '') || Number(n) < 1) throw new Error(`Cannot read "${part}". Use unit:count pairs like 1:10, 2:10.`);
    out[u] = Number(n);
  }
  if (!Object.keys(out).length) throw new Error('Enter at least one unit:count pair.');
  return out;
}

function Counts({ data, empty = 'None yet' }) {
  const entries = Object.entries(data || {});
  if (!entries.length) return <span className="muted small">{empty}</span>;
  return (
    <div className="kv">
      {entries.map(([k, v]) => <div key={k}><Badge value={k} /><strong style={{ fontFamily: 'var(--serif)', fontSize: 22 }}>{v}</strong></div>)}
    </div>
  );
}

export default function Moderation() {
  const toast = useToast();
  const [stats, setStats] = useState(null);
  const [pipe, setPipe] = useState(null);
  const [queue, setQueue] = useState(null);
  const [dups, setDups] = useState([]);
  const [error, setError] = useState(null);
  const [subject, setSubject] = useState('');
  const [units, setUnits] = useState('1:10, 2:10, 3:10');
  const [seed, setSeed] = useState('');
  const [audit, setAudit] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setStats(await api('/moderation/stats'));
      setPipe(await api('/pipeline/stats'));
      setQueue(await api('/moderation/queue'));
      setDups(await api('/pipeline/duplicates'));
    } catch (e) { setError(e); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function build(e) {
    e.preventDefault();
    setError(null);
    try {
      const body = { subject, units: parseUnits(units) };
      if (seed.trim()) body.seed = Number(seed);
      const r = await api('/moderation/pool/build', { method: 'POST', body });
      const short = Object.keys(r.shortfall).length ? ` Short by: ${JSON.stringify(r.shortfall)}.` : '';
      toast(`Pool built: ${r.selected} question(s) sampled.${short}`, short ? 'warn' : 'good');
      load();
    } catch (err) { setError(err); }
  }

  async function decide(id, decision) {
    setError(null);
    try {
      await api(`/moderation/${id}/decide`, { method: 'POST', body: { decision } });
      toast(`Question ${decision === 'approve' ? 'approved' : 'rejected'}.`);
      load();
    } catch (err) { setError(err); }
  }

  return (
    <>
      <PageHeader eyebrow="Administration" title="Moderation"
                  subtitle="Sample review pools, resolve reviewer disagreements, and keep an eye on duplicates and the audit trail." />
      <div className="stack-l">
        <ErrorBox error={error} />
        <div className="grid-3">
          <Card title="Questions by processing outcome" icon={Boxes}>{pipe ? <Counts data={pipe.questions} /> : <Skeleton lines={2} />}</Card>
          <Card title="Review pool status" icon={Gavel} iconTone="navy">{stats ? <Counts data={stats} /> : <Skeleton lines={2} />}</Card>
          <Card title="Audit log integrity" icon={Fingerprint} iconTone="good"
                actions={<button className="btn btn-secondary btn-sm" onClick={async () => { try { setAudit(await api('/moderation/audit/verify')); } catch (e) { setError(e); } }}>Verify chain</button>}>
            {!audit && <p className="muted small">Checks that no past event was altered or removed.</p>}
            {audit && (audit.ok
              ? <Alert tone="good">Chain intact: {audit.length} events.</Alert>
              : <Alert tone="bad">Chain broken at event {audit.broken_at}.</Alert>)}
          </Card>
        </div>

        <div className="grid-2">
          <Card title="Build an anonymous review pool" icon={Dices} subtitle="A random, unit-balanced sample goes to the blind panel">
            <form className="stack" onSubmit={build}>
              <label className="field"><span className="lab">Subject</span>
                <input value={subject} onChange={(e) => setSubject(e.target.value)} required placeholder="Engineering Mathematics" /></label>
              <label className="field"><span className="lab">Questions per unit (unit:count)</span>
                <input value={units} onChange={(e) => setUnits(e.target.value)} /></label>
              <label className="field"><span className="lab">Seed (optional, for reproducible demos)</span>
                <input value={seed} onChange={(e) => setSeed(e.target.value)} inputMode="numeric" /></label>
              <button className="btn btn-primary"><Dices size={16} />Sample random pool</button>
            </form>
          </Card>
          <Card title="Possible duplicates" icon={Copy} iconTone="warn" subtitle="Found by the dedup engine (IDs only, no text)">
            {dups.length === 0 ? <Empty icon={ShieldCheck} title="All clear">No duplicates flagged.</Empty> : (
              <div className="table-wrap"><table className="table">
                <thead><tr><th>Question</th><th>Type</th><th>Similarity</th></tr></thead>
                <tbody>{dups.map((d) => <tr key={d.question_id}><td className="mono">{d.question_id.slice(0, 8)}</td><td><Badge value={d.status} /></td><td>{d.similarity}</td></tr>)}</tbody>
              </table></div>
            )}
          </Card>
        </div>

        <Card title={`Moderation queue (${queue ? queue.length : 0})`} icon={Gavel} iconTone="warn" subtitle="Questions where reviewers disagreed or scored low">
          {queue && queue.length === 0 && <Empty icon={ShieldCheck} title="Nothing to decide">Reviewer disagreements land here.</Empty>}
          <div className="stack">
            {queue && queue.map((q) => (
              <article key={q.question_id} className="card" style={{ background: 'var(--surface-2)', boxShadow: 'none' }}>
                <div className="row wrap" style={{ marginBottom: 10 }}><Badge value={q.qtype} />
                  <span className="small muted">{q.subject} · unit {q.unit} · {q.marks} mark(s) · author’s difficulty {Number(q.difficulty).toFixed(2)}</span></div>
                <p className="stem"><MathText text={q.stem} /></p>
                {q.options && <ol className="opts">{q.options.map((o, i) => <li key={i} className={q.correct_option === i ? 'correct' : ''}><MathText text={o} /></li>)}</ol>}
                <div className="table-wrap" style={{ margin: '14px 0', background: '#fff' }}><table className="table">
                  <thead><tr><th>Reviewer</th><th>Decision</th><th>Quality</th><th>Difficulty</th><th>Comment</th></tr></thead>
                  <tbody>{q.reviews.map((r) => <tr key={r.reviewer}><td><b>{r.reviewer}</b></td><td><Badge value={r.decision} /></td><td>{r.quality}</td>
                    <td>{Number(r.difficulty).toFixed(2)}</td><td>{r.comment || <span className="faint">–</span>}</td></tr>)}</tbody>
                </table></div>
                <div className="row wrap">
                  <button className="btn btn-good" onClick={() => decide(q.question_id, 'approve')}><ThumbsUp size={15} />Approve</button>
                  <button className="btn btn-danger" onClick={() => decide(q.question_id, 'reject')}><ThumbsDown size={15} />Reject</button>
                </div>
              </article>
            ))}
          </div>
        </Card>
      </div>
    </>
  );
}
