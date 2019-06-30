#!/usr/bin/python3

import json
import logging
import os
import socket
import sys

from flask import Flask, render_template, abort, jsonify, request
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

sys.path.append(os.getcwd())

"""APP CONFIGURATION """
ip = '127.0.0.1'
port = 5000
hostname = socket.gethostbyaddr(ip)[0]
transport_schema = 'http'

app = Flask(__name__)
logging.basicConfig(format='[%(asctime)s %(levelname)s]: %(message)s',
                    datefmt='%m/%d/%Y %I:%M:%S %p',
                    level='INFO')
basedir = os.path.abspath(os.path.dirname(__file__))

"""DATABASE CONNECTION PROPERTIES """

DB_HOST = 'localhost'
DB_USERNAME = 'classroom'
DB_PASSWORD = 'classroom'
DB_NAME = 'classroom_db'

DB_URL = os.environ.get('DATABASE_URL') or \
         'mysql://' + DB_USERNAME + ":" + DB_PASSWORD + "@" + DB_HOST + ':3306/' + DB_NAME


class Config(object):
    SQLALCHEMY_DATABASE_URI = DB_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False


config = Config()
app.config.from_object(config)
db = SQLAlchemy(app)

"""ORM"""
SENTENCE_ENTITY_NAME = 'Sentence'
SENTENCE_REFERENCE = 'sentence.id'
SENTENCE_BACK_REFERENCE = 'sentence'

EXERCISE_ENTITY_NAME = 'Exercise'
EXERCISE_REFERENCE = 'exercise.id'
EXERCISE_BACK_REFERENCE = 'exercise'

TASKS_ENTITY_NAME = 'Task'


class Sentence(db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False, unique=True)
    exercise_id = db.Column(db.Integer, db.ForeignKey(EXERCISE_REFERENCE), nullable=True)
    text = db.Column(db.Text(42940000), nullable=False)


class Exercise(db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False, unique=True)
    student_url = db.Column(db.String(50), unique=True, nullable=False)

    # sentences = db.relationship(EXERCISE_ENTITY_NAME, backref=SENTENCE_BACK_REFERENCE, lazy=True)
    # tasks = db.relationship(TASKS_ENTITY_NAME, backref=EXERCISE_BACK_REFERENCE, lazy=False)


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False, unique=True)
    sentence_id = db.Column(db.Integer, db.ForeignKey(SENTENCE_REFERENCE), nullable=False)
    correct_answer = db.Column(db.String(50), nullable=False)
    task_input = db.Column(db.String(50), nullable=True)
    is_completed = db.Column(db.Boolean, nullable=False, default=False)
    failed_attempts = db.Column(db.Integer, nullable=False, default=0)


migrate = Migrate(app, db)

# when we reach here, we should already have an initialized database layer
"""ROUTES AND HANDLERS"""
API_PREFIX = '/api/v1'


def bad_request(error_message):
    abort(400, {"message": error_message})  # FIXME: missing proper Content-Type header, it should be application/json


def not_found(error_message):
    abort(404, {"message": error_message})  # FIXME: missing proper Content-Type header, it should be application/json


def ok(message):
    return jsonify({'message': message}), 200


#### PUBLIC RESOURCES:
@app.route("/")
@app.route("/index")
def index():
    return '<a href="/exercise/TestLink">Test</a>'


@app.route("/exercise/<exercise_link>")
def exercise(exercise_link):
    return render_template("exercise.html", exercise_link=exercise_link)


@app.route("/check", methods=["POST"])
def check():
    ANSWERS = {'task1': 'am', 'task2': 'were'}
    check_answer_in_db = lambda _id, _answer: ANSWERS[_id] == _answer

    # https://javascript.info/bubbling-and-capturing
    payload = json.loads(request.data.decode('utf-8'))
    task_id = payload["task_id"]
    task_answer = payload["task_answer"]
    app.logger.info(payload)
    # TODO remove contraction sensitivity (parse "'m" as "am" and so on)

    submit_result = check_answer_in_db(task_id, task_answer)

    return jsonify(id=task_id, result=submit_result)


import re

TATOEBA_SEL = 'body > div > div.container > div > div.section > div.sentence-and-translations > div'
ID_SEL = 'md-subheader > a'
TEXT_SEL = 'div.sentence > div.text'

DEFAULT_TATOEBA_PARAMS = {
    'from': 'eng',
    'to': 'und',
    'orphans': 'no',
    'unapproved': 'no',
    'native': '',
    'user': '',
    'tags': '',
    'list': '907',
    'has_audio': '',
    'trans_filter': 'limit',
    'trans_to': 'und',
    'trans_link': '',
    'trans_user': '',
    'trans_orphan': '',
    'trans_unapproved': '',
    'trans_has_audio': '',
    'sort': 'words',
    'sort_reverse': 'yes'
}
import requests_html


