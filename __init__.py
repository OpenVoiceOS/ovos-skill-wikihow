import os
import re
from typing import Dict, List, Optional, Tuple

from ovos_bus_client.session import SessionManager, Session
from ovos_utils.log import LOG
from ovos_workshop.decorators import intent_handler
from ovos_workshop.skills.common_query_skill import CommonQuerySkill, CQSMatchLevel
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


class WikiHowSkill(CommonQuerySkill):
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

    def CQS_match_query_phrase(self, phrase: str) -> Optional[Tuple[str, CQSMatchLevel, str, Dict]]:
        """
        Match a query phrase and provide a response from WikiHow if a match is found.

        Args:
            phrase (str): The input query phrase.

        Returns:
            Optional[Tuple[str, CQSMatchLevel, str, Dict]]: The phrase, confidence level, response, and additional data if matched, otherwise None.
        """
        kw = self.extract_keyword(phrase, self.lang)
        if not kw:  # not a "how to" question
            return None
        LOG.debug("WikiHow query: " + phrase)
        how_to = self.get_how_to(phrase)
        if not how_to:
            return None

        sess = SessionManager.get()
        self.session_results[sess.session_id] = {"phrase": phrase,
                                                 "image": None,
                                                 "lang": sess.lang,
                                                 "stop_signaled": False,
                                                 "system_unit": sess.system_unit,
                                                 "spoken_answer": None}
        response = how_to["intro"]
        self.session_results[sess.session_id]["how_to"] = how_to
        return (phrase, CQSMatchLevel.EXACT, response,
                {'query': phrase, 'answer': response, "how_to": how_to})

    def CQS_action(self, phrase: str, data: Dict) -> None:
        """
        Perform an action when the WikiHow result is selected (e.g., display the steps).

        Args:
            phrase (str): The input query phrase.
            data (Dict): Additional data, including the how-to guide.
        """
        self.speak_how_to(data.get("how_to"))

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


