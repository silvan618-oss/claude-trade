import json, re
PETER="Peter, a short chubby boy with straight fair blond hair, a round face, bulging pale eyes and full cheeks, in a grey jumper and a red-gold tie,"
S=("Candid first-person video from my own eye level, as if I just raised my old phone and hit record. The attached reference image defines the look of the whole video: real live-action phone footage, real people, real film-set locations of a gothic wizarding boarding school in the 1970s, soft muted colours, NOT anime, NOT cartoon, NOT CGI-looking. The attached character images define only each person's face, hair and clothes. "
"2015 smartphone video quality: soft focus, visible noise and slight compression, motion blur, uneven handheld framing that shakes in my hand, people cut off at the edges, no flash, no filter, audio like a phone microphone with {audio}. "
"The person holding the camera never speaks and makes no sound. The only people who speak are {speakers}, and each turns their face to the camera before speaking so their lips are visible moving with every word. All dialogue is spoken in English with natural British accents, casual teenage talk. No caption, no text overlay, no bar on the video. "
"{scene} Vertical 9:16. No watermark, no visible phone or camera.")
V=[
("they've been at this for a week","Stil-Referenz, @prongs, @padfoot, @moony",
 "a crackling fire, quills scratching, parchment rustling and a boy sighing",
 "@prongs and @padfoot",
 "A round dormitory in a tower at night, four-poster beds with red curtains, the floor completely covered in sheets of parchment joined together with ink lines of corridors and staircases. @prongs lies on his stomach in the middle of it drawing with a quill, ink on his fingers and his glasses pushed up into his messy hair. @padfoot lies on his back on the floor with his feet up on a bed, holding a sheet above his face. @moony sits cross-legged on a bed with a stack of finished sheets. For the first two seconds nobody looks up, James keeps drawing and Sirius keeps squinting at his sheet, as if they heard me. Then James looks at the camera, lips moving: \"It's nearly done. Two more floors.\" He listens for two seconds as if I'm answering, then Sirius tilts his head back to look at the camera upside down and says: \"He said that on Monday.\" James throws a balled-up sheet at him without looking up and says: \"Monday I meant it less.\" Two seconds pass with Sirius laughing and Remus quietly adding a sheet to his pile."),
("the stag looks like a goat","Stil-Referenz, @prongs, @padfoot",
 "a crackling fire, a quill scratching and two boys arguing",
 "@prongs and @padfoot",
 "The same tower dormitory at night, parchment everywhere. @prongs kneels over a sheet holding up a small ink drawing of a stag with antlers, looking proud. @padfoot leans over his shoulder with a huge grin. For the first two seconds James holds the drawing toward the camera and turns it slightly to catch the light, as if he heard me. Then he says, lips moving: \"Look at that. That's a stag. That's me.\" He listens for two seconds as if I'm answering, then Sirius grabs the sheet, holds it next to his own face and says to the camera: \"It's a goat. It's a sad little goat.\" James snatches it back and says: \"The antlers are the hard part.\" Sirius says: \"It's got a beard, Prongs.\" Two seconds pass with James staring at the drawing, then quietly scratching out the beard."),
("remus is the only one actually working","Stil-Referenz, @moony, @padfoot",
 "a quill scratching steadily, a fire, one soft snore and a clock ticking",
 "@moony",
 "The tower dormitory late at night, most candles burnt down. @moony sits at a small desk under the window, tired, a scar across his cheek, writing tiny corridor names onto a long strip of parchment with a fine quill, a half-eaten bar of chocolate beside his hand. Behind him @padfoot is asleep face down on the floor on top of the parchment, one arm over a stack of sheets. For the first two seconds Remus keeps writing without looking up, only his eyebrows go up, as if he heard me. Then he glances at the camera and says quietly, lips moving: \"Someone has to spell the corridors right.\" He listens for two seconds as if I'm answering, breaks off a piece of chocolate, and says: \"He did the whole dungeon level. Then he lay down on it.\" He looks over his shoulder at Sirius, back at the camera, and says: \"I'm not waking him. He drools on the ink.\" Two seconds pass with him writing again and Sirius snoring."),
("peter got lost testing it","Stil-Referenz, @prongs (Peter wird beschrieben)",
 "an echoing stone corridor, hurried footsteps and a nervous voice",
 "Peter, the chubby blond boy, and @prongs",
 "A long stone corridor with portraits and a suit of armour, grey daylight from tall windows. "+PETER+" stands in the middle of the corridor holding a torn piece of parchment upside down, turning it round and round, out of breath. @prongs walks up from behind him and takes the parchment out of his hands. For the first two seconds Peter keeps turning the sheet and looks around helplessly, as if he heard me. Then he looks at the camera and says, lips moving: \"It said left. I went left. There's no left.\" He listens for two seconds as if I'm answering. James turns the parchment the right way up, holds it in front of Peter's face and says to the camera: \"He's been on the wrong floor for an hour.\" Peter looks at it, looks up at the ceiling, and says: \"Oh. That's the third floor.\" James pats him on the shoulder and says: \"This is the fifth, Wormtail.\" Two seconds pass with Peter staring at the sheet and James steering him toward the stairs."),
("we needed the seventh floor","Stil-Referenz, @prongs, @padfoot",
 "whispering, bare feet on stone, a distant door creaking and wind in a corridor",
 "@padfoot and @prongs",
 "A dark stone corridor at night lit only by moonlight through a window. @padfoot crouches against the wall in his pyjamas holding a sheet of parchment and a quill, whispering. Next to him a pair of legs in pyjama trousers and bare feet stand in mid-air with nothing above them, as if the upper half of the person is invisible, and the parchment floats up as an invisible hand takes it. For the first two seconds Sirius keeps drawing a line on the sheet and glances up and down the corridor, as if he heard me. Then he looks at the camera and whispers, lips moving: \"Shh. Last floor. Then we're done.\" He listens for two seconds as if I'm answering. The floating legs shuffle, and @prongs's head appears out of thin air above them as he pulls the cloak back, looks at the camera and whispers: \"The cloak only covers one of us. I called it.\" Sirius hisses: \"You always call it.\" James's head vanishes again and the legs walk off down the corridor. Two seconds pass with Sirius following on tiptoe and the camera creeping after them."),
("filch nearly got us","Stil-Referenz, @padfoot, @moony (Peter wird beschrieben)",
 "heavy breathing, three boys pressed together, a cat meowing and slow footsteps with a lantern creaking",
 "@padfoot and Peter, the chubby blond boy",
 "Very dark and cramped, the back of a thick tapestry in a corridor, moonlight and a swinging lantern light glowing through the fabric from the other side. @padfoot, @moony and "+PETER+" are squeezed together behind it, Peter squashed in the middle with his face pressed against Remus's shoulder, all three holding their breath. A cat's shadow passes on the other side of the tapestry. For the first two seconds nobody moves, only the lantern light sways over their faces and Peter's eyes go wider and wider, as if they heard me and are begging me to be quiet. Then Sirius turns his face to the camera and mouths almost silently, lips moving: \"Don't. Breathe.\" He listens for two seconds while the footsteps come closer and stop. Peter squeaks in a tiny whisper to the camera: \"I need to sneeze.\" Sirius claps his hand over Peter's mouth and whispers: \"If you sneeze, I'll tell him it was you.\" The footsteps move away, the light fades, and all three sag against the wall. Two seconds pass with Remus quietly laughing into his sleeve."),
("lily wants to know what we're doing","Stil-Referenz, @evans, @prongs",
 "a busy common room, a fire, chatter and one very calm girl's voice",
 "@evans and @prongs",
 "A warm red common room in the afternoon, students in the background. @evans stands with her arms crossed and one eyebrow raised, looking at @prongs, who stands in front of her with a big roll of parchment held behind his back, smiling far too innocently, his hair flattened with one hand. For the first two seconds Lily keeps staring at James and James keeps smiling, and neither of them blinks, as if they heard me. Then Lily looks at the camera and says, lips moving: \"He's hiding something. Look at his face.\" She listens for two seconds as if I'm answering. James looks at the camera and says: \"It's homework. A very large homework.\" Lily says to the camera: \"He hasn't done homework since second year.\" James backs away one step, the parchment slips and unrolls across the floor behind him, and he says: \"Alright, it's a map. Don't tell her.\" Lily says: \"I'm standing right here.\" Two seconds pass with James rolling the map back up as fast as he can and Lily shaking her head."),
("the password","Stil-Referenz, @padfoot, @moony, @prongs",
 "a crackling fire, groaning, laughing and a wand tapping on parchment",
 "@padfoot, @moony and @prongs",
 "The tower dormitory at night. The finished map lies folded on a bed, still blank on the outside. @padfoot stands on the bed with his wand in the air like he's giving a speech, @prongs sits on the floor with his head in his hands, @moony lies on the next bed holding a pillow over his face. For the first two seconds Sirius keeps his wand raised and looks around for applause, as if he heard me. Then he looks at the camera and says, lips moving: \"I solemnly swear that I am up to no good. That's the password. Genius.\" He listens for two seconds as if I'm answering. Remus lifts the pillow, looks at the camera and says: \"It's nine words. Nine.\" James looks up and says: \"It's the worst thing I've ever heard.\" Sirius points his wand at the folded parchment, says the phrase again quietly, and ink lines spread across the blank surface. James and Remus both sit up and stare. James says: \"...it's perfect.\" Two seconds pass with Sirius bowing on the bed."),
("it works","Stil-Referenz, @prongs, @padfoot, @moony (Peter wird beschrieben)",
 "parchment unfolding, ink scratching by itself, four boys going quiet and then whooping",
 "@prongs and @padfoot",
 "The tower dormitory at night, all four boys crowded on the floor around a big parchment map spread open, its folds opening by themselves, thin ink lines drawing corridors and tiny labelled dots moving along them. @prongs, @padfoot, @moony and "+PETER+" all lean over it with their faces lit from below by a candle. For the first two seconds nobody says anything, they just watch the tiny dots move, as if they heard me and can't answer. Then James looks up at the camera with a huge grin, lips moving: \"Every single person. Every floor. Look, that's Filch.\" He listens for two seconds as if I'm answering. Sirius points at a dot in the corner of the map, looks at the camera and says: \"And that's Peter's dot. In the bathroom. Ten minutes ago.\" Peter mumbles that he had to go. James taps the map with his wand and says to the camera: \"Mischief managed.\" The ink lines drain away until the parchment is blank again, and all four boys fall back onto the floor whooping. Two seconds pass with Sirius lying on the floor laughing and Remus folding the map carefully."),
]

