# NO LICENSE

from adapt.intent import IntentBuilder
from mycroft.skills.core import MycroftSkill
from mycroft.util.log import LOG

import requests
import bs4
from time import sleep

__author__ = 'jarbas'


class WikiHowSkill(MycroftSkill):
    def __init__(self):
        super(WikiHowSkill, self).__init__()
        self.wikihow = WikihowScrapper()

    def initialize(self):
        intent = IntentBuilder("RandomHowtoIntent"). \
            require("HowToKeyword").require("RandomKeyword").build()
        self.register_intent(intent, self.handle_random_how_to_intent)

        intent = IntentBuilder("TellMoreHowtoIntent"). \
            require("TellMoreKeyword").require("PreviousHowto").build()
        self.register_intent(intent, self.handle_detailed_how_to_intent)

        intent = IntentBuilder("RepeatHowtoIntent"). \
            require("RepeatKeyword").require("PreviousHowto").build()
        self.register_intent(intent, self.handle_repeat_how_to_intent)

        self.register_intent_file("howto.intent", self.handle_how_to_intent)

    def speak_how_to(self, how_to):
        title = how_to["title"]
        steps = how_to["steps"]
        self.speak(title)
        i = 0
        for step in steps:
            self.speak("step " + str(i) + ", " + step)
            i += 1
            sleep(0.2)
        self.set_context("PreviousHowto", title)

    def handle_how_to_intent(self, message):
        query = message.data["query"]
        how_to = self.wikihow.get_how_to(query)
        if not how_to:
            self.speak_dialog("howto.failure")
            self.remove_context("PreviousHowto")
        else:
            self.speak_how_to(how_to)

    def handle_repeat_how_to_intent(self, message):
        how_to = self.wikihow.last
        self.speak_how_to(how_to)

    def handle_detailed_how_to_intent(self, message):
        how_to = self.wikihow.last
        detailed = how_to["detailed"]
        LOG.debug(detailed)
        self.speak(detailed)

    def handle_random_how_to_intent(self, message):
        how_to = self.wikihow.random_how_to()
        self.speak_how_to(how_to)


def create_skill():
    return WikiHowSkill()


class WikihowScrapper(object):
    def __init__(self):
        self.last = None

    def search_wikihow(self, search_term):
        LOG.info("Seaching wikihow for " + search_term)
        search_url = "http://www.wikihow.com/wikiHowTo?search="
        search_term_query = search_term.replace(" ", "+")
        search_url += search_term_query
        # print search_url
        # open url
        html = self.get_html(search_url)
        soup = bs4.BeautifulSoup(html, "html.parser")
        # parse for links
        list = []
        links = soup.findAll('a', attrs={'class': "result_link"})
        for link in links:
            url = "http:" + link.get('href')
            list.append(url)
        return list

    def get_html(self, url):
        headers = {'User-Agent': "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:41.0) Gecko/20100101 Firefox/41.0"}
        r = requests.get(url, headers=headers)
        html = r.text.encode("utf8")
        return html

    def get_steps(self, url):
        # open url
        html = self.get_html(url)
        soup = bs4.BeautifulSoup(html, "html.parser")

        # get title
        title_html = soup.findAll("h1", {"class": "firstHeading"})
        for html in title_html:
            url = "http:" + html.find("a").get("href")
        title = url.replace("http://www.wikihow.com/", "").replace("-", " ")

        # get steps
        steps = []
        ex_steps = []
        step_html = soup.findAll("div", {"class": "step"})
        for html in step_html:
            step = html.find("b")
            step = step.text

            trash = str(html.find("script"))
            trash = trash.replace("<script>", "").replace("</script>", "").replace(";", "")
            ex_step = html.text.replace(trash, "")

            trash_i = ex_step.find("//<![CDATA[")
            trash_e = ex_step.find(">")
            trash = ex_step[trash_i:trash_e+1]
            ex_step = ex_step.replace(trash, "")

            trash_i = ex_step.find("http://")
            trash_e = ex_step.find(".mp4")
            trash = ex_step[trash_i:trash_e + 4]
            ex_step = ex_step.replace(trash, "")

            trash = "WH.performance.mark('step1_rendered');"
            ex_step = ex_step.replace(trash, "")
            ex_step = ex_step.replace("\n", "")

            steps.append(step)
            ex_steps.append(ex_step)

        # get step pic
        pic_links = []
        pic_html = soup.findAll("a", {"class": "image lightbox"})
        # TODO check pic link, some steps dont have pics!, numbering is wrong
        # sometimes
        for html in pic_html:
            html = html.find("img")
            i = str(html).find("data-src=")
            pic = str(html)[i:].replace('data-src="', "")
            i = pic.find('"')
            pic = pic[:i]
            pic_links.append(pic)

        # link is returned in case of random link
        return title, steps, ex_steps, pic_links, url

    def get_how_to(self, subject):
        how_tos = {}
        links = self.search_wikihow(subject)
        if links == []:
            LOG.info("No wikihow results")
            return None
        link = links[0]
        how_to = {}
        # get steps and pics
        title, steps, descript, pics, link = self.get_steps(link)
        how_to["title"] = title
        how_to["steps"] = steps
        how_to["detailed"] = descript
        how_to["pics"] = pics
        how_to["url"] = link
        how_tos[title] = how_to
        self.last = how_to
        return how_to

    def get_how_tos(self, subject, number=3):
        how_tos = {}
        links = self.search_wikihow(subject)
        if links == []:
            LOG.info("No wikihow results")
            return
        for link in links:
            how_to = {}
            # get steps and pics
            title, steps, descript, pics, link = self.get_steps(link)
            how_to["title"] = title
            how_to["steps"] = steps
            how_to["detailed"] = descript
            how_to["pics"] = pics
            how_to["url"] = link
            how_tos[title] = how_to
            if len(how_tos) >= number:
                break
        self.last = how_tos
        return how_tos

    def random_how_to(self):
        link = "http://www.wikihow.com/Special:Randomizer"
        # get steps and pics
        title, steps, descript, pics, link = self.get_steps(link)
        how_to = {}
        how_to["title"] = title
        how_to["steps"] = steps
        how_to["detailed"] = descript
        how_to["pics"] = pics
        how_to["url"] = link
        return how_to
