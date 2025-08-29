import React from 'react';
import './SiteDetails.css';
import { archiveService } from '../../services/ArchiveService';

class SiteDetailsComponent extends React.Component {
  handleJobChange = (e) => {
    const { archiveJobs, onJobChange } = this.props;
    const job = archiveJobs.find(j => j.id === parseInt(e.target.value));
    if (job) onJobChange(job);
  };

  renderJobOption = (job) => (
    <option key={job.id} value={job.id}>
      Job #{job.id} - {archiveService.formatDate(job.time_started)} ({job.page_count} pages)
    </option>
  );

  renderPageItem = (page) => {
    const { onOpenPage } = this.props;

    return (
      <li key={page.id} className="page-item">
        <div className="page-info">
          <button
            onClick={() => onOpenPage(page)}
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
    );
  };

  renderNoSelection() {
    return (
      <div className="no-selection">
        <h2>Select a site to view archived versions</h2>
        <p>Click on a site from the left sidebar to see its archived pages and versions.</p>
      </div>
    );
  }

  renderSiteContent() {
    const {
      selectedSite,
      archiveJobs,
      selectedJob,
      sitePages,
      isArchiving,
      onReArchive
    } = this.props;

    return (
      <>
        <div className="site-header">
          <h2>{selectedSite.host}</h2>
          <button
            onClick={onReArchive}
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
            onChange={this.handleJobChange}
          >
            {archiveJobs.map(this.renderJobOption)}
          </select>
        </div>

        {sitePages.length > 0 && (
          <div className="pages-section">
            <h3>Archived Pages ({sitePages.length})</h3>
            <ul className="pages-list">
              {sitePages.map(this.renderPageItem)}
            </ul>
          </div>
        )}
      </>
    );
  }

  render() {
    const { selectedSite } = this.props;

    return (
      <section className="site-details">
        {selectedSite ? this.renderSiteContent() : this.renderNoSelection()}
      </section>
    );
  }
}

export default SiteDetailsComponent;