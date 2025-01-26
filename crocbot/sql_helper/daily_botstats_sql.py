from sqlalchemy import Column, String, Integer, func
from sql_helper import BASE, SESSION

class DailyBotStats(BASE):
    __tablename__ = "daily_botstats"
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False, unique=True, index=True)
    date = Column(String(80))
    chats_added = Column(Integer, default=0)
    games_played = Column(Integer, default=0)
    cheats_detected = Column(Integer, default=0)

    def __init__(self, id, date, chats_added, games_played, cheats_detected):
        self.id = id
        self.date = date
        self.chats_added = chats_added
        self.games_played = games_played
        self.cheats_detected = cheats_detected

    def __repr__(self):
        return "<DailyBotStats %s>" % self.id
    
DailyBotStats.__table__.create(checkfirst=True, bind=SESSION.bind)

def get_last30days_stats_sql() -> list:
    try:
        return SESSION.query(DailyBotStats).order_by(DailyBotStats.id).limit(30).all()
    except Exception as e:
        print(e)
        return []

def update_dailystats_sql(date: str, type: int, amount: int) -> bool:
    """
    type: 0 = games_played, 1 = cheats_detected, 2 = chats_added
    """
    try:
        adder = SESSION.query(DailyBotStats).filter_by(date=str(date)).first()
        if adder:
            if type == 0:
                adder.games_played = int(adder.games_played) + amount
            elif type == 1:
                adder.cheats_detected = int(adder.cheats_detected) + amount
            elif type == 2:
                adder.chats_added = int(adder.chats_added) + amount
            else:
                return False
        else:
            if type == 0:
                adder = DailyBotStats(None, str(date), 0, amount, 0)
            elif type == 1:
                adder = DailyBotStats(None, str(date), 0, 0, amount)
            elif type == 2:
                adder = DailyBotStats(None, str(date), amount, 0, 0)
            else:
                return False
        SESSION.add(adder)
        SESSION.commit()
        return True
    except Exception as e:
        print(e)
        SESSION.rollback()
        return False
