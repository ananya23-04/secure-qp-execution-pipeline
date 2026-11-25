import React, { useEffect, useState } from 'react';
import { Files, ListChecks, RefreshCw, ChevronRight, PenLine } from 'lucide-react';
import { api } from '../lib/api.js';
import { Badge, Card, Empty, ErrorBox, Issues, PageHeader, Skeleton } from '../components/ui.jsx';

export default function MySubmissions() {
  const [rows, setRows] = useState(null);
  const [open, setOpen] = useState(null);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  async function load() {
    setError(null);
    try { setRows(await api('/submissions/mine')); } catch (e) { setError(e); }
  }
  useEffect(() => { load(); }, []);

  async function show(id) {
    setOpen(id);
    setReport(null);
    try { setReport(await api(`/submissions/${id}/report`)); } catch (e) { setError(e); }
  }

  return (
    <>
      <PageHeader eyebrow="Contribute" title="My submissions"
                  subtitle="Track how each batch was processed: validated, checked for duplicates, and passed to review."
                  actions={<><button className="btn btn-secondary" onClick={load}><RefreshCw size={15} />Refresh</button>
                    <a className="btn btn-primary" href="#/submit"><PenLine size={15} />Write a question</a></>} />
      <ErrorBox error={error} />
      <div className="cols-main" style={{ marginTop: error ? 16 : 0 }}>
        <Card title="Submissions" icon={Files} flush>
          <div style={{ padding: 22, paddingTop: 16 }}>
            {rows === null && !error && <Skeleton lines={4} />}
            {rows && rows.length === 0 && <Empty icon={Files} title="Nothing submitted yet">Questions you submit will be listed here.</Empty>}
            {rows && rows.length > 0 && (
              <div className="table-wrap"><table className="table">
                <thead><tr><th>Submitted</th><th>Questions</th><th>Status</th><th /></tr></thead>
                <tbody>{rows.map((r) => (
                  <tr key={r.id} className={open === r.id ? 'sel' : ''}>
                    <td>{new Date(r.created_at).toLocaleString()}</td><td>{r.question_count}</td><td><Badge value={r.status} /></td>
                    <td style={{ textAlign: 'right' }}><button className="btn btn-secondary btn-sm" onClick={() => show(r.id)}>Details<ChevronRight size={14} /></button></td>
                  </tr>))}</tbody>
              </table></div>
            )}
          </div>
        </Card>
        <Card title="Per-question outcome" icon={ListChecks} iconTone="navy">
          {!open && <Empty icon={ListChecks} title="Pick a submission">Select one on the left to see how each question was handled.</Empty>}
          {open && !report && <Skeleton />}
          {report && (
            <div className="stack">
              <div className="row wrap">{Object.entries(report.summary).map(([k, v]) => <span key={k} className="row" style={{ gap: 6 }}><Badge value={k} /><b>× {v}</b></span>)}</div>
              <div className="table-wrap"><table className="table">
                <thead><tr><th>#</th><th>Outcome</th><th>Details</th></tr></thead>
                <tbody>{report.questions.map((r) => (
                  <tr key={r.index}><td>{r.index + 1}</td><td><Badge value={r.status} /></td><td><Issues codes={r.issues} /></td></tr>))}</tbody>
              </table></div>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
