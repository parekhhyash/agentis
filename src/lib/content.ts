import { useCallback, useEffect, useState } from 'react'

import { authedFetch } from './backendApi'

// Mirrors backend/agents/content_copy/schemas.py and api/social.py.

export interface ContentIssue {
  level: 'error' | 'warning'
  message: string
  // A claim about the company its profile doesn't back.
  quote?: string | null
}

export interface Publication {
  provider: SocialProvider
  url: string
  posted_at: string
  posts: number
}

export interface ContentVariant {
  id: string
  angle: string
  text: string
  parts: string[]
  title: string | null
  subtitle: string | null
  headlines: string[]
  descriptions: string[]
  tags?: string[]
  score: number | null
  scores: Record<string, number>
  reason: string
  issues: ContentIssue[]
  published: Publication[]
  // Changed by the user after it was written.
  edited?: boolean
}

export interface Requirements {
  min_words: number | null
  max_words: number | null
  max_characters: number | null
  must_include: string[]
  sections: string[]
  notes: string
}

export interface ContentPiece {
  id: string
  format: string
  label: string
  platform: SocialProvider | null
  limit: number | null
  x_count: boolean
  topic: string
  // Older results don't have these.
  requirements?: Requirements
  subtitle_label?: string | null
  title_limit?: number | null
  subtitle_limit?: number | null
  variants: ContentVariant[]
  recommended_id: string | null
}

export interface ContentResult {
  kind: 'content_copy'
  request: string
  summary: string
  pieces: ContentPiece[]
  notes: string[]
}

export function isContentResult(value: unknown): value is ContentResult {
  return typeof value === 'object' && value !== null && (value as { kind?: string }).kind === 'content_copy'
}

export const SHAPES: Record<string, 'post' | 'thread' | 'article' | 'email' | 'ad'> = {
  linkedin_post: 'post',
  x_post: 'post',
  x_thread: 'thread',
  instagram_caption: 'post',
  blog_post: 'article',
  email: 'email',
  ad_copy: 'ad',
  medium_story: 'article',
  long_form: 'article',
  general: 'post',
}

