import React, { useCallback, useEffect, useId, useState } from 'react';
import { BadgeCheck, Check, Download, FileCheck2, Layers, Lock, Plus, RefreshCw, ShieldCheck, Sparkles, Unlock, Users, FileText, Printer, ScanSearch } from 'lucide-react';
import { api, randomHex, sha256Hex } from '../lib/api.js';
import { Alert, Badge, Card, Empty, ErrorBox, PageHeader, Skeleton } from '../components/ui.jsx';

const STEPS = [
  { id: 'committing', name: 'Commit', icon: Lock },
  { id: 'revealing', name: 'Reveal', icon: Unlock },
  { id: 'ready', name: 'Generate', icon: Sparkles },
  { id: 'generated', name: 'Approve release', icon: Users },
  { id: 'released', name: 'Render', icon: Printer },
];
const STEP_HELP = {
  committing: 'Each custodian commits a hidden secret. Nobody can see anyone else’s.',
  revealing: 'All commitments are in. Each custodian now reveals their secret.',
  ready: 'The seed is fixed by every secret together. Generate Sets A/B/C.',
  generated: 'Sets exist as metadata only. Every custodian must approve release before any paper is rendered.',
  released: 'All custodians approved. Render each set to a PDF.',
};

export function parseMarks(text) {
  const out = {};
  for (const part of text.split(',').map((s) => s.trim()).filter(Boolean)) {
    const [u, n] = part.split(':').map((s) => s.trim());
    if (!/^\d+$/.test(u || '') || !/^\d+$/.test(n || '') || Number(n) < 1) throw new Error(`Cannot read "${part}". Use unit:marks pairs like 1:10, 2:10.`);
    out[u] = Number(n);
  }
  if (!Object.keys(out).length) throw new Error('Enter at least one unit:marks pair.');
  return out;
}

export function buildBlueprint(f) {
  const units = parseMarks(f.units);
  const total = Number(f.total_marks);
  if (Object.values(units).reduce((a, b) => a + b, 0) !== total) throw new Error('Unit marks must add up to the total marks.');
  const mix = { easy: Number(f.easy), medium: Number(f.medium), hard: Number(f.hard) };
  if (Math.abs(mix.easy + mix.medium + mix.hard - 1) > 0.01) throw new Error('Easy + medium + hard shares must add up to 1.');
  const bp = {
    subject: f.subject.trim(), num_sets: Number(f.num_sets), total_marks: total, units,
    difficulty_mix: mix, difficulty_tolerance: Number(f.tolerance),
    min_higher_order_pct: Number(f.higher), max_overlap_pct: Number(f.overlap),
  };
  if (f.useTypes) {
    bp.qtype_marks = { mcq: Number(f.mcq), short: Number(f.short), long: Number(f.long) };
    if (bp.qtype_marks.mcq + bp.qtype_marks.short + bp.qtype_marks.long !== total) throw new Error('MCQ + short + long marks must add up to the total marks.');
  }
  return bp;
}

const DEFAULTS = {
  title: 'End-Term Examination', subject: '', num_sets: 3, total_marks: 30, units: '1:10, 2:10, 3:10',
  easy: 0.3, medium: 0.5, hard: 0.2, tolerance: 0.2, higher: 10, overlap: 40,
  useTypes: true, mcq: 5, short: 10, long: 15, commits: 3,
};

// The label holds only the field name; the hint is linked with aria-describedby so screen readers
// announce it as a description rather than as part of the name.
function Field({ label, children, hint }) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id} className="lab">{label}</label>
      {React.cloneElement(children, { id, 'aria-describedby': hint ? `${id}-hint` : undefined })}
      {hint && <span className="hint" id={`${id}-hint`}>{hint}</span>}
    </div>
  );
}

