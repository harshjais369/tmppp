from sqlalchemy import Column, String
from crocbot.sql_helper import BASE, SESSION
import time

class CurrentGame(BASE):
    __tablename__ = "current_game"
    chat_id = Column(String(30), primary_key=True)
    leader_id = Column(String(30))
    started_at = Column(String(30))
    word = Column(String(50))

    def __init__(self, chat_id, leader_id, started_at, word):
        self.chat_id = chat_id
        self.leader_id = leader_id
        self.started_at = started_at
        self.word = word

    def __repr__(self):
        return "<Current Game %s>" % self.chat_id

CurrentGame.__table__.create(checkfirst=True, bind=SESSION.bind)

def addGame_sql(chat_id, leader_id, word):
    try:
        adder = SESSION.query(CurrentGame).get(str(chat_id))
        if adder:
            SESSION.delete(adder)
        adder = CurrentGame(str(chat_id), str(leader_id), str(int(time.time())), str(word))
        SESSION.add(adder)
        SESSION.commit()
        return True
    except Exception as e:
        print(e)
        SESSION.rollback()
        return False

def getGame_sql(chat_id):
    try:
        return SESSION.query(CurrentGame).get(str(chat_id))
    except Exception as e:
        print(e)
        SESSION.rollback()
        return None
    finally:
        SESSION.close()

def removeGame_sql(chat_id):
    try:
        rem = SESSION.query(CurrentGame).get(str(chat_id))
        if rem:
            SESSION.delete(rem)
            SESSION.commit()
            return True
    except Exception as e:
        print(e)
        SESSION.rollback()
        return False
    finally:
        SESSION.close()
