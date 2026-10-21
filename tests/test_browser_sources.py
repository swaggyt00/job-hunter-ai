import unittest
from datetime import datetime, timedelta, timezone
from browser_sources import posted_date, cards_from_html, parse_detail, remote_state, challenge_detected

class BrowserSourcesTests(unittest.TestCase):
    def test_dates(self):
        now=datetime(2026,10,21,tzinfo=timezone(timedelta(hours=3)))
        self.assertEqual(posted_date("сегодня",now),"2026-10-21")
        self.assertEqual(posted_date("вчера",now),"2026-10-20")
        self.assertEqual(posted_date("19 октября 2026",now),"2026-10-19")
        self.assertEqual(posted_date("21 октября",now),"2026-10-21")
        self.assertEqual(posted_date("не указана",now),"")

    def test_list_links(self):
        hh='<a href="/vacancy/138706534?query=AI">AI Content Creator</a>'
        dream='<a href="/employers/2494103/vakansii/138276601"><h4>Контент-креатор / AI-креатор</h4></a>'
        self.assertEqual(len(cards_from_html(hh,"HeadHunter (веб)")),1)
        self.assertEqual(len(cards_from_html(dream,"Dream Job")),1)
        self.assertEqual(cards_from_html(dream,"Dream Job")[0]["title"],"Контент-креатор / AI-креатор")

    def test_detail_date_and_remote(self):
        html='<main><h1>AI Video Creator</h1><p>100 000–150 000 ₽</p><p>Полностью удалённая работа, полная занятость</p><p>Вакансия опубликована: 20 октября 2026, Москва</p></main>'
        j=parse_detail(html,"Dream Job","https://dreamjob.ru/employers/123/vakansii/1234")
        self.assertEqual(j["published"],"2026-10-20")
        self.assertTrue(j["remote"])
        self.assertIn("100 000",j["salary"])

    def test_non_remote_and_archive(self):
        self.assertFalse(remote_state("Готовность к гибриду, 2 дня в офисе, остальные удалённо"))
        html='<main><h1>Вакансия в архиве</h1><h2>AI Engineer</h2><p>Вакансия опубликована: 21 октября 2026</p></main>'
        self.assertIsNone(parse_detail(html,"Dream Job","https://dreamjob.ru/employers/123/vakansii/1234"))

    def test_challenge_only_visible(self):
        self.assertFalse(challenge_detected('<script>const captchaFlag = true</script><main><h1>Работа</h1></main>'))
        self.assertTrue(challenge_detected('<main><h1>Подтвердите, что вы не робот</h1></main>'))
        self.assertTrue(challenge_detected("",status=403))

if __name__=="__main__":unittest.main()