function CreateExam({ onCreated }) {
  const [f, setF] = useState(DEFAULTS);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value });

  let unitSum = null;
  try { unitSum = Object.values(parseMarks(f.units)).reduce((a, b) => a + b, 0); } catch { /* shown on submit */ }
  const mixSum = Number(f.easy) + Number(f.medium) + Number(f.hard);
  const typeSum = Number(f.mcq) + Number(f.short) + Number(f.long);

  async function create(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const r = await api('/exams', { method: 'POST', body: { title: f.title, blueprint: buildBlueprint(f), required_commits: Number(f.commits) } });
      onCreated(r.id);
    } catch (err) { setError(err); } finally { setBusy(false); }
  }

  const ok = (cond) => <Badge tone={cond ? 'good' : 'warn'} plain>{cond ? '✓ adds up' : 'does not add up'}</Badge>;
  return (
    <form className="stack-l" onSubmit={create}>
      <div className="stack">
        <h3 style={{ fontSize: 16 }}>Basics</h3>
        <div className="grid-3">
          <div style={{ gridColumn: 'span 2' }}><Field label="Exam title"><input value={f.title} onChange={set('title')} required minLength={3} /></Field></div>
          <Field label="Subject"><input value={f.subject} onChange={set('subject')} required placeholder="Engineering Mathematics" /></Field>
          <Field label="Number of sets"><input type="number" min="1" max="6" value={f.num_sets} onChange={set('num_sets')} /></Field>
          <Field label="Total marks"><input type="number" min="1" value={f.total_marks} onChange={set('total_marks')} /></Field>
          <Field label="Custodians required" hint="Each uses their own admin account"><input type="number" min="1" max="10" value={f.commits} onChange={set('commits')} /></Field>
        </div>
      </div>
      <div className="stack">
        <h3 style={{ fontSize: 16 }}>Blueprint</h3>
        <Field label="Marks per unit (unit:marks)" hint={<>Total {unitSum ?? '?'} of {f.total_marks} {unitSum !== null && ok(unitSum === Number(f.total_marks))}</>}>
          <input value={f.units} onChange={set('units')} /></Field>
        <div className="grid-3">
          <Field label="Easy share"><input type="number" step="0.05" min="0" max="1" value={f.easy} onChange={set('easy')} /></Field>
          <Field label="Medium share"><input type="number" step="0.05" min="0" max="1" value={f.medium} onChange={set('medium')} /></Field>
          <Field label="Hard share"><input type="number" step="0.05" min="0" max="1" value={f.hard} onChange={set('hard')} /></Field>
        </div>
        <div className="hint">Shares total {mixSum.toFixed(2)} {ok(Math.abs(mixSum - 1) <= 0.01)}</div>
        <div className="grid-3">
          <Field label="Difficulty tolerance"><input type="number" step="0.05" min="0" max="0.5" value={f.tolerance} onChange={set('tolerance')} /></Field>
          <Field label="Min higher-order %"><input type="number" min="0" max="100" value={f.higher} onChange={set('higher')} /></Field>
          <Field label="Max overlap between sets %"><input type="number" min="0" max="100" value={f.overlap} onChange={set('overlap')} /></Field>
        </div>
        <label className="check"><input type="checkbox" checked={f.useTypes} onChange={set('useTypes')} /><span>Fix marks per question type</span></label>
        {f.useTypes && (
          <>
            <div className="grid-3">
              <Field label="MCQ marks"><input type="number" min="0" value={f.mcq} onChange={set('mcq')} /></Field>
              <Field label="Short-answer marks"><input type="number" min="0" value={f.short} onChange={set('short')} /></Field>
              <Field label="Long-answer marks"><input type="number" min="0" value={f.long} onChange={set('long')} /></Field>
            </div>
            <div className="hint">Types total {typeSum} {ok(typeSum === Number(f.total_marks))}</div>
          </>
        )}
      </div>
      <ErrorBox error={error} />
      <div><button className="btn btn-primary" disabled={busy} style={{ minHeight: 44 }}><Check size={16} />Create exam</button></div>
    </form>
  );
}

