#!/usr/bin/env python3
"""Hampstead Heath and its village - build the walking audio guide.

Everything the guide says lives in STOPS, below. Running this file renders the
narration to AAC with a system voice, measures what came out, and writes
index.html from the same text, so the transcript on the page can never drift
out of step with the recording.

    python3 build.py              audio, then the page
    python3 build.py --page       page only, timed from the audio already there
    python3 build.py --cover      redraw cover.jpg
    python3 build.py --voices     list the voices available for this engine
    python3 build.py --sample     render one track so you can hear the voice
    python3 build.py --cost       how many credits a full rebuild costs

Needs macOS (afconvert) and mutagen. The voice comes from ElevenLabs by
default; see the ENGINE note below for why, and for the local alternative.
"""

import html as _html
import json
import math
import os
import re
import subprocess
import sys
import time

# --------------------------------------------------------------------------
# the voice.
#
# "elevenlabs"  every paid ElevenLabs plan grants commercial rights to the
#               audio you generate on it. Needs ELEVENLABS_API_KEY and a voice
#               id: run `python3 build.py --voices` to list them.
# "say"         a macOS system voice. Free and offline, but the macOS licence
#               (SLA 2.F) allows System Voices only for personal,
#               non-commercial use and forbids publishing them, which rules
#               out putting them on a website. Drafting only.
# --------------------------------------------------------------------------
# "google"      Chirp 3: HD. Commercial use under the standard Google Cloud
#               terms, and ~1M HD characters a month are free, which is about
#               thirty times this script.
ENGINE = os.environ.get("TTS_ENGINE", "google")

VOICE = "Jamie (Premium)"        # macOS voice, when ENGINE is "say"
RATE = 168                       # words per minute, when ENGINE is "say"

EL_VOICE = os.environ.get("ELEVENLABS_VOICE_ID", "")
EL_MODEL = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")
EL_FORMAT = "mp3_44100_128"      # 192 needs Creator or above
EL_SPEED = 0.94                  # 1.0 is their default; this is a walking pace
EL_STABILITY = 0.55
EL_SIMILARITY = 0.8
EL_API = "https://api.elevenlabs.io/v1"

GG_VOICE = os.environ.get("GOOGLE_VOICE", "en-GB-Chirp3-HD-Charon")
GG_SPEED = 0.94                  # 1.0 is normal; 0.25 to 2.0 allowed
GG_API = "https://texttospeech.googleapis.com/v1"

AAC_BITRATE = "48000"     # mono speech; 64k is twice what this needs

ALBUM = "Hampstead Heath - a walking gazetteer"
HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO = os.path.join(HERE, "audio")
FULL = os.path.join(HERE, "hampstead-heath-full-walk.m4a")
STAMP = os.path.join(HERE, "voice.json")   # what actually made the audio here

# --------------------------------------------------------------------------
# the narration. body = spoken paragraphs; walk = the "walk on" instruction,
# which is also spoken, because it is the half of the guide that gets you to
# the next place.
# --------------------------------------------------------------------------

