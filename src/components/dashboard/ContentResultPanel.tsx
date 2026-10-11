import { useState } from 'react'

import { BackendApiError } from '../../lib/backendApi'
import {
  copyForMedium,
  destinationsFor,
  publishVariant,
  requirementsText,
  SHAPES,
  textLength,
  variantAsText,
  wordCount,
  xIntentUrl,
  type ContentPiece,
  type ContentResult,
  type ContentVariant,
  type Publication,
  type SocialProvider,
  type useSocialConnections,
} from '../../lib/content'
import RichText from './RichText'

const NETWORK: Record<SocialProvider, string> = { linkedin: 'LinkedIn', x: 'X', notion: 'Notion', medium: 'Medium' }
const CRITERIA = ['hook', 'clarity', 'specificity', 'voice', 'cta'] as const
const PUBLIC: SocialProvider[] = ['linkedin', 'x']

function publishedText(pub: Publication): string {
  if (pub.provider === 'notion') return 'Saved to Notion · Open'
  if (pub.provider === 'medium') return 'Medium draft saved · Open'
  return `Posted on ${NETWORK[pub.provider]}${pub.posts > 1 ? ` (${pub.posts} posts)` : ''} · View`
}

// "612 words", red when outside what the user asked for.
function Words({ text, piece }: { text: string; piece: ContentPiece }) {
  const count = wordCount(text)
  const req = piece.requirements
  const off = Boolean(req && ((req.min_words && count < req.min_words) || (req.max_words && count > req.max_words)))
  return (
    <span className={`text-[11px] tabular-nums ${off ? 'font-semibold text-red-600' : 'text-slate-400'}`}>
      {count.toLocaleString('en-US')} words
    </span>
  )
}

function Counter({ value, limit, xCount }: { value: string; limit: number | null; xCount: boolean }) {
  if (!limit) return null
  const size = textLength(value, xCount)
  return (
    <span className={`text-[11px] tabular-nums ${size > limit ? 'font-semibold text-red-600' : 'text-slate-400'}`}>
      {size.toLocaleString('en-US')} / {limit.toLocaleString('en-US')}
    </span>
  )
}

function Field({ label, value, limit }: { label: string; value: string | null; limit?: number }) {
  if (!value) return null
  return (
    <div>
      <p className="flex items-center justify-between text-[11px] font-medium tracking-wide text-slate-400 uppercase">
        {label}
        {limit && <Counter value={value} limit={limit} xCount={false} />}
      </p>
      <p className="text-sm text-slate-800">{value}</p>
    </div>
  )
}

