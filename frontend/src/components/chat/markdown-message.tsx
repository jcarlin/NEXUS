import React, { Fragment, useState, useCallback, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Copy, Check } from "lucide-react";
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

  // Recurse into React elements (e.g. unresolved link references wrapping [N])
  if (React.isValidElement<{ children?: React.ReactNode }>(children) && children.props?.children) {
    const inner = injectCitations(children.props.children, sources, onCitationClick);
    if (inner !== children.props.children) {
      return React.cloneElement(children, {}, inner);
    }
  }

  return children;
}

function CodeBlock({ language, children }: { language: string; children: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(children);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [children]);

  return (
    <div className="overflow-hidden rounded-md border border-border/50">
      <div className="flex items-center justify-between bg-muted/80 px-3 py-1.5">
        <span className="text-[11px] font-medium text-muted-foreground">{language || "code"}</span>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
        >
          {copied ? <Check className="h-3 w-3 text-green-600" /> : <Copy className="h-3 w-3" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <SyntaxHighlighter
        style={oneDark}
        language={language || "text"}
        customStyle={{ margin: 0, borderRadius: 0, fontSize: "0.75rem" }}
      >
        {children}
      </SyntaxHighlighter>
    </div>
  );
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
          const langMatch = className?.match(/language-(\w+)/);
          if (langMatch) {
            const code = String(children).replace(/\n$/, "");
            return <CodeBlock language={langMatch[1]!} >{code}</CodeBlock>;
          }
          return (
            <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs" {...props}>
              {children}
            </code>
          );
        },
        pre: ({ children }) => <div className="my-3">{children}</div>,
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
