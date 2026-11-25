import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, Info, XCircle, Inbox } from 'lucide-react';
import { ISSUE_TEXT } from '../lib/math.js';
import { label, tone } from '../lib/labels.js';

export function PageHeader({ eyebrow, title, subtitle, actions }) {
  return (
    <header className="page-head">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {subtitle && <p className="lede">{subtitle}</p>}
      </div>
      {actions && <div className="row wrap">{actions}</div>}
    </header>
  );
}

export function Card({ title, subtitle, icon: Icon, iconTone, actions, children, flush, className = '' }) {
  return (
    <section className={`card${flush ? ' flush' : ''} ${className}`}>
      {(title || actions) && (
        <header className="card-head" style={flush ? { padding: '18px 22px 0' } : undefined}>
          <div className="card-title">
            {Icon && <span className={`icon-tile ${iconTone || ''}`}><Icon size={18} strokeWidth={2} /></span>}
            <div>
              <h2>{title}</h2>
              {subtitle && <div className="card-sub">{subtitle}</div>}
            </div>
          </div>
          {actions && <div className="row">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

// Status badge: pass a status code (labelled + coloured automatically) or custom children.
export function Badge({ value, tone: t, children, plain }) {
  return <span className={`badge ${t || tone(value)}${plain ? ' plain' : ''}`}>{children ?? label(value)}</span>;
}
export const Chip = Badge; // backwards-compatible alias

const ALERT_ICON = { good: CheckCircle2, bad: XCircle, warn: AlertTriangle, info: Info };

export function Alert({ tone: t = 'info', children }) {
  if (!children) return null;
  const Icon = ALERT_ICON[t] || Info;
  return <div className={`alert ${t}`} role={t === 'bad' ? 'alert' : undefined}><Icon size={17} /><div>{children}</div></div>;
}

export function ErrorBox({ error }) {
  if (!error) return null;
  return <Alert tone="bad">{error.message || String(error)}</Alert>;
}

export function Issues({ codes }) {
  if (!codes || !codes.length) return null;
  return (
    <ul className="issues">
      {codes.map((c) => <li key={c}><AlertTriangle size={14} />{ISSUE_TEXT[c] || c}</li>)}
    </ul>
  );
}

export function Empty({ icon: Icon = Inbox, title, children }) {
  return (
    <div className="empty">
      <span className="icon-tile"><Icon size={22} /></span>
      {title && <strong>{title}</strong>}
      <div>{children}</div>
    </div>
  );
}

export function Skeleton({ lines = 3 }) {
  return (
    <div className="stack-s" aria-busy="true" aria-label="Loading">
      {Array.from({ length: lines }, (_, i) => <div key={i} className="skel" style={{ width: `${92 - i * 14}%`, height: 16 }} />)}
    </div>
  );
}

export function Segmented({ name, value, onChange, options, label: ariaLabel }) {
  return (
    <div className="seg" role="radiogroup" aria-label={ariaLabel}>
      {options.map((o) => (
        <label key={o.value} className={value === o.value ? 'on' : ''}>
          <input type="radio" name={name} value={o.value} checked={value === o.value} onChange={() => onChange(o.value)} />
          {o.icon}{o.label}
        </label>
      ))}
    </div>
  );
}

// ---- toasts ---------------------------------------------------------------------------------
const ToastCtx = createContext(() => {});
const T_ICON = { good: CheckCircle2, bad: XCircle, warn: AlertTriangle, info: Info };

export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const timers = useRef([]);
  useEffect(() => () => timers.current.forEach(clearTimeout), []);
  const push = useCallback((message, t = 'good') => {
    const id = Math.random().toString(36).slice(2);
    setItems((x) => [...x.slice(-3), { id, message, t }]);
    timers.current.push(setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), 5500));
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((i) => { const Icon = T_ICON[i.t] || Info; return <div key={i.id} className={`toast ${i.t}`}><Icon size={18} /><span>{i.message}</span></div>; })}
      </div>
    </ToastCtx.Provider>
  );
}
export const useToast = () => useContext(ToastCtx);
