select
    id,
    link,
    host,
    status_code,
    content_type,
    content_length
from archived_resource
where host = %(host)s
    and scraping_job = %(job_id)s
    and content_type = 'text/html; charset=utf-8'
order by link;
