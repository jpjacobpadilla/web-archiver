insert into archived_resource (
    link,
    host,
    status_code,
    content_type,
    content,
    content_length,
    scraping_job
)
values (
    %(link)s,
    %(host)s,
    %(status_code)s,
    %(content_type)s,
    %(content)s,
    %(content_length)s,
    %(scraping_job)s
)
returning id;
