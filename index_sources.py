"""Experimental public search-index discovery. Never scrapes the target job sites."""
import re
from urllib.parse import urlparse, parse_qs, unquote
from html import unescape
import xml.etree.ElementTree as ET

INDEX_TERMS = (
    "AI креатор удаленно",
    "нейрокреатор удаленно",
    "AI video creator remote",
    "LLM разработчик удаленно",
    "AI automation инженер",
)
SITES = {
    "HH индекс": ("site:hh.ru/vacancy/", re.compile(r"^https?://(?:[a-z]+\.)?hh\.ru/vacancy/\d+")),
    "Dream Job индекс": ("site:dreamjob.ru/employers/ vakansii", re.compile(r"^https?://(?:www\.)?dreamjob\.ru/employers/\d+/vakansii/\d+")),
    "getmatch индекс": ("site:getmatch.ru/vacancies/", re.compile(r"^https?://(?:www\.)?getmatch\.ru/vacancies/[a-zA-Z0-9_-]+")),
}
def clean(value):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(value or ""))).strip()

def parse_index_rss(data, source):
    """Return only canonical job links. RSS pubDate is INDEX DATE, not job publish date."""
    jobs=[]
    try: root=ET.fromstring(data[:1500000])
    except ET.ParseError: return jobs
    pattern=SITES[source][1]
    for item in root.findall(".//item"):
        def field(tag):
            n=item.find(tag)
            return "".join(n.itertext()).strip() if n is not None else ""
        link=unescape(field("link")).split("#")[0].split("?")[0]
        if not pattern.match(link): continue
        title=clean(field("title"))[:200]
        desc=clean(field("description"))[:1500]
        if not title: continue
        if "в архиве" in (title+" "+desc).casefold(): continue
        # No fabricated publishing date, no assertion of remote work.
        jobs.append(dict(title=title,company="Не указана",source=source,
            url=link,description=desc,published="",salary="",remote=None,location="Россия"))
    return jobs

async def fetch_index(client):
    """Search only third-party public web indexes. Report errors/zero transparently."""
    jobs=[]
    statuses={}
    for name,(site,_) in SITES.items():
        seen={}
        errors=[]
        for term in INDEX_TERMS[:3]:
            try:
                resp=await client.get("https://www.bing.com/search",
                    params={"q":site+" "+term,"format":"rss"},
                    headers={"Accept":"application/rss+xml, application/xml", "User-Agent":"JobHunterAI/0.4 (personal noncommercial vacancy discovery)"},
                    timeout=14, follow_redirects=True)
                resp.raise_for_status()
                if not resp.text.lstrip().startswith("<?xml") and not resp.text.lstrip().startswith("<rss"):
                    errors.append("Not an RSS response")
                    break
                for job in parse_index_rss(resp.content,name): seen[job["url"]]=job
            except Exception as exc:
                errors.append(type(exc).__name__ +": "+str(exc)[:80])
                break
        statuses[name] = (f"{len(seen)} индексных ссылок; дата неизвестна"
                          if seen else ("Нет индексных ссылок"+("; "+errors[0] if errors else "")))
        jobs.extend(seen.values())
    return jobs,statuses
