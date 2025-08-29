import re
import asyncio
import urllib.parse
from datetime import datetime
from pathlib import Path

from lxml import html as lxml_html
from stealth_requests import AsyncStealthSession
from psycopg_pool import AsyncConnectionPool


# CSS url(...) finder regex
CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)(?!data:)(?!about:)([^'\"\)]*)\1\s*\)", re.IGNORECASE)

SQL_DIR = Path(__file__).parent / 'sql'
SQL_INSERT_JOB = (SQL_DIR / 'insert_job.sql').read_text(encoding='utf-8')
SQL_ARCHIVE_CONTENT = (SQL_DIR / 'archive_content.sql').read_text(encoding='utf-8')


class BasicArchiver:
    def __init__(self, pg_pool: AsyncConnectionPool, url: str, num_workers: int = 5, max_pages: int = 10):
        """
        Args:
            pg_pool: Psycopg connection pool instance
            url: Starting URL to archive (determines allowed domain)
            num_workers: Number of concurrent workers for crawling
            max_pages: Maximum number of pages to archive
        """
        self.pg_pool = pg_pool
        self.num_workers = num_workers
        self.url = url
        self.max_pages = max_pages

        self.url_queue: asyncio.Queue[str] = asyncio.Queue()
        self.seen: set[str] = set()
        self.total_links_seen = 0
        self.start_time = datetime.now()
        self._seen_lock = asyncio.Lock()
        self._allowed_netloc = urllib.parse.urlparse(self.url).netloc.lower()

        self.job_id: int | None = None
        self.session: AsyncStealthSession | None = None

    def same_domain(self, u: str) -> bool:
        """
        Check if a URL belongs to the same domain as the initial URL.
        """
        p = urllib.parse.urlparse(u)
        return p.scheme in {'http', 'https'} and p.netloc.lower() == self._allowed_netloc


    @staticmethod
    def abs_url(base: str, u: str | None) -> str | None:
        """
        Convert a relative URL to an absolute URL and remove any fragment identifier.

        Args:
            base: The base URL to resolve relative URLs against
            u: The URL to convert (can be relative or absolute)

        Returns:
            The absolute URL with fragment removed, or None if input URL is None/empty

        Examples:
            abs_url("https://example.com/page", "../style.css")
            -> "https://example.com/style.css"

            abs_url("https://example.com/", "/contact#section")
            -> "https://example.com/contact"

            abs_url("https://example.com/", "https://other.com/file.js")
            -> "https://other.com/file.js"
        """
        if not u:
            return None
        a = urllib.parse.urljoin(base, u)
        a, _ = urllib.parse.urldefrag(a)
        return a

    async def run(self) -> None:
        """
        Start the archiving process.
        """
        async with self.pg_pool.connection() as conn:
            async with conn.cursor() as cur:
                # create a new archive job and return its id
                await cur.execute(SQL_INSERT_JOB)
                row = await cur.fetchone()
                self.job_id = row[0]  # save job id on the instance

        # Seed the queue so workers have something to do
        await self.put_todo(self.url)

        async with AsyncStealthSession() as session:
            self.session = session

            workers = [asyncio.create_task(self.worker()) for _ in range(self.num_workers)]
            await self.url_queue.join()

            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

    async def worker(self) -> None:
        while True:
            try:
                await self.process_one()
            except asyncio.CancelledError:
                return

    async def process_one(self) -> None:
        url = await self.url_queue.get()
        try:
            await self.crawl(url)
        except Exception as exc:
            print(exc)
        finally:
            self.url_queue.task_done()

    async def crawl(self, url: str) -> None:
        """
        Crawl a single URL and extract links if it's an HTML page.

        Args:
            url: The URL to crawl
        """
        await asyncio.sleep(0.1)

        resp = await self.session.get(url)

        final_url = str(resp.url)
        if not self.same_domain(final_url):
            return

        print(f'Crawled page: {url} - Status code: {resp.status_code}')

        ctype = (resp.headers.get('content-type') or '').lower()
        is_html = 'text/html' in ctype and resp.status_code == 200

        if is_html:
            pages, assets = await self.parse_links(base=final_url, text=resp.text or '')
            await self.on_found_links(pages | assets)

        await self.archive_content(resp, source_url=final_url)

    async def archive_content(self, resp, source_url: str) -> None:
        """
        Store the response content in the database.

        Args:
            resp: HTTP response object containing headers, content, etc.
            source_url: Original URL that was requested

        Extracts response data and inserts it into the archived_resource table
        associated with the current archive job.
        """
        headers = resp.headers or {}
        content = resp.content
        link = resp.request.url or source_url

        params = {
            'link': link,
            'host': urllib.parse.urlparse(link).netloc.lower(),
            'status_code': resp.status_code,
            'content_type': headers.get('content-type'),
            'content': content,
            'content_length': len(content),
            'scraping_job': self.job_id,
        }

        async with self.pg_pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(SQL_ARCHIVE_CONTENT, params)
                _row = await cur.fetchone()  # id if you want it

    async def parse_links(self, base: str, text: str) -> tuple[set[str], set[str]]:
        """
        Parse HTML content and extract all links to pages and assets.

        Args:
            base: Base URL for resolving relative links
            text: HTML content to parse

        Returns:
            Tuple of (page_links, asset_links) where both are sets of absolute URLs
            from the same domain. Pages are from <a> tags, assets are from <img>,
            <script>, <link>, CSS url(), srcset attributes, etc.

        Uses lxml to parse HTML and extract links from various elements and attributes.
        Filters out data: URIs, fragments, and off-domain links.
        """
        pages: set[str] = set()
        assets: set[str] = set()

        try:
            doc = lxml_html.fromstring(text or '')
        except Exception:
            return pages, assets

        # Make relative links absolute (respects <base href> if present)
        doc.make_links_absolute(base, resolve_base_href=True)

        # 1) Page links (<a href>)
        for el in doc.xpath('//a[@href]'):
            u = self.abs_url(base, el.get('href'))
            if u and self.same_domain(u):
                pages.add(u)

        # 2) Asset links
        # img/src, poster, script/src, iframe/src, embed/src, audio/src, video/src, source/src, track/src
        asset_xpaths = [
            (
                'src',
                '//img[@src] | //script[@src] | //iframe[@src] | //embed[@src] | //audio[@src] | //video[@src] | //source[@src] | //track[@src]',
            ),
            ('poster', '//video[@poster]'),
            ('href', '//link[@href]'),  # stylesheets, icons, preloads, etc.
        ]
        for attr, xp in asset_xpaths:
            for el in doc.xpath(xp):
                u = self.abs_url(base, el.get(attr))
                if u and self.same_domain(u):
                    assets.add(u)

        # 3) srcset (img/source)
        for el in doc.xpath('//img[@srcset] | //source[@srcset]'):
            srcset = el.get('srcset') or ''
            for cand in srcset.split(','):
                part = cand.strip().split()[0] if cand.strip() else ''
                u = self.abs_url(base, part)
                if u and self.same_domain(u):
                    assets.add(u)

        # 4) Inline style attributes: url(...)
        for el in doc.xpath('//*[@style]'):
            style_val = el.get('style') or ''
            for m in CSS_URL_RE.finditer(style_val):
                u = self.abs_url(base, m.group(2).strip())
                if u and self.same_domain(u):
                    assets.add(u)

        # 5) <style> blocks: url(...)
        for el in doc.xpath('//style'):
            css_text = el.text or ''
            for m in CSS_URL_RE.finditer(css_text):
                u = self.abs_url(base, m.group(2).strip())
                if u and self.same_domain(u):
                    assets.add(u)

        # Ensure assets aren't crawled as pages
        assets -= pages
        return pages, assets

    async def on_found_links(self, urls: set[str]) -> None:
        """
        Process newly discovered URLs and add unseen ones to the crawl queue.

        Args:
            urls: Set of absolute URLs discovered during parsing

        Uses a lock to prevent race conditions when multiple workers discover
        the same URLs simultaneously. Only adds URLs that haven't been seen before.
        """
        async with self._seen_lock:
            new = urls - self.seen
            self.seen.update(new)

        for u in new:
            await self.put_todo(u)

    async def put_todo(self, url: str) -> None:
        """
        Add a URL to the crawl queue if it meets criteria.

        Args:
            url: URL to potentially add to the queue

        Checks if the URL is valid (http/https, same domain) and if we haven't
        exceeded the max_pages limit before adding it to the queue.
        """
        if self.total_links_seen >= self.max_pages:
            return

        p = urllib.parse.urlparse(url)
        if p.scheme not in {'http', 'https'} or not self.same_domain(url):
            return

        self.total_links_seen += 1
        await self.url_queue.put(url)
