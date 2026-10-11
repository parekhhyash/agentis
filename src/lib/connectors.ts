// Apps users can connect so agents can act in them. To add one: give it an
// entry here, then a backend integration (see backend/integrations/) and a
// status/connect hook like useGoogleConnection.

export interface ConnectorInfo {
  id: string
  name: string
  description: string
  usedBy: string
  // Monogram tile colour (brand palette); Google uses its own mark.
  tile: string
  monogram: string
  available: boolean
}

export const CONNECTORS: ConnectorInfo[] = [
  {
    id: 'google',
    name: 'Gmail & Google Calendar',
    description: 'Send and reply to email from your Gmail, and book meetings with Google Meet links.',
    usedBy: 'Sales & Outreach',
    tile: 'bg-surface ring-1 ring-slate-200',
    monogram: 'G',
    available: true,
  },
  {
    id: 'hubspot',
    name: 'HubSpot',
    description: 'Ask about contacts, companies and deals, and add or update records (you approve each change), through HubSpot\u2019s MCP server.',
    usedBy: 'General, Lead Research',
    tile: 'bg-brand-pink text-ink',
    monogram: 'H',
    available: true,
  },
  {
    id: 'salesforce',
    name: 'Salesforce',
    description: 'Query and update accounts, contacts and opportunities through Salesforce\u2019s hosted MCP server.',
    usedBy: 'General, Lead Research',
    tile: 'bg-brand-sky text-white',
    monogram: 'S',
    available: true,
  },
  {
    id: 'zoho',
    name: 'Zoho CRM',
    description: 'Search and update leads, contacts and deals through your Zoho CRM MCP server.',
    usedBy: 'General, Lead Research',
    tile: 'bg-brand-orchid text-white',
    monogram: 'Z',
    available: true,
  },
  {
    id: 'linkedin',
    name: 'LinkedIn',
    description: 'Post the Content & Copy agent\u2019s LinkedIn drafts to your profile after you confirm.',
    usedBy: 'Content & Copy',
    tile: 'bg-brand-blue text-white',
    monogram: 'in',
    available: true,
  },
  {
    id: 'x',
    name: 'X (Twitter)',
    description: 'Drafted posts and threads open in X, ready to publish from your own account with one click. Free, nothing to connect.',
    usedBy: 'Content & Copy',
    tile: 'bg-ink text-white',
    monogram: 'X',
    available: true,
  },
  {
    id: 'notion',
    name: 'Notion',
    description: 'Save any Content & Copy draft as a private page in your Notion workspace, ready to edit and share.',
    usedBy: 'Content & Copy',
    tile: 'bg-brand-mauve text-white',
    monogram: 'N',
    available: true,
  },
  {
    id: 'medium',
    name: 'Medium',
    description: 'Save stories as drafts on Medium to publish from there. Needs an integration token made before 2025.',
    usedBy: 'Content & Copy',
    tile: 'bg-brand-violet text-white',
    monogram: 'M',
    available: true,
  },
  {
    id: 'outlook',
    name: 'Outlook & Microsoft 365',
    description: 'Email and calendar for teams on Microsoft.',
    usedBy: 'Sales & Outreach',
    tile: 'bg-brand-blue text-white',
    monogram: 'O',
    available: false,
  },
  {
    id: 'slack',
    name: 'Slack',
    description: 'Get updates from your agents and hand them tasks from a channel.',
    usedBy: 'Every agent',
    tile: 'bg-brand-violet text-white',
    monogram: 'S',
    available: false,
  },
  {
    id: 'sheets',
    name: 'Google Sheets',
    description: 'Read data for reports and export leads to a sheet.',
    usedBy: 'Data & Reporting',
    tile: 'bg-brand-yellow text-ink',
    monogram: 'S',
    available: false,
  },
]
