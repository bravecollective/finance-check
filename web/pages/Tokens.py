import os
from typing import Union

import mysql.connector
import requests
from flask import render_template, Response, url_for, session, Flask
from werkzeug.utils import redirect


class Tokens:
    __corporation_names = {}

    __have_corporations = []

    __available_tokens = []

    def __init__(self, app: Flask):
        self.__app = app
        self.__esi_base_url = 'https://esi.evetech.net/latest'
        self.__core_base_url = os.getenv('API_BASE_URL') + '/api/app'
        self.__auth_header = {'Authorization': 'Bearer ' + os.getenv('API_KEY')}
        self.__login_name = os.getenv('API_EVE_LOGIN')
        self.__check_alliances = os.getenv('CHECK_ALLIANCES')
        self.__check_corporations = os.getenv('CHECK_CORPORATIONS')

        self.__db = mysql.connector.connect(
            host=os.getenv('DB_HOST'),
            port=os.getenv('DB_PORT', 3306),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_DATABASE'),
        )

    def show(self) -> Union[str, Response]:
        if 'character_id' not in session:
            return redirect(url_for('auth_login'))

        want_corporations = self.__fetch_alliance_corporations()
        if self.__check_corporations:
            want_corporations[0] = [int(x) for x in self.__check_corporations.split(',')]

        all_corporation_ids = []
        for alliance_id in want_corporations.keys():
            all_corporation_ids = all_corporation_ids + want_corporations[alliance_id]
        self.__fetch_names(all_corporation_ids)

        cursor = self.__db.cursor(dictionary=True)
        cursor.execute("SELECT id, corporation_name, character_id, last_journal_date, active FROM corporations")
        self.__have_corporations = cursor.fetchall()
        cursor.close()

        url = '{}/v1/esi/eve-login/{name}/token-data'.format(self.__core_base_url, name=self.__login_name)
        response = requests.get(url, headers=self.__auth_header)
        if response.status_code == 200:
            self.__available_tokens = response.json()
        else:
            self.__app.logger.error(response.content)

        return render_template(
            'tokens.html',
            character_id=session['character_id'],
            want_corporations=want_corporations,
            have_corporations=self.__have_corporations,
            find_have_corporation=self.__find_have_corporation,
            find_available_tokens=self.__find_available_tokens,
            find_corporation_name=self.__find_corporation_name
        )

    def __fetch_alliance_corporations(self) -> dict:
        # return {99003214: [98024275], 99010079: [98112599, 98209548]}
        want_alliance_corporations = {}
        if self.__check_alliances:
            for alliance_id in [int(x) for x in self.__check_alliances.split(',')]:
                url = '{}/alliances/{alliance_id}/corporations/'.format(self.__esi_base_url, alliance_id=alliance_id)
                response = requests.get(url)
                if response.status_code == 200:
                    want_alliance_corporations[alliance_id] = response.json()
                else:
                    self.__app.logger.error(response.content)
        return want_alliance_corporations

    def __fetch_names(self, corporation_ids: []) -> None:
        """self.__corporation_names = {
           98024275: 'Rational Chaos Inc.', 98112599: 'Black Queen Enterprises', 98209548: 'Brave Little Toaster.',
           98645283: 'Brave United Holding', 98599810: 'Brave Nubs'}
        return"""
        url = '{}/universe/names/'.format(self.__esi_base_url)
        response = requests.post(url, json=corporation_ids)  # Note: corporation_ids cannot have more than 1000 items
        if response.status_code == 200:
            for item in response.json():
                if item['category'] == 'corporation':
                    self.__corporation_names[item['id']] = item['name']
        else:
            self.__app.logger.error(response.content)

    def __find_have_corporation(self, corporation_id: int) -> Union[dict, None]:
        for corporation in self.__have_corporations:
            if corporation['id'] == corporation_id:
                return corporation

    def __find_available_tokens(self, corporation_id: int) -> list:
        tokens = []
        for token in self.__available_tokens:
            if token['corporationId'] == corporation_id:
                tokens.append(token)
        return tokens

    def __find_corporation_name(self, corporation_id: int) -> str:
        if corporation_id in self.__corporation_names:
            return self.__corporation_names[corporation_id]
        return ''