function Body({
  piece,
  variant,
  editing,
  draft,
  onDraft,
}: {
  piece: ContentPiece
  variant: ContentVariant
  editing: boolean
  draft: { text: string; parts: string[] }
  onDraft: (draft: { text: string; parts: string[] }) => void
}) {
  const shape = SHAPES[piece.format] ?? 'post'
  const box = 'w-full rounded-lg border border-slate-300 bg-surface px-3 py-2 text-sm text-slate-800 focus:border-sky-400 focus:outline-none'

  if (shape === 'thread') {
    return (
      <ol className="space-y-2">
        {draft.parts.map((part, i) => (
          <li key={i} className="rounded-lg border border-slate-200 px-3 py-2">
            <div className="mb-1 flex items-center justify-between text-[11px] text-slate-400">
              <span>
                {i + 1}/{draft.parts.length}
              </span>
              <Counter value={part} limit={piece.limit} xCount={piece.x_count} />
            </div>
            {editing ? (
              <textarea
                value={part}
                rows={3}
                onChange={(e) => onDraft({ ...draft, parts: draft.parts.map((p, j) => (j === i ? e.target.value : p)) })}
                className={box}
              />
            ) : (
              <p className="text-sm whitespace-pre-wrap text-slate-800">{part}</p>
            )}
          </li>
        ))}
      </ol>
    )
  }
  if (shape === 'ad') {
    return (
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <p className="text-[11px] font-medium tracking-wide text-slate-400 uppercase">Headlines (30 max)</p>
          {variant.headlines.map((h, i) => (
            <p key={i} className="flex items-baseline justify-between gap-2 text-sm text-slate-800">
              <span>{h}</span>
              <Counter value={h} limit={30} xCount={false} />
            </p>
          ))}
        </div>
        <div className="space-y-1.5">
          <p className="text-[11px] font-medium tracking-wide text-slate-400 uppercase">Descriptions (90 max)</p>
          {variant.descriptions.map((d, i) => (
            <p key={i} className="text-sm text-slate-800">
              {d} <Counter value={d} limit={90} xCount={false} />
            </p>
          ))}
        </div>
        <div className="sm:col-span-2">
          <Field label="Primary text" value={variant.text} limit={125} />
        </div>
      </div>
    )
  }
  if (shape === 'article') {
    // Older blog results predate the per-piece labels and limits.
    const subtitleLabel = piece.subtitle_label ?? 'Meta description'
    const subtitleLimit = piece.subtitle_limit ?? (piece.format === 'blog_post' ? 155 : undefined)
    return (
      <div className="space-y-2">
        <div className="flex items-baseline justify-between gap-3">
          <h4 className="text-base font-semibold text-slate-900">{variant.title}</h4>
          {variant.title && piece.title_limit && <Counter value={variant.title} limit={piece.title_limit} xCount={false} />}
        </div>
        <Field label={subtitleLabel} value={variant.subtitle} limit={subtitleLimit ?? undefined} />
        <div className="max-h-96 overflow-y-auto rounded-lg border border-slate-200 px-3 py-2">
          <RichText text={variant.text} />
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          {variant.tags && variant.tags.length > 0 ? (
            <ul className="flex flex-wrap gap-1.5">
              {variant.tags.map((tag) => (
                <li key={tag} className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">
                  {tag}
                </li>
              ))}
            </ul>
          ) : (
            <span />
          )}
          <Words text={variant.text} piece={piece} />
        </div>
      </div>
    )
  }
  if (shape === 'email') {
    return (
      <div className="space-y-2">
        <Field label="Subject" value={variant.title} limit={60} />
        <Field label="Preview" value={variant.subtitle} limit={90} />
        <p className="rounded-lg border border-slate-200 px-3 py-2 text-sm whitespace-pre-wrap text-slate-800">{variant.text}</p>
      </div>
    )
  }
  return (
    <div>
      {editing ? (
        <textarea value={draft.text} rows={8} onChange={(e) => onDraft({ ...draft, text: e.target.value })} className={box} />
      ) : (
        <p className="rounded-lg border border-slate-200 px-3 py-2 text-sm whitespace-pre-wrap text-slate-800">{draft.text}</p>
      )}
      <div className="mt-1 flex justify-end gap-3">
        {(piece.requirements?.min_words || piece.requirements?.max_words || !piece.limit) && <Words text={draft.text} piece={piece} />}
        <Counter value={draft.text} limit={piece.limit} xCount={piece.x_count} />
      </div>
    </div>
  )
}

