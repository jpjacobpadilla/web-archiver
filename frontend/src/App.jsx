import React from 'react';
import { useArchiveData } from './hooks/useArchiveData';
import { archiveService } from './services/ArchiveService';
import { ViewingPage } from './models/ViewingPage';
import HeaderComponent from './components/Header/Header.jsx';
import ArchiveFormComponent from './components/ArchiveForm/ArchiveForm.jsx';
import SitesSidebarComponent from './components/SitesSidebar/SitesSidebar.jsx';
import SiteDetailsComponent from './components/SiteDetails/SiteDetails.jsx';
import './App.css';

class UrlManager {
  static updateUrl(host, jobId, pageUrl) {
    const params = new URLSearchParams();
    if (host) params.set('host', host);
    if (jobId) params.set('job', jobId);
    if (pageUrl) params.set('page', pageUrl);

    const newUrl = params.toString() ? `?${params.toString()}` : '/';
    window.history.pushState({}, '', newUrl);
  }

  static getUrlParams() {
    const params = new URLSearchParams(window.location.search);
    return {
      host: params.get('host'),
      jobId: params.get('job'),
      pageUrl: params.get('page')
    };
  }
}

function App() {
  const {
    archivedSites,
    selectedSite,
    setSelectedSite,
    archiveJobs,
    selectedJob,
    setSelectedJob,
    sitePages,
    isArchiving,
    fetchSiteJobs,
    fetchJobPages,
    startArchive
  } = useArchiveData();

  const [viewingPage, setViewingPage] = React.useState(null);

  // URL routing effect
  React.useEffect(() => {
    const { host, jobId, pageUrl } = UrlManager.getUrlParams();

    if (host && archivedSites.length > 0) {
      const site = archivedSites.find(s => s.host === host);
      if (site && (!selectedSite || selectedSite.host !== host)) {
        handleSiteSelect(site, jobId, pageUrl);
      } else if (site && selectedSite && selectedSite.host === host && pageUrl && !viewingPage) {
        // Handle direct URL access to a page when site is already selected
        const job = jobId ? archiveJobs.find(j => j.id === parseInt(jobId)) : selectedJob;
        if (job && sitePages.length > 0) {
          const page = { link: decodeURIComponent(pageUrl) };
          openArchivedPage(page, job, archiveJobs);
        }
      }
    }
  }, [archivedSites, selectedSite, archiveJobs, selectedJob, sitePages, viewingPage]);

  const handleSiteSelect = async (site, targetJobId = null, targetPageUrl = null) => {
    setSelectedSite(site);
    setSelectedJob(null);

    const jobs = await fetchSiteJobs(site.host);
    if (jobs.length > 0) {
      const job = targetJobId ? jobs.find(j => j.id === parseInt(targetJobId)) : jobs[0];
      if (job) {
        setSelectedJob(job);
        await fetchJobPages(site.host, job.id);

        if (targetPageUrl) {
          const page = { link: decodeURIComponent(targetPageUrl) };
          openArchivedPage(page, job, jobs);
          return; // Don't update URL again
        }
      }
    }

    UrlManager.updateUrl(site.host, targetJobId || (jobs[0] && jobs[0].id), null);
  };

  const handleJobChange = (job) => {
    setSelectedJob(job);
    fetchJobPages(selectedSite.host, job.id);

    // If we're currently viewing a page, update the viewing page to the new job
    if (viewingPage) {
      const updatedViewingPage = viewingPage.updateForJob(job, archiveJobs, archiveService);
      console.log('Job changed - new index:', updatedViewingPage.currentJobIndex, 'total jobs:', archiveJobs.length);
      setViewingPage(updatedViewingPage);
      UrlManager.updateUrl(selectedSite.host, job.id, encodeURIComponent(viewingPage.originalUrl));
    } else {
      UrlManager.updateUrl(selectedSite.host, job.id, null);
    }
  };

  const handleReArchive = async () => {
    if (!selectedSite) return;
    const result = await startArchive(`https://${selectedSite.host}`, 25);
    if (result.success) {
      alert('Re-archive started!');
      setTimeout(() => fetchSiteJobs(selectedSite.host), 5000);
    } else {
      alert('Failed to start re-archive');
    }
  };

  const openArchivedPage = (page, job = selectedJob, jobs = archiveJobs) => {
    const pageData = ViewingPage.fromPageAndJob(page, job, jobs, archiveService, selectedSite.host);
    setViewingPage(pageData);
    UrlManager.updateUrl(selectedSite.host, job.id, encodeURIComponent(page.link));
  };

  const goBackInTime = () => {
    if (!viewingPage || !viewingPage.canGoBack(archiveJobs.length)) return;

    const newPageData = viewingPage.goBack(archiveJobs, archiveService);
    setViewingPage(newPageData);
    UrlManager.updateUrl(selectedSite.host, newPageData.jobId, encodeURIComponent(viewingPage.originalUrl));
  };

  const goForwardInTime = () => {
    if (!viewingPage || !viewingPage.canGoForward()) return;

    const newPageData = viewingPage.goForward(archiveJobs, archiveService);
    setViewingPage(newPageData);
    UrlManager.updateUrl(selectedSite.host, newPageData.jobId, encodeURIComponent(viewingPage.originalUrl));
  };

  const closeArchivedPage = () => {
    setViewingPage(null);
    UrlManager.updateUrl(selectedSite.host, selectedJob?.id, null);
  };

  return (
    <div className="app">
      <HeaderComponent
        viewingPage={viewingPage}
        onCloseArchivedPage={closeArchivedPage}
        onGoBack={goBackInTime}
        onGoForward={goForwardInTime}
        archiveJobs={archiveJobs}
      />

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
          <ArchiveFormComponent
            onArchiveSubmit={startArchive}
            isArchiving={isArchiving}
          />

          <div className="content">
            <SitesSidebarComponent
              archivedSites={archivedSites}
              selectedSite={selectedSite}
              onSiteSelect={handleSiteSelect}
            />

            <SiteDetailsComponent
              selectedSite={selectedSite}
              archiveJobs={archiveJobs}
              selectedJob={selectedJob}
              sitePages={sitePages}
              isArchiving={isArchiving}
              onJobChange={handleJobChange}
              onReArchive={handleReArchive}
              onOpenPage={openArchivedPage}
            />
          </div>
        </main>
      )}
    </div>
  );
}

export default App;