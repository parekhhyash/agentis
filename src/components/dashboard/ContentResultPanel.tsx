import { useState, type ReactNode } from 'react'

import { BackendApiError } from '../../lib/backendApi'
import {
  copyForMedium,
  destinationsFor,
  linkedinShareUrl,
  publishVariant,
  saveVariant,
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
  type VariantEdits,
} from '../../lib/content'
import RichText from './RichText'

const NETWORK: Record<SocialProvider, string> = { linkedin: 'LinkedIn', x: 'X', notion: 'Notion', medium: 'Medium' }
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

type Shape = 'post' | 'thread' | 'article' | 'email' | 'ad'

// The fields an option of each shape has, which the user can change.
interface Draft {
  title: string
  subtitle: string
  text: string
  parts: string[]
  headlines: string[]
  descriptions: string[]
  tags: string[]
}

const FIELDS: Record<Shape, (keyof Draft)[]> = {
  post: ['text'],
  thread: ['parts'],
  article: ['title', 'subtitle', 'text', 'tags'],
  email: ['title', 'subtitle', 'text'],
  ad: ['headlines', 'descriptions', 'text'],
}

function draftOf(v: ContentVariant): Draft {
  return {
    title: v.title ?? '',
    subtitle: v.subtitle ?? '',
    text: v.text,
    parts: v.parts,
    headlines: v.headlines,
    descriptions: v.descriptions,
    tags: v.tags ?? [],
  }
}

// Only the fields the user changed, for the save request.
function changesIn(shape: Shape, draft: Draft, variant: ContentVariant): VariantEdits {
  const saved = draftOf(variant)
  const out: Record<string, string | string[]> = {}
  for (const key of FIELDS[shape]) {
    if (JSON.stringify(draft[key]) !== JSON.stringify(saved[key])) out[key] = draft[key]
  }
  return out as VariantEdits
}

// The option as it reads now, edits included, for copying and opening elsewhere.
function withDraft(variant: ContentVariant, draft: Draft): ContentVariant {
  return { ...variant, ...draft, title: draft.title || null, subtitle: draft.subtitle || null }
}

const inputClass =
  'w-full rounded-lg border border-slate-200 bg-transparent px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:border-sky-500 focus:outline-none disabled:opacity-70'

// Tall enough for the text, counting wrapped lines, within a range.
function rowsFor(text: string, min: number, max: number): number {
  const lines = text.split('\n').reduce((sum, line) => sum + Math.max(1, Math.ceil(line.length / 85)), 0)
  return Math.min(max, Math.max(min, lines + 1))
}

function Field({ label, aside, children }: { label: ReactNode; aside?: ReactNode; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 flex items-center justify-between gap-3 text-xs font-medium text-slate-500">
        <span>{label}</span>
        {aside}
      </span>
      {children}
    </label>
  )
}

function TextBox({ value, onChange, editable, min = 6, max = 18 }: { value: string; onChange: (value: string) => void; editable: boolean; min?: number; max?: number }) {
  return (
    <textarea
      className={`${inputClass} resize-y leading-relaxed`}
      disabled={!editable}
      rows={rowsFor(value, min, max)}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

const MAX_TAGS = 5

// Medium's topic tags: shown as a list, removable, with a box to add more.
function Tags({ tags, editable, onChange }: { tags: string[]; editable: boolean; onChange: (tags: string[]) => void }) {
  const [entry, setEntry] = useState('')
  function add() {
    const tag = entry.replace(/^#/, '').trim()
    if (tag && tags.length < MAX_TAGS && !tags.some((t) => t.toLowerCase() === tag.toLowerCase())) onChange([...tags, tag])
    setEntry('')
  }
  return (
    <div>
      <p className="mb-1 text-xs font-medium text-slate-500">
        Tags <span className="font-normal text-slate-400">· Medium topic tags, added when you publish (up to {MAX_TAGS})</span>
      </p>
      <ul className="flex flex-wrap items-center gap-1.5">
        {tags.map((tag) => (
          <li key={tag} className="flex items-center rounded-full bg-slate-100 py-0.5 pr-1 pl-2.5 text-xs text-slate-700">
            {tag}
            {editable ? (
              <button
                type="button"
                aria-label={`Remove the tag ${tag}`}
                onClick={() => onChange(tags.filter((t) => t !== tag))}
                className="ml-0.5 rounded-full px-1 text-slate-400 hover:text-slate-700"
              >
                ×
              </button>
            ) : (
              <span className="pr-1.5" />
            )}
          </li>
        ))}
        {editable && tags.length < MAX_TAGS && (
          <li>
            <input
              value={entry}
              maxLength={25}
              placeholder="Add a tag"
              aria-label="Add a tag"
              onChange={(e) => setEntry(e.target.value)}
              onBlur={add}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ',') {
                  e.preventDefault()
                  add()
                }
              }}
              className="w-28 rounded-full border border-dashed border-slate-300 bg-transparent px-2.5 py-0.5 text-xs text-slate-800 placeholder:text-slate-400 focus:border-sky-500 focus:outline-none"
            />
          </li>
        )}
      </ul>
    </div>
  )
}

