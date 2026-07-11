import type { SourceObject } from '../api/types';
import { formatSourceType } from '../lib/format';

export function SourcePanel({ sources }: { sources: SourceObject[] }) {
  return (
    <section className="answer-section source-panel" aria-labelledby="source-heading">
      <h3 id="source-heading">Nguồn tham khảo</h3>
      {sources.length === 0 ? (
        <p className="source-empty">Chưa có nguồn phù hợp trong tập dữ liệu MVP. Câu trả lời cần được xem là định hướng thận trọng.</p>
      ) : (
        <ul className="source-list">
          {sources.map((source) => (
            <li key={source.id} className="source-item">
              <div className="source-heading-row">
                <div>
                  <p className="source-title">{source.title}</p>
                  <p className="source-name">{source.source_name}</p>
                </div>
                <span className="source-type">{formatSourceType(source.source_type)}</span>
              </div>
              <p className="source-snippet">{source.snippet}</p>
              <div className="source-footer">
                <span>Kiểm tra: {source.last_checked}</span>
                {source.url && (
                  <a href={source.url} target="_blank" rel="noreferrer">Mở nguồn</a>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
