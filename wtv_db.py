import logging
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()
from sqlalchemy import create_engine
from sqlalchemy import Column, Integer, String, Date, ForeignKey, Boolean, Text
from sqlalchemy.orm import sessionmaker, relationship
import os
from datetime import date, datetime
import sys


def is_int(s):
    try:
        int(s)
        return True
    except ValueError:
        return False


class Series(Base):
    __tablename__ = 'series'

    id = Column(Integer, primary_key=True)
    name = Column(String(128), unique=True)

    def __repr__(self):
        return 'Series[Id={}, Name={}]'.format(self.id, self.name)


class CandidateEpisode(Base):
    __tablename__ = 'candidate_episode'

    id = Column(Integer, primary_key=True)
    name = Column(String(128))
    description = Column(Text)
    air_date = Column(Date)
    season = Column(Integer)
    episode_num = Column(Integer)
    series_id = Column(Integer, ForeignKey('series.id'))
    series = relationship('Series')

    wtv_file_id = Column(Integer, ForeignKey('wtv_file.filename'))
    wtv_file = relationship('WtvFile', back_populates='candidate_episodes')

    @staticmethod
    def from_tvdb(series, e):
        return CandidateEpisode(id=int(e['id']),
                                name=e['episodeName'],
                                description=e['overview'],
                                air_date=datetime.strptime(e['firstAired'], '%Y-%m-%d').date(),
                                season = int(e['airedSeason']),
                                episode_num=int(e['airedEpisodeNumber']),
                                series=series )

    def get_details(self):
        padded_season = str(self.season) if self.season >= 10 else '0' + str(self.season)
        padded_episode_num = str(self.episode_num) if self.episode_num >= 10 else '0' + str(self.episode_num)
        return '{} - s{}e{} - {}'.format(self.series.name, padded_season, padded_episode_num, self.name)

    def __repr__(self):
        return 'Episode[id={}, series={}, name={}, air_date={}, season={}, num={}]'.format(self.id, self.series.name,
                                                                                           self.name, self.air_date,
                                                                                           self.season,
                                                                                           self.episode_num)


class WtvFile(Base):
    __tablename__ = 'wtv_file'

    filename = Column(String(256), primary_key=True)
    description = Column(Text)
    candidate_episodes = relationship('CandidateEpisode', cascade='all, delete-orphan')
    selected_episode = relationship('SelectedEpisode', back_populates='wtv_file', uselist=False, cascade='all, delete-orphan')


class SelectedEpisode(Base):
    __tablename__ = 'selected_episode'

    # id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey('candidate_episode.id'), nullable=False)
    episode = relationship('CandidateEpisode', uselist=False)
    wtv_file_id = Column(String(256), ForeignKey('wtv_file.filename'), nullable=False, primary_key=True)
    wtv_file = relationship('WtvFile', uselist=False, back_populates='selected_episode')


class WtvDb():
    def __init__(self, db_file):
        if ':memory:' == db_file:
            self._engine = create_engine('sqlite:///:memory:', echo=False)
        else:
            path = os.path.abspath(db_file)
            self._engine = create_engine('sqlite:///' + path, echo=False)
        Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine)
        self._session = self._Session()

    def store_candidates(self, tvdb, wtv_filename, meta, episodes):
        series_name = meta['Title']
        series = tvdb.search_series(series_name)
        candidates = [CandidateEpisode.from_tvdb(series, e) for e in episodes]
        wtv_file = WtvFile(filename=wtv_filename, description=meta['WM/SubTitleDescription'])
        wtv_file=self._session.merge(wtv_file)
        wtv_file.candidate_episodes=candidates
        self._session.commit()

    def get_or_create_series(self, id, series_name):
        series = self._session.query(Series).get(id)
        if not series:
            series = Series(id=id, name=series_name)
            self.save(series)
        return series

    def save(self, obj):
        self._session.add(obj)
        self._session.commit()

    def find_series(self, series_name):
        query = self._session.query(Series).filter(Series.name == series_name)
        return query.one_or_none()

    def get_selected_episode(self, wtv_filename):
        query = self._session.query(WtvFile).filter(WtvFile.filename == wtv_filename)
        wtv = query.one_or_none()
        if wtv and wtv.selected_episode:
            return wtv.selected_episode.episode
        else:
            return None

    def get_wtv(self, filename):
        return self._session.query(WtvFile).get(filename)

    def delete_wtv(self, filename):
        wtv_file = self.get_wtv(filename)
        if wtv_file:
            self._session.delete(wtv_file)
            self._session.commit()
        else:
            raise Exception('File not found: {}'.format(filename))

    def resolve_all(self):
        query = self._session.query(WtvFile).order_by(WtvFile.filename).all()
        for wtv_file in query:
            print()
            if self.resolve(wtv_file):
                return

    def resolve(self, wtv_file):
        while True:
            print(wtv_file.filename)
            print(wtv_file.description)
            print()
            print('Options:')
            count = 1
            for ep in wtv_file.candidate_episodes:
                selected = ''
                if wtv_file.selected_episode and wtv_file.selected_episode.episode == ep:
                    selected = '*'
                print('  {}{}) '.format(selected, count), end='')
                print(ep.get_details())
                print('     Air Date: {}'.format(ep.air_date))
                print('     {}'.format(ep.description))
                count += 1
            selection = input('Selection: ')
            if selection == 'q':
                return True
            elif selection == '':
                return False
            elif is_int(selection):
                s = int(selection)
                if 0 < s < count:
                    if wtv_file.selected_episode:
                        wtv_file.selected_episode.episode = wtv_file.candidate_episodes[s - 1]
                        self.save(wtv_file)
                    else:
                        self.save(SelectedEpisode(episode=wtv_file.candidate_episodes[s - 1], wtv_file=wtv_file))
                else:
                    print('Invalid input')
            else:
                print('Invalid input')


if __name__ == '__main__':
    if len(sys.argv) > 1:
        wtvdb = WtvDb(sys.argv[1])
        wtvdb.resolve_all()
    else:
        print('Too few args')
