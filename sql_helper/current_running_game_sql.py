from sqlalchemy import Column, String, Integer
from . import BASE, SESSION

class CurrentGame(BASE):
    __tablename__ = "current_game"
    chat_id = Column(Integer, primary_key=True)
    leading_user_id = Column(Integer)
    started_at = Column(Integer)
    word = Column(String(255))

    def __init__(self, chat_id, leading_user_id, started_at, word):
        self.chat_id = chat_id
        self.leading_user_id = leading_user_id
        self.started_at = started_at
        self.word = word

    def __repr__(self):
        return "<Current Game %s>" % self.chat_id

CurrentGame.__table__.create(checkfirst=True)

def addGame_sql(chat_id, leading_user_id, started_at, word):
    try:
        adder = SESSION.query(CurrentGame).get(chat_id)
        if adder:
            SESSION.delete(adder)
        adder = CurrentGame(chat_id, leading_user_id, started_at, word)
        SESSION.add(adder)
        SESSION.commit()
        return True
    except Exception as e:
        print(e)
        SESSION.rollback()
        return False

def getGame_sql(chat_id):
    try:
        return SESSION.query(CurrentGame).get(chat_id)
    except Exception as e:
        print(e)
        SESSION.rollback()
        return None
    finally:
        SESSION.close()

def removeGame_sql(chat_id):
    try:
        rem = SESSION.query(CurrentGame).get(chat_id)
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
