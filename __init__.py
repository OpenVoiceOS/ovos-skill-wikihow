from adapt.intent import IntentBuilder
from mycroft.skills.core import MycroftSkill, intent_handler, intent_file_handler
from mycroft.util.log import LOG
from mycroft.audio import wait_while_speaking

from pywikihow import WikiHow

__author__ = 'jarbas'


class WikiHowSkill(MycroftSkill):
    def initialize(self):
        self.wikihow = WikiHow()
        self.last = None

    def speak_how_to(self, how_to, detailed=False):
        title = how_to["title"]
        if detailed:
            steps = [s["detailed"] for s in how_to["steps"]]
        else:
            steps = [s["step"] for s in how_to["steps"]]
        self.speak(title)
        wait_while_speaking()
        for i, step in enumerate(steps):
            self.speak("step " + str(i) + ", " + step)
            wait_while_speaking()
        self.set_context("PreviousHowto", title)
        self.last = how_to
    
    @intent_file_handler('howto.intent')
    def handle_how_to_intent(self, message):
        query = message.data["query"]
        how_tos = self.wikihow.how_to(query)
        if not len(how_tos):
            self.speak_dialog("howto.failure")
            self.remove_context("PreviousHowto")
        else:
            self.speak_how_to(how_tos[0])

    @intent_handler(IntentBuilder("RepeatHowtoIntent"). \
            require("RepeatKeyword").require("PreviousHowto"))
    def handle_repeat_how_to_intent(self, message):
        how_to = self.last
        self.speak_how_to(how_to)

    @intent_handler(IntentBuilder("TellMoreHowtoIntent"). \
            require("TellMoreKeyword").require("PreviousHowto"))
    def handle_detailed_how_to_intent(self, message):
        how_to = self.last
        self.speak_how_to(how_to, detailed=True)

    @intent_handler(IntentBuilder("RandomHowtoIntent"). \
            require("HowToKeyword").require("RandomKeyword"))
    def handle_random_how_to_intent(self, message):
        how_to = self.wikihow.random()
        self.speak_how_to(how_to)


def create_skill():
    return WikiHowSkill()

