// Apps users can connect so agents can act in them. To add one: give it an
// entry here, then a backend integration (see backend/integrations/) and a
// status/connect hook like useGoogleConnection.

// Each app's own logo. From svg-logos (github.com/gilbarbara/logos) and
// Simple Icons (HubSpot, Google Sheets), both CC0; the marks belong to their
// owners and are shown only to name the app.
import gmail from '../assets/connectors/gmail.svg'
import googleCalendar from '../assets/connectors/google-calendar.svg'
import googleSheets from '../assets/connectors/google-sheets.svg'
import hubspot from '../assets/connectors/hubspot.svg'
import linkedin from '../assets/connectors/linkedin.svg'
import medium from '../assets/connectors/medium.svg'
import microsoft from '../assets/connectors/microsoft.svg'
import notion from '../assets/connectors/notion.svg'
import salesforce from '../assets/connectors/salesforce.svg'
import slack from '../assets/connectors/slack.svg'
import x from '../assets/connectors/x.svg'
import zoho from '../assets/connectors/zoho.svg'

export interface ConnectorInfo {
  id: string
  name: string
  description: string
  usedBy: string
  // Logo image URLs: one, or two for a pair like Gmail and Calendar.
  logos: string[]
  // A black mark (X, Notion, Medium), shown white on the dark-mode tile.
  monochrome?: boolean
  available: boolean
}

export const CONNECTORS: ConnectorInfo[] = [
  {
    id: 'google',
    name: 'Gmail & Google Calendar',
    description: 'Send and reply to email from your Gmail, and book meetings with Google Meet links.',
    usedBy: 'Sales & Outreach',
    logos: [gmail, googleCalendar],
    available: true,
  },
  {
    id: 'sheets',
    name: 'Google Sheets',
    description:
      'Add a sheet as a data file (read again whenever a report uses it), and export leads or report tables to a new sheet.',
    usedBy: 'Data & Reporting, Lead Research',
    logos: [googleSheets],
    available: true,
  },
  {
    id: 'hubspot',
    name: 'HubSpot',
    description: 'Ask about contacts, companies and deals, and add or update records (you approve each change), through HubSpot\u2019s MCP server.',
    usedBy: 'General, Lead Research',
    logos: [hubspot],
    available: true,
  },
  {
    id: 'salesforce',
    name: 'Salesforce',
    description:
      'Query and update accounts, contacts and opportunities through Salesforce\u2019s hosted MCP server. Your Salesforce admin sets up a small app once (steps below).',
    usedBy: 'General, Lead Research',
    logos: [salesforce],
    available: true,
  },
  {
    id: 'zoho',
    name: 'Zoho CRM',
    description: 'Search and update leads, contacts and deals through your Zoho CRM MCP server (free from Zoho; no Agentis setup).',
    usedBy: 'General, Lead Research',
    logos: [zoho],
    available: true,
  },
  {
    id: 'linkedin',
    name: 'LinkedIn',
    description: 'Post the Content & Copy agent\u2019s LinkedIn drafts to your profile after you confirm.',
    usedBy: 'Content & Copy',
    logos: [linkedin],
    available: true,
  },
  {
    id: 'x',
    name: 'X (Twitter)',
    description: 'Drafted posts and threads open in X, ready to publish from your own account with one click. Free, nothing to connect.',
    usedBy: 'Content & Copy',
    logos: [x],
    monochrome: true,
    available: true,
  },
  {
    id: 'notion',
    name: 'Notion',
    description: 'Save any Content & Copy draft as a private page in your Notion workspace, ready to edit and share.',
    usedBy: 'Content & Copy',
    logos: [notion],
    monochrome: true,
    available: true,
  },
  {
    id: 'medium',
    name: 'Medium',
    description: 'Save stories as drafts on Medium to publish from there. Needs an integration token made before 2025.',
    usedBy: 'Content & Copy',
    logos: [medium],
    monochrome: true,
    available: true,
  },
  {
    id: 'outlook',
    name: 'Outlook & Microsoft 365',
    description: 'Email and calendar for teams on Microsoft.',
    usedBy: 'Sales & Outreach',
    logos: [microsoft],
    available: false,
  },
  {
    id: 'slack',
    name: 'Slack',
    description: 'Get updates from your agents and hand them tasks from a channel.',
    usedBy: 'Every agent',
    logos: [slack],
    available: false,
  },
]
