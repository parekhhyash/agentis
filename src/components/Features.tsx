const LEADS = [
  { name: 'Mamaearth', meta: 'D2C beauty · Gurugram', fit: 'Strong fit', tone: 'bg-emerald-50 text-emerald-700', initial: 'M', tile: 'bg-brand-pink' },
  { name: 'DrinkPrime', meta: 'Consumer · Bengaluru', fit: 'Strong fit', tone: 'bg-emerald-50 text-emerald-700', initial: 'D', tile: 'bg-brand-sky' },
  { name: 'OZi', meta: 'Kids retail · Mumbai', fit: 'Possible', tone: 'bg-amber-50 text-amber-700', initial: 'O', tile: 'bg-brand-yellow' },
]

function LeadsMockup() {
  return (
    <div className="pointer-events-none absolute -right-4 -bottom-6 w-60 rotate-2 rounded-xl border border-slate-200 bg-surface p-4 shadow-xl sm:w-72">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold text-slate-900">Qualified leads</span>
        <span className="rounded-full bg-brand-blue/10 px-2 py-0.5 text-[10px] font-medium text-brand-blue">5 of 5 found</span>
      </div>
      <ul className="mt-3 space-y-2.5">
        {LEADS.map((l) => (
          <li key={l.name} className="flex items-center gap-2.5">
            <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-[11px] font-semibold text-ink ${l.tile}`}>
              {l.initial}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-[11px] font-semibold text-slate-900">{l.name}</span>
              <span className="block truncate text-[9px] text-slate-400">{l.meta}</span>
            </span>
            <span className={`rounded-full px-2 py-0.5 text-[9px] font-semibold whitespace-nowrap ${l.tone}`}>{l.fit}</span>
          </li>
        ))}
      </ul>
      <div className="mt-3 flex items-center gap-1.5 border-t border-slate-100 pt-2.5 text-[10px] text-slate-500">
        <svg viewBox="0 0 16 16" className="h-3 w-3 text-brand-blue" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M6.5 9.5 9.5 6.5M7 4.5l1-1a2.5 2.5 0 0 1 3.5 3.5l-1 1M9 11.5l-1 1A2.5 2.5 0 0 1 4.5 9l1-1" strokeLinecap="round" />
        </svg>
        Every claim linked to a source
      </div>
    </div>
  )
}

const SEQUENCE = [
  { step: 'Intro email', when: 'Mon', status: 'Opened', dot: 'bg-brand-sky' },
  { step: 'Follow-up', when: 'Thu', status: 'Replied', dot: 'bg-brand-yellow' },
  { step: 'Call invite', when: 'Fri', status: 'Booked', dot: 'bg-emerald-400' },
]

function SequenceMockup() {
  return (
    <div className="pointer-events-none absolute -right-4 -bottom-6 w-60 -rotate-2 rounded-xl bg-surface p-4 shadow-xl sm:w-72">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold text-slate-900">Outreach sequence</span>
        <span className="text-[10px] whitespace-nowrap text-slate-400">3 steps</span>
      </div>
      <ol className="mt-3 space-y-2">
        {SEQUENCE.map((s, i) => (
          <li key={s.step} className="flex items-center gap-2.5">
            <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[9px] font-semibold text-ink ${s.dot}`}>
              {i + 1}
            </span>
            <span className="flex-1 text-[11px] text-slate-700">{s.step}</span>
            <span className="text-[10px] text-slate-400">{s.when}</span>
            <span className="w-12 rounded-full bg-slate-100 py-0.5 text-center text-[9px] font-medium text-slate-600">
              {s.status}
            </span>
          </li>
        ))}
      </ol>
      <div className="mt-3 flex items-center gap-1.5 rounded-lg bg-brand-violet/10 px-2.5 py-1.5 text-[10px] font-semibold text-brand-violet dark:bg-brand-violet/25 dark:text-[#a98bff]">
        <svg viewBox="0 0 16 16" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <rect x="2.5" y="3.5" width="11" height="10" rx="1.5" />
          <path d="M2.5 6.5h11M5.5 2v3M10.5 2v3" strokeLinecap="round" />
        </svg>
        Meeting booked · Fri 3:00 PM
      </div>
    </div>
  )
}

