import os
import re
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from urllib.parse import urlsplit, urlunsplit, quote, unquote

from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.schemas import ArchiveRequest, ArchivedSite, ArchiveJob, ArchivedPage
from archiver import BasicArchiver


SQL_DIR = Path(__file__).parent / 'sql'
SQL_GET_ARCHIVED_SITES = (SQL_DIR / 'get_archived_sites.sql').read_text(encoding='utf-8')
SQL_GET_SITE_JOBS = (SQL_DIR / 'get_site_jobs.sql').read_text(encoding='utf-8')
SQL_GET_JOB_PAGES = (SQL_DIR / 'get_job_pages.sql').read_text(encoding='utf-8')
SQL_DEBUG_QUERY = (SQL_DIR / 'debug_available_url.sql').read_text(encoding='utf-8')
SQL_FETCH_CONTENT = (SQL_DIR / 'get_content.sql').read_text(encoding='utf-8')


@asynccontextmanager
async def lifespan(app: FastAPI):
    await pool.open()

    try:
        yield
    finally:
        if pool:
            await pool.close()


app = FastAPI(title='Web Archiver API', lifespan=lifespan)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173'],  # Vite default port
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# Database connection
PG_URI = os.environ['PG_URI']
pool = AsyncConnectionPool(PG_URI, open=False)


# Regex patterns
WB_STAMP_RE = re.compile(r'(\d{14})([a-z]{2}_)?')
WB_REFERER_RE = re.compile(
    r'/web/(?P<ts>\d{14})(?P<mod>[a-z]{2}_)?/https?%3A%2F%2F(?P<host>[^/%\?]+)',
    re.IGNORECASE,
)


def _wb_ts_from_iso(dt_str: str) -> str:
    """Convert ISO datetime string to 14-digit Wayback timestamp."""
    if re.fullmatch(r'\d{14}', dt_str):
        return dt_str
    try:
        d = datetime.fromisoformat(dt_str.replace('Z', '+00:00')).astimezone(timezone.utc)
        return d.strftime('%Y%m%d%H%M%S')
    except Exception:
        digits = re.sub(r'\D', '', dt_str)
        return (digits + '00000000000000')[:14]


