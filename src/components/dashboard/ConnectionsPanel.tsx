import type { ReactNode } from 'react'

import { CONNECTORS, type ConnectorInfo } from '../../lib/connectors'
import type { SocialProvider, useSocialConnections } from '../../lib/content'
import type { CrmProvider, useCrmConnections } from '../../lib/crm'
import { partConnected, type GooglePart, type GoogleStatus } from '../../lib/googleConnection'
import CrmConnectControls from './CrmConnectControls'
import DataFilesPanel from './DataFilesPanel'
import SocialConnectControls from './SocialConnectControls'

const GOOGLE_IDS = new Set<string>(['gmail', 'calendar', 'sheets'])
const CRM_IDS = new Set<string>(['hubspot', 'salesforce', 'zoho'])
const SOCIAL_IDS = new Set<string>(['linkedin', 'x', 'notion', 'medium'])

// The app's own logo, straight on the card (no tile), in both themes; black
// marks (X, Notion, Medium) turn white in dark mode.
function Tile({ connector }: { connector: ConnectorInfo }) {
  return (
    <span className="relative flex h-11 w-11 shrink-0 items-center justify-center">
      <img
        src={connector.logo}
        alt=""
        className={`object-contain ${connector.id === 'zoho' ? 'w-10' : 'h-8 w-8'} ${connector.monochrome ? 'dark:invert' : ''}`}
      />
    </span>
  )
}

type Google = {
  status: GoogleStatus | null
  error: string | null
  busy: boolean
  connect: (part?: GooglePart) => void
  disconnect: (part?: GooglePart) => void
}

// Gmail, Google Calendar and Google Sheets each have their own permission
// and Disconnect, on one Google account.
function GoogleControls({ part, google }: { part: GooglePart; google: Google }) {
  const status = google.status
  if (!status) return <p className="text-sm text-slate-400">{google.error ?? 'Checking…'}</p>
  if (!status.configured) return <p className="text-sm text-amber-700">Not set up on the server yet.</p>
  if (partConnected(status, part))
    return (
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-2 text-sm text-slate-600">
          <span className="h-2 w-2 shrink-0 rounded-full bg-emerald-500" />
          <span className="truncate">{status.email}</span>
        </span>
        <button
          type="button"
          onClick={() => google.disconnect(part)}
          disabled={google.busy}
          className="rounded-full px-3 py-1.5 text-sm font-medium text-slate-500 transition-colors hover:bg-slate-100 disabled:opacity-50"
        >
          Disconnect
        </button>
      </div>
    )
  return (
    <div className="space-y-1.5">
      <button
        type="button"
        onClick={() => google.connect(part)}
        disabled={google.busy}
        className="rounded-full bg-brand-blue px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-blue/90 disabled:opacity-50"
      >
        {google.busy ? 'Opening Google…' : 'Connect'}
      </button>
      {status.email && <p className="text-xs text-slate-500">Uses your Google account {status.email}.</p>}
    </div>
  )
}

function Card({ connector, children }: { connector: ConnectorInfo; children: ReactNode }) {
  return (
    <div className="flex flex-col rounded-2xl border border-slate-200 bg-surface p-5">
      <div className="flex items-start gap-3">
        <Tile connector={connector} />
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-slate-900">{connector.name}</h3>
          <p className="text-xs text-slate-500">Used by {connector.usedBy}</p>
        </div>
      </div>
      <p className="mt-3 flex-1 text-sm leading-relaxed text-slate-600">{connector.description}</p>
      <div className="mt-4">{children}</div>
    </div>
  )
}

export default function ConnectionsPanel({
  google,
  crm,
  social,
  notice,
}: {
  google: Google
  crm: ReturnType<typeof useCrmConnections>
  social: ReturnType<typeof useSocialConnections>
  notice: ReactNode
}) {
  const sheets = {
    configured: Boolean(google.status?.configured),
    connected: partConnected(google.status, 'sheets'),
    busy: google.busy,
    connect: () => google.connect('sheets'),
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="font-display text-3xl text-slate-900">Connect</h1>
      <p className="mt-2 text-slate-500">
        Give your agents access to the apps you already use. Each person connects their own account, and you
        approve anything an agent sends.
      </p>

      {notice && <div className="mt-6">{notice}</div>}

      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        {CONNECTORS.map((connector) => (
          <Card key={connector.id} connector={connector}>
            {GOOGLE_IDS.has(connector.id) ? (
              <GoogleControls part={connector.id as GooglePart} google={google} />
            ) : CRM_IDS.has(connector.id) ? (
              <CrmConnectControls provider={connector.id as CrmProvider} crm={crm} />
            ) : SOCIAL_IDS.has(connector.id) ? (
              <SocialConnectControls provider={connector.id as SocialProvider} social={social} />
            ) : (
              <span className="inline-block rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-500">
                Coming soon
              </span>
            )}
          </Card>
        ))}
      </div>

      <DataFilesPanel sheets={sheets} />
    </div>
  )
}
