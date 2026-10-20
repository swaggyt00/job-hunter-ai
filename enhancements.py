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



def parse_geekjob_html(html):
    """Parse public GeekJob vacancy cards, without login or hidden APIs."""
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin
    import re
    soup=BeautifulSoup(html,"html.parser")
    jobs={}
    ru_months={"января":1,"февраля":2,"марта":3,"апреля":4,"мая":5,
        "июня":6,"июля":7,"августа":8,"сентября":9,"октября":10,"ноября":11,"декабря":12}
    for a in soup.select('a[href*="/vacancy/"]'):
        url=urljoin("https://geekjob.ru",a.get("href","")).split("?")[0]
        if not re.match(r"^https://geekjob\.ru/vacancy/[a-zA-Z0-9_-]+$",url): continue
        li=a.find_parent("li") or a.find_parent("article") or a
        phrases=[p.get_text(" ",strip=True) for p in li.find_all("p")]
        phrases=[p.strip() for p in phrases if len(p.strip())>=5 and
                 p.strip().lower() not in ("remote","office","parttime","relocate")]
        if not phrases: continue
        title=phrases[0][:180]
        company=phrases[1][:120] if len(phrases)>1 else "Не указана"
        raw=li.get_text(" ",strip=True)
        lower=raw.casefold()
        remote=("remote" in lower or "удалён" in lower or "удален" in lower)
        pub=""
        date_tag=li.find("time")
        if date_tag:
            label=date_tag.get("datetime") or date_tag.get_text(" ",strip=True)
            stamp=parse_date(label)
            if stamp: pub=stamp.isoformat()
            else:
                m=re.search(r"(\d{1,2})\s+(%s)" % "|".join(ru_months),label.casefold())
                if m:
                    try:
                        dt=datetime(datetime.now(timezone.utc).year,ru_months[m.group(2)],int(m.group(1)),tzinfo=timezone.utc)
                        if dt.date() > datetime.now(timezone.utc).date(): dt=dt.replace(year=dt.year-1)
                        pub=dt.isoformat()
                    except ValueError: pass
        jobs[url]=dict(title=title,company=company,source="GeekJob",
            url=url,description=raw[:7000],published=pub,salary="",
            remote=remote,location="Россия")
    return list(jobs.values())

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
    async def geekjob():
        collected={}
        failures=[]
        for page in (1,2):
            try:
                res=await client.get("https://geekjob.ru/vacancies",params={"page":page},
                    headers={"User-Agent":"JobHunterAI/0.3 personal-job-search"},timeout=20)
                res.raise_for_status()
                jobs=parse_geekjob_html(res.text)
                for j in jobs:
                    if published_within(j["published"],max_age): collected[j["url"]]=j
            except Exception as ex:
                failures.append(str(ex)[:95])
        if not collected and failures: raise RuntimeError("; ".join(failures[:2]))
        statuses["GeekJob"]=str(len(collected))+" свежих вакансий" + (f" ({len(failures)} ошибок)" if failures else "")
        return list(collected.values())
    grouped = await asyncio.gather(habr(),trudvsem(),geekjob(),return_exceptions=True)
    jobs=[]
    for key,out in zip(("Хабр Карьера","Работа России","GeekJob"),grouped):
        if isinstance(out,Exception):
            statuses[key]="Ошибка: "+str(out)[:130]
        else: jobs.extend(out)
    return jobs,statuses
