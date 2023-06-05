from Donwloader import Donwloader
from BColors import BColors
import json
import os
import re


def get_config(config_path):
    f = open(config_path)
    config = json.load(f)
    f.close()
    return config


def get_simple_name(name):
    name = re.sub('[\W_]+', ' ', name)
    name = re.sub(r'[^\x00-\x7f]', ' ', name)
    name = re.sub(' +', '_', name.lower().strip())
    return name 


def print_enter(data):
    if data:
        print(f'{BColors.OKGREEN}> {data}{BColors.ENDC}')



config = get_config('config.json')



print('Search query (default "order:popular"): ', end='')
search_query = input()
if not search_query:
    search_query = 'order:popular'
print_enter(search_query)



default_save_dir = get_simple_name(search_query)
print(f'Enter name of the database directory to save (default "{default_save_dir}"): ', end='')
save_dir = input()
if not save_dir:
    save_dir = default_save_dir
print_enter(save_dir)



print('Save .txt tag files? (default "yes") [y/n]: ', end='')
save_tags = input() != 'n'
print_enter('yes' if save_tags else 'no')



print('Create a separate directory for each data type (jpeg/pgn/mp4..)? (default "no") [y/n]: ', end='')
formats_grouping = input() == 'y'
print_enter('yes' if formats_grouping else 'no')



print('How many files download? (Press "Enter" or write -1 to download all): ', end='')
max_donwload = input()
if not max_donwload:
    max_donwload = -1

try:
    max_donwload = int(max_donwload)
except:
    max_donwload = -1
print_enter('all' if max_donwload <= 0 else max_donwload)



donwloader = Donwloader(
    save_dir=os.path.join(config['save']['save_dir'], save_dir), 
    save_tags=save_tags, 
    formats_grouping=formats_grouping, 
    max_donwload=max_donwload
)

if config['sankaku']['username'] and config['sankaku']['password']:
    donwloader.set_user(config['sankaku']['username'], config['sankaku']['password'])
else:
    print_enter('download without authorization')

donwloader.download(search_query)