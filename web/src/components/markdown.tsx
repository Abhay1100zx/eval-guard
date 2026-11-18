"use client";

import { Children, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

/** Replaces "[2]" in plain text with a small button that calls onCite(2). Numbers with no matching source stay as text. */
function withCites(node: ReactNode, sources: number, onCite: (n: number) => void): ReactNode {
  return Children.map(node, (child) => {
    if (typeof child !== "string") return child;
    return child.split(/(\[\d{1,2}\])/g).map((part, i) => {
      const n = /^\[(\d{1,2})\]$/.exec(part)?.[1];
      if (!n || Number(n) < 1 || Number(n) > sources) return part;
      return (
        <button
          key={i}
          type="button"
          onClick={() => onCite(Number(n))}
          aria-label={`Show source ${n}`}
          className="mx-0.5 inline-flex size-[1.2rem] -translate-y-px items-center justify-center rounded-full bg-accent/20 align-baseline text-[0.68rem] font-semibold text-accent transition hover:bg-accent/35"
        >
          {n}
        </button>
      );
    });
  });
}

/**
 * Renders an AI answer as markdown. Raw HTML in the text is never rendered (react-markdown escapes it), and links open
 * in a new tab. With `sources` and `onCite`, "[1]"-style citations become buttons.
 */
export function Markdown({ text, sources = 0, onCite }: { text: string; sources?: number; onCite?: (n: number) => void }) {
  const c = (children: ReactNode) => (onCite && sources > 0 ? withCites(children, sources, onCite) : children);
  const components: Components = {
    p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{c(children)}</p>,
    li: ({ children }) => <li className="my-0.5">{c(children)}</li>,
    strong: ({ children }) => <strong className="font-semibold">{c(children)}</strong>,
    em: ({ children }) => <em>{c(children)}</em>,
    ul: ({ children }) => <ul className="my-2 list-disc pl-5">{children}</ul>,
    ol: ({ children }) => <ol className="my-2 list-decimal pl-5">{children}</ol>,
    h1: ({ children }) => <h3 className="mb-1 mt-3 text-base font-semibold first:mt-0">{children}</h3>,
    h2: ({ children }) => <h3 className="mb-1 mt-3 text-base font-semibold first:mt-0">{children}</h3>,
    h3: ({ children }) => <h4 className="mb-1 mt-3 font-semibold first:mt-0">{children}</h4>,
    a: ({ href, children }) => (
      <a href={href} target="_blank" rel="noopener noreferrer" className="text-accent underline underline-offset-2">
        {children}
      </a>
    ),
    blockquote: ({ children }) => <blockquote className="my-2 border-l-2 border-accent/40 pl-3 text-muted">{children}</blockquote>,
    pre: ({ children }) => <pre className="glass-inset my-2 overflow-x-auto rounded-xl p-3 text-xs [&_code]:bg-transparent [&_code]:p-0">{children}</pre>,
    code: ({ children }) => <code className="rounded bg-surface-2 px-1 py-0.5 text-[0.85em]">{children}</code>,
    hr: () => <hr className="my-3 border-border" />,
    table: ({ children }) => (
      <div className="my-2 overflow-x-auto">
        <table className="w-full text-left text-xs">{children}</table>
      </div>
    ),
    th: ({ children }) => <th className="border-b border-border px-2 py-1 font-semibold">{c(children)}</th>,
    td: ({ children }) => <td className="border-b border-border px-2 py-1">{c(children)}</td>,
  };
  return <ReactMarkdown components={components} remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>; // gfm adds tables, strikethrough and task lists
}
