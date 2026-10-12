import type { ReactNode } from 'react'

// Renders the small Markdown subset the Manager writes (headings,
// bullet and numbered lists, paragraphs, **bold**, `code`, links) as React
// elements. No HTML is ever injected.

function inline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^\s)]+\))/g
  let last = 0
  let match: RegExpExecArray | null
  let i = 0
  while ((match = pattern.exec(text))) {
    if (match.index > last) nodes.push(text.slice(last, match.index))
    const token = match[0]
    const key = `${keyPrefix}-${i++}`
    if (token.startsWith('**')) {
      nodes.push(
        <strong key={key} className="font-semibold text-slate-900">
          {token.slice(2, -2)}
        </strong>,
      )
    } else if (token.startsWith('`')) {
      nodes.push(
        <code key={key} className="rounded bg-slate-100 px-1 py-0.5 text-[0.9em]">
          {token.slice(1, -1)}
        </code>,
      )
    } else {
      const [, label, href] = token.match(/\[([^\]]+)\]\(([^)]+)\)/) ?? []
      nodes.push(
        <a key={key} href={href} target="_blank" rel="noreferrer" className="text-sky-600 underline-offset-2 hover:underline">
          {label}
        </a>,
      )
    }
    last = match.index + token.length
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}

type Block =
  | { kind: 'heading'; text: string }
  | { kind: 'paragraph'; lines: string[] }
  | { kind: 'list'; ordered: boolean; items: string[] }

function parse(source: string): Block[] {
  const blocks: Block[] = []
  for (const raw of source.replace(/\r\n/g, '\n').split('\n')) {
    const line = raw.trimEnd()
    const last = blocks[blocks.length - 1]
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/)
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/)
    if (!line.trim()) {
      blocks.push({ kind: 'paragraph', lines: [] })
    } else if (/^#{1,6}\s+/.test(line)) {
      blocks.push({ kind: 'heading', text: line.replace(/^#{1,6}\s+/, '') })
    } else if (bullet || numbered) {
      const ordered = Boolean(numbered)
      const text = (bullet ?? numbered)![1]
      if (last?.kind === 'list' && last.ordered === ordered) last.items.push(text)
      else blocks.push({ kind: 'list', ordered, items: [text] })
    } else if (last?.kind === 'paragraph') {
      last.lines.push(line.trim())
    } else {
      blocks.push({ kind: 'paragraph', lines: [line.trim()] })
    }
  }
  return blocks.filter((b) => b.kind !== 'paragraph' || b.lines.length > 0)
}

export default function RichText({ text }: { text: string }) {
  return (
    <div className="space-y-3 text-[15px] leading-relaxed text-slate-700">
      {parse(text).map((block, b) => {
        if (block.kind === 'heading') {
          return (
            <h4 key={b} className="pt-1 font-semibold text-slate-900">
              {inline(block.text, `h${b}`)}
            </h4>
          )
        }
        if (block.kind === 'list') {
          const List = block.ordered ? 'ol' : 'ul'
          return (
            <List key={b} className={`space-y-1 pl-5 ${block.ordered ? 'list-decimal' : 'list-disc'} marker:text-slate-400`}>
              {block.items.map((item, i) => (
                <li key={i}>{inline(item, `l${b}-${i}`)}</li>
              ))}
            </List>
          )
        }
        return <p key={b}>{block.lines.map((line, i) => [i > 0 && <br key={`br${i}`} />, ...inline(line, `p${b}-${i}`)])}</p>
      })}
    </div>
  )
}
