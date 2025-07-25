from urllib.parse import quote_plus
from SankakuParserBase import SankakuParserBase
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import requests


class ChanSankakuParser(SankakuParserBase):
    def __init__(self):
        super().__init__() 
        self.search_params = "lang=en&hide_posts_in_books=in-larger-tags&limit=40"
        self.last_next_id = ""
        self.last_search_tags = ""


    def __del__(self):
        super().__del__()


    def check_auth(self, user=None, delay=30):
        super()._get_driver().get("https://sankaku.app")
        try:
            json = self._get_json(f'https://sankakuapi.com/users/me?lang=en')
            if user:
                if json['user']['name'] != user:
                    self._clear_all_site_data()
                    return False
        
            return True
        except:
            return False


    def auth(self, user, password, delay=30):
        driver = super()._get_driver()
        try:
            driver.get("https://login.sankakucomplex.com/login")
    
            present = EC.presence_of_element_located((By.CSS_SELECTOR, "form input[name='email']"))
            WebDriverWait(driver, delay).until(present)

            time.sleep(3)

            email_input = driver.find_element(By.CSS_SELECTOR, "form input[name='email']")
            password_input = driver.find_element(By.CSS_SELECTOR, "form input[name='password']")
            submit_button = driver.find_element(By.CSS_SELECTOR, "form button[type='submit']")

            email_input.send_keys(user)
            password_input.send_keys(password)

            submit_button.click()

            present = EC.presence_of_element_located((By.XPATH, "//div[normalize-space()='Not now']"))
            WebDriverWait(driver, delay).until(present)

            not_now = driver.find_element(By.XPATH, "//div[normalize-space()='Not now']")
            not_now.click()

            present = EC.presence_of_element_located((By.CSS_SELECTOR, "input[id='autocomplete']"))
            WebDriverWait(driver, delay).until(present)
        except Exception as e:
            raise Exception('Wrong username or password')
        
        time.sleep(1)


    def search(self, tags):
        self.last_search_tags = quote_plus(tags)
    
        json = self._get_json(f'https://sankakuapi.com/v2/posts/keyset?{self.search_params}&tags={self.last_search_tags}')
        self.last_next_id = json['meta']['next']
        
        return self._search_cleaner(json)
    

    def auto_tag(self, text):
        try:
            words =  text.strip().split()  
            last_word = words[0] if words else ""
            if last_word == "":
                return []

            encoded_tag = quote_plus(last_word)
            json_data = self._get_json(f'https://sankakuapi.com/tags/autosuggestCreating?tag={encoded_tag}&show_meta=0&target=post', with_driver=False)

            return [item["tagName"] for item in json_data if "tagName" in item]
        except:
            return []


    def next(self):
        if self.last_next_id is None:
            return []

        json = self._get_json(f'https://sankakuapi.com/v2/posts/keyset?{self.search_params}&tags={self.last_search_tags}&next={self.last_next_id}')
        self.last_next_id = json['meta']['next']

        return self._search_cleaner(json)
    

    def get_full_info(self, info):
        return info


    def _get_json(self, url, with_driver=True, site_url=None):
        if with_driver:
            session = super()._get_requests_session(site_url)
            json_data = session.get(url).json()
            session.close()

            if 'success' in json_data and not json_data['success']:
                raise Exception(json_data['code'])

            return json_data
        else:
            return requests.get(url).json()
        

    def _search_cleaner(self, json):
        clean_data = []

        for media in json['data']:
            if media['file_url'] is None:
                continue

            clean_data.append({
                'id': media['id'],
                'file': media['file_url'],
                'format': media['file_type'].split('/')[1],
                'tags': super()._tags_cleaner(media['tag_names']),
                'request_full_info': False
            })

        return clean_data
