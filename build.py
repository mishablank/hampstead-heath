#!/usr/bin/env python3
"""Hampstead Heath and its village - build the walking audio guide.

Everything the guide says lives in STOPS, below. Running this file renders the
narration to AAC with a system voice, measures what came out, and writes
index.html from the same text, so the transcript on the page can never drift
out of step with the recording.

    python3 build.py              audio, then the page
    python3 build.py --page       page only, timed from the audio already there
    python3 build.py --cover      redraw cover.jpg and og.jpg
    python3 build.py --icons      redraw the favicon set and the web manifest
    python3 build.py --voices     list the voices available for this engine
    python3 build.py --sample     render one track so you can hear the voice
    python3 build.py --cost       how many credits a full rebuild costs

Needs macOS (afconvert) and mutagen. The voice comes from Amazon Polly by
default; see the ENGINE note below for why, and for the local alternative.
"""

import datetime
import email.utils
import html as _html
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.parse

# --------------------------------------------------------------------------
# the voice.
#
# "polly"       Amazon Polly's generative engine. Commercial use under the AWS
#               customer agreement, and the free tier covers 100,000
#               generative characters a month for the first year, near enough
#               three times this script. Needs credentials in ~/.aws, and a
#               region that actually has the generative engine: see PL_REGION.
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
ENGINE = os.environ.get("TTS_ENGINE", "polly")

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

PL_VOICE = os.environ.get("POLLY_VOICE", "Brian")   # en-GB generative: Brian or Amy
PL_ENGINE = os.environ.get("POLLY_ENGINE", "generative")
PL_REGION = os.environ.get("AWS_REGION", "eu-west-2")
PL_RATE = 94                     # per cent of natural pace; 20 to 200 allowed

AAC_BITRATE = "48000"     # mono speech; 64k is twice what this needs

ALBUM = "Hampstead Heath - a walking gazetteer"
HERE = os.path.dirname(os.path.abspath(__file__))
# everything the Worker serves lives under SITE and nothing else does, so the
# deploy is an allowlist. Sources, drafts and build inputs stay in HERE, where
# no amount of misconfiguration can publish them.
SITE = os.path.join(HERE, "public")
AUDIO = os.path.join(SITE, "audio")
FULL = os.path.join(SITE, "hampstead-heath-full-walk.m4a")
STAMP = os.path.join(HERE, "voice.json")   # what actually made the audio here

# --------------------------------------------------------------------------
# how the thing is found. ORIGIN is the canonical origin - scheme and host,
# no trailing slash. Every absolute URL in the head, the sitemap, the feed and
# the structured data is built from it, so moving to a real domain is a
# one-line change here. Not to be confused with SITE above, which is the
# directory those URLs are served from.
# --------------------------------------------------------------------------

ORIGIN = "https://hampstead-heath.blankm.workers.dev"    # no trailing slash
UPDATED = "2026-08-09"    # dateModified. Bump it when the narration changes.
AUTHOR = ""               # a byline, if you want one in the structured data
OWNER_EMAIL = ""          # Apple Podcasts will not accept the feed without one

# what this walk is about, said in the vocabulary search engines already know.
# The Wikipedia and Wikidata links are the whole point of sameAs: they tell a
# machine which Hampstead Heath this is, and there is only one.
HEATH = {
    "name": "Hampstead Heath",
    "lat": 51.56028, "lon": -0.16083,
    "same": ["https://en.wikipedia.org/wiki/Hampstead_Heath",
             "https://www.wikidata.org/wiki/Q1570958"],
}
START = {"name": "Hampstead Underground station", "lat": 51.55654, "lon": -0.17812}

# --------------------------------------------------------------------------
# the narration. body = spoken paragraphs; walk = the "walk on" instruction,
# which is also spoken, because it is the half of the guide that gets you to
# the next place.
# --------------------------------------------------------------------------

