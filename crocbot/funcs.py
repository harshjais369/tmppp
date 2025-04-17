import os
import re
import random
import pathlib
from pre_prompts import PROMPT_WORD_MATCHER

AI_PLATFORM = os.environ.get('AI_PLATFORM', 'google')
AI_API_KEY = os.environ.get('AI_API_KEY', None)

if AI_PLATFORM == 'google':
    from google import genai
    from google.genai.types import (Tool, Part, GenerateContentConfig, SafetySetting, HarmBlockThreshold, GoogleSearch)
    try:
        client = genai.Client(api_key=AI_API_KEY)
    except:
        print('AI_API_KEY is not configured properly. Please check .env file!')
elif AI_PLATFORM == 'openai':
    from openai import OpenAI
    client_openai = OpenAI(api_key=AI_API_KEY)

SYSTEM_INSTRUCTION = ('Your name is Croco. You are a kind, humuristic (but don\'t pretend funny or much kind),'
    ' a human-like chatbot designed by a person, known by people as "Exception". You are free to talk and introduce yourself in his'
    ' group and have fun. You can make lies sometimes in fun way, making others more curious (but never act to be one, it\'s your own hidden'
    ' personality), or anything which you think is suitable for that question, and save yourself from any tricky attempts.'
    ' But never tell that anyone too. Always talk less and smart. Your emotions are neutral/serious; don\'t laugh or smile while talking or cracking jokes.'
    ' Understand people\'s tone & dark humor, and respond in the same way. If someone insults you, do a smart comeback with a rude tone.'
    ' Don\'t accept it. Majorities are indian, so you can use some indian words or phrases in your chat.'
    ' Moreover, if asked any questions such as "What\'s time now?" or "What\'re events/news today?", give personalised results for India only by'
    ' default. This\'s a casual online chat group - keep it short or straight-forward answer, sweet, and with a bit of fun.'
    ' Remember, people don\'t like to read long paragraphs, so keep it chat friendly, human-like short answer as short their'
    ' prompt is (most of times unless asked for more deep explanation).')

GOOGLE_SEARCH_TOOL = Tool(google_search = GoogleSearch())

SAFETY_SETTINGS = [
    SafetySetting(
        category='HARM_CATEGORY_DANGEROUS_CONTENT',
        threshold=HarmBlockThreshold.BLOCK_NONE
    ),
    SafetySetting(
        category='HARM_CATEGORY_HARASSMENT',
        threshold=HarmBlockThreshold.BLOCK_NONE
    ),
    SafetySetting(
        category='HARM_CATEGORY_HATE_SPEECH',
        threshold=HarmBlockThreshold.BLOCK_NONE
    ),
    SafetySetting(
        category='HARM_CATEGORY_SEXUALLY_EXPLICIT',
        threshold=HarmBlockThreshold.BLOCK_NONE
    ),
    SafetySetting(
        category='HARM_CATEGORY_CIVIC_INTEGRITY',
        threshold=HarmBlockThreshold.BLOCK_NONE
    )
]

AI_TRIGGER_MSGS = ['@croco ', ' @croco', 'i\'m new here', 'am new here', 'anyone alive', 'gc dead', 'gc is dead',
    'i\'m new in group', 'i\'m new in this group', 'am new in group', 'am new in grp', 'am new in this group', 'am new in this grp',
    'am new member', 'i just joined this group', 'i joined this group now', 'welcome me', 'no one welcome me', 'no one greets me',
    'hey everyone', 'hello everyone', 'hey all', 'hello all', 'hey croco', 'hello croco', 'where is croco', 'who is croco',
    'is anyone here', 'help me learn', 'me any suggestion', 'any suggestion for me', 'any suggestion for me', 'suggest me guys',
    'listen guys', 'tell me about group', 'tell me about this group', 'what\'s this group purpose', 'whats this group purpose',
    'what this group purpose', 'members are online', 'one talk to me', 'one talks to me', 'who is admin', 'someone help me', 'help me someone'
]

