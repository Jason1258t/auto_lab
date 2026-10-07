// Markdown from the backend (model output, quotes from web pages). Safe
// by design: react-markdown never renders raw HTML and drops unsafe links
// (javascript: and similar). Links open in a new tab without a referrer.
import type { ReactNode } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'

function textOf(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textOf).join('')
  return ''
}

const components: Components = {
  h1: ({ children }) => <h2 className="font-heading text-2xl font-semibold">{children}</h2>,
  h2: ({ children }) => <h3 className="mt-2 font-heading text-xl font-semibold">{children}</h3>,
  h3: ({ children }) => <h4 className="font-semibold">{children}</h4>,
  p: ({ children }) => <p className="leading-7">{children}</p>,
  ul: ({ children }) => <ul className="ml-6 list-disc">{children}</ul>,
  ol: ({ children }) => <ol className="ml-6 list-decimal">{children}</ol>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="text-primary underline underline-offset-2">
      {children}
    </a>
  ),
  // "*(⚠ no source)*" from the write step: make it stand out for the reviewer.
  em: ({ children }) =>
    textOf(children).includes('⚠') ? (
      <em className="rounded bg-destructive/10 px-1 text-sm text-destructive not-italic">{children}</em>
    ) : (
      <em>{children}</em>
    ),
  code: ({ children }) => <code className="rounded bg-muted px-1 text-sm">{children}</code>,
  pre: ({ children }) => <pre className="overflow-auto rounded-md bg-muted p-3 text-sm">{children}</pre>,
  img: ({ alt }) => <span className="text-muted-foreground">[{alt}]</span>, // no images from outside
}

export function Markdown({ text }: { text: string }) {
  return (
    <div className="grid gap-3 break-words">
      <ReactMarkdown components={components}>{text}</ReactMarkdown>
    </div>
  )
}