def scrape_tatoeba_sentences(raw_query, **kwargs):
    max_pages = kwargs.pop('max_pages', 2)
    # TODO pagination (parameter max_pages)
    query_translator = {
        ' ': '+',
        '\(': '%28',
        '\|': '%7C',
        '\)': '%29',
        '\^': '%5E',
        '\$': '%24',
        '\?': '%3F'
        # add more?
    }
    query = raw_query
    for key, value in query_translator.items():
        query = re.sub(key, value, query)
    prefix = f"https://tatoeba.org/eng/sentences/search?query={query}&"
    if len(kwargs) == 0:
        kwargs = DEFAULT_TATOEBA_PARAMS
    url = prefix + '&'.join([f"{arg}={kwargs[arg]}" for arg in kwargs])
    app.logger.info('Scraping tatoeba for %s' % url)
    session = requests_html.HTMLSession(verify=False)
    r = session.get(url)
    if r.status_code == 200:
        app.logger.info('OK')
        response_translator = {
            r'</span>': '>',
            r'<span class="match">': '<',
            r'<div class="text" flex="" dir="ltr">\n {2,}| *</div>': ''
        }
        sentences = []
        for element in r.html.find(TATOEBA_SEL):
            try:
                (link,) = element.find(ID_SEL)[0].absolute_links
                id = link.split("/")[-1]
                text = element.find(TEXT_SEL)[0].html
                for key, value in response_translator.items():
                    text = re.sub(key, value, text)
                sentence = {'id': id, 'phrase': raw_query, 'text': text}

                # FIXME: replace text field with a json of sentence

                sentences.append(text.split('\n')[1].strip())
            except IndexError:
                pass

        return sentences
    else:
        app.logger.warning('Cannot reach tatoeba for some reason')
        return None


@app.route("/exercise/generate", methods=['POST'])
def generate():
    post_data = request.data.decode('utf-8')
    if not post_data or post_data == '':
        bad_request('Either the request body is missing, or json is incorrect.')
    queries = []
    try:
        queries = json.loads(request.data.decode('utf-8'))['queries']
    except Exception as e:
        bad_request('JSON cannot be decoded: %s' % e)
    app.logger.info('New search queries: %s' % queries)

    sentences = [scrape_tatoeba_sentences(s) for s in queries]

    return jsonify(sentences=sentences), 200


import uuid


def extract_tasks(sentence):
    parts = re.split(r"(<.*?>)", sentence)
    for part in parts:
        if part.startswith("<") and part.endswith(">"):
            task = part[1:-1]
            yield task


def save_sentence(sentence, exercise_id):
    entity = Sentence(text=sentence, exercise_id=exercise_id)
    db.session.add(entity)
    db.session.commit()
    return entity.id


def save_task(task, sentence_id):
    entity = Task(correct_answer=task, sentence_id=sentence_id)
    db.session.add(entity)
    db.session.commit()
    return entity.id


def save_exercise(unique_url):
    exercise = Exercise(student_url=unique_url)
    db.session.add(exercise)
    db.session.commit()
    return exercise.id


def create_exercise(sentences):
    def get_random_string(string_length=10):
        """Returns a random string of length string_length."""
        random = str(uuid.uuid4())  # Convert UUID format to a Python string.
        random = random.replace("-", "")  # Remove the UUID '-'.
        return random[0:string_length]  # Return the random string.

    unique_url = get_random_string(string_length=50)

    app.logger.info('Create new exercise')
    exercise_id = save_exercise(unique_url)
    app.logger.info("New exercise with id: %s" % exercise_id)
    for s in sentences:
        sentence_id = save_sentence(s, exercise_id)
        tasks = [r for r in extract_tasks(s)]
        app.logger.info('Storing tasks for sentence with id %s / exercise id: %s', sentence_id, exercise_id)
        for t in tasks:
            save_task(t, sentence_id)

    return unique_url


@app.route('/exercise/submit', methods=['PUT'])
def submit():
    post_data = request.json
    if not post_data:
        bad_request("Either the request body is missing or json is incorrect")
    if 'sentences' not in post_data:
        bad_request("Missing 'sentences' list in the post data")
    sentences = post_data['sentences']
    sentences_count = len(sentences)
    if sentences_count == 0:
        bad_request('Sentences list cannot be empty')

    app.logger.info("Submitting %s new sentence(s)" % sentences_count)
    unique_url = create_exercise(sentences=sentences)
    return jsonify(
        student_url=f"{transport_schema}://{hostname}:{port}/exercise/{unique_url}",
        tasks=sentences_count), 201


if __name__ == '__main__':
    app.run(host=ip, port=port)
