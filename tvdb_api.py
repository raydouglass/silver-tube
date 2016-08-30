import requests
import json
import sys

BASE_URL = 'https://api.thetvdb.com'

SERIES = {}


class TVDB():
    def __init__(self, api_key, username, user_key):
        self._api_key = api_key
        self._username = username
        self._user_key = user_key
        self._jwt = None
        self.series = {}
        self._read_data()

    def _get_jwt(self):
        payload = {'apikey': self._api_key, 'username': self._username, 'userkey': self._user_key}
        res = requests.post(BASE_URL + '/login', json=payload)
        res.raise_for_status()
        return res.json()['token']

    def refresh(self):
        if self._jwt is None:
            self._jwt = self._get_jwt()
        else:
            headers = {'Authorization': 'Bearer ' + self._jwt}
            res = requests.get(BASE_URL + '/refresh_token', headers=headers)
            if res.status_code == requests.codes.ok:
                self._jwt = res.json()['token']
            else:
                self._jwt = self._get_jwt()

    def search_series(self, name):
        if self._jwt is None:
            self.refresh()
        if name not in self.series:
            headers = {'Authorization': 'Bearer ' + self._jwt}
            params = {'name': name}
            res = requests.get(BASE_URL + '/search/series', params=params, headers=headers)
            if res.status_code == requests.codes.ok:
                res = res.json()
                for s in res['data']:
                    if s['seriesName'] == name:
                        self.series[name] = s['id']
                        self._write_data()
        return self.series[name]

    def get_episodes(self, series_id):
        if self._jwt is None:
            self.refresh()
        headers = {'Authorization': 'Bearer ' + self._jwt}
        page = 1
        episodes = []
        while page is not None:
            res = requests.get(BASE_URL + '/series/{}/episodes'.format(series_id), headers=headers,
                               params={'page': page})
            res = res.json()
            episodes.extend(res['data'])
            page = res['links']['next']
        return episodes

    def find_episode(self, series, episode=None, air_date=None):
        if episode is None and air_date is None:
            raise Exception('Both episode and air_date cannot be null')
        id = self.search_series(series)
        if id:
            if episode:
                episodes = self.get_episodes(id)
                for e in episodes:
                    if e['episodeName'] == episode:
                        return (e['airedSeason'], e['airedEpisodeNumber'])
            if air_date:
                if self._jwt is None:
                    self.refresh()
                headers = {'Authorization': 'Bearer ' + self._jwt}
                params = {'firstAired': air_date}
                res = requests.get(BASE_URL + '/series/{}/episodes/query'.format(id),
                                   headers=headers,
                                   params=params)
                res = res.json()
                if 'data' in res:
                    if len(res['data']) == 1:
                        e = res['data'][0]
                        return (e['airedSeason'], e['airedEpisodeNumber'])
        return (None, None)

    def test(self):
        # /series/{id}/episodes/query
        if self._jwt is None:
            self.refresh()
        headers = {'Authorization': 'Bearer ' + self._jwt}
        series_id = self.search_series('Parking Wars')
        res = requests.get(BASE_URL + '/series/{}/episodes/query/params'.format(series_id), headers=headers)
        return res.json()

    def query(self, series_name, firstAired):
        if self._jwt is None:
            self.refresh()
        headers = {'Authorization': 'Bearer ' + self._jwt}
        series_id = self.search_series(series_name)
        params = {'firstAired': firstAired}
        res = requests.get(BASE_URL + '/series/{}/episodes/query'.format(series_id), headers=headers, params=params)
        return res.json()

    def _write_data(self):
        with open('series.json', 'w') as file:
            json.dump(self.series, file)

    def _read_data(self):
        try:
            with open('series.json', 'r') as f:
                self.series = json.load(f)
        except (OSError, IOError) as e:
            pass


def main(args):
    import configparser
    import wtv
    configparser = configparser.ConfigParser()
    configparser.read('config.ini')
    TVDB_USERNAME = configparser.get('tvdb', 'username')
    TVDB_USER_KEY = configparser.get('tvdb', 'userkey')
    TVDB_API_KEY = configparser.get('tvdb', 'apikey')

    tvdb = TVDB(api_key=TVDB_API_KEY, username=TVDB_USERNAME, user_key=TVDB_USER_KEY)
    meta = wtv.extract_metadata(args[1])
    for key in meta:
        print('{}={}'.format(key, meta[key]))
    print()
    series = meta['Title']
    name = meta['WM/SubTitle']

    print('Title: {}'.format(series))
    print('SubTitle: {}'.format(name))
    season, episode_num = tvdb.find_episode(series, name)
    print('Season: {}'.format(season))
    print('Episode: {}'.format(episode_num))


if __name__ == '__main__':
    main(sys.argv)
