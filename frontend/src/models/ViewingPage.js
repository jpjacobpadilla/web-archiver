export class ViewingPage {
  constructor({ url, originalUrl, timestamp, host, jobId, currentJobIndex }) {
    this.url = url;
    this.originalUrl = originalUrl;
    this.timestamp = timestamp;
    this.host = host;
    this.jobId = jobId;
    this.currentJobIndex = currentJobIndex;
  }

  static fromPageAndJob(page, job, jobs, archiveService, host) {
    const encodedUrl = encodeURIComponent(page.link);
    const url = archiveService.getArchivedPageUrl(job.id, encodedUrl);

    return new ViewingPage({
      url,
      originalUrl: page.link,
      timestamp: job.time_started,
      host,
      jobId: job.id,
      currentJobIndex: jobs.findIndex(j => j.id === job.id),
    });
  }

  updateForJob(job, archiveService) {
    const encodedUrl = encodeURIComponent(this.originalUrl);
    const url = archiveService.getArchivedPageUrl(job.id, encodedUrl);

    return new ViewingPage({
      url,
      originalUrl: this.originalUrl,
      timestamp: job.time_started,
      host: this.host,
      jobId: job.id,
      currentJobIndex: this.currentJobIndex,
    });
  }

  canGoBack(totalJobs) {
    return this.currentJobIndex < totalJobs - 1;
  }

  canGoForward() {
    return this.currentJobIndex > 0;
  }

  goBack(jobs, archiveService) {
    if (!this.canGoBack(jobs.length)) return this;

    const olderJob = jobs[this.currentJobIndex + 1];
    const encodedUrl = encodeURIComponent(this.originalUrl);
    const url = archiveService.getArchivedPageUrl(olderJob.id, encodedUrl);

    return new ViewingPage({
      ...this,
      url,
      timestamp: olderJob.time_started,
      jobId: olderJob.id,
      currentJobIndex: this.currentJobIndex + 1,
    });
  }

  goForward(jobs, archiveService) {
    if (!this.canGoForward()) return this;

    const newerJob = jobs[this.currentJobIndex - 1];
    const encodedUrl = encodeURIComponent(this.originalUrl);
    const url = archiveService.getArchivedPageUrl(newerJob.id, encodedUrl);

    return new ViewingPage({
      ...this,
      url,
      timestamp: newerJob.time_started,
      jobId: newerJob.id,
      currentJobIndex: this.currentJobIndex - 1,
    });
  }
}