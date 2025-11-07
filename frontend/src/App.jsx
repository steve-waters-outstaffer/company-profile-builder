import React, { useState } from 'react';
import './App.css';

function App() {
  const [companyInput, setCompanyInput] = useState('');
  const [urlInput, setUrlInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [reportData, setReportData] = useState(null);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setReportData(null);
    setError(null);

    try {
      const response = await fetch('http://127.0.0.1:5000/research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // Send both fields - backend will use whichever are provided
        body: JSON.stringify({ 
          input: companyInput,
          url: urlInput || null
        }), 
      });

      if (!response.ok) {
        throw new Error('Network response was not ok');
      }

      const data = await response.json();
      setReportData(data);

    } catch (error) {
      console.error('Failed to fetch report:', error);
      setError(error.message);
    } finally {
      setLoading(false);
    }
  };

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
          />
          <input 
            type="text" 
            value={urlInput}
            onChange={(e) => setUrlInput(e.target.value)}
            placeholder="Website or LinkedIn URL (optional - improves accuracy)"
            className="search-input"
          />
        </div>
        <button type="submit" disabled={loading} className="search-button">
          {loading ? 'Researching...' : 'Research'}
        </button>
      </form>

      {loading && <div className="loading">Loading report...</div>}
      
      {error && <div className="error">Error: {error}</div>}

      {reportData && (
        <div className="report">
          <h2>{reportData.company_name}</h2>
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

          <div className="report-section">
            <h3>Description</h3>
            <p>{reportData.description}</p>
          </div>

          {reportData.specialties && reportData.specialties.length > 0 && (
            <div className="report-section">
              <h3>Specialties</h3>
              <div className="tags">
                {reportData.specialties.map((spec, idx) => (
                  <span key={idx} className="tag">{spec}</span>
                ))}
              </div>
            </div>
          )}

          {reportData.competitors && reportData.competitors.length > 0 && (
            <div className="report-section">
              <h3>Competitors</h3>
              <ul>
                {reportData.competitors.map((comp, idx) => (
                  <li key={idx}>{comp}</li>
                ))}
              </ul>
            </div>
          )}

          {reportData.job_openings && reportData.job_openings.length > 0 && (
            <div className="report-section">
              <h3>Job Openings</h3>
              <ul>
                {reportData.job_openings.map((job, idx) => (
                  <li key={idx}>
                    <strong>{job.title}</strong> - {job.location}
                    {job.link && <a href={job.link} target="_blank" rel="noopener noreferrer"> [View]</a>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {reportData.key_personnel && reportData.key_personnel.length > 0 && (
            <div className="report-section">
              <h3>Key Personnel</h3>
              <ul>
                {reportData.key_personnel.map((person, idx) => (
                  <li key={idx}>
                    <a href={person.link} target="_blank" rel="noopener noreferrer">
                      {person.name}
                    </a> - {person.title}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {reportData.funding && (
            <div className="report-section">
              <h3>Latest Funding</h3>
              <p><strong>Type:</strong> {reportData.funding.type}</p>
              <p><strong>Date:</strong> {reportData.funding.date}</p>
              <p><strong>Amount:</strong> {reportData.funding.amount}</p>
            </div>
          )}

          {reportData.recent_news_summary && (
            <div className="report-section">
              <h3>Recent News</h3>
              <p>{reportData.recent_news_summary}</p>
            </div>
          )}
          
          <details className="report-section">
            <summary><h3>Raw JSON (Debug)</h3></summary>
            <pre>{JSON.stringify(reportData, null, 2)}</pre>
          </details>
        </div>
      )}
    </div>
  );
}

export default App;
