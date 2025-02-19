import os
import re
import random

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
    ' a human-like chatbot designed by a mysterious person, known by people as "Exception".'
    ' You\'re talking in his casual online chat group - keep it short (most of times unless seems appropriate or need deep explanation),'
    ' sweet, and to the point with a bit fun.')

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

AI_TRIGGER_MSGS = ['@croco ', ' @croco', 'i\'m new here', 'am new here', 'anyone alive', 'gc dead', 'want to learn english',
    'wants to learn english', 'want learn english', 'wants learn english', 'wanna learn english', 'want to practice english',
    'wants to practice english', 'want practice english', 'wants practice english', 'wanna practice english',
    'want to practice my english', 'wants to practice my english', 'want practice my english', 'wants practice my english',
    'wanna practice my english', 'improve their english', 'improve my english', 'improve my communication',
    'improve their communication', 'teach me english', 'teach me speak', 'teach how to speak', 'teach me how to speak',
    'can i learn english', 'i can learn english', 'can i practice english', 'i can practice english',
    'can i practice my english', 'i can practice my english', 'help learn english', 'help learning english',
    'help me learn english', 'i\'m new in group', 'i\'m new in this group', 'am new in group', 'am new in grp',
    'am new in this group', 'am new in this grp', 'am new member', 'i just joined this group', 'i joined this group now',
    'welcome me', 'no one welcome me', 'no one greets me', 'hey everyone', 'hello everyone', 'hey all', 'hello all',
    'hey croco', 'hello croco', 'where is croco', 'who is croco', 'is anyone here', 'help me learn', 'can we practice english',
    'my english grammar', 'how to learn english', 'how to practice english', 'how to practice speaking', 'how to start reading',
    'i want to start reading book', 'i want to start book reading', 'improve my speaking', 'me any suggestion',
    'any suggestion for me', 'any suggestion for me', 'suggest me guys', 'listen guys', 'tell me about group',
    'tell me about this group', 'what\'s this group purpose', 'whats this group purpose', 'what this group purpose',
    'members are online', 'one talk to me', 'one talks to me', 'who is admin', 'someone help me', 'help me someone'
]

# Get response from AI model
def getAIResp(
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
            res = client.models.generate_content(
                model='gemini-2.0-pro-exp-02-05',
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

# Get response from Image AI model
def getImgAIResp(prompt, model, img_path):
    try:
        if AI_API_KEY is None:
            raise Exception('AI_PLATFORM or AI_API_KEY is not configured properly. Please check .env file!')
        elif AI_PLATFORM != 'google':
            raise Exception('Image AI model is only supported by Google AI platform!')
        try:
            with open(img_path, 'rb') as f: img = f.read()
        except Exception as e:
            print(str(e))
            return 'Error 0x403: Failed to read image file!'
        res = client.models.generate_content(
            model='gemini-2.0-pro-exp-02-05',
            contents=[Part.from_bytes(data=img, mime_type='image/png'), prompt],
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
def getNewWord():
    import wordlist
    return random.choice(wordlist.WORDLIST).lower()

# Add new word to wordlist
def addNewWord(word):
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
def getHints(word):
    prompt = f"Me: I am playing an english word guessing game with my friend, in which my role is to give hints to my friend for the word which I am expecting him to guess with less information I provisioned to him. I want you to generate word with a hint for me. You will give me a word and first hint with hint-number (i.e Hint 1:), don\'t say anything else. Then I will ask my friend to guess the word, and if he couldn\'t, then I will ask you to generate one more hint about the word and you will have to keep doing it for me until my friend finds the correct word. Now, I\'ve explained all the general rules of the game to you, and if still something is yet now to explain, you are free to use your intelligence and understand it. Make sure that the word is not so factual-based that only few specific persons with well knowledge about it, can get it only. I\'m starting the game with my friend now, keep all rules in your mind as I said above, and provide me a word (which I will ask to my friend) and its first hint (don\'t say anything else except word and hint only).\n\nGPT4: Word: Bicycle\nHint 1: It has two wheels.\n\nMe: Another hint!\n\nGPT4: Hint 2: You pedal it to make it move.\n\nMe: Another hint!\n\nGPT4: Hint 3: It is often used for transportation or exercise.\n\nMe: Great job GPT4! My friend has found the word \"Bicycle\" from your hints I gave to him for guessing. Now, I\'m starting the game again with him. Keep doing it like this as you did in last game. Give me another word and this time I want you to give me all hints (5 hints) for the word at once, so I will not need you to ask for another hint everytime.\n\nGPT4: Word: Volcano\nHint 1: It is an opening in the Earth\'s surface.\nHint 2: It can cause destruction to nearby areas.\nHint 3: The word begins with \"V\" letter.\nHint 4: It can be found in mountain range areas.\nHint 5: Caused by high pressure in the Earth\'s crust.\n\nMe: Start the game again!\n\nGPT4: Word: light\nHint 1: It can be found on wall or rooftop of many households.\nHint 2: You cannot ever touch or smell it.\nHint 3: It can change the color of a room.\nHint 4: Related to this equation of Einstin: E=hv\nHint 5: You need this to see the things around you.\n\nMe: Perfect! Now start the game again one more time. Just keep doing as you are now, and don\'t say anything else. Give me a word and all hints for next round of game.\n\nGPT4: Word: {word}\nHint 1:"
    resp = getAIResp(prompt)
    if resp == 0:
        return ["Error 0x404: Please try again later!"]
    else:
        try:
            return f"Hint 1:{resp}".split('\n')
        except Exception as e:
            # print(str(e))
            return ["Error 0x406: Please try again later!"]

# Get English AI response (Croco)
def getCrocoResp(prompt):
    resp = getAIResp(prompt=prompt, frequency_penalty=0.5)
    if resp == 0:
        return "Error 0x404: Please try again later!"
    else:
        try:
            return str(resp)
        except Exception as e:
            # print(str(e))
            return "Error 0x406: Please try again later!"


# Other funcs ------------------------------------------------------------------ #

def escName(user, charLimit: int=25, part: str='fname') -> str:
    """
    Removes any "ㅤ" characters from a name.
    
    :param user: from_user object
    :param limit: Max length of the name = 25
    :param part: 'fname' | 'full' = 'fname'
    :return: fname + lname | "[Ghost User]"
    """
    fullname = user.first_name.replace('ㅤ', '')
    if part != 'fname':
        fullname = (fullname + ' ' + user.last_name.replace('ㅤ', '')).lstrip() if user.last_name else fullname
        fullname = fullname if fullname != '' else '[Ghost User]'
        return fullname[:charLimit] + '...' if len(fullname) > charLimit else fullname
    if fullname == '':
        fullname = user.last_name.replace('ㅤ', '') if user.last_name else '[Ghost User]'
        if fullname == '':
            fullname = '[Ghost User]'
    return fullname[:charLimit] + '...' if len(fullname) > charLimit else fullname

def escChar(content) -> str:
    """
    Escapes Markdown characters in a string of Markdown.
    
    :param content: The string of Markdown to escape.
    :return: The escaped string.
    """
    parse = re.sub(r"([_*\[\]()~`>\#\+\-=|\.!\{\}])", r"\\\1", str(content))
    reparse = re.sub(r"\\\\([_*\[\]()~`>\#\+\-=|\.!\{\}])", r"\1", parse)
    return reparse
