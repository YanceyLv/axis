import { KlineChart } from "../components/Charts";
import { formatDateTime } from "../data-format";
import type { KnowledgeCase as KnowledgeCaseType } from "../types";

interface KnowledgeCaseProps {
  knowledgeCase: KnowledgeCaseType;
}

export function KnowledgeCase({ knowledgeCase }: KnowledgeCaseProps) {
  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>知识库</h1>
          <p>{knowledgeCase.title}</p>
        </div>
      </header>

      <div className="case-layout">
        <section className="panel chart-panel">
          <div className="panel-title">
            <h2>{knowledgeCase.symbol} 历史走势</h2>
            <span className="muted">{knowledgeCase.strategyName} / {formatDateTime(knowledgeCase.createdAt)}</span>
          </div>
          <KlineChart candles={knowledgeCase.candles} />
        </section>

        <aside className="panel detail-side">
          <div className="stat-block">
            <span>案例评分</span>
            <strong>{knowledgeCase.score}</strong>
          </div>
          <div className="stat-block">
            <span>关联策略</span>
            <strong>{knowledgeCase.strategyName}</strong>
          </div>
          <p>{knowledgeCase.summary}</p>
        </aside>
      </div>

      <div className="split-layout">
        <section className="panel">
          <div className="panel-title">
            <h2>成立原因</h2>
          </div>
          <ul className="analysis-list">
            {knowledgeCase.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </section>

        <section className="panel">
          <div className="panel-title">
            <h2>复盘经验</h2>
          </div>
          <ul className="analysis-list">
            {knowledgeCase.lessons.map((lesson) => (
              <li key={lesson}>{lesson}</li>
            ))}
          </ul>
        </section>
      </div>
    </section>
  );
}
