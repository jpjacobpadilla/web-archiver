class ArchiveService {
  constructor() {
    this.API_BASE = 'http://localhost:8000/api';
  }

  async fetchArchivedSites() {
    const response = await fetch(`${this.API_BASE}/archived-sites`);
    return response.json();
  }

  async fetchSiteJobs(host) {
    const response = await fetch(`${this.API_BASE}/archived-sites/${host}/jobs`);
    return response.json();
  }

  async fetchJobPages(host, jobId) {
    const response = await fetch(`${this.API_BASE}/archived-sites/${host}/jobs/${jobId}/pages`);
    return response.json();
  }

  async startArchive(url, maxPages) {
    const response = await fetch(`${this.API_BASE}/archive`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: url.trim(),
        max_pages: maxPages,
        num_workers: 12,
      }),
    });
    return response;
  }

  getArchivedPageUrl(jobId, encodedUrl) {
    return `${this.API_BASE}/web/${jobId}/${encodedUrl}`;
  }

  formatDate(dateString) {
    return new Date(dateString).toLocaleString();
  }
}

// Export singleton instance
export const archiveService = new ArchiveService();