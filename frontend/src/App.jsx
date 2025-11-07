import React, { useState, useEffect } from 'react';
import './App.css';
import { getFirestore, doc, onSnapshot } from 'firebase/firestore';
import { initializeApp } from 'firebase/app';

// Firebase config
const firebaseConfig = {
  apiKey: "AIzaSyBUGRFbmL3J0AazYufSdmY7D7L-b6Xyc_Y",
  authDomain: "gen-lang-client-0048564118.firebaseapp.com",
  projectId: "gen-lang-client-0048564118",
  storageBucket: "gen-lang-client-0048564118.firebasestorage.app",
  messagingSenderId: "373126702591",
  appId: "1:373126702591:web:44414268a376decdd933ca"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const db = getFirestore(app);

// The steps we expect from the backend agent_flow.py
const ALL_STEPS = [
  { id: 'start', label: 'Starting research...' },
  { id: 'find_linkedin_url', label: 'Finding LinkedIn Profile' },
  { id: 'scrape_linkedin', label: 'Scraping LinkedIn Data' },
  { id: 'find_jobs_and_news', label: 'Finding Careers Page & News' },
  { id: 'scrape_careers_page', label: 'Scraping Careers Page' },
  { id: 'generate_final_report', label: 'Generating Final Report' }
];

function App() {
  const [companyInput, setCompanyInput] = useState('');
  const [urlInput, setUrlInput] = useState('');
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [completedSteps, setCompletedSteps] = useState([]);
  const [reportData, setReportData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const storedJobId = localStorage.getItem('research_job_id');
    if (storedJobId) {
      setJobId(storedJobId);
    }
  }, []);

  useEffect(() => {
    if (!jobId) {
      setReportData(null);
      setCompletedSteps([]);
      setJobStatus(null);
      return;
    }

    localStorage.setItem('research_job_id', jobId);

    const unsub = onSnapshot(doc(db, "research_jobs", jobId), (docSnapshot) => {
      if (docSnapshot.exists()) {
        const data = docSnapshot.data();
        setJobStatus(data.status);
        setCompletedSteps(data.steps_complete || []);

        if (data.status === 'complete') {
          // Combine LinkedIn data with LLM-generated fields
          const combinedReport = {
            // All LinkedIn data
            ...data.linkedin_data,
            // LLM-generated fields
            job_openings: data.job_openings || [],
            recent_news_summary: data.recent_news_summary || ''
          };
          
          setReportData(combinedReport);
          localStorage.removeItem('research_job_id');
          // Keep jobId so report stays visible
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

    return () => unsub();
  }, [jobId]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setJobId(null); // Clear old job first
    setReportData(null);
    setError(null);
    setCompletedSteps([]);
    setJobStatus('pending');

    try {
      const response = await fetch('https://company-researcher-373126702591.us-central1.run.app/start-research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input: companyInput, url: urlInput || null }),
      });

      if (!response.ok) throw new Error('Failed to start research job');

      const data = await response.json();
      setJobId(data.job_id);
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

      {isLoading && (
        <div className="steps-container">
          <h3>Working on it...</h3>
          {ALL_STEPS.map((step, idx) => {
            const isComplete = completedSteps.includes(step.id);
            const isCurrent = !isComplete && idx === completedSteps.length;

            return (
              <div key={step.id} className={`step-item ${isComplete ? 'step-complete' : ''} ${isCurrent ? 'step-current' : ''}`}>
                <span className="step-icon">{isComplete ? '✅' : '...'}</span>
                {step.label}
              </div>
            );
          })}
        </div>
      )}

      {error && <div className="error">Error: {error}</div>}

      {reportData && (
        <div className="report">
          {reportData.logo && (
            <div className="company-header">
              <img src={reportData.logo} alt={`${reportData.name} logo`} className="company-logo" />
              <h2>{reportData.name}</h2>
            </div>
          )}
          {!reportData.logo && <h2>{reportData.name}</h2>}

          <div className="report-section">
            <h3>Basic Info</h3>
            <p><strong>Website:</strong> <a href={reportData.website} target="_blank" rel="noopener noreferrer">{reportData.website}</a></p>
            <p><strong>LinkedIn:</strong> <a href={reportData.url} target="_blank" rel="noopener noreferrer">{reportData.url}</a></p>
            <p><strong>Industry:</strong> {reportData.industry}</p>
            <p><strong>Size:</strong> {reportData.size} ({reportData.employeeCount} employees)</p>
            <p><strong>Founded:</strong> {reportData.founded}</p>
            <p><strong>Headquarters:</strong> {reportData.headquarters}</p>
            {reportData.type && <p><strong>Type:</strong> {reportData.type}</p>}
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

          {reportData.similarPages && reportData.similarPages.length > 0 && (
            <div className="report-section">
              <h3>Competitors</h3>
              <ul className="competitors-list">
                {reportData.similarPages.map((comp, idx) => (
                  <li key={idx}>
                    {comp.image && <img src={comp.image} alt={comp.name} className="competitor-logo" />}
                    <a href={comp.link} target="_blank" rel="noopener noreferrer">{comp.name}</a>
                  </li>
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

          {reportData.employees && reportData.employees.length > 0 && (
            <div className="report-section">
              <h3>Key Personnel</h3>
              <ul className="personnel-list">
                {reportData.employees.map((person, idx) => (
                  <li key={idx}>
                    {person.image && <img src={person.image} alt={person.name} className="person-avatar" />}
                    <div className="person-info">
                      <a href={person.link} target="_blank" rel="noopener noreferrer">{person.name}</a>
                      {person.title && <span> - {person.title}</span>}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {reportData.funding && reportData.funding.lastRound && reportData.funding.lastRound.type && (
            <div className="report-section">
              <h3>Latest Funding</h3>
              <p><strong>Type:</strong> {reportData.funding.lastRound.type}</p>
              {reportData.funding.lastRound.date && <p><strong>Date:</strong> {reportData.funding.lastRound.date}</p>}
              {reportData.funding.lastRound.amount && <p><strong>Amount:</strong> {reportData.funding.lastRound.amount}</p>}
            </div>
          )}

          {reportData.recent_news_summary && (
            <div className="report-section">
              <h3>Recent News</h3>
              <p>{reportData.recent_news_summary}</p>
            </div>
          )}

          {reportData.posts && reportData.posts.length > 0 && (
            <div className="report-section">
              <h3>Recent LinkedIn Posts</h3>
              <div className="posts-list">
                {reportData.posts.slice(0, 5).map((post, idx) => (
                  <div key={idx} className="post-item">
                    <p className="post-date">{new Date(post.datePublished).toLocaleDateString()}</p>
                    <p className="post-text">{post.text.substring(0, 200)}{post.text.length > 200 ? '...' : ''}</p>
                    <a href={post.url} target="_blank" rel="noopener noreferrer">Read more</a>
                  </div>
                ))}
              </div>
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