NAMES=[('prongs','James'),('padfoot','Sirius'),('moony','Remus'),('evans','Lily'),('snivellus','Snape')]
def refnames(text):
    """Outside dialogue quotes: every mention of a person is the reference name with @, in capitals."""
    parts=text.split('"')            # even indexes = narration, odd = spoken lines
    seen=set()
    for i in range(0,len(parts),2):
        p=parts[i]
        for ref,real in NAMES:
            p=p.replace('@'+ref, real)          # normalise to the real name first
            p=re.sub(r'\b'+real+r"(?='s\b|\b)", '\x00'+ref, p)   # mark every narration mention
        out=''
        for tok in re.split(r'(\x00[a-z]+)', p):
            if tok.startswith('\x00'):
                ref=tok[1:]
                out+='@'+ref.upper()          # every narration mention carries the @
            else: out+=tok
        parts[i]=out
    return '"'.join(parts)
clips=[dict(n=i,title=t,attach=a.replace('@prongs','@PRONGS').replace('@padfoot','@PADFOOT').replace('@moony','@MOONY').replace('@evans','@EVANS'),note="Folge 1",img=refnames(S.format(audio=au,speakers=sp,scene=sc))) for i,(t,a,au,sp,sc) in enumerate(V,1)]
WORLDS=[dict(key="mar",name="Marauders",clips=clips)]
d=json.dumps(WORLDS,ensure_ascii=False).replace('</','<\\/')
h=open('/home/user/claude-trade/snaps/prompts/batch-02-hp-videos.html',encoding='utf-8').read()
h=h.replace('<title>Wizarding Videos 02</title>','<title>Marauders Folge 1</title>')
h=re.sub(r"const DATA = .*?;\nconst INSTR", lambda m:"const DATA = "+d+";\nconst INSTR", h, flags=re.S)
h=re.sub(r"const INSTR = \(name\)=>`.*?`;", lambda m: "const INSTR = (name)=>`ANLEITUNG FÜR FLOW – MARAUDERS, FOLGE 1: DIE KARTE (9 CLIPS)\n10 Sekunden pro Clip, 9:16, Text-zu-Video ohne Startframe, in dieser Reihenfolge. Pro Clip die Stil-Referenz und die genannten Charaktere anhängen. Jede Person steht in der Beschreibung bei jeder Erwähnung als @NAME in Großbuchstaben. Peter hat in Flow keine Referenz und ist im Prompt beschrieben.\nAlle Dialoge auf Englisch mit britischem Akzent. Der Kamerahalter spricht nie. Jeder Satz gehört zu der sichtbaren Person, die im Prompt genannt ist, mit sichtbar bewegtem Mund. Kein Caption-Balken, Text kommt später im Schnitt.\n`;", h, flags=re.S)
h=h.replace('Wizarding World Batch 02, alle 18 Video-Prompts. Startframe ist jeweils das fertige Bild mit derselben Caption.','Marauders, Folge 1: sie bauen die Karte. 9 Clips ohne Startframe, ohne Caption-Balken. Die Caption oben ist nur der Titel für deinen Schnitt. Unter jedem Clip steht, was anzuhängen ist.')
open('marauders-01.html','w',encoding='utf-8').write(h)
print(len(clips))
