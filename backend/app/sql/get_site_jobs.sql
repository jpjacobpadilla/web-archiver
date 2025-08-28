select
    aj.id,
    aj.time_started,
    count(ar.id) as page_count
from archive_jobs aj
join archived_resource ar on aj.id = ar.scraping_job
where ar.host = %(host)s ar.content_type= 'text/html;'
group by aj.id, aj.time_started
order by aj.time_started desc;