if __name__ == "__main__":
    from ovos_utils.fakebus import FakeBus


    # print speak for debugging
    def spk(utt, *args, **kwargs):
        print(utt)


    s = WikiHowSkill(skill_id="fake.test", bus=FakeBus())
    s.speak = spk

    phrase, conf, response, data = s.CQS_match_query_phrase("how do I train my dog")
    s.speak(response)
    # House training a puppy or adult dog may seem daunting, but almost any dog can be trained to wait at the door and relieve themselves outside, instead of going into the house. Create a schedule for feeding your dog and taking them outside. Then, reward your dog with treats and praise when they relieve themselves in the designated outdoor spot. Patience and a good sense of humor are all you really need to help your dog adapt to life as a pet in your home.
    s.CQS_action(phrase, data)
    # Step 1, This is the most important thing you can do to teach your dog to relieve themself outside. While it may seem excessive, try to take them outside as frequently as possible, about every half an hour. Stick to a schedule and try not to miss even one designated "outside time," since your dog will learn to associate these outside trips with relieving themself. If you're training a puppy, you'll need to take them outside more frequently. Puppies have small bladders and can't physically hold their pee for long periods of time.
    # Step 2, Feed your dog at the same time in the morning and at night, then wait 20 to 30 minutes before taking him outside. Having a feeding schedule will make it easier to predict when your dog will have to go to the bathroom, making housetraining easier. Puppies need to be fed three times a day. If you have a puppy, schedule a regular lunchtime feeding as well. Again, a puppy should be given more opportunities to go outside, since it has a smaller bladder.
    # Step 3, Signs include walking around stiffly, sniffing the floor as though they’re looking for a place to go, holding their tail in a funny position, and so on. If your dog shows signs that he needs to go to the bathroom, take them outside right away, even if it's before the designated time to go out. Include a verbal cue, such as saying, "outside" before you take them out. Eventually, you'll be able to ask them if they need to go outside, simply by saying the word. When you first start training your dog to go outside, you're teaching them that when they feel the urge, that means it's time to go outside. Each time your dog successfully goes outside, the idea that bathroom equals outside is reinforced.
    # Step 4, Choose in your backyard, or if you don't have one, near a green patch of grass somewhere. Take your dog back to the same place each and every time you go outside. Dogs are creatures of habit. You can help your dog feel comfortable and less anxious by picking a good spot for them to use as their "bathroom" each time they go out. Use a verbal cue such as, "go potty" when you've reached the spot. They’ll learn to associate it with the place. Remember to follow your city's ordinances regarding picking up after your pet. If you have no choice but to let your dog use a public spot as their bathroom, you'll need to bring a bag so you can pick up the waste and dispose of it.
    # Step 5, When you first bring your dog or puppy home, plan to spend a lot of time watching your pet to make sure they don’t go to the bathroom indoors. This supervisory period is imperative because it enables you to teach the dog to quickly associate the urge to use the bathroom with going outside. Intercepting the dog or puppy before they go in the house is the best way to house train quickly. If you can't stay home all day to supervise your dog, you'll need to have someone else come over to take the dog out several times during the day. Make sure the person knows to take the dog to the designated spot each time.
    # Step 6, If you leave your dog or puppy free to roam the house at night, they are sure to end up soiling the floor. Keeping them in a cozy crate at night and when you're gone reduces the chance that they’ll make a mess. Dogs don't like to soil their dens, so your dog will try to wait until they can go outside to relieve themself. Do not let your dog stay in their crate for too long before taking them outside. If you wait too long, they’ll have no choice but to relieve themself in the crate. Dogs need plenty of exercise and playtime too, so you should never leave them crated for more than a few hours at a time or overnight.
    # Step 7, If your dog makes a mess in the house ( and they definitely will ) , clean it up right away and use a cleaning solution to get rid of the scent. If your dog smells an old mess in a certain spot, they’ll think of that as a bathroom spot. Do not punish the dog for making a mess. Just clean it up and stick to the schedule.
    # Step 8, Dogs learn best through positive reinforcement and they quickly learn the best way to get it. Every time your dog is able to go to the bathroom in their designated spot, reward them with a little treat, lots of praise, and a scratch on the head. You can, of course, reward your dog for other things, like learning how to sit and stay. All good behavior should be rewarded.
    # Step 9, When you're treating your dog for going to the bathroom in their spot, give them a treat and praise right after they finish using the restroom. Don't give it too early or too late, or they won't associate it with going to the bathroom in the right spot.
    # Step 10, Some people have had success using the bell method instead of a treat. When your dog goes to the bathroom in their spot, you ring a bell or pleasant-sounding chime as part of their reward. The dog will come to look forward to the sound of the chime, which should only be used in this specific situation. The drawback here is that, eventually, you won't want to keep using a chime or bell every time your dog goes to the bathroom. Initially phasing it out might be confusing to the dog.
    # Step 11, Whenever you're taking your dog to the bathroom or talking about it, keep your voice light and pleasant. Never raise your voice or take on a menacing tone, because your dog will start to associate their bodily functions with punishment and fear. If your dog makes a mess inside, you can withhold praise, but don't yell at the dog or make them feel ashamed. If using verbal cues, such as "outside", "go potty", or "good dog" be consistent. The repetition of these words along with the action and environment will reinforce where you want your dog to relieve themself.
    # Step 12, Dogs don't respond well to punishment. It scares them and instead of learning to perform well for you, they learn to fear you. Never yell, hit, or do anything that could cause your dog to feel afraid. Do not rub your dog's face in their mess. Contrary to some beliefs, this does not teach a dog not to go to the bathroom in the house. The dog will not understand what you're doing and you'll just end up scaring him.
    # Step 13, If you live on a high rise, you won't be able to make it outside every time your dog needs to go to the bathroom. Pick a spot in your apartment that isn't right in the middle of your living space, but is also easy for your dog to access at any time. A corner of the laundry room or kitchen works well. Choose a spot on hardwood or vinyl flooring, rather than carpet.
    # Step 14, A newspaper is a cheap material you can use to create a bathroom mat for your dog. Absorbent training pads are also available in pet stores. Choose the option that's most convenient for your household. You could also use a dog litter tray. If you'll also take your dog outside to relieve themself, consider filling the tray with soil. This way, the dog will learn that it's acceptable to relieve themself outdoors and indoors.
    # Step 15, Take your dog to the bathroom mat on a strict schedule, just as you would if you were training your dog to go to a spot outside. Frequently walk them to the mat throughout the day and each time they show signs of needing to relieve themself.
    # Step 16, The scent of the urine will help your dog remember that the mat is the place to go to the bathroom. Remove feces right away, but leave a sheet of newspaper or a small bit of padding with urine on the clean mat so your dog will naturally know where to go.
    # Step 17, Each time they successfully go on the mat, reward them with a treat, petting, and praise. They’ll eventually come to associate going to the bathroom on the mat with positive feelings, and they’ll start going there without your help before too long.
