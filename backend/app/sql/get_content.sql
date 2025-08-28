select content, content_type, host
from archived_resource
where scraping_job = %(job_id)s and link = %(link)s
limit 1;