STOPS = [
dict(kind="intro", n=None, title="How to use this", where="Introduction", body=[
"Hampstead Heath and its village. A walking gazetteer, in twenty stops.",

"This is a single loop that starts and ends outside Hampstead Underground "
"station, on Heath Street. Something over three hours of walking before you "
"stop for anything at all, and unlike almost every other walk in London, this "
"one has hills in it. It goes through the village first, up to the highest "
"ground in inner London, west to a half-ruined Edwardian pergola, north-east "
"along the top to Kenwood, and then down the east side of the Heath past the "
"swimming ponds and home.",

"Wear shoes you do not mind. Two thirds of this is unpaved, the Heath sits on "
"London clay, and it holds water for days after rain.",

"Fifteen of the twenty stops are free. Three more are free unless you get into "
"the water. Two of them charge at the door.",

"Every track starts with where you should be standing and ends by telling you "
"where to go next. Pause it whenever you want to look at something properly. "
"Nothing here is a race, and the walking times are honest rather than precise.",
], walk=
"So. Stand with your back to the station entrance and look up Heath Street. "
"Stop one is the ground under your feet."),

dict(kind="village", n=1, title="Hampstead Underground Station",
     where="Heath Street", body=[
"Stop one. Hampstead Underground station, which is the deepest hole in London.",

"The platforms are fifty-eight and a half metres beneath the pavement you are "
"standing on. A hundred and ninety-two feet, and the deepest of any station on "
"the network. It has never had an escalator and it never will, because the "
"climb is too steep to build one. The lifts are the deepest on the Underground, "
"and the emergency staircase spiralling around them runs to more than three "
"hundred and twenty steps.",

"The reason is the hill rather than the tunnel. Leslie Green's station opened "
"in nineteen oh seven near the top of a hill of London clay, and the railway "
"underneath had to stay roughly level while the ground above it climbed.",

"Now the better fact, and you cannot see any of it. Half a mile north of here, "
"under the Heath you are about to walk across, there is a station that never "
"opened. North End, or Bull and Bush. The platforms were dug out and then the "
"housing that was meant to fill them was never built, because Henrietta "
"Barnett bought the land above and made sure it stayed empty. Trains pass "
"through the unlit space every few minutes. In the nineteen fifties it was "
"quietly fitted out as a control room for the tunnel floodgates, in case of "
"nuclear attack.",

"Free, unless you go down.",
], walk=
"South down Heath Street, on the right-hand pavement, about two minutes. Church "
"Row opens on your right, and it will stop you where you stand."),

dict(kind="village", n=2, title="Church Row and Saint John-at-Hampstead",
     where="Church Row", body=[
"Stop two. Church Row, and the parish church at the end of it.",

"Walk down the middle of the road and look at both sides at once. This is the "
"oldest complete street in Hampstead, laid out around seventeen twenty, and it "
"is usually called the finest Georgian row in London that is not in a square. "
"What makes it work is the discipline. Same brick, same eaves line, same "
"railings, and no two doorcases quite alike.",

"At the end is Saint John-at-Hampstead. Look at it before you go in, because "
"the tower is at the east end, where the altar is supposed to be. Nobody has "
"ever fully explained why. When the church needed more room in eighteen "
"seventy eight the architect gave up arguing with the tower and turned the "
"inside round instead, which is why you will walk in and find the altar at the "
"wrong end of the building.",

"In the churchyard, in the south-east corner, is John Constable, in a chest "
"tomb of Portland stone with his wife Maria. He lived at forty "
"Well Walk, ten minutes from here, and he is buried within sight of the sky he "
"spent the last years of his life painting over and over again. You will end "
"this walk outside his front door.",

"The extension across the road holds Hugh Gaitskell, who nearly became Prime "
"Minister, the actor Anton Walbrook, and the ashes of Peter Cook.",

"Free, and open most days.",
], walk=
"Out through the top of the churchyard into Holly Walk, which is the narrow "
"lane climbing north between the walls. Keep going up as it becomes Holly Bush "
"Hill and then Hampstead Grove. Four minutes. The tall brown house behind "
"wrought-iron gates on your right is stop three."),

dict(kind="house", n=3, title="Fenton House", where="Hampstead Grove", body=[
"Stop three. Fenton House.",

"Sixteen eighty six, which makes it one of the earliest and largest merchant's "
"houses left in Hampstead, built when this was a hill village a long carriage "
"ride from London. Lady Binning left it to the National Trust in nineteen "
"fifty two with everything still in it.",

"Two reasons to go in. The first is that this is not a silent house. It holds "
"the Benton Fletcher collection of early keyboard instruments, harpsichords "
"and spinets and virginals and clavichords, the earliest of them from fifteen "
"forty, and they are deliberately kept in playing order rather than in "
"retirement. Musicians come and practise on them during opening hours. If you "
"are lucky, and you often are, you will hear the house before you reach the "
"first floor.",

"The second is the garden, which is walled, three hundred years old, and laid "
"out on three levels so you never see all of it at once. The orchard at the "
"bottom grows around thirty heritage varieties of apple and pear that the "
"supermarkets gave up on decades ago, and in autumn you are welcome to pick up "
"the windfalls. Go up onto the balcony for the view south. On a clear day you "
"can see the City from a seventeenth-century roof.",

"National Trust, so there is a charge, and this is one of only two stops on the "
"whole walk that wants money at the door. Generally Wednesday to Sunday in "
"season, and worth checking before you climb the hill.",
], walk=
"Carry on north up Hampstead Grove for one minute. Lower Terrace runs off to "
"the left. At the end of it, behind a gate, on top of what looks like a "
"grass-covered bunker, is stop four."),

dict(kind="high", n=4, title="Hampstead Observatory", where="Lower Terrace", body=[
"Stop four. The Hampstead Observatory.",

"A small white dome on the roof of a Victorian reservoir, at the highest point "
"of the highest hill in inner London. It was built in nineteen ten by the "
"Hampstead Scientific Society, which had been formed eleven years earlier by "
"local people who wanted to look at things, and the Society is still running "
"it now, with volunteers, a hundred and sixteen years later.",

"Inside is a six-inch Cooke refractor from the end of the nineteenth century, "
"lent to the Society in nineteen twenty three by a member and never taken "
"back. It is a beautiful piece of brass engineering and it is still the "
"instrument they use.",

"Here is the part worth writing down. It is open to the public, it is free, "
"and almost nobody in London knows. Friday and Saturday evenings, eight until "
"ten, from the middle of September to the middle of April, plus Sunday "
"mornings to look at the sun through the proper filters. All of that is "
"weather permitting, which in this country is doing a great deal of work.",

"You are two hundred metres from a tube station, looking at Saturn, for "
"nothing, in a shed on a reservoir. That is the single most Hampstead sentence "
"in this guide.",
], walk=
"Back to Hampstead Grove and keep climbing north. Ninety seconds, and the road "
"runs out at a junction with a pond in the middle of it."),

dict(kind="high", n=5, title="Whitestone Pond", where="the top of Heath Street", body=[
"Stop five. Whitestone Pond, and the roof of London.",

"You are standing at a hundred and thirty-four metres above sea level, and "
"there is a flagstaff by the water marking four hundred and forty feet. This "
"is the highest point in London, and here is the honest version of that claim. "
"It is the highest point in inner London, comfortably. It is not the highest "
"point in Greater London, which is Westerham Heights, out on the Kent border "
"in Bromley, and nearly twice as high. Nobody has ever put a flagstaff on that "
"one, because nobody would come.",

"The pond is older than the road. It was the Horse Pond, fed by nothing but "
"rain and dew, and the ramps were cut into it so that carters could drive "
"horses in to drink and wash their hooves at the top of the climb out of "
"London. The white stone that gives it its name is a milestone, still there at "
"the edge, counting the miles back to Holborn.",

"Later it went slightly to its head. Victorian Hampstead called this "
"Hampstead-on-Sea, paddled in it, sailed model boats on it, and skated on it "
"in hard winters.",

"Turn round slowly. On a clear day you can see Harrow on the Hill to the west "
"and the whole eastern skyline of London below you, and you are still standing "
"in a road junction.",

"Free, and there is a bus stop here for anyone who has already had enough.",
], walk=
"West down North End Way, keeping the Heath on your left, for about eight "
"minutes. Watch on the left for Inverforth Close, which is a private-looking "
"turning that is not private. Follow it to the end and go up the steps."),

dict(kind="high", n=6, title="The Hill Garden and Pergola",
     where="Inverforth Close, North End Way", body=[
"Stop six. The Hill Garden, and the Pergola.",

"You have found the raised walkway. Go up and along it slowly, because this is "
"the strangest thing on the Heath and it takes a minute to work out what you "
"are looking at.",

"It belonged to William Hesketh Lever, the soap millionaire who became Lord "
"Leverhulme, and who bought the house here in nineteen oh four. He hired "
"Thomas Mawson, the leading garden designer of the day, and told him he wanted "
"a terrace to entertain on, raised high enough to look out over the Heath "
"rather than up at it.",

"The problem was the material. You cannot raise several acres of ground "
"without an enormous quantity of spoil, and spoil is expensive to buy and "
"ruinous to cart. And then in nineteen oh seven the tube arrived in Hampstead, "
"which meant men digging a tunnel a mile away and no idea what to do with what "
"came out of it. Lever did the deal. The terrace you are walking on is the "
"inside of Hampstead's hill, taken out of the ground to make the Northern "
"line, and stacked up here.",

"He kept extending it until he died in nineteen twenty five, at which point it "
"was about two hundred and thirty metres of colonnade and nobody wanted the "
"upkeep. It went to the public in nineteen sixty three and it has been gently "
"falling apart ever since, which is precisely why it looks like this. Wisteria "
"in the joints, no roof in places, and the best decayed-grandeur photograph in "
"London.",

"Free. Open daily from half past eight until dusk, and it is at its "
"ridiculous best in the first two weeks of June.",
], walk=
"Back out to North End Way and turn left, north-west, for about seven minutes. "
"The gates of Golders Hill Park are on your left, opposite the end of West "
"Heath Avenue."),

dict(kind="high", n=7, title="Golders Hill Park", where="North End Way", body=[
"Stop seven. Golders Hill Park.",

"This is the tidy end of the Heath. Thirty-six acres of Victorian park with "
"mown grass, a bandstand, and a walled flower garden, all of it attached to a "
"wilderness, which is a very odd thing to walk into after the Pergola.",

"There was a mansion here. A bomb removed it during the war and the ruins were "
"cleared afterwards, so the lawn where the house stood is now simply the best "
"place in the park to sit down.",

"What you came for is behind the trees to the north. There is a zoo, it is "
"free, and it is properly good. Ring-tailed lemurs, donkeys, a collection of "
"birds, and a small herd of fallow deer in a paddock that is large enough that "
"you sometimes have to look for them. In summer there is a butterfly house. It "
"is run by the City of London Corporation as part of the Heath, and there is "
"no ticket office, no queue, and no gift shop at the end of it, which by the "
"standards of London zoology is close to miraculous.",

"There is also a decent cafe, and this is the right place on this walk to eat "
"something, because from here on there is nothing until the ponds.",

"Free. Open daily, and the deer are more active in the first hour.",
], walk=
"Out of the gates, turn round, and walk back south-east up North End Way. It "
"is a steady climb of about twelve minutes back to Whitestone Pond. Stop eight "
"is the large white weatherboarded building on the corner as you arrive."),

dict(kind="village", n=8, title="Jack Straw's Castle", where="North End Way", body=[
"Stop eight. Jack Straw's Castle, which is no longer a pub and has not been "
"one since two thousand and two.",

"Stand back and look at it anyway, because for two hundred years this was "
"where London came up the hill to. The name belongs to a leader of the "
"Peasants' Revolt of thirteen eighty one, who is supposed to have addressed a "
"crowd from a hay wagon on this spot. That is a story rather than a record, "
"and it has been attached to the site since at least the seventeenth century.",

"What is documented is the walking. Dickens used this pub as the destination "
"at the end of a good march, and wrote to his friend John Forster proposing "
"exactly that: a brisk walk over Hampstead Heath, and a red-hot chop and a "
"glass of good wine at Jack Straw's Castle at the end of it. Thackeray came. "
"Wilkie Collins came. And Karl Marx, who lived down the hill in Kentish Town, "
"brought his family up here on Sundays for roast veal, beer and donkey rides "
"for the children, which is documented in more detail than most of his "
"economics.",

"The building in front of you is not the one they drank in. That was bombed, "
"and this replacement went up in the early nineteen sixties, in weatherboard, "
"by Raymond Erith, the architect who later rebuilt the inside of Ten Downing "
"Street. It is now flats and a gym, and it is listed, which means the state "
"has protected a nineteen sixties pastiche of an eighteenth-century inn. "
"London does this constantly and it is usually the right answer.",

"Free to look at. Nothing to go into.",
], walk=
"Cross to the Heath side and take the path running east beside Spaniards Road "
"for about two hundred metres. Then bear right, downhill, off the ridge. A "
"narrow lane drops away in front of you into a hollow full of houses. Five "
"minutes."),

dict(kind="village", n=9, title="The Vale of Health", where="off East Heath Road", body=[
"Stop nine. The Vale of Health.",

"A hamlet of about a hundred houses, completely surrounded by open Heath, with "
"one road in and the same road out. There is no through traffic because there "
"is nowhere to go through to.",

"The name is a lie, and a very good one. Until the end of the eighteenth "
"century this hollow was a marsh called Hatchett's Bottom, which was drained "
"in seventeen seventy seven when the water company got to work on the ponds. "
"The first houses went up on the drained ground, somebody needed to sell them, "
"and by eighteen oh one the deeds are calling it the Vale of Health. A malarial "
"bog renamed as a health resort, and it worked so completely that the older "
"name has vanished.",

"Who lived here is out of all proportion to its size. Leigh Hunt took a house "
"in eighteen sixteen and turned it into the meeting place of a generation, "
"which means Keats, Shelley, Byron and Hazlitt all walked down this lane. "
"Rabindranath Tagore stayed here in nineteen twelve, the year the English "
"Gitanjali was being prepared in London, and he had the Nobel Prize within "
"months. D H Lawrence and Frieda lived at number one Byron Villas in nineteen "
"fifteen, the year The Rainbow was prosecuted for obscenity and the unsold "
"copies were burned by order of the court.",

"Behind the houses, if you look, are the caravans and yards of the showmen who "
"run the funfair that still comes onto the Heath on bank holidays. It is the "
"least likely industrial estate in London.",

"Free. It is somebody's street, so read the room.",
], walk=
"Back up the lane the way you came, and rejoin Spaniards Road at the top. Turn "
"right and follow it north-east along the ridge, with the Heath falling away "
"on both sides, for about twelve minutes. The road narrows to a pinch, and the "
"pinch is stop ten."),

dict(kind="village", n=10, title="The Spaniards Inn", where="Spaniards Road", body=[
"Stop ten. The Spaniards Inn, and the toll house that is still in the way.",

"Look at the road before you look at the pub. The little building on the other "
"side is an eighteenth-century toll house, and the gap between the two of them "
"is why every bus, van and lorry on this road has to wait its turn. A tollgate "
"that stopped collecting tolls generations ago is still, physically, taxing "
"your journey.",

"The inn claims fifteen eighty five. What happened here that we can date "
"exactly is the Gordon Riots, in June seventeen eighty. An anti-Catholic mob "
"came up the hill intending to burn down Kenwood, which is ten minutes further "
"along this road and belonged to Lord Mansfield, the Lord Chief Justice, "
"because he was thought to be too soft on Catholics. The landlord opened his "
"cellars to them in the garden. Mansfield's steward, who had run down here in "
"a panic, helped. By the time the cavalry arrived the mob had been drinking "
"free for hours and was in no condition to burn anything. Kenwood is still "
"standing because of a bar bill.",

"It has the literary traffic you would expect. Dickens sends Mrs Bardell and "
"her friends up here in Pickwick Papers, Bram Stoker points at it in Dracula, "
"and it has claimed Dick Turpin for two hundred years, which is romantic and "
"almost certainly untrue.",

"Open as a pub, with a large garden, and it is the last chance for lunch "
"before Kenwood.",
], walk=
"Continue east along Hampstead Lane, past the toll house, for about five "
"minutes. The gate into the Kenwood estate is on your right. Go in and follow "
"the drive until the trees stop."),

dict(kind="house", n=11, title="Kenwood House", where="Hampstead Lane", body=[
"Stop eleven. Kenwood.",

"A white villa at the top of a slope of grass, with a lake below it. Before "
"you go in, look at the little bridge on the lake. It is a fake. There is no "
"bridge, only a painted timber front, put there in the eighteenth century "
"because the view needed one, and it has been fooling people from this exact "
"angle for two hundred years.",

"The house is Robert Adam's, remodelled from seventeen sixty four for William "
"Murray, the first Earl of Mansfield, and the Great Library is the reason "
"architects come. It is a room with a curved and painted ceiling, screens of "
"columns at each end, and pale blue and pink and gilt everywhere. It should be "
"exhausting and instead it is one of the calmest rooms in England.",

"What is hanging on the walls is the real surprise. Edward Cecil Guinness, the "
"first Earl of Iveagh, bought the estate in nineteen twenty five, died two "
"years later, and left the house and sixty-three paintings to the nation on "
"the condition that people could see them for nothing. So there is a Rembrandt "
"self-portrait, late, with two mysterious circles on the wall behind him. "
"There is a Vermeer. There is Gainsborough, Reynolds, Turner and Hals. It is "
"free, it has always been free, and it is never full.",

"One more thing about that Vermeer. In February nineteen seventy four somebody "
"put a sledgehammer through the barred window and took it, and then demanded "
"the transfer of two IRA prisoners as the price of its return. It came back "
"three months later, wrapped in newspaper, propped in a City churchyard. "
"Nobody was ever charged.",

"Free. Open daily, and book ahead if you want to be certain of the house.",
], walk=
"Do not leave yet. Stay inside, find the portrait of two young women in the "
"garden, one of them carrying fruit. Stop twelve is standing in front of it."),

dict(kind="house", n=12, title="Dido Elizabeth Belle", where="inside Kenwood", body=[
"Stop twelve. Dido Elizabeth Belle.",

"She was born in seventeen sixty one, the daughter of Sir John Lindsay, a "
"naval officer and Lord Mansfield's nephew, and an enslaved woman called Maria "
"Belle. She was brought to this house as a small child and she lived in it for "
"about thirty years, raised alongside her cousin Elizabeth Murray, running the "
"dairy and the poultry yard, and helping Mansfield with his correspondence. A "
"visiting American described being unable to make sense of her position at "
"the dinner table, which tells you rather more about him than about her.",

"The portrait shows the two cousins together and gives them equal weight, "
"which for its date is close to unheard of. It was attributed to Zoffany for "
"two centuries and turns out to be by a young Scot called David Martin. The "
"original hangs in Perthshire now, so what you are looking at here is a copy.",

"And then the law. In seventeen seventy two Mansfield decided the Somerset "
"case, in which an enslaved man in England was to be shipped to Jamaica and "
"sold, and he ruled that it could not be done. It is the judgment everybody "
"quotes as the end of slavery in England, and two things about that are worth "
"getting straight while you are standing here.",

"The first is that the famous line, that the air of England is too pure for a "
"slave to breathe in, was not Mansfield's. It was said by James Somerset's "
"barrister, quoting a much older case, and it has been put in the judge's "
"mouth by two hundred years of retelling. The second is that Mansfield's "
"ruling was deliberately narrow. He tried repeatedly to make the parties "
"settle so that he would not have to decide anything at all, and slavery went "
"on being legal in the colonies for another sixty years.",

"He did free Dido in his will, explicitly, and left her money. He knew exactly "
"what he had not done.",
], walk=
"Out of the house by the south front and down across the lawn. Keep the lake "
"on your right, follow the path east out of the estate, and pick up Millfield "
"Lane heading south. Eight minutes. The gate on your right is stop thirteen, "
"and if you are a man you are not going through it."),

dict(kind="water", n=13, title="The Kenwood Ladies' Pond", where="off Millfield Lane", body=[
"Stop thirteen. The Kenwood Ladies' Pond, which opened in nineteen twenty six "
"and is therefore a hundred years old this year.",

"It is the only lifeguarded women-only open-water swimming place in Britain, "
"it is open every single day of the year, and it is spring-fed and unheated, "
"which means about four degrees in February and low twenties in August. Women "
"swim through the winter here in numbers that grow every year.",

"What is behind the hedge is a walled meadow with a concrete jetty, a set of "
"steps into brown water, lifeguards, and a rule against photographs that "
"everybody actually keeps. That last part is the point of it. There is nowhere "
"else within a hundred miles where several hundred women a day undress "
"outdoors, in public, and are neither photographed nor commented on.",

"It has been defended, repeatedly and successfully, by the association of "
"swimmers who use it, ever since the nineteen seventies. When the City of "
"London has proposed changes here, the swimmers have generally won.",

"If you are a woman: pay at the gate, take a towel, and give yourself half an "
"hour. If you are not: the hedge is the answer, and the men's pond is four "
"minutes further on.",

"Small charge to swim, and free to walk past.",
], walk=
"South down Millfield Lane, with the ponds through the trees on your right. "
"Keats met Coleridge in this lane in April eighteen nineteen and walked with "
"him for two miles while Coleridge talked without stopping about nightingales, "
"dreams, mermaids and metaphysics. Keats wrote the whole list down afterwards. "
"Four minutes."),

dict(kind="water", n=14, title="The Highgate Men's Pond", where="Millfield Lane", body=[
"Stop fourteen. The Highgate Men's Pond.",

"Also open every day of the year. Also lifeguarded, also unheated, and rather "
"less discreet than the one you have just walked past: there is a diving "
"board, a concrete deck, and a large meadow beside it where the sunbathing has "
"been famously and legally unclothed for decades.",

"In midwinter, when the water is close to freezing, there is a queue. The men "
"who swim here through January are mostly not athletes, they are simply people "
"who have decided that this is what they do, and the club culture around it "
"goes back well over a century.",

"Three ponds on this Heath are open for swimming and it is worth knowing the "
"difference. The men's pond and the ladies' pond run all year. The mixed pond, "
"further down the other chain, only opens from April to October. All of them "
"are lifeguarded, all of them charge a few pounds, and none of them will let "
"you in when the lifeguards have gone home. That is not bureaucracy. It is "
"cold, deep, dark water with weed in it, and people who have ignored that rule "
"have died in it.",

"Small charge to swim.",
], walk=
"Leave the lane and strike west across the Heath, uphill, away from the water. "
"Aim for the trees on the skyline. Seven minutes, and you are looking for a "
"low round mound inside an iron fence, which is easy to walk straight past."),

dict(kind="high", n=15, title="The Tumulus", where="south of the Highgate Ponds", body=[
"Stop fifteen. The tumulus, which the whole of north London calls Boudica's "
"grave.",

"It is a round mound, about thirty-six metres across and three metres high, "
"ringed with railings and padlocked, with trees growing out of the top of it. "
"It is a scheduled ancient monument, which is the same legal protection given "
"to Stonehenge.",

"The story is that the queen of the Iceni was buried here after her defeat by "
"the Romans in about the year sixty one. It is a wonderful story and there is "
"no evidence for it whatsoever. It seems to have been attached to the mound in "
"the nineteenth century by people who wanted it to be true, which is also how "
"Boudica came to be buried under a platform at King's Cross, in another story "
"that is equally popular and equally baseless.",

"In eighteen ninety four the British Museum sent Charles Hercules Read to dig "
"it, in front of a considerable crowd. He cut into it, found some charcoal, "
"and found nothing else at all. His conclusion was that anything buried here "
"would have dissolved in the acid soil long ago, which is honest, and which "
"settles nothing.",

"So it is probably a Bronze Age burial mound, three and a half thousand years "
"old, sitting between a running track and a swimming pond. Or it is the base "
"of a seventeenth-century windmill, which is the other serious theory and a "
"considerably worse afternoon out.",

"Free, and you cannot go in, and neither can anybody else.",
], walk=
"South-west, up the last of the slope, three minutes, until the ground stops "
"rising and there are benches and a great many people facing the same way."),

dict(kind="high", n=16, title="Parliament Hill", where="Parliament Hill Fields", body=[
"Stop sixteen. Parliament Hill. Ninety-eight metres, and the best free view in "
"London.",

"Take it left to right. Canary Wharf on the far left, then the towers of the "
"City in a clump, then the dome of Saint Paul's sitting low and pale in front "
"of them, then the Shard, and on a good day the transmitter at Crystal Palace "
"on the ridge beyond.",

"Now the thing almost nobody standing here knows. That view is protected by "
"law. Saint Paul's as seen from this hill is a designated Protected Vista, "
"which means that if a developer proposes a tower anywhere in the corridor "
"between you and the cathedral, they must model it from this spot, and if it "
"gets in the way it does not get built. The London skyline has been shaped, "
"repeatedly, by a sightline from a bench on a hill in Camden.",

"The name is unsettled. The likeliest explanation is that Parliamentary troops "
"were stationed up here during the Civil War, guarding the northern approach "
"to London. The better story, which you will be told, is that the Gunpowder "
"plotters came up here to watch Parliament explode. There is no evidence for "
"it and it appears to have been invented in the nineteenth century, along with "
"a good deal else on this hill.",

"It is also called Kite Hill, and on any windy Saturday you will see why.",

"Free, and the first hour after sunrise is the version to see.",
], walk=
"Down the north-west slope, past the running track, and keep going down to the "
"bottom corner of the Heath on Gordon House Road. Eight minutes. Stop "
"seventeen is the long blue rectangle behind the fence."),

dict(kind="water", n=17, title="Parliament Hill Lido", where="Gordon House Road", body=[
"Stop seventeen. Parliament Hill Lido.",

"Sixty metres of unheated open-air water, opened in nineteen thirty eight at "
"the very end of the great age of London lido building, when the London County "
"Council was putting these things up across the city on the theory that "
"working people were entitled to swim outdoors in the sun.",

"Most of them are gone. This one survived, is listed, and was relined in "
"stainless steel, which is why on a bright morning the whole pool looks like "
"mercury and photographs better than anything else on this walk.",

"It is open every day of the year and it is not heated on any of them. In "
"January the water sits around four degrees and there is still a queue at "
"seven in the morning. There is a serious early-swimming culture here that has "
"nothing to do with fitness and everything to do with the twenty minutes "
"afterwards.",

"Charged, cheaper early, and towels are your own problem.",
], walk=
"Back up onto the Heath and head north-east, downhill, to the bottom of the "
"chain of ponds on the Hampstead side, near South End Green. Ten minutes. Walk "
"up the path with the water on your left."),

dict(kind="water", n=18, title="The Hampstead Ponds and the River Fleet",
     where="the Hampstead chain", body=[
"Stop eighteen. The ponds, and the river underneath them.",

"None of these is a lake. Every pond on this Heath is a dammed valley, and the "
"grass bank you are walking along is the dam. The water in them is the River "
"Fleet, which rises in two arms up on this hill, one under this chain and one "
"under the Highgate chain, and which meets itself at Camden Town before "
"running down under Farringdon and out into the Thames at Blackfriars.",

"It was dammed for money. The Hampstead Water Company was incorporated in "
"sixteen ninety two to supply London, and it spent the next century blocking "
"these streams and piping the water down the hill in hollowed elm trunks. The "
"ponds you swim in are a privatised seventeenth-century water utility that "
"nobody ever got round to filling in.",

"Downstream, the Fleet was progressively covered over, turned into a sewer, "
"and forgotten so completely that Fleet Street is named after a river most "
"Londoners assume never existed. It is still down there. In heavy rain you can "
"hear it through the gratings at Ray Street in Clerkenwell.",

"And then the modern argument. Because these are legally reservoirs, and "
"because a dam failure here would send water down into Camden and Kentish "
"Town, the City of London was required to rebuild the dams. It did, between "
"twenty fourteen and twenty sixteen, at enormous cost, against a furious local "
"campaign called Dam Nonsense. The result is the gentle grassy slopes you are "
"standing on, which are engineered spillways pretending to be scenery. They "
"look like they have always been there. That is the whole idea.",

"Free.",
], walk=
"Carry on down to the bottom of the ponds and out onto South End Green. Take "
"Keats Grove, which runs west off it. Three minutes. The white house behind "
"the garden wall on your left is stop nineteen."),

dict(kind="house", n=19, title="Keats House", where="Keats Grove", body=[
"Stop nineteen. Keats House.",

"It was built as a pair of semi-detached houses called Wentworth Place, and it "
"is why you are on this street rather than any other. John Keats moved into "
"one half in December eighteen eighteen, at twenty-three, having just nursed "
"his brother Tom through the tuberculosis that killed him and that was going "
"to kill Keats. The Brawne family moved into the other half. Fanny Brawne was "
"eighteen. They became engaged over the garden wall, more or less literally.",

"What happened next is the most productive year in English poetry. In the "
"spring of eighteen nineteen, in this house and this garden, he wrote Ode to a "
"Nightingale, Ode on a Grecian Urn, Ode on Melancholy and Ode to Psyche, which "
"is most of the work he is remembered for, in about three months. His friend "
"Charles Brown said the nightingale had built a nest in the garden that "
"spring, that Keats took a chair out under the plum tree one morning, and that "
"he came back in with scraps of paper he then pushed behind some books. That "
"is Ode to a Nightingale.",

"He left in September eighteen twenty for the Italian climate, on the advice "
"of doctors who had nothing else to offer. He died in Rome five months later, "
"aged twenty-five, convinced he had failed.",

"The house was nearly demolished in the nineteen twenties and was saved by "
"public subscription, a great deal of it raised in America. The plum tree is a "
"replacement. Everything else is astonishingly quiet.",

"Ticketed, and inexpensive. Generally Wednesday to Friday and Sunday, so check "
"before you come.",
], walk=
"Out of the gate, west along Keats Grove to Downshire Hill, then right into "
"Willow Road. Cross East Heath Road and go up Well Walk. Five minutes. You "
"will pass a small stone drinking fountain on the right, and it is the reason "
"the whole village exists."),

dict(kind="village", n=20, title="Well Walk and Burgh House",
     where="Well Walk and New End Square", body=[
"Stop twenty. Well Walk, the well, and Burgh House.",

"Start at the fountain. That is the chalybeate well, and chalybeate means the "
"water has iron in it. In sixteen ninety eight the young Earl of Gainsborough "
"and his mother gave six acres of ground around these springs to trustees, in "
"perpetuity, for the benefit of the poor of Hampstead. The trust they set up "
"that day still exists and still gives money away in this parish, three "
"hundred and twenty-eight years later.",

"What the trustees did with it in the meantime was open a spa. Hampstead Wells "
"sold the water by the flask in London, built a pump room and assembly rooms, "
"and for about fifty years this village was a resort. It went the way of "
"eighteenth-century resorts: successful, then crowded, then disreputable, then "
"over. The fountain in front of you is a Victorian replacement, and no, do not "
"drink from it.",

"At number forty, further along, John Constable lived from eighteen twenty "
"seven. He painted the sky above this Heath obsessively, in oil, outdoors, "
"dozens and dozens of studies with the weather and the time of day written on "
"the back, decades before anyone thought that was a reasonable way to spend an "
"afternoon. His wife Maria died in that house in eighteen twenty eight. He is "
"buried where you started, at stop two.",

"And on New End Square, thirty seconds away, is Burgh House. Seventeen oh "
"four, Grade One listed, free to walk into, with the Hampstead Museum on the "
"first floor and a decent cafe in the basement that opens onto a garden. In "
"the nineteen thirties it was the home of Rudyard Kipling's daughter, and "
"Kipling's last outing before he died in January nineteen thirty six was to "
"come here and see her.",

"Free. Generally Wednesday to Friday and Sunday, from late morning.",
]),

dict(kind="close", n=None, title="Three ways to walk it",
     where="If you do not have three hours", body=[
"That is the twenty. The station is four minutes away: Flask Walk out of the "
"top of Well Walk, then left up the High Street, and you are back where you "
"started.",

"Three hours is a Saturday, not a Tuesday, so here are three shorter versions "
"that fit a real week.",

"The first: the village hour. About fifty minutes, free, any day, no bookings. "
"Stops one, two, four, five, nine and twenty. Station, Church Row, the "
"observatory, the top of London, down into the Vale of Health and back along "
"Well Walk. No mud, and you can do it in office shoes.",

"The second: the houses. Half a day, Wednesday to Sunday, because that is the "
"one window when all four of them are open. Stops three, eleven, twelve, "
"nineteen and twenty. Fenton House, Kenwood, Keats House and Burgh House. "
"Kenwood and Burgh House are free, Keats is a few pounds, Fenton House is the "
"one that charges properly. Book Kenwood if you want to be sure of the house.",

"The third: the water. Any day of the year, and this is the one to do at seven "
"in the morning. Stops thirteen or fourteen, then seventeen, then eighteen. "
"The ladies' pond and the men's pond are open every day of the year, the mixed "
"pond only from April to October, and the lido never closes. Swim, then walk "
"up the ponds to South End Green for breakfast. It will reorganise your entire "
"opinion of London.",
]),

dict(kind="close", n=None, title="Didn't make twenty", where="The near misses", body=[
"Last track. Eight places cut for distance rather than for quality. All times "
"are walking, from Hampstead station.",

"The Freud Museum, twelve minutes, at twenty Maresfield Gardens. Freud got out "
"of Vienna in nineteen thirty eight and died here the following year, and the "
"consulting room is intact, rugs, antiquities, couch and all. Ticketed, "
"Wednesday to Sunday.",

"Two Willow Road, fifteen minutes, which you walked past between stops "
"nineteen and twenty. Ernő Goldfinger built it for himself in nineteen thirty "
"nine and it is now National Trust. He demolished cottages to do it, which "
"annoyed a neighbour called Ian Fleming so thoroughly that Fleming gave the "
"name to a Bond villain. Goldfinger consulted his lawyers. He did not sue.",

"The Isokon building, twenty minutes, on Lawn Road. Nineteen thirty four, the "
"first modernist block of flats in Britain, built with communal everything and "
"almost no kitchens. Gropius, Breuer and Moholy-Nagy all lived in it, so did "
"Agatha Christie, and so did a working cell of Soviet agents. Small free "
"gallery, weekends in the warmer half of the year.",

"Highgate Cemetery, thirty-five minutes across the Heath. Marx, George Eliot, "
"Douglas Adams, and the Egyptian Avenue. Ticketed, and the west side is the "
"one to book.",

"The Holly Bush, four minutes, up Holly Mount. Gas-lit rooms and no music. "
"Possibly the best pub in this postcode.",

"The Flask at Highgate, thirty minutes, if you have gone to the cemetery "
"anyway. Sixteen sixty three, and a warren.",

"Kentish Town City Farm, twenty-five minutes. Britain's first city farm, "
"nineteen seventy two, and still free.",

"And the Everyman, two minutes from where you started, on Holly Bush Vale. A "
"drill hall, then a theatre, then a cinema from nineteen thirty three, and it "
"is still showing films tonight.",

"Two closing warnings. The opening hours in this guide were checked in August "
"twenty twenty-six and they are the first thing that will change, so confirm "
"before you set out for anything ticketed. And the Heath has no lighting. "
"After dark it is genuinely dark, the paths are not obvious, and the swimming "
"ponds are only open when the lifeguards are there.",

"That is the end of the walk. The station is behind you.",
]),
]

