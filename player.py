from threading import Thread, Lock
from random import choice, random
from time import sleep, strftime
from termcolor import colored
import logging
import os

import requests
import json


logger = logging.basicConfig()
lock = Lock()


base_url = 'https://eentegen100.gamedia.nl/eentegen100/api/'
register = 'user/register'
rooms = 'rooms/getuserrooms'
find_game = 'room/findgame'
find_user = 'user/find'
questions = ''
headers = {'Content-Type': 'application/x-www-form-urlencoded',
           'X-Unity-Version': '2018.4.6f1',
            'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 5.1.1; XT1524 Build/LMY49F)',
            'Host': 'eentegen100.gamedia.nl',
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip'}
letters  = ['a', 'b', 'c']

authentication_data = '''
{{"ID": 0,
"PictureVersion": 0,
"Username": "{username}",
"Password": "{password}",
"Email": "{email}",
"SessionToken": null,
"HasWon1vs100": false,
"TotalXp": 0,
"HasAcceptedGdpr": {gdpr}
}}
'''

with open('/usr/share/dict/words') as fle:
    words = fle.read().split()


if os.path.exists('./answers.json'):
    with open('answers.json') as fle:
        answers = json.load(fle)
else:
    answers = {}

if os.path.exists('./players.json'):
    with open('players.json') as fle:
        players = json.load(fle)
else:
    players = {}


def post(session, url, data, headers=headers):
    data = {key: json.dumps(value) if type(value) in [list, dict]
            else value for key, value in data.items()}
    return session.post(url, headers=headers, data=data, verify=False)


def handle_content(result, function=''):
    try:
        return result.json()['Content']
    except Exception as e:
        print(function, colored('ContentError' + function, 'red'), e)
        print(colored(result.content, 'yellow'))
        return False


def save_question(question):
    with lock:
        answers[question['ID']] = question


def save_answer(question_id, answer):
    with lock:
        answers[question_id]['answer'] = answer


def get_answer(question_id):
    return answers.get(question_id, {}).get('answer', random.choice(['a', 'b', 'c']))


players = {}


class Player(Thread):
    def __init__(self, email="", username="", password=""):
        super().__init__()
        self.session = requests.Session()
        self.user = {}

        # Look like the actual app
        self.session.get(base_url + 'game/getversion')

        email = email or str(random() * 100) + "@mailinator.com"
        username = username or choice(words)
        password = password or "password"
        self.credentials = [self.email, self.username, self.password]

        user = self.login(*self.credentials)
        if user:
            self.user = user
        else:
            if self.register(*self.credentials):
                self.user = self.login(*self.credentials)

    def register(self, email, username, password):
        data = {'user': json.loads(authentication_data.format(
            username=username,
            password=password,
            email=email,
            gdpr="null").replace('\n', ''))}

        result = post(self.session, base_url + "user/register",
                      headers=headers, data=data)
        res = handle_content(result, 'register')
        if res:
            if res['RegisterSuccess']:
                return True
        return False

    def login(self, email, username, password):
        url = base_url + 'user/login'
        data = {'user': json.loads(authentication_data.format(
            username=username,
            password=password,
            email=email,
            gdpr="true").replace('\n', ''))}
        result = post(self.session, url, data=data)
        logging.info(result.text)
        res = handle_content(result, 'login')

        if res:
            if res['LoginSuccess']:
                print(res['User']["Username"], colored('Logged in...', 'green'))
                return res['User']
        return False

    def get_user_rooms(self):
        url = base_url + 'room/getuserrooms'
        data = {'user': self.user, 'retrieveXp': True}
        current_room = post(self.session, url, data=data)
        room_json = handle_content(current_room, 'get_user_room')

        if room_json:
            session_token = current_room.json().get("SessionToken", 0)
            self.user['SessionToken'] = session_token
            return [room for room in room_json['UserRooms']]
        return False

    def find_room(self, room_type):
        url = base_url + find_game
        data = {'user': self.user,
                'roomType': room_type}

        room = post(self.session, url, data=data, headers=headers)
        room_json = handle_content(room, 'find_room')

        if room_json:
            return room_json
        return False

    def find_1vs100_game(self):
        user_rooms = self.get_user_rooms()
        existing = [room for room in user_rooms
                    if room['RoomOfUser']['RoomType'] == "1vs100"]
        if not existing:
            room = self.find_room('1vs100')

            if "RoomOfUser" in room:
                self.user['SessionToken'] = room['SessionToken']
                return room['RoomOfUser']
            else:
                return room
        else:
            return existing[0]['RoomOfUser']

    def get_question(self, room):
        data = {'user': self.user, 'room': room}
        print('getting question')
        print(data)
        print()
        question = post(self.session, base_url + 'question/get', data=data,
                        headers=headers)
        return handle_content(question, 'get_question')

    def answer_questions(self, room, correct=False):
        question = self.get_question(room)
        while question:
            save_question(question)
            logging.info(question['QuestionText'])
            if correct:
                answer_letter = get_answer(question['ID'])
            else:
                answer_letter = choice(letters)

            end = self.submit_answer(question, room, answer_letter)

            if end:
                question = False
            else:
                question = self.get_question(room)

    def submit_answer(self, question, room, answer=''):
        data = {'user': self.user,
                'userMove': {
                    'CurrentQuestion': question,
                    'GivenAnswer': answer,
                    "CorrectAnswer": "\u0000",
                    "EscapeUsed": False,
                    "JokerUsed": False,
                    "TimeTaken": None,
                    "ScoreForQuestion": 0},
                'room': room,
                }
        sleep(1 + random())
        move_raw = post(self.session, base_url + 'question/submit', data=data)
        move = handle_content(move_raw, 'submit_answer')
        print('answered')

        if move:
            save_answer(question['ID'], move['Move']['CorrectAnswer'])

            self.user['SessionToken'] = move_raw.json()['SessionToken']
            return move['endOfGame']

        return True

    def accept_room(self, room):
        url = base_url + 'room/accept'
        data = {'user': self.user,
                'room': room['RoomOfUser'],
                }

        result = post(self.session, url, data=data)
        if result:
            return True
        return False

    def get_room_state(self, room):
        url = base_url + 'score/getroomstate'
        data = {'user': self.user,
                'room': room}
        state = post(self.session, url, data=data, headers=headers)
        state = handle_content(state, 'get_room_state')
        if state:
            return state
        else:
            print('RoomState error', state)
            return False

    def play_1vs100(self, god_mode=False):
        room = self.find_1vs100_game()
        self.answer_questions(room, god_mode)

    def delete_account(self):
        url = base_url + 'user/deleteprofile'
        data = {'user': self.user}
        post(self.session, url, data)

    def get_friend_list(self):
        url = base_url + 'user/getfriends'
        data = {'user': self.user}
        res = post(self.session, url, data=data)
        friend_list = handle_content(res)
        return friend_list

    def find_users(self, name):
        url = base_url + 'user/find'
        data = {'user': self.user, 'userName': name}
        result = post(self.session, url, data=data)
        other_user = handle_content(result)
        return other_user

    def add_friend(self, other):
        url = base_url + 'user/addfriend'
        data = {'currentUser': self.user,
                'friendUser': other.user
                }
        sleep(random())
        invitation = post(self.session, url, data=data)
        invitation_result = handle_content(invitation, 'add_friend')

    def accept_friend(self, other):
        url = base_url + 'user/accept'
        data = {'currentUser': self.user,
                'friendUser': other.user
                }
        result = post(self.session, url, data=data)
        print(handle_content(result, 'accept friend'))

    def play_1vs1(self, room):
        choose_category = room['ChooseCategory']
        if choose_category:
            category = self.get_category(room)
            if category:
                session_token = self.submit_category(room, category)
                if session_token:
                    self.user['SessionToken'] = session_token
        else:
            room_state = self.get_room_state(room)
            self.user['SessionToken'] = \
                    room_state['AllUserMovesAtQuestion'][0]['CurrentUser']['SessionToken']
        print('Starting to answer questions', room['RoomOfUser'])
        print()
        self.answer_questions(room['RoomOfUser'])

    def get_category(self, room):
        url = base_url + 'room/getcategories'
        data = {'user': self.user,
                'room': room['RoomOfUser']}
        categories_result = post(self.session, url, data=data)
        categories = handle_content(categories_result, 'get Category')

        if categories:
            for category in categories:
                if category['Name'] == 'Computer en media':
                    break
                if category['Name'] == 'Kunst en cultuur':
                    break
                if category['Name'] == 'Muziek':
                    break
                if category['Name'] == 'Geschiedenis':
                    break
        else:
            return False
        return category

    def submit_category(self, room, category):
        url = base_url + 'room/submitcategory'
        data = {'category': category,
                'user': self.user,
                'room': room['RoomOfUser']}
        res = post(self.session, url, data=data).json()
        if res:
            return res['SessionToken']
        return False

    def invite_user(self, other):
        url = base_url + 'room/invite'
        data = {'currentUser': self.user,
                'otherUser': other.user}
        post(self.session, url, data)

    def play_all_rooms(self):
        rooms = self.get_user_rooms()
        for room in rooms:
            if room_is_active(room):
                room_type = room['RoomOfUser']['RoomType']
                if room_type == '1vs1':
                    print(room)
                    other_user = get_player(room['OtherUser']['ID'])
                    if not room['UserHasAccepted']:
                        if self.accept_room(room):
                            continue
                        else:
                            print('Error in accepting room', room)
                    elif room['UserHasAccepted'] and room['OtherUserHasAccepted'] \
                        and room['UserHasOpenQuestions']\
                        or room['ChooseCategory']:
                        self.play_1vs1(room)
                    else:
                        pass
                else:
                    self.answer_questions(room['RoomOfUser'])

def room_is_active(room):
    if (room['TimeLeftInMinutes'] != -1
        and room['RoomOfUser']['Round'] <= 2):
        return True
    return False

def get_user(id_):
    return players[id_]

if __name__ == '__main__':
    if not players:
        for _ in range(2):
            player = Player()
            players[player.user['ID']] = player

    num_games = 7
    try:
        while True:
            for _ in range(num_games):
                player.invite_user(player2)

            for _ in range(num_games):
                player.play_all_rooms()
                player2.play_all_rooms()
    except KeyboardInterrupt:
        print('Quitting, please wait while we save things')
        with open('answers.json', 'w') as fle:
            json.dump(answers, fle)

        with open('players.json', 'w') as fle:
            json.dump({id_: player.credentials for id_, player in players.items()})
        print('Done saving.')
    finally:
        print('Bye!')
