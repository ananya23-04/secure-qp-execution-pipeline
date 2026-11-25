// One place for human wording of internal status codes: [label, tone]
const MAP = {
  raw_ingested: ['Received', 'info'], validated: ['Validating', 'info'], deduplicated: ['Processed', 'good'],
  unique: ['Unique', 'good'], near_duplicate: ['Near-duplicate', 'warn'], duplicate: ['Duplicate', 'muted'], invalid: ['Invalid', 'bad'],
  in_pool: ['In review pool', 'info'], approved: ['Approved', 'good'], rejected: ['Rejected', 'bad'], moderation: ['Needs moderation', 'warn'],
  committing: ['Collecting commitments', 'info'], revealing: ['Revealing secrets', 'info'], ready: ['Seed ready', 'good'],
  generated: ['Sets generated', 'good'], released: ['Released', 'good'],
  mcq: ['Multiple choice', 'accent'], short: ['Short answer', 'accent'], long: ['Long answer', 'accent'],
  approve: ['Approved', 'good'], reject: ['Rejected', 'bad'],
};
export const label = (k) => (MAP[k] ? MAP[k][0] : String(k).replace(/_/g, ' '));
export const tone = (k) => (MAP[k] ? MAP[k][1] : 'muted');
