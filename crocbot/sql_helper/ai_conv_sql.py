from sqlalchemy import Column, String, Integer, Text
from sql_helper import BASE, SESSION
import time

class AiConvSql(BASE):
    __tablename__ = "ai_conv"
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False, unique=True, index=True)
    chat_id = Column(String(30), nullable=False)
    time = Column(String(30))
    prompt = Column(Text)

    def __init__(self, chat_id, id, time, prompt):
        self.id = id
        self.chat_id = chat_id
        self.time = time
        self.prompt = prompt

AiConvSql.__table__.create(checkfirst=True, bind=SESSION.bind)

def getAllConv_sql(chat_id):
    try:
        return SESSION.query(AiConvSql).filter_by(chat_id=str(chat_id)).all()
    except Exception as e:
        print(e)
        SESSION.rollback()
        return None
    finally:
        SESSION.close()

def updateEngAIPrompt_sql(id, chat_id, prompt, isNewConv):
    try:
        adder = False
        if isNewConv:
            adder = SESSION.query(AiConvSql).filter_by(chat_id=str(chat_id)).first()
        else:
            adder = SESSION.query(AiConvSql).get(id)
        if adder:
            adder.time = str(int(time.time()))
            adder.prompt = prompt
        else:
            adder = AiConvSql(id=None, chat_id=str(chat_id), time=str(int(time.time())), prompt=str(prompt))
        SESSION.add(adder)
        SESSION.commit()
        return True
    except Exception as e:
        print(e)
        SESSION.rollback()
        return False
