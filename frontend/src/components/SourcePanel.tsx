import { useId, useState } from 'react';
import type { SourceObject } from '../api/types';
import { safeSourceHref, type SafeSource } from '../lib/sourceUrl';

const SOURCE_LABEL = 'Nguồn tham khảo';
const CITATION_LINK_LABEL = 'Xem văn bản chính thức';
const OFFICIAL_SEARCH_LINK_LABEL = 'Xem nguồn chính thức';

/**
 * Legal Correction Round 1 (task §5/§6): a curated rule's legal support can
 * be MULTIPLE independently traceable provisions that legitimately share
 * one document's official URL (e.g. a red-light rule's fine and its
 * licence-point deduction are both inside Nghị định 168/2024/NĐ-CP, so both
 * citations carry the exact same `vbpl.vn` link). `lib/sourceUrl.ts`'s
 * `selectSafeSources` de-duplicates by URL, which would silently collapse
 * two distinct citations into one -- this local variant de-duplicates by
 * `id` instead (falling back to the href when `id` is empty), so distinct
 * citations are never merged just because they resolve to the same
 * document. Behavior for every existing source is unchanged: MODE_2D and
 * official-search sources already have one unique `id` per unique href, so
 * id-based and href-based de-duplication agree for them.
 */
function selectSafeSourcesByIdentity(sources: readonly SourceObject[] | null | undefined): SafeSource[] {
  if (!sources) return [];

  const seenKeys = new Set<string>();
  const safeSources: SafeSource[] = [];

  for (const source of sources) {
    const href = safeSourceHref(source.url);
    if (href === null) continue;
    const dedupeKey = source.id || href;
    if (seenKeys.has(dedupeKey)) continue;
    seenKeys.add(dedupeKey);
    safeSources.push({ source, href });
  }

  return safeSources;
}

/** Vietnamese heading per traffic citation role (task §6) -- mirrors
 * `legal_fallback_orchestrator.py::_CITATION_ROLE_LABELS` exactly so the
 * backend's own summary text and this panel never disagree about what a
 * role means. Never label `signal_interpretation` (Luật 36 Điều 11) as the
 * penalty provision. */
const CITATION_ROLE_LABELS: Record<string, string> = {
  primary_penalty: 'Căn cứ mức phạt',
  licence_point_deduction: 'Căn cứ trừ điểm GPLX',
  signal_interpretation: 'Quy tắc tín hiệu giao thông',
};

/** "Điều 7 khoản 7 điểm c" / "Điều 11 khoản 1-4" (no điểm segment when the
 * citation genuinely has none, e.g. a multi-khoản signal-interpretation
 * rule -- never invented). Reads the string `clause_number` (not the
 * integer-only `applicable_clause`), so a khoản range like "1-4" renders
 * exactly, without lossy parsing. */
function citationLocatorLine(source: SourceObject): string {
  const parts = [`Điều ${source.article_number}`];
  if (source.clause_number) {
    parts.push(`khoản ${source.clause_number}`);
  }
  if (source.point_number) {
    parts.push(`điểm ${source.point_number}`);
  }
  return parts.join(' ');
}

/**
 * One traffic legal-citation card (task §6): its own role heading, its own
 * document/article/clause/point locator, its own relevance note, and its
 * own official URL -- never merged with a sibling citation's card or prose,
 * even when both share the same document's URL.
 */