# stops that want money: Fenton House and Keats House at the door, the two
# ponds and the lido only if you get in the water.
PAID = {3, 13, 14, 17, 19}

KIND = {
    "intro":   ("Introduction",   "intro"),
    "village": ("Village",        "village"),
    "high":    ("High ground",    "high"),
    "water":   ("Water",          "water"),
    "house":   ("House & museum", "house"),
    "close":   ("Closing",        "close"),
}

# --------------------------------------------------------------------------
# audio
# --------------------------------------------------------------------------

def slug(text):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


def spoken(stop):
    """Exactly what the voice says, in order."""
    parts = list(stop["body"])
    if stop.get("walk"):
        parts.append(stop["walk"])
    return "\n\n".join(parts)


def key():
    k = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not k:
        sys.exit("Set ELEVENLABS_API_KEY (or TTS_ENGINE=say to draft locally).")
    return k


def el_get(path):
    import urllib.request
    req = urllib.request.Request(EL_API + path, headers={"xi-api-key": key()})
    return json.load(urllib.request.urlopen(req, timeout=60))


def list_voices():
    """Print the voices this account can use, so you can pick one."""
    if ENGINE == "google":
        return gg_voices()
    if ENGINE == "say":
        return subprocess.run(["say", "-v", "?"], check=True) and None
    voices = el_get("/voices").get("voices", [])
    print("%-26s %-24s %s" % ("NAME", "VOICE ID", "LABELS"))
    for v in sorted(voices, key=lambda v: v.get("name", "")):
        lab = v.get("labels") or {}
        bits = " ".join("%s=%s" % (k, lab[k]) for k in
                        ("accent", "gender", "age", "use_case", "description") if lab.get(k))
        print("%-26s %-24s %s" % (v.get("name", "?")[:26], v.get("voice_id", ""), bits[:74]))
    print("\nPick one and: export ELEVENLABS_VOICE_ID=<id>")