function Body({
  piece,
  draft,
  editable,
  onDraft,
}: {
  piece: ContentPiece
  draft: Draft
  editable: boolean
  onDraft: (patch: Partial<Draft>) => void
}) {
  const shape: Shape = SHAPES[piece.format] ?? 'post'
  const [preview, setPreview] = useState(false)
  const setItem = (key: 'parts' | 'headlines' | 'descriptions', i: number, value: string) =>
    onDraft({ [key]: draft[key].map((item, j) => (j === i ? value : item)) })

  if (shape === 'thread') {
    return (
      <ol className="space-y-2">
        {draft.parts.map((part, i) => (
          <li key={i}>
            <Field
              label={`Post ${i + 1} of ${draft.parts.length}`}
              aside={<Counter value={part} limit={piece.limit} xCount={piece.x_count} />}
            >
              <TextBox value={part} min={3} max={8} editable={editable} onChange={(v) => setItem('parts', i, v)} />
            </Field>
          </li>
        ))}
      </ol>
    )
  }
  if (shape === 'ad') {
    return (
      <div className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-2">
            {draft.headlines.map((h, i) => (
              <Field key={i} label={`Headline ${i + 1}`} aside={<Counter value={h} limit={30} xCount={false} />}>
                <input className={inputClass} disabled={!editable} value={h} onChange={(e) => setItem('headlines', i, e.target.value)} />
              </Field>
            ))}
          </div>
          <div className="space-y-2">
            {draft.descriptions.map((d, i) => (
              <Field key={i} label={`Description ${i + 1}`} aside={<Counter value={d} limit={90} xCount={false} />}>
                <TextBox value={d} min={2} max={4} editable={editable} onChange={(v) => setItem('descriptions', i, v)} />
              </Field>
            ))}
          </div>
        </div>
        <Field label="Primary text" aside={<Counter value={draft.text} limit={125} xCount={false} />}>
          <TextBox value={draft.text} min={3} max={8} editable={editable} onChange={(text) => onDraft({ text })} />
        </Field>
      </div>
    )
  }
  if (shape === 'article') {
    // Older blog results predate the per-piece labels and limits.
    const subtitleLabel = piece.subtitle_label ?? 'Meta description'
    const subtitleLimit = piece.subtitle_limit ?? (piece.format === 'blog_post' ? 155 : null)
    const toggle = 'rounded px-1.5 py-0.5 text-[11px] font-medium'
    return (
      <div className="space-y-3">
        <Field label="Title" aside={<Counter value={draft.title} limit={piece.title_limit ?? null} xCount={false} />}>
          <input
            className={`${inputClass} font-semibold`}
            disabled={!editable}
            value={draft.title}
            onChange={(e) => onDraft({ title: e.target.value })}
          />
        </Field>
        <Field label={subtitleLabel} aside={<Counter value={draft.subtitle} limit={subtitleLimit} xCount={false} />}>
          <input className={inputClass} disabled={!editable} value={draft.subtitle} onChange={(e) => onDraft({ subtitle: e.target.value })} />
        </Field>
        <div>
          <div className="mb-1 flex items-center justify-between gap-3 text-xs font-medium text-slate-500">
            <span className="flex items-center gap-1">
              Text
              <span className="ml-1 flex rounded-md bg-slate-100 p-0.5" role="group" aria-label="Show the text as">
                <button
                  type="button"
                  aria-pressed={!preview}
                  onClick={() => setPreview(false)}
                  className={`${toggle} ${!preview ? 'bg-surface text-slate-800 shadow-sm' : 'text-slate-500'}`}
                >
                  {editable ? 'Edit' : 'Markdown'}
                </button>
                <button
                  type="button"
                  aria-pressed={preview}
                  onClick={() => setPreview(true)}
                  className={`${toggle} ${preview ? 'bg-surface text-slate-800 shadow-sm' : 'text-slate-500'}`}
                >
                  Preview
                </button>
              </span>
            </span>
            <Words text={draft.text} piece={piece} />
          </div>
          {preview ? (
            <div className="max-h-[32rem] overflow-y-auto rounded-lg border border-slate-200 px-3 py-2">
              <RichText text={draft.text} />
            </div>
          ) : (
            <TextBox value={draft.text} min={10} max={26} editable={editable} onChange={(text) => onDraft({ text })} />
          )}
        </div>
        {piece.format === 'medium_story' && <Tags tags={draft.tags} editable={editable} onChange={(tags) => onDraft({ tags })} />}
      </div>
    )
  }
  if (shape === 'email') {
    return (
      <div className="space-y-3">
        <Field label="Subject" aside={<Counter value={draft.title} limit={60} xCount={false} />}>
          <input className={inputClass} disabled={!editable} value={draft.title} onChange={(e) => onDraft({ title: e.target.value })} />
        </Field>
        <Field label="Preview line" aside={<Counter value={draft.subtitle} limit={90} xCount={false} />}>
          <input className={inputClass} disabled={!editable} value={draft.subtitle} onChange={(e) => onDraft({ subtitle: e.target.value })} />
        </Field>
        <Field label="Message">
          <TextBox value={draft.text} min={8} max={22} editable={editable} onChange={(text) => onDraft({ text })} />
        </Field>
      </div>
    )
  }
  const words = Boolean(piece.requirements?.min_words || piece.requirements?.max_words || !piece.limit)
  return (
    <Field
      label={piece.format === 'instagram_caption' ? 'Caption' : piece.platform ? 'Post' : 'Text'}
      aside={
        <span className="flex gap-3">
          {words && <Words text={draft.text} piece={piece} />}
          <Counter value={draft.text} limit={piece.limit} xCount={piece.x_count} />
        </span>
      }
    >
      <TextBox value={draft.text} editable={editable} onChange={(text) => onDraft({ text })} />
    </Field>
  )
}

