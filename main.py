from Donwloader import Donwloader
from SankakuParser import SankakuParser
from Logger import Logger
from InquirerPy import prompt
from InquirerPy.validator import EmptyInputValidator
from prompt_toolkit.completion import Completer, Completion, ThreadedCompleter
import json
import os
import re


def get_config():
    f = open('config.user.json' if os.path.exists('config.user.json') else 'config.json')
    config = json.load(f)
    f.close()
    return config


def get_simple_name(name):
    name = re.sub('[\W_]+', ' ', name)
    name = re.sub(r'[^\x00-\x7f]', ' ', name)
    name = re.sub(' +', '_', name.lower().strip())
    return name 


class SankakuTagCompleter(Completer):
    def get_completions(self, document, complete_event):
        before = document.get_word_before_cursor()
        for tag in SankakuParser.auto_tag(before):
            yield Completion(tag, -len(before))


questions = [
    {
        'type': 'input',
        'name': 'search_query',
        'message': 'Search query:',
        "completer": ThreadedCompleter(SankakuTagCompleter()),
        'default': 'order:popular',
        'validate': EmptyInputValidator(message="Search query cannot be empty")
    },
    {
        'type': 'input',
        'name': 'save_dir',
        'message': 'Enter name of the database directory to save:',
        'default': lambda answers: get_simple_name(answers['search_query']),
        'validate': EmptyInputValidator(message="Save directory cannot be empty")
    },
    {
        'type': 'confirm',
        'name': 'save_tags',
        'message': 'Save .txt tag files? (default "yes"):',
        'default': True
    },
    {
        'type': 'confirm',
        'name': 'formats_grouping',
        'message': 'Create a separate directory for each data type (jpeg/pgn/mp4..)? (default "no"):',
        'default': False
    },
    {
        'type': 'input',
        'name': 'max_donwload',
        'message': 'How many files download?:',
        'default': 'all',
        'validate': lambda result: result.isdigit() and int(result) > 0 or result == 'all' or 'Must be "all" or a positive number'
    }
]

answers = prompt(questions)

search_query = answers['search_query'].strip()
save_dir = answers['save_dir'].strip()
save_tags = answers['save_tags']
formats_grouping = answers['formats_grouping']
max_donwload = int(answers['max_donwload']) if answers['max_donwload'] != 'all' else -1

config = get_config()

donwloader = Donwloader(
    save_dir=os.path.join(config['save']['save_dir'], save_dir), 
    save_tags=save_tags, 
    formats_grouping=formats_grouping, 
    max_donwload=max_donwload
)

if config['sankaku']['username'] and config['sankaku']['password']:
    donwloader.set_user(config['sankaku']['username'], config['sankaku']['password'])
else:
    Logger.info('Download without authorization')

Logger.info('')

donwloader.download(search_query)