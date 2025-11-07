import React, { useState } from 'react';
import './App.css';

function App() {
  { id: 'find_jobs_and_news', label: 'Searching for Jobs & News' },
  { id: 'generate_final_report', label: 'Generating Final Report' }
];

function App() {
  const [companyInput, setCompanyInput] = useState('');
  const [urlInput, setUrlInput] = useState('');

  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null); // 'pending', 'running', 'complete', 'error'
  const [completedSteps, setCompletedSteps] = useState([]);
  const [reportData, setReportData] = useState(null);
  const [error, setError] = useState(null);

  // On load, check localStorage for a running job
  useEffect(() => {
    const storedJobId = localStorage.getItem('research_job_id');
    if (storedJobId) {
      setJobId(storedJobId);
    }
  }, []);

  // Main listener effect: When jobId changes, subscribe to Firestore
  useEffect(() => {
    if (!jobId) {
      // Clear old report if we start a new job
      setReportData(null);
      setCompletedSteps([]);
      setJobStatus(null);
      return;
    }

    // Save to localStorage to survive refresh
    localStorage.setItem('research_job_id', jobId);

    // Subscribe to real-time updates for this job
    const unsub = onSnapshot(doc(db, "research_jobs", jobId), (doc) => {
      if (doc.exists()) {
        const data = doc.data();
        setJobStatus(data.status);
        setCompletedSteps(data.steps_complete || []);

        if (data.status === 'complete') {
          setReportData(data.final_report);
          localStorage.removeItem('research_job_id'); // Clear job on complete
          setJobId(null);
        } else if (data.status === 'error') {
          setError(data.error);
          localStorage.removeItem('research_job_id');
          setJobId(null);
        }
      } else {
        setError("Job not found.");
        localStorage.removeItem('research_job_id');
        setJobId(null);
      }
    });

    // Cleanup subscription on unmount or when jobId changes
    return () => unsub();

  }, [jobId]);

  const handleSubmit = async (e) => {
    e.preventDefault();

    // Clear previous run
    setReportData(null);
    setError(null);
    setCompletedSteps([]);
    setJobStatus('pending'); // Show loading state immediately

    try {
      // Use the new /start-research endpoint
      const response = await fetch('https://company-researcher-373126702591.us-central1.run.app/start-research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          input: companyInput,
          url: urlInput || null
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to start research job');
      }

      const data = await response.json();
      setJobId(data.job_id); // This will trigger the useEffect listener

    } catch (error) {
      console.error('Failed to start report:', error);
      setError(error.message);
      setJobStatus(null);
    }
  };

  const isLoading = jobStatus === 'pending' || jobStatus === 'running';

  return (
      <div className="App">
        <h1>Company Profile Builder</h1>

        <form onSubmit={handleSubmit} className="search-form">
          <div className="input-group">
            <input
                type="text"
                value={companyInput}
                onChange={(e) => setCompanyInput(e.target.value)}
                placeholder="Company name (required)"
                className="search-input"
                required
                disabled={isLoading}
            />
            <input
                type="text"
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                placeholder="Website or LinkedIn URL (optional)"
                className="search-input"
                disabled={isLoading}
            />
          </div>
          <button type="submit" disabled={isLoading} className="search-button">
            {isLoading ? 'Researching...' : 'Research'}
          </button>
        </form>

        {/* --- Real-time Step Tracker --- */}
        {isLoading && (
            <div className="steps-container">
              <h3>Working on it...</h3>
              {ALL_STEPS.map(step => {
                const isComplete = completedSteps.includes(step.id);
                const isCurrent = !isComplete && completedSteps.length > 0 && completedSteps[completedSteps.length - 1] === ALL_STEPS[ALL_STEPS.indexOf(step) - 1]?.id;

                let statusClass = '';
                if (isComplete) statusClass = 'step-complete';
                if (isCurrent) statusClass = 'step-current';

                return (
                    <div key={step.id} className={`step-item ${statusClass}`}>
                      <span className="step-icon">{isComplete ? '✅' : '...'}</span>
                      {step.label}
                    </div>
                );
              })}
            </div>
        )}

        {error && <div className="error">Error: {error}</div>}

        {/* --- Final Report (Same as before) --- */}
        {reportData && (
            <div className="report">
              <h2>{reportData.company_name}</h2>
              {/* ... (all your existing report sections) ... */}
              <div className="report-section">
                <h3>Basic Info</h3>
                <p><strong>Website:</strong> <a href={reportData.website} target="_blank" rel="noopener noreferrer">{reportData.website}</a></p>
                <p><strong>LinkedIn:</strong> <a href={reportData.linkedin_url} target="_blank" rel="noopener noreferrer">{reportData.linkedin_url}</a></p>
                <p><strong>Industry:</strong> {reportData.industry}</p>
                <p><strong>Size:</strong> {reportData.company_size_bracket} ({reportData.employee_count} employees)</p>
                <p><strong>Founded:</strong> {reportData.founded_year}</p>
                <p><strong>Headquarters:</strong> {reportData.headquarters}</p>
                <p><strong>Followers:</strong> {reportData.followers?.toLocaleString()}</p>
              </div>
              {/* ... etc ... */}
            </div>
        )}
      </div>
  );
}

export default App;