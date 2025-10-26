import React, { useState, useEffect } from 'react';
//Global styles and gradient
import './index.css'; 

import LitigationColumn from './components/LitigationColumn';
import './components/LitigationColumn.css'; 

function App() {
  //State to hold the array of case data
  const [cases, setCases] = useState([]);
  
  //Define the order of the columns
  const litigationPhases = ["Discovery", "Settlement Discussion", "Pre-Trial", "Trial"];

  //useEffect hook runs once when the component first mounts
  useEffect(() => {
    //Fetch the data from master.json located in the 'public' folder
    fetch('/master.json') // Correct path for files in the public folder
      .then(response => {
        //Check if the request was successful
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        //Parse the JSON data from the response
        return response.json();
      })
      .then(data => {
        // Update the 'cases' state with the fetched data
        setCases(data);
      })
      .catch(error => {
        // Log any errors that occur during fetching or parsing
        console.error("Error fetching case data:", error);
        // Optionally, set state to show an error message to the user
      });
  }, []); // The empty dependency array [] means this effect runs only once

  // Function passed down to CaseCard to update a case's status
  const handleUpdateStatus = (caseId, newStatus) => {
    setCases(currentCases =>
      // Create a new array by mapping over the existing cases
      currentCases.map(c =>
        // If the current case's ID matches the one to update...
        c.id === caseId 
          // ...create a new object with the updated status
          ? { ...c, status: newStatus } 
          // ...otherwise, keep the case object as is
          : c 
      )
    );
  };

  // Render the main structure of the application
  return (
    <div className="App">
      {/* The main title, styled by index.css */}
      <h1 className="app-title">Litigation Phase Tracker</h1>
      
      {/* Container for the columns */}
      <main className="dashboard-container">
        {/* Map over the defined phases to create each column */}
        {litigationPhases.map(phase => {
          // Filter the cases array to get only cases matching the current phase
          const casesForPhase = cases.filter(c => c.litigation_phase === phase);
          
          // Render a LitigationColumn component for the current phase
          return (
            <LitigationColumn
              key={phase} // React needs a unique key for list items
              title={phase} // The title of the column
              cases={casesForPhase} // The filtered list of cases for this column
              onUpdateStatus={handleUpdateStatus} // Pass the update function down
            />
          );
        })}
      </main>
    </div>
  );
}

// Export the App component for use in index.js
export default App;
