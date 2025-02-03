import os
import re
from typing import Dict, List, Optional, Tuple, Any
from ovos_plugin_manager.templates.language import LanguageTranslator, LanguageDetector

from ovos_bus_client.session import SessionManager, Session
from ovos_plugin_manager.templates.solvers import QuestionSolver
from ovos_utils.log import LOG
from ovos_workshop.decorators import intent_handler, common_query
from ovos_workshop.skills.ovos import OVOSSkill
from padacioso import IntentContainer
from padacioso.bracket_expansion import expand_parentheses
from pywikihow import WikiHow
from quebra_frases import sentence_tokenize



def _normalize_text(text: str) -> str:
    """
    Normalize the input text by removing content inside curly braces {}, square brackets [], parentheses (),
    HTML tags, and URLs. Strips leading/trailing whitespace.

    Args:
        text (str): Input text to normalize.

    Returns:
        str: Normalized text.
    """
    text = re.sub(r"\{.*?\}|\[.*?\]|\(.*?\)|<.*?>", "", text)
    text = re.sub(r"http\S+|www\S+", "", text)
    return text.strip()


class WikiHowSkill(OVOSSkill):
    TIMEOUT_SECONDS_PER_SENTENCE: int = 30

    def __init__(self, *args, **kwargs) -> None:
        """
        Initialize the WikiHowSkill with necessary attributes and resources.
        """
        super().__init__(*args, **kwargs)
        self.kw_matchers: Dict[str, IntentContainer] = {}
        self.session_results: Dict[str, Dict] = {}  # session_id: {}
        self.speaking: bool = False  # for stop handling
        self.stop_signaled: bool = False
        self.wikihow: WikiHow = WikiHow()
        self.register_kw_xtract()

    def register_kw_xtract(self) -> None:
        """
        Register keyword extractors for each language by loading patterns from how-to intent files.
        Uses Padacioso to manage keyword matching.
        """
        for lang in self.native_langs:
            filename = f"{self.root_dir}/locale/{lang.lower()}/howto.intent"
            if not os.path.isfile(filename):
                LOG.warning(f"{filename} not found! wikihow common QA will be disabled for '{lang}'")
                continue
            samples: List[str] = []
            with open(filename) as f:
                for line in f.read().split("\n"):
                    if not line.strip() or line.startswith("#"):
                        continue
                    if "(" in line:
                        samples += expand_parentheses(line)
                    else:
                        samples.append(line)

            lang = lang.split("-")[0]
            if lang not in self.kw_matchers:
                self.kw_matchers[lang] = IntentContainer()
            self.kw_matchers[lang].add_intent("question", samples)

    def extract_keyword(self, utterance: str, lang: str) -> Optional[str]:
        """
        Extract the keyword from the utterance using registered keyword matchers for the given language.

        Args:
            utterance (str): The input phrase from which to extract a keyword.
            lang (str): The language to use for keyword extraction.

        Returns:
            Optional[str]: Extracted keyword if available, otherwise None.
        """
        lang = lang.split("-")[0]
        # TODO - closest lang / dialect support
        if lang not in self.kw_matchers:
            return None
        matcher: IntentContainer = self.kw_matchers[lang]
        match = matcher.calc_intent(utterance)
        kw = match.get("entities", {}).get("query")
        if kw:
            LOG.debug(f"WikiHow Keyword: {kw} - Confidence: {match['conf']}")
        else:
            LOG.debug(f"Could not extract search keyword for '{lang}' from '{utterance}'")
        return kw

    # wikihow internals
    def _tx(self, data: Dict) -> Dict:
        """
        Translate WikiHow content (title, steps) into the target language using the skill's translator.

        Args:
            data (Dict): WikiHow content in dictionary format.

        Returns:
            Dict: Translated WikiHow content.
        """
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

    def get_how_to(self, query: str, num: int = 1) -> Optional[Dict]:
        """
        Search for a how-to guide on WikiHow and return the result.

        Args:
            query (str): The query string to search for.
            num (int, optional): Maximum number of results to retrieve. Defaults to 1.

        Returns:
            Optional[Dict]: WikiHow content in dictionary format, or None if no result found.
        """
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
        return data

    def speak_how_to(self, how_to: Dict, sess: Optional[Session] = None) -> None:
        """
        Speak the steps of a WikiHow guide.

        Args:
            how_to (Dict): The WikiHow guide in dictionary format.
            sess (Optional[Session], optional): The session to manage during the speaking process. Defaults to None.
        """
        sess = sess or SessionManager.get()
        title = how_to["title"]
        total = len(how_to["steps"])
        LOG.debug(f"HowTo contains {total} steps")

        self.set_context("WikiHow", title)
        for idx, s in enumerate(how_to["steps"]):
            if self.session_results[sess.session_id].get("stop_signaled"):
                LOG.debug(f"Stopping how-to reading for session: {sess.session_id}")
                break

            if s.get("picture"):
                self.gui.show_image(caption=title, url=s["picture"],
                                    override_idle=True, override_animations=True)

            if self.settings.get("detailed", True):
                txt = s["summary"] + "\n" + s["description"]
            else:
                txt = s["summary"]

            txt = _normalize_text(txt)

            sents = sentence_tokenize(txt)
            self.speak_dialog("step", {"number": idx + 1, "step": sents[0]}, wait=self.TIMEOUT_SECONDS_PER_SENTENCE)
            if len(sents) > 1:
                for s in sents[1:]:
                    if not self.session_results[sess.session_id].get("stop_signaled"):
                        self.speak(s, wait=self.TIMEOUT_SECONDS_PER_SENTENCE)

        LOG.debug("end of HowTo")
        self.session_results.pop(sess.session_id)
        self.gui.release()

    # intents
    @intent_handler('wikihow.intent')
    def handle_how_to_intent(self, message) -> None:
        """
        Handle the 'how to' intent, search for WikiHow results, and speak them.

        Args:
            message: The message object containing the user's query.
        """
        query = message.data["query"]
        how_to = self.get_how_to(query)
        if not how_to:
            self.speak_dialog("howto.failure")
            self.remove_context("WikiHow")
        else:
            sess = SessionManager.get(message)
            self.speak_how_to(how_to, sess)

    def cq_callback(self, utterance: str, answer: str, lang: str):
        """ If selected show gui """
        sess = SessionManager.get()
        how_to = self.session_results[sess.session_id]["how_to"]
        self.speak_how_to(how_to)

    @common_query(callback=cq_callback)
    def match_common_query(self, phrase: str, lang: str) -> Tuple[str, float]:
        """
        Match a query phrase and provide a response from WikiHow if a match is found.

        Args:
            phrase (str): The input query phrase.

        Returns:
            Optional[Tuple[str, CQSMatchLevel, str, Dict]]: The phrase, confidence level, response, and additional data if matched, otherwise None.
        """
        kw = self.extract_keyword(phrase, lang)
        if not kw:  # not a "how to" question
            return None
        LOG.debug("WikiHow query: " + phrase)
        how_to = self.get_how_to(phrase)
        if not how_to:
            return None

        sess = SessionManager.get()
        self.session_results[sess.session_id] = {"phrase": phrase,
                                                 "image": None,
                                                 "lang": lang,
                                                 "stop_signaled": False,
                                                 "system_unit": sess.system_unit,
                                                 "spoken_answer": None}
        response = how_to["intro"]
        self.session_results[sess.session_id]["how_to"] = how_to
        return response, 0.7

    def stop_session(self, sess: Session) -> bool:
        """
        Stop the current WikiHow session by signaling that the user has requested to stop.

        Args:
            sess (Session): The session to stop.

        Returns:
            bool: True if the session was successfully stopped, False otherwise.
        """
        if sess.session_id in self.session_results:
            self.session_results[sess.session_id]["stop_signaled"] = True
            return True
        return False