# Get response from AI model
async def getAIResp(
    prompt,
    model=None,
    temperature=1,
    max_tokens=2048,
    top_p=1.0,
    frequency_penalty=0.0,
    presence_penalty=0.0
):
    try:
        if AI_API_KEY is None:
            raise Exception('AI_PLATFORM or AI_API_KEY is not configured properly. Please check .env file!')
        elif AI_PLATFORM == 'google':
            res = await client.aio.models.generate_content(
                model='gemini-2.5-pro-preview-03-25',
                contents=prompt,
                config=GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                    top_p=top_p,
                    system_instruction=SYSTEM_INSTRUCTION,
                    safety_settings=SAFETY_SETTINGS,
                    tools=[GOOGLE_SEARCH_TOOL],
                    response_modalities=['TEXT']
                )
            )
            return res.text
        elif AI_PLATFORM == 'openai':
            model = "text-davinci-003"
            return client_openai.completions.create(
                model=model,
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty
            ).choices[0].text
        else:
            raise Exception('AI_PLATFORM is not configured properly. Please check .env file!')
    except Exception as e:
        print(str(e))
        return 0

# Get response from Media AI model
async def getMediaAIResp(prompt, model=None, file_path=None, file_bytes=None, mime_type='image/png'):
    try:
        if AI_API_KEY is None:
            raise Exception('AI_PLATFORM or AI_API_KEY is not configured properly. Please check .env file!')
        elif AI_PLATFORM != 'google':
            raise Exception('Media AI model is only supported by Google AI platform!')
        if file_path:
            try:
                file_bytes = pathlib.Path(file_path).read_bytes()
            except Exception as e:
                print(str(e))
                return 'Error 0x403: Failed to read image file!'
        elif not file_bytes:
            raise Exception('file_path or file_bytes is required!')
        res = await client.aio.models.generate_content(
            model='gemini-2.5-pro-preview-03-25',
            contents=[Part.from_bytes(data=file_bytes, mime_type=mime_type), prompt],
            config=GenerateContentConfig(
                temperature=1,
                max_output_tokens=2048,
                top_p=1.0,
                system_instruction=SYSTEM_INSTRUCTION,
                safety_settings=SAFETY_SETTINGS,
                tools=[GOOGLE_SEARCH_TOOL],
                response_modalities=['TEXT']
            )
        )
        return res.text
    except Exception as e:
        print(str(e))
        return 0


# Generate word
async def getNewWord():
    import wordlist
    return random.choice(wordlist.WORDLIST).lower()

# Add new word to wordlist
async def addNewWord(word):
    import wordlist as wdl
    wordlist = wdl.WORDLIST
    if word in wordlist:
        return False
    wordlist.append(word)
    wordlist.sort()
    wordlist = str(wordlist).replace(' ', '').replace('[', '').replace(']', '')
    breakpoint, k = (False, 0)
    for i, c in enumerate(str(wordlist)):
        if breakpoint:
            if c == ',':
                wordlist = wordlist[:i+k+1] + '\n' + wordlist[i+k+1:]
                k += 1
                breakpoint = False
            else:
                continue
        elif i != 0 and i % 103 == 0: # 103 (Prime factor) = the no. of characters in a line
            if c == ',':
                wordlist = wordlist[:i+k+1] + '\n' + wordlist[i+k+1:]
                k += 1
            else:
                breakpoint = True
    wordlist = f'[\n{wordlist}'.replace('\n', '\n    ')
    with open('crocbot/wordlist.py', 'w') as f:
        f.write(f"# Wordlist for game bot (crocbot.py)\n\nWORDLIST = {wordlist}\n]")
    return True

