from sqlalchemy import Column, String, Integer, Text
from sql_helper import BASE, SESSION
import time

class AiConvSql(BASE):
    __tablename__ = "ai_conv"
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False, unique=True, index=True)
    time = Column(String(30))
    prompt = Column(Text)

    def __init__(self, id, time, prompt):
        self.id = id
        self.time = time
        self.prompt = prompt

AiConvSql.__table__.create(checkfirst=True, bind=SESSION.bind)

def getAllConv_sql():
    pass

def updateEngAIPrompt_sql(id, prompt):
    pass
