import React from 'react';
import CaseCard from './CaseCard';
import './LitigationColumn.css';

function LitigationColumn({ title, cases, onUpdateStatus }) {
  return (
    <div className="litigation-column">
      <h2 className="column-title">{title}</h2>
      <div className="column-content">
        {cases.length > 0 ? (
          cases.map(caseData => (
            <CaseCard
              key={caseData.id}
              caseData={caseData}
              onUpdateStatus={onUpdateStatus}
            />
          ))
        ) : (
          <p className="empty-column-message">No cases in this phase.</p>
        )}
      </div>
    </div>
  );
}

export default LitigationColumn;