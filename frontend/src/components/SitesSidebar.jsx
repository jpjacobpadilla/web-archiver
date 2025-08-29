import React from 'react';
import { archiveService } from '../services/ArchiveService';

class SitesSidebarComponent extends React.Component {
  renderSiteItem = (site) => {
    const { selectedSite, onSiteSelect } = this.props;
    const isSelected = selectedSite?.host === site.host;

    return (
      <li
        key={site.host}
        className={isSelected ? 'selected' : ''}
        onClick={() => onSiteSelect(site)}
      >
        <div className="site-info">
          <strong>{site.host}</strong>
          <div className="site-meta">
            <small>{site.page_count} pages</small>
            <small>{site.job_count} archive{site.job_count !== 1 ? 's' : ''}</small>
            <small>{archiveService.formatDate(site.latest_job_time)}</small>
          </div>
        </div>
      </li>
    );
  };

  render() {
    const { archivedSites } = this.props;

    return (
      <aside className="sites-sidebar">
        <h2>Archived Sites</h2>
        {archivedSites.length === 0 ? (
          <p>No archived sites yet. Archive your first site above!</p>
        ) : (
          <ul className="sites-list">
            {archivedSites.map(this.renderSiteItem)}
          </ul>
        )}
      </aside>
    );
  }
}

export default SitesSidebarComponent;