function PieceCard({
  requestId,
  piece,
  social,
  onPieceChange,
  onOpenConnect,
}: {
  requestId: string
  piece: ContentPiece
  social: ReturnType<typeof useSocialConnections>
  onPieceChange: (piece: ContentPiece) => void
  onOpenConnect: () => void
}) {
  const [selectedId, setSelectedId] = useState(piece.recommended_id ?? piece.variants[0]?.id)
  const variant = piece.variants.find((v) => v.id === selectedId) ?? piece.variants[0]
  const [drafts, setDrafts] = useState<Record<string, { text: string; parts: string[] }>>({})
  const [editing, setEditing] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState<SocialProvider | null>(null)
  const [message, setMessage] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)

  if (!variant) return null
  const draft = drafts[variant.id] ?? { text: variant.text, parts: variant.parts }
  const edited = draft.text !== variant.text || draft.parts.join('\u0000') !== variant.parts.join('\u0000')
  const places = destinationsFor(piece)
  // The piece's own network (LinkedIn / X) gets the main button and a confirm step.
  const network = places.find((p) => PUBLIC.includes(p)) ?? null
  const status = network ? social.byProvider(network) : null
  const published = network ? variant.published.find((p) => p.provider === network) : undefined
  const done = (provider: SocialProvider) => variant.published.some((p) => p.provider === provider)
  const notion = social.byProvider('notion')
  const medium = social.byProvider('medium')
  const mediumStory = piece.format === 'medium_story'
  const asked = requirementsText(piece.requirements)
  const overLimit =
    piece.limit != null &&
    (SHAPES[piece.format] === 'thread'
      ? draft.parts.some((p) => textLength(p, piece.x_count) > (piece.limit ?? Infinity))
      : textLength(draft.text, piece.x_count) > piece.limit)

  async function copy() {
    const text = variantAsText({ ...variant, text: draft.text, parts: draft.parts }, piece.format)
    try {
      await navigator.clipboard.writeText(text)
      setMessage({ tone: 'ok', text: 'Copied' })
    } catch {
      setMessage({ tone: 'error', text: 'Copy failed; select the text instead' })
    }
  }

  async function publish(provider: SocialProvider) {
    setBusy(provider)
    setMessage(null)
    try {
      const updated = await publishVariant(requestId, {
        piece_id: piece.id,
        variant_id: variant.id,
        provider,
        ...(edited ? (SHAPES[piece.format] === 'thread' ? { parts: draft.parts } : { text: draft.text }) : {}),
      })
      onPieceChange({ ...piece, variants: piece.variants.map((v) => (v.id === updated.id ? updated : v)) })
      setEditing(false)
      setConfirming(false)
    } catch (err) {
      const fallback = PUBLIC.includes(provider) ? 'Posting failed' : `Saving to ${NETWORK[provider]} failed`
      setMessage({ tone: 'error', text: err instanceof BackendApiError ? err.message : fallback })
      setConfirming(false)
    } finally {
      setBusy(null)
    }
  }

  // Without X's paid API, X opens with the post (or a thread's first post)
  // filled in; the whole thread goes to the clipboard for the rest.
  async function openInX() {
    const thread = SHAPES[piece.format] === 'thread'
    window.open(xIntentUrl(thread ? (draft.parts[0] ?? '') : draft.text), '_blank', 'noopener')
    if (thread && draft.parts.length > 1) {
      try {
        await navigator.clipboard.writeText(draft.parts.join('\n\n'))
        setMessage({ tone: 'ok', text: 'X opened with post 1. The whole thread is copied: add the rest with the + button in X.' })
      } catch {
        setMessage({ tone: 'ok', text: 'X opened with post 1. Add the rest with the + button in X.' })
      }
    }
  }

  async function copyMedium() {
    try {
      await copyForMedium({ ...variant, text: draft.text }, piece.format)
      setMessage({ tone: 'ok', text: 'Copied with formatting. Paste it into a new Medium story.' })
    } catch {
      setMessage({ tone: 'error', text: 'Copy failed; select the text instead' })
    }
  }

  const secondary = 'rounded-full border border-slate-300 px-3 py-1 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50'

  return (
    <section className="rounded-xl border border-slate-200 bg-surface p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h4 className="text-sm font-semibold text-slate-900">{piece.label}</h4>
        {piece.topic && <span className="min-w-0 truncate text-xs text-slate-500">{piece.topic}</span>}
        {asked && <p className="w-full text-xs text-slate-500">You asked for: {asked}</p>}
      </div>

      {piece.variants.length > 1 && (
        <div role="tablist" className="mb-3 flex flex-wrap gap-1.5">
          {piece.variants.map((v, i) => (
            <button
              key={v.id}
              role="tab"
              type="button"
              aria-selected={v.id === variant.id}
              onClick={() => {
                setSelectedId(v.id)
                setEditing(false)
                setConfirming(false)
                setMessage(null)
              }}
              className={`rounded-lg border px-2.5 py-1.5 text-left text-xs transition-colors ${
                v.id === variant.id ? 'border-sky-400 bg-sky-50 text-slate-900' : 'border-slate-200 text-slate-600 hover:bg-slate-50'
              }`}
            >
              <span className="font-semibold">Option {i + 1}</span>
              {v.score != null && <span className="ml-1 tabular-nums text-slate-500">{v.score.toFixed(1)}</span>}
              {v.id === piece.recommended_id && <span className="ml-1.5 font-semibold text-brand-blue">Recommended</span>}
              {v.angle && <span className="block text-[11px] text-slate-400">{v.angle}</span>}
            </button>
          ))}
        </div>
      )}

      <Body piece={piece} variant={variant} editing={editing} draft={draft} onDraft={(d) => setDrafts((prev) => ({ ...prev, [variant.id]: d }))} />

      {variant.issues.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {variant.issues.map((issue, i) => (
            <li
              key={i}
              className={`rounded-md px-2 py-0.5 text-[11px] ${issue.level === 'error' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-700'}`}
            >
              {issue.message}
            </li>
          ))}
        </ul>
      )}

      {(variant.reason || Object.keys(variant.scores).length > 0) && (
        <p className="mt-2 text-xs text-slate-500">
          {variant.reason}
          {Object.keys(variant.scores).length > 0 && (
            <span className="ml-1 text-slate-400">
              ({CRITERIA.filter((c) => c in variant.scores).map((c) => `${c} ${variant.scores[c]}`).join(' · ')})
            </span>
          )}
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button type="button" onClick={() => void copy()} className={secondary}>
          Copy
        </button>
        {(SHAPES[piece.format] === 'post' || SHAPES[piece.format] === 'thread') && !published && (
          <button type="button" onClick={() => setEditing((v) => !v)} className={secondary}>
            {editing ? 'Done editing' : 'Edit'}
          </button>
        )}
        {mediumStory && !medium?.connected && (
          <>
            <button type="button" onClick={() => void copyMedium()} className={secondary}>
              Copy for Medium
            </button>
            <a href="https://medium.com/new-story" target="_blank" rel="noreferrer" className="text-sm font-medium text-sky-600 hover:underline">
              Open Medium
            </a>
          </>
        )}

        <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
          {notion?.configured && !done('notion') && (
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => (notion.connected ? void publish('notion') : onOpenConnect())}
              title={notion.connected ? `Save as a private page in ${notion.account ?? 'Notion'}` : 'Connect Notion first'}
              className={secondary}
            >
              {busy === 'notion' ? 'Saving…' : 'Save to Notion'}
            </button>
          )}
          {places.includes('medium') && medium?.connected && !done('medium') && (
            <button type="button" disabled={busy !== null} onClick={() => void publish('medium')} className={secondary}>
              {busy === 'medium' ? 'Saving…' : 'Save Medium draft'}
            </button>
          )}
          {network &&
            !published &&
            (!status?.configured && network === 'x' ? (
              <button
                type="button"
                disabled={overLimit}
                title={overLimit ? 'Shorten it to fit the limit first' : 'Opens X with this post ready; you press Post'}
                onClick={() => void openInX()}
                className="rounded-full bg-ink px-3.5 py-1 text-sm font-semibold text-white hover:bg-ink/90 disabled:opacity-50 dark:bg-white dark:text-ink"
              >
                Open in X
              </button>
            ) : !status?.configured ? (
              <span className="text-xs text-slate-400">{NETWORK[network]} posting isn&rsquo;t set up on the server</span>
            ) : !status.connected ? (
              <button type="button" onClick={onOpenConnect} className="text-sm font-medium text-sky-600 hover:underline">
                Connect {NETWORK[network]} to post
              </button>
            ) : confirming ? (
              <span className="flex flex-wrap items-center gap-2 text-sm">
                <span className="text-slate-600">
                  Post publicly as {status.account}?{network === 'x' ? ' Uses X API credits.' : ''}
                </span>
                <button type="button" onClick={() => setConfirming(false)} className="rounded-full px-3 py-1 text-slate-500 hover:bg-slate-100">
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => void publish(network)}
                  className="rounded-full bg-brand-blue px-3.5 py-1 font-semibold text-white hover:bg-brand-blue/90 disabled:opacity-50"
                >
                  {busy === network ? 'Posting…' : 'Post now'}
                </button>
              </span>
            ) : (
              <button
                type="button"
                disabled={overLimit || busy !== null}
                title={overLimit ? 'Shorten it to fit the limit first' : undefined}
                onClick={() => setConfirming(true)}
                className="rounded-full bg-brand-blue px-3.5 py-1 text-sm font-semibold text-white hover:bg-brand-blue/90 disabled:opacity-50"
              >
                Post to {NETWORK[network]}
              </button>
            ))}
        </div>
      </div>
      {variant.published.length > 0 && (
        <ul className="mt-2 flex flex-wrap justify-end gap-x-4 gap-y-1">
          {variant.published.map((pub) => (
            <li key={pub.provider}>
              <a href={pub.url} target="_blank" rel="noreferrer" className="text-sm font-medium text-emerald-700 hover:underline">
                {publishedText(pub)}
              </a>
            </li>
          ))}
        </ul>
      )}
      {message && <p className={`mt-2 text-xs ${message.tone === 'ok' ? 'text-emerald-700' : 'text-red-700'}`}>{message.text}</p>}
    </section>
  )
}

export default function ContentResultPanel({
  requestId,
  result,
  social,
  onResultChange,
  onOpenConnect,
}: {
  requestId: string
  result: ContentResult
  social: ReturnType<typeof useSocialConnections>
  onResultChange: (result: ContentResult) => void
  onOpenConnect: () => void
}) {
  return (
    <div className="space-y-4">
      {result.summary && <p className="text-sm text-slate-700">{result.summary}</p>}
      {result.pieces.map((piece) => (
        <PieceCard
          key={piece.id}
          requestId={requestId}
          piece={piece}
          social={social}
          onOpenConnect={onOpenConnect}
          onPieceChange={(updated) => onResultChange({ ...result, pieces: result.pieces.map((p) => (p.id === updated.id ? updated : p)) })}
        />
      ))}
      {result.notes.length > 0 && (
        <ul className="space-y-1 text-xs text-slate-500">
          {result.notes.map((note, i) => (
            <li key={i}>{note}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
