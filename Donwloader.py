from SankakuParser import SankakuParser
from BColors import BColors
import time
import os



class Donwloader:
    save_dir = None
    sankaku = None
    user = None
    password = None
    save_tags  = None
    formats_grouping = None
    max_donwload = None
    
    save_counter = 1
    page_counter = 1
    is_authorized = False



    def __init__(self, save_dir = 'media', save_tags = True, formats_grouping = True, max_donwload = -1):
        self.sankaku = SankakuParser()
        self.save_dir = save_dir
        self.save_tags = save_tags
        self.formats_grouping = formats_grouping
        self.max_donwload = max_donwload



    def set_user(self, user, password):
        self.user = user
        self.password = password



    def download_page(self, data):
        for media in data:
            try:
                if self.formats_grouping:
                    save_dir = os.path.join(os.path.abspath(os.curdir), self.save_dir, media["format"])
                else:
                    save_dir = os.path.join(os.path.abspath(os.curdir), self.save_dir)
                
                os.makedirs(save_dir, exist_ok=True) 

                self.sankaku.download(media, save_dir, save_tags=self.save_tags)

                print(f'{BColors.OKGREEN} [OK] {BColors.ENDC} {BColors.OKBLUE} {self.save_counter} {BColors.ENDC} | {BColors.OKBLUE} {media["id"]} {BColors.ENDC} | {media["file"]}')

                self.save_counter += 1
                if self.save_counter > self.max_donwload and self.max_donwload > 0:
                    return False

            except Exception as err:
                print(f'{BColors.FAIL} [ERROR] {err=}, {type(err)=} {BColors.ENDC}')
        
        self.page_counter += 1
        print(f'{BColors.OKGREEN} [------------------------ PAGE {self.page_counter} END ------------------------] {BColors.ENDC}')
        print()
        time.sleep(5)

        return True



    def download(self, search):
        if not self.is_authorized and self.user and self.password:      
            print(f'{BColors.WARNING} Authorization... {BColors.ENDC}', end='')
            try:
                self.sankaku.auth(self.user, self.password)
                print(f'{BColors.OKGREEN} [OK] {BColors.ENDC}')

                self.is_authorized = True

            except Exception as err:
                print(f'{BColors.FAIL} [ERROR] {err=}, {type(err)=} {BColors.ENDC}')
                return

            print()

        self.save_counter = 1
        self.page_counter = 1

        data = None
        try:
            print(f'{BColors.OKGREEN} [------------------------ LOAD {self.page_counter} PAGE ------------------------] {BColors.ENDC}')
            data = self.sankaku.search(search)
        except Exception as err:
            print(f'{BColors.FAIL} [ERROR] {err=}, {type(err)=} {BColors.ENDC}')


        if self.download_page(data):
            while True:
                try:
                    print(f'{BColors.OKGREEN} [------------------------ LOAD {self.page_counter} PAGE ------------------------] {BColors.ENDC}')
                    data = self.sankaku.next()
                    if not data:
                        break

                    if not self.download_page(data):
                        break
                except Exception as err:
                    print(f'{BColors.FAIL} [ERROR] {err=}, {type(err)=} {BColors.ENDC}')
            
        print(f'{BColors.OKGREEN} [DONE] {BColors.ENDC}')

