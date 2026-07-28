import { useId, useState } from 'react';
import type { SourceObject } from '../api/types';
import { selectSafeSources } from '../lib/sourceUrl';

const SOURCE_LABEL = 'Nguồn tham khảo';

/**
 * Compact source reference.
 *
 * Collapsed, this shows only "Nguồn tham khảo". The previous panel rendered a
 * title card, publisher line, type badge, snippet and checked date for every
 * source, which crowded out the answer itself.
 *
 * All three states are driven by the same validated collection, so a response
 * whose URLs are all unsafe renders nothing at all rather than an empty panel
 * or a dead control.
 */
export function SourcePanel({ sources }: { sources: SourceObject[] }) {
  const [expanded, setExpanded] = useState(false);
  const listId = useId();
  const safeSources = selectSafeSources(sources);

  // Zero valid sources: no section, no heading, no disabled control, no gap.
  if (safeSources.length === 0) return null;

  // Exactly one: a direct link, with no disclosure to operate.
  if (safeSources.length === 1) {
    return (
      <p className="source-cta">
        <a
          className="source-cta-link"
          href={safeSources[0].href}
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
          {safeSources.map(({ source, href }) => (
            <li key={source.id}>
              <a href={href} target="_blank" rel="noopener noreferrer">
                {source.title || source.source_name || href}
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