const DRAFTS = [
  { kind: 'Blog post', lines: ['w-full', 'w-11/12', 'w-4/5'] },
  { kind: 'Ad copy', lines: ['w-5/6', 'w-2/3'] },
  { kind: 'LinkedIn post', lines: ['w-full', 'w-3/4'] },
]

function DraftsMockup() {
  return (
    <div className="relative mt-6 h-44" aria-hidden="true">
      {DRAFTS.map((d, i) => (
        <div
          key={d.kind}
          className="absolute inset-x-0 rounded-xl bg-surface p-3 shadow-lg"
          style={{ top: `${i * 34}px`, transform: `rotate(${[-2, 1.5, -1][i]}deg) scale(${0.92 + i * 0.04})`, zIndex: i }}
        >
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-semibold text-slate-900">{d.kind}</span>
            {i === DRAFTS.length - 1 && (
              <span className="rounded-full bg-brand-mauve/15 px-2 py-0.5 text-[9px] font-medium text-brand-mauve">
                On-brand tone
              </span>
            )}
          </div>
          <div className="mt-2 space-y-1.5">
            {d.lines.map((w, j) => (
              <div key={j} className={`h-1.5 rounded-full bg-slate-200 ${w}`} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function ChatMockup() {
  return (
    <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-3">
      <div className="flex justify-start">
        <div className="max-w-[75%] rounded-lg rounded-bl-sm bg-surface px-3 py-1.5 text-[11px] text-slate-600 shadow-sm">
          My order hasn't arrived yet
        </div>
      </div>
      <div className="mt-2 flex justify-end">
        <div className="max-w-[75%] rounded-lg rounded-br-sm bg-brand-blue px-3 py-1.5 text-[11px] text-white shadow-sm">
          Sorry for the wait! Here&apos;s how to track it
        </div>
      </div>
      <p className="mt-1 text-right text-[10px] text-slate-400">Draft, sent when you approve</p>
    </div>
  )
}

// Points (0-100) for the report's chart, drawn into a 200x64 viewBox.
const REPORT_POINTS = [18, 30, 24, 42, 36, 58, 52, 74]

function ReportMockup() {
  const xy = REPORT_POINTS.map((p, i) => [(i * 200) / (REPORT_POINTS.length - 1), 60 - (p / 100) * 52] as const)
  const line = xy.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ')
  const [lastX, lastY] = xy[xy.length - 1]
  return (
    <div className="pointer-events-none absolute -right-4 -bottom-6 w-60 rotate-2 rounded-xl border border-white/40 bg-surface p-4 shadow-xl sm:w-72">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold text-slate-900">Weekly report</span>
        <span className="rounded-full bg-brand-pink/40 px-2 py-0.5 text-[10px] font-medium text-slate-700">
          Mon 9:00
        </span>
      </div>
      <div className="mt-3 flex items-baseline gap-2">
        <span className="font-display text-3xl text-slate-900">+40%</span>
        <span className="text-[11px] text-slate-500">pipeline vs last week</span>
      </div>
      <svg viewBox="0 0 200 64" className="mt-2 h-auto w-full" aria-hidden="true">
        <path d={`${line} L200 64 L0 64 Z`} className="fill-brand-pink/50" />
        <path d={line} fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="stroke-pink-600" />
        <circle cx={lastX} cy={lastY} r="3.5" className="fill-pink-600" />
      </svg>
      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
        {[
          ['Leads', '128'],
          ['Replies', '34'],
          ['Meetings', '9'],
        ].map(([label, value]) => (
          <div key={label} className="rounded-lg bg-slate-50 py-1.5">
            <div className="text-xs font-semibold text-slate-900">{value}</div>
            <div className="text-[9px] text-slate-500">{label}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Features() {
  return (
    <section id="features" className="relative z-10 px-4 py-24 sm:px-6 sm:py-32">
      <div className="mx-auto max-w-2xl text-center">
        <span className="text-sm font-semibold tracking-[0.2em] text-brand-blue uppercase">
          Agents
        </span>
        <h2 className="font-display mt-4 text-4xl text-slate-900 sm:text-5xl">
          One team, every function
        </h2>
        <p className="mt-6 text-lg leading-relaxed text-slate-600">
          Each agent specializes in a single job, the way a great hire would,
          and they all report to you.
        </p>
      </div>

      <div className="mx-auto mt-16 grid max-w-[78rem] min-[1680px]:max-w-[86rem] grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {/* Lead Research — white, wide, qualified-leads mockup */}
        <div className="relative col-span-1 min-h-72 overflow-hidden rounded-2xl border border-slate-200 bg-surface p-7 pb-52 shadow-sm sm:col-span-2 sm:pb-7">
          <h3 className="max-w-[60%] text-xl font-semibold text-slate-900">
            Lead Research
          </h3>
          <p className="mt-2 max-w-[55%] text-[15px] leading-relaxed text-slate-600">
            Find and qualify real companies as sales leads, so your pipeline
            keeps filling while you sleep.
          </p>
          <LeadsMockup />
        </div>

        {/* Sales & Outreach — solid violet, wide, outreach sequence mockup */}
        <div className="relative col-span-1 min-h-72 overflow-hidden rounded-2xl bg-brand-violet p-7 pb-48 sm:col-span-2 sm:pb-7">
          <h3 className="max-w-[60%] text-xl font-semibold text-white">
            Sales &amp; Outreach
          </h3>
          <p className="mt-2 max-w-[55%] text-[15px] leading-relaxed text-white/80">
            Draft sequences, follow up, and book meetings with the leads
            already qualified for you.
          </p>
          <SequenceMockup />
        </div>

        {/* Content & Copy — mauve, narrow, stacked drafts mockup */}
        <div className="relative col-span-1 overflow-hidden rounded-2xl bg-brand-mauve p-7">
          <h3 className="text-lg font-semibold text-white">
            Content &amp; Copy
          </h3>
          <p className="mt-2 text-[15px] leading-relaxed text-white/85">
            Blog posts, ad copy, and social captions that sound like your
            brand, not a template.
          </p>
          <DraftsMockup />
        </div>

        {/* Customer Support — white, narrow, chat mockup framed inside */}
        <div className="col-span-1 rounded-2xl border border-slate-200 bg-surface p-7 shadow-sm">
          <h3 className="text-lg font-semibold text-slate-900">
            Customer Support
          </h3>
          <p className="mt-2 text-[15px] leading-relaxed text-slate-600">
            Sort tickets by urgency and draft replies from your help articles. You approve each one; the rest go to your team.
          </p>
          <ChatMockup />
        </div>

        {/* Data & Reporting — deep pink (white text stays readable), wide, report mockup */}
        <div className="relative col-span-1 min-h-80 overflow-hidden rounded-2xl bg-pink-600 p-7 pb-56 sm:col-span-2 sm:pb-7">
          <h3 className="text-xl font-semibold text-white">
            Data &amp; Reporting
          </h3>
          <p className="mt-2 max-w-[55%] text-[15px] leading-relaxed text-white/85">
            Turn raw numbers into a clean weekly report, no spreadsheet
            wrangling required.
          </p>
          <ReportMockup />
        </div>

        {/* Operations — white, full width banner */}
        <div
          className="relative col-span-1 overflow-hidden rounded-2xl border border-slate-200 bg-surface p-7 sm:col-span-2 lg:col-span-4"
          style={{
            backgroundImage:
              'radial-gradient(circle, var(--color-slate-200) 1px, transparent 1px)',
            backgroundSize: '16px 16px',
            backgroundPosition: 'right -20px top -20px',
          }}
        >
          <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
            <div>
              <h3 className="text-xl font-semibold text-slate-900">
                Operations
              </h3>
              <p className="mt-2 max-w-md text-[15px] leading-relaxed text-slate-600">
                Put any agent on a schedule: a Monday report, daily follow-up
                drafts, a fresh lead list every month. It runs on time, and you
                still approve anything that goes out.
              </p>
            </div>
            <span className="inline-flex shrink-0 items-center gap-2 rounded-full bg-brand-blue px-4 py-2 text-sm font-semibold text-white">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-white/70 motion-reduce:animate-none" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-white" />
              </span>
              Always on
            </span>
          </div>
        </div>
      </div>
    </section>
  )
}
