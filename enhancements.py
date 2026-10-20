"""Russian job feeds and date utilities. Public feeds/APIs only, no authentication bypass."""
import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

HABR_FEED = "https://career.habr.com/vacancies/rss"
TRUDVSEM_API = "https://opendata.trudvsem.ru/api/v1/vacancies"
SEARCHES = ("AI", "LLM", "Langgraph", "нейросети", "генеративный", "автоматизация", "видеопродюсер")
TRUD_QUERIES = ("AI", "LLM", "нейросети", "генеративный", "автоматизация", "нейродизайнер")

def parse_date(value):
    """Parse ISO/RFC822 without confusing unknown dates with today."""
    if not value: return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except (ValueError, TypeError):
        try: dt = parsedate_to_datetime(str(value))
        except (ValueError, TypeError, IndexError): return None
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def published_within(value, days=None, since=None):
    dt = parse_date(value)
    if not dt: return False
    if since:
        return dt.date() >= since
    if days is None: days = 7
    return dt >= datetime.now(timezone.utc) - timedelta(days=int(days))

def parse_habr_feed(xml):
    root = ET.fromstring(xml)
    found=[]
    import re
    for item in root.findall(".//item"):
        fields = {child.tag.rsplit("}", 1)[-1].lower(): (child.text or "").strip()
                  for child in item}
        title = fields.get("title","")
        matched = re.search(r"«(.+?)»", title)
        if matched: title = matched.group(1)
        desc=fields.get("description","")
        url=fields.get("link","")
        if not url.startswith("https://career.habr.com/vacancies/"): continue
        from html import unescape
        desc=unescape(desc)
        found.append(dict(title=unescape(title), company=unescape(fields.get("author") or "Не указана"),
            source="Хабр Карьера", url=url, description=desc,
            published=(parse_date(fields.get("pubdate")) or datetime(1970,1,1,tzinfo=timezone.utc)).isoformat()
                  if fields.get("pubdate") else "",
            salary="", remote=("можно удалённо" in desc.casefold() or "удален" in desc.casefold()),
            location="Россия"))
    return found

def parse_trudvsem(doc):
    rows = (doc.get("results") or {}).get("vacancies") or []
    jobs=[]
    for row in rows:
        v=row.get("vacancy") or {}
        url=v.get("vac_url","")
        if not url.startswith("https://trudvsem.ru/vacancy/"): continue
        description=" ".join(str(v.get(k) or "") for k in
                             ("job-name", "duty", "requirements", "qualification", "schedule","scheduleTypeComment"))
        schedule=description.casefold()
        remote=any(s in schedule for s in
                   ("дистанцион", "удалённ", "удаленн", "работа из дома", "remote"))
        salary=v.get("salary") or ""
        jobs.append(dict(title=str(v.get("job-name") or ""),company=str((v.get("company") or {}).get("name") or "Не указана"),
            source="Работа России",url=url, description=description[:9500],
            published=str(v.get("creation-date") or v.get("hireDate") or ""),
            salary=str(salary),remote=remote,location="Россия"))
    return jobs

async def fetch_russian_sources(client, max_age=30):
    """Return (vacancies, source-status). Every source is isolated and observable."""
    statuses = {}
    async def habr():
        output={}
        errors=[]
        for query in SEARCHES:
            try:
                res=await client.get(HABR_FEED,params={"q":query},
                                     headers={"User-Agent":"JobHunterAI/0.3 personal-job-search"},
                                     timeout=18)
                res.raise_for_status()
                rows=parse_habr_feed(res.content)
                for j in rows:
                    if published_within(j["published"],max_age):
                        output[j["url"]]=j
            except Exception as ex:
                errors.append(type(ex).__name__ + " " + str(ex)[:80])
            await asyncio.sleep(0.18)
        if not output and errors: raise RuntimeError("; ".join(errors[:2]))
        statuses["Хабр Карьера"] = f"{len(output)} свежих вакансий по {len(SEARCHES)} запросам" + (f" ({len(errors)} ошибок)" if errors else "")
        return list(output.values())
    async def trudvsem():
        output={}
        errors=[]
        for query in TRUD_QUERIES:
            try:
                res=await client.get(TRUDVSEM_API,params={"text":query,"limit":70,"offset":0},
                                     headers={"User-Agent":"JobHunterAI/0.3 personal-job-search"},
                                     timeout=21)
                res.raise_for_status()
                payload=res.json()
                for j in parse_trudvsem(payload):
                    if published_within(j["published"],max_age):
                        output[j["url"]]=j
            except Exception as ex:
                errors.append(type(ex).__name__ + " " + str(ex)[:80])
            await asyncio.sleep(0.18)
        if not output and errors: raise RuntimeError("; ".join(errors[:2]))
        statuses["Работа России"] = f"{len(output)} свежих вакансий" + (f" ({len(errors)} ошибок)" if errors else "")
        return list(output.values())
    grouped = await asyncio.gather(habr(),trudvsem(),return_exceptions=True)
    jobs=[]
    for key,out in zip(("Хабр Карьера","Работа России"),grouped):
        if isinstance(out,Exception):
            statuses[key]="Ошибка: "+str(out)[:130]
        else: jobs.extend(out)
    return jobs,statuses
