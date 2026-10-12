// Apps users can connect so agents can act in them. To add one: give it an
// entry here, then a backend integration (see backend/integrations/) and a
// status/connect hook like useGoogleConnection.

// Each app's own logo. From svg-logos (github.com/gilbarbara/logos) and
// Simple Icons (HubSpot, Google Sheets), both CC0; the marks belong to their
// owners and are shown only to name the app.
import gmail from '../assets/connectors/gmail.svg'
import freshdesk from '../assets/connectors/freshdesk.svg'
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
import zendesk from '../assets/connectors/zendesk.svg'
import zoho from '../assets/connectors/zoho.svg'

export interface ConnectorInfo {
  id: string
  name: string
  description: string
  usedBy: string
  // Logo image URL.
  logo: string
  // A black mark (X, Notion, Medium), shown white on the dark-mode tile.
  monochrome?: boolean
  available: boolean
}

export const CONNECTORS: ConnectorInfo[] = [
  {
    id: 'gmail',
    name: 'Gmail',
    description: 'Draft, send and reply to email from your own Gmail, each one after you approve it.',
    usedBy: 'Sales & Outreach, Customer Support, Operations',
    logo: gmail,
    available: true,
  },
  {
    id: 'calendar',
    name: 'Google Calendar',
    description: 'Book meetings with Google Meet links, checked against your calendar for clashes.',
    usedBy: 'Sales & Outreach',
    logo: googleCalendar,
    available: true,
  },
  {
    id: 'sheets',
    name: 'Google Sheets',
    description:
      'Add a sheet as a data file (read again whenever a report uses it), and export leads or report tables to a new sheet.',
    usedBy: 'Data & Reporting, Lead Research',
    logo: googleSheets,
    available: true,
  },
  {
    id: 'hubspot',
    name: 'HubSpot',
    description: 'Ask about contacts, companies and deals, and add or update records (you approve each change), through HubSpot\u2019s MCP server.',
    usedBy: 'Manager, Lead Research',
    logo: hubspot,
    available: true,
  },
  {
    id: 'salesforce',
    name: 'Salesforce',
    description:
      'Query and update accounts, contacts and opportunities through Salesforce\u2019s hosted MCP server. Your Salesforce admin sets up a small app once (Connect shows how).',
    usedBy: 'Manager, Lead Research',
    logo: salesforce,
    available: true,
  },
  {
    id: 'zoho',
    name: 'Zoho CRM',
    description: 'Search and update leads, contacts and deals through your Zoho CRM MCP server (free from Zoho; no Agentis setup).',
    usedBy: 'Manager, Lead Research',
    logo: zoho,
    available: true,
  },
  {
    id: 'freshdesk',
    name: 'Freshdesk',
    description: 'Triage open tickets and draft replies or private notes from your help articles; you approve each one.',
    usedBy: 'Customer Support',
    logo: freshdesk,
    available: true,
  },
  {
    id: 'zendesk',
    name: 'Zendesk',
    description: 'Triage open tickets and draft replies or internal notes from your Help Center; you approve each one.',
    usedBy: 'Customer Support',
    logo: zendesk,
    monochrome: true,
    available: true,
  },
  {
    id: 'zoho_desk',
    name: 'Zoho Desk',
    description: 'Triage open tickets and draft replies or private comments from your knowledge base; you approve each one.',
    usedBy: 'Customer Support',
    logo: zoho,
    available: true,
  },
  {
    id: 'linkedin',
    name: 'LinkedIn',
    description: 'Drafted posts open in LinkedIn with the text filled in, ready to post from your own profile. Free, nothing to connect.',
    usedBy: 'Content & Copy',
    logo: linkedin,
    available: true,
  },
  {
    id: 'x',
    name: 'X (Twitter)',
    description: 'Drafted posts and threads open in X, ready to publish from your own account with one click. Free, nothing to connect.',
    usedBy: 'Content & Copy',
    logo: x,
    monochrome: true,
    available: true,
  },
  {
    id: 'notion',
    name: 'Notion',
    description: 'Save any Content & Copy draft as a private page in your Notion workspace, ready to edit and share.',
    usedBy: 'Content & Copy',
    logo: notion,
    monochrome: true,
    available: true,
  },
  {
    id: 'medium',
    name: 'Medium',
    description: 'Save stories as drafts on Medium to publish from there. Needs an integration token made before 2025.',
    usedBy: 'Content & Copy',
    logo: medium,
    monochrome: true,
    available: true,
  },
  {
    id: 'outlook',
    name: 'Outlook & Microsoft 365',
    description: 'Email and calendar for teams on Microsoft.',
    usedBy: 'Sales & Outreach',
    logo: microsoft,
    available: false,
  },
  {
    id: 'slack',
    name: 'Slack',
    description: 'Get updates from your agents and hand them tasks from a channel.',
    usedBy: 'Every agent',
    logo: slack,
    available: false,
  },
]
