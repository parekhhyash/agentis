-- Salesforce hosted MCP servers only accept an External Client App created in
-- the same org, so each company signs in with its own app. The connection
-- keeps that app's consumer key, its sign-in domain and (encrypted by the
-- backend, if the app has one) its consumer secret, for token refreshes.

alter table public.crm_connections
  add column if not exists client_id text,
  add column if not exists client_secret_encrypted text,
  add column if not exists login_url text;