function Stacked({ items, palette }) {
  const total = items.reduce((a, [, v]) => a + v, 0) || 1;
  return (
    <>
      <div className="bar">{items.map(([k, v], i) => v > 0 && <i key={k} className={palette(i, k)} style={{ width: `${(v / total) * 100}%` }} title={`${k}: ${v}`} />)}</div>
      <div className="legend">{items.map(([k, v], i) => <span key={k}><b className={palette(i, k)} />{k} · {v}</span>)}</div>
    </>
  );
}

function SetCard({ label, s, exam, run, busy, note }) {
  const released = exam.status === 'released';
  const d = s.marks_by_difficulty;
  return (
    <div className="setcard">
      <div className="row between">
        <div className="row" style={{ gap: 12 }}><span className="setletter">{label}</span>
          <div><h3 style={{ fontSize: 18 }}>Set {label}</h3><div className="small muted">{s.questions} questions · {s.total_marks} marks</div></div></div>
      </div>
      <div><div className="tiny muted" style={{ fontWeight: 600, marginBottom: 6 }}>MARKS BY UNIT</div>
        <Stacked items={Object.entries(s.marks_by_unit).map(([u, m]) => [`Unit ${u}`, m])} palette={(i) => `c${i % 3}`} /></div>
      <div><div className="tiny muted" style={{ fontWeight: 600, marginBottom: 6 }}>DIFFICULTY</div>
        <Stacked items={[['easy', d.easy], ['medium', d.medium], ['hard', d.hard]]} palette={(i, k) => `d-${k}`} /></div>
      <div><div className="tiny muted" style={{ fontWeight: 600, marginBottom: 6 }}>QUESTION TYPES</div>
        <Stacked items={Object.entries(s.marks_by_qtype)} palette={(i) => `c${3 + (i % 3)}`} /></div>
      <div className="row between small"><span className="muted">Content hash</span><span className="hash" title="Fingerprint of this set's questions">{s.paper_hash.slice(0, 12)}</span></div>
      {released ? (
        <div className="row wrap">
          <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => run(`Rendered set ${label}`, () => api(`/exams/${exam.id}/papers/${label}/render`, { method: 'POST' }))}>Render</button>
          <button className="btn btn-secondary btn-sm" disabled={busy} onClick={() => run(null, async () => {
            const res = await api(`/exams/${exam.id}/papers/${label}/pdf`, { raw: true });
            const url = URL.createObjectURL(await res.blob());
            const a = document.createElement('a');
            a.href = url; a.download = `SafeExam_Set_${label}.pdf`; a.click();
            setTimeout(() => URL.revokeObjectURL(url), 5000);
          })}><Download size={14} />Download PDF</button>
          <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => run(null, async () => {
            const v = await api(`/exams/${exam.id}/papers/${label}/render-verify`);
            note(`Set ${label} re-render check`, v.reproducible ? 'Re-rendered byte-for-byte identical.' : `Mismatch: ${JSON.stringify(v)}`, v.reproducible);
          })}>Verify</button>
        </div>
      ) : <div className="hint">Rendering unlocks after every custodian approves release.</div>}
    </div>
  );
}

