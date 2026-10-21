"""Read public job search pages: HH via Chromium; Dream Job via HTML.
No CAPTCHA solving, access-control bypass, applications or profile exporting.
"""
import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, urlsplit, urlencode
from bs4 import BeautifulSoup
from enhancements import parse_date, published_within

LOG=logging.getLogger("browser_sources")
MSK=timezone(timedelta(hours=3))
MONTHS=dict(zip(("января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря"),range(1,13)))
HH_QUERIES=("AI креатор","AI video creator","LLM разработчик","AI автоматизация")
DJ_QUERIES=("AI креатор","нейрокреатор","AI видео","LLM разработчик","AI автоматизация")
HH_PATTERN=re.compile(r"https://(?:[a-z]+\.)?hh\.ru/vacancy/\d+")
DJ_PATTERN=re.compile(r"https://(?:www\.)?dreamjob\.ru/employers/\d+/vakansii/\d+")
REMOTE_WORDS=("можно удалённо","можно удаленно","удалённая работа","удаленная работа","полностью удал","дистанционная работа","удалённо","удаленно","remote")
NONREMOTE=("только офис","строго офис","готовность к гибриду","гибридный формат","2 дня в офисе","проживание в москве обязательно","выездные съёмки в москве","выездные съемки в москве")
CHALLENGE=("подтвердите, что вы не робот","verify you are human","подозрительная активность","проверка безопасности","доступ ограничен","captcha","капча")

def posted_date(value,now=None):
    if not value:return ""
    d=parse_date(str(value))
    if d:return d.date().isoformat()
    today=now or datetime.now(MSK)
    v=str(value).lower().replace("\u00a0"," ")
    if re.search(r"\bсегодня\b",v):return today.date().isoformat()
    if re.search(r"\bвчера\b",v):return (today-timedelta(days=1)).date().isoformat()
    m=re.search(r"\b(\d{1,2})\s+("+ "|".join(MONTHS) + r")\s*(\d{4})?",v)
    if not m:return ""
    year=int(m.group(3)) if m.group(3) else today.year
    try:
        d=datetime(year,MONTHS[m.group(2)],int(m.group(1)),tzinfo=MSK)
        if not m.group(3) and d>today+timedelta(days=1):d=d.replace(year=year-1)
        return d.date().isoformat()
    except ValueError:return ""

def remote_state(body):
    s=(body or "").lower().replace("\u00a0"," ")
    if any(w in s for w in NONREMOTE):return False
    if any(w in s for w in REMOTE_WORDS):return True
    return None

def challenge_detected(html,status=200):
    if status in (401,403,429):return True
    # Ignore invisible JS strings mentioning captcha: check visible text only.
    soup=BeautifulSoup(html[:200000],"html.parser")
    for x in soup.select("script,style"):x.decompose()
    txt=soup.get_text(" ",strip=True)[:6500].lower()
    return any(w in txt for w in CHALLENGE)

def canonical(href,source):
    base="https://hh.ru" if source=="HeadHunter (веб)" else "https://dreamjob.ru"
    u=urlsplit(urljoin(base,href or ""))
    url=f"{u.scheme}://{u.netloc}{u.path}"
    rule=HH_PATTERN if source=="HeadHunter (веб)" else DJ_PATTERN
    return url if rule.fullmatch(url) else ""

def cards_from_html(html,source,limit=25):
    soup=BeautifulSoup(html,"html.parser")
    data={}
    for a in soup.select('a[href*="/vacancy/"],a[href*="/vakansii/"]'):
        url=canonical(a.get("href"),source)
        if not url:continue
        title=a.get_text(" ",strip=True)
        parent=a.find_parent("article") or a.find_parent("li")
        if not 6<=len(title)<=180:
            h=(a.find(["h2","h3","h4"]) or (parent.find(["h2","h3","h4"]) if parent else None))
            title=h.get_text(" ",strip=True) if h else ""
        title=re.sub(r"\s+"," ",title).strip()
        if 6<=len(title)<=180:data[url]={"url":url,"title":title}
        if len(data)>=limit:break
    return list(data.values())

