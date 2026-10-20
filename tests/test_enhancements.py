import unittest
from datetime import datetime, timedelta, timezone
from enhancements import parse_date, published_within, parse_habr_feed, parse_trudvsem, parse_geekjob_html

class TestPublicationAndSources(unittest.TestCase):
    def test_rfc822_and_iso(self):
        self.assertEqual(parse_date("Tue, 20 Oct 2026 14:48:43 +0300").hour, 11)
        self.assertEqual(parse_date("2026-10-20T11:48:43+00:00").hour, 11)
        self.assertIsNone(parse_date(""))
        self.assertIsNone(parse_date("not a date"))

    def test_range(self):
        recent=(datetime.now(timezone.utc)-timedelta(hours=3)).isoformat()
        old=(datetime.now(timezone.utc)-timedelta(days=15)).isoformat()
        self.assertTrue(published_within(recent,days=1))
        self.assertFalse(published_within(old,days=7))
        self.assertFalse(published_within("",days=7))
        self.assertTrue(published_within("2026-10-19",since=datetime(2026,10,18).date()))
        self.assertFalse(published_within("2026-10-17",since=datetime(2026,10,18).date()))

    def test_habr_rss(self):
        xml='''<rss><channel><item>
        <title>Требуется «AI-разработчик» (от 150 000 ₽)</title>
        <author>Компания</author>
        <link>https://career.habr.com/vacancies/100123</link>
        <description>Полный рабочий день. Можно удалённо. Python LLM</description>
        <pubDate>Tue, 20 Oct 2026 14:48:43 +0300</pubDate>
        </item></channel></rss>'''.encode()
        jobs=parse_habr_feed(xml)
        self.assertEqual(len(jobs),1)
        self.assertEqual(jobs[0]["title"],"AI-разработчик")
        self.assertTrue(jobs[0]["remote"])
        self.assertEqual(jobs[0]["company"],"Компания")
        self.assertTrue(jobs[0]["published"].startswith("2026-10-20T11:48"))

    def test_geekjob(self):
        markup='''<ul><li><a href="/vacancy/6abc123"><p>AI Video Creator</p>
        <p>Media Studio</p><p>remote</p><time>20 октября</time></a></li></ul>'''
        jobs=parse_geekjob_html(markup)
        self.assertEqual(len(jobs),1)
        self.assertTrue(jobs[0]["remote"])
        self.assertEqual(jobs[0]["company"],"Media Studio")
        self.assertEqual(jobs[0]["title"],"AI Video Creator")
        self.assertTrue(jobs[0]["url"].startswith("https://geekjob.ru/vacancy/"))

    def test_trudvsem(self):
        doc={"results":{"vacancies":[{"vacancy":{"job-name":"AI-креатор","vac_url":"https://trudvsem.ru/vacancy/card/x/1",
            "company":{"name":"Studio"},"creation-date":"2026-10-20",
            "schedule":"Дистанционная работа", "salary":"от 100000", "duty":"Генерировать рекламу"}}]}}
        jobs=parse_trudvsem(doc)
        self.assertEqual(len(jobs),1)
        self.assertTrue(jobs[0]["remote"])
        self.assertIn("100000",jobs[0]["salary"])
        self.assertEqual(jobs[0]["source"],"Работа России")

if __name__=="__main__":
    unittest.main()
