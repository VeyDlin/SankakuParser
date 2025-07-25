from ChanSankakuParser import ChanSankakuParser
from IdolSankakuParser import IdolSankakuParser
from Logger import Logger
import time
import os
from enum import Enum


class DonwloaderMode(Enum):
    IDOL = "idol"
    CHAN = "chan"


class Donwloader:
    save_counter = 1
    page_counter = 1
    is_authorized = False


    def __init__(self, save_dir = 'media', save_tags = True, formats_grouping = True, max_donwload = -1, mode = DonwloaderMode.CHAN):
        self.parser = ChanSankakuParser() if mode is DonwloaderMode.CHAN else IdolSankakuParser()
        self.mode = mode
        self.save_dir = save_dir
        self.save_tags = save_tags
        self.formats_grouping = formats_grouping
        self.max_donwload = max_donwload
        self.user = None
        self.password = None


    def init_driver(self):
        self.parser.init_driver()


    @staticmethod
    def auto_tag(text, mode = DonwloaderMode.CHAN):
        parser = ChanSankakuParser() if mode is DonwloaderMode.CHAN else IdolSankakuParser()
        return parser.auto_tag(text)


    def set_user(self, user, password):
        self.user = user
        self.password = password


    def download(self, search):
        Logger.info("Checking login...")
        try:
            if self.parser.check_auth(self.user):
                Logger.success("You are already successfully authorized")
                self.is_authorized = True
            else:
                Logger.info("You are not authorized")
        except:
            Logger.error("An error occurred while checking login")

        if not self.is_authorized and self.user and self.password:      
            Logger.info("Authorizing...")
            try:
                self.parser.auth(self.user, self.password)
                Logger.success("Authorization successful")
                self.is_authorized = True
            except Exception as err:
                Logger.warning("Authorization error; download without authorization")
            
        print()

        self.save_counter = 1
        self.page_counter = 1
        data = None
        try:
            Logger.page_header(self.page_counter)
            data = self.parser.search(search)
        except Exception as err:
            Logger.error("Search error", err)


        if self._download_page(data):
            while True:
                try:
                    Logger.page_header(self.page_counter)
                    data = self.parser.next()
                    if not data:
                        break

                    if not self._download_page(data):
                        break
                except Exception as err:
                    Logger.error("Error loading next page", err)
            
        Logger.success("DONE")


    def _download_page(self, data):
        for media in data:
            try:
                if media["request_full_info"]:
                    media = self.parser.get_full_info(media)
                    time.sleep(10)

                if self.formats_grouping:
                    save_dir = os.path.join(os.path.abspath(os.curdir), self.save_dir, media["format"])
                else:
                    save_dir = os.path.join(os.path.abspath(os.curdir), self.save_dir)
                
                os.makedirs(save_dir, exist_ok=True) 

                self.parser.download(media, save_dir, save_tags=self.save_tags)
                
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