def parse_detail(html,source,url,title=""):
    soup=BeautifulSoup(html,"html.parser")
    h=soup.find("h1")
    title=h.get_text(" ",strip=True) if h else title
    if not title:return None
    body=soup.find("main") or soup.body or soup
    content=re.sub(r"\s+"," ",body.get_text(" ",strip=True))
    if "вакансия в архиве" in content[:500].lower() or "вакансия закрыта" in content[:500].lower():return None
    pub=""
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            o=json.loads(script.string or script.get_text())
            items=o if isinstance(o,list) else [o]
            for item in items:
                if not isinstance(item,dict):continue
                if item.get("@type")=="JobPosting":
                    pub=posted_date(item.get("datePosted",""))
                    if pub:break
        except (ValueError,TypeError):pass
        if pub:break
    if not pub:
        match=re.search(r"Вакансия опубликована\s*:?\s*(сегодня|вчера|\d{1,2}\s+[а-яё]+(?:\s+\d{4})?)",content,re.I)
        if match:pub=posted_date(match.group(1))
    if not pub:
        for tag in body.select("time"):
            pub=posted_date(tag.get("datetime") or tag.get_text(" ",strip=True))
            if pub:break
    # Don't let unrelated recommendations contaminate work-format detection.
    desc=re.split(r"Похожие вакансии|Вакансии из других подборок",content,maxsplit=1)[0][:11000]
    salary=""
    m=re.search(r"(?:от\s*)?\d[\d\s\u00a0]{3,}(?:\s*[–-]\s*\d[\d\s\u00a0]{3,})?\s*(?:₽|руб|RUB)",desc[:950],re.I)
    if m:salary=re.sub(r"\s+"," ",m.group())[:90]
    company="Не указана"
    c=soup.select_one('[data-qa="vacancy-company-name"]')
    if c:company=c.get_text(" ",strip=True)[:120]
    if source=="Dream Job" and company=="Не указана":
        c=soup.select_one('a[href^="/employers/"]')
        if c:company=c.get_text(" ",strip=True)[:120] or company
    return dict(title=title[:200],company=company,source=source,url=url,
        description=desc,published=pub,salary=salary,remote=remote_state(desc),location="Россия")

async def dreamjob_fetch(client, max_age=30):
    links={}
    errors=[]
    for q in DJ_QUERIES:
        try:
            r=await client.get("https://dreamjob.ru/vakansii",params={"jbfrp[text]":q},timeout=25)
            if challenge_detected(r.text,r.status_code):
                return [],"Остановлено: Dream Job запрашивает подтверждение доступа"
            r.raise_for_status()
            for card in cards_from_html(r.text,"Dream Job",limit=20):links[card["url"]]=card
        except Exception as e:errors.append(type(e).__name__+": "+str(e)[:70])
        await asyncio.sleep(.3)
    jobs=[]
    checked=0
    for card in list(links.values())[:30]:
        try:
            r=await client.get(card["url"],timeout=25)
            if challenge_detected(r.text,r.status_code):
                return jobs,"Остановлено: Dream Job запросил проверку"
            r.raise_for_status()
            j=parse_detail(r.text,"Dream Job",card["url"],card["title"])
            checked+=1
            if j and j["published"] and published_within(j["published"],max_age):
                jobs.append(j)
        except Exception as e:errors.append(type(e).__name__+": "+str(e)[:70])
        await asyncio.sleep(.35)
    status=f"{len(jobs)} вакансий с датой; {len(links)} ссылок; проверено {checked}"
    if errors:status+=f"; ошибок {len(errors)}: {errors[0]}"
    return jobs,status

async def hh_browser_fetch(max_age=30):
    if os.getenv("HH_BROWSER_ENABLED","1")!="1":return [],"Отключён в настройках"
    try:from playwright.async_api import async_playwright
    except ImportError:return [],"Браузер Playwright не установлен"
    links={}
    jobs=[]
    errors=[]
    try:
        async with async_playwright() as p:
            ctx=await p.chromium.launch_persistent_context(
                os.getenv("HH_PROFILE_DIR","/app/data/hh-profile"),headless=True,
                viewport={"width":1360,"height":900},locale="ru-RU",
                timezone_id="Europe/Moscow",args=["--no-sandbox","--disable-dev-shm-usage"])
            try:
                page=await ctx.new_page()
                for term in HH_QUERIES:
                    try:
                        url="https://hh.ru/search/vacancy?"+urlencode({"text":term,"schedule":"remote","order_by":"publication_time","items_on_page":"20"})
                        resp=await page.goto(url,wait_until="domcontentloaded",timeout=28000)
                        await page.wait_for_timeout(1100)
                        html=await page.content()
                        if challenge_detected(html,resp.status if resp else 0):
                            return [],"Нужна ручная проверка HH. Автопоиск остановлен."
                        for c in cards_from_html(html,"HeadHunter (веб)",limit=20):links[c["url"]]=c
                    except Exception as e:errors.append(type(e).__name__+": "+str(e)[:70])
                    await page.wait_for_timeout(650)
                for c in list(links.values())[:26]:
                    try:
                        resp=await page.goto(c["url"],wait_until="domcontentloaded",timeout=25000)
                        html=await page.content()
                        if challenge_detected(html,resp.status if resp else 0):
                            return jobs,"Нужна ручная проверка HH. Автопоиск остановлен."
                        j=parse_detail(html,"HeadHunter (веб)",c["url"],c["title"])
                        if j and j["published"] and published_within(j["published"],max_age):
                            jobs.append(j)
                    except Exception as e:errors.append(type(e).__name__+": "+str(e)[:70])
                    await page.wait_for_timeout(650)
                status=f"{len(jobs)} вакансий с датой; {len(links)} ссылок поиска"
                if errors:status+=f"; ошибок {len(errors)}: {errors[0]}"
                return jobs,status
            finally:await ctx.close()
    except Exception as e:
        LOG.warning("HH browser failed: %s",e)
        return [],"Браузер HH не запустился: "+type(e).__name__+": "+str(e)[:100]
