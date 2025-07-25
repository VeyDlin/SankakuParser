from Donwloader import Donwloader, DonwloaderMode
from Logger import Logger
from InquirerPy import prompt
from InquirerPy.base.control import Choice
from InquirerPy.validator import EmptyInputValidator
from prompt_toolkit.completion import Completer, Completion, ThreadedCompleter
import json
import os
import re

mode = DonwloaderMode.CHAN

def get_config():
    f = open('config.user.json' if os.path.exists('config.user.json') else 'config.json')
    config = json.load(f)
    f.close()
    return config


def get_simple_name(name):
    name = re.sub(r'[\W_]+', ' ', name)
    name = re.sub(r'[^\x00-\x7f]', ' ', name)
    name = re.sub(r' +', '_', name.lower().strip())
    return name 


class SankakuTagCompleter(Completer):
    def get_completions(self, document, complete_event):
        before = document.get_word_before_cursor()
        for tag in Donwloader.auto_tag(before, mode):
            yield Completion(tag, -len(before))


mode = prompt([{
    'type': 'list',
    'name': 'mode',
    'message': 'Mode:',
    'choices': [
        Choice(value=DonwloaderMode.CHAN, name="Chan"),
        Choice(value=DonwloaderMode.IDOL, name="Idol"),
    ],
    'default': DonwloaderMode.CHAN
}])['mode']


answers = prompt([
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
        'type': 'list',
        'name': 'save_tags',
        'message': 'Save .txt tag files?:',
        'choices': [
            Choice(value=True, name="Yes"),
            Choice(value=False, name="No"),
        ],
        'default': True
    },
    {
        'type': 'list',
        'name': 'formats_grouping',
        'message': 'Create a separate directory for each data type (jpeg/pgn/mp4..)?:',
        'choices': [
            Choice(value=True, name="Yes"),
            Choice(value=False, name="No"),
        ],
        'default': False
    },
    {
        'type': 'input',
        'name': 'max_donwload',
        'message': 'How many files download?:',
        'default': 'all',
        'validate': lambda result: result.isdigit() and int(result) > 0 or result == 'all' or 'Must be "all" or a positive number'
    }
])

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
    max_donwload=max_donwload,
    mode=mode
)

donwloader.init_driver()

user_config = config['sankaku']['chan'] if mode is DonwloaderMode.CHAN else config['sankaku']['idol']
if user_config['username'] and user_config['password']:
    donwloader.set_user(user_config['username'], user_config['password'])
else:
    Logger.info('Download without authorization')

print()

donwloader.download(search_query)