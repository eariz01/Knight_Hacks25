import React, { useState, useEffect } from 'react';
import './index.css';
// Make sure to delete or comment out any import for 'App.css'
import LitigationColumn from './components/LitigationColumn';
import './components/LitigationColumn.css';

function App() {
  const [cases, setCases] = useState([]);
  // Sets the column order
  const litigationPhases = ["Discovery", "Settlement Discussion", "Pre-Trial", "Trial"];

  useEffect(() => {
    // This fetches the data from the public folder
    fetch('/sampleData.json')
      .then(response => response.json())
      .then(data => setCases(data))
      .catch(error => console.error("Error fetching case data:", error));
  }, []);

  // This function allows child components (CaseCard) to update the main state
  const handleUpdateStatus = (caseId, newStatus) => {
    setCases(currentCases =>
      currentCases.map(c =>
        c.id === caseId ? { ...c, status: newStatus } : c
      )
    );
  };

  return (
    <div className="App">
      {/* Integrated title, no separate header bar */}
      <h1 className="app-title">Litigation Phase Tracker</h1>
      
      <main className="dashboard-container">
        {litigationPhases.map(phase => {
          // Filter cases that belong in this column
          const casesForPhase = cases.filter(c => c.litigation_phase === phase);
          
          return (
            <LitigationColumn
              key={phase}
              title={phase}
              cases={casesForPhase}
              onUpdateStatus={handleUpdateStatus}
            />
          );
        })}
      </main>
    </div>
  );
}

export default App;