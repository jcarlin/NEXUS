import { Fragment, useCallback, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CitationMarker } from "./citation-marker";
import type { SourceDocument } from "@/types";

interface MarkdownMessageProps {
  content: string;
  sources: SourceDocument[];
  onCitationClick?: (source: SourceDocument, index: number) => void;
}

/** Walk children and replace [N] patterns with CitationMarker components. */
function injectCitations(
  children: ReactNode,
  sources: SourceDocument[],
  onCitationClick?: (source: SourceDocument, index: number) => void,
): ReactNode {
  if (typeof children === "string") {
    const parts = children.split(/(\[\d+\])/g);
    if (parts.length === 1) return children;
    return parts.map((part, i) => {
      const match = part.match(/^\[(\d+)\]$/);
      if (match) {
        const idx = parseInt(match[1]!, 10) - 1;
        const source = sources[idx];
        if (source) {
          return (
            <CitationMarker
              key={`cite-${i}`}
              index={idx}
              source={source}
              onQuickView={
                onCitationClick
                  ? () => onCitationClick(source, idx)
                  : undefined
              }
            />
          );
        }
      }
      return <Fragment key={i}>{part}</Fragment>;
    });
  }

  if (Array.isArray(children)) {
    return children.map((child, i) => (
      <Fragment key={i}>
        {injectCitations(child, sources, onCitationClick)}
      </Fragment>
    ));
  }

  return children;
}

export function MarkdownMessage({ content, sources, onCitationClick }: MarkdownMessageProps) {
  const inject = useCallback(
    (children: ReactNode) => injectCitations(children, sources, onCitationClick),
    [sources, onCitationClick],
  );

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => (
          <p className="mb-3 last:mb-0 leading-relaxed">{inject(children)}</p>
        ),
        h1: ({ children }) => (
          <h1 className="mb-3 mt-4 text-lg font-bold first:mt-0">{inject(children)}</h1>
        ),
        h2: ({ children }) => (
          <h2 className="mb-2 mt-4 text-base font-semibold first:mt-0">{inject(children)}</h2>
        ),
        h3: ({ children }) => (
          <h3 className="mb-2 mt-3 text-sm font-semibold first:mt-0">{inject(children)}</h3>
        ),
        strong: ({ children }) => (
          <strong className="font-semibold">{inject(children)}</strong>
        ),
        em: ({ children }) => <em>{inject(children)}</em>,
        ul: ({ children }) => (
          <ul className="mb-3 list-disc pl-5 space-y-1">{children}</ul>
        ),
        ol: ({ children }) => (
          <ol className="mb-3 list-decimal pl-5 space-y-1">{children}</ol>
        ),
        li: ({ children }) => (
          <li className="leading-relaxed">{inject(children)}</li>
        ),
        blockquote: ({ children }) => (
          <blockquote className="my-3 border-l-2 border-primary/30 pl-3 italic text-muted-foreground">
            {children}
          </blockquote>
        ),
        code: ({ className, children, ...props }) => {
          const isBlock = className?.includes("language-");
          if (isBlock) {
            return (
              <code
                className="block overflow-x-auto rounded-md bg-muted p-3 font-mono text-xs"
                {...props}
              >
                {children}
              </code>
            );
          }
          return (
            <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs" {...props}>
              {children}
            </code>
          );
        },
        pre: ({ children }) => <pre className="my-3">{children}</pre>,
        table: ({ children }) => (
          <div className="my-3 overflow-x-auto">
            <table className="w-full border-collapse text-xs">{children}</table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="border-b bg-muted/50">{children}</thead>
        ),
        th: ({ children }) => (
          <th className="px-3 py-1.5 text-left font-medium">{inject(children)}</th>
        ),
        td: ({ children }) => (
          <td className="border-t px-3 py-1.5">{inject(children)}</td>
        ),
        a: ({ href, children }) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary underline underline-offset-2 hover:text-primary/80"
          >
            {inject(children)}
          </a>
        ),
        hr: () => <hr className="my-4 border-border" />,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
