-- Helpdesk connections for the Customer Support agent (Freshdesk, Zendesk,
-- Zoho Desk). One row per user and helpdesk. The credential is encrypted by
-- the backend (Fernet, INTEGRATIONS_ENCRYPTION_KEY): the API key for
-- Freshdesk, the API token for Zendesk, and the OAuth refresh token for Zoho
-- Desk. Gmail, the no-helpdesk option, uses the Google connection.

create table if not exists public.support_connections (
  user_id uuid not null references auth.users (id) on delete cascade,
  provider text not null check (provider in ('freshdesk', 'zendesk', 'zoho_desk')),
  -- Freshdesk: yourcompany.freshdesk.com; Zendesk: yourcompany.zendesk.com;
  -- Zoho Desk: the API host for the account's data centre (desk.zoho.in).
  domain text not null,
  -- Zendesk: the agent email the API token belongs to.
  email text,
  -- Zoho Desk: the organisation (portal) the tickets live in.
  org_id text,
  account_label text,
  secret_encrypted text not null,
  connected_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, provider)
);

-- Backend only: RLS on with no policies, like crm_connections.
alter table public.support_connections enable row level security;