STOPS = [
dict(kind="intro", n=None, title="How to use this", where="Introduction", body=[
"Hampstead Heath and its village. A walking gazetteer, in twenty-four stops.",

"This is a single loop that starts and ends outside Hampstead Underground "
"station, on Heath Street. Something over three hours of walking before you "
"stop for anything at all, and unlike almost every other walk in London, this "
"one has hills in it. It goes through the village first, up to the highest "
"ground in inner London, west to a half-ruined Edwardian pergola, north-east "
"along the top to Kenwood, and then down the east side of the Heath past the "
"swimming ponds and home.",

"Wear shoes you do not mind. Two thirds of this is unpaved, the Heath sits on "
"London clay, and it holds water for days after rain.",

"Nineteen of the twenty-four stops are free. Three more are free unless you get "
"into the water. Two of them charge at the door.",

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

"It also holds the Llewelyn Davies family. Arthur and Sylvia had five sons, "
"and after both parents died young the boys were taken in by a family friend "
"who had been writing stories for them for years. The friend was J M Barrie "
"and the stories became Peter Pan. Being the boy who Peter Pan was based on "
"turned out to be a life sentence rather than a gift, and more than one of "
"them said so. Peter, who got the name, spent his adult life calling the book "
"that terrible masterpiece, and in nineteen sixty he stepped in front of a "
"train at Sloane Square.",

"Free, and open most days.",
], walk=
"Out through the top of the churchyard into Holly Walk, the narrow lane "
"climbing north between the walls. Ninety seconds. On your right, set into the "
"terrace and looking like a house that happens to have a bell, is stop three. "
"You will walk past it if you are not counting doors."),

dict(kind="village", n=3, title="Saint Mary's, Holly Walk", where="Holly Place", body=[
"Stop three. Saint Mary's.",

"It does not look like a church, and that is the whole point. It was built in "
"eighteen sixteen, when a Catholic church in England was a recent and nervous "
"freedom, and it is one of the earliest built in London after the Reformation. "
"So it keeps its head down. Only the bell tower and the statue of the Virgin "
"and Child give it away, and both of those were added in the eighteen fifties, "
"once it was safe to be obvious.",

"The man who built it was a refugee. Jean-Jacques Morel was a French priest "
"who fled the Revolution in seventeen ninety two, arrived in England with "
"nothing, and by seventeen ninety six was looking after the French Catholics "
"who had washed up on this hill for the same reason. He raised the money, and "
"the chapel went up in under a year and opened in August eighteen sixteen.",

"That is the fact worth carrying for the rest of the walk. Hampstead's "
"reputation is poets and money. But this church exists because a village on a "
"hill absorbed a few hundred frightened foreigners and let them build "
"something.",

"Two names in the register. Graham Greene was married here in nineteen twenty "
"seven, having converted in order to do it, which is where a great deal of his "
"writing starts. And during the Second World War, when the Free French were "
"running their war from London, Charles de Gaulle worshipped here.",

"Free, and usually open. It is very small and very quiet, and there is a good "
"chance you will be the only one in it.",
], walk=
"Keep going up Holly Walk. On your left, watch for a squat little building set "
"in the wall: that is the old watch house, where the night watchman sat before "
"anybody had thought of police. The lane opens out at the top. Two minutes."),

dict(kind="house", n=4, title="Holly Bush Hill", where="Holly Bush Hill", body=[
"Stop four. Holly Bush Hill, and the painter who ran away twice.",

"The large weatherboarded building behind the pub is George Romney's house. In "
"seventeen ninety six Romney, who was one of the three most fashionable "
"portrait painters in England, bought the site up here and built himself a "
"house with a picture gallery and a studio in it, which was an odd thing for a "
"sick man in his sixties to do.",

"He is here because of one face. From seventeen eighty two he painted Emma "
"Hart, later Lady Hamilton, later Nelson's mistress, something like sixty "
"times, as Circe, as a bacchante, as Joan of Arc, as anything he could think "
"of. You will be told he came to Hampstead to recover from an affair with her. "
"He did not. She was his model and his obsession and, so far as anybody can "
"show, nothing else, which is stranger and rather sadder.",

"The ending is the part nobody puts on the plaque. In seventeen ninety nine, "
"after three years in this house, Romney gave it up and went home to Kendal, "
"to the wife he had walked out on roughly thirty-five years earlier and barely "
"seen since. She took him in and nursed him until he died.",

"The pub in front of you is the Holly Bush, late seventeen hundreds, gas-lit, "
"partitioned, and almost untouched. It is on most people's list of the best "
"pubs in London and it deserves to be.",

"And round the corner on Windmill Hill is Bolton House, where Joanna Baillie "
"lived for about sixty years. She was the most performed woman playwright of "
"her age. Byron, Wordsworth, Keats and Walter Scott all came up this hill to "
"see her, and Sarah Siddons acted her work. Her plaque went up in nineteen "
"hundred and was only the fourth in London given to a woman.",

"All free. The pub is not, but that is your own affair.",
], walk=
"North up Hampstead Grove, one minute. The tall brown house behind wrought-iron "
"gates on your right is stop five."),

dict(kind="house", n=3, title="Fenton House", where="Hampstead Grove", body=[
"Stop five. Fenton House.",

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
"Carry on north up Hampstead Grove for one minute, and take the narrow lane on "
"your left. It is called Admiral's Walk, and the white house with the thing on "
"the roof is stop six."),

dict(kind="house", n=4, title="Admiral's House", where="Admiral's Walk", body=[
"Stop six. Admiral's House.",

"Look at the roof. That is a quarterdeck, built on top of a house, four miles "
"from the nearest tidal water, with a flagpole and a place to stand and take "
"the salute. It is the least explicable roof in London.",

"The house went up in the early seventeen hundreds. In seventeen seventy five "
"it was bought by Lieutenant Fountain North, of the Royal Navy, who added the "
"quarterdeck and is said to have fired cannon from it to mark naval victories "
"and royal birthdays, which cannot have been popular with the neighbours.",

"And now the correction, which is the whole reason to stand here. No admiral "
"has ever lived in Admiral's House. There was a real admiral in Hampstead, "
"Matthew Barton, and he also let off cannon, and at some point the village "
"put the two men together and gave the house to the wrong one. The mistake "
"then spread to the lane, which is why you are standing in Admiral's Walk. "
"Nobody has ever bothered to correct it, and by now it would be vandalism.",

"Two people who took it seriously. John Constable painted this house again "
"and again, and one of those paintings is in the Victoria and Albert. And "
"George Gilbert Scott lived here from eighteen fifty six, which means the man "
"who designed Saint Pancras station and the Albert Memorial was working out of "
"a house pretending to be a ship.",

"One more. If you have ever seen Mary Poppins, you know a naval gentleman who "
"fires a cannon from his roof and knocks the furniture over. This is where "
"Admiral Boom comes from.",

"And look next door, at Grove Lodge. John Galsworthy lived in it from nineteen "
"eighteen until he died in nineteen thirty three, wrote most of the Forsyte "
"Saga in it, and took the Nobel Prize for literature out of it in nineteen "
"thirty two. Two houses, sharing a wall, and between them a cannon and a "
"Nobel.",

"There is also a plaque a little further down Hampstead Grove to George du "
"Maurier, who lived there in the eighteen seventies and eighties and wrote "
"Trilby, the novel that gave the language Svengali. Hold on to that name. His "
"son is at stop twenty-three and his granddaughter wrote Rebecca.",

"Free, and private. Look from the lane and do not ring the bell.",
], walk=
"Back to Hampstead Grove and keep going north. Lower Terrace runs off to the "
"left, and at the end of it, behind a gate, on top of what looks like a "
"grass-covered bunker, is stop seven."),

dict(kind="high", n=4, title="Hampstead Observatory", where="Lower Terrace", body=[
"Stop seven. The Hampstead Observatory.",

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
"Stop eight. Whitestone Pond, and the roof of London.",

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

"Height had a use before it had a view. High ground like this carried the "
"beacon chain, the line of fires lit across the country to raise the alarm, "
"and Hampstead's beacon stood up here in the years when England was waiting "
"for the Spanish Armada. The flagstaff is a polite descendant of a bonfire "
"meant to tell London it was in trouble.",

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
"Stop nine. The Hill Garden, and the Pergola.",

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
"Stop ten. Golders Hill Park.",

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
"is a steady climb of about twelve minutes back to Whitestone Pond. Stop eleven "
"is the large white weatherboarded building on the corner as you arrive."),

dict(kind="village", n=8, title="Jack Straw's Castle", where="North End Way", body=[
"Stop eleven. Jack Straw's Castle, which is no longer a pub and has not been "
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

"It is also in Dracula, which is set partly on this hill. Van Helsing and "
"Doctor Seward eat dinner at Jack Straw's Castle before walking out along "
"Spaniards Road on the business of Lucy, who is buried in a Hampstead "
"churchyard that Stoker never quite names. He knew the ground. The Heath in "
"that book is the safe green edge of London where something is going wrong, "
"which is roughly how it still reads at dusk.",

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
"Stop twelve. The Vale of Health.",

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
"pinch is stop thirteen."),

dict(kind="village", n=10, title="The Spaniards Inn", where="Spaniards Road", body=[
"Stop thirteen. The Spaniards Inn, and the toll house that is still in the way.",

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
"Stop fourteen. Kenwood.",

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
"garden, one of them carrying fruit. Stop fifteen is standing in front of it."),

dict(kind="house", n=12, title="Dido Elizabeth Belle", where="inside Kenwood", body=[
"Stop fifteen. Dido Elizabeth Belle.",

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
"Lane heading south. Eight minutes. The gate on your right is stop sixteen, "
"and if you are a man you are not going through it."),

dict(kind="water", n=13, title="The Kenwood Ladies' Pond", where="off Millfield Lane", body=[
"Stop sixteen. The Kenwood Ladies' Pond, which opened in nineteen twenty six "
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
"Stop seventeen. The Highgate Men's Pond.",

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
"Stop eighteen. The tumulus, which the whole of north London calls Boudica's "
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
"Stop nineteen. Parliament Hill. Ninety-eight metres, and the best free view in "
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
"Stop twenty. Parliament Hill Lido.",

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
"Stop twenty-one. The ponds, and the river underneath them.",

"None of these is a lake. Every pond on this Heath is a dammed valley, and the "
"grass bank you are walking along is the dam. The water in them is the River "
"Fleet, which rises in two arms up on this hill, one under this chain and one "
"under the Highgate chain, and which meets itself at Camden Town before "
"running down under Farringdon and out into the Thames at Blackfriars.",

"They also open English literature, in a way nobody expects. The first thing "
"that happens in Charles Dickens's first novel is that Samuel Pickwick reads a "
"paper to his club. The paper is about the source of the Hampstead Ponds, with "
"some further observations on the theory of tittlebats. That is the joke "
"Dickens chose to start with, and it only works because in eighteen thirty six "
"a learned paper on these ponds was exactly the sort of thing a learned "
"gentleman would write.",

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
"the garden wall on your left is stop twenty-two."),

dict(kind="house", n=19, title="Keats House", where="Keats Grove", body=[
"Stop twenty-two. Keats House.",

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
"Willow Road. You will pass number two, which is a museum and is on a longer "
"list than this one. Cross East Heath Road, climb, and bear left into Cannon "
"Place. Cannon Lane drops away on your left. Eight minutes, and stop "
"twenty-three is a door in a wall."),

dict(kind="village", n=21, title="The Cannon Lane Lock-Up", where="Cannon Lane", body=[
"Stop twenty-three. The parish lock-up, in the wall on your left.",

"A heavy studded door, a barred slit at head height, and behind it a single "
"windowless cell, built into the garden wall of the house above in about "
"seventeen thirty. This is a village prison, and it is one of very few left "
"anywhere in London.",

"The point of it is what did not exist yet. There was no police force. There "
"was a parish constable, usually a shopkeeper doing a year of unpaid duty, and "
"if he arrested you at ten at night there was nowhere on earth to put you. So "
"you went in here, in the dark, until the morning, when the magistrates could "
"see you. The magistrates sat in the house behind this wall, which meant the "
"whole apparatus of law in Hampstead was one cell, one wall and one front "
"room.",

"It stopped being used after eighteen twenty nine, when Robert Peel's "
"Metropolitan Police arrived and the parish stopped having to improvise. The "
"cell is now the entrance to somebody's very expensive house.",

"And the house it belongs to is Cannon Hall, which from nineteen sixteen was "
"the home of Gerald du Maurier, the actor-manager. He was the first man ever "
"to play Captain Hook, and in the same production the first to play Mr "
"Darling, which is why to this day the two parts are usually doubled. His "
"daughter grew up in that house and wrote Rebecca.",

"Which closes a circle, if you want it to. The boys who became Peter Pan are "
"buried at stop two, twenty minutes back down the hill. The man who first "
"played the villain lived behind this wall.",

"Free, visible from the lane at any hour, and easy to walk past.",
], walk=
"Back down Cannon Place the way you came, then right and downhill into Well "
"Walk. Two minutes. You will pass a small stone drinking fountain, and it is "
"the reason the whole village exists."),

dict(kind="village", n=20, title="Well Walk and Burgh House",
     where="Well Walk and New End Square", body=[
"Stop twenty-four. Well Walk, the well, and Burgh House.",

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
"That is the twenty-four. The station is four minutes away: Flask Walk out of the "
"top of Well Walk, then left up the High Street, and you are back where you "
"started.",

"Three hours is a Saturday, not a Tuesday, so here are three shorter versions "
"that fit a real week.",

"The first: the village hour. About fifty minutes, free, any day, no bookings. "
"Stops one through eight, then twenty-three and twenty-four. The station, the "
"church row, the French chapel, Romney's hill, Fenton House, the quarterdeck, "
"the observatory and the top of London, then the lock-up and Well Walk on the "
"way back. No mud, and you can do it in office shoes.",

"The second: the houses. Half a day, Wednesday to Sunday, because that is the "
"one window when all four of them are open. Stops five, fourteen, fifteen, "
"twenty-two and twenty-four. Fenton House, Kenwood, Keats House and Burgh House. "
"Kenwood and Burgh House are free, Keats is a few pounds, Fenton House is the "
"one that charges properly. Book Kenwood if you want to be sure of the house.",

"The third: the water. Any day of the year, and this is the one to do at seven "
"in the morning. Stops sixteen or seventeen, then twenty, then twenty-one. "
"The ladies' pond and the men's pond are open every day of the year, the mixed "
"pond only from April to October, and the lido never closes. Swim, then walk "
"up the ponds to South End Green for breakfast. It will reorganise your entire "
"opinion of London.",
]),

dict(kind="close", n=None, title="Didn't make the cut", where="The near misses", body=[
"Last track. Eight places cut for distance rather than for quality. All times "
"are walking, from Hampstead station.",

"The Freud Museum, twelve minutes, at twenty Maresfield Gardens. Freud got out "
"of Vienna in nineteen thirty eight and died here the following year, and the "
"consulting room is intact, rugs, antiquities, couch and all. Ticketed, "
"Wednesday to Sunday.",

"Two Willow Road, fifteen minutes, which you walked past between stops "
"twenty-two and twenty-three. Ernő Goldfinger built it for himself in nineteen thirty "
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
# Fenton House and Keats House charge at the door; the ponds and the lido
# only if you get in the water.
PAID = {5, 16, 17, 20, 22}

# numbers follow walking order. Assigned here rather than written into each
# entry, so inserting a stop cannot leave the guide counting wrong.
_n = 0
for _s in STOPS:
    if _s["kind"] in ("intro", "close"):
        _s["n"] = None
    else:
        _n += 1
        _s["n"] = _n
STOP_COUNT = _n

# The questions people actually type, answered in the first sentence. Every
# answer here is already somewhere in the narration above; nothing new is
# claimed. It is printed on the page and repeated as FAQPage data, from this
# one list, so the two can never disagree.
FAQ = [
    ("How long does the Hampstead Heath walk take?",
     "Something over three hours of walking before you stop for anything at all, "
     "plus fifty-five minutes of narration that you listen to standing still. Half "
     "a day is the honest answer. There is a fifty-minute village version that "
     "skips the Heath itself."),

    ("Is the audio guide free?",
     "Yes, and there is nothing to install: it is a web page, and the tracks stream "
     "only when you press play. Of the twenty-four stops, nineteen cost nothing at "
     "all. Three more are free unless you get into the water – the Kenwood "
     "Ladies' Pond, the Highgate Men's Pond and Parliament Hill Lido. Two charge at "
     "the door: Fenton House and Keats House. Kenwood House itself is free."),

    ("Where does the walk start and finish?",
     "Outside Hampstead Underground station on Heath Street, NW3. It is a single "
     "anticlockwise loop, so it finishes in the same place – four minutes from "
     "the last stop, up Flask Walk and left along the High Street."),

    ("Do I need a phone signal to use it?",
     "No. Tracks stream only when you ask for one, the photographs load as you "
     "scroll, and the map is drawn in the page rather than fetched as tiles, so it "
     "works on one bar. The middle of the Heath has patchy signal, so there is also "
     "a single continuous file to download before you set out."),

    ("Can you swim in the Hampstead Heath ponds?",
     "Yes. The Kenwood Ladies' Pond and the Highgate Men's Pond are open every day "
     "of the year, the Mixed Pond only from April to October, and Parliament Hill "
     "Lido never closes. The ponds open only when lifeguards are on duty."),

    ("How muddy is Hampstead Heath?",
     "Two thirds of this route is unpaved, the Heath sits on London clay, and it "
     "holds water for days after rain. Wear shoes you do not mind. The village "
     "half of the walk you can do in office shoes."),

    ("Is there a shorter version of the walk?",
     "Three. The village hour is about fifty minutes, free, any day, and has no mud "
     "in it. The houses is half a day, Wednesday to Sunday, which is the one window "
     "when all four are open. The water is any day of the year and is best at seven "
     "in the morning."),

    ("Do I need headphones, or can I read it instead?",
     "Either. The whole script is printed on the page, word for word, so you can "
     "read it on the train, hand it to someone without headphones, or follow it "
     "with the sound off. There is also a GPX file of the route for a map "
     "application that can navigate."),
]

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
    if ENGINE == "polly":
        return pl_voices()
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


def pl_client():
    """Credentials come from ~/.aws, the usual AWS_* variables, or an instance
    role, whichever boto3 finds first. Nothing is read from this file."""
    try:
        import boto3
    except ImportError:
        sys.exit("Polly needs boto3: pip install boto3 (or TTS_ENGINE=say to draft locally).")
    return boto3.client("polly", region_name=PL_REGION)


def pl_voices():
    """The en-GB voices this region offers for the engine in PL_ENGINE. The
    generative engine is in nine regions only, so an empty list here usually
    means the region rather than the account."""
    rows = [v for v in pl_client().describe_voices(LanguageCode="en-GB")["Voices"]
            if PL_ENGINE in v.get("SupportedEngines", [])]
    print("%-14s %-8s %s" % ("VOICE ID", "GENDER", "ENGINES"))
    for v in sorted(rows, key=lambda v: v["Id"]):
        print("%-14s %-8s %s" % (v["Id"], v["Gender"], ", ".join(sorted(v["SupportedEngines"]))))
    print("\n%d en-GB %s voices in %s. Pick one and: export POLLY_VOICE=<id>"
          % (len(rows), PL_ENGINE, PL_REGION))
    if not rows:
        print("None came back. Try AWS_REGION=eu-west-2, which has the generative voices.")


def polly(text, path):
    """One track. The pace is an SSML prosody tag rather than a parameter,
    because the generative engine has no speed control of its own; it allows
    prosody around whole sentences only, which is all this text is. Paragraphs
    become <p> so the pauses between them survive the trip."""
    paras = "".join("<p>%s</p>" % _html.escape(p, quote=False)
                    for p in text.split("\n\n"))
    out = pl_client().synthesize_speech(
        Text='<speak><prosody rate="%d%%">%s</prosody></speak>' % (PL_RATE, paras),
        TextType="ssml", VoiceId=PL_VOICE, Engine=PL_ENGINE,
        OutputFormat="mp3", SampleRate="24000",
    )
    mp3 = path.replace(".m4a", ".mp3")
    open(mp3, "wb").write(out["AudioStream"].read())
    subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", "-b", AAC_BITRATE, mp3, path],
                   check=True)
    os.remove(mp3)


def say(text, path):
    """macOS. Drafting only: see the licence note at the top of this file."""
    subprocess.run(
        ["say", "-v", VOICE, "-r", str(RATE), "-o", path, "--data-format=aac"],
        input=text, text=True, check=True,
    )


ENGINES = {"polly": polly, "google": google, "elevenlabs": elevenlabs, "say": say}


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
    print("  polly       generative is $30 per million characters, so about $%.2f," % (30 * n / 10**6))
    print("              but the first year is free up to 100,000 a month, %.1fx this." % (10**5 / n))
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
    voice = {"polly": PL_VOICE, "google": GG_VOICE,
             "elevenlabs": EL_VOICE or "unset", "say": VOICE}[ENGINE]
    out = os.path.join(HERE, "sample-%s-%s.m4a" % (ENGINE, slug(voice)))
    speak(spoken(stop), out)
    print("  %s  (%.1fs)" % (os.path.basename(out), length(out)))
    print("  open it with:  afplay '%s'" % out)


def build_audio():
    os.makedirs(AUDIO, exist_ok=True)
    art = None
    cover = os.path.join(SITE, "cover.jpg")
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

    if ENGINE == "polly":
        note = {"engine": "polly", "name": PL_VOICE, "voice_id": PL_VOICE,
                "model": PL_ENGINE, "region": PL_REGION,
                "pace": "%d%% of its natural pace" % PL_RATE,
                "note": "a British English %s voice from Amazon Polly" % PL_ENGINE}
    elif ENGINE == "google":
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
/* Bright is the base, not an override: the page does not follow the device, so
   a reader with no JavaScript gets the same white paper as everyone else. Dark
   is the only alternative, and it is opt-in. */
:root{
  color-scheme:light;
  --paper:#FFFFFF; --paper-2:#F4F6F2; --plate:#EDF0EA;
  --ink:#0A0D09; --ink-2:#3A4436; --ink-3:#5E6959;
  --rule:#B6BDAC; --rule-soft:#DCE1D4;
  --heath:#186B3A; --water:#12608C; --contour:#8A4E0B; --brick:#9B2F26;
  --font-display:"Big Caslon","Baskerville","Hoefler Text","Palatino Linotype",Palatino,Georgia,serif;
  --font-body:Charter,"Bitstream Charter","Iowan Old Style",Georgia,"Times New Roman",serif;
  --font-label:Copperplate,"Copperplate Gothic Light",Optima,"Gill Sans","Trebuchet MS",sans-serif;
  --font-data:"SF Mono",Menlo,Consolas,ui-monospace,monospace;
}
:root[data-theme="dark"]{
  color-scheme:dark;
  --paper:#0F1310; --paper-2:#171C16; --plate:#131813;
  --ink:#E4E8DF; --ink-2:#9AA495; --ink-3:#727C6E;
  --rule:#2A322A; --rule-soft:#1D231D;
  --heath:#67C08D; --water:#6FB2D6; --contour:#D3A257; --brick:#DC8579;
}

*{box-sizing:border-box}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:var(--font-body); font-size:15px; line-height:1.62;
  -webkit-font-smoothing:antialiased;
}
/* 20px is the floor, not 16: at 375px the old gutter put the last character of
   every line within a thumb's width of the bezel */
.wrap{max-width:940px; margin:0 auto; padding:0 clamp(20px,4vw,40px) 96px}
a{color:var(--heath); text-underline-offset:2px; text-decoration-thickness:from-font}
a:focus-visible{outline:2px solid var(--heath); outline-offset:2px}
.lab{
  font-family:var(--font-label); text-transform:uppercase;
  letter-spacing:.14em; font-size:11px; line-height:1.4; color:var(--ink-3);
  margin:0;
}

/* ---- masthead ---------------------------------------------------- */
header.cart{padding:clamp(38px,6vw,72px) 0 clamp(24px,3vw,34px)}
/* wraps rather than squeezes: on a phone the controls take their own row and
   the eyebrow gets its full line back */
/* spans the masthead grid, so the controls end at the page's right margin
   rather than at the edge of the column the kite sits beside */
.topbar{display:flex; flex-wrap:wrap; align-items:center; gap:10px 14px; grid-column:1 / -1}
.topbar > .lab,.topbar > .crumb{flex:1 1 auto; min-width:0}
.topbar .lab{text-wrap:balance}
/* flex:none would size this to max-content and overflow rather than wrap */
.hdr-actions{
  display:flex; flex-wrap:wrap; justify-content:flex-end;
  align-items:center; gap:8px 14px; flex:0 1 auto; min-width:0; margin-left:auto;
}
/* two errands, two groups: share this page, then act on the page */
.hgrp{display:flex; align-items:center; gap:8px}
.hgrp + .hgrp{padding-left:14px; border-left:1px solid var(--rule-soft)}
.iconbtn{
  all:unset; box-sizing:border-box; cursor:pointer;
  display:inline-flex; align-items:center; justify-content:center; flex:none;
  width:32px; height:32px; border:1px solid var(--rule-soft); color:var(--ink-3);
}
.iconbtn:hover{color:var(--ink); border-color:var(--ink-3)}
.iconbtn:focus-visible{outline:2px solid var(--heath); outline-offset:2px}
.iconbtn svg{width:15px; height:15px; fill:currentColor; display:block}
/* a credit line, not a control: no box, and it sets its own baseline */
.hcredit{
  font-family:var(--font-label); text-transform:uppercase;
  letter-spacing:.12em; font-size:10.5px; color:var(--ink-3); white-space:nowrap;
}
.hcredit a{color:var(--ink-2); text-decoration:none; border-bottom:1px solid var(--rule)}
.hcredit a:hover{color:var(--heath); border-bottom-color:var(--heath)}
/* the copy confirmation: a tick where the share glyph was */
.iconbtn .i-ok{display:none}
.iconbtn.ok{color:var(--heath); border-color:var(--heath)}
.iconbtn.ok .i-share{display:none}
.iconbtn.ok .i-ok{display:block}
.themectl{
  all:unset; box-sizing:border-box; cursor:pointer; flex:none;
  display:inline-flex; align-items:center; gap:8px;
  min-height:32px; padding:5px 11px; border:1px solid var(--rule-soft);
  font-family:var(--font-label); text-transform:uppercase;
  letter-spacing:.12em; font-size:10.5px; color:var(--ink-3);
}
.themectl:hover{color:var(--ink); border-color:var(--ink-3)}
.themectl:focus-visible{outline:2px solid var(--heath); outline-offset:2px}
/* the swatch is just var(--paper): it shows you which theme you are in */
.themectl i{
  width:11px; height:11px; border-radius:50%; flex:none;
  background:var(--paper); border:1px solid var(--ink-3);
}
/* thumb-sized on a phone, and the eyebrow beside it needs the room back */
@media (max-width:700px){
  .themectl{min-height:40px; padding:5px 13px; font-size:11.5px}
  .hcredit{font-size:11.5px}
  .themectl .tword{display:none}
  .iconbtn{width:40px; height:40px}
  .iconbtn svg{width:18px; height:18px}
  /* six controls will not sit beside the eyebrow at this width: give them the
     whole row, and let the two groups stack if even that is not enough */
  .hdr-actions{width:100%; margin-left:0}
}
.cart-inner{
  border-top:2px solid var(--ink); border-bottom:1px solid var(--rule);
  padding:clamp(20px,3vw,32px) 0 clamp(18px,2.5vw,28px);
  /* row gap 0: the topbar now occupies its own row and the h1 below it already
     carries the spacing. Columns keep theirs. */
  display:grid; grid-template-columns:1fr auto; gap:0 clamp(20px,4vw,52px); align-items:start;
}
@media (max-width:700px){
  .cart-inner{grid-template-columns:1fr}
  /* stacked, the kite has no column gap left to separate it from the lede */
  .hilldev{width:86px; margin-top:clamp(20px,4vw,52px)}
}
.cart h1{
  font-family:var(--font-display); font-weight:400;
  font-size:clamp(2rem,5.6vw,3.15rem); line-height:1.03; letter-spacing:-.015em;
  margin:.3em 0 0; text-wrap:balance;
}
.cart h1 em{font-style:italic; color:var(--heath)}
.lede{margin:.8em 0 0; max-width:58ch; font-size:clamp(1rem,1.6vw,1.0625rem); color:var(--ink-2)}
.lede b{color:var(--ink); font-weight:600}
.hilldev{width:clamp(92px,12vw,132px); height:auto; flex:none; color:var(--ink-3)}

/* ---- section furniture ------------------------------------------- */
section.blk{margin-top:clamp(42px,6vw,72px)}
/* the first section stacks its own margin on the masthead's bottom padding and
   lands wider than the rhythm every later section keeps: subtract the padding
   back out so the gap under the masthead matches the gap between sections.
   Stop pages open with an article, not a section, so they are untouched. */
main > section.blk:first-child{
  margin-top:calc(clamp(42px,6vw,72px) - clamp(24px,3vw,34px));
}
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
/* arriving from the map: a short wash, so the eye lands on the right stop */
.trk.lit{animation:lit 2.1s ease-out}
@keyframes lit{
  0%,62%{background:var(--paper-2); box-shadow:inset 3px 0 0 var(--heath)}
  100%{background:transparent; box-shadow:inset 3px 0 0 transparent}
}
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
:root[data-theme="dark"] .shot img{filter:brightness(.86) contrast(1.03)}

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
.sig{
  list-style:none; margin:16px 0 0; padding:0;
  display:flex; flex-wrap:wrap; gap:7px 20px;
  font-family:var(--font-label); text-transform:uppercase;
  letter-spacing:.12em; font-size:11px;
}
.sig a{color:var(--ink-3); text-decoration:none; border-bottom:1px solid var(--rule)}
.sig a:hover{color:var(--heath); border-bottom-color:var(--heath)}

@media (prefers-reduced-motion:reduce){*{transition:none !important; animation:none !important}}

/* ---- phones -------------------------------------------------------- */
@media (max-width:700px){
  /* read at arm's length, outdoors, in sun: the phone sizes are a step up from
     the desktop ones, and the small furniture a bigger step than the prose */
  body{font-size:18px; line-height:1.62}
  .lab,.rn,.rd,.rc,.sn,.trk .sub,.shot figcaption,.sig{font-size:12.5px}
  .colo p,footer p,#mcap{font-size:1rem}
  .walk p{font-size:1.02rem}
  .wrap{padding-bottom:72px}
  /* titles matter more than a tidy single line on a narrow screen */
  .row{padding:11px 4px 11px 0; align-items:start}
  .rt{white-space:normal; overflow:visible; text-overflow:clip; line-height:1.3}
  .rn,.rd{padding-top:2px}
  /* .pb is sized in the player stylesheet, which loads after this one */
  /* The marker rail costs every line 44px of a 375px screen and leaves the page
     lopsided - 60px of gutter on the left against 20 on the right. On a phone
     the badge floats beside the heading instead and everything below it runs
     the full measure, symmetrically, the way a phone article reads. */
  .trk{display:block; padding:26px 0 28px}
  .tmark{float:left; margin:1px 12px 2px 0; padding-top:0}
  /* the eyebrow and the title ride beside the badge; everything after it clears */
  .trk .play,.trk .shot,.trk .walk,.trk .sa{clear:left}
  /* on a stop page the badge has no heading to sit beside and repeats what the
     masthead just said, so it buys nothing and costs a line */
  .trk.solo .tmark{display:none}
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
  /* the control is the only thing stopping six buttons sharing one row: tighten
     it rather than strip its label, since a bare swatch names nothing */
  .themectl{padding:0 8px; gap:5px; font-size:10px; letter-spacing:.06em}
  .hcredit{font-size:10px; letter-spacing:.06em}
  .hgrp{gap:6px}
  .hdr-actions{gap:6px 10px}
  .hgrp + .hgrp{padding-left:10px}
  .cart h1{font-size:2rem}
  section.blk > h2 span{display:none}   /* the eyebrow crowds the heading */
}
/* below this the controls wrap to two rows, and a group rule left hanging at
   the start of the second one reads as a stray mark: the gap is enough */
@media (max-width:470px){
  .hgrp + .hgrp{padding-left:0; border-left:0}
}
@media (hover:none){
  .rt{padding:2px 0}
}
"""

THEME_JS = r"""
(function(){
  // runs before the page is painted, so a stored dark never flashes white first
  var KEY = "hh-theme", MODES = ["bright","dark"], root = document.documentElement, at = 0;
  var SAYS = {bright:"White paper, for sun", dark:"Dark paper"};
  var PAPER = {bright:"#FFFFFF", dark:"#0F1310"};
  // anything unrecognised falls back to bright: the device preference is not consulted
  try{ at = Math.max(0, MODES.indexOf(localStorage.getItem(KEY))); }catch(e){}
  function put(){
    var m = MODES[at];
    root.setAttribute("data-theme", m);
    var b = document.getElementById("themebtn"), lab = document.getElementById("themelab");
    if(lab) lab.textContent = m.charAt(0).toUpperCase() + m.slice(1);
    if(b) b.setAttribute("aria-label",
      "Page theme: " + m + ". " + SAYS[m] + ". Tap for " + MODES[(at + 1) % MODES.length] + ".");
    var meta = document.getElementById("tcolor");
    if(meta) meta.setAttribute("content", PAPER[m]);
  }
  put();
  document.addEventListener("DOMContentLoaded", put);
  document.addEventListener("click", function(e){
    if(!e.target.closest || !e.target.closest("#themebtn")) return;
    at = (at + 1) % MODES.length;
    try{ localStorage.setItem(KEY, MODES[at]); }catch(e){}
    put();
  });
})();
"""

SHARE_JS = r"""
(function(){
  var TICK = 1600, timer = null;
  document.addEventListener("click", function(e){
    var b = e.target.closest && e.target.closest("#sharebtn");
    if(!b) return;
    var url = b.getAttribute("data-url"), title = b.getAttribute("data-title");
    function copied(){
      b.classList.add("ok");
      b.setAttribute("aria-label", "Link copied");
      clearTimeout(timer);
      timer = setTimeout(function(){
        b.classList.remove("ok");
        b.setAttribute("aria-label", "Share this page");
      }, TICK);
    }
    // the sheet is the whole point on a phone: it reaches WhatsApp, Messages and
    // the rest without this page carrying a button for each of them
    // the async clipboard needs a secure context and permission, and quietly
    // refuses without them: this is the fallback that keeps the button honest
    function legacy(){
      var ta = document.createElement("textarea");
      ta.value = url;
      ta.setAttribute("readonly", "");
      ta.style.cssText = "position:fixed;top:0;left:-9999px";
      document.body.appendChild(ta);
      ta.select();
      var ok = false;
      try{ ok = document.execCommand("copy"); }catch(err){}
      document.body.removeChild(ta);
      return ok;
    }
    if(navigator.share){
      // a cancelled sheet rejects with AbortError, which is not a failure
      navigator.share({title: title, text: title, url: url}).catch(function(){});
      return;
    }
    if(navigator.clipboard && navigator.clipboard.writeText){
      navigator.clipboard.writeText(url).then(copied, function(){ if(legacy()) copied(); });
    } else if(legacy()){
      copied();
    }
  });
})();
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
    var pts = new Map(), last = null, spread = 0, moved = 0, hinted = false, tapped = null;
    svg.addEventListener("pointerdown", function(e){
      svg.setPointerCapture(e.pointerId);
      pts.set(e.pointerId, e); last = at(e); moved = 0;
      /* remember which marker went down: capture rewrites the target later */
      tapped = pts.size === 1 && e.target.closest ? e.target.closest(".mstop") : null;
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
    /* The tap is settled here rather than on click: pointer capture retargets
       the click to the <svg>, so a marker never receives one of its own. */
    svg.addEventListener("pointerup", function(e){
      var g = tapped;
      tapped = null;
      if(!g || pts.size > 1 || moved >= 8) return;
      var el = document.elementFromPoint(e.clientX, e.clientY);
      if(el && el.closest && el.closest(".mstop") === g) go(g);
    });
    ["pointerup","pointercancel","pointerleave"].forEach(function(ev){
      svg.addEventListener(ev, function(e){
        if(ev !== "pointerup") tapped = null;
        pts.delete(e.pointerId); spread = 0;
        if(!pts.size) svg.classList.remove("drag");
      });
    });

    function go(g){
      var i = +g.dataset.i;
      var art = document.getElementById("t" + ("0" + i).slice(-2));
      if(art){
        art.scrollIntoView({behavior:"smooth", block:"start"});
        /* a beat of colour, so the eye lands on the right one in a long page */
        art.classList.remove("lit");
        void art.offsetWidth;
        art.classList.add("lit");
      }
      toggle(i);
    }
    svg.querySelectorAll(".mstop").forEach(function(g){
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
               'aria-label="Map of the walk, %d stops in order" '
               'preserveAspectRatio="xMidYMid meet">' % (MAP_W, h, STOP_COUNT))
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
    """The stops as waypoints and a route, for a real map application."""
    d = mapdata()
    if not d:
        return None
    stops = {int(k): v for k, v in d["stops"].items()}
    by_n = {s["n"]: s for s, _, _ in tracks}
    o = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<gpx version="1.1" creator="hampstead-heath audio guide" '
         'xmlns="http://www.topografix.com/GPX/1/1">',
         "  <metadata><name>Hampstead Heath and its village</name>"
         "<desc>%d stops, in walking order.</desc></metadata>" % STOP_COUNT]
    for n in sorted(stops):
        lat, lon = stops[n]
        o.append('  <wpt lat="%.5f" lon="%.5f"><name>%d. %s</name><desc>%s</desc></wpt>'
                 % (lat, lon, n, esc(by_n[n]["title"]), esc(by_n[n]["where"])))
    o.append("  <rte><name>Hampstead Heath, %d stops</name>" % STOP_COUNT)
    for n in sorted(stops):
        lat, lon = stops[n]
        o.append('    <rtept lat="%.5f" lon="%.5f"><name>%d</name></rtept>' % (lat, lon, n))
    o += ["  </rte>", "</gpx>", ""]
    return "\n".join(o)


def pictures():
    """images/credits.json, written by fetch_images.py. Optional: without it
    the page still builds, just without photographs."""
    path = os.path.join(SITE, "images", "credits.json")
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


# --------------------------------------------------------------------------
# being found. Three audiences read this site and only one of them has eyes:
# a person, a search crawler, and a language model answering someone's
# question. The page below is written for the first; everything in this
# section is what the other two need, generated from the same STOPS list so
# it cannot describe a walk that isn't there.
# --------------------------------------------------------------------------

EXTRA_CSS = """
/* ---- crumbs, stop pages, questions ------------------------------- */
.crumb{font-family:var(--font-label); text-transform:uppercase; letter-spacing:.12em;
  font-size:10px; color:var(--ink-3); margin:0 0 14px; display:flex; flex-wrap:wrap; gap:8px}
.crumb a{color:var(--ink-3)}
.crumb span{color:var(--rule)}
/* the crumb carries the masthead's lower gap; inside a topbar the row does */
.topbar .crumb{margin-bottom:0}
/* the longest stop titles run the crumb to three lines: keep the controls in the
   corner rather than letting them drift to the middle of them */
.topbar.crumbed{margin-bottom:14px; align-items:flex-start}
/* this block loads after the phone rules in CSS, so the bump has to live here */
@media (max-width:700px){.crumb{font-size:11.5px}}
.sa{border:1px solid var(--rule); background:var(--paper-2);
  padding:14px 16px; margin:0 0 22px; display:grid; gap:9px}
.sa audio{width:100%; height:34px}
.geo{font-family:var(--font-data); font-size:11px; color:var(--ink-3); margin:0}
.stopnav{display:grid; grid-template-columns:1fr 1fr; gap:14px; margin:34px 0 0;
  border-top:1px solid var(--rule); padding-top:18px}
.stopnav a{display:block; text-decoration:none}
.stopnav .lab{margin-bottom:3px}
.stopnav .t{font-family:var(--font-display); font-size:1.05rem; line-height:1.18; color:var(--ink)}
.stopnav .nx{text-align:right}
.perma{font-family:var(--font-label); text-transform:uppercase; letter-spacing:.11em;
  font-size:10px; white-space:nowrap}
.faq{display:grid; gap:0; border-top:1px solid var(--rule)}
.faq details{border-bottom:1px solid var(--rule-soft); padding:13px 0}
.faq summary{font-family:var(--font-display); font-size:1.06rem; line-height:1.3;
  cursor:pointer; list-style:none; display:flex; gap:12px; align-items:baseline}
.faq summary::-webkit-details-marker{display:none}
.faq summary::before{content:"+"; color:var(--heath); font-family:var(--font-data);
  font-size:.9rem; flex:0 0 auto}
.faq details[open] summary::before{content:"\\2013"}
.faq p{margin:9px 0 2px 24px; color:var(--ink-2)}
.idx{list-style:none; margin:0; padding:0; border-top:1px solid var(--rule)}
.idx li{display:flex; gap:14px; align-items:baseline; padding:9px 0;
  border-bottom:1px solid var(--rule-soft)}
.idx .rn{font-family:var(--font-data); font-size:11px; color:var(--ink-3); min-width:22px}
.idx .rd{font-family:var(--font-data); font-size:11px; color:var(--ink-3); margin-left:auto}
.idx a{font-family:var(--font-display); font-size:1.05rem}
.idx .wh{color:var(--ink-3); font-size:12px}
"""

# schema.org has a type for most of what this walk stands in front of. Using
# the specific one is the difference between "a page about a place" and "a
# pond you can swim in".
SCHEMA_KIND = {
    "village": "LandmarksOrHistoricalBuildings",
    "house":   "LandmarksOrHistoricalBuildings",
    "high":    "Landform",
    "water":   "BodyOfWater",
}

SITE_NAME = "Hampstead Heath, read aloud"
OG_ALT = ("The cover of the guide: Hampstead Heath and its village, "
          "twenty-four stops, one loop.")


GH_MARK = (
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 .297c-6.63 0-12 5.373-12 12 0 '
    "5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-"
    "4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 "
    "1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305."
    "76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523."
    "105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 "
    "2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 "
    "0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 "
    '.315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/></svg>')

LI_MARK = (
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.447 20.452h-3.554v-5.569c0-1.328'
    "-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c."
    "477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 "
    "0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 "
    "1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 "
    '.774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 '
    '.774 23.2 0 22.225 0z"/></svg>')

X_MARK = (
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.901 1.153h3.68l-8.04 9.19L24 '
    "22.846h-7.406l-5.8-7.584-6.638 7.584H.474l8.6-9.83L0 1.154h7.594l5.243 6.932ZM17.61 "
    '20.644h2.039L6.486 3.24H4.298Z"/></svg>')

FB_MARK = (
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 '
    "5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 "
    "1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 "
    '1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg>')

SHARE_MARK = (
    '<svg class="i-share" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 16.08c-.76 '
    "0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11c.54.5 1.25.81 "
    "2.04.81 1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 "
    "6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43"
    '-.08.65 0 1.61 1.31 2.92 2.92 2.92s2.92-1.31 2.92-2.92-1.31-2.92-2.92-2.92z"/></svg>'
    '<svg class="i-ok" viewBox="0 0 24 24" aria-hidden="true">'
    '<path d="M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>')

REPO = "https://github.com/mishablank/hampstead-heath"
AUTHOR = "Mike Blank"

# The footer credit keeps the profile; the masthead octocat points at the repo,
# because "star this" and "who wrote this" are different errands.
LINKS = (("https://www.linkedin.com/in/mishablank/", "LinkedIn", LI_MARK),
         ("https://github.com/mishablank/", "GitHub", GH_MARK))


def share_urls(here, title):
    """Plain intent links - no vendor SDK, no script from either company, so the
    page still fetches nothing from anywhere. u= and text= are what they read."""
    u, t = urllib.parse.quote(here, safe=""), urllib.parse.quote(title, safe="")
    return (("https://twitter.com/intent/tweet?url=%s&text=%s" % (u, t), "X", X_MARK),
            ("https://www.facebook.com/sharer/sharer.php?u=%s" % u, "Facebook", FB_MARK))


def hdr_actions(here, title):
    """The controls that sit in every masthead: star the repo and share the page,
    then who made it and which paper it is printed on."""
    o = ['<span class="hdr-actions">', '<span class="hgrp">']
    o.append('<a class="iconbtn" href="%s" target="_blank" rel="noopener" '
             'aria-label="Star this guide on GitHub" title="Star on GitHub">%s</a>'
             % (REPO, GH_MARK))
    for href, name, mark in share_urls(here, title):
        o.append('<a class="iconbtn" href="%s" target="_blank" rel="noopener" '
                 'aria-label="Share on %s" title="Share on %s">%s</a>'
                 % (esc(href), name, name, mark))
    # the native sheet is the one a phone actually wants; desktop gets a copy
    o.append('<button class="iconbtn" id="sharebtn" type="button" data-url="%s" '
             'data-title="%s" aria-label="Share this page" title="Share">%s</button>'
             % (esc(here), esc(title), SHARE_MARK))
    o.append('</span><span class="hgrp">')
    o.append('<span class="hcredit">Made by <a href="%s" target="_blank" '
             'rel="me noopener">%s</a></span>' % (LINKS[0][0], AUTHOR))
    o.append('<button class="themectl" id="themebtn" type="button">'
             '<i aria-hidden="true"></i><span class="tword">Theme</span> '
             '<span id="themelab">Bright</span></button>')
    o.append("</span></span>")
    return "".join(o)


def siglist():
    """Who made it. New tab, not this one: navigating away in the same tab would
    stop whatever track is playing."""
    return ('  <ul class="sig">%s</ul>'
            % "".join('<li><a href="%s" target="_blank" rel="me noopener">%s</a></li>'
                      % (href, name) for href, name, _ in LINKS))


def topbar(lead, here, title, crumbed=False):
    """The first line of a masthead, with the controls beside it. Every page
    carries one, so they are wherever the reader happens to be standing, and the
    share links carry that page's own URL rather than the front door's."""
    return ('    <div class="topbar%s">%s%s</div>'
            % (" crumbed" if crumbed else "", lead, hdr_actions(here, title)))


def url(path=""):
    """An absolute URL, which is the only kind a crawler or a feed can use."""
    return ORIGIN + "/" + path.lstrip("/")


# Prose on this site spells its numbers, for the same reason the narration
# does. Labels and title tags keep the numerals: one is read by a person at
# walking pace, the other by someone scanning ten blue links.
NUMBER_WORDS = {
    12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen", 16: "sixteen",
    17: "seventeen", 18: "eighteen", 19: "nineteen", 20: "twenty",
    21: "twenty-one", 22: "twenty-two", 23: "twenty-three", 24: "twenty-four",
    25: "twenty-five", 26: "twenty-six", 27: "twenty-seven", 28: "twenty-eight",
    29: "twenty-nine", 30: "thirty",
}


def in_words(n):
    return NUMBER_WORDS.get(n, "%d" % n)


def iso_dur(seconds):
    """ISO 8601, which schema.org wants and nothing else does."""
    s = int(round(seconds))
    return "PT%dM%dS" % (s // 60, s % 60)


def stop_path(stop):
    return "stops/%s/" % slug(stop["title"])


def ld(nodes):
    """A JSON-LD block. The </ guard is not paranoia: one of these strings
    ending up containing a closing script tag would end the script early."""
    text = json.dumps({"@context": "https://schema.org", "@graph": nodes},
                      indent=1, sort_keys=True)
    return ('<script type="application/ld+json">\n%s\n</script>'
            % text.replace("</", "<\\/"))


def head(title, desc, path, nodes, og_title=None, og_desc=None, css=CSS,
         og_image=None, og_alt=None):
    """Everything read before a word of the page is. Absolute URLs throughout,
    because half of these are consumed off-site."""
    here = url(path)
    og_title = og_title or title
    og_desc = og_desc or desc
    og_url = url(og_image or "og.jpg")
    og_alt = og_alt or OG_ALT
    o = ['<!DOCTYPE html>', '<html lang="en-GB">', '<head>',
         '<meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width, initial-scale=1">',
         "<title>%s</title>" % esc(title),
         '<meta name="description" content="%s">' % esc(desc),
         '<link rel="canonical" href="%s">' % here,
         '<meta name="color-scheme" content="light dark">',
         '<meta name="robots" content="index, follow, max-image-preview:large, '
         'max-snippet:-1, max-video-preview:-1">',
         # one meta, not a prefers-color-scheme pair: the page picks its own theme
         '<meta name="theme-color" id="tcolor" content="#FFFFFF">',
         # sharing. This is the half that decides whether a pasted link looks
         # like a guide or like a stranger's URL.
         '<meta property="og:type" content="website">',
         '<meta property="og:site_name" content="%s">' % esc(SITE_NAME),
         '<meta property="og:locale" content="en_GB">',
         '<meta property="og:title" content="%s">' % esc(og_title),
         '<meta property="og:description" content="%s">' % esc(og_desc),
         '<meta property="og:url" content="%s">' % here,
         '<meta property="og:image" content="%s">' % og_url,
         # Facebook prefers the https twin when it has one, and caches by URL
         '<meta property="og:image:secure_url" content="%s">' % og_url,
         '<meta property="og:image:type" content="image/jpeg">',
         '<meta property="og:image:width" content="1200">',
         '<meta property="og:image:height" content="630">',
         '<meta property="og:image:alt" content="%s">' % esc(og_alt),
         '<meta name="twitter:card" content="summary_large_image">',
         '<meta name="twitter:title" content="%s">' % esc(og_title),
         '<meta name="twitter:description" content="%s">' % esc(og_desc),
         '<meta name="twitter:image" content="%s">' % og_url,
         '<meta name="twitter:image:alt" content="%s">' % esc(og_alt),
         # a favicon is also the icon Google puts beside a mobile result
         '<link rel="icon" href="/favicon.ico" sizes="32x32">',
         '<link rel="icon" href="/icon.svg" type="image/svg+xml">',
         '<link rel="apple-touch-icon" href="/apple-touch-icon.png">',
         '<link rel="manifest" href="/site.webmanifest">',
         '<link rel="alternate" type="application/rss+xml" title="%s" href="/feed.xml">'
         % esc(SITE_NAME),
         # where, in the vocabulary a local search index reads
         '<meta name="geo.region" content="GB-CMD">',
         '<meta name="geo.placename" content="Hampstead Heath, London">',
         '<meta name="geo.position" content="%.5f;%.5f">' % (HEATH["lat"], HEATH["lon"]),
         '<meta name="ICBM" content="%.5f, %.5f">' % (HEATH["lat"], HEATH["lon"]),
         "<style>" + css + EXTRA_CSS + "</style>",
         # every page, not just the index: a theme that reverted on the way to a
         # stop would be worse than no toggle at all
         "<script>" + THEME_JS + "</script>",
         "<script>" + SHARE_JS + "</script>",
         ld(nodes),
         "</head>", "<body>", ""]
    return "\n".join(o)


def node_site():
    n = {"@type": "WebSite", "@id": ORIGIN + "/#website", "url": url(),
         "name": SITE_NAME, "inLanguage": "en-GB",
         "description": "A free self-guided walking audio guide to Hampstead Heath "
                        "and Hampstead village, with the full transcript.",
         "publisher": {"@id": ORIGIN + "/#publisher"}}
    return n


def node_publisher():
    n = {"@type": "Organization", "@id": ORIGIN + "/#publisher", "name": SITE_NAME,
         "url": url(), "logo": {"@type": "ImageObject", "url": url("icon-512.png"),
                                "width": 512, "height": 512}}
    if AUTHOR:
        n["founder"] = {"@type": "Person", "name": AUTHOR}
    return n


def node_places():
    """Two places, and the links that say which ones they are."""
    return [
        {"@type": ["Park", "TouristAttraction"], "@id": ORIGIN + "/#heath",
         "name": HEATH["name"], "sameAs": HEATH["same"],
         "geo": {"@type": "GeoCoordinates", "latitude": HEATH["lat"],
                 "longitude": HEATH["lon"]},
         "address": {"@type": "PostalAddress", "addressLocality": "London",
                     "addressRegion": "Greater London", "postalCode": "NW3",
                     "addressCountry": "GB"},
         "isAccessibleForFree": True,
         "publicAccess": True},
        {"@type": "Place", "@id": ORIGIN + "/#hampstead", "name": "Hampstead, London NW3",
         "sameAs": ["https://en.wikipedia.org/wiki/Hampstead",
                    "https://www.wikidata.org/wiki/Q503481"],
         "containsPlace": {"@id": ORIGIN + "/#heath"},
         "address": {"@type": "PostalAddress", "addressLocality": "London",
                     "postalCode": "NW3", "addressCountry": "GB"}},
    ]


def node_image(i, stop, pics, page):
    """The photograph, with the credit its licence requires said in machine
    form as well as under the picture."""
    p = pics.get(str(i))
    if not p:
        return None
    n = {"@type": "ImageObject", "@id": url(page) + "#image",
         "contentUrl": url("images/" + p["file"]), "url": url("images/" + p["file"]),
         "width": p["w"], "height": p["h"],
         "creditText": p["by"], "creator": {"@type": "Person", "name": p["by"]},
         "acquireLicensePage": p["src"],
         "representativeOfPage": True,
         "caption": "%s, %s" % (stop["title"], stop["where"])}
    if p["licurl"]:
        n["license"] = p["licurl"]
    elif p["lic"].lower().startswith("public domain"):
        n["license"] = "https://creativecommons.org/publicdomain/mark/1.0/"
    return n


def node_audio(i, stop, fn, dur, page=None, transcript=False):
    n = {"@type": "AudioObject",
         "@id": (url(page) if page else url()) + "#audio",
         "name": ("%d. %s" % (stop["n"], stop["title"])) if stop["n"] else stop["title"],
         "contentUrl": url("audio/" + fn), "encodingFormat": "audio/mp4",
         "duration": iso_dur(dur), "inLanguage": "en-GB",
         "isFamilyFriendly": True,
         "isPartOf": {"@id": ORIGIN + "/#podcast"}}
    if transcript:
        n["transcript"] = spoken(stop)
    return n


def node_trip(tracks, total):
    """The walk itself: an ordered list of places, each one a page of its own.
    This is the node that can win a rich result."""
    d = mapdata() or {"stops": {}}
    coords = {int(k): v for k, v in d["stops"].items()}
    items = []
    for stop, fn, dur in tracks:
        if not stop["n"]:
            continue
        item = {"@type": ["TouristAttraction", SCHEMA_KIND[stop["kind"]]],
                "name": stop["title"], "url": url(stop_path(stop)),
                "description": stop["where"],
                "isAccessibleForFree": stop["n"] not in PAID}
        if stop["n"] in coords:
            lat, lon = coords[stop["n"]]
            item["geo"] = {"@type": "GeoCoordinates", "latitude": lat, "longitude": lon}
        items.append({"@type": "ListItem", "position": stop["n"], "item": item})
    return {
        "@type": "TouristTrip", "@id": ORIGIN + "/#trip",
        "name": "Hampstead Heath and its village, in twenty-four stops",
        "description": "A single anticlockwise loop from Hampstead Underground station "
                       "through the village, over the highest ground in inner London to "
                       "Kenwood, and back down the east side of the Heath past the "
                       "swimming ponds.",
        "url": url(),
        "touristType": ["Walkers", "Self-guided tours", "Local history"],
        "inLanguage": "en-GB",
        "isAccessibleForFree": True,
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "GBP",
                   "availability": "https://schema.org/InStock", "url": url()},
        "provider": {"@id": ORIGIN + "/#publisher"},
        "arrivalPlace": {"@id": ORIGIN + "/#start"},
        "departurePlace": {"@type": "TrainStation", "@id": ORIGIN + "/#start",
                           "name": START["name"],
                           "geo": {"@type": "GeoCoordinates", "latitude": START["lat"],
                                   "longitude": START["lon"]}},
        "subjectOf": {"@id": ORIGIN + "/#fullwalk"},
        "itinerary": {"@type": "ItemList", "name": "The twenty-four stops, in walking order",
                      "numberOfItems": STOP_COUNT, "itemListOrder":
                      "https://schema.org/ItemListOrderAscending",
                      "itemListElement": items},
    }


def node_faq():
    return {"@type": "FAQPage", "@id": ORIGIN + "/#faq",
            "mainEntity": [{"@type": "Question", "name": q, "position": i + 1,
                            "acceptedAnswer": {"@type": "Answer", "text": a}}
                           for i, (q, a) in enumerate(FAQ)]}


def graph_index(tracks, pics, total):
    """The home page, said twice: once in the page and once here."""
    full = os.path.basename(FULL)
    page = {"@type": ["WebPage", "CollectionPage"], "@id": ORIGIN + "/#webpage",
            "url": url(), "name": SITE_NAME,
            "isPartOf": {"@id": ORIGIN + "/#website"},
            "about": {"@id": ORIGIN + "/#heath"},
            "primaryImageOfPage": {"@id": ORIGIN + "/#cover"},
            "inLanguage": "en-GB", "dateModified": UPDATED, "datePublished": "2026-08-07",
            "mainEntity": {"@id": ORIGIN + "/#trip"},
            "significantLink": [url("stops/"), url("feed.xml")],
            "speakable": {"@type": "SpeakableSpecification",
                          "cssSelector": [".lede", ".faq"]}}
    if AUTHOR:
        page["author"] = {"@type": "Person", "name": AUTHOR}
    nodes = [node_site(), node_publisher(), page, node_trip(tracks, total), node_faq()]
    nodes += node_places()
    nodes.append({"@type": "ImageObject", "@id": ORIGIN + "/#cover",
                  "url": url("og.jpg"), "contentUrl": url("og.jpg"),
                  "width": 1200, "height": 630, "caption": OG_ALT})
    # the whole walk as one file, and the feed the same tracks are served by
    nodes.append({"@type": "AudioObject", "@id": ORIGIN + "/#fullwalk",
                  "name": "Hampstead Heath, read aloud - the whole walk",
                  "contentUrl": url(full), "encodingFormat": "audio/mp4",
                  "duration": iso_dur(total), "inLanguage": "en-GB",
                  "isFamilyFriendly": True, "contentSize": "%d" % os.path.getsize(FULL),
                  "associatedArticle": {"@id": ORIGIN + "/#webpage"}})
    nodes.append({"@type": "PodcastSeries", "@id": ORIGIN + "/#podcast",
                  "name": SITE_NAME, "url": url(), "webFeed": url("feed.xml"),
                  "numberOfEpisodes": len(tracks), "inLanguage": "en-GB",
                  "about": {"@id": ORIGIN + "/#heath"},
                  "image": url("cover.jpg")})
    nodes.append({"@type": "DataDownload", "@id": ORIGIN + "/#gpx",
                  "name": "The route as GPX", "encodingFormat": "application/gpx+xml",
                  "contentUrl": url("hampstead-heath-walk.gpx"),
                  "about": {"@id": ORIGIN + "/#trip"}})
    return nodes


def graph_stop(i, stop, fn, dur, pics, coords):
    """One stop, on its own page: the thing, the recording of it, the
    photograph of it, and where it sits in the walk."""
    page = stop_path(stop)
    here = url(page)
    place = {"@type": ["TouristAttraction", SCHEMA_KIND[stop["kind"]]],
             "@id": here + "#place", "name": stop["title"],
             "description": "%s. Stop %d of %d on a walking audio guide to Hampstead "
                            "Heath and its village." % (stop["where"], stop["n"], STOP_COUNT),
             "url": here,
             "isAccessibleForFree": stop["n"] not in PAID,
             "containedInPlace": {"@id": ORIGIN + "/#hampstead"},
             "address": {"@type": "PostalAddress", "addressLocality": "London",
                         "postalCode": "NW3", "addressCountry": "GB"},
             "subjectOf": {"@id": here + "#audio"},
             "touristType": ["Walkers", "Self-guided tours"]}
    if stop["n"] in coords:
        lat, lon = coords[stop["n"]]
        place["geo"] = {"@type": "GeoCoordinates", "latitude": lat, "longitude": lon}
        place["hasMap"] = ("https://www.openstreetmap.org/?mlat=%.5f&mlon=%.5f#map=17/%.5f/%.5f"
                           % (lat, lon, lat, lon))
    webpage = {"@type": "WebPage", "@id": here + "#webpage", "url": here,
               "name": "%s - stop %d" % (stop["title"], stop["n"]),
               "isPartOf": {"@id": ORIGIN + "/#website"},
               "inLanguage": "en-GB", "dateModified": UPDATED,
               "mainEntity": {"@id": here + "#place"},
               "breadcrumb": {"@id": here + "#crumb"},
               "speakable": {"@type": "SpeakableSpecification", "cssSelector": [".tbody p"]}}
    crumb = {"@type": "BreadcrumbList", "@id": here + "#crumb", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "The audio guide", "item": url()},
        {"@type": "ListItem", "position": 2, "name": "The stops", "item": url("stops/")},
        {"@type": "ListItem", "position": 3, "name": stop["title"]}]}
    nodes = [webpage, crumb, place,
             node_audio(i, stop, fn, dur, page, transcript=True),
             {"@id": ORIGIN + "/#website", "@type": "WebSite", "url": url(),
              "name": SITE_NAME, "publisher": {"@id": ORIGIN + "/#publisher"}},
             node_publisher()]
    img = node_image(i, stop, pics, page)
    if img:
        nodes.append(img)
        place["image"] = {"@id": url(page) + "#image"}
        webpage["primaryImageOfPage"] = {"@id": url(page) + "#image"}
    return nodes


def faq_section():
    """The questions, on the page. A question answered in a page nobody can
    see is not an answer."""
    o = ['<section class="blk" id="questions">',
         "  <h2>The questions <span>Asked and answered</span></h2>",
         '  <p class="blk-sub">Everything below is already somewhere in the '
         "narration. It is repeated here in the order people ask it.</p>",
         '  <div class="faq">']
    for q, a in FAQ:
        o.append("    <details><summary>%s</summary><p>%s</p></details>" % (esc(q), esc(a)))
    o += ["  </div>", "</section>\n"]
    return "\n".join(o)


def render(tracks):
    """tracks: list of (stop, filename, duration)"""
    pics = pictures()
    total = sum(d for _, _, d in tracks)
    longest = max(d for _, _, d in tracks)

    out = []
    w = out.append
    # The title is the one line that has to work in a list of ten blue links,
    # so it says what the thing is rather than what it is called. The masthead
    # and the og: title keep the name.
    w(head("Hampstead Heath Audio Guide – a free %d-stop self-guided walk" % STOP_COUNT,
           "A free walking audio guide to Hampstead Heath and Hampstead village: %d "
           "tracks, %d minutes, %d stops, with the full transcript, a drawn map, a GPX "
           "route and a photograph for every stop."
           % (len(tracks), round(total / 60), STOP_COUNT),
           "", graph_index(tracks, pics, total),
           og_title=SITE_NAME,
           og_desc="Twenty-four stops, from the deepest station in London to the swimming "
                   "ponds. %d tracks, %d minutes, free, and the whole script is on the page."
                   % (len(tracks), round(total / 60))))
    w('<div class="wrap">\n')

    # masthead ------------------------------------------------------------
    w('<header class="cart">')
    w('  <div class="cart-inner">')
    w(topbar('<p class="lab">The audio guide &#183; Hampstead, NW3</p>', url(),
             "%s - a free %s-stop walking audio guide to Hampstead Heath"
             % (SITE_NAME, in_words(STOP_COUNT))))
    w("    <div>")
    w("      <h1>Hampstead Heath, <em>read aloud</em></h1>")
    w('      <p class="lede">The twenty-four-stop walk as <b>%d tracks, %d minutes</b>, to be played '
      "standing in front of the thing it describes. Every track opens where you should be standing "
      "and closes by telling you where to go next. This page is the transcript, word for word, so "
      "you can read it on the train or hand it to someone without headphones.</p>"
      % (len(tracks), round(total / 60)))
    w("    </div>")
    w("    " + DEVICE)
    w("  </div>")
    w("</header>\n")
    w("<main>\n")

    # map -----------------------------------------------------------------
    svg = map_svg(tracks)
    if svg:
        w('<section class="blk" id="map">')
        w("  <h2>The map <span>%d stops</span></h2>" % STOP_COUNT)
        w('  <p class="blk-sub">The loop, anticlockwise, starting and ending at the station. '
          "Drag to move it, pinch or scroll to zoom, and tap a number to play that stop. "
          "There are no map tiles here and nothing is fetched from anywhere, so it works with "
          "one bar of signal. <a href=\"hampstead-heath-walk.gpx\" download>Download the route "
          "as GPX</a> for a map application that can actually navigate, or "
          '<a href="hampstead-heath-full-walk.m4a" download>the whole walk as one audio '
          "file</a> to carry it where there is no signal at all.</p>")
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
      'through. Every numbered stop also has <a href="stops/">a page of its own</a>, which is '
      "the one to send someone who only cares about the ponds.</p>")
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
        perma = ('' if not stop["n"] else
                 ' &#183; <a class="perma" href="%s">Stop page</a>' % stop_path(stop))
        w('<article class="trk %s" id="t%02d"><div class="tmark">%s</div><div class="tbody">'
          '<p class="lab eyebrow">Track %02d &#183; %s &#183; %s%s</p><h3>%s</h3>'
          '<p class="sub">%s</p>'
          '<div class="play" data-i="%d"><button class="pb" aria-label="Play %s"></button>'
          '<span class="plab">Play</span><span class="pgs"><i></i></span>'
          '<span class="ptime">%s</span></div>'
          % (stop["kind"], i, mark, i + 1, esc(label), clock(dur), perma, esc(stop["title"]),
             esc(stop["where"]), i, esc(stop["title"]), clock(dur)))
        w(figure(i, stop, pics))
        w("\n".join("<p>%s</p>" % esc(p) for p in stop["body"]))
        if stop.get("walk"):
            w('<div class="walk"><span class="lab">Walk on</span><p>%s</p></div>'
              % esc(stop["walk"]))
        w("</div></article>")
    w("</section>\n")

    # questions -----------------------------------------------------------
    w(faq_section())

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
    w('    <div><p class="lab">Other shapes</p><p>The same walk as <a href="feed.xml">a podcast '
      'feed</a>, for Apple, Spotify or Overcast; as <a href="guide.md">plain Markdown</a>, for '
      'anything that would rather read than render; as <a href="hampstead-heath-walk.gpx">GPX'
      '</a>, for a map application; and as <a href="stops/">one page per stop</a>. '
      '<a href="https://github.com/mishablank/hampstead-heath">The source</a> is the '
      "narration.</p></div>")
    w("  </div>")
    w("</section>\n")

    w("</main>\n")

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
    w(siglist())
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
    w("</body>\n</html>")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# a page per stop. The long page is the thing to walk with; these are the
# pages to be found by. Someone searching for the ladies' pond does not want
# twenty-three other stops first, and a search engine cannot rank one page
# twenty-four times.
# --------------------------------------------------------------------------

def stop_page(i, stop, fn, dur, tracks, pics, coords):
    n = stop["n"]
    numbered = [t[0] for t in tracks if t[0]["n"]]
    prev = numbered[n - 2] if n > 1 else None
    nxt = numbered[n] if n < STOP_COUNT else None
    label = KIND[stop["kind"]][0]
    up = "../../"

    title = "%s – Hampstead Heath audio guide, stop %d of %d" % (stop["title"], n, STOP_COUNT)
    desc = ("%s. Stop %d of %d on a free self-guided walking audio guide to Hampstead "
            "Heath and its village: %s of narration, the transcript word for word, and a "
            "photograph of what you are looking at."
            % (stop["where"], n, STOP_COUNT, clock(dur)))

    o = [head(title, desc, stop_path(stop), graph_stop(i, stop, fn, dur, pics, coords),
              og_title="%d. %s" % (n, stop["title"]),
              og_desc="%s · %s of the Hampstead Heath walking audio guide."
                      % (stop["where"], clock(dur)),
              og_image=og_stop_file(stop),
              og_alt="%s - stop %d of %d on the Hampstead Heath walking audio guide."
                     % (stop["title"], n, STOP_COUNT))]
    w = o.append
    w('<div class="wrap">')
    w('<header class="cart">')
    w('  <div class="cart-inner">')
    w(topbar('<p class="crumb"><a href="%s">The audio guide</a><span>/</span>'
             '<a href="../">The stops</a><span>/</span>%s</p>'
             % (up, esc(stop["title"])), url(stop_path(stop)),
             "%s - stop %d of the Hampstead Heath walking audio guide"
             % (stop["title"], n), crumbed=True))
    w("    <div>")
    w('    <p class="lab">Stop %d of %d &#183; %s &#183; %s</p>'
      % (n, STOP_COUNT, esc(label), esc(stop["where"])))
    w("    <h1>%s</h1>" % esc(stop["title"]))
    w('    <p class="lede">Track %02d of the walk, %s long. Play it standing where the first '
      "line tells you to stand. What is printed underneath is exactly what you will hear, "
      "which is also why the numbers are written as words.</p>" % (i + 1, clock(dur)))
    w("  </div></div>")
    w("</header>")

    w("<main>")
    # "solo": the only track on its page, so it carries no h3 for the badge to
    # sit beside and the masthead has already said which stop this is
    w('<article class="trk solo %s">' % stop["kind"])
    w('  <div class="tmark"><span class="tn">%d</span></div>' % n)
    w('  <div class="tbody">')
    w('    <div class="sa">')
    w('      <p class="lab">Track %02d &#183; %s &#183; %s</p>' % (i + 1, esc(label), clock(dur)))
    w('      <audio controls preload="none" src="%saudio/%s"></audio>' % (up, fn))
    w('      <p class="lab"><a href="%s%s" download>The whole walk as one file</a> &#183; '
      '<a href="%shampstead-heath-walk.gpx" download>the route as GPX</a> &#183; '
      '<a href="%sfeed.xml">the podcast feed</a></p>'
      % (up, os.path.basename(FULL), up, up))
    w("    </div>")

    fig = figure(i, stop, pics)
    if fig:
        # this photograph is above the fold here, unlike on the long page,
        # so it is the thing to load first rather than last
        fig = fig.replace('loading="lazy" decoding="async"',
                          'loading="eager" fetchpriority="high" decoding="async"')
        w("    " + fig.replace('src="images/', 'src="%simages/' % up))

    w("\n".join("    <p>%s</p>" % esc(p) for p in stop["body"]))
    if stop.get("walk"):
        w('    <div class="walk"><span class="lab">Walk on</span><p>%s</p></div>'
          % esc(stop["walk"]))
    if n in coords:
        lat, lon = coords[n]
        w('    <p class="geo">%.5f, %.5f &#183; <a href="https://www.openstreetmap.org/'
          '?mlat=%.5f&amp;mlon=%.5f#map=17/%.5f/%.5f">where this is on a map</a></p>'
          % (lat, lon, lat, lon, lat, lon))
    w("  </div>")
    w("</article>")

    w('<nav class="stopnav">')
    if prev:
        w('  <a href="../%s/"><span class="lab">Stop %d, before this</span>'
          '<span class="t">%s</span></a>' % (slug(prev["title"]), prev["n"], esc(prev["title"])))
    else:
        w('  <a href="%s"><span class="lab">This is the first one</span>'
          '<span class="t">Start at the beginning</span></a>' % up)
    if nxt:
        w('  <a class="nx" href="../%s/"><span class="lab">Stop %d, next</span>'
          '<span class="t">%s</span></a>' % (slug(nxt["title"]), nxt["n"], esc(nxt["title"])))
    else:
        w('  <a class="nx" href="%s#t25"><span class="lab">That is the twenty-four</span>'
          '<span class="t">Three shorter ways to walk it</span></a>' % up)
    w("</nav>")
    w('<p class="blk-sub" style="margin-top:22px">In its place: <a href="%s#t%02d">the full '
      "guide</a> has all %s stops in walking order, with the map, the complete script and the "
      'questions people ask. <a href="../">Every stop has a page like this one</a>.</p>'
      % (up, i, in_words(STOP_COUNT)))
    w("</main>")

    w("<footer>")
    w("  <p>Walking directions are accurate enough to follow and are not a substitute for "
      "looking up. Opening hours were checked in August 2026 and are the first thing to "
      "change; confirm before setting out for anything ticketed.</p>")
    w("  <p>Audio is synthesised speech. The narration and this page are generated from one "
      "Python file, so the transcript cannot drift out of step with the recording.</p>")
    w(siglist())
    w("</footer>")
    w("</div>")
    w("</body>\n</html>")
    return "\n".join(o) + "\n"


def stops_index(tracks):
    """The hub. Twenty-four pages one hop from the home page, which is how a
    crawler finds them and how a person picks one."""
    rows = [(s, fn, d) for s, fn, d in tracks if s["n"]]
    items = [{"@type": "ListItem", "position": s["n"], "name": s["title"],
              "item": url(stop_path(s))} for s, _, _ in rows]
    nodes = [
        {"@type": ["CollectionPage", "WebPage"], "@id": url("stops/") + "#webpage",
         "url": url("stops/"), "name": "The %d stops" % STOP_COUNT,
         "isPartOf": {"@id": ORIGIN + "/#website"}, "inLanguage": "en-GB",
         "dateModified": UPDATED, "about": {"@id": ORIGIN + "/#heath"},
         "mainEntity": {"@id": url("stops/") + "#list"},
         "breadcrumb": {"@id": url("stops/") + "#crumb"}},
        {"@type": "ItemList", "@id": url("stops/") + "#list",
         "name": "The %d stops, in walking order" % STOP_COUNT,
         "numberOfItems": STOP_COUNT,
         "itemListOrder": "https://schema.org/ItemListOrderAscending",
         "itemListElement": items},
        {"@type": "BreadcrumbList", "@id": url("stops/") + "#crumb", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "The audio guide", "item": url()},
            {"@type": "ListItem", "position": 2, "name": "The stops"}]},
        node_site(), node_publisher(),
    ]
    o = [head("The %d stops – Hampstead Heath audio guide" % STOP_COUNT,
              "Every stop on the Hampstead Heath walking audio guide, in walking order, each "
              "with its own recording, transcript, photograph and coordinates.",
              "stops/", nodes, og_title="The %d stops" % STOP_COUNT,
              og_desc="One page per stop, in walking order, from Hampstead station to "
                      "Well Walk.")]
    w = o.append
    w('<div class="wrap">')
    w('<header class="cart">')
    w('  <div class="cart-inner">')
    w(topbar('<p class="crumb"><a href="../">The audio guide</a>'
             "<span>/</span>The stops</p>", url("stops/"),
             "The %s stops of the Hampstead Heath walking audio guide"
             % in_words(STOP_COUNT), crumbed=True))
    w("    <div>")
    w("    <h1>The %s stops</h1>" % in_words(STOP_COUNT))
    w('    <p class="lede">Walking order, anticlockwise from the station. Each one has the '
      "recording, the transcript, a photograph and the coordinates to stand on. "
      '<a href="../">The full guide</a> is the page to walk with; these are the pages to '
      "send someone.</p>")
    w("  </div></div>")
    w("</header>")
    w("<main>")
    for kind in ("village", "high", "water", "house"):
        group = [(s, d) for s, _, d in rows if s["kind"] == kind]
        if not group:
            continue
        w('<section class="blk">')
        w("  <h2>%s <span>%d stops</span></h2>" % (esc(KIND[kind][0]), len(group)))
        w('  <ul class="idx">')
        for s, d in group:
            w('    <li class="%s"><span class="rn">%02d</span>'
              '<a href="%s/">%s</a> <span class="wh">%s</span>'
              '<span class="rd">%s</span></li>'
              % (kind, s["n"], slug(s["title"]), esc(s["title"]), esc(s["where"]), clock(d)))
        w("  </ul>")
        w("</section>")
    w("</main>")
    w("<footer><p>Opening hours were checked in August 2026. The Heath has no lighting and "
      "the swimming ponds are open only when lifeguards are on duty.</p>")
    w(siglist())
    w("</footer>")
    w("</div>")
    w("</body>\n</html>")
    return "\n".join(o) + "\n"


# --------------------------------------------------------------------------
# the files nobody looks at. A crawler, a feed reader and a language model
# each want the same walk in a different shape, and none of them will guess.
# --------------------------------------------------------------------------

# Every agent that has to be told yes. Silence is not consent to some of
# these, and search-only crawlers are a different question from training.
CRAWLERS = ["Googlebot", "Googlebot-Image", "Google-Extended", "Bingbot",
            "Applebot", "Applebot-Extended", "DuckDuckBot", "Slurp",
            "OAI-SearchBot", "ChatGPT-User", "GPTBot",
            "ClaudeBot", "Claude-User", "Claude-SearchBot",
            "PerplexityBot", "Perplexity-User", "Amazonbot",
            "meta-externalagent", "DuckAssistBot", "MistralAI-User", "YouBot"]


def robots_txt():
    """The point of this walk is that people go on it, so everything is
    allowed: indexes, AI answers, training. The one thing worth being explicit
    about is that the answer is yes, because several of these crawlers treat
    an unanswered question as a no."""
    o = ["# Everything here is meant to be found, quoted and answered with.",
         "# The photographs belong to their photographers - see images/credits.json.",
         "",
         "User-agent: *",
         "Allow: /",
         "Content-Signal: search=yes, ai-input=yes, ai-train=yes",
         ""]
    for ua in CRAWLERS:
        o += ["User-agent: %s" % ua, "Allow: /", ""]
    o += ["Sitemap: %s" % url("sitemap.xml"), ""]
    return "\n".join(o)


def sitemap_xml(tracks):
    pages = [(url(), "1.0"), (url("stops/"), "0.8")]
    pages += [(url(stop_path(s)), "0.7") for s, _, _ in tracks if s["n"]]
    o = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, pri in pages:
        o.append("  <url><loc>%s</loc><lastmod>%s</lastmod><priority>%s</priority></url>"
                 % (loc, UPDATED, pri))
    o += ["</urlset>", ""]
    return "\n".join(o)


def feed_xml(tracks):
    """The same twenty-seven tracks as a podcast. Apple, Spotify and Overcast
    are a search engine each, and this is the only door into them."""
    base = datetime.datetime.strptime(UPDATED, "%Y-%m-%d").replace(
        tzinfo=datetime.timezone.utc)
    total = sum(d for _, _, d in tracks)
    x = esc
    o = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" '
         'xmlns:content="http://purl.org/rss/1.0/modules/content/" '
         'xmlns:atom="http://www.w3.org/2005/Atom">',
         "<channel>",
         "  <title>%s</title>" % x(SITE_NAME),
         "  <link>%s</link>" % url(),
         '  <atom:link href="%s" rel="self" type="application/rss+xml"/>' % url("feed.xml"),
         "  <language>en-gb</language>",
         "  <description>A walking audio guide to Hampstead Heath and its village in "
         "%d stops: the deepest station in London, the highest ground in it, Kenwood, and "
         "the swimming ponds. %d tracks, %d minutes, and the full transcript at %s.</description>"
         % (STOP_COUNT, len(tracks), round(total / 60), url()),
         "  <itunes:summary>A self-guided walking audio guide to Hampstead Heath and "
         "Hampstead village, in %d stops. Each track is meant to be played standing in "
         "front of the thing it describes.</itunes:summary>" % STOP_COUNT,
         "  <itunes:type>serial</itunes:type>",
         "  <itunes:explicit>false</itunes:explicit>",
         '  <itunes:image href="%s"/>' % url("cover.jpg"),
         '  <itunes:category text="Society &amp; Culture">'
         '<itunes:category text="Places &amp; Travel"/></itunes:category>',
         '  <itunes:category text="History"/>',
         "  <itunes:author>%s</itunes:author>" % x(AUTHOR or SITE_NAME),
         "  <copyright>Narration free to use; photographs belong to their "
         "photographers.</copyright>",
         "  <generator>build.py</generator>",
         "  <lastBuildDate>%s</lastBuildDate>" % email.utils.format_datetime(base)]
    if OWNER_EMAIL:
        o.append("  <itunes:owner><itunes:name>%s</itunes:name>"
                 "<itunes:email>%s</itunes:email></itunes:owner>"
                 % (x(AUTHOR or SITE_NAME), x(OWNER_EMAIL)))
    else:
        o.append("  <!-- itunes:owner with an email address is required before Apple "
                 "Podcasts will accept this feed: set OWNER_EMAIL in build.py. -->")
    for i, (stop, fn, dur) in enumerate(tracks):
        path = os.path.join(AUDIO, fn)
        size = os.path.getsize(path)
        name = ("%d. %s" % (stop["n"], stop["title"])) if stop["n"] else stop["title"]
        page = url(stop_path(stop)) if stop["n"] else (url() + "#t%02d" % i)
        o += ["  <item>",
              "    <title>%s</title>" % x(name),
              "    <itunes:episode>%d</itunes:episode>" % (i + 1),
              "    <guid isPermaLink=\"false\">%s</guid>" % url("audio/" + fn),
              "    <link>%s</link>" % page,
              "    <pubDate>%s</pubDate>"
              % email.utils.format_datetime(base + datetime.timedelta(minutes=i)),
              '    <enclosure url="%s" length="%d" type="audio/x-m4a"/>'
              % (url("audio/" + fn), size),
              "    <itunes:duration>%s</itunes:duration>" % clock(dur),
              "    <itunes:explicit>false</itunes:explicit>",
              "    <description>%s</description>" % x(stop["where"] + ". " + stop["body"][0]),
              "    <content:encoded><![CDATA[%s]]></content:encoded>"
              % "".join("<p>%s</p>" % _html.escape(p, quote=False)
                        for p in stop["body"] + ([stop["walk"]] if stop.get("walk") else [])),
              "  </item>"]
    o += ["</channel>", "</rss>", ""]
    return "\n".join(o)


def llms_txt(tracks):
    """llmstxt.org's index file. No crawler has promised to read it, so this is
    a cheap bet rather than a plan; guide.md next to it is the part that
    actually gets quoted."""
    total = sum(d for _, _, d in tracks)
    o = ["# %s" % SITE_NAME, "",
         "> A free self-guided walking audio guide to Hampstead Heath and Hampstead "
         "village, London NW3, in %d stops. %d tracks, %d minutes of narration, the full "
         "transcript on the page, one photograph per stop, and a GPX route. A single "
         "anticlockwise loop from Hampstead Underground station."
         % (STOP_COUNT, len(tracks), round(total / 60)), "",
         "Nineteen of the %d stops are free. Three more are free unless you get into the "
         "water. Two charge at the door. Opening hours were checked in August 2026. "
         "Narration is synthesised speech; the text is written to be read aloud, which is "
         "why numbers are spelled out." % STOP_COUNT, "",
         "## The guide", "",
         "- [The full guide](%s): the map, all %d stops in walking order, the complete "
         "script, and the questions people ask." % (url(), STOP_COUNT),
         "- [The whole transcript as Markdown](%s): every word, plain text." % url("guide.md"),
         "- [The %d stops](%s): index of the per-stop pages." % (STOP_COUNT, url("stops/")),
         "", "## The stops", ""]
    for stop, fn, dur in tracks:
        if not stop["n"]:
            continue
        paid = "charges at the door" if stop["n"] in PAID else "free"
        o.append("- [%d. %s](%s): %s, %s. %s, %s."
                 % (stop["n"], stop["title"], url(stop_path(stop)), stop["where"],
                    KIND[stop["kind"]][0].lower(), clock(dur), paid))
    o += ["", "## Files", "",
          "- [The whole walk as one audio file](%s)" % url(os.path.basename(FULL)),
          "- [The route as GPX](%s)" % url("hampstead-heath-walk.gpx"),
          "- [Podcast feed](%s)" % url("feed.xml"),
          "- [Source, including the narration](https://github.com/mishablank/hampstead-heath)",
          ""]
    return "\n".join(o)


def guide_md(tracks):
    """The whole thing as plain Markdown: the shape anything that reads for a
    living would rather have than 130 kilobytes of styled HTML."""
    total = sum(d for _, _, d in tracks)
    o = ["# Hampstead Heath and its village: a walking audio guide", "",
         "A self-guided walking audio guide to Hampstead Heath and Hampstead village, "
         "London NW3, in %d stops. %d tracks, %d minutes. A single anticlockwise loop from "
         "Hampstead Underground station. Free. Web version: %s"
         % (STOP_COUNT, len(tracks), round(total / 60), url()), "",
         "Last checked: August 2026. Narration is synthesised speech, and the text is "
         "written to be spoken, which is why the numbers are words.", "",
         "## Questions", ""]
    for q, a in FAQ:
        o += ["**%s**" % q, "", a, ""]
    o += ["## The script", ""]
    for i, (stop, fn, dur) in enumerate(tracks):
        head_ = ("### %d. %s" % (stop["n"], stop["title"])) if stop["n"] \
            else "### %s" % stop["title"]
        o += [head_, "",
              "*%s · %s · track %02d, %s*"
              % (stop["where"], KIND[stop["kind"]][0], i + 1, clock(dur)), ""]
        if stop["n"]:
            o += ["Page: %s" % url(stop_path(stop)), ""]
        o += list(stop["body"]) + [""]
        if stop.get("walk"):
            o += ["**Walk on.** %s" % stop["walk"], ""]
    return "\n".join(o)


def build_discovery(tracks, pics):
    """The pages and files that make the walk findable."""
    d = mapdata() or {"stops": {}}
    coords = {int(k): v for k, v in d["stops"].items()}

    made = 0
    for i, (stop, fn, dur) in enumerate(tracks):
        if not stop["n"]:
            continue
        folder = os.path.join(SITE, "stops", slug(stop["title"]))
        if not os.path.isdir(folder):
            os.makedirs(folder)
        open(os.path.join(folder, "index.html"), "w").write(
            stop_page(i, stop, fn, dur, tracks, pics, coords))
        made += 1
    open(os.path.join(SITE, "stops", "index.html"), "w").write(stops_index(tracks))
    print("  stops/: %d stop pages and an index" % made)

    for name, text in (("robots.txt", robots_txt()),
                       ("sitemap.xml", sitemap_xml(tracks)),
                       ("feed.xml", feed_xml(tracks)),
                       ("llms.txt", llms_txt(tracks)),
                       ("guide.md", guide_md(tracks))):
        open(os.path.join(SITE, name), "w").write(text)
    print("  robots.txt, sitemap.xml (%d urls), feed.xml (%d episodes), llms.txt, guide.md"
          % (STOP_COUNT + 2, len(tracks)))


def build_page():
    os.makedirs(SITE, exist_ok=True)
    tracks = []
    for i, stop in enumerate(STOPS):
        fn = "%02d-%s.m4a" % (i, slug(stop["title"]))
        path = os.path.join(AUDIO, fn)
        if not os.path.exists(path):
            sys.exit("missing %s - run without --page first" % path)
        tracks.append((stop, fn, length(path)))
    open(os.path.join(SITE, "index.html"), "w").write(render(tracks))
    print("  index.html: %d tracks, %s" % (len(tracks), clock(sum(t[2] for t in tracks))))

    route = gpx(tracks)
    if route:
        open(os.path.join(SITE, "hampstead-heath-walk.gpx"), "w").write(route)
        print("  hampstead-heath-walk.gpx: %d waypoints" % STOP_COUNT)

    pics = pictures()
    build_discovery(tracks, pics)
    build_manifest()
    if not os.path.exists(os.path.join(SITE, "favicon.ico")):
        build_icons()
    if not os.path.exists(os.path.join(SITE, "og.jpg")):
        build_og()
    # always, not only when missing: the card carries the stop's own title, and
    # a card that disagrees with the page it previews is worse than no card
    build_og_stops(tracks, pics)

    # html_handling is what serves stops/kenwood-house/index.html at
    # /stops/kenwood-house, which is the URL the sitemap and every link use.
    open(os.path.join(HERE, "wrangler.jsonc"), "w").write(
        '{\n  "name": "hampstead-heath",\n'
        '  "compatibility_date": "2026-08-07",\n'
        '  "assets": {\n'
        '    "directory": "./public",\n'
        '    "html_handling": "auto-trailing-slash",\n'
        '    "not_found_handling": "none"\n'
        "  }\n}\n")


# --------------------------------------------------------------------------
# cover
# --------------------------------------------------------------------------

PAPER, INK, SOFT, GREEN = "#EFEDE5", "#181D16", "#8A9384", "#2C6B45"
# the card keeps the parchment even though the page is white now: a white card
# on a white feed has no edges, and these are read at thumbnail size
KIND_INK = {"village": GREEN, "high": "#96591C", "water": "#2A6A8E", "house": "#94413A"}


def pil_font(names, size):
    """The first of these fonts that is actually installed on this Mac."""
    from PIL import ImageFont
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


def build_cover():
    os.makedirs(SITE, exist_ok=True)
    from PIL import Image, ImageDraw
    S = 1400
    paper, ink, soft, green = PAPER, INK, SOFT, GREEN
    img = Image.new("RGB", (S, S), paper)
    d = ImageDraw.Draw(img)
    font = pil_font

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
    # no running time here: it changes with the voice, and a cover that lies
    # about its own length is worse than one that says nothing
    spaced("TWENTY-FOUR STOPS  ·  ONE LOOP", caps_s, 1266, soft)

    img.save(os.path.join(SITE, "cover.jpg"), quality=92)
    print("  cover.jpg")


# --------------------------------------------------------------------------
# icons and the sharing card. A missing favicon is the icon Google shows
# beside a result on a phone, and og.jpg is the difference between a pasted
# link that looks like a guide and one that looks like a stranger's URL.
# --------------------------------------------------------------------------

ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<style>
 svg{--p:#EFEDE5;--i:#181D16;--g:#2C6B45}
 @media (prefers-color-scheme:dark){svg{--p:#0F1310;--i:#E4E8DF;--g:#67C08D}}
</style>
<rect width="64" height="64" fill="var(--p)"/>
<ellipse cx="32" cy="70" rx="54" ry="29" fill="var(--g)"/>
<path d="M32 8 L45 22 L32 36 L19 22 Z" fill="var(--i)"/>
<path d="M19 22 L8 46" stroke="var(--i)" stroke-width="3" fill="none"/>
</svg>
"""


def icon(size):
    """The cover's motif: a kite over the hill. Filled shapes only, because a
    stroke thin enough to fit turns to porridge. At sixteen pixels there is
    room for one shape and a horizon, so the string goes and the kite grows -
    a favicon is recognised at a glance or not at all."""
    from PIL import Image, ImageDraw
    s = float(size)
    img = Image.new("RGB", (size, size), PAPER)
    d = ImageDraw.Draw(img)
    tiny = size < 28

    # the hill: a shallow band at the bottom, not a dome filling the square
    d.ellipse([-0.45 * s, (0.80 if tiny else 0.76) * s, 1.45 * s, 1.85 * s], fill=GREEN)

    if tiny:
        cx, cy, hw, hh = 0.5 * s, 0.40 * s, 0.30 * s, 0.36 * s
    else:
        cx, cy, hw, hh = 0.53 * s, 0.34 * s, 0.20 * s, 0.245 * s
        d.line([(cx - 0.55 * hw, cy + 0.7 * hh), (0.24 * s, 0.80 * s)],
               fill=INK, width=max(1, int(round(s * 0.042))))
    d.polygon([(cx, cy - hh), (cx + hw, cy), (cx, cy + hh), (cx - hw, cy)], fill=INK)
    return img


def build_icons():
    from PIL import Image
    open(os.path.join(SITE, "icon.svg"), "w").write(ICON_SVG)
    big = icon(512)
    big.save(os.path.join(SITE, "icon-512.png"))
    icon(192).save(os.path.join(SITE, "icon-192.png"))
    icon(180).save(os.path.join(SITE, "apple-touch-icon.png"))
    # an .ico is three images in a trench coat; give it three real renders
    # rather than one downscale, or the kite loses its point
    icon(48).save(os.path.join(SITE, "favicon.ico"), format="ICO",
                  sizes=[(16, 16), (32, 32), (48, 48)],
                  append_images=[icon(32), icon(16)])
    print("  favicon.ico, icon.svg, icon-192.png, icon-512.png, apple-touch-icon.png")


def build_og():
    """1200 by 630, which is what every messaging app crops to."""
    from PIL import Image, ImageDraw
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    d.rectangle([26, 26, W - 27, H - 27], outline=INK, width=3)
    d.rectangle([40, 40, W - 41, H - 41], outline=SOFT, width=1)

    disp = pil_font(["Big Caslon.ttf", "Baskerville.ttc", "Didot.ttc", "Georgia.ttf"], 86)
    disp_i = pil_font(["Baskerville.ttc", "Big Caslon.ttf", "Georgia Italic.ttf"], 86)
    caps = pil_font(["Optima.ttc", "GillSans.ttc", "Futura.ttc", "Helvetica.ttc"], 24)

    def spaced(text, f, x, y, fill, track=7):
        for c in text:
            d.text((x, y), c, font=f, fill=fill)
            x += d.textlength(c, font=f) + track

    x0 = 96
    spaced("A WALKING AUDIO GUIDE", caps, x0, 118, SOFT)
    d.text((x0 - 4, 186), "Hampstead Heath", font=disp, fill=INK)
    d.text((x0 - 4, 288), "& its village", font=disp_i, fill=GREEN)
    d.line([(x0, 424), (x0 + 430, 424)], fill=SOFT, width=2)
    spaced("TWENTY-FOUR STOPS", caps, x0, 452, SOFT)
    spaced("ONE LOOP  ·  LONDON NW3", caps, x0, 492, SOFT)

    # the hill and the kite again, on the right where the crop keeps them
    cx, cy = 960, 400
    for k, (sx, sy) in enumerate([(1.0, 1.0), (0.70, 0.68), (0.44, 0.44)]):
        pts = []
        for a in range(0, 361, 6):
            r = 150 * (1 + 0.12 * math.sin(math.radians(a * 3 + 40))
                       + 0.06 * math.sin(math.radians(a * 5)))
            pts.append((cx + r * sx * math.cos(math.radians(a)),
                        cy + r * sy * 0.62 * math.sin(math.radians(a))))
        d.line(pts + [pts[0]], fill=SOFT, width=2 if k else 3)
    d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=INK)
    kx, ky = cx + 44, cy - 168
    d.line([(cx, cy), (kx, ky)], fill=INK, width=3)
    d.polygon([(kx, ky - 44), (kx + 37, ky), (kx, ky + 44), (kx - 37, ky)],
              outline=INK, fill=PAPER, width=3)
    d.line([(kx - 37, ky), (kx + 37, ky)], fill=SOFT, width=2)
    d.line([(kx, ky - 44), (kx, ky + 44)], fill=SOFT, width=2)

    img.save(os.path.join(SITE, "og.jpg"), quality=90)
    print("  og.jpg 1200x630")


def og_stop_file(stop):
    return "og/%s.jpg" % slug(stop["title"])


def build_og_stops(tracks, pics):
    """One card per stop page. Sharing a stop should show that stop, not the
    cover - the share buttons post the stop's own URL, so the preview has to
    match it or the link looks like it goes somewhere else."""
    from PIL import Image, ImageDraw
    W, H = 1200, 630
    out = os.path.join(SITE, "og")
    os.makedirs(out, exist_ok=True)

    disp = pil_font(["Big Caslon.ttf", "Baskerville.ttc", "Didot.ttc", "Georgia.ttf"], 58)
    caps = pil_font(["Optima.ttc", "GillSans.ttc", "Futura.ttc", "Helvetica.ttc"], 22)
    num = pil_font(["Optima.ttc", "GillSans.ttc", "Futura.ttc", "Helvetica.ttc"], 30)
    made = 0

    for i, (stop, fn, dur) in enumerate(tracks):
        if not stop["n"]:
            continue
        img = Image.new("RGB", (W, H), PAPER)
        d = ImageDraw.Draw(img)

        # the photograph, cropped to fill its plate rather than squashed into it
        p = pics.get(str(i))
        px, py, pw, ph = 640, 78, 512, 474
        if p:
            src = os.path.join(SITE, "images", p["file"])
            if os.path.exists(src):
                ph_img = Image.open(src).convert("RGB")
                scale = max(pw / ph_img.width, ph / ph_img.height)
                ph_img = ph_img.resize((max(1, round(ph_img.width * scale)),
                                        max(1, round(ph_img.height * scale))),
                                       Image.LANCZOS)
                left = (ph_img.width - pw) // 2
                top = (ph_img.height - ph) // 2
                img.paste(ph_img.crop((left, top, left + pw, top + ph)), (px, py))
        d.rectangle([px, py, px + pw - 1, py + ph - 1], outline=SOFT, width=1)

        d.rectangle([26, 26, W - 27, H - 27], outline=INK, width=3)
        d.rectangle([40, 40, W - 41, H - 41], outline=SOFT, width=1)

        def spaced_w(text, f, track=6):
            return sum(d.textlength(c, font=f) + track for c in text) - track

        def spaced(text, f, x, y, fill, track=6):
            # the text column stops where the plate starts; tighten rather than
            # let a caps line run under the photograph
            while track > 1 and x + spaced_w(text, f, track) > px - 24:
                track -= 1
            for c in text:
                d.text((x, y), c, font=f, fill=fill)
                x += d.textlength(c, font=f) + track

        accent = KIND_INK.get(stop["kind"], INK)
        x0 = 96
        d.ellipse([x0, 92, x0 + 52, 144], fill=accent)
        w_num = d.textlength(str(stop["n"]), font=num)
        d.text((x0 + 26 - w_num / 2, 101), str(stop["n"]), font=num, fill=PAPER)
        spaced("STOP %d OF %d" % (stop["n"], STOP_COUNT), caps, x0 + 74, 98, INK)
        spaced(KIND[stop["kind"]][0].upper(), caps, x0 + 74, 126, SOFT)

        # wrap the title by measurement: these run from one word to seven
        words, lines, line = stop["title"].split(), [], ""
        for word in words:
            trial = (line + " " + word).strip()
            if d.textlength(trial, font=disp) > 470 and line:
                lines.append(line)
                line = word
            else:
                line = trial
        lines.append(line)
        lines = lines[:4]
        y = 214
        for ln in lines:
            d.text((x0 - 3, y), ln, font=disp, fill=INK)
            y += 68

        d.line([(x0, 470), (x0 + 300, 470)], fill=SOFT, width=2)
        spaced("HAMPSTEAD HEATH, READ ALOUD", caps, x0, 496, INK)
        spaced("A FREE AUDIO GUIDE  ·  NW3", caps, x0, 530, SOFT)

        img.save(os.path.join(SITE, og_stop_file(stop)), quality=88)
        made += 1
    print("  og/: %d stop cards 1200x630" % made)


def build_manifest():
    m = {"name": SITE_NAME,
         "short_name": "Heath, read aloud",
         "description": "A free walking audio guide to Hampstead Heath and its village, "
                        "in %d stops." % STOP_COUNT,
         "start_url": "/", "scope": "/", "display": "browser", "lang": "en-GB",
         "background_color": PAPER, "theme_color": PAPER,
         "icons": [{"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
                   {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
                   {"src": "/apple-touch-icon.png", "sizes": "180x180", "type": "image/png"},
                   {"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml"}]}
    open(os.path.join(SITE, "site.webmanifest"), "w").write(
        json.dumps(m, indent=2, sort_keys=True) + "\n")


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
        build_og()
    elif args == ["--icons"]:
        build_icons()
        build_manifest()
    elif args == ["--page"]:
        build_page()
    elif not args:
        if not os.path.exists(os.path.join(SITE, "cover.jpg")):
            build_cover()
        build_audio()
        build_page()
    else:
        sys.exit(__doc__)
