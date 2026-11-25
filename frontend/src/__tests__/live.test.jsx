// Integration test: runs the real portal components against a REAL running backend.
//   SAFEEXAM_LIVE_URL=http://localhost:8000 npx vitest run src/__tests__/live.test.jsx
// Needs the demo data (python -m app.demo_seed). Skipped when the variable is not set.
import React from 'react';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import App from '../App.jsx';

const BASE = process.env.SAFEEXAM_LIVE_URL;
const PASSWORD = 'DemoPass12345';
const suite = BASE ? describe : describe.skip;

async function tokenFor(email) {
  const r = await globalThis.__realFetch(new URL('/auth/login', BASE), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password: PASSWORD }),
  });
  expect(r.status).toBe(200);
  return (await r.json()).access_token;
}
async function loginAs(email) {
  sessionStorage.setItem('safeexam.token', await tokenFor(email));
}

suite('portal against the live API', () => {
  beforeAll(() => {
    globalThis.__realFetch = globalThis.fetch;
    globalThis.fetch = (u, o) => globalThis.__realFetch(new URL(u, BASE), o);   // portal uses relative URLs
  });
  afterAll(() => { globalThis.fetch = globalThis.__realFetch; });

  const T = { timeout: 60000 };

  it('faculty: lists submissions, shows outcomes, and submits a new question through the form', async () => {
    await loginAs('faculty1@juit.ac.in');
    render(<App />);
    fireEvent.click(await screen.findByRole('link', { name: 'My submissions' }, T));
    const rows = await screen.findAllByText('Details', {}, T);
    fireEvent.click(rows[0]);
    expect((await screen.findAllByText('Unique', {}, T)).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('link', { name: 'Submit questions' }));
    fireEvent.change(await screen.findByLabelText('Subject'), { target: { value: 'Engineering Mathematics' } });
    const n = 2 + Math.floor(Math.random() * 9000);                         // a new question every run (dedup would drop repeats)
    fireEvent.change(screen.getByLabelText('Question text'), { target: { value: `Compute $\\int_0^1 ${n}x^{${n - 1}}\\,dx$ and justify each step of the working.` } });
    fireEvent.click(screen.getByLabelText('Mark option A as correct'));
    ['$1$', '$2$', '$3$', '$0$'].forEach((v, i) => fireEvent.change(screen.getByLabelText(`Option ${'ABCD'[i]}`), { target: { value: v } }));
    fireEvent.click(screen.getByRole('button', { name: 'Add to batch' }));
    fireEvent.click(screen.getByLabelText(/I confirm these questions/));
    fireEvent.click(screen.getByRole('button', { name: 'Submit batch' }));
    await screen.findByText('Processing result', {}, T);
    await waitFor(() => expect(screen.queryAllByText(/^(Unique|Near-duplicate)$/).length).toBeGreaterThan(0), T);
    expect(screen.queryAllByText('Invalid')).toHaveLength(0);
  }, 120000);

  it('reviewer: sees an anonymous queue item and submits a review', async () => {
    // an admin samples the question faculty1 just submitted into a fresh review pool
    const adminTok = await tokenFor('you@juit.ac.in');
    const pool = await globalThis.fetch('/moderation/pool/build', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${adminTok}` },
      body: JSON.stringify({ subject: 'Engineering Mathematics', units: { 1: 1 } }),
    });
    expect((await pool.json()).selected).toBe(1);
    await loginAs('reviewer1@juit.ac.in');
    render(<App />);
    fireEvent.click(await screen.findByRole('link', { name: 'Review' }, T));
    await screen.findByText(/author and author’s difficulty rating are hidden/, {}, T);
    expect(document.body.textContent).not.toMatch(/FAC-[0-9A-F]{12}/);
    fireEvent.click(screen.getByRole('button', { name: 'Submit review' }));
    await screen.findByText(/Review recorded/, {}, T);
  }, 120000);

  it('admin: moderation dashboard loads stats, pool builder and audit check', async () => {
    await loginAs('you@juit.ac.in');
    render(<App />);
    fireEvent.click(await screen.findByRole('link', { name: 'Moderation' }, T));
    await screen.findByText('Questions by processing outcome', {}, T);
    await screen.findByText(/Moderation queue/, {}, T);
    fireEvent.click(screen.getByRole('button', { name: 'Verify chain' }));
    await screen.findByText(/Chain intact/, {}, T);
  }, 120000);

  it('admin: drives a whole exam in the UI - commit, reveal, generate, release, render, verify', async () => {
    await loginAs('you@juit.ac.in');
    render(<App />);
    fireEvent.click(await screen.findByRole('link', { name: 'Exams' }, T));
    await screen.findByText(/Demo End-Term/, {}, T);                         // exam from the seeder is listed
    fireEvent.click(screen.getByRole('button', { name: 'New exam' }));
    fireEvent.change(await screen.findByLabelText('Exam title'), { target: { value: 'UI Driven Exam' } });
    fireEvent.change(screen.getByLabelText('Subject'), { target: { value: 'Engineering Mathematics' } });
    fireEvent.change(screen.getByLabelText('Custodians required'), { target: { value: '1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create exam' }));

    fireEvent.click(await screen.findByRole('button', { name: 'Commit my secret' }, T));
    fireEvent.click(await screen.findByRole('button', { name: 'Reveal my secret' }, T));
    fireEvent.click(await screen.findByRole('button', { name: /Generate sets/ }, T));
    await screen.findByText('Generated sets', {}, T);
    fireEvent.click(await screen.findByRole('button', { name: 'Approve release' }, T));
    const renders = await screen.findAllByRole('button', { name: 'Render' }, T);
    expect(renders).toHaveLength(3);
    fireEvent.click(renders[0]);
    await screen.findByText(/Rendered set A/, {}, T);
    const verifySet = () => screen.getAllByRole('button', { name: 'Verify' })[0];
    await waitFor(() => expect(verifySet().disabled).toBe(false), T);        // buttons lock while a request runs
    fireEvent.click(verifySet());
    await screen.findByText(/byte-for-byte identical/, {}, T);
    const verifyExam = () => screen.getByRole('button', { name: /Verify seed, constraints/ });
    await waitFor(() => expect(verifyExam().disabled).toBe(false), T);
    fireEvent.click(verifyExam());
    await screen.findByText(/reproducible yes/, {}, T);
  }, 180000);
});