class WikiHowSolver(QuestionSolver):
    def __init__(self, config: Optional[Dict[str, Any]] = None,
                 translator: Optional[LanguageTranslator] = None,
                 detector: Optional[LanguageDetector] = None):
        super().__init__(config, enable_tx=False, priority=60,
                         translator=translator, detector=detector)
        self.verbose = self.config.get("verbose", True)

    def get_data(self, query: str,
                 lang: Optional[str] = "en",
                 units: Optional[str] = None) -> Dict[str, str]:
        """
        Retrieves WordNet data for the given query.

        Args:
            query (str): The query string.
            lang (Optional[str]): The language of the query. Defaults to None.
            units (Optional[str]): Optional units for the query. Defaults to None.

        Returns:
            Dict[str, str]: A dictionary containing WordNet data such as lemmas, antonyms, definitions, etc.
        """
        for how in WikiHow.search(query, max_results=1, lang=lang):
            return how.as_dict()

    def get_spoken_answer(self, query: str,
                          lang: Optional[str] = None,
                          units: Optional[str] = None) -> Optional[str]:
        """
        Obtain the spoken answer for a given query.

        Args:
            query (str): The query text.
            lang (Optional[str]): Optional language code. Defaults to None.
            units (Optional[str]): Optional units for the query. Defaults to None.

        Returns:
            str: The spoken answer as a text response.
        """
        for how in WikiHow.search(query, max_results=1, lang=lang):
            ans = f"{how.title}\n{how.intro}"
            for s in how.steps:
                ans += f"\n{s.number} - {s.summary}"
                if self.verbose:
                    ans += f"\n{s.description}"
            return _normalize_text(ans)


WIKIHOW_PERSONA = {
  "name": "Wikihow",
  "solvers": [
    "ovos-solver-wikihow-plugin",
    "ovos-solver-failure-plugin"
  ]
}

if __name__ == "__main__":
    from ovos_utils.fakebus import FakeBus

    s = WikiHowSolver({"verbose": True})
    print(s.get_spoken_answer("how to use linux", "en"))
    # Use Linux
    # Most desktop computers run some version of Microsoft Windows, but most servers and a growing number of desktop computers run on Linux kernels, which are flavors of Unix. Learning your way around Linux is traditionally daunting at first, as it seems quite different from Windows, but many current versions are easy to use as they are designed to mimic the Windows look-and-feel. Moving to Linux can be a very rewarding experience, as Linux can be customized more easily, and is generally much faster than Microsoft Windows.
    # 1 - Become familiar with the system.
    # 2 - Test your hardware with a "Live CD" that is supplied by many of the distributions of Linux.
    # 3 - Attempt the tasks you usually use your computer for.
    # 4 - Learn the distributions of Linux.
    # 5 - Consider dual-booting.
    # 6 - Install software
    # 7 - Learn to use  the command-line interface.
    # 8 - Familiarize yourself with the Linux file system.
    # 9 - Keep investigating the potential of your Linux install.
