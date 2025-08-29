import React from 'react';
import './Header.css';

class HeaderComponent extends React.Component {
  render() {
    const { viewingPage, onCloseArchivedPage, onGoBack, onGoForward, archiveJobs } = this.props;

    const canGoBack = viewingPage?.canGoBack(archiveJobs.length) || false;
    const canGoForward = viewingPage?.canGoForward() || false;

    return (
      <header>
        <h1>Jacob's Web Archiver</h1>
        <p>Your personal Wayback button for the internet.</p>

        {viewingPage && (
          <div className="archive-banner">
            <div className="banner-content">
              <button onClick={onCloseArchivedPage} className="nav-btn">
                Back to Archive List
              </button>

              <div className="time-controls">
                <button
                  onClick={onGoBack}
                  className="nav-btn"
                  disabled={!canGoBack}
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
                  onClick={onGoForward}
                  className="nav-btn"
                  disabled={!canGoForward}
                >
                  Newer →
                </button>
              </div>
            </div>
          </div>
        )}
      </header>
    );
  }
}

export default HeaderComponent;