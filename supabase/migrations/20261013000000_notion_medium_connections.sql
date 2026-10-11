-- Content & Copy can also save to Notion (a private page) and Medium (a
-- draft). Both reuse social_connections: Notion signs in with OAuth; Medium
-- stores a pasted integration token, encrypted like the rest.

alter table public.social_connections drop constraint if exists social_connections_provider_check;
alter table public.social_connections
  add constraint social_connections_provider_check check (provider in ('linkedin', 'x', 'notion', 'medium'));
