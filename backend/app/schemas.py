from datetime import datetime

from pydantic import BaseModel


# Data models
class ArchiveRequest(BaseModel):
    url: str
    max_pages: int | None = 25
    num_workers: int | None = 8


class ArchivedSite(BaseModel):
    host: str
    latest_job_time: datetime
    page_count: int
    job_count: int


class ArchiveJob(BaseModel):
    id: int
    time_started: datetime
    page_count: int


class ArchivedPage(BaseModel):
    id: int
    link: str
    host: str
    status_code: int | None
    content_type: str | None
    content_length: int | None
