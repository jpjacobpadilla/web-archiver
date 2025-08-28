select
    link
from archived_resource
where scraping_job = %(job_id)s
limit 10;