// Words as a reader counts them (backend/agents/content_copy/checks.py).
export function wordCount(text: string): number {
  return (text.replace(/https?:\/\/\S+/g, ' link ').match(/[\p{L}\p{N}](?:[\p{L}\p{N}'’.-]*[\p{L}\p{N}])?/gu) ?? []).length
}

// Where an option can go: Notion takes anything, Medium any article, LinkedIn
// and X their own formats (backend/services/content_runner.py destinations).
export function destinationsFor(piece: ContentPiece): SocialProvider[] {
  const places: SocialProvider[] = []
  if (piece.platform === 'linkedin' || piece.platform === 'x') places.push(piece.platform)
  if (SHAPES[piece.format] === 'article') places.push('medium')
  places.push('notion')
  return places
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function inlineHtml(text: string): string {
  return escapeHtml(text)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2">$1</a>')
}

// The small markdown subset the agent writes, as HTML, so a story pasted into
// an editor like Medium's keeps its headings, lists and emphasis.
export function markdownToHtml(markdown: string): string {
  const out: string[] = []
  let list: 'ul' | 'ol' | null = null
  const close = () => {
    if (list) out.push(`</${list}>`)
    list = null
  }
  for (const raw of markdown.split('\n')) {
    const line = raw.trimEnd()
    const heading = line.match(/^(#{1,4})\s+(.*)$/)
    const bullet = line.match(/^\s*[-*]\s+(.*)$/)
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/)
    if (heading) {
      close()
      const level = Math.min(heading[1].length, 4)
      out.push(`<h${level}>${inlineHtml(heading[2])}</h${level}>`)
    } else if (bullet || numbered) {
      const kind = bullet ? 'ul' : 'ol'
      if (list !== kind) {
        close()
        out.push(`<${kind}>`)
        list = kind
      }
      out.push(`<li>${inlineHtml((bullet ?? numbered)![1])}</li>`)
    } else if (line.startsWith('>')) {
      close()
      out.push(`<blockquote>${inlineHtml(line.replace(/^>\s?/, ''))}</blockquote>`)
    } else if (line.trim()) {
      close()
      out.push(`<p>${inlineHtml(line)}</p>`)
    } else {
      close()
    }
  }
  close()
  return out.join('')
}

// An article as it reads: title, the line under it (a blog post's meta
// description is metadata, so it's left out), then the body.
function storyMarkdown(variant: ContentVariant, format: string): string {
  const subtitle = format !== 'blog_post' && variant.subtitle ? `*${variant.subtitle}*` : ''
  return [variant.title && `# ${variant.title}`, subtitle, variant.text].filter(Boolean).join('\n\n')
}

// X's own "post intent" link: opens X with the text filled in, and the user
// presses Post from their own account. Free, with no developer app needed
// (X's API is pay-per-use for new developers since February 2026).
export function xIntentUrl(text: string): string {
  return `https://x.com/intent/tweet?text=${encodeURIComponent(text)}`
}

// LinkedIn's share link: opens the post box with the text filled in, and the
// user presses Post from their own profile. Free, like X's post intent.
export function linkedinShareUrl(text: string): string {
  return `https://www.linkedin.com/feed/?shareActive=true&text=${encodeURIComponent(text)}`
}

// A story for Medium's editor: title, subtitle and body as rich text.
export async function copyForMedium(variant: ContentVariant, format: string): Promise<void> {
  const markdown = storyMarkdown(variant, format)
  const html = markdownToHtml(markdown)
  if (typeof ClipboardItem !== 'undefined' && navigator.clipboard.write) {
    await navigator.clipboard.write([
      new ClipboardItem({
        'text/html': new Blob([html], { type: 'text/html' }),
        'text/plain': new Blob([markdown], { type: 'text/plain' }),
      }),
    ])
    return
  }
  await navigator.clipboard.writeText(markdown)
}

// Characters as X counts them (backend/agents/content_copy/formats.py): every
// link is 23, emoji and CJK count 2.
export function xLength(text: string): number {
  let total = 0
  const parts = text.split(/(https?:\/\/\S+)/i)
  for (const part of parts) {
    if (/^https?:\/\//i.test(part)) {
      total += 23
      continue
    }
    for (const char of part) {
      const code = char.codePointAt(0) ?? 0
      const light =
        code <= 0x10ff || (code >= 0x2000 && code <= 0x200d) || (code >= 0x2010 && code <= 0x201f) || (code >= 0x2032 && code <= 0x2037)
      total += light ? 1 : 2
    }
  }
  return total
}

export function textLength(text: string, xCount: boolean): number {
  return xCount ? xLength(text) : text.length
}

// Plain text for the clipboard, in the shape the platform expects.
export function variantAsText(variant: ContentVariant, format: string): string {
  const shape = SHAPES[format] ?? 'post'
  if (shape === 'thread') return variant.parts.join('\n\n')
  if (shape === 'ad')
    return [
      ...variant.headlines.map((h, i) => `Headline ${i + 1}: ${h}`),
      ...variant.descriptions.map((d, i) => `Description ${i + 1}: ${d}`),
      variant.text && `Primary text: ${variant.text}`,
    ]
      .filter(Boolean)
      .join('\n')
  if (shape === 'article') return storyMarkdown(variant, format)
  if (shape === 'email')
    return [variant.title && `Subject: ${variant.title}`, variant.subtitle && `Preview: ${variant.subtitle}`, variant.text]
      .filter(Boolean)
      .join('\n\n')
  return variant.text
}

export function publishVariant(
  requestId: string,
  body: { piece_id: string; variant_id: string; provider: SocialProvider },
): Promise<ContentVariant> {
  return authedFetch<ContentVariant>(`/content/requests/${requestId}/publish`, { method: 'POST', body: JSON.stringify(body) })
}

// The parts of an option the user can change.
export type VariantEdits = Partial<Pick<ContentVariant, 'title' | 'subtitle' | 'text' | 'parts' | 'headlines' | 'descriptions' | 'tags'>>

// Saves the user's edits; the server checks the option again and returns it.
export function saveVariant(requestId: string, variantId: string, body: VariantEdits & { piece_id: string }): Promise<ContentVariant> {
  return authedFetch<ContentVariant>(`/content/requests/${requestId}/variants/${variantId}`, { method: 'PATCH', body: JSON.stringify(body) })
}

// --- LinkedIn / X connections ---------------------------------------------------

export type SocialProvider = 'linkedin' | 'x' | 'notion' | 'medium'

export interface SocialStatus {
  provider: SocialProvider
  name: string
  configured: boolean
  connected: boolean
  account: string | null
  expires_at: string | null
  connect_with: 'oauth' | 'token'
}

export function useSocialConnections(enabled = true) {
  const [providers, setProviders] = useState<SocialStatus[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<SocialProvider | null>(null)

  const refresh = useCallback(async () => {
    try {
      setProviders((await authedFetch<{ providers: SocialStatus[] }>('/integrations/social')).providers)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not check your LinkedIn and X connections')
    }
  }, [])

  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    authedFetch<{ providers: SocialStatus[] }>('/integrations/social')
      .then((data) => !cancelled && setProviders(data.providers))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : 'Could not check your connections'))
    return () => {
      cancelled = true
    }
  }, [enabled])

  async function connect(provider: SocialProvider): Promise<string | null> {
    setBusy(provider)
    try {
      const { url } = await authedFetch<{ url: string }>(`/integrations/social/${provider}/connect`, { method: 'POST' })
      window.location.href = url
      return null
    } catch (err) {
      setBusy(null)
      return err instanceof Error ? err.message : 'Could not start the sign-in'
    }
  }

  // Medium: a pasted integration token, checked by the server.
  async function connectWithToken(provider: SocialProvider, token: string): Promise<string | null> {
    setBusy(provider)
    try {
      await authedFetch(`/integrations/social/${provider}/token`, { method: 'POST', body: JSON.stringify({ token }) })
      await refresh()
      return null
    } catch (err) {
      return err instanceof Error ? err.message : 'Could not connect'
    } finally {
      setBusy(null)
    }
  }

  async function disconnect(provider: SocialProvider) {
    setBusy(provider)
    try {
      await authedFetch(`/integrations/social/${provider}`, { method: 'DELETE' })
      await refresh()
    } finally {
      setBusy(null)
    }
  }

  const byProvider = (p: SocialProvider) => providers?.find((s) => s.provider === p) ?? null
  return { providers, error, busy, connect, connectWithToken, disconnect, refresh, byProvider }
}