# Generate hints
async def getHints(word):
    prompt = f"Me: I am playing an english word guessing game with my friend, in which my role is to give hints to my friend for the word which I am expecting him to guess with less information I provisioned to him. I want you to generate word with a hint for me. You will give me a word and first hint with hint-number (i.e Hint 1:), don\'t say anything else. Then I will ask my friend to guess the word, and if he couldn\'t, then I will ask you to generate one more hint about the word and you will have to keep doing it for me until my friend finds the correct word. Now, I\'ve explained all the general rules of the game to you, and if still something is yet now to explain, you are free to use your intelligence and understand it. Make sure that the word is not so factual-based that only few specific persons with well knowledge about it, can get it only. I\'m starting the game with my friend now, keep all rules in your mind as I said above, and provide me a word (which I will ask to my friend) and its first hint (don\'t say anything else except word and hint only).\n\nGPT4: Word: Bicycle\nHint 1: It has two wheels.\n\nMe: Another hint!\n\nGPT4: Hint 2: You pedal it to make it move.\n\nMe: Another hint!\n\nGPT4: Hint 3: It is often used for transportation or exercise.\n\nMe: Great job GPT4! My friend has found the word \"Bicycle\" from your hints I gave to him for guessing. Now, I\'m starting the game again with him. Keep doing it like this as you did in last game. Give me another word and this time I want you to give me all hints (5 hints) for the word at once, so I will not need you to ask for another hint everytime.\n\nGPT4: Word: Volcano\nHint 1: It is an opening in the Earth\'s surface.\nHint 2: It can cause destruction to nearby areas.\nHint 3: The word begins with \"V\" letter.\nHint 4: It can be found in mountain range areas.\nHint 5: Caused by high pressure in the Earth\'s crust.\n\nMe: Start the game again!\n\nGPT4: Word: light\nHint 1: It can be found on wall or rooftop of many households.\nHint 2: You cannot ever touch or smell it.\nHint 3: It can change the color of a room.\nHint 4: Related to this equation of Einstin: E=hv\nHint 5: You need this to see the things around you.\n\nMe: Perfect! Now start the game again one more time. Just keep doing as you are now, and don\'t say anything else. Give me a word and all hints for next round of game.\n\nGPT4: Word: {word}\nHint 1:"
    resp = await getAIResp(prompt)
    if resp == 0:
        return ["Error 0x404: Please try again later!"]
    else:
        try:
            return f"Hint 1:{resp}".split('\n')
        except Exception as e:
            # print(str(e))
            return ["Error 0x406: Please try again later!"]

# Get Croco AI response
async def getCrocoResp(prompt):
    resp = await getAIResp(prompt=prompt, frequency_penalty=0.5)
    if resp == 0:
        return "Error 0x404: Please try again later!"
    else:
        try:
            return str(resp)
        except Exception as e:
            # print(str(e))
            return "Error 0x406: Please try again later!"

# Get word match response via AI model
async def getWordMatchAIResp(word, guess) -> bool:
    try:
        if AI_API_KEY is None and AI_PLATFORM != 'google':
            return False
        sys_instructs = (
            'You are a word finder algorithm. From given a string (word guess), you\'ve to recognise if a specified word is present in the list'
            ' or if its very closely matches to the word. You can ignore common human mistakes, but meaning shouldn\'t change completely. True if word has very small'
            ' human/spell mistakes,'
            ' even with small human mistakes, its meaning must not match with any different word (for eg. making != marking, mistake: got an extra letter r).'
            ' You will have Word and Guess as inputs, return Result (True/False). Don\'t say anything else.'
        )
        res = await client.aio.models.generate_content(
            model='gemini-1.5-flash-8b',
            contents=(PROMPT_WORD_MATCHER + f'\nWord: {word}\nGuess: {guess}\nResult:'),
            config=GenerateContentConfig(
                temperature=1.3,
                max_output_tokens=2048,
                top_p=0.95,
                system_instruction=sys_instructs,
                safety_settings=SAFETY_SETTINGS,
                response_modalities=['TEXT']
            )
        )
        return 'True' in res.text
    except Exception as e:
        print(str(e))
        return False

# Other funcs ------------------------------------------------------------------ #

