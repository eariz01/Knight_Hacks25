import React, { useState } from 'react';
import './CaseCard.css';

function CaseCard({ caseData, onUpdateStatus }) {
  const [isExpanded, setIsExpanded] = useState(false);

  // Helper function to get the correct CSS class for the status border
  const getStatusClass = (status) => {
    // Clean the status data to ignore whitespace
    const cleanStatus = status ? status.trim() : 'Not Started'; 
    
    switch (cleanStatus) {
      case 'Approved':
        return 'status-approved';
      case 'Not Approved':
        return 'status-not-approved';
      case 'Pending':
        return 'status-pending';
      case 'Not Started':
      default:
        return 'status-not-started';
    }
  };

  // Flips the isExpanded state
  const toggleExpand = () => {
    setIsExpanded(!isExpanded);
  };

  // Get the checklist for the case's *current* phase
  const currentPhaseChecklist = caseData.checklist?.[caseData.litigation_phase] || {};

  return (
    <div className={`case-card ${getStatusClass(caseData.status)}`}>
      {/* ALWAYS VISIBLE HEADER */}
      <div className="card-always-visible" onClick={toggleExpand}>
        <div className="card-header-top">
          <strong>{caseData.main_summary}</strong>
          <span className="case-id">ID: {caseData.id}</span>
        </div>
        <div className="card-client-name">
          Client: <span>{caseData.client_name || 'N/A'}</span>
        </div>
        <div className="card-venue">
          <span>
            Venue: {caseData.venue ? `${caseData.venue.court_type}, ${caseData.venue.county}` : 'N/A'}
          </span>
          <span className="expand-icon">{isExpanded ? '▲' : '▼'}</span>
        </div>
      </div>

      {/* DROPDOWN CONTENT - Renders only when isExpanded is true */}
      {isExpanded && (
        <div className="card-dropdown-content">
          <div className="card-section">
            <strong>Key Findings:</strong>
            <ul>
              {caseData.key_findings.map((finding, index) => (
                <li key={index}>{finding}</li>
              ))}
            </ul>
          </div>

          <div className="card-section">
            <strong>Medical History:</strong>
            <p>{caseData.medical_history_summary}</p>
          </div>

          <div className="card-section">
            <strong>HIPAA Necessity:</strong>
            <p>{caseData.hipaa_necessity}</p>
          </div>

          {/* Relevant Cases Section */}
          <div className="card-section relevant-cases-section">
            <strong>Relevant Cases:</strong>
            {caseData.relevant_cases && caseData.relevant_cases.length > 0 ? (
              <ul>
                {caseData.relevant_cases.map((rc, index) => (
                  <li key={index}>
                    <p><strong>{rc.case_name}</strong> - {rc.citation}</p>
                    <p>Court: {rc.court}</p>
                    <p>Summary: {rc.summary}</p>
                    <p>Relevance: {(rc.relevance_score * 100).toFixed(0)}%</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p>No relevant state cases found.</p>
            )}

            {/* This block is now corrected with 'fc' */}
            <strong>Federal Cases:</strong>
            {caseData.federal_cases && caseData.federal_cases.length > 0 ? (
              <ul>
                {caseData.federal_cases.map((fc, index) => ( 
                  <li key={index}>
                    <p><strong>{fc.case_name}</strong> - {fc.citation}</p>
                    <p>Court: {fc.court}</p>
                    <p>Summary: {fc.summary}</p>
                    <p>Relevance: {(fc.relevance_score * 100).toFixed(0)}%</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p>No relevant federal cases found.</p>
            )}
            {caseData.notes && <p className="case-notes">Notes: {caseData.notes}</p>}
          </div>

          {/* Dynamic Checklist Section */}
          {Object.keys(currentPhaseChecklist).length > 0 && (
            <div className="card-section checklist-section">
              <strong>{caseData.litigation_phase} Checklist:</strong>
              <ul>
                {Object.entries(currentPhaseChecklist).map(([step, isComplete]) => (
                  <li key={step} className={isComplete ? 'checklist-item-complete' : 'checklist-item-incomplete'}>
                    {step}
                  </li>
                ))}
              </ul>
            </div>
          )}


          <div className="card-footer">
            <strong>Political Reading:</strong> {caseData.political_reading}
          </div>

          {/* This logic now cleans the data, just like getStatusClass */}
          {caseData.status && caseData.status.trim() === 'Pending' && (
            <div className="action-buttons">
              <button
                className="btn btn-approve"
                onClick={(e) => { 
                  e.stopPropagation(); // Prevents card from closing
                  onUpdateStatus(caseData.id, 'Approved'); 
                }}
              >
                Approve
              </button>
              <button
                className="btn btn-decline"
                onClick={(e) => { 
                  e.stopPropagation(); // Prevents card from closing
                  onUpdateStatus(caseData.id, 'Not Approved'); 
                }}
              >
                Decline
              </button>
            </div>
          )}

        </div>
      )}
    </div>
  );
}

export default CaseCard;