def elevenlabs(text, path):
    """One track. Returns MP3, which afconvert turns into the AAC the page
    already expects."""
    import urllib.error
    import urllib.request
    if not EL_VOICE:
        sys.exit("Set ELEVENLABS_VOICE_ID. Run `python3 build.py --voices` to see them.")
    body = json.dumps({
        "text": text,
        "model_id": EL_MODEL,
        "voice_settings": {"stability": EL_STABILITY, "similarity_boost": EL_SIMILARITY,
                           "speed": EL_SPEED, "use_speaker_boost": True},
    }).encode()
    url = "%s/text-to-speech/%s?output_format=%s" % (EL_API, EL_VOICE, EL_FORMAT)
    req = urllib.request.Request(url, data=body, headers={
        "xi-api-key": key(), "content-type": "application/json", "accept": "audio/mpeg"})

    for attempt in range(5):
        try:
            audio = urllib.request.urlopen(req, timeout=300).read()
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf8", "replace")[:300]
            if e.code in (401, 403):
                sys.exit("ElevenLabs rejected the key: %s" % detail)
            if e.code == 422:
                sys.exit("ElevenLabs rejected the request (voice id or model?): %s" % detail)
            if e.code == 429 or e.code >= 500:
                time.sleep(6 * (attempt + 1))
                continue
            sys.exit("ElevenLabs error %d: %s" % (e.code, detail))
    else:
        sys.exit("ElevenLabs kept refusing; try again later.")

    mp3 = path.replace(".m4a", ".mp3")
    open(mp3, "wb").write(audio)
    subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", "-b", AAC_BITRATE, mp3, path],
                   check=True)
    os.remove(mp3)


def gg_call(path_, body=None):
    """Google accepts either an API key on the query string or a bearer token.
    The key is the browser-only setup; the token is what you get from
    `gcloud auth print-access-token` if the key is ever refused."""
    import urllib.error
    import urllib.request
    url = GG_API + path_
    headers = {"content-type": "application/json"}
    apikey = os.environ.get("GOOGLE_API_KEY", "").strip()
    token = os.environ.get("GOOGLE_ACCESS_TOKEN", "").strip()
    if apikey:
        url += ("&" if "?" in url else "?") + "key=" + apikey
    elif token:
        headers["Authorization"] = "Bearer " + token
    else:
        sys.exit("Set GOOGLE_API_KEY (or GOOGLE_ACCESS_TOKEN).")
    project = os.environ.get("GOOGLE_PROJECT", "").strip()
    if project:
        headers["x-goog-user-project"] = project

    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers)
    for attempt in range(5):
        try:
            return json.load(urllib.request.urlopen(req, timeout=300))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf8", "replace")[:400]
            if e.code in (401, 403):
                sys.exit("Google refused the credentials (%d).\n%s\n\n"
                         "Usually: the Text-to-Speech API is not enabled on the project, "
                         "the key is restricted to other APIs, or billing is off." % (e.code, detail))
            if e.code == 400:
                sys.exit("Google rejected the request (voice name or speed?):\n%s" % detail)
            if e.code == 429 or e.code >= 500:
                time.sleep(6 * (attempt + 1))
                continue
            sys.exit("Google error %d: %s" % (e.code, detail))
    sys.exit("Google kept refusing; try again later.")


def gg_voices():
    """The Chirp 3: HD voices available for British English."""
    out = gg_call("/voices?languageCode=en-GB")
    rows = [v for v in out.get("voices", []) if "Chirp3-HD" in v.get("name", "")]
    print("%-34s %s" % ("VOICE NAME", "GENDER"))
    for v in sorted(rows, key=lambda v: v["name"]):
        print("%-34s %s" % (v["name"], v.get("ssmlGender", "")))
    print("\n%d Chirp 3: HD voices. Pick one and: export GOOGLE_VOICE=<name>" % len(rows))
    if not rows:
        print("None came back. Other en-GB voices exist; drop the Chirp3-HD filter to see them.")


def google(text, path):
    import base64
    out = gg_call("/text:synthesize", {
        "input": {"text": text},
        "voice": {"languageCode": "en-GB", "name": GG_VOICE},
        "audioConfig": {"audioEncoding": "MP3", "speakingRate": GG_SPEED,
                        "sampleRateHertz": 44100},
    })
    mp3 = path.replace(".m4a", ".mp3")
    open(mp3, "wb").write(base64.b64decode(out["audioContent"]))
    subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", "-b", AAC_BITRATE, mp3, path],
                   check=True)
    os.remove(mp3)


def say(text, path):
    """macOS. Drafting only: see the licence note at the top of this file."""
    subprocess.run(
        ["say", "-v", VOICE, "-r", str(RATE), "-o", path, "--data-format=aac"],
        input=text, text=True, check=True,
    )


ENGINES = {"google": google, "elevenlabs": elevenlabs, "say": say}


def speak(text, path):
    if ENGINE not in ENGINES:
        sys.exit("TTS_ENGINE must be one of: %s" % ", ".join(sorted(ENGINES)))
    ENGINES[ENGINE](text, path)


def pcm_of(path):
    """The samples out of a RIFF file. afconvert writes WAVE_FORMAT_EXTENSIBLE,
    which the stdlib wave module refuses to open, so walk the chunks."""
    import struct
    raw = open(path, "rb").read()
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        sys.exit("not a WAV: " + path)
    pos = 12
    while pos + 8 <= len(raw):
        cid, size = struct.unpack("<4sI", raw[pos:pos + 8])
        body = raw[pos + 8:pos + 8 + size]
        if cid == b"data":
            return body
        pos += 8 + size + (size & 1)
    sys.exit("no data chunk in " + path)


def write_wav(path, frames, rate=44100, channels=1, width=2):
    import struct
    n = len(frames)
    hdr = (b"RIFF" + struct.pack("<I", 36 + n) + b"WAVEfmt " + struct.pack("<IHHIIHH",
           16, 1, channels, rate, rate * channels * width, channels * width, width * 8)
           + b"data" + struct.pack("<I", n))
    open(path, "wb").write(hdr + frames)


def concat(paths, out):
    """Join the finished tracks into the full walk, rather than paying to
    synthesise the whole script a second time. Decode, splice, encode once."""
    tmp = os.path.join(AUDIO, "_join.wav")
    frames, parts = [], []
    for i, p in enumerate(paths):
        w = os.path.join(AUDIO, "_p%02d.wav" % i)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@44100", "-c", "1", p, w],
                       check=True)
        parts.append(w)
        frames.append(pcm_of(w))
    write_wav(tmp, b"".join(frames))
    subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", "-b", AAC_BITRATE, tmp, out],
                   check=True)
    for p in parts + [tmp]:
        os.remove(p)


def voice_note():
    """What the page should say about the voice. Read from the stamp written
    when the audio was made, so the page describes the audio that is actually
    in the repo rather than whatever the config happens to say today."""
    if os.path.exists(STAMP):
        return json.load(open(STAMP))
    return {"engine": ENGINE, "name": VOICE, "pace": "%d words per minute" % RATE,
            "note": "the British English system voice"}


def cost():
    n = sum(len(spoken(s)) for s in STOPS)
    print("%d characters of narration across %d tracks." % (n, len(STOPS)))
    print("The continuous file is spliced from the finished tracks, not synthesised")
    print("again, so a rebuild costs exactly that once.\n")
    print("  google      Chirp 3: HD is billed per character, but the monthly free")
    print("              allowance is around a million HD characters, roughly %dx this." % (10**6 // n))
    print("  elevenlabs  about %d credits; Starter is 30,000 a month, Creator 100,000." % n)
    print("  say         free, and not licensed for anything you publish.")


def length(path):
    from mutagen.mp4 import MP4
    return MP4(path).info.length


def tag(path, i, stop, art):
    from mutagen.mp4 import MP4, MP4Cover
    m = MP4(path)
    name = stop["title"] if stop["n"] is None else "%d. %s" % (stop["n"], stop["title"])
    m["\xa9nam"] = name
    m["\xa9alb"] = ALBUM
    m["\xa9ART"] = m["aART"] = "Hampstead Heath"
    m["\xa9gen"] = "Spoken"
    m["trkn"] = [(i + 1, len(STOPS))]
    if art:
        m["covr"] = [MP4Cover(art, imageformat=MP4Cover.FORMAT_JPEG)]
    m.save()


def sample(i=4):
    """One track, named after the voice that made it, so you can put two of
    them side by side and actually choose. Track 4 is a good test: 75 seconds,
    a date, a proper noun and a dry last line."""
    stop = STOPS[i]
    voice = {"google": GG_VOICE, "elevenlabs": EL_VOICE or "unset", "say": VOICE}[ENGINE]
    out = os.path.join(HERE, "sample-%s-%s.m4a" % (ENGINE, slug(voice)))
    speak(spoken(stop), out)
    print("  %s  (%.1fs)" % (os.path.basename(out), length(out)))
    print("  open it with:  afplay '%s'" % out)


def build_audio():
    os.makedirs(AUDIO, exist_ok=True)
    art = None
    cover = os.path.join(HERE, "cover.jpg")
    if os.path.exists(cover):
        art = open(cover, "rb").read()

    made = []
    for i, stop in enumerate(STOPS):
        path = os.path.join(AUDIO, "%02d-%s.m4a" % (i, slug(stop["title"])))
        speak(spoken(stop), path)
        tag(path, i, stop, art)
        made.append(path)
        print("  %-46s %5.1fs" % (os.path.basename(path), length(path)))

    print("  ... splicing the whole walk from those tracks")
    concat(made, FULL)
    from mutagen.mp4 import MP4, MP4Cover
    m = MP4(FULL)
    m["\xa9nam"] = "Hampstead Heath - the full walk"
    m["\xa9alb"] = ALBUM
    m["\xa9ART"] = "Hampstead Heath"
    if art:
        m["covr"] = [MP4Cover(art, imageformat=MP4Cover.FORMAT_JPEG)]
    m.save()

    if ENGINE == "google":
        # en-GB-Chirp3-HD-Charon -> Charon
        note = {"engine": "google", "name": GG_VOICE.split("-")[-1], "voice_id": GG_VOICE,
                "pace": "%g of its natural pace" % GG_SPEED,
                "note": "a British English Chirp 3: HD voice from Google Cloud"}
    elif ENGINE == "elevenlabs":
        name = EL_VOICE
        for v in el_get("/voices").get("voices", []):
            if v.get("voice_id") == EL_VOICE:
                name = v.get("name", EL_VOICE)
                break
        note = {"engine": "elevenlabs", "name": name, "voice_id": EL_VOICE, "model": EL_MODEL,
                "pace": "%g of its natural pace" % EL_SPEED,
                "note": "an ElevenLabs voice, licensed for commercial use"}
    else:
        note = {"engine": "say", "name": VOICE, "pace": "%d words per minute" % RATE,
                "note": "the British English system voice"}
    json.dump(note, open(STAMP, "w"), indent=1)


# --------------------------------------------------------------------------
# the page
# --------------------------------------------------------------------------

def esc(text):
    return _html.escape(text, quote=False).encode("ascii", "xmlcharrefreplace").decode()


def clock(seconds):
    seconds = int(round(seconds))
    return "%d:%02d" % (seconds // 60, seconds % 60)


CSS = """
:root{
  --paper:#EFEDE5; --paper-2:#F7F6F0; --plate:#E8E6DD;
  --ink:#181D16; --ink-2:#525C4C; --ink-3:#7C8676;
  --rule:#C7CBBC; --rule-soft:#DDE0D2;
  --heath:#2C6B45; --water:#2A6A8E; --contour:#96591C; --brick:#94413A;
  --font-display:"Big Caslon","Baskerville","Hoefler Text","Palatino Linotype",Palatino,Georgia,serif;
  --font-body:Charter,"Bitstream Charter","Iowan Old Style",Georgia,"Times New Roman",serif;
  --font-label:Copperplate,"Copperplate Gothic Light",Optima,"Gill Sans","Trebuchet MS",sans-serif;
  --font-data:"SF Mono",Menlo,Consolas,ui-monospace,monospace;
}
@media (prefers-color-scheme:dark){:root{
  --paper:#0F1310; --paper-2:#171C16; --plate:#131813;
  --ink:#E4E8DF; --ink-2:#9AA495; --ink-3:#727C6E;
  --rule:#2A322A; --rule-soft:#1D231D;
  --heath:#67C08D; --water:#6FB2D6; --contour:#D3A257; --brick:#DC8579;
}}
:root[data-theme="dark"]{
  --paper:#0F1310; --paper-2:#171C16; --plate:#131813;
  --ink:#E4E8DF; --ink-2:#9AA495; --ink-3:#727C6E;
  --rule:#2A322A; --rule-soft:#1D231D;
  --heath:#67C08D; --water:#6FB2D6; --contour:#D3A257; --brick:#DC8579;
}
:root[data-theme="light"]{
  --paper:#EFEDE5; --paper-2:#F7F6F0; --plate:#E8E6DD;
  --ink:#181D16; --ink-2:#525C4C; --ink-3:#7C8676;
  --rule:#C7CBBC; --rule-soft:#DDE0D2;
  --heath:#2C6B45; --water:#2A6A8E; --contour:#96591C; --brick:#94413A;
}

*{box-sizing:border-box}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:var(--font-body); font-size:15px; line-height:1.62;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:940px; margin:0 auto; padding:0 clamp(16px,4vw,40px) 96px}
a{color:var(--heath); text-underline-offset:2px; text-decoration-thickness:from-font}
a:focus-visible{outline:2px solid var(--heath); outline-offset:2px}
.lab{
  font-family:var(--font-label); text-transform:uppercase;
  letter-spacing:.14em; font-size:11px; line-height:1.4; color:var(--ink-3);
  margin:0;
}

/* ---- masthead ---------------------------------------------------- */
header.cart{padding:clamp(38px,6vw,72px) 0 clamp(24px,3vw,34px)}
.cart-inner{
  border-top:2px solid var(--ink); border-bottom:1px solid var(--rule);
  padding:clamp(20px,3vw,32px) 0 clamp(18px,2.5vw,28px);
  display:grid; grid-template-columns:1fr auto; gap:clamp(20px,4vw,52px); align-items:start;
}
@media (max-width:700px){.cart-inner{grid-template-columns:1fr} .hilldev{width:86px}}
.cart h1{
  font-family:var(--font-display); font-weight:400;
  font-size:clamp(2rem,5.6vw,3.15rem); line-height:1.03; letter-spacing:-.015em;
  margin:.3em 0 0; text-wrap:balance;
}
.cart h1 em{font-style:italic; color:var(--heath)}
.lede{margin:.8em 0 0; max-width:58ch; font-size:clamp(1rem,1.6vw,1.0625rem); color:var(--ink-2)}
.lede b{color:var(--ink); font-weight:600}
.hilldev{width:clamp(92px,12vw,132px); height:auto; flex:none; color:var(--ink-3)}

.stats{
  list-style:none; margin:clamp(18px,2.6vw,28px) 0 0; padding:0;
  display:grid; grid-template-columns:repeat(5,minmax(0,1fr));
  gap:1px; background:var(--rule-soft); border:1px solid var(--rule-soft);
}
/* 5 stats never divide evenly below 5 columns; let the last one take up the slack */
@media (max-width:860px){
  .stats{grid-template-columns:repeat(3,minmax(0,1fr))}
  .stats li:last-child{grid-column:span 2}
}
@media (max-width:470px){
  .stats{grid-template-columns:repeat(2,minmax(0,1fr))}
  .stats li:last-child{grid-column:span 2}
}
.stats li{background:var(--paper); padding:12px 14px 13px}
.stats .n{
  font-family:var(--font-label); font-size:1.4rem; line-height:1; display:block;
  margin-bottom:8px; font-variant-numeric:tabular-nums;
}
.stats .n small{font-size:.6em; color:var(--ink-3); letter-spacing:.06em}

/* ---- section furniture ------------------------------------------- */
section.blk{margin-top:clamp(42px,6vw,72px)}
section.blk > h2{
  font-family:var(--font-display); font-weight:400; font-size:clamp(1.45rem,3vw,1.95rem);
  margin:0; border-bottom:2px solid var(--ink); padding-bottom:9px;
  display:flex; justify-content:space-between; align-items:baseline; gap:16px;
}
section.blk > h2 span{font-family:var(--font-label); text-transform:uppercase;
  letter-spacing:.13em; font-size:11px; color:var(--ink-3)}
.blk-sub{margin:13px 0 0; color:var(--ink-2); max-width:62ch}

/* ---- the tape: contents ------------------------------------------ */
.tape{margin:20px 0 0; border-top:1px solid var(--rule-soft)}
.row{
  display:grid; grid-template-columns:3.2ch minmax(0,1fr) 76px 5ch 5.5ch;
  gap:0 14px; align-items:center; color:inherit;
  padding:8px 6px 8px 0; border-bottom:1px solid var(--rule-soft);
}
/* the hosted build inserts a play button ahead of the track number */
.tape.audio .row{grid-template-columns:auto 3.2ch minmax(0,1fr) 76px 5ch 5.5ch}
.row:hover{background:var(--paper-2)}
.rn{font-family:var(--font-data); font-size:11px; color:var(--ink-3); font-variant-numeric:tabular-nums}
.rt{font-family:var(--font-display); font-size:1.02rem; line-height:1.25;
    text-decoration:none; color:inherit;
    overflow:hidden; text-overflow:ellipsis; white-space:nowrap}
.rt:hover{text-decoration:underline; text-decoration-color:var(--rule); text-underline-offset:3px}
.rt:focus-visible{outline:2px solid var(--heath); outline-offset:2px}
.sn{font-family:var(--font-data); font-size:.74em; color:var(--ink-3);
    font-variant-numeric:tabular-nums; display:inline-block; width:2.2ch;
    text-align:right; margin-right:.7em}
.row.village .sn{color:var(--heath)}
.row.high .sn{color:var(--contour)}
.row.water .sn{color:var(--water)}
.row.house .sn{color:var(--brick)}
.rbar{display:block; height:3px; background:var(--rule-soft)}
.rbar i{display:block; height:100%; background:var(--ink-3)}
.row.village .rbar i{background:var(--heath)}
.row.high .rbar i{background:var(--contour)}
.row.water .rbar i{background:var(--water)}
.row.house .rbar i{background:var(--brick)}
.rd,.rc{font-family:var(--font-data); font-size:11px; font-variant-numeric:tabular-nums; text-align:right}
.rd{color:var(--ink-2)} .rc{color:var(--ink-3)}
.tape-key{display:flex; justify-content:space-between; gap:14px; margin:9px 2px 0}
@media (max-width:620px){
  .row{grid-template-columns:3.2ch minmax(0,1fr) 5ch; gap:0 12px}
  .tape.audio .row{grid-template-columns:auto 3.2ch minmax(0,1fr) 5ch}
  .rbar,.rc{display:none}
  .tape-key{display:grid; gap:4px}
  .trk{gap:0 15px}
}

/* ---- transcript --------------------------------------------------- */
.trk{
  display:grid; grid-template-columns:auto minmax(0,1fr); gap:0 22px;
  padding:30px 0 32px; border-bottom:1px solid var(--rule-soft); scroll-margin-top:18px;
}
.tmark{padding-top:6px}
.tn{
  font-family:var(--font-label); font-size:1rem; font-weight:700;
  width:34px; height:34px; border-radius:50%; display:grid; place-items:center;
  color:var(--paper); background:var(--ink-3); font-variant-numeric:tabular-nums;
}
.trk.village .tn{background:var(--heath)}
.trk.high .tn{background:var(--contour)}
.trk.water .tn{background:var(--water)}
.trk.house .tn{background:var(--brick)}
.tn.sym{background:transparent; color:var(--ink-3); border:1px solid var(--rule); font-size:1.3rem}
.trk h3{
  font-family:var(--font-display); font-weight:400; font-size:1.5rem; line-height:1.16;
  margin:7px 0 0; letter-spacing:-.005em; text-wrap:balance;
}
.trk .sub{font-family:var(--font-data); font-size:11px; color:var(--ink-3); margin:6px 0 0}
.tbody p{margin:1.05em 0 0; max-width:64ch}
.tbody p:first-child{margin-top:0}
.eyebrow{font-variant-numeric:tabular-nums}

/* ---- the map ------------------------------------------------------ */
.mapwrap{margin:22px 0 0}
.mapbox{position:relative; border:1px solid var(--rule-soft); background:var(--paper-2)}
/* pan-y, not none: one finger must still scroll the page past the map */
#mp{display:block; width:100%; height:auto; touch-action:pan-y; cursor:grab}
#mp.drag{cursor:grabbing}
.mheath{fill:var(--heath); fill-opacity:.10; stroke:var(--heath); stroke-opacity:.45; stroke-width:1.6}
.mwater{fill:var(--water); fill-opacity:.30; stroke:var(--water); stroke-opacity:.5; stroke-width:1}
.mroad{fill:none; stroke:var(--ink-3); stroke-opacity:.45; stroke-width:1.6; stroke-linecap:round}
.mroute{fill:none; stroke:var(--ink-2); stroke-opacity:.65; stroke-width:2.4;
        stroke-dasharray:2 9; stroke-linecap:round; stroke-linejoin:round}
.mstop{cursor:pointer}
.mhit{fill:transparent}
.mdot{fill:var(--ink-3); stroke:var(--paper); stroke-width:2.5}
.mstop.village .mdot{fill:var(--heath)} .mstop.high .mdot{fill:var(--contour)}
.mstop.water .mdot{fill:var(--water)}   .mstop.house .mdot{fill:var(--brick)}
.mnum{font-family:var(--font-label); font-size:15px; text-anchor:middle;
      fill:var(--paper); font-weight:700; pointer-events:none}
.mstop:hover .mdot,.mstop:focus .mdot{stroke:var(--ink)}
.mstop:focus{outline:none}
.mstop:focus-visible .mdot{stroke:var(--ink); stroke-width:4}
.mstop.on .mdot{stroke:var(--ink); stroke-width:4}
.mdotme{fill:var(--slate,#37608A); stroke:var(--paper); stroke-width:3}
.macc{fill:var(--water); fill-opacity:.18; stroke:var(--water); stroke-opacity:.5}
.mapctl{
  position:absolute; right:8px; top:8px; display:flex; flex-direction:column; gap:6px;
  align-items:stretch;
}
.mapctl button{
  all:unset; cursor:pointer; text-align:center; box-sizing:border-box;
  min-width:36px; min-height:36px; line-height:34px; padding:0 9px;
  background:var(--paper); border:1px solid var(--rule); color:var(--ink-2);
  font-family:var(--font-label); text-transform:uppercase; letter-spacing:.1em; font-size:10.5px;
}
.mapctl button:hover{color:var(--ink); border-color:var(--ink-2)}
.mapctl button:focus-visible{outline:2px solid var(--heath); outline-offset:2px}
/* a caption is a sentence, not a label: no shouting */
#mcap{margin:9px 2px 0; font-size:.84rem; line-height:1.5; color:var(--ink-3); max-width:70ch}
#mcap a{color:inherit}
.mapkey{display:flex; flex-wrap:wrap; gap:4px 18px; margin:10px 2px 0}
.mapkey span{display:inline-flex; align-items:center; gap:7px}
.mapkey i{width:10px; height:10px; border-radius:50%; display:inline-block}

/* ---- one photograph per track ------------------------------------- */
.shot{margin:18px 0 0; max-width:62ch}
.shot img{
  display:block; width:100%; height:auto;
  border:1px solid var(--rule-soft); background:var(--plate);
}
.shot figcaption{margin:8px 0 0; color:var(--ink-3)}
.shot figcaption a{color:inherit; text-decoration-color:var(--rule)}
.shot figcaption a:hover{color:var(--ink-2)}
/* photographs shot in daylight glare on a dark page */
@media (prefers-color-scheme:dark){.shot img{filter:brightness(.86) contrast(1.03)}}
:root[data-theme="dark"] .shot img{filter:brightness(.86) contrast(1.03)}
:root[data-theme="light"] .shot img{filter:none}

/* the one device this page adds: standing still vs moving */
.walk{
  margin:20px 0 0; padding:11px 0 12px 16px; border-left:2px solid var(--heath);
  display:grid; gap:5px; max-width:62ch;
}
.walk .lab{color:var(--heath)}
.walk p{margin:0; font-size:.94rem; color:var(--ink-2); max-width:none}

/* ---- colophon ------------------------------------------------------ */
.colo{display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:1px;
  background:var(--rule-soft); border:1px solid var(--rule-soft); margin-top:22px}
.colo div{background:var(--paper); padding:17px 18px 19px; display:grid; gap:7px; align-content:start}
.colo p{margin:0; font-size:.9rem; color:var(--ink-2)}
.colo code{font-family:var(--font-data); font-size:.82em; color:var(--ink)}

footer{margin-top:clamp(42px,6vw,68px); padding-top:20px; border-top:1px solid var(--rule);
  color:var(--ink-3); font-size:.85rem}
footer p{margin:0 0 8px; max-width:70ch}

@media (prefers-reduced-motion:reduce){*{transition:none !important; animation:none !important}}

/* ---- phones -------------------------------------------------------- */
@media (max-width:700px){
  body{font-size:16px; line-height:1.6}
  .wrap{padding-bottom:72px}
  /* titles matter more than a tidy single line on a narrow screen */
  .row{padding:11px 4px 11px 0; align-items:start}
  .rt{white-space:normal; overflow:visible; text-overflow:clip; line-height:1.3}
  .rn,.rd{padding-top:2px}
  /* .pb is sized in the player stylesheet, which loads after this one */
  .trk{gap:0 14px; padding:26px 0 28px}
  .tn{width:30px; height:30px; font-size:.95rem}
  .tbody p,.shot,.walk,.play{max-width:none}
  .colo div{padding:15px 16px 17px}
  .bar{padding:8px 12px; padding-bottom:calc(8px + env(safe-area-inset-bottom))}
  .bseek::-webkit-slider-thumb{width:16px; height:16px}
  .bseek::-moz-range-thumb{width:16px; height:16px}
  /* controls under the map rather than over it: the map is small enough */
  .mapctl{
    position:static; flex-direction:row; gap:0; justify-content:flex-end;
    border-top:1px solid var(--rule-soft);
  }
  .mapctl button{border:0; border-left:1px solid var(--rule-soft); min-height:42px; line-height:42px}
  .mapctl button:first-child{border-left:0}
  .mapctl #mlocate{flex:1}   /* fills the row rather than leaving a gap */
}
@media (max-width:430px){
  .cart h1{font-size:2rem}
  .stats li{padding:11px 12px 12px}
  .stats .n{font-size:1.25rem}
  section.blk > h2 span{display:none}   /* the eyebrow crowds the heading */
}
@media (hover:none){
  .rt{padding:2px 0}
}
"""

PLAYER_CSS = """
/* one shared audio element drives every control on the page */
.pb{
  all:unset; box-sizing:border-box; cursor:pointer; flex:none;
  width:22px; height:22px; border:1px solid var(--rule); border-radius:50%;
  display:grid; place-items:center; color:var(--ink-2);
  transition:border-color .14s, color .14s, background .14s;
}
.pb::before{
  content:""; width:0; height:0; margin-left:2px;
  border-left:6px solid currentColor; border-top:4px solid transparent;
  border-bottom:4px solid transparent;
}
.pb:hover{border-color:var(--ink); color:var(--ink); background:var(--paper-2)}
.pb:focus-visible{outline:2px solid var(--heath); outline-offset:2px}
.row.on .pb,.pb.on{border-color:var(--heath); color:var(--heath)}
.pb.on::before{
  margin-left:0; width:7px; height:8px; border:0;
  background:linear-gradient(to right,currentColor 0 2.5px,transparent 2.5px 4.5px,currentColor 4.5px 7px);
}
.row.on .rt{color:var(--heath)}

/* the big control inside each transcript entry */
.play{
  display:flex; align-items:center; gap:11px; margin:14px 0 0;
  border:0; background:none; padding:0; width:100%; max-width:62ch;
}
.play .pb{width:34px; height:34px; border-width:1.5px}
.play .pb::before{border-left-width:9px; border-top-width:6px; border-bottom-width:6px; margin-left:3px}
.play .pb.on::before{width:10px; height:12px;
  background:linear-gradient(to right,currentColor 0 3.5px,transparent 3.5px 6.5px,currentColor 6.5px 10px)}
.play .plab{font-family:var(--font-label); text-transform:uppercase; letter-spacing:.13em;
  font-size:10.5px; color:var(--ink-3); flex:none}
.pgs{flex:1; height:2px; background:var(--rule-soft); min-width:40px}
.pgs i{display:block; height:100%; width:0; background:var(--heath)}
.play .ptime{font-family:var(--font-data); font-size:11px; color:var(--ink-3);
  font-variant-numeric:tabular-nums; flex:none}

/* sticky transport */
.bar{
  position:fixed; left:0; right:0; bottom:0; z-index:40;
  background:var(--paper-2); border-top:1px solid var(--ink);
  box-shadow:0 -6px 24px -14px rgba(0,0,0,.4);
  display:grid; grid-template-columns:auto auto auto minmax(0,1fr) auto;
  align-items:center; gap:0 12px; padding:9px clamp(12px,3vw,22px);
  padding-bottom:calc(9px + env(safe-area-inset-bottom));
}
.bar[hidden]{display:none}
.bar button{
  all:unset; cursor:pointer; color:var(--ink-2); display:grid; place-items:center;
  width:30px; height:30px; font-family:var(--font-data); font-size:15px;
}
.bar button:hover{color:var(--ink)}
.bar button:focus-visible{outline:2px solid var(--heath); outline-offset:1px}
.bar #bplay{color:var(--ink); font-size:17px}
.bmeta{display:grid; gap:3px; min-width:0}
.bmeta .bt{font-family:var(--font-display); font-size:.95rem; line-height:1.2;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis}
.brow{display:flex; align-items:center; gap:9px}
.bseek{
  -webkit-appearance:none; appearance:none; flex:1; height:3px; min-width:0;
  background:var(--rule-soft); cursor:pointer;
}
.bseek::-webkit-slider-thumb{-webkit-appearance:none; width:11px; height:11px;
  border-radius:50%; background:var(--heath)}
.bseek::-moz-range-thumb{width:11px; height:11px; border:0; border-radius:50%; background:var(--heath)}
.bseek:focus-visible{outline:2px solid var(--heath); outline-offset:3px}
.btime{font-family:var(--font-data); font-size:10.5px; color:var(--ink-3);
  font-variant-numeric:tabular-nums; flex:none}
body.playing{padding-bottom:76px}
@media (max-width:560px){
  .bar{grid-template-columns:auto auto minmax(0,1fr) auto; gap:0 8px}
  .bar #bprev{display:none}
}

/* thumbs, not cursors. These live here, after the .pb{all:unset} above, or
   they lose to it on source order and quietly do nothing. */
@media (max-width:700px){
  .pb{width:30px; height:30px}
  .pb::before{border-left-width:8px; border-top-width:5.5px; border-bottom-width:5.5px}
  .pb.on::before{width:9px; height:11px;
    background:linear-gradient(to right,currentColor 0 3px,transparent 3px 6px,currentColor 6px 9px)}
}
@media (hover:none){
  .pb{position:relative}
  .pb::after{content:""; position:absolute; inset:-8px; border-radius:50%}
}
"""

PLAYER_JS = r"""
(function(){
  "use strict";
  var T = __TRACKS__, cur = -1, mapPaint = null;
  var A = new Audio();
  A.preload = "none";                     // nothing downloads until you press play

  var bar   = document.getElementById("bar"),
      bplay = document.getElementById("bplay"),
      btitle= document.getElementById("btitle"),
      bseek = document.getElementById("bseek"),
      btime = document.getElementById("btime");

  function ms(s){
    if(!isFinite(s) || s < 0) s = 0;
    return Math.floor(s/60) + ":" + ("0" + Math.floor(s%60)).slice(-2);
  }
  function ctrls(i){
    return document.querySelectorAll('[data-i="' + i + '"]');
  }
  function paint(){
    document.querySelectorAll(".pb").forEach(function(b){ b.classList.remove("on"); });
    document.querySelectorAll(".row").forEach(function(r){ r.classList.remove("on"); });
    if(cur < 0) return;
    var live = !A.paused;
    ctrls(cur).forEach(function(el){
      if(el.classList.contains("row")) el.classList.add("on");
      el.querySelectorAll(".pb").forEach(function(b){
        if(live) b.classList.add("on");
        b.setAttribute("aria-label", (live ? "Pause " : "Play ") + T[cur].t);
      });
    });
    bplay.innerHTML = live ? "&#10073;&#10073;" : "&#9654;";
    bplay.setAttribute("aria-label", live ? "Pause" : "Play");
    if(mapPaint) mapPaint(cur);
  }
  function progress(){
    var d = A.duration || T[cur] && T[cur].d || 0,
        p = d ? A.currentTime / d : 0;
    ctrls(cur).forEach(function(el){
      el.querySelectorAll(".pgs i").forEach(function(i){ i.style.width = (p*100) + "%"; });
    });
    bseek.value = Math.round(p * 1000);
    btime.textContent = ms(A.currentTime) + " / " + ms(d);
  }
  function load(i){
    cur = i;
    A.src = T[i].f;
    btitle.textContent = T[i].t;
    bar.hidden = false;
    document.body.classList.add("playing");
  }
  function toggle(i){
    if(i === cur){
      if(A.paused) A.play(); else A.pause();
      return;
    }
    document.querySelectorAll(".pgs i").forEach(function(x){ x.style.width = 0; });
    load(i);
    A.play();
  }
  function step(d){
    var i = cur + d;
    if(i >= 0 && i < T.length){ toggle(i); }
  }

  document.addEventListener("click", function(e){
    var b = e.target.closest(".pb");
    if(!b) return;
    e.preventDefault();
    toggle(+b.closest("[data-i]").dataset.i);
  });

  bplay.addEventListener("click", function(){ if(cur >= 0) toggle(cur); });
  document.getElementById("bnext").addEventListener("click", function(){ step(1); });
  document.getElementById("bprev").addEventListener("click", function(){ step(-1); });
  document.getElementById("bstop").addEventListener("click", function(){
    A.pause(); A.currentTime = 0; bar.hidden = true;
    document.body.classList.remove("playing");
    document.querySelectorAll(".pgs i").forEach(function(x){ x.style.width = 0; });
    cur = -1; paint();
  });
  bseek.addEventListener("input", function(){
    var d = A.duration || 0;
    if(d) A.currentTime = d * (bseek.value / 1000);
  });

  A.addEventListener("play", paint);
  A.addEventListener("pause", paint);
  A.addEventListener("timeupdate", progress);
  A.addEventListener("loadedmetadata", progress);
  /* deliberately no auto-advance: between stops you are walking, not listening */
  A.addEventListener("ended", function(){ paint(); });
  A.addEventListener("error", function(){
    btitle.textContent = "Could not load that track - check your connection";
  });

  /* ---- the map ----------------------------------------------------- */
  (function(){
    var svg = document.getElementById("mp");
    if(!svg) return;
    var vb0 = svg.getAttribute("viewBox").split(/\s+/).map(Number),
        vb  = vb0.slice(),
        cap = document.getElementById("mcap"),
        capText = cap ? cap.innerHTML : "",
        me  = document.getElementById("mme");

    function apply(){
      svg.setAttribute("viewBox", vb.join(" "));
      /* markers keep their size on screen however far you have zoomed in */
      var k = vb[2] / vb0[2];
      svg.querySelectorAll(".mdot").forEach(function(c){ c.setAttribute("r", 14 * k); });
      svg.querySelectorAll(".mhit").forEach(function(c){ c.setAttribute("r", 36 * k); });
      svg.querySelectorAll(".mnum").forEach(function(t){
        t.style.fontSize = (15 * k) + "px"; t.setAttribute("y", 5 * k);
      });
      svg.querySelectorAll(".mdot,.mdotme").forEach(function(c){
        c.style.strokeWidth = (2.5 * k) + "px";
      });
      svg.querySelector(".mroute").style.strokeWidth = (2.4 * k) + "px";
      svg.querySelector(".mroute").style.strokeDasharray = (2*k) + " " + (9*k);
      svg.querySelector(".mroad").style.strokeWidth = (1.6 * k) + "px";
    }
    function zoom(factor, cx, cy){
      var w = Math.min(vb0[2], Math.max(vb0[2] / 14, vb[2] * factor)),
          h = w * vb0[3] / vb0[2];
      if(cx === undefined){ cx = vb[0] + vb[2]/2; cy = vb[1] + vb[3]/2; }
      vb = [cx - (cx - vb[0]) * w / vb[2], cy - (cy - vb[1]) * h / vb[3], w, h];
      clamp(); apply();
    }
    function clamp(){
      vb[0] = Math.max(vb0[0] - vb[2]*.15, Math.min(vb[0], vb0[2] - vb[2] + vb[2]*.15));
      vb[1] = Math.max(vb0[1] - vb[3]*.15, Math.min(vb[1], vb0[3] - vb[3] + vb[3]*.15));
    }
    function at(e){
      var r = svg.getBoundingClientRect();
      return [vb[0] + (e.clientX - r.left) / r.width * vb[2],
              vb[1] + (e.clientY - r.top) / r.height * vb[3]];
    }

    document.querySelectorAll(".mapctl [data-z]").forEach(function(b){
      b.addEventListener("click", function(){
        var z = b.dataset.z;
        if(z === "fit"){ vb = vb0.slice(); apply(); }
        else zoom(z === "in" ? 1/1.6 : 1.6);
      });
    });
    svg.addEventListener("wheel", function(e){
      e.preventDefault();
      var p = at(e);
      zoom(e.deltaY > 0 ? 1.15 : 1/1.15, p[0], p[1]);
    }, {passive:false});

    /* drag to pan, one finger or a mouse; pinch with two */
    var pts = new Map(), last = null, spread = 0, moved = 0, hinted = false;
    svg.addEventListener("pointerdown", function(e){
      svg.setPointerCapture(e.pointerId);
      pts.set(e.pointerId, e); last = at(e); moved = 0;
      if(pts.size === 2) spread = 0;
      svg.classList.add("drag");
    });
    svg.addEventListener("pointermove", function(e){
      if(!pts.has(e.pointerId)) return;
      pts.set(e.pointerId, e);
      /* one finger scrolls the page, two move the map. Trapping the scroll
         under a full-width map is the usual sin of embedded maps. */
      if(e.pointerType === "touch" && pts.size < 2){
        if(cap && !hinted){ hinted = true; cap.textContent = "Two fingers to move the map.";
          setTimeout(function(){ cap.innerHTML = capText; hinted = false; }, 2200); }
        return;
      }
      if(pts.size >= 2){
        var a = [...pts.values()], d = Math.hypot(
          a[0].clientX - a[1].clientX, a[0].clientY - a[1].clientY);
        if(spread) zoom(spread / d, vb[0] + vb[2]/2, vb[1] + vb[3]/2);
        spread = d; return;
      }
      var p = at(e);
      vb[0] -= p[0] - last[0]; vb[1] -= p[1] - last[1];
      moved += Math.abs(p[0]-last[0]) + Math.abs(p[1]-last[1]);
      clamp(); apply(); last = at(e);
    });
    ["pointerup","pointercancel","pointerleave"].forEach(function(ev){
      svg.addEventListener(ev, function(e){
        pts.delete(e.pointerId); spread = 0;
        if(!pts.size) svg.classList.remove("drag");
      });
    });

    function go(g){
      var i = +g.dataset.i;
      var art = document.getElementById("t" + ("0" + i).slice(-2));
      if(art) art.scrollIntoView({behavior:"smooth", block:"start"});
      toggle(i);
    }
    svg.querySelectorAll(".mstop").forEach(function(g){
      g.addEventListener("click", function(){ if(moved < 8) go(g); });
      g.addEventListener("keydown", function(e){
        if(e.key === "Enter" || e.key === " "){ e.preventDefault(); go(g); }
      });
      g.addEventListener("pointerenter", function(){
        if(cap) cap.textContent = g.getAttribute("aria-label").replace(
          ". Play it and jump to the transcript.", "");
      });
      g.addEventListener("pointerleave", function(){ if(cap) cap.innerHTML = capText; });
    });

    /* the map follows the player */
    mapPaint = function(i){
      svg.querySelectorAll(".mstop").forEach(function(g){
        g.classList.toggle("on", +g.dataset.i === i);
      });
    };

    /* where am I: the browser's own geolocation, nothing sent anywhere */
    var btn = document.getElementById("mlocate"), watch = null, bb = __MAPBBOX__;
    btn.addEventListener("click", function(){
      if(!navigator.geolocation){ cap.textContent = "This browser will not share a location."; return; }
      if(watch !== null){
        navigator.geolocation.clearWatch(watch); watch = null;
        me.hidden = true; btn.textContent = "Where am I"; cap.innerHTML = capText; return;
      }
      btn.textContent = "Finding...";
      watch = navigator.geolocation.watchPosition(function(pos){
        var la = pos.coords.latitude, lo = pos.coords.longitude;
        var x = (lo - bb[1]) / (bb[3] - bb[1]) * vb0[2],
            y = (bb[2] - la) / (bb[2] - bb[0]) * vb0[3];
        btn.textContent = "Hide me";
        if(x < 0 || y < 0 || x > vb0[2] || y > vb0[3]){
          me.hidden = true;
          cap.textContent = "You are outside this map. It only covers the Heath and the village.";
          return;
        }
        me.hidden = false;
        cap.innerHTML = capText;
        me.setAttribute("transform", "translate(" + x.toFixed(1) + " " + y.toFixed(1) + ")");
        var mpp = (bb[3] - bb[1]) * 111320 * Math.cos(bb[0] * Math.PI/180) / vb0[2];
        me.querySelector(".macc").setAttribute("r", Math.min(400, (pos.coords.accuracy||30) / mpp));
      }, function(){
        btn.textContent = "Where am I";
        cap.textContent = "Could not get a location. On the Heath that is usually the trees.";
        watch = null;
      }, {enableHighAccuracy:true, maximumAge:10000, timeout:20000});
    });

    apply();
  })();

  if("mediaSession" in navigator){
    A.addEventListener("play", function(){
      navigator.mediaSession.metadata = new MediaMetadata({
        title: T[cur].t,
        artist: "Hampstead Heath - a walking gazetteer",
        artwork: [{src: "cover.jpg", sizes: "1400x1400", type: "image/jpeg"}]
      });
    });
    navigator.mediaSession.setActionHandler("nexttrack", function(){ step(1); });
    navigator.mediaSession.setActionHandler("previoustrack", function(){ step(-1); });
  }
})();
"""

DEVICE = """<svg class="hilldev" viewBox="0 0 120 120" aria-hidden="true">
      <g fill="none" stroke="currentColor" stroke-width="1" opacity=".85">
        <path d="M6 92 C22 88 30 76 44 74 C58 72 66 80 82 76 C96 73 106 66 114 62"/>
        <path d="M14 82 C28 78 34 68 46 66 C58 64 66 70 80 67 C92 64 100 58 108 55"/>
        <path d="M24 72 C34 69 40 61 48 59 C58 57 64 61 76 59 C86 57 92 52 99 49"/>
      </g>
      <g stroke="currentColor" stroke-width="1" opacity=".5" fill="none">
        <ellipse cx="40" cy="102" rx="15" ry="4"/>
        <ellipse cx="76" cy="108" rx="19" ry="5"/>
      </g>
      <g stroke="currentColor" stroke-width="1.4" fill="none">
        <path d="M62 55 L62 30"/>
        <path d="M62 30 L74 20 L86 30 L74 40 Z" stroke-width="1.6"/>
        <path d="M74 40 q3 6 -2 9 q-5 3 -2 8" stroke-width="1" opacity=".6"/>
      </g>
      <circle cx="62" cy="56" r="2.6" fill="currentColor"/>
    </svg>"""


MAP_W = 1000.0          # viewBox units across; height follows from the latitude


def mapdata():
    path = os.path.join(HERE, "map.json")
    return json.load(open(path)) if os.path.exists(path) else None


def projector(bbox):
    """Equirectangular, scaled so a metre east is a metre north on the page."""
    s, w, n, e = bbox
    mid = math.radians((s + n) / 2)
    wide = (e - w) * math.cos(mid)
    h = MAP_W * (n - s) / wide
    def xy(lat, lon):
        return ((lon - w) / (e - w) * MAP_W, (n - lat) / (n - s) * h)
    return xy, h


def path_d(rings, xy, close):
    out = []
    for ring in rings:
        pts = ["%.1f %.1f" % xy(lat, lon) for lat, lon in ring]
        if pts:
            out.append("M" + "L".join(pts) + ("Z" if close else ""))
    return "".join(out)


def map_svg(tracks):
    """An inline SVG map: no tiles, no libraries, no network. Geometry is
    OpenStreetMap, simplified by fetch_map.py."""
    d = mapdata()
    if not d:
        return ""
    xy, h = projector(d["bbox"])
    stops = {int(k): v for k, v in d["stops"].items()}

    # markers, nudged apart where two stops share a doorway (11 and 12)
    placed, marks = [], []
    for n in sorted(stops):
        x, y = xy(*stops[n])
        while any(math.hypot(x - px, y - py) < 22 for px, py in placed):
            x, y = x + 17, y + 9
        placed.append((x, y))
        stop = next(s for s, _, _ in tracks if s["n"] == n)
        i = [s for s, _, _ in tracks].index(stop)
        dur = clock(next(t for s, _, t in tracks if s is stop))
        marks.append((n, x, y, stop, i, dur))

    # the connector is stop order, not the walked path, and says so
    route = "M" + "L".join("%.1f %.1f" % xy(*stops[n]) for n in sorted(stops))

    out = ['<figure class="mapwrap">']
    out.append('<div class="mapbox">')
    out.append('<svg id="mp" viewBox="0 0 %d %.0f" role="group" '
               'aria-label="Map of the walk, twenty stops in order" '
               'preserveAspectRatio="xMidYMid meet">' % (MAP_W, h))
    out.append('<path class="mheath" d="%s"/>' % path_d(d["heath"], xy, True))
    out.append('<path class="mroad" d="%s"/>' % path_d(d["roads"], xy, False))
    out.append('<path class="mwater" d="%s"/>' % path_d(d["water"], xy, True))
    out.append('<path class="mroute" d="%s"/>' % route)
    out.append('<g class="mstops">')
    for n, x, y, stop, i, dur in marks:
        out.append('<g class="mstop %s" data-i="%d" data-n="%d" tabindex="0" role="button" '
                   'aria-label="Stop %d, %s, %s. Play it and jump to the transcript." '
                   'transform="translate(%.1f %.1f)">'
                   '<circle class="mhit" r="30"/><circle class="mdot" r="14"/>'
                   '<text class="mnum" y="5">%d</text></g>'
                   % (stop["kind"], i, n, n, esc(stop["title"]), dur, x, y, n))
    out.append("</g>")
    out.append('<g id="mme" hidden><circle class="macc" r="0"/><circle class="mdotme" r="9"/></g>')
    out.append("</svg>")
    out.append('<div class="mapctl">'
               '<button type="button" data-z="in" aria-label="Zoom in">+</button>'
               '<button type="button" data-z="out" aria-label="Zoom out">&#8722;</button>'
               '<button type="button" data-z="fit">Fit</button>'
               '<button type="button" id="mlocate">Where am I</button>'
               "</div>")
    out.append("</div>")
    out.append('<figcaption id="mcap">Tap a number to play that stop. The dotted line '
               'is the order of the stops, not the path you walk. Map data '
               '<a href="https://www.openstreetmap.org/copyright">&#169; OpenStreetMap '
               'contributors</a>, ODbL.</figcaption>')
    out.append("</figure>")
    return "\n".join(out)


def gpx(tracks):
    """The twenty stops as waypoints and a route, for a real map application."""
    d = mapdata()
    if not d:
        return None
    stops = {int(k): v for k, v in d["stops"].items()}
    by_n = {s["n"]: s for s, _, _ in tracks}
    o = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<gpx version="1.1" creator="hampstead-heath audio guide" '
         'xmlns="http://www.topografix.com/GPX/1/1">',
         "  <metadata><name>Hampstead Heath and its village</name>"
         "<desc>Twenty stops, in walking order.</desc></metadata>"]
    for n in sorted(stops):
        lat, lon = stops[n]
        o.append('  <wpt lat="%.5f" lon="%.5f"><name>%d. %s</name><desc>%s</desc></wpt>'
                 % (lat, lon, n, esc(by_n[n]["title"]), esc(by_n[n]["where"])))
    o.append("  <rte><name>Hampstead Heath, twenty stops</name>")
    for n in sorted(stops):
        lat, lon = stops[n]
        o.append('    <rtept lat="%.5f" lon="%.5f"><name>%d</name></rtept>' % (lat, lon, n))
    o += ["  </rte>", "</gpx>", ""]
    return "\n".join(o)


def pictures():
    """images/credits.json, written by fetch_images.py. Optional: without it
    the page still builds, just without photographs."""
    path = os.path.join(HERE, "images", "credits.json")
    return json.load(open(path)) if os.path.exists(path) else {}


def figure(i, stop, pics):
    """A photograph and the credit its licence requires."""
    p = pics.get(str(i))
    if not p:
        return ""
    where = stop["where"] if stop["n"] else "Hampstead Heath"
    alt = "%s, %s" % (stop["title"], where) if stop["n"] else where
    if p["lic"].lower().startswith("public domain"):
        credit = ('<a href="%s">%s</a> &#183; public domain, via Wikimedia Commons'
                  % (esc(p["src"]), esc(p["by"])))
    else:
        lic = ('<a href="%s">%s</a>' % (esc(p["licurl"]), esc(p["lic"]))
               if p["licurl"] else esc(p["lic"]))
        credit = ('Photograph by <a href="%s">%s</a> &#183; %s &#183; %s'
                  % (esc(p["src"]), esc(p["by"]), lic, esc(p["edit"])))
    return ('<figure class="shot"><img src="images/%s" alt="%s" width="%d" height="%d" '
            'loading="lazy" decoding="async">'
            '<figcaption class="lab">%s</figcaption></figure>'
            % (esc(p["file"]), esc(alt), p["w"], p["h"], credit))


def render(tracks):
    """tracks: list of (stop, filename, duration)"""
    pics = pictures()
    total = sum(d for _, _, d in tracks)
    longest = max(d for _, _, d in tracks)
    free = sum(1 for s in STOPS if s["n"] and s["n"] not in PAID)

    out = []
    w = out.append
    w('<meta charset="utf-8">')
    w('<meta name="viewport" content="width=device-width, initial-scale=1">')
    w('<meta name="description" content="A twenty-stop walking audio guide to Hampstead Heath '
      'and its village: 23 tracks, 36 minutes, with the full transcript, a map and a photograph '
      'for every stop.">')
    w('<meta name="color-scheme" content="light dark">')
    w("<title>The Audio Guide &#8211; Hampstead Heath &amp; Its Village</title>")
    w("<style>" + CSS + "</style>\n")
    w('<div class="wrap">\n')

    # masthead ------------------------------------------------------------
    w('<header class="cart">')
    w('  <div class="cart-inner">')
    w("    <div>")
    w('      <p class="lab">The audio guide &#183; Hampstead, NW3</p>')
    w("      <h1>Hampstead Heath, <em>read aloud</em></h1>")
    w('      <p class="lede">The twenty-stop walk as <b>%d tracks, %d minutes</b>, to be played '
      "standing in front of the thing it describes. Every track opens where you should be standing "
      "and closes by telling you where to go next. This page is the transcript, word for word, so "
      "you can read it on the train or hand it to someone without headphones.</p>"
      % (len(tracks), round(total / 60)))
    w("    </div>")
    w("    " + DEVICE)
    w("  </div>")
    w('  <ul class="stats">')
    w('<li><span class="n">%d</span><span class="lab">Tracks</span></li>' % len(tracks))
    w('<li><span class="n">%d<small> min</small></span><span class="lab">End to end</span></li>'
      % round(total / 60))
    w('<li><span class="n">20</span><span class="lab">Stops on the loop</span></li>')
    w('<li><span class="n">%s</span><span class="lab">Average track</span></li>'
      % clock(total / len(tracks)))
    w('<li><span class="n">%d</span><span class="lab">That cost nothing</span></li>' % free)
    w("  </ul>")
    w('<p class="blk-sub" style="margin-top:18px">Press play on any stop. Tracks stream only when '
      "you ask for one and the photographs load only as you scroll to them, so this page stays "
      "cheap on mobile data. Nothing auto-advances &#8211; between stops you are walking, not "
      "listening. "
      '<a href="hampstead-heath-full-walk.m4a" download>Download the whole walk as one file</a> '
      "if you would rather have it offline, because the Heath has patchy signal in the "
      "middle.</p>")
    w("</header>\n")

    # map -----------------------------------------------------------------
    svg = map_svg(tracks)
    if svg:
        w('<section class="blk" id="map">')
        w("  <h2>The map <span>Twenty stops</span></h2>")
        w('  <p class="blk-sub">The loop, anticlockwise, starting and ending at the station. '
          "Drag to move it, pinch or scroll to zoom, and tap a number to play that stop. "
          "There are no map tiles here and nothing is fetched from anywhere, so it works with "
          "one bar of signal. <a href=\"hampstead-heath-walk.gpx\" download>Download the route "
          "as GPX</a> for a map application that can actually navigate.</p>")
        w(svg)
        w('  <div class="mapkey lab">')
        for kind, label in (("village", "Village & street"), ("high", "High ground"),
                            ("water", "Water"), ("house", "House & museum")):
            w('    <span><i style="background:var(--%s)"></i>%s</span>'
              % ({"village": "heath", "high": "contour", "water": "water",
                  "house": "brick"}[kind], label))
        w("  </div>")
        w("</section>\n")

    # contents ------------------------------------------------------------
    w('<section class="blk">')
    w("  <h2>The tape <span>%s of narration</span></h2>" % clock(total))
    w('  <p class="blk-sub">Track order is walking order. The measure shows how long you stand in '
      "each place; the last column is the clock position if you play the whole thing straight "
      "through.</p>")
    w('  <nav class="tape audio">')
    at = 0.0
    for i, (stop, fn, dur) in enumerate(tracks):
        num = '<span class="sn">%d</span>' % stop["n"] if stop["n"] else ""
        w('<div class="row %s" data-i="%d"><button class="pb" aria-label="Play %s"></button>'
          '<span class="rn">%02d</span><a class="rt" href="#t%02d">%s%s</a>'
          '<span class="rbar"><i style="width:%.1f%%"></i></span>'
          '<span class="rd">%s</span><span class="rc">%s</span></div>'
          % (stop["kind"], i, esc(stop["title"]), i + 1, i, num, esc(stop["title"]),
             100.0 * dur / longest, clock(dur), clock(at)))
        at += dur
    w("  </nav>")
    w('  <div class="tape-key">')
    w('    <p class="lab">Bar colour follows the gazetteer: village, high ground, water, house</p>')
    w('    <p class="lab">Track &#183; length &#183; from start</p>')
    w("  </div>")
    w("</section>\n")

    # transcript ----------------------------------------------------------
    w('<section class="blk">')
    w("  <h2>The script <span>Verbatim</span></h2>")
    w('  <p class="blk-sub">What is printed here is exactly what is spoken, which is why the '
      "numbers are written as words. Broadcast habit: a reader who says &#8220;sixteen ninety "
      "two&#8221; never has to decide what &#8220;1692&#8221; sounds like.</p>")
    for i, (stop, fn, dur) in enumerate(tracks):
        label = KIND[stop["kind"]][0]
        mark = ('<span class="tn">%d</span>' % stop["n"] if stop["n"]
                else '<span class="tn sym">&#183;</span>')
        w('<article class="trk %s" id="t%02d"><div class="tmark">%s</div><div class="tbody">'
          '<p class="lab eyebrow">Track %02d &#183; %s &#183; %s</p><h3>%s</h3>'
          '<p class="sub">%s</p>'
          '<div class="play" data-i="%d"><button class="pb" aria-label="Play %s"></button>'
          '<span class="plab">Play</span><span class="pgs"><i></i></span>'
          '<span class="ptime">%s</span></div>'
          % (stop["kind"], i, mark, i + 1, esc(label), clock(dur), esc(stop["title"]),
             esc(stop["where"]), i, esc(stop["title"]), clock(dur)))
        w(figure(i, stop, pics))
        w("\n".join("<p>%s</p>" % esc(p) for p in stop["body"]))
        if stop.get("walk"):
            w('<div class="walk"><span class="lab">Walk on</span><p>%s</p></div>'
              % esc(stop["walk"]))
        w("</div></article>")
    w("</section>\n")

    # colophon ------------------------------------------------------------
    w('<section class="blk">')
    w("  <h2>How it was made <span>Colophon</span></h2>")
    w('  <div class="colo">')
    v = voice_note()
    w('    <div><p class="lab">Voice</p><p>%s, at %s &#8211; slower than conversation, which is '
      "what you want when the listener is also crossing roads and watching for tree "
      "roots.</p></div>" % (esc(v["name"]), esc(v["pace"])))
    w('    <div><p class="lab">Files</p><p>%d AAC tracks, tagged as one album with cover art, plus '
      "a single continuous <code>FULL WALK</code> file for anyone who would rather not keep "
      "pressing play.</p></div>" % len(tracks))
    w('    <div><p class="lab">Pictures</p><p>One photograph per track, picked to show the thing '
      "you are standing in front of rather than the prettiest view of it. All of them are "
      "Creative Commons or public domain, from Wikimedia Commons, credited under the picture and "
      "fetched by <code>fetch_images.py</code>.</p></div>")
    w('    <div><p class="lab">Rebuilding it</p><p>The narration lives in one Python file, '
      "<code>build.py</code>. The audio and this page are both generated from it, so the "
      "transcript can never drift out of step with the recording.</p></div>")
    w('    <div><p class="lab">Changing the voice</p><p>Any installed system voice works. Swap the '
      "name and the pace at the top of the generator and re-run it; the whole set rebuilds in "
      "about a minute.</p></div>")
    w("  </div>")
    w("</section>\n")

    w("<footer>")
    w("  <p>Walking directions were written from the Heath's own path network and the streets "
      "between them. They are accurate enough to follow and are not a substitute for looking up. "
      "The Heath is not a park with a fence and a plan; several of these turnings are deliberately "
      "unmarked, which is the reason they are still worth finding.</p>")
    w("  <p>Opening hours were checked in August 2026 and are the first thing to change. Confirm "
      "before setting out for anything ticketed. The Heath has no lighting, the swimming ponds are "
      "open only when lifeguards are on duty, and both of those facts matter more here than "
      "anywhere else on this list.</p>")
    w("<p>Audio is synthesised speech &#8211; %s, %s, at %s. Good enough to walk to, and not a "
      "broadcast read.</p>" % (esc(v["name"]), esc(v["note"]), esc(v["pace"])))
    w("</footer>\n")
    w("</div>")

    # player --------------------------------------------------------------
    w("<!-- ===== player: injected only into the hosted build ===== -->")
    w("<style>" + PLAYER_CSS + "</style>\n")
    w('<div class="bar" id="bar" hidden>')
    w('  <button id="bprev" aria-label="Previous track" title="Previous">&#8249;</button>')
    w('  <button id="bplay" aria-label="Pause">&#10073;&#10073;</button>')
    w('  <button id="bnext" aria-label="Next track" title="Next">&#8250;</button>')
    w('  <div class="bmeta">')
    w('    <span class="bt" id="btitle"></span>')
    w('    <span class="brow">')
    w('      <input class="bseek" id="bseek" type="range" min="0" max="1000" value="0" '
      'aria-label="Seek within track">')
    w('      <span class="btime" id="btime">0:00 / 0:00</span>')
    w("    </span>")
    w("  </div>")
    w('  <button id="bstop" aria-label="Stop and close player">&#10005;</button>')
    w("</div>\n")

    data = [{"f": "audio/" + fn,
             "t": (s["title"] if s["n"] is None else "%d. %s" % (s["n"], s["title"])),
             "d": round(d, 1)} for s, fn, d in tracks]
    d = mapdata()
    js = (PLAYER_JS
          .replace("__TRACKS__", json.dumps(data, ensure_ascii=False))
          .replace("__MAPBBOX__", json.dumps(d["bbox"]) if d else "null"))
    w("<script>" + js.encode("ascii", "xmlcharrefreplace").decode() + "</script>")
    return "\n".join(out) + "\n"


def build_page():
    tracks = []
    for i, stop in enumerate(STOPS):
        fn = "%02d-%s.m4a" % (i, slug(stop["title"]))
        path = os.path.join(AUDIO, fn)
        if not os.path.exists(path):
            sys.exit("missing %s - run without --page first" % path)
        tracks.append((stop, fn, length(path)))
    open(os.path.join(HERE, "index.html"), "w").write(render(tracks))
    print("  index.html: %d tracks, %s" % (len(tracks), clock(sum(t[2] for t in tracks))))

    route = gpx(tracks)
    if route:
        open(os.path.join(HERE, "hampstead-heath-walk.gpx"), "w").write(route)
        print("  hampstead-heath-walk.gpx: 20 waypoints")

    open(os.path.join(HERE, "wrangler.jsonc"), "w").write(
        '{\n  "name": "hampstead-heath",\n'
        '  "compatibility_date": "2026-08-07",\n'
        '  "assets": { "directory": "." }\n}\n')


# --------------------------------------------------------------------------
# cover
# --------------------------------------------------------------------------

def build_cover():
    from PIL import Image, ImageDraw, ImageFont
    S = 1400
    paper, ink, soft, green = "#EFEDE5", "#181D16", "#8A9384", "#2C6B45"
    img = Image.new("RGB", (S, S), paper)
    d = ImageDraw.Draw(img)

    def font(names, size):
        for n in names:
            for base in ("/System/Library/Fonts/Supplemental/", "/System/Library/Fonts/",
                         "/Library/Fonts/"):
                p = base + n
                if os.path.exists(p):
                    try:
                        return ImageFont.truetype(p, size)
                    except OSError:
                        pass
        return ImageFont.load_default()

    disp = font(["Big Caslon.ttf", "Baskerville.ttc", "Didot.ttc", "Georgia.ttf"], 132)
    disp_i = font(["Baskerville.ttc", "Big Caslon.ttf", "Georgia Italic.ttf"], 132)
    caps = font(["Optima.ttc", "GillSans.ttc", "Futura.ttc", "Helvetica.ttc"], 33)
    caps_s = font(["Optima.ttc", "GillSans.ttc", "Futura.ttc", "Helvetica.ttc"], 30)

    d.rectangle([78, 78, S - 78, S - 78], outline=ink, width=3)
    d.rectangle([96, 96, S - 96, S - 96], outline=soft, width=1)

    def spaced(text, f, y, fill, track=9):
        widths = [d.textlength(c, font=f) for c in text]
        total = sum(widths) + track * (len(text) - 1)
        x = (S - total) / 2
        for c, wd in zip(text, widths):
            d.text((x, y), c, font=f, fill=fill)
            x += wd + track

    spaced("A WALKING GAZETTEER", caps, 196, soft)
    spaced("HAMPSTEAD HEATH, NW3", caps_s, 252, green)

    # a hill in contour, with a kite over it and two ponds below
    cx, cy = S / 2, 640
    for k, (sx, sy) in enumerate([(1.0, 1.0), (0.72, 0.70), (0.46, 0.46)]):
        pts = []
        import math
        for a in range(0, 361, 6):
            r = 250 * (1 + 0.12 * math.sin(math.radians(a * 3 + 40))
                       + 0.06 * math.sin(math.radians(a * 5)))
            pts.append((cx + r * sx * math.cos(math.radians(a)),
                        cy + r * sy * 0.62 * math.sin(math.radians(a))))
        d.line(pts + [pts[0]], fill=soft, width=2 if k else 3)

    d.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=ink)
    d.line([(cx, cy), (cx + 62, cy - 210)], fill=ink, width=4)
    kx, ky = cx + 62, cy - 210
    d.polygon([(kx, ky - 62), (kx + 52, ky), (kx, ky + 62), (kx - 52, ky)],
              outline=ink, fill=paper, width=4)
    d.line([(kx - 52, ky), (kx + 52, ky)], fill=soft, width=2)
    d.line([(kx, ky - 62), (kx, ky + 62)], fill=soft, width=2)

    d.text((S / 2, 1002), "Hampstead Heath", font=disp, fill=ink, anchor="mm")
    d.text((S / 2, 1122), "& its village", font=disp_i, fill=green, anchor="mm")

    d.line([(S / 2 - 200, 1236), (S / 2 + 200, 1236)], fill=soft, width=2)
    spaced("TWENTY STOPS  ·  36 MINUTES", caps_s, 1266, soft)

    img.save(os.path.join(HERE, "cover.jpg"), quality=92)
    print("  cover.jpg")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--voices"]:
        list_voices()
    elif args == ["--cost"]:
        cost()
    elif args == ["--sample"]:
        sample()
    elif args == ["--cover"]:
        build_cover()
    elif args == ["--page"]:
        build_page()
    elif not args:
        if not os.path.exists(os.path.join(HERE, "cover.jpg")):
            build_cover()
        build_audio()
        build_page()
    else:
        sys.exit(__doc__)
