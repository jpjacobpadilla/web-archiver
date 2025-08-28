import asyncio
from datetime import datetime
import re
import urllib.parse
from typing import Set, Tuple, Optional

from lxml import html as lxml_html
from stealth_requests import AsyncStealthSession
from psycopg_pool import AsyncConnectionPool

PG_URI = 'postgresql://app_user:dev_password@localhost:5432/app_db'
pool = AsyncConnectionPool(PG_URI, open=False)


class BasicArchiver:
    # CSS url(...) finder (ignores data: and about:)
    CSS_URL_RE = re.compile(
        r"url\(\s*(['\"]?)(?!data:)(?!about:)([^'\"\)]*)\1\s*\)",
        re.IGNORECASE
    )

    def __init__(
            self,
            pg_pool: AsyncConnectionPool,
            url: str,
            num_workers: int = 5,
            max_pages: int = 10
    ):
        self.pg_pool = pg_pool
        self.num_workers = num_workers
        self.url = url
        self.max_pages = max_pages

        self.url_queue: "asyncio.Queue[str]" = asyncio.Queue()
        self.seen: Set[str] = set()
        self.total_links_seen = 0
        self.start_time = datetime.now()
        self.job_id: int | None = None

        # Add lock to prevent race conditions on seen set
        self._seen_lock = asyncio.Lock()

        self.session: AsyncStealthSession | None = None

        # Strict same-host policy anchor
        self._allowed_netloc = urllib.parse.urlparse(self.url).netloc.lower()

    def same_domain(self, u: str) -> bool:
        p = urllib.parse.urlparse(u)
        return p.scheme in {"http", "https"} and p.netloc.lower() == self._allowed_netloc

    @staticmethod
    def abs_url(base: str, u: Optional[str]) -> Optional[str]:
        if not u:
            return None
        a = urllib.parse.urljoin(base, u)
        a, _ = urllib.parse.urldefrag(a)
        return a

    @staticmethod
    def classify_type(content_type: Optional[str], url: str) -> str:
        ct = (content_type or "").split(";")[0].strip().lower()
        ext = url.rsplit(".", 1)[-1].lower() if "." in url else ""
        if ct == "text/html" or ext in {"html", "htm", "php", "asp", "aspx"}:
            return "html"
        if ct == "text/css" or ext == "css":
            return "css"
        if ct in {"application/javascript", "text/javascript"} or ext in {"js", "mjs"}:
            return "js"
        if ct.startswith("image/") or ext in {"png", "jpg", "jpeg", "gif", "svg", "webp", "bmp", "ico"}:
            return "image"
        if ct.startswith("video/") or ext in {"mp4", "webm", "ogg", "mov", "mkv"}:
            return "video"
        if ct.startswith("font/") or ext in {"woff", "woff2", "ttf", "otf", "eot"}:
            return "font"
        return "other"

    async def run(self):
        async with self.pg_pool.connection() as conn:
            async with conn.cursor() as cur:
                # create a new archive job and return its id
                await cur.execute(
                    """
                    insert into archive_jobs (time_started)
                    values (CURRENT_TIMESTAMP) returning id
                    """
                )
                row = await cur.fetchone()
                self.job_id = row[0]  # save job id on the instance

        # Seed the queue so workers have something to do
        await self.put_todo(self.url)

        # If AsyncStealthSession is actually async, change to: async with AsyncStealthSession() as session:
        async with AsyncStealthSession() as session:
            self.session = session

            workers = [asyncio.create_task(self.worker()) for _ in range(self.num_workers)]
            await self.url_queue.join()

            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

    async def worker(self):
        while True:
            try:
                await self.process_one()
            except asyncio.CancelledError:
                return

    async def process_one(self):
        url = await self.url_queue.get()
        try:
            await self.crawl(url)
        except Exception as exc:
            print(exc)
        finally:
            self.url_queue.task_done()

    async def crawl(self, url: str):
        # light pacing to avoid hammering
        await asyncio.sleep(0.1)

        # If get() is async in your lib, make this: resp = await self.session.get(url)
        resp = await self.session.get(url)

        final_url = str(resp.url)
        if not self.same_domain(final_url):
            # Redirected off-domain — drop
            return

        print(resp.status_code)

        ctype = (resp.headers.get("content-type") or "").lower()
        is_html = "text/html" in ctype and resp.status_code == 200

        if is_html:
            pages, assets = await self.parse_links(base=final_url, text=resp.text or "")
            await self.on_found_links(pages | assets)

        await self.archive_content(resp, source_url=final_url)

    async def archive_content(self, resp, source_url: str):
        headers = resp.headers or {}
        content = resp.content
        link = resp.url or source_url

        params = {
            "link": link,
            "host": urllib.parse.urlparse(link).netloc.lower(),
            "status_code": resp.status_code,
            "content_type": headers.get("content-type"),
            "content": content,
            "content_length": len(content),
            "scraping_job": self.job_id,
        }

        sql = """
              insert into archived_resource
              (link, host, status_code, content_type, content, content_length, scraping_job)
              values (%(link)s, %(host)s, %(status_code)s, %(content_type)s,
                      %(content)s, %(content_length)s, %(scraping_job)s) returning id \
              """

        async with self.pg_pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                _row = await cur.fetchone()  # id if you want it

    async def parse_links(self, base: str, text: str) -> Tuple[Set[str], Set[str]]:
        """
        Parse HTML and return (pages_to_crawl, assets_to_fetch), both same-domain.
        Uses lxml; normalizes to absolute links and strips fragments.
        """
        pages: Set[str] = set()
        assets: Set[str] = set()

        try:
            doc = lxml_html.fromstring(text or "")
        except Exception:
            return pages, assets

        # Make relative links absolute (respects <base href> if present)
        doc.make_links_absolute(base, resolve_base_href=True)

        # 1) Page links (<a href>)
        for el in doc.xpath("//a[@href]"):
            u = self.abs_url(base, el.get("href"))
            if u and self.same_domain(u):
                pages.add(u)

        # 2) Asset links
        # img/src, poster, script/src, iframe/src, embed/src, audio/src, video/src, source/src, track/src
        asset_xpaths = [
            ("src",
             "//img[@src] | //script[@src] | //iframe[@src] | //embed[@src] | //audio[@src] | //video[@src] | //source[@src] | //track[@src]"),
            ("poster", "//video[@poster]"),
            ("href", "//link[@href]"),  # stylesheets, icons, preloads, etc.
        ]
        for attr, xp in asset_xpaths:
            for el in doc.xpath(xp):
                u = self.abs_url(base, el.get(attr))
                if u and self.same_domain(u):
                    assets.add(u)

        # 3) srcset (img/source)
        for el in doc.xpath("//img[@srcset] | //source[@srcset]"):
            srcset = el.get("srcset") or ""
            for cand in srcset.split(","):
                part = cand.strip().split()[0] if cand.strip() else ""
                u = self.abs_url(base, part)
                if u and self.same_domain(u):
                    assets.add(u)

        # 4) Inline style attributes: url(...)
        for el in doc.xpath("//*[@style]"):
            style_val = el.get("style") or ""
            for m in self.CSS_URL_RE.finditer(style_val):
                u = self.abs_url(base, m.group(2).strip())
                if u and self.same_domain(u):
                    assets.add(u)

        # 5) <style> blocks: url(...)
        for el in doc.xpath("//style"):
            css_text = el.text or ""
            for m in self.CSS_URL_RE.finditer(css_text):
                u = self.abs_url(base, m.group(2).strip())
                if u and self.same_domain(u):
                    assets.add(u)

        # Ensure assets aren't crawled as pages
        assets -= pages
        return pages, assets

    async def on_found_links(self, urls: Set[str]):
        # Use lock to prevent race conditions when checking/updating seen set
        async with self._seen_lock:
            new = urls - self.seen
            self.seen.update(new)

        # Queue new URLs (outside the lock since put_todo is already thread-safe)
        for u in new:
            await self.put_todo(u)

    async def put_todo(self, url: str):
        if self.total_links_seen >= self.max_pages:
            return
        p = urllib.parse.urlparse(url)
        if p.scheme not in {"http", "https"}:
            return
        if p.netloc.lower() != self._allowed_netloc:
            return
        self.total_links_seen += 1
        await self.url_queue.put(url)


async def main():
    await pool.open()

    archiver = BasicArchiver(
        pg_pool=pool,
        url="https://jacobpadilla.com",
        max_pages=50,
        num_workers=8,
    )

    await archiver.run()


if __name__ == "__main__":
    asyncio.run(main())