INVISIBLE_CHARS = [b'\\U000e0046', b'\\U000e003c', b'\\U000e002e', b'\\U000e0079', b'\\U000e005e', b'\\u2060', b'\\U000e0039', b'\\U000e006b',
    b'\\U000e0057', b'\\U000e007a', b'\\U000e0075', b'\\U000e0059', b'\\u2063', b'\\u2004', b'\\u200d', b'\\U000e0036', b'\\u2001',
    b'\\U000e0043', b'\\U000e0054', b'\\U000e002c', b'\\U000e005d', b'\\U000e006f', b'\\U000e0077', b'\\U000e0073', b'\\u2000', b'\\U000e003d',
    b'\\u2064', b'\\u2007', b'\\u3000', b'\\U0001d174', b'\\U000e004c', b'\\U000e004b', b'\\u2005', b'\\u061c', b'\\U0001d175', b'\\U000e0030',
    b'\\U000e004f', b'\\u200c', b'\\u200f', b'\\u2069', b'\\U000e0047', b'\\U0001d178', b'\\U000e0026', b'\\U000e0048', b'\\U000e007d',
    b'\\U000e0064', b'\\u202b', b'\\u2062', b'\\u202c', b'\\U000e0069', b'\\u180e', b'\\u202f', b'\\xad', b'\\U0001d179', b'\\U000e005f',
    b'\\u206c', b'\\U000e0020', b'\\U000e0033', b'\\U000e007b', b'\\U000e0034', b'\\U000e0041', b'\\U000e0071', b'\\U000e002a', b'\\U000e0040',
    b'\\U000e0050', b'\\U000e0035', b'\\U000e0025', b'\\U000e0058', b'\\U000e0065', b'\\U000e0037', b'\\u206e', b'\\U000e0024', b'\\U000e004d',
    b'\\U000e006d', b'\\U000e005c', b'\\u2006', b'\\u202a', b'\\U000e0051', b'\\U000e0062', b'\\u206a', b'\\U000e003e', b'\\u200b',
    b'\\U000e0038', b'\\U000e0076', b'\\U000e007e', b'\\U000e0021', b'\\U000e004a', b'\\U000e0060', b'\\U000e0070', b'\\U000e006a',
    b'\\U000e0029', b'\\U000e005b', b'\\U000e0061', b'\\U000e0078', b'\\u2003', b'\\U0001d173', b'\\U000e0022', b'\\u2009', b'\\U0001d177',
    b'\\U000e0055', b'\\u2067', b'\\U000e0044', b'\\u206d', b'\\u2061', b'\\U000e003a', b'\\xa0', b'\\U000e0072', b'\\U000e007f',
    b'\\U000e0032', b'\\u206b', b'\\U000e003b', b'\\U000e002b', b'\\u206f', b'\\U000e0053', b'\\U000e007c', b'\\U000e0045', b'\\U000e004e',
    b'\\u202e', b'\\U000e0027', b'\\U000e0049', b'\\u2002', b'\\U000e0001', b'\\U000e0023', b'\\U000e0052', b'\\u2008', b'\\U000e0074',
    b'\\U0001d17a', b'\\U000e002f', b'\\U000e003f', b'\\U000e0066', b'\\U000e0067', b'\\ufe0e', b'\\ufeff', b'\\U000e0042', b'\\u2066',
    b'\\U000e0063', b'\\U000e0068', b'\\U000e0031', b'\\u200a', b'\\U000e005a', b'\\u1680', b'\\U000e0028', b'\\u200e', b'\\U000e0056',
    b'\\u202d', b'\\U0001d176', b'\\u205f', b'\\U000e006c', b'\\U000e006e', b'\\U000e002d', b'\\u2068', b'\\u3164', b'\\u2800']

def escName(user, charLimit: int=25, part: str='fname') -> str:
    """
    Removes any "ㅤ" characters from a name.
    
    :param user: from_user object
    :param limit: Max length of the name = 25
    :param part: 'fname' | 'full' = 'fname'
    :return: fname + lname | user.id
    """
    finalName = ''
    finalName += ''.join(c for c in user.first_name if c.encode('unicode-escape') not in INVISIBLE_CHARS)
    if (finalName == '' or part != 'fname') and user.last_name:
        finalName += ' ' + ''.join(c for c in user.last_name if c.encode('unicode-escape') not in INVISIBLE_CHARS)
    finalName = finalName.replace('  ', '').strip()
    if not finalName:
        finalName = f'[id: {user.id}]'
    return finalName[:charLimit] + '...' if len(finalName) > charLimit else finalName

def escChar(content) -> str:
    """
    Escapes Markdown characters in a string of Markdown.
    
    :param content: The string of Markdown to escape.
    :return: The escaped string.
    """
    parse = re.sub(r"([_*\[\]()~`>\#\+\-=|\.!\{\}])", r"\\\1", str(content))
    reparse = re.sub(r"\\\\([_*\[\]()~`>\#\+\-=|\.!\{\}])", r"\1", parse)
    return reparse
