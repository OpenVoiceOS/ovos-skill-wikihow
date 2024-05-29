from time import sleep

from ovos_workshop.decorators import intent_handler
from ovos_workshop.intents import IntentBuilder
from ovos_workshop.skills import OVOSSkill
from pywikihow import WikiHow, RandomHowTo


class WikiHowSkill(OVOSSkill):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_howto = None
        self.current_step = 0
        self.detailed = False
        self.speaking = False  # better stop handling
        self.stop_signaled = False
        self.wikihow = WikiHow()

    def initialize(self):
        self.gui.register_handler('skill-wikihow.jarbasskills.next',
                                  self.handle_next)
        self.gui.register_handler('skill-wikihow.jarbasskills.prev',
                                  self.handle_prev)

    # wikihow internals
    def display_howto(self):
        self.gui.clear()
        self.gui["title"] = self.current_howto["title"]
        if self.detailed:
            self.gui["caption"] = self.current_howto["steps"][
                                      self.current_step]["description"] or self.current_howto[
                                      "steps"][self.current_step]["summary"]
        else:
            self.gui["caption"] = self.current_howto["steps"][
                self.current_step]["summary"]
        self.gui["imgLink"] = self.current_howto["steps"][
            self.current_step]["picture"]

        # TODO fix pywikihow, no pictures currently
        # self.gui.show_text(self.current_howto["steps"][step]["description"],
        #                   override_idle=True)

        self.gui.show_page("howto.qml", override_idle=True)  # TODO finish this
        # self.gui.show_image(self.gui["imgLink"],
        #                    title = self.gui["title"],
        #                    caption=self.gui["caption"],
        #                    fill='PreserveAspectFit', override_idle=True)
        self.set_context("WikiHow", self.current_howto["title"])

    def _tx(self, data):
        translated = self.translator.translate(data["title"], self.lang)
        data["title"] = translated

        for idx, step in enumerate(data["steps"]):
            translated = self.translator.translate(step["summary"],
                                                   self.lang)
            data["steps"][idx]["summary"] = translated

            translated = self.translator.translate(step["description"],
                                                   self.lang)
            data["steps"][idx]["description"] = translated
        return data

    def get_how_to(self, query, num=1):
        data = None
        lang = self.lang.split("-")[0]
        tx = False
        if lang not in self.wikihow.lang2url:
            tx = True
            lang = "en"
        for how_to in self.wikihow.search(query, max_results=num, lang=lang):
            data = how_to.as_dict()
            # translate if lang not supported by wikihpw
            if tx:
                data = self._tx(data)
        self.current_howto = data
        return data

    def speak_step(self):
        if self.detailed:
            steps = [s["description"] for s in self.current_howto["steps"]]
        else:
            steps = [s["summary"] for s in self.current_howto["steps"]]

        self.speak_dialog("step", {
            "number": self.current_step + 1,
            "step": steps[self.current_step]
        }, wait=True)

    def speak_how_to(self, how_to=None, start_step=-1):
        self.stop()
        self.speaking = True
        how_to = how_to or self.current_howto
        title = how_to["title"]
        total = len(how_to["steps"])
        self.speak(title, wait=True)
        self.current_step = start_step
        for i in range(total):
            if self.stop_signaled:
                self.stop_signaled = False
                return
            self.handle_next()
            sleep(1)

    # intents
    @intent_handler('howto.intent')
    def handle_how_to_intent(self, message):
        query = message.data["query"]
        # TODO allow user to select how to
        self.detailed = False
        how_to = self.get_how_to(query)
        if not how_to:
            self.speak_dialog("howto.failure")
            self.remove_context("WikiHow")
        else:
            self.speak_how_to()

    @intent_handler(IntentBuilder("RepeatHowtoIntent"). \
                    require("RepeatKeyword").require("WikiHow"))
    def handle_repeat_how_to_intent(self, message):
        self.speak_step()

    @intent_handler(IntentBuilder("TellMoreHowtoIntent"). \
                    require("TellMoreKeyword").require("WikiHow"))
    def handle_detailed_how_to_intent(self, message):
        self.detailed = True
        self.stop()
        self.display_howto()
        self.speak_step()

    @intent_handler(IntentBuilder("RandomHowtoIntent"). \
                    require("HowToKeyword").require("RandomKeyword"))
    def handle_random_how_to_intent(self, message):
        self.stop()
        self.detailed = False
        lang = self.lang.split("-")[0]
        tx = False
        if lang not in self.wikihow.lang2url:
            tx = True
            lang = "en"
        how_to = RandomHowTo(lang=lang).as_dict()
        if tx:
            how_to = self._tx(how_to)
        self.current_howto = how_to
        self.speak_how_to(how_to)

    @intent_handler(
        IntentBuilder("NextStepIntent").require("next").optionally(
            "picture").require("WikiHow"))
    def handle_next(self, message=None):
        total = len(self.current_howto["steps"])
        if message:
            self.stop()  # gui buttons used, abort speech
        self.current_step += 1
        if self.current_step >= total:
            self.current_step = total - 1
        self.display_howto()
        self.speak_step()

    @intent_handler(
        IntentBuilder("PrevStepIntent").require("previous").optionally(
            "picture").require("WikiHow"))
    def handle_prev(self, message=None):
        self.current_step -= 1
        if self.current_step < 0:
            self.current_step = 0
        self.display_howto()
        self.speak_step()

    @intent_handler(
        IntentBuilder("ContinueIntent").require("continue").optionally(
            "picture").require("WikiHow"))
    def handle_continue(self, message=None):
        self.speak_how_to(start_step=self.current_step)

    def stop(self):
        if self.speaking:
            self.speaking = False
            self.stop_signaled = True
            return True
        return False
