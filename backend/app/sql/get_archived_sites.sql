select
    ar.host,
    max(aj.time_started) as latest_job_time,
    count(distinct ar.id) as page_count,
    count(distinct aj.id) as job_count
from archived_resource ar
join archive_jobs aj on ar.scraping_job = aj.id
where ar.content_type like 'text/html%'
   or ar.content_type = 'text/html'
group by ar.host
order by latest_job_time desc;