function ExamDetail({ id, me }) {
  const [exam, setExam] = useState(null);
  const [error, setError] = useState(null);
  const [notes, setNotes] = useState([]);
  const [busy, setBusy] = useState(false);
  const secretKey = `safeexam.secret.${id}.${me.email}`;

  const load = useCallback(async () => {
    try { setExam(await api(`/exams/${id}`)); } catch (e) { setError(e); }
  }, [id]);
  useEffect(() => { setExam(null); setNotes([]); setError(null); load(); }, [load]);

  const note = (title, text, ok = true) => setNotes((n) => [{ title, text, ok, k: Math.random() }, ...n].slice(0, 4));

  async function run(success, fn) {
    setError(null);
    setBusy(true);
    try {
      await fn();
      if (success) note(success, '', true);
      await load();
    } catch (e) { setError(e); } finally { setBusy(false); }
  }

  const commit = () => run('Committed. Your secret is stored in this browser until you reveal it.', async () => {
    const secret = localStorage.getItem(secretKey) || `secret-${randomHex(16)}`;
    localStorage.setItem(secretKey, secret);
    await api(`/exams/${id}/commit`, { method: 'POST', body: { commitment: await sha256Hex(secret) } });
  });
  const reveal = () => run('Secret revealed.', async () => {
    let secret = localStorage.getItem(secretKey);
    if (!secret) secret = window.prompt('No secret is stored in this browser. Paste the secret you committed with:') || '';
    if (!secret) throw new Error('A secret is required to reveal.');
    await api(`/exams/${id}/reveal`, { method: 'POST', body: { secret } });
  });

  if (!exam) return <Card title="Exam" icon={FileCheck2}>{error ? <ErrorBox error={error} /> : <Skeleton lines={4} />}</Card>;
  const stepIdx = STEPS.findIndex((s) => s.id === exam.status);
  const bp = exam.blueprint;
  const approvals = exam.release_approvals ?? 0;
  const dots = (n, of) => <span className="dots">{Array.from({ length: of }, (_, i) => <i key={i} className={i < n ? 'on' : ''} />)}</span>;

  return (
    <div className="stack">
      <Card title={exam.title} icon={FileCheck2} subtitle={`${exam.subject} · ${bp.num_sets} sets · ${bp.total_marks} marks`}
            actions={<><Badge value={exam.status} /><button className="btn btn-ghost btn-sm" onClick={load} aria-label="Refresh"><RefreshCw size={15} /></button></>}>
        <div className="stack">
          <ol className="stepper" aria-label="Exam progress" style={{ listStyle: 'none', padding: 0 }}>
            {STEPS.map((s, i) => (
              <li key={s.id} className={`step${i < stepIdx ? ' done' : i === stepIdx ? ' now' : ''}`}>
                <span className="dot">{i < stepIdx ? <Check size={17} /> : <s.icon size={16} />}</span><span className="name">{s.name}</span>
              </li>
            ))}
          </ol>
          <p className="muted">{STEP_HELP[exam.status]}</p>
          <div className="grid-3">
            <div className="card" style={{ boxShadow: 'none', background: 'var(--surface-2)', padding: 14 }}>
              <div className="tiny muted" style={{ fontWeight: 600 }}>COMMITMENTS</div>
              <div className="row" style={{ marginTop: 6 }}>{dots(exam.commits, exam.required_commits)}<b>{exam.commits}/{exam.required_commits}</b></div></div>
            <div className="card" style={{ boxShadow: 'none', background: 'var(--surface-2)', padding: 14 }}>
              <div className="tiny muted" style={{ fontWeight: 600 }}>REVEALED</div>
              <div className="row" style={{ marginTop: 6 }}>{dots(exam.revealed, Math.max(exam.commits, 1))}<b>{exam.revealed}/{exam.commits}</b></div></div>
            <div className="card" style={{ boxShadow: 'none', background: 'var(--surface-2)', padding: 14 }}>
              <div className="tiny muted" style={{ fontWeight: 600 }}>RELEASE APPROVALS</div>
              <div className="row" style={{ marginTop: 6 }}>{dots(approvals, exam.required_commits)}<b>{approvals}/{exam.required_commits}</b></div></div>
          </div>
          {exam.seed && <div className="small"><span className="muted">Seed </span><span className="hash" style={{ wordBreak: 'break-all' }}>{exam.seed}</span></div>}
          <ErrorBox error={error} />
          {notes.map((n) => <Alert key={n.k} tone={n.ok ? 'good' : 'bad'}>{n.title}{n.text ? `: ${n.text}` : ''}</Alert>)}
          <div className="row wrap">
            {exam.status === 'committing' && <button className="btn btn-primary" disabled={busy} onClick={commit}><Lock size={15} />Commit my secret</button>}
            {exam.status === 'revealing' && <button className="btn btn-primary" disabled={busy} onClick={reveal}><Unlock size={15} />Reveal my secret</button>}
            {exam.status === 'ready' && <button className="btn btn-primary" disabled={busy} onClick={() => run('Sets generated.', () => api(`/exams/${id}/generate`, { method: 'POST' }))}><Sparkles size={15} />Generate sets (CP-SAT)</button>}
            {exam.status === 'generated' && <button className="btn btn-primary" disabled={busy} onClick={() => run('Your release approval was recorded.', () => api(`/exams/${id}/release`, { method: 'POST' }))}><BadgeCheck size={16} />Approve release</button>}
            {(exam.status === 'generated' || exam.status === 'released') && (
              <button className="btn btn-secondary" disabled={busy} onClick={() => run(null, async () => {
                const v = await api(`/exams/${id}/verify`);
                const ok = v.seed_ok && v.constraints_ok && v.reproducible;
                note('Exam verification', `seed ${v.seed_ok ? 'ok' : 'BAD'} · constraints ${v.constraints_ok ? 'ok' : 'BAD'} · reproducible ${v.reproducible ? 'yes' : 'NO'}`, ok);
              })}><ScanSearch size={15} />Verify seed, constraints and reproducibility</button>
            )}
          </div>
          {(exam.status === 'committing' || exam.status === 'revealing') && (
            <p className="hint">Each custodian must use a different admin account, in their own browser tab or window.</p>
          )}
        </div>
      </Card>
      {Object.keys(exam.sets || {}).length > 0 && (
        <Card title="Generated sets" icon={Layers} iconTone="navy" subtitle="Question text stays encrypted. These are marks and hashes only until release.">
          <div className="grid-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(215px, 1fr))' }}>
            {Object.entries(exam.sets).map(([l, s]) => <SetCard key={l} label={l} s={s} exam={exam} run={run} busy={busy} note={note} />)}
          </div>
        </Card>
      )}
    </div>
  );
}

