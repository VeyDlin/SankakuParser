from SankakuParser import SankakuParser
from Logger import Logger
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
                
                Logger.success(f"{Logger.s(self.save_counter, 'pointer')} | {Logger.s(media['id'], 'pointer')} | {Logger.s(media['file'], 'skipped')}")

                self.save_counter += 1
                if self.save_counter > self.max_donwload and self.max_donwload > 0:
                    return False

            except Exception as err:
                Logger.error("Error while downloading file", err)
        
        self.page_counter += 1
        Logger.page_separator(self.page_counter)
        time.sleep(5)

        return True


    def download(self, search):
        if not self.is_authorized and self.user and self.password:      
            Logger.info("Authorization... ")
            try:
                self.sankaku.auth(self.user, self.password)
                Logger.success("Authorization successful")
                self.is_authorized = True

            except Exception as err:
                Logger.error("Authorization error", err)
                return

            print()

        self.save_counter = 1
        self.page_counter = 1
        data = None
        try:
            Logger.page_header(self.page_counter)
            data = self.sankaku.search(search)
        except Exception as err:
            Logger.error("Search error", err)


        if self.download_page(data):
            while True:
                try:
                    Logger.page_header(self.page_counter)
                    data = self.sankaku.next()
                    if not data:
                        break

                    if not self.download_page(data):
                        break
                except Exception as err:
                    Logger.error("Error loading next page", err)
            
        Logger.success("DONE")