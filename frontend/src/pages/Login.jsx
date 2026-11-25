import React, { useState } from 'react';
import { Eye, EyeOff, EyeOff as Blind, KeyRound, Fingerprint, ShieldCheck, ArrowRight } from 'lucide-react';
import { api, setToken } from '../lib/api.js';
import { ErrorBox, Alert } from '../components/ui.jsx';
import Brand from '../components/Logo.jsx';

const FEATURES = [
  { icon: Blind, title: 'Blind peer review', text: 'Reviewers see the question, never the author. Disagreements go to a moderator, anonymously.' },
  { icon: KeyRound, title: 'Custodian-approved release', text: 'No paper is rendered until every custodian has approved. The seed is committed before it is known.' },
  { icon: Fingerprint, title: 'Tamper-evident audit trail', text: 'Every action is hash-chained. Altering history breaks the chain and is detected.' },
];

export default function Login({ onLoggedIn }) {
  const [mode, setMode] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [institution, setInstitution] = useState('');
  const [show, setShow] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState('');

  async function submit(e) {
    e.preventDefault();
    setError(null);
    setInfo('');
    setBusy(true);
    try {
      if (mode === 'register') {
        const r = await api('/auth/register', { method: 'POST', body: { email, password, institution } });
        setInfo(`Account created. Reviewers will only ever see you as ${r.pseudonym}.`);
      }
      const t = await api('/auth/login', { method: 'POST', body: { email, password } });
      setToken(t.access_token);
      onLoggedIn();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const login = mode === 'login';
  return (
    <div className="auth">
      <aside className="auth-art">
        <Brand />
        <div>
          <div className="sheets" aria-hidden="true">
            <div className="sheet"><i /><i className="s" /><i className="a" /><i /><i className="s" /></div>
            <div className="sheet"><i className="a" /><i /><i /><i className="s" /><i /></div>
            <div className="sheet"><i /><i className="s" /><i /><i className="a" /><i /><span className="seal"><ShieldCheck size={20} /></span></div>
          </div>
          <h1>Question papers that <em>cannot leak.</em></h1>
          <p className="lede">From the first draft to the exam hall, every step is blind, approved by several custodians, and recorded.</p>
        </div>
        <div className="stack">
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <div className="feature" key={title}>
              <span className="icon-tile"><Icon size={18} /></span>
              <div><h3>{title}</h3><p>{text}</p></div>
            </div>
          ))}
        </div>
      </aside>

      <main className="auth-form">
        <div className="auth-card stack-l">
          <div>
            <h2>{login ? 'Welcome back' : 'Create your account'}</h2>
            <p className="muted" style={{ marginTop: 4 }}>{login ? 'Sign in to continue to SafeExam.' : 'Faculty accounts can write and submit questions.'}</p>
          </div>
          <form onSubmit={submit} className="stack">
            <div className="field">
              <label htmlFor="email" className="lab" style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink-2)' }}>Email</label>
              <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="username" placeholder="name@university.edu" />
            </div>
            <div className="field">
              <label htmlFor="password" className="lab" style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink-2)' }}>Password</label>
              <div className="pw">
                <input id="password" type={show ? 'text' : 'password'} value={password} onChange={(e) => setPassword(e.target.value)} required minLength={10}
                       autoComplete={login ? 'current-password' : 'new-password'} placeholder="At least 10 characters" />
                <button type="button" onClick={() => setShow(!show)} aria-label={show ? 'Hide password' : 'Show password'}>
                  {show ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>
            </div>
            {!login && (
              <div className="field">
                <label htmlFor="inst" className="lab" style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink-2)' }}>Institution</label>
                <input id="inst" value={institution} onChange={(e) => setInstitution(e.target.value)} required minLength={2} placeholder="Your university or department" />
              </div>
            )}
            <ErrorBox error={error} />
            <Alert tone="good">{info}</Alert>
            <button className="btn btn-primary btn-block" disabled={busy} style={{ minHeight: 46 }}>
              {busy ? 'Please wait…' : login ? 'Sign in' : 'Create account'}{!busy && <ArrowRight size={16} />}
            </button>
          </form>
          <p className="muted small">
            {login ? 'New contributor? ' : 'Already registered? '}
            <button type="button" className="link-btn" onClick={() => { setMode(login ? 'register' : 'login'); setError(null); setInfo(''); }}>
              {login ? 'Create an account' : 'Sign in instead'}
            </button>
          </p>
        </div>
      </main>
    </div>
  );
}
