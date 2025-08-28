import React, { useState, useEffect } from 'react';
import './App.css';

const API_BASE = 'http://localhost:8000';

function App() {
  const [archivedSites, setArchivedSites] = useState([]);
  const [selectedSite, setSelectedSite] = useState(null);
  const [archiveJobs, setArchiveJobs] = useState([]);
  const [sitePages, setSitePages] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [newUrl, setNewUrl] = useState('');
  const [isArchiving, setIsArchiving] = useState(false);
  const [viewingPage, setViewingPage] = useState(null);

  // NEW: max pages slider state
  const [maxPages, setMaxPages] = useState(25);

  useEffect(() => {
    fetchArchivedSites();
  }, []);

  const fetchArchivedSites = async () => {
    try {
      const response = await fetch(`${API_BASE}/archived-sites`);
      const data = await response.json();
      setArchivedSites(data);
    } catch (error) {
      console.error('Error fetching archived sites:', error);
    }
  };

  const fetchSiteJobs = async (host) => {
    try {
      const response = await fetch(`${API_BASE}/archived-sites/${host}/jobs`);
      const data = await response.json();
      setArchiveJobs(data);
      if (data.length > 0) {
        setSelectedJob(data[0]);
        fetchJobPages(host, data[0].id);
      }
    } catch (error) {
      console.error('Error fetching site jobs:', error);
    }
  };

  const fetchJobPages = async (host, jobId) => {
    try {
      const response = await fetch(`${API_BASE}/archived-sites/${host}/jobs/${jobId}/pages`);
      const data = await response.json();
      setSitePages(data);
    } catch (error) {
      console.error('Error fetching job pages:', error);
    }
  };

  const handleSiteSelect = (site) => {
    setSelectedSite(site);
    setSelectedJob(null);
    setSitePages([]);
    fetchSiteJobs(site.host);
  };

  const handleJobChange = (job) => {
    setSelectedJob(job);
    if (selectedSite) {
      fetchJobPages(selectedSite.host, job.id);
    }
  };

  const handleArchiveSubmit = async (e) => {
    e.preventDefault();
    if (!newUrl.trim()) return;

    setIsArchiving(true);
    try {
      const response = await fetch(`${API_BASE}/archive`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: newUrl.trim(),
          max_pages: maxPages,        // use slider value
          num_workers: 12,
        }),
      });

      if (response.ok) {
        alert('Archive started!');
        setNewUrl('');
        setTimeout(fetchArchivedSites, 5000);
      } else {
        alert('Failed to start archive');
      }
    } catch (error) {
      console.error('Error starting archive:', error);
      alert('Error starting archive');
    } finally {
      setIsArchiving(false);
    }
  };

  const handleReArchive = async () => {
    if (!selectedSite) return;

    setIsArchiving(true);
    try {
      const response = await fetch(`${API_BASE}/archive`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: `https://${selectedSite.host}`,
          max_pages: maxPages,        // use slider value
          num_workers: 12,
        }),
      });

      if (response.ok) {
        const result = await response.json();
        alert(`Re-archive started! Job ID: ${result.job_id ?? 'N/A'}`);
        setTimeout(() => fetchSiteJobs(selectedSite.host), 5000);
      } else {
        alert('Failed to start re-archive');
      }
    } catch (error) {
      console.error('Error starting re-archive:', error);
      alert('Error starting re-archive');
    } finally {
      setIsArchiving(false);
    }
  };

  const openArchivedPage = (page) => {
    const encodedUrl = encodeURIComponent(page.link);
    const url = `${API_BASE}/web/${selectedJob.id}/${encodedUrl}`;

    setViewingPage({
      url,
      originalUrl: page.link,
      timestamp: selectedJob.time_started,
      host: selectedSite.host,
      jobId: selectedJob.id,
      currentJobIndex: archiveJobs.findIndex(job => job.id === selectedJob.id),
    });
  };

  const goBackInTime = () => {
    if (!viewingPage || viewingPage.currentJobIndex >= archiveJobs.length - 1) return;
    const olderJob = archiveJobs[viewingPage.currentJobIndex + 1];
    const encodedUrl = encodeURIComponent(viewingPage.originalUrl);
    const url = `${API_BASE}/web/${olderJob.id}/${encodedUrl}`;
    setViewingPage(v => ({
      ...v,
      url,
      timestamp: olderJob.time_started,
      jobId: olderJob.id,
      currentJobIndex: v.currentJobIndex + 1,
    }));
  };

  const goForwardInTime = () => {
    if (!viewingPage || viewingPage.currentJobIndex <= 0) return;
    const newerJob = archiveJobs[viewingPage.currentJobIndex - 1];
    const encodedUrl = encodeURIComponent(viewingPage.originalUrl);
    const url = `${API_BASE}/web/${newerJob.id}/${encodedUrl}`;
    setViewingPage(v => ({
      ...v,
      url,
      timestamp: newerJob.time_started,
      jobId: newerJob.id,
      currentJobIndex: v.currentJobIndex - 1,
    }));
  };

  const closeArchivedPage = () => setViewingPage(null);

  const formatDate = (dateString) => new Date(dateString).toLocaleString();

  const getStatusColor = (statusCode) => {
    if (!statusCode) return '';
    if (statusCode >= 200 && statusCode < 300) return 'status-success';
    if (statusCode >= 300 && statusCode < 400) return 'status-redirect';
    if (statusCode >= 400) return 'status-error';
    return '';
  };

  return (
    <div className="app">
      <header>
        <h1>Jacob's Web Archiver</h1>
        <p>Your personal Wayback button for the internet.</p>

        {viewingPage && (
          <div className="archive-banner">
            <div className="banner-content">
              <button onClick={closeArchivedPage} className="nav-btn home-btn">
                Back to Archive List
              </button>

              <div className="time-controls">
                <button
                  onClick={goBackInTime}
                  className="nav-btn"
                  disabled={viewingPage.currentJobIndex >= archiveJobs.length - 1}
                >
                  ← Older
                </button>

                <div className="archive-info">
                  <span className="url-info">{viewingPage.originalUrl}</span>
                  <span className="date-info">
                    Job #{viewingPage.jobId} - {new Date(viewingPage.timestamp).toLocaleString()}
                  </span>
                </div>

                <button
                  onClick={goForwardInTime}
                  className="nav-btn"
                  disabled={viewingPage.currentJobIndex <= 0}
                >
                  Newer →
                </button>
              </div>
            </div>
          </div>
        )}
      </header>

      {viewingPage ? (
        <div className="iframe-container">
          <iframe
            src={viewingPage.url}
            className="archived-page-frame"
            title={`Archived: ${viewingPage.originalUrl}`}
          />
        </div>
      ) : (
        <main>
          <section className="archive-section">
            <h2>Archive a New URL</h2>
            <form onSubmit={handleArchiveSubmit} className="archive-form">
              <input
                type="url"
                value={newUrl}
                onChange={(e) => setNewUrl(e.target.value)}
                placeholder="Enter URL to archive (e.g., https://example.com)"
                required
                disabled={isArchiving}
              />

              {/* NEW: How many pages slider */}
              <div className="range-wrap">
                <label htmlFor="max-pages" className="range-label">
                  How many pages: <span className="range-value">{maxPages}</span>
                </label>
                <input
                  id="max-pages"
                  type="range"
                  min={10}
                  max={1000}
                  step={10}
                  value={maxPages}
                  onChange={(e) => setMaxPages(parseInt(e.target.value, 10))}
                  disabled={isArchiving}
                />
              </div>

              <button className="standard-button-main" type="submit" disabled={isArchiving}>
                {isArchiving ? 'Archiving...' : 'Archive Site'}
              </button>
            </form>
          </section>

          <div className="content">
            <aside className="sites-sidebar">
              <h2>Archived Sites</h2>
              {archivedSites.length === 0 ? (
                <p>No archived sites yet. Archive your first site above!</p>
              ) : (
                <ul className="sites-list">
                  {archivedSites.map((site) => (
                    <li
                      key={site.host}
                      className={selectedSite?.host === site.host ? 'selected' : ''}
                      onClick={() => handleSiteSelect(site)}
                    >
                      <div className="site-info">
                        <strong>{site.host}</strong>
                        <div className="site-meta">
                          <small>{site.page_count} pages</small>
                          <small>{site.job_count} archive{site.job_count !== 1 ? 's' : ''}</small>
                          <small>{formatDate(site.latest_job_time)}</small>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </aside>

            <section className="site-details">
              {selectedSite ? (
                <>
                  <div className="site-header">
                    <h2>{selectedSite.host}</h2>
                    <button
                      onClick={handleReArchive}
                      disabled={isArchiving}
                      className="standard-button-main"
                    >
                      {isArchiving ? 'Archiving...' : 'Re-Archive'}
                    </button>
                  </div>

                  <div className="job-selector">
                    <h3>Select Archive Version:</h3>
                    <select
                      value={selectedJob?.id || ''}
                      onChange={(e) => {
                        const job = archiveJobs.find(j => j.id === parseInt(e.target.value));
                        if (job) handleJobChange(job);
                      }}
                    >
                      {archiveJobs.map((job) => (
                        <option key={job.id} value={job.id}>
                          Job #{job.id} - {formatDate(job.time_started)} ({job.page_count} pages)
                        </option>
                      ))}
                    </select>
                  </div>

                  {sitePages.length > 0 && (
                    <div className="pages-section">
                      <h3>Archived Pages ({sitePages.length})</h3>
                      <ul className="pages-list">
                        {sitePages.map((page) => (
                          <li key={page.id} className="page-item">
                            <div className="page-info">
                              <button
                                onClick={() => openArchivedPage(page)}
                                className="page-link"
                              >
                                {page.link}
                              </button>
                              <div className="page-meta">
                                {page.content_length && (
                                  <span className="content-length">
                                    {(page.content_length / 1024).toFixed(1)}KB
                                  </span>
                                )}
                              </div>
                            </div>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </>
              ) : (
                <div className="no-selection">
                  <h2>Select a site to view archived versions</h2>
                  <p>Click on a site from the left sidebar to see its archived pages and versions.</p>
                </div>
              )}
            </section>
          </div>
        </main>
      )}
    </div>
  );
}

export default App;
