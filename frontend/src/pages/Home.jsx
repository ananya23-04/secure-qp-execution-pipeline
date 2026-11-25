import React, { useEffect, useState } from 'react';
import { ArrowRight, ClipboardCheck, Files, FileCheck2, Layers, PenLine, ShieldCheck, Scale, Boxes, Filter, Send } from 'lucide-react';
import { api } from '../lib/api.js';
import { Alert, Badge, Card, Skeleton, PageHeader } from '../components/ui.jsx';

const sum = (o) => Object.values(o || {}).reduce((a, b) => a + b, 0);
const greet = () => { const h = new Date().getHours(); return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'; };
const nameOf = (email) => {
  const n = email.split('@')[0].replace(/[._\-\d]+/g, ' ').trim();
  return n ? n.charAt(0).toUpperCase() + n.slice(1) : 'there';
};
const settled = (r) => (r.status === 'fulfilled' ? r.value : null);

function Stat({ icon: Icon, tone, value, caption }) {
  return (
    <div className="card stat">
      <span className={`icon-tile ${tone || ''}`} style={{ width: 46, height: 46, borderRadius: 13 }}><Icon size={22} /></span>
      <div><div className="num">{value}</div><div className="cap">{caption}</div></div>
    </div>
  );
}

function FacultyBlock() {
  const [rows, setRows] = useState(undefined);
  useEffect(() => { api('/submissions/mine').then(setRows).catch(() => setRows(null)); }, []);
  const last = rows && rows.length ? rows[rows.length - 1] : null;
  return (
    <Card title="Your contributions" subtitle="Questions you have written" icon={PenLine}
          actions={<a className="btn btn-primary btn-sm" href="#/submit"><PenLine size={15} />Write a question</a>}>
      {rows === undefined && <Skeleton />}
      {rows === null && <Alert tone="warn">Could not load your submissions.</Alert>}
      {rows && (
        <div className="grid-3">
          <Stat icon={Files} tone="navy" value={rows.length} caption={rows.length === 1 ? 'submission' : 'submissions'} />
          <Stat icon={Layers} value={rows.reduce((a, r) => a + r.question_count, 0)} caption="questions contributed" />
          <div className="card stat" style={{ boxShadow: 'none' }}>
            <div><div className="cap" style={{ marginTop: 0 }}>Latest</div>
              <div style={{ marginTop: 6 }}>{last ? <Badge value={last.status} /> : <span className="muted small">Nothing yet</span>}</div></div>
          </div>
        </div>
      )}
    </Card>
  );
}

function ReviewerBlock() {
  const [data, setData] = useState(undefined);
  useEffect(() => {
    Promise.allSettled([api('/review/queue?limit=20'), api('/review/mine/history')]).then(([q, h]) => setData({ queue: settled(q), history: settled(h) }));
  }, []);
  const waiting = data?.queue ? data.queue.length : null;
  return (
    <Card title="Peer review" subtitle="Blind: you never see who wrote a question" icon={ClipboardCheck} iconTone="navy"
          actions={<a className="btn btn-secondary btn-sm" href="#/review">Open queue<ArrowRight size={15} /></a>}>
      {data === undefined && <Skeleton />}
      {data && (
        <div className="grid-3">
          <Stat icon={ClipboardCheck} tone="warn" value={waiting === null ? '–' : waiting >= 20 ? '20+' : waiting} caption="waiting in your queue" />
          <Stat icon={ShieldCheck} tone="good" value={data.history ? data.history.length : '–'} caption="reviews completed" />
        </div>
      )}
    </Card>
  );
}

function AdminBlock() {
  const [d, setD] = useState(undefined);
  useEffect(() => {
    Promise.allSettled([api('/pipeline/stats'), api('/moderation/stats'), api('/exams')]).then(([p, m, e]) =>
      setD({ pipe: settled(p), review: settled(m) || {}, exams: settled(e) || [] }));
  }, []);
  if (d === undefined) return <Card title="Pipeline" icon={Boxes}><Skeleton lines={4} /></Card>;
  const q = d.pipe?.questions || {};
  const subs = d.pipe?.submissions || {};
  const ex = (s) => d.exams.filter((e) => e.status === s).length;
  const inProgress = ex('committing') + ex('revealing') + ex('ready');
  const attention = [];
  if (d.review.moderation) attention.push({ href: '#/moderation', text: d.review.moderation > 1 ? `${d.review.moderation} disputed questions need a moderator decision` : '1 disputed question needs a moderator decision' });
  if (ex('generated')) attention.push({ href: '#/exams', text: ex('generated') > 1 ? `${ex('generated')} exams are waiting for custodian release approval` : '1 exam is waiting for custodian release approval' });
  if (q.invalid) attention.push({ href: '#/moderation', text: q.invalid > 1 ? `${q.invalid} questions failed validation` : '1 question failed validation' });

  const stages = [
    { no: 1, icon: Send, title: 'Collection', big: sum(q), unit: 'questions', href: '#/moderation', rows: [['Submissions', sum(subs)]] },
    { no: 2, icon: Filter, title: 'Pre-processing', big: (q.unique || 0) + (q.near_duplicate || 0), unit: 'kept', href: '#/moderation',
      rows: [['Duplicates removed', q.duplicate || 0], ['Near-duplicates tagged', q.near_duplicate || 0], ['Invalid', q.invalid || 0]] },
    { no: 3, icon: Scale, title: 'Peer review', big: d.review.approved || 0, unit: 'approved', href: '#/moderation',
      rows: [['In review pool', d.review.in_pool || 0], ['Needs moderation', d.review.moderation || 0], ['Rejected', d.review.rejected || 0]] },
    { no: 4, icon: Layers, title: 'Set generation', big: d.exams.length, unit: 'exams', href: '#/exams',
      rows: [['In progress', inProgress], ['Sets generated', ex('generated')]] },
    { no: 5, icon: FileCheck2, title: 'Release', big: ex('released'), unit: 'released', href: '#/exams', rows: [['Awaiting approval', ex('generated')]] },
  ];

  return (
    <div className="stack">
      <Card title="Pipeline status" subtitle="Live counts across every stage, from collection to release" icon={Boxes}>
        <div className="pipeline">
          {stages.map((s) => (
            <a key={s.no} className="stage" href={s.href}>
              <div className="row between"><span className="st-no">Stage {s.no}</span><s.icon size={17} color="var(--accent)" /></div>
              <h3>{s.title}</h3>
              <div className="big">{s.big} <span className="muted small" style={{ fontFamily: 'var(--sans)', fontWeight: 500 }}>{s.unit}</span></div>
              <ul>{s.rows.map(([k, v]) => <li key={k}>{k}: <b>{v}</b></li>)}</ul>
            </a>
          ))}
        </div>
      </Card>
      {attention.length > 0 && (
        <Card title="Needs your attention" icon={Scale} iconTone="warn">
          <div className="stack-s">
            {attention.map((a) => <a key={a.text} href={a.href} className="alert warn" style={{ textDecoration: 'none' }}><ArrowRight size={16} /><div>{a.text}</div></a>)}
          </div>
        </Card>
      )}
    </div>
  );
}

export default function Home({ me }) {
  const has = (r) => me.roles.includes(r);
  return (
    <>
      <PageHeader eyebrow={greet()} title={`Welcome back, ${nameOf(me.email)}`}
                  subtitle="Here is where things stand. Every action you take is recorded in a tamper-evident audit log." />
      <div className="stack-l">
        {has('admin') && <AdminBlock />}
        {has('reviewer') && <ReviewerBlock />}
        <FacultyBlock />
      </div>
    </>
  );
}
