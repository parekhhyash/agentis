-- Data files can come from Google Sheets as well as uploads. A sheet keeps
-- its link and tab; the backend reads it again (at most every 5 minutes)
-- when Data & Reporting uses it, so reports and scheduled runs see the
-- current numbers.

alter table public.datasets
  add column if not exists source text not null default 'upload' check (source in ('upload', 'google_sheets')),
  add column if not exists source_url text,
  add column if not exists source_tab text,
  add column if not exists refreshed_at timestamptz;