def _wb_ts_to_iso(ts14: str) -> str:
    """Convert 14-digit Wayback timestamp to ISO datetime."""
    dt = datetime.strptime(ts14, '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _abs_url(base_host: str, val: str) -> str | None:
    """Convert relative URLs to absolute URLs for the same host."""
    if not val or val.startswith(('#', 'data:', 'mailto:', 'javascript:')):
        return None

    if val.startswith('//'):
        parsed = urlsplit('https:' + val)
    elif val.startswith(('http://', 'https://')):
        parsed = urlsplit(val)
    else:
        if val.startswith('/'):
            absu = f'https://{base_host}{val}'
        else:
            absu = f'https://{base_host}/{val}'
        parsed = urlsplit(absu)

    if parsed.hostname != base_host:
        return None

    return urlunsplit(parsed)


def _wb_path(job_id: int, full_url: str, kind: str = '') -> str:
    """Build Wayback-style path: /web/{job_id}{modifier}/{encoded_url}"""
    mod = ''
    if kind == 'image':
        mod = 'im_'
    elif kind == 'css':
        mod = 'cs_'
    elif kind == 'js':
        mod = 'js_'

    enc = quote(full_url, safe='')
    return f'/web/{job_id}{mod}/{enc}'


def rewrite_links_in_html(html_content: str, original_host: str, job_id: int) -> str:
    """Rewrite HTML links to point to archived versions."""
    soup = BeautifulSoup(html_content, 'html.parser')

    # Rewrite href attributes
    for tag in soup.find_all(['a', 'link'], href=True):
        href = tag['href']
        absu = _abs_url(original_host, href)
        if not absu:
            continue

        kind = ''
        if tag.name == 'link':
            rels = set((tag.get('rel') or []))
            if 'stylesheet' in rels:
                kind = 'css'
            elif 'icon' in rels or 'apple-touch-icon' in rels:
                kind = 'image'

        tag['href'] = _wb_path(job_id, absu, kind)

    # Rewrite src attributes
    for tag in soup.find_all(['img', 'script'], src=True):
        src = tag['src']
        absu = _abs_url(original_host, src)
        if not absu:
            continue
        kind = 'image' if tag.name == 'img' else 'js'
        tag['src'] = _wb_path(job_id, absu, kind)

    return str(soup)


async def _fetch_from_db(job_id: int, absolute_url: str):
    """Fetch archived resource from database by job ID."""
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(SQL_FETCH_CONTENT, {'job_id': job_id, 'link': absolute_url})
            return await cur.fetchone()


def _normalize_bytes(raw):
    """Convert various byte formats to bytes."""
    if raw is None:
        return b''
    if isinstance(raw, memoryview):
        return raw.tobytes()
    if isinstance(raw, (bytearray, bytes)):
        return bytes(raw)
    return bytes(raw)


@app.get('/archived-sites', response_model=list[ArchivedSite])
async def get_archived_sites():
    """Get all archived sites with their latest archive job."""
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(SQL_GET_ARCHIVED_SITES)
            rows = await cur.fetchall()
            return [
                ArchivedSite(
                    host=row['host'],
                    latest_job_time=row['latest_job_time'],
                    page_count=row['page_count'],
                    job_count=row['job_count'],
                )
                for row in rows
            ]


@app.get('/archived-sites/{host}/jobs', response_model=list[ArchiveJob])
async def get_site_jobs(host: str):
    """Get all archive jobs for a specific host."""
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(SQL_GET_SITE_JOBS, {'host': host})
            rows = await cur.fetchall()
            return [
                ArchiveJob(
                    id=row['id'],
                    time_started=row['time_started'],
                    page_count=row['page_count'],
                )
                for row in rows
            ]


@app.get('/archived-sites/{host}/jobs/{job_id}/pages', response_model=list[ArchivedPage])
async def get_job_pages(host: str, job_id: int):
    """Get all archived pages for a specific job."""
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(SQL_GET_JOB_PAGES, {'host': host, 'job_id': job_id})
            rows = await cur.fetchall()
            return [
                ArchivedPage(
                    id=row['id'],
                    link=row['link'],
                    host=row['host'],
                    status_code=row['status_code'],
                    content_type=row['content_type'],
                    content_length=row['content_length'],
                )
                for row in rows
            ]


@app.get('/web/{job_and_mod}/{original_url:path}')
async def web_wayback(job_and_mod: str, original_url: str):
    """Serve archived web pages and resources by job ID."""
    # Parse job ID and modifier
    if job_and_mod.isdigit():
        job_id = int(job_and_mod)
    else:
        # Handle modifiers like 5im_, 5cs_, 5js_, etc.
        match = re.match(r'(\d+)([a-z_]+)?', job_and_mod)
        if not match:
            raise HTTPException(status_code=400, detail='Invalid job ID/modifier')
        job_id = int(match.group(1))

    absolute_url = unquote(original_url)
    parsed = urlsplit(absolute_url)
    host = parsed.hostname

    if not host or not parsed.scheme:
        raise HTTPException(status_code=400, detail='URL must be absolute')

    # Debug logging
    print(f'Looking for job_id={job_id}, url={absolute_url}')

    row = await _fetch_from_db(job_id, absolute_url)
    if not row:
        # Try to find what URLs we do have for this job
        async with pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(SQL_DEBUG_QUERY, {'job_id': job_id})
                available_urls = await cur.fetchall()
                print(f'Available URLs for job {job_id}: {[r["link"] for r in available_urls]}')

        raise HTTPException(status_code=404, detail=f'Archived resource not found: {absolute_url}')

    raw = _normalize_bytes(row['content'])
    ctype = (row['content_type'] or '').lower()

    if ctype.startswith('text/html'):
        html = raw.decode('utf-8', errors='ignore')
        rewritten = rewrite_links_in_html(html, host, job_id)
        return Response(content=rewritten, media_type='text/html')

    return Response(content=raw, media_type=row['content_type'] or 'application/octet-stream')


async def run_archive(pool: AsyncConnectionPool, url: str, max_pages: int, num_workers: int) -> None:
    archiver = BasicArchiver(
        pg_pool=pool,
        url=url,
        max_pages=max_pages,
        num_workers=num_workers,
    )
    await archiver.run()


@app.post('/archive')
async def trigger_archive(request: ArchiveRequest):
    """
    Trigger a new archive of the given URL. Schedules work and returns immediately.
    The job id is created inside BasicArchiver.run().
    """
    try:
        loop = asyncio.get_running_loop()
        loop.call_soon(
            loop.create_task,
            run_archive(
                pool,
                str(request.url),
                request.max_pages or 100,
                request.num_workers or 10,
            ),
        )

        return {
            'message': f'archive scheduled for {request.url}',
            'status': 'scheduled',
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'archive failed to schedule: {e}')
