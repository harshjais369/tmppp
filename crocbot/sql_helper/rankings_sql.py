from sqlalchemy import Column, String, Integer, func
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

def incrementPoints_sql(user_id, chat_id, point, name):
    try:
        adder = SESSION.query(RankingsSql).filter_by(user_id=str(user_id), chat_id=str(chat_id)).first()
        if adder:
            adder.points = int(adder.points) + int(point)
            adder.last_played = str(int(time.time()))
            adder.name = str(name)
        else:
            adder = RankingsSql(None, str(user_id), str(chat_id), int(point), str(int(time.time())), str(name))
        SESSION.add(adder)
        SESSION.commit()
        return True
    except Exception as e:
        print(e)
        SESSION.rollback()
        return False

def getUserPoints_sql(user_id):
    try:
        return SESSION.query(RankingsSql).filter_by(user_id=str(user_id)).order_by(RankingsSql.last_played.desc()).all()
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
        return SESSION.query(RankingsSql).order_by(RankingsSql.last_played.desc()).limit(10000).all()
    except Exception as e:
        print(e)
        SESSION.rollback()
        return None
    finally:
        SESSION.close()

def getTop10Chats_sql():
    try:
        return SESSION.query(RankingsSql.chat_id, func.sum(RankingsSql.points)).group_by(RankingsSql.chat_id).order_by(func.sum(RankingsSql.points).desc()).limit(10).all()
    except Exception as e:
        print(e)
        SESSION.rollback()
        return None
    finally:
        SESSION.close()

def getAllChatIds_sql():
    chatIds = []
    userIds = []
    try:
        chatIdsList = SESSION.query(RankingsSql.chat_id).group_by(RankingsSql.chat_id).all()
        userIdsList = SESSION.query(RankingsSql.user_id).group_by(RankingsSql.user_id).all()
        for chatId in chatIdsList:
            chatIds.append(chatId[0])
        for userId in userIdsList:
            userIds.append(userId[0])
        return chatIds, userIds
    except Exception as e:
        print(e)
        SESSION.rollback()
        return [], []
    finally:
        SESSION.close()