export default function Exams({ me }) {
  const [list, setList] = useState(null);
  const [sel, setSel] = useState(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try { setList(await api('/exams')); } catch (e) { setError(e); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <>
      <PageHeader eyebrow="Administration" title="Exams"
                  subtitle="Build a blueprint, fix the seed with every custodian’s secret, generate parallel sets, and release them for rendering only when everyone approves." />
      <div className="cols-side">
        <Card title="Your exams" icon={FileText} actions={<button className="btn btn-primary btn-sm" onClick={() => { setCreating(true); setSel(null); }}><Plus size={15} />New exam</button>}>
          <ErrorBox error={error} />
          {list === null && !error && <Skeleton lines={3} />}
          {list && list.length === 0 && <Empty icon={FileText} title="No exams yet">Create one from a blueprint. You need enough approved questions in the bank.</Empty>}
          <div className="stack-s">
            {(list || []).map((e) => (
              <button key={e.id} className={`listbtn${sel === e.id ? ' active' : ''}`} onClick={() => { setSel(e.id); setCreating(false); }}>
                <span className="t">{e.title}</span><Badge value={e.status} />
              </button>
            ))}
          </div>
        </Card>
        <div>
          {creating && <Card title="New exam blueprint" icon={Plus}><CreateExam onCreated={(id) => { setCreating(false); setSel(id); load(); }} /></Card>}
          {!creating && sel && <ExamDetail id={sel} me={me} />}
          {!creating && !sel && <Card title="Exam generation" icon={ShieldCheck} iconTone="good"><Empty icon={FileCheck2} title="Select or create an exam">The lifecycle, custodian progress and generated sets appear here.</Empty></Card>}
        </div>
      </div>
    </>
  );
}
