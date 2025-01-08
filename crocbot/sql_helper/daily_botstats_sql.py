from sqlalchemy import Column, String, Integer, func
from sql_helper import BASE, SESSION

class DailyBotStats(BASE):
    __tablename__ = "daily_botstats"
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False, unique=True, index=True)
    date = Column(String(80))
    chats_added = Column(Integer, default=0)
    games_played = Column(Integer, default=0)
    active_players = Column(Integer, default=0)

    def __init__(self, id, date, chats_added, games_played, active_players):
        self.id = id
        self.date = date
        self.chats_added = chats_added
        self.games_played = games_played
        self.active_players = active_players

    def __repr__(self):
        return "<DailyBotStats %s>" % self.id
    
DailyBotStats.__table__.create(checkfirst=True, bind=SESSION.bind)

def new_joined_chat_sql(date):
    try:
        adder = SESSION.query(DailyBotStats).filter_by(date=str(date)).first()
        if adder:
            adder.chats_added = int(adder.chats_added) + 1
        else:
            adder = DailyBotStats(None, str(date), 1, 0, 0)
        SESSION.add(adder)
        SESSION.commit()
        return True
    except Exception as e:
        print(e)
        SESSION.rollback()
        return False
