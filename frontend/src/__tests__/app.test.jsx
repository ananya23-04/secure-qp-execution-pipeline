import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import App from '../App.jsx';
import Submit, { toPayload, validate } from '../pages/Submit.jsx';
import { buildBlueprint } from '../pages/Exams.jsx';
import { parseUnits } from '../pages/Moderation.jsx';

function mockFetch(routes) {
  const calls = [];
  global.fetch = vi.fn(async (url, opts = {}) => {
    const key = `${opts.method || 'GET'} ${url}`;
    calls.push({ key, body: opts.body ? JSON.parse(opts.body) : undefined, headers: opts.headers });
    const hit = routes[key];
    if (hit === undefined) return new Response(JSON.stringify({ detail: `no mock for ${key}` }), { status: 404 });
    const { status = 200, body } = hit.__status ? hit : { body: hit };
    return new Response(JSON.stringify(body), { status });
  });
  return calls;
}

const ME = (roles) => ({ email: 'x@juit.ac.in', pseudonym: 'FAC-1', institution: 'JUIT', roles });

describe('App shell', () => {
  it('shows the sign-in form when signed out', () => {
    mockFetch({});
    render(<App />);
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeTruthy();
  });

  it('logs in and shows only the screens the user may use', async () => {
    mockFetch({
      'POST /auth/login': { access_token: 'tok' },
      'GET /auth/me': ME(['faculty', 'reviewer']),
      'GET /review/queue?limit=5': [],
      'GET /review/mine/history': [],
    });
    render(<App />);
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'x@juit.ac.in' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'supersecret123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() => expect(screen.getByRole('link', { name: 'Submit questions' })).toBeTruthy());
    expect(screen.getByRole('link', { name: 'Review' })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Overview' }).getAttribute('aria-current')).toBe('page');
    expect(screen.queryByRole('link', { name: 'Exams' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'Moderation' })).toBeNull();
    expect(sessionStorage.getItem('safeexam.token')).toBe('tok');
  });

  it('gives admins the moderation and exam screens', async () => {
    sessionStorage.setItem('safeexam.token', 'tok');
    mockFetch({ 'GET /auth/me': ME(['faculty', 'admin']) });
    render(<App />);
    await waitFor(() => expect(screen.getByRole('link', { name: 'Moderation' })).toBeTruthy());
    expect(screen.getByRole('link', { name: 'Exams' })).toBeTruthy();
    expect(screen.queryByRole('link', { name: 'Review' })).toBeNull();
  });

  it('returns to sign-in if the saved token is rejected', async () => {
    sessionStorage.setItem('safeexam.token', 'stale');
    mockFetch({ 'GET /auth/me': { __status: true, status: 401, body: { detail: 'Invalid or expired token' } } });
    render(<App />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Sign in' })).toBeTruthy());
    expect(sessionStorage.getItem('safeexam.token')).toBeNull();
  });
});

describe('Submit page', () => {
  const fill = () => {
    fireEvent.change(screen.getByLabelText('Subject'), { target: { value: 'Maths' } });
    fireEvent.change(screen.getByLabelText('Question text'), { target: { value: 'What is $2+2$ in base ten?' } });
    ['A', 'B', 'C', 'D'].forEach((l, i) =>
      fireEvent.change(screen.getByLabelText(`Option ${l}`), { target: { value: ['3', '4', '5', '6'][i] } }));
    fireEvent.click(screen.getByLabelText('Mark option B as correct'));
  };

  it('previews live, batches, and posts the exact payload the API expects', async () => {
    const calls = mockFetch({
      'POST /submissions': { id: 'abc', status: 'raw_ingested', question_count: 1 },
      'GET /submissions/abc/report': { submission_status: 'deduplicated', summary: { unique: 1 }, questions: [{ index: 0, status: 'unique', issues: [] }] },
    });
    const { container } = render(<Submit />);
    fill();
    expect(container.querySelector('.preview .katex')).not.toBeNull();            // live KaTeX preview
    fireEvent.click(screen.getByRole('button', { name: 'Add to batch' }));
    expect(screen.getByText(/1 question in batch/)).toBeTruthy();
    fireEvent.click(screen.getByLabelText(/I confirm these questions/));
    fireEvent.click(screen.getByRole('button', { name: 'Submit batch' }));
    await waitFor(() => expect(screen.getByText('Unique')).toBeTruthy());
    const post = calls.find((c) => c.key === 'POST /submissions');
    expect(post.body.rights_declared).toBe(true);
    expect(post.body.questions[0]).toEqual({
      qtype: 'mcq', stem: 'What is $2+2$ in base ten?', options: ['3', '4', '5', '6'], correct_option: 1,
      solution_latex: null, subject: 'Maths', unit: 1, bloom: 'understand', difficulty: 0.5, marks: 1,
    });
  });

  it('blocks a question with broken LaTeX', () => {
    mockFetch({});
    render(<Submit />);
    fill();
    fireEvent.change(screen.getByLabelText('Question text'), { target: { value: 'Broken $math never closed here' } });
    expect(screen.getByText(/A \$ is not closed/)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Add to batch' }).disabled).toBe(true);
  });

  it('validates MCQ rules', () => {
    const base = { qtype: 'mcq', stem: 'A long enough stem here', options: ['a', 'a'], correct: 0, solution: '', subject: 'M', unit: 1, bloom: 'apply', difficulty: 0.5, marks: 1 };
    expect(validate(base).problems.join()).toMatch(/different from each other/);
    expect(validate({ ...base, options: ['a', ''] }).problems.join()).toMatch(/Fill in every option/);
    expect(toPayload({ ...base, qtype: 'short' }).options).toBeNull();
  });
});

describe('Admin form helpers', () => {
  it('parses unit lists', () => {
    expect(parseUnits('1:10, 2:5')).toEqual({ 1: 10, 2: 5 });
    expect(() => parseUnits('one:ten')).toThrow(/Cannot read/);
  });
  const f = { subject: 'Maths', num_sets: 3, total_marks: 30, units: '1:10,2:10,3:10', easy: 0.3, medium: 0.5, hard: 0.2,
    tolerance: 0.2, higher: 10, overlap: 40, useTypes: true, mcq: 5, short: 10, long: 15 };
  it('builds a blueprint matching the API schema', () => {
    expect(buildBlueprint(f)).toEqual({
      subject: 'Maths', num_sets: 3, total_marks: 30, units: { 1: 10, 2: 10, 3: 10 },
      difficulty_mix: { easy: 0.3, medium: 0.5, hard: 0.2 }, difficulty_tolerance: 0.2,
      min_higher_order_pct: 10, max_overlap_pct: 40, qtype_marks: { mcq: 5, short: 10, long: 15 },
    });
  });
  it('rejects inconsistent totals before calling the server', () => {
    expect(() => buildBlueprint({ ...f, units: '1:10,2:10' })).toThrow(/add up/);
    expect(() => buildBlueprint({ ...f, easy: 0.5 })).toThrow(/add up to 1/);
    expect(() => buildBlueprint({ ...f, mcq: 1 })).toThrow(/add up/);
  });
});
