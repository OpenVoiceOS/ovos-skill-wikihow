from adapt.intent import IntentBuilder
from mycroft.skills.core import MycroftSkill, intent_handler, intent_file_handler
from mtranslate import translate
from pywikihow import WikiHow, RandomHowTo


class WikiHowSkill(MycroftSkill):
    def __init__(self):
        super(WikiHowSkill, self).__init__("WikiHowSkill")
        self.current_howto = None
        self.translate_cache = {}
        self.wikihow = WikiHow()

    def display_howto(self, message=None, step=0, detailed=False):
        if message:
            step = message.data.get("step", 0)
        self.gui["title"] = self.current_howto["title"]
        if detailed:
            self.gui["caption"] = self.current_howto["steps"][step]["description"]
        else:
            self.gui["caption"] = self.current_howto["steps"][step]["summary"]
        self.gui["imgLink"] = self.current_howto["steps"][step]["picture"]

        # TODO fix pywikihow, no pictures currently
        self.gui.show_text(self.current_howto["steps"][step]["description"],
                           override_idle=True)

        #self.gui.show_page("howto.qml", override_idle=True)  # TODO finish this
        #self.gui.show_image(self.gui["imgLink"],
        #                    title = self.gui["title"],
        #                    caption=self.gui["caption"],
        #                    fill='PreserveAspectFit', override_idle=True)

    def _tx(self, data):
        if data["title"] not in self.translate_cache:
            translated = translate(data["title"], self.lang)
            self.translate_cache[data["title"]] = translated
            data["title"] = translated
        else:
            data["title"] = self.translate_cache[data[k]]

        for idx, step in enumerate(data["steps"]):
            if step["summary"] not in self.translate_cache:
                translated = translate(step["summary"], self.lang)
                self.translate_cache[step["summary"]] = translated
                data["steps"][idx]["summary"] = translated
            else:
                data["steps"][idx]["summary"] = self.translate_cache[
                    step["summary"]]

            if step["description"] not in self.translate_cache:
                translated = translate(step["description"], self.lang)
                self.translate_cache[step["description"]] = translated
                data["steps"][idx]["description"] = translated
            else:
                data["steps"][idx]["description"] = self.translate_cache[
                    step["description"]]
        return data

    def get_how_to(self, query, num=1):
        data = None
        lang = self.lang.split("-")[0]
        tx = False
        if lang not in self.wikihow.lang2url:
            tx = True
            lang = "en"
        for how_to in self.wikihow.search(query, max_results=num,  lang=lang):
            data = how_to.as_dict()
            # translate if lang not supported by wikihpw
            if tx:
               data = self._tx(data)
        self.current_howto = data
        return data

    def speak_how_to(self, how_to=None, detailed=False):
        how_to = how_to or self.current_howto
        title = how_to["title"]
        if detailed:
            steps = [s["description"] for s in how_to["steps"]]
        else:
            steps = [s["summary"] for s in how_to["steps"]]
        self.speak(title, wait=True)

        # TODO fix pywikihow images scrapping for step by step
        self.gui.show_url(self.current_howto["url"], override_idle=True)

        for i, step in enumerate(steps):
            #self.display_howto(step=i, detailed=detailed)
            self.speak_dialog("step",
                              {"number": i + 1, "step": step},
                              wait=True)
        self.set_context("PreviousHowto", title)

    @intent_file_handler('howto.intent')
    def handle_how_to_intent(self, message):
        query = message.data["query"]
        # TODO allow user to select how to
        how_to = self.get_how_to(query)
        if not how_to:
            self.speak_dialog("howto.failure")
            self.remove_context("PreviousHowto")
        else:
            self.speak_how_to()

    @intent_handler(IntentBuilder("RepeatHowtoIntent"). \
            require("RepeatKeyword").require("PreviousHowto"))
    def handle_repeat_how_to_intent(self, message):
        self.speak_how_to()

    @intent_handler(IntentBuilder("TellMoreHowtoIntent"). \
            require("TellMoreKeyword").require("PreviousHowto"))
    def handle_detailed_how_to_intent(self, message):
        self.speak_how_to(detailed=True)

    @intent_handler(IntentBuilder("RandomHowtoIntent"). \
            require("HowToKeyword").require("RandomKeyword"))
    def handle_random_how_to_intent(self, message):

        lang = self.lang.split("-")[0]
        tx = False
        if lang not in self.wikihow.lang2url:
            tx = True
            lang = "en"
        how_to = RandomHowTo(lang=lang)
        if tx:
            how_to = self._tx(how_to)
        self.current_howto = how_to
        self.speak_how_to(how_to)


def create_skill():
    return WikiHowSkill()

