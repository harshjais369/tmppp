from sqlalchemy import Column, String, Integer
from sql_helper import BASE, SESSION
import time

class RankingsSql(BASE):
    __tablename__ = "rankings"
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False, unique=True, index=True)
    user_id = Column(String(30))
    chat_id = Column(String(30))
    points = Column(Integer, default=1)
    last_played = Column(String(80))
    name = Column(String(255))

    def __init__(self, id, user_id, chat_id, points, last_played, name):
        self.id = id
        self.user_id = user_id
        self.chat_id = chat_id
        self.points = points
        self.last_played = last_played
        self.name = name

    def __repr__(self):
        return "<Rankings %s>" % self.id

RankingsSql.__table__.create(checkfirst=True, bind=SESSION.bind)

def incrementPoints_sql(user_id, chat_id, name):
    try:
        adder = SESSION.query(RankingsSql).filter_by(user_id=str(user_id), chat_id=str(chat_id)).first()
        if adder:
            adder.points = int(adder.points) + 1
            adder.last_played = str(int(time.time()))
            adder.name = str(name)
        else:
            adder = RankingsSql(None, str(user_id), str(chat_id), 1, str(int(time.time())), str(name))
        SESSION.add(adder)
        SESSION.commit()
        return True
    except Exception as e:
        print(e)
        SESSION.rollback()
        return False

def getUserPoints_sql(user_id):
    try:
        return SESSION.query(RankingsSql).filter_by(user_id=str(user_id)).all()
    except Exception as e:
        print(e)
        SESSION.rollback()
        return None
    finally:
        SESSION.close()

def getTop25Players_sql(chat_id):
    try:
        return SESSION.query(RankingsSql).filter_by(chat_id=str(chat_id)).order_by(RankingsSql.points.desc()).limit(25).all()
    except Exception as e:
        print(e)
        SESSION.rollback()
        return None
    finally:
        SESSION.close()

def getTop25PlayersInAllChats_sql():
    try:
        return SESSION.query(RankingsSql).order_by(RankingsSql.points.desc()).limit(250).all()
    except Exception as e:
        print(e)
        SESSION.rollback()
        return None
    finally:
        SESSION.close()

def getTop10Chats_sql():
    pass
