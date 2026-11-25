import React, { useCallback, useEffect, useState } from 'react';
import { ClipboardCheck, FileCheck2, Files, LayoutDashboard, LogOut, Menu, PenLine, Scale, X } from 'lucide-react';
import { api, getToken, setToken } from './lib/api.js';
import Brand, { LogoMark } from './components/Logo.jsx';
import { Badge, ToastProvider } from './components/ui.jsx';
import Login from './pages/Login.jsx';
import Home from './pages/Home.jsx';
import Submit from './pages/Submit.jsx';
import MySubmissions from './pages/MySubmissions.jsx';
import Review from './pages/Review.jsx';
import Moderation from './pages/Moderation.jsx';
import Exams from './pages/Exams.jsx';

const SECTIONS = [
  { label: null, items: [{ id: 'home', label: 'Overview', icon: LayoutDashboard, roles: ['faculty'], view: (me) => <Home me={me} /> }] },
  { label: 'Contribute', items: [
    { id: 'submit', label: 'Submit questions', icon: PenLine, roles: ['faculty'], view: () => <Submit /> },
    { id: 'mine', label: 'My submissions', icon: Files, roles: ['faculty'], view: () => <MySubmissions /> },
  ] },
  { label: 'Peer review', items: [{ id: 'review', label: 'Review', icon: ClipboardCheck, roles: ['reviewer'], view: () => <Review /> }] },
  { label: 'Administration', items: [
    { id: 'moderation', label: 'Moderation', icon: Scale, roles: ['admin'], view: () => <Moderation /> },
    { id: 'exams', label: 'Exams', icon: FileCheck2, roles: ['admin'], view: (me) => <Exams me={me} /> },
  ] },
];

const fromHash = () => window.location.hash.replace(/^#\/?/, '');
const initials = (email) => email.split('@')[0].replace(/[^a-z]/gi, '').slice(0, 2).toUpperCase() || '?';

function Shell() {
  const [me, setMe] = useState(null);
  const [booting, setBooting] = useState(!!getToken());
  const [tab, setTab] = useState(fromHash());
  const [open, setOpen] = useState(false);

  const loadMe = useCallback(async () => {
    try { setMe(await api('/auth/me')); } catch { setToken(null); setMe(null); } finally { setBooting(false); }
  }, []);

  useEffect(() => { if (getToken()) loadMe(); }, [loadMe]);
  useEffect(() => {
    const on = () => { setTab(fromHash()); setOpen(false); window.scrollTo?.(0, 0); };
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);

  if (booting) return <div className="boot">Loading…</div>;
  if (!me) return <Login onLoggedIn={() => { setBooting(true); loadMe(); }} />;

  const sections = SECTIONS.map((s) => ({ ...s, items: s.items.filter((i) => i.roles.some((r) => me.roles.includes(r))) })).filter((s) => s.items.length);
  const all = sections.flatMap((s) => s.items);
  const current = all.find((t) => t.id === tab) || all[0];

  return (
    <div className="app">
      <div className={`scrim${open ? ' open' : ''}`} onClick={() => setOpen(false)} />
      <aside className={`sidebar${open ? ' open' : ''}`} aria-label="Main navigation">
        <Brand as="a" />
        <nav className="nav">
          {sections.map((s) => (
            <React.Fragment key={s.label || 'top'}>
              {s.label && <div className="nav-label">{s.label}</div>}
              {s.items.map((t) => (
                <a key={t.id} href={`#/${t.id}`} aria-current={t.id === current.id ? 'page' : undefined}>
                  <t.icon size={18} />{t.label}
                </a>
              ))}
            </React.Fragment>
          ))}
        </nav>
        <div className="usercard">
          <div className="usercard-top">
            <span className="avatar">{initials(me.email)}</span>
            <div className="email">{me.email}</div>
          </div>
          <div className="roles">{me.roles.map((r) => <Badge key={r} tone="accent" plain>{r}</Badge>)}</div>
          <button className="btn btn-secondary btn-sm btn-block" style={{ marginTop: 12 }} onClick={() => { setToken(null); setMe(null); window.location.hash = ''; }}>
            <LogOut size={15} />Sign out
          </button>
        </div>
      </aside>
      <div>
        <div className="mobilebar">
          <button className="btn btn-secondary btn-sm" onClick={() => setOpen(!open)} aria-label="Toggle navigation">{open ? <X size={17} /> : <Menu size={17} />}</button>
          <LogoMark size={30} /><strong style={{ fontFamily: 'var(--serif)', fontSize: 18 }}>SafeExam</strong>
        </div>
        <main className="main-inner">{current.view(me)}</main>
      </div>
    </div>
  );
}

export default function App() {
  return <ToastProvider><Shell /></ToastProvider>;
}