function PieceCard({
  requestId,
  piece,
  showLabel,
  social,
  onPieceChange,
  onOpenConnect,
}: {
  requestId: string
  piece: ContentPiece
  showLabel: boolean
  social: ReturnType<typeof useSocialConnections>
  onPieceChange: (piece: ContentPiece) => void
  onOpenConnect: () => void
}) {
  const [selectedId, setSelectedId] = useState(piece.recommended_id ?? piece.variants[0]?.id)
  const variant = piece.variants.find((v) => v.id === selectedId) ?? piece.variants[0]
  // Unsaved edits, per option, so switching options doesn't lose them.
  const [drafts, setDrafts] = useState<Record<string, Draft>>({})
  const [saving, setSaving] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState<SocialProvider | null>(null)
  const [message, setMessage] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)

  if (!variant) return null
  const shape: Shape = SHAPES[piece.format] ?? 'post'
  const draft = drafts[variant.id] ?? draftOf(variant)
  const changes = changesIn(shape, draft, variant)
  const dirty = Object.keys(changes).length > 0
  const current = withDraft(variant, draft)
  const places = destinationsFor(piece)
  // The piece's own network (LinkedIn / X) gets the main button and a confirm step.
  const network = places.find((p) => PUBLIC.includes(p)) ?? null
  const status = network ? social.byProvider(network) : null
  const published = network ? variant.published.find((p) => p.provider === network) : undefined
  // A public post can't change once it's out; private pages and drafts can.
  const postedPublicly = variant.published.some((p) => PUBLIC.includes(p.provider))
  const editable = !postedPublicly && !saving && busy === null
  const done = (provider: SocialProvider) => variant.published.some((p) => p.provider === provider)
  const notion = social.byProvider('notion')
  const medium = social.byProvider('medium')
  const mediumStory = piece.format === 'medium_story'
  const overLimit =
    piece.limit != null &&
    (shape === 'thread'
      ? draft.parts.some((p) => textLength(p, piece.x_count) > (piece.limit ?? Infinity))
      : textLength(draft.text, piece.x_count) > piece.limit)

  function edit(patch: Partial<Draft>) {
    setDrafts((prev) => ({ ...prev, [variant.id]: { ...draft, ...patch } }))
    setMessage(null)
  }

  function undo() {
    setDrafts((prev) => {
      const next = { ...prev }
      delete next[variant.id]
      return next
    })
    setMessage(null)
  }

  // Saves the edits; the server checks the option again (limits, your
  // requirements, figures, claims) and returns it.
  async function save(): Promise<boolean> {
    if (!dirty) return true
    setSaving(true)
    setMessage(null)
    try {
      const updated = await saveVariant(requestId, variant.id, { piece_id: piece.id, ...changes })
      onPieceChange({ ...piece, variants: piece.variants.map((v) => (v.id === updated.id ? updated : v)) })
      undo()
      setMessage({ tone: 'ok', text: 'Saved and checked again' })
      return true
    } catch (err) {
      setMessage({ tone: 'error', text: err instanceof BackendApiError ? err.message : 'Saving your changes failed' })
      return false
    } finally {
      setSaving(false)
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(variantAsText(current, piece.format))
      setMessage({ tone: 'ok', text: 'Copied' })
    } catch {
      setMessage({ tone: 'error', text: 'Copy failed; select the text instead' })
    }
  }

  async function publish(provider: SocialProvider) {
    setBusy(provider)
    setMessage(null)
    try {
      // What gets posted or saved is what the user sees: save edits first.
      if (dirty && !(await save())) return
      const updated = await publishVariant(requestId, { piece_id: piece.id, variant_id: variant.id, provider })
      onPieceChange({ ...piece, variants: piece.variants.map((v) => (v.id === updated.id ? updated : v)) })
      setConfirming(false)
      setMessage(null)
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
    const thread = shape === 'thread'
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

  // Without a LinkedIn connection, LinkedIn's post box opens with the text.
  function openInLinkedIn() {
    window.open(linkedinShareUrl(draft.text), '_blank', 'noopener')
  }

  async function copyMedium() {
    try {
      await copyForMedium(current, piece.format)
      setMessage({
        tone: 'ok',
        text: `Copied with formatting. Paste it into a new Medium story${current.tags?.length ? ', then add the tags when you publish' : ''}.`,
      })
    } catch {
      setMessage({ tone: 'error', text: 'Copy failed; select the text instead' })
    }
  }

  const secondary = 'rounded-full border border-slate-300 px-3 py-1 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50'
  const primary = 'rounded-full bg-brand-blue px-3.5 py-1 text-sm font-semibold text-white hover:bg-brand-blue/90 disabled:opacity-50'
  const tabNote = (v: ContentVariant) =>
    drafts[v.id] && Object.keys(changesIn(shape, drafts[v.id], v)).length > 0 ? 'Unsaved' : v.edited ? 'Edited' : ''

  return (
    <section className="rounded-xl border border-slate-200 bg-surface p-4">
      {showLabel && <h4 className="mb-3 text-sm font-semibold text-slate-900">{piece.label}</h4>}

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
                setConfirming(false)
                setMessage(null)
              }}
              className={`rounded-lg border px-2.5 py-1.5 text-left text-xs transition-colors ${
                v.id === variant.id ? 'border-sky-400 bg-sky-50 text-slate-900' : 'border-slate-200 text-slate-600 hover:bg-slate-50'
              }`}
            >
              <span className="font-semibold">Option {i + 1}</span>
              {v.id === piece.recommended_id && <span className="ml-1.5 font-semibold text-brand-blue">Recommended</span>}
              {(v.angle || tabNote(v)) && (
                <span className="block text-[11px] text-slate-400">{[v.angle, tabNote(v)].filter(Boolean).join(' · ')}</span>
              )}
            </button>
          ))}
        </div>
      )}

      <Body key={variant.id} piece={piece} draft={draft} editable={editable} onDraft={edit} />

      {dirty && (
        <div className="mt-2 flex flex-wrap items-center justify-end gap-2 text-sm">
          <span className="mr-auto text-xs text-slate-500">Unsaved changes</span>
          <button type="button" disabled={saving} onClick={undo} className="rounded-full px-3 py-1 text-slate-500 hover:bg-slate-100 disabled:opacity-50">
            Undo
          </button>
          <button type="button" disabled={saving || busy !== null} onClick={() => void save()} className={primary}>
            {saving ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      )}

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

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button type="button" onClick={() => void copy()} className={secondary}>
          Copy
        </button>
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
              disabled={busy !== null || saving}
              onClick={() => (notion.connected ? void publish('notion') : onOpenConnect())}
              title={notion.connected ? `Save as a private page in ${notion.account ?? 'Notion'}` : 'Connect Notion first'}
              className={secondary}
            >
              {busy === 'notion' ? 'Saving…' : 'Save to Notion'}
            </button>
          )}
          {places.includes('medium') && medium?.connected && !done('medium') && (
            <button type="button" disabled={busy !== null || saving} onClick={() => void publish('medium')} className={secondary}>
              {busy === 'medium' ? 'Saving…' : 'Save Medium draft'}
            </button>
          )}
          {network &&
            !published &&
            (!status?.connected ? (
              // Not connected (or the server has no app for it): open the
              // network with the post ready, and the user presses Post there.
              <>
                {status?.configured && (
                  <button type="button" onClick={onOpenConnect} className="text-sm font-medium text-sky-600 hover:underline">
                    Connect {NETWORK[network]} to post from here
                  </button>
                )}
                <button
                  type="button"
                  disabled={overLimit}
                  title={overLimit ? 'Shorten it to fit the limit first' : `Opens ${NETWORK[network]} with this post ready; you press Post`}
                  onClick={() => (network === 'x' ? void openInX() : openInLinkedIn())}
                  className="rounded-full bg-ink px-3.5 py-1 text-sm font-semibold text-white hover:bg-ink/90 disabled:opacity-50 dark:bg-white dark:text-ink"
                >
                  Open in {NETWORK[network]}
                </button>
              </>
            ) : confirming ? (
              <span className="flex flex-wrap items-center gap-2 text-sm">
                <span className="text-slate-600">
                  Post publicly as {status.account}?{network === 'x' ? ' Uses X API credits.' : ''}
                  {dirty ? ' Your changes are saved first.' : ''}
                </span>
                <button type="button" onClick={() => setConfirming(false)} className="rounded-full px-3 py-1 text-slate-500 hover:bg-slate-100">
                  Cancel
                </button>
                <button type="button" disabled={busy !== null || saving} onClick={() => void publish(network)} className={primary}>
                  {busy === network ? 'Posting…' : 'Post now'}
                </button>
              </span>
            ) : (
              <button
                type="button"
                disabled={overLimit || busy !== null || saving}
                title={overLimit ? 'Shorten it to fit the limit first' : undefined}
                onClick={() => setConfirming(true)}
                className={primary}
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
  // Scores are the agent's own working notes; older results had them in the summary.
  const summary = result.summary.replace(/\s?\(\d+(?:\.\d+)?\/10\)/g, '')
  return (
    <div className="space-y-4">
      {summary && <p className="text-sm text-slate-700">{summary}</p>}
      {result.pieces.map((piece) => (
        <PieceCard
          key={piece.id}
          requestId={requestId}
          piece={piece}
          showLabel={result.pieces.length > 1}
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