function TrafficCitationBlock({ source, href }: SafeSource) {
  const heading = CITATION_ROLE_LABELS[source.citation_role ?? ''] ?? 'Căn cứ pháp lý';
  return (
    <div className="legal-citation legal-citation--traffic">
      <h3 className="legal-citation-heading">{heading}</h3>
      <p className="legal-citation-title">{source.document_title || source.source_name}</p>
      <p className="legal-citation-reference">{citationLocatorLine(source)}</p>
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

/** True only when the backend resolved curated article-level metadata for
 * this source (MODE_2D). Never true from model output: `article_number`
 * only ever comes from `SnippetRecord`/`attach_deposit_citation_metadata`.
 * Explicitly excludes a `retrieved_at` source: an official-search result can
 * also carry a resolved `article_number` + `document_title`, and must always
 * render as the official-search variant (with its domain/retrieval-date
 * display), never be mistaken for a curated MODE_2D citation. */
function hasArticleCitation(source: SourceObject): boolean {
  return Boolean(source.article_number && source.document_title && !source.retrieved_at);
}

/** True only for a Public Beta V0 official-source-search result: those are
 * the only sources ever carrying `retrieved_at` (curated/static sources use
 * `last_checked` instead -- see `contracts/legal_trust.py`). */
function hasOfficialSearchCitation(source: SourceObject): boolean {
  return Boolean(source.retrieved_at);
}

function hostnameOf(href: string): string {
  try {
    return new URL(href).hostname;
  } catch {
    return href;
  }
}

/**
 * Official-source-search variant (task §10): title, document number,
 * article/clause when found, the official domain hostname, and the
 * retrieval date -- so a user can see at a glance that this was fetched
 * live rather than served from the curated pack.
 */
function OfficialSearchCitationBlock({ source, href }: SafeSource) {
  const reference = [
    source.document_number ? `Số ${source.document_number}` : null,
    source.article_number ? `Điều ${source.article_number}` : null,
  ].filter(Boolean).join(' — ');

  return (
    <div className="legal-citation legal-citation--official-search">
      <h3 className="legal-citation-heading">Nguồn pháp luật chính thức</h3>
      <p className="legal-citation-title">{source.title || source.source_name}</p>
      {reference && <p className="legal-citation-reference">{reference}</p>}
      <p className="legal-citation-meta">
        <span className="legal-citation-domain">{hostnameOf(href)}</span>
        {' · '}
        <span className="legal-citation-retrieved-at">Tra cứu lúc {source.retrieved_at}</span>
      </p>
      <p className="source-cta">
        <a className="source-cta-link" href={href} target="_blank" rel="noopener noreferrer">
          {OFFICIAL_SEARCH_LINK_LABEL}
        </a>
      </p>
    </div>
  );
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
  const safeSources = selectSafeSourcesByIdentity(sources);

  // Zero valid sources: no section, no heading, no disabled control, no gap.
  if (safeSources.length === 0) return null;

  // Legal Correction Round 1 (task §6): when EVERY safe source is one of a
  // curated traffic rule's structured legal citations, render all of them
  // directly -- each its own role-labeled card, never merged into one card
  // or hidden behind a click, and never mixed with the generic disclosure
  // used for other multi-source responses. A rule with only one citation
  // (the helmet rule) still renders through this same path, still with its
  // own "Căn cứ mức phạt" heading rather than the generic one.
  if (safeSources.length > 0 && safeSources.every((safeSource) => Boolean(safeSource.source.citation_role))) {
    return (
      <div className="source-cta traffic-citations">
        {safeSources.map((safeSource) => (
          <TrafficCitationBlock key={safeSource.source.id || safeSource.href} {...safeSource} />
        ))}
      </div>
    );
  }

  // Exactly one: a direct link (or a full citation block), with no
  // disclosure to operate -- never both a citation block and a generic link
  // for the same single source.
  if (safeSources.length === 1) {
    const safeSource = safeSources[0];
    if (hasArticleCitation(safeSource.source)) {
      return <LegalCitationBlock {...safeSource} />;
    }
    if (hasOfficialSearchCitation(safeSource.source)) {
      return <OfficialSearchCitationBlock {...safeSource} />;
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
            <li key={safeSource.source.id || safeSource.href}>
              {hasArticleCitation(safeSource.source) ? (
                <LegalCitationBlock {...safeSource} />
              ) : hasOfficialSearchCitation(safeSource.source) ? (
                <OfficialSearchCitationBlock {...safeSource} />
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
