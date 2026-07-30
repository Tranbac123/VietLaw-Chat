import { useId, useState } from 'react';
import type { SourceObject } from '../api/types';
import { selectSafeSources, type SafeSource } from '../lib/sourceUrl';

const SOURCE_LABEL = 'Nguồn tham khảo';
const CITATION_LINK_LABEL = 'Xem văn bản chính thức';

/** True only when the backend resolved curated article-level metadata for
 * this source (MODE_2D). Never true from model output: `article_number`
 * only ever comes from `SnippetRecord`/`attach_deposit_citation_metadata`. */
function hasArticleCitation(source: SourceObject): boolean {
  return Boolean(source.article_number && source.document_title);
}

/** "Khoản 2 Điều 328" / "Điều 328" — no clause prefix when the backend did
 * not resolve one, per the instruction not to invent a clause. */
function referenceLine(source: SourceObject): string {
  const clause = source.applicable_clause != null ? `Khoản ${source.applicable_clause} ` : '';
  const document = [source.document_title, source.document_number ? `số ${source.document_number}` : null]
    .filter(Boolean)
    .join(', ');
  return `${clause}Điều ${source.article_number} — ${document}`;
}

/**
 * Legal-citation variant of the source display: article, clause (when
 * resolved), document identity and the curated relevance note are all
 * visible without opening the link. Replaces the generic link entirely for
 * this source -- never rendered alongside a second generic card for the
 * same citation.
 */
function LegalCitationBlock({ source, href }: SafeSource) {
  return (
    <div className="legal-citation">
      <h3 className="legal-citation-heading">Căn cứ pháp lý</h3>
      <p className="legal-citation-reference" title={source.article_title ?? undefined}>
        {referenceLine(source)}
      </p>
      {source.relevance_note && (
        <p className="legal-citation-relevance">{source.relevance_note}</p>
      )}
      <p className="source-cta">
        <a className="source-cta-link" href={href} target="_blank" rel="noopener noreferrer">
          {CITATION_LINK_LABEL}
        </a>
      </p>
    </div>
  );
}

/**
 * Compact source reference.
 *
 * Collapsed, this shows only "Nguồn tham khảo" -- unless the backend resolved
 * article-level legal-citation metadata for that source (MODE_2D), in which
 * case the citation panel (article, clause, document identity, relevance,
 * official link) renders in its place, never in addition to it. Sources
 * without curated article-level metadata fall back to this original generic
 * display unchanged.
 *
 * All states are driven by the same validated collection, so a response
 * whose URLs are all unsafe renders nothing at all rather than an empty panel
 * or a dead control.
 */
export function SourcePanel({ sources }: { sources: SourceObject[] }) {
  const [expanded, setExpanded] = useState(false);
  const listId = useId();
  const safeSources = selectSafeSources(sources);

  // Zero valid sources: no section, no heading, no disabled control, no gap.
  if (safeSources.length === 0) return null;

  // Exactly one: a direct link (or a full citation block), with no
  // disclosure to operate -- never both a citation block and a generic link
  // for the same single source.
  if (safeSources.length === 1) {
    const safeSource = safeSources[0];
    if (hasArticleCitation(safeSource.source)) {
      return <LegalCitationBlock {...safeSource} />;
    }
    return (
      <p className="source-cta">
        <a
          className="source-cta-link"
          href={safeSource.href}
          target="_blank"
          rel="noopener noreferrer"
        >
          {SOURCE_LABEL}
        </a>
      </p>
    );
  }

  return (
    <div className="source-cta">
      <button
        className="source-cta-toggle"
        type="button"
        aria-expanded={expanded}
        aria-controls={listId}
        onClick={() => setExpanded((value) => !value)}
      >
        <span className="source-cta-caret" aria-hidden="true">{expanded ? '▾' : '▸'}</span>
        {SOURCE_LABEL} ({safeSources.length})
      </button>
      {expanded && (
        <ul className="source-cta-list" id={listId}>
          {safeSources.map((safeSource) => (
            <li key={safeSource.source.id}>
              {hasArticleCitation(safeSource.source) ? (
                <LegalCitationBlock {...safeSource} />
              ) : (
                <a href={safeSource.href} target="_blank" rel="noopener noreferrer">
                  {safeSource.source.title || safeSource.source.source_name || safeSource.href}
                </a>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
