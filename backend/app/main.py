import re
from typing import List, Optional
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from urllib.parse import urlsplit, urlunsplit, quote, unquote

from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row

from bs4 import BeautifulSoup

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response


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
PG_URI = 'postgresql://app_user:dev_password@localhost:5432/app_db'
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


def _abs_url(base_host: str, val: str) -> Optional[str]:
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
            query = """
                    SELECT content, content_type, host
                    FROM archived_resource
                    WHERE scraping_job = %s \
                      AND link = %s LIMIT 1 \
                    """
            await cur.execute(query, (job_id, absolute_url))
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


# API Endpoints
@app.get('/archived-sites', response_model=List[ArchivedSite])
async def get_archived_sites():
    """Get all archived sites with their latest archive job."""
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            query = """
                    SELECT ar.host, \
                           MAX(aj.time_started)  AS latest_job_time, \
                           COUNT(DISTINCT ar.id) AS page_count, \
                           COUNT(DISTINCT aj.id) AS job_count
                    FROM archived_resource ar
                             JOIN archive_jobs aj ON ar.scraping_job = aj.id
                    WHERE ar.content_type LIKE 'text/html%%' \
                       OR ar.content_type = 'text/html'
                    GROUP BY ar.host
                    ORDER BY latest_job_time DESC \
                    """
            await cur.execute(query)
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


@app.get('/archived-sites/{host}/jobs', response_model=List[ArchiveJob])
async def get_site_jobs(host: str):
    """Get all archive jobs for a specific host."""
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            query = """
                    SELECT aj.id, \
                           aj.time_started, \
                           COUNT(ar.id) AS page_count
                    FROM archive_jobs aj
                             JOIN archived_resource ar ON aj.id = ar.scraping_job
                    WHERE ar.host = %s
                      AND (ar.content_type LIKE 'text/html%%' OR ar.content_type = 'text/html')
                    GROUP BY aj.id, aj.time_started
                    ORDER BY aj.time_started DESC \
                    """
            await cur.execute(query, (host,))
            rows = await cur.fetchall()
            return [
                ArchiveJob(
                    id=row['id'],
                    time_started=row['time_started'],
                    page_count=row['page_count'],
                )
                for row in rows
            ]


@app.get('/archived-sites/{host}/jobs/{job_id}/pages', response_model=List[ArchivedPage])
async def get_job_pages(host: str, job_id: int):
    """Get all archived pages for a specific job."""
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            query = """
                    SELECT id, link, host, status_code, content_type, content_length
                    FROM archived_resource
                    WHERE host = %s
                      AND scraping_job = %s
                      AND (content_type LIKE 'text/html%%' OR content_type = 'text/html')
                    ORDER BY link \
                    """
            await cur.execute(query, (host, job_id))
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
                debug_query = 'SELECT link FROM archived_resource WHERE scraping_job = %s LIMIT 10'
                await cur.execute(debug_query, (job_id,))
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


@app.post('/archive')
async def trigger_archive(request: ArchiveRequest):
    """Trigger a new archive of the given URL."""
    try:
        # Create a new archive job
        async with pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                query = """
                        INSERT INTO archive_jobs (time_started)
                        VALUES (NOW()) RETURNING id \
                        """
                await cur.execute(query)
                job_row = await cur.fetchone()
                job_id = job_row['id']

        return {
            'message': f'Archive triggered for {request.url}',
            'status': 'started',
            'job_id': job_id,
            'max_pages': request.max_pages,
            'num_workers': request.num_workers,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Archive failed: {str(e)}')


# Asset fallback routes
@app.get('/static/{path:path}')
async def static_fallback(path: str, request: Request):
    """Handle static asset requests from archived pages."""
    referer = request.headers.get('referer', '')
    job_match = re.search(r'/web/(\d+)[^/]*/', referer)
    if not job_match:
        raise HTTPException(status_code=404, detail='Static asset not found')

    job_id = int(job_match.group(1))

    # Extract host from referer
    host_match = re.search(r'https?%3A%2F%2F([^/%\?]+)', referer)
    if not host_match:
        raise HTTPException(status_code=404, detail='Cannot determine host')

    host = unquote(host_match.group(1))
    absolute_url = f'https://{host}/static/{path}'

    row = await _fetch_from_db(job_id, absolute_url)
    if not row:
        raise HTTPException(status_code=404, detail='Archived static asset not found')

    raw = _normalize_bytes(row['content'])
    return Response(content=raw, media_type=row['content_type'] or 'application/octet-stream')


@app.get('/favicon.ico')
async def favicon_fallback(request: Request):
    """Handle favicon requests from archived pages."""
    referer = request.headers.get('referer', '')
    job_match = re.search(r'/web/(\d+)[^/]*/', referer)
    if not job_match:
        raise HTTPException(status_code=404, detail='Favicon not found')

    job_id = int(job_match.group(1))

    # Extract host from referer
    host_match = re.search(r'https?%3A%2F%2F([^/%\?]+)', referer)
    if not host_match:
        raise HTTPException(status_code=404, detail='Cannot determine host')

    host = unquote(host_match.group(1))
    absolute_url = f'https://{host}/favicon.ico'

    row = await _fetch_from_db(job_id, absolute_url)
    if not row:
        raise HTTPException(status_code=404, detail='Archived favicon not found')

    raw = _normalize_bytes(row['content'])
    return Response(content=raw, media_type=row['content_type'] or 'image/x-icon')


# General asset fallback route
@app.get('/{path:path}')
async def general_fallback(path: str, request: Request):
    """Handle any other asset requests by looking at referer."""
    # Skip API endpoints
    if path.startswith(('archived-sites', 'archive', 'web/')):
        raise HTTPException(status_code=404, detail='Not found')

    referer = request.headers.get('referer', '')
    job_match = re.search(r'/web/(\d+)[^/]*/', referer)
    if not job_match:
        raise HTTPException(status_code=404, detail=f'Asset not found: /{path}')

    job_id = int(job_match.group(1))

    # Extract host from referer
    host_match = re.search(r'https?%3A%2F%2F([^/%\?]+)', referer)
    if not host_match:
        raise HTTPException(status_code=404, detail='Cannot determine host')

    host = unquote(host_match.group(1))
    absolute_url = f'https://{host}/{path}'

    row = await _fetch_from_db(job_id, absolute_url)
    if not row:
        raise HTTPException(status_code=404, detail=f'Archived asset not found: /{path}')

    raw = _normalize_bytes(row['content'])
    return Response(content=raw, media_type=row['content_type'] or 'application/octet-stream')


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='0.0.0.0', port=8000)
