import { useState, useEffect } from 'react';
import { archiveService } from '../services/ArchiveService';

export class ArchiveDataManager {
  constructor() {
    this.archivedSites = [];
    this.selectedSite = null;
    this.archiveJobs = [];
    this.selectedJob = null;
    this.sitePages = [];
    this.isArchiving = false;
  }

  async fetchArchivedSites() {
    try {
      const data = await archiveService.fetchArchivedSites();
      this.archivedSites = data;
      return data;
    } catch (error) {
      console.error('Error fetching archived sites:', error);
      return [];
    }
  }

  async fetchSiteJobs(host) {
    try {
      const data = await archiveService.fetchSiteJobs(host);
      this.archiveJobs = data;
      return data;
    } catch (error) {
      console.error('Error fetching site jobs:', error);
      return [];
    }
  }

  async fetchJobPages(host, jobId) {
    try {
      const data = await archiveService.fetchJobPages(host, jobId);
      this.sitePages = data;
      return data;
    } catch (error) {
      console.error('Error fetching job pages:', error);
      return [];
    }
  }

  async startArchive(url, maxPages) {
    this.isArchiving = true;
    try {
      const response = await archiveService.startArchive(url, maxPages);
      if (response.ok) {
        setTimeout(() => this.fetchArchivedSites(), 5000);
        return { success: true };
      } else {
        return { success: false };
      }
    } catch (error) {
      console.error('Error starting archive:', error);
      return { success: false };
    } finally {
      this.isArchiving = false;
    }
  }
}

export const useArchiveData = () => {
  const [manager] = useState(() => new ArchiveDataManager());
  const [archivedSites, setArchivedSites] = useState([]);
  const [selectedSite, setSelectedSite] = useState(null);
  const [archiveJobs, setArchiveJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [sitePages, setSitePages] = useState([]);
  const [isArchiving, setIsArchiving] = useState(false);

  useEffect(() => {
    fetchArchivedSites();
  }, []);

  const fetchArchivedSites = async () => {
    const data = await manager.fetchArchivedSites();
    setArchivedSites(data);
  };

  const fetchSiteJobs = async (host) => {
    const data = await manager.fetchSiteJobs(host);
    setArchiveJobs(data);
    return data;
  };

  const fetchJobPages = async (host, jobId) => {
    const data = await manager.fetchJobPages(host, jobId);
    setSitePages(data);
    return data;
  };

  const startArchive = async (url, maxPages) => {
    setIsArchiving(true);
    const result = await manager.startArchive(url, maxPages);
    setIsArchiving(false);
    return result;
  };

  return {
    archivedSites,
    selectedSite,
    setSelectedSite,
    archiveJobs,
    selectedJob,
    setSelectedJob,
    sitePages,
    isArchiving,
    fetchArchivedSites,
    fetchSiteJobs,
    fetchJobPages,
    startArchive
  };
};