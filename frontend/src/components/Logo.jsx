import React from 'react';
import { ShieldCheck } from 'lucide-react';

export function LogoMark({ size = 40 }) {
  return (
    <span className="logo" style={{ width: size, height: size }} aria-hidden="true">
      <ShieldCheck size={Math.round(size * 0.55)} strokeWidth={2.2} />
    </span>
  );
}

export default function Brand({ as: Tag = 'div' }) {
  return (
    <Tag className="brand">
      <LogoMark />
      <span>
        <div className="brand-name">SafeExam</div>
        <div className="brand-tag">Zero-trust question papers</div>
      </span>
    </Tag>
  );
}
