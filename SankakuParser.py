from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import urllib.parse
import time
import os
import requests
import shutil


class SankakuParser:
    driver = None
    search_params = 'lang=en&hide_posts_in_books=in-larger-tags&limit=40'
    last_next_id = ""
    last_search_tags = ""


    def __init__(self, debug_window = False):
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--enable-javascript")
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

        if not debug_window:
            chrome_options.add_argument("--autoplay-policy=user-gesture-required")
            chrome_options.add_argument("--log-level=3")
            chrome_options.add_argument('headless')
            chrome_options.add_argument('window-size=1920x1080')
            chrome_options.add_argument("disable-gpu")
            chrome_options.add_experimental_option(
                "prefs", {"profile.managed_default_content_settings.images": 2}
            )

        self.driver = webdriver.Chrome(options=chrome_options)


    def __del__(self):
        if self.driver:
            self.driver.quit()


    def get_requests_session(self):
        session = requests.Session()

        selenium_user_agent = self.driver.execute_script('return navigator.userAgent;')
        session.headers.update({'user-agent': selenium_user_agent})
        
        for cookie in self.driver.get_cookies():
            session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'])

        access_token = next(
            (obj for obj in self.driver.get_cookies() if obj['name'] == 'accessToken'),
            None
        )
        if access_token:
            session.headers.update({'Authorization': f"Bearer {access_token['value']}"})
             
        return session


    def get_json(self, url):
        session = self.get_requests_session()
        json_data = session.get(url).json()

        if 'success' in json_data and not json_data['success']:
            raise Exception(json_data['code'])

        return json_data


    def auth(self, user, password, delay = 30):
        self.driver.get("https://login.sankakucomplex.com/login")
  
        present = EC.presence_of_element_located((By.CSS_SELECTOR, "form input[name='email']"))
        WebDriverWait(self.driver, delay).until(present)

        time.sleep(3)

        email_input = self.driver.find_element(By.CSS_SELECTOR, "form input[name='email']",)
        password_input = self.driver.find_element(By.CSS_SELECTOR, "form input[name='password']")
        submit_button = self.driver.find_element(By.CSS_SELECTOR, "form button[type='submit']")

        email_input.send_keys(user)
        password_input.send_keys(password)

        submit_button.click()

        try:
            present = EC.presence_of_element_located((By.XPATH, "//div[normalize-space()='Not now']"))
            WebDriverWait(self.driver, delay).until(present)

            not_now = self.driver.find_element(By.XPATH, "//div[normalize-space()='Not now']")
            not_now.click()

            present = EC.presence_of_element_located((By.CSS_SELECTOR, "input[id='autocomplete']"))
            WebDriverWait(self.driver, delay).until(present)
        except Exception as e:
            raise Exception('Wrong username or password')
        
        time.sleep(1)


    def search(self, tags):
        self.last_search_tags = tags.replace(' ', '+')
    
        json = self.get_json(f'https://capi-v2.sankakucomplex.com/posts/keyset?{self.search_params}&tags={self.last_search_tags}')
        self.last_next_id = json['meta']['next']
        
        return self.search_cleaner(json)
    

    @staticmethod
    def auto_tag(text):
        try:
            words =  text.strip().split()  
            last_word = words[0] if words else ""
            if last_word == "":
                return []

            encoded_tag = urllib.parse.quote(last_word)
            json_data = requests.get(f'https://sankakuapi.com/tags/autosuggestCreating?tag={encoded_tag}&show_meta=0&target=post').json()

            return [item["tagName"] for item in json_data if "tagName" in item]
        except:
            return []


    def next(self):
        if self.last_next_id is None:
            return []

        json = self.get_json(f'https://capi-v2.sankakucomplex.com/posts/keyset?{self.search_params}&tags={self.last_search_tags}&next={self.last_next_id}')
        self.last_next_id = json['meta']['next']

        return self.search_cleaner(json)
    

    def download(self, json, save_dir, name = None, save_tags = False):
        if name is None:
            name = json['id']

        session = self.get_requests_session()

        response = session.get(json['file'], stream=True)

        with response as r:
            media_file = os.path.join(save_dir, f'{name}.{json["format"]}')
            with open(media_file, 'wb') as f:
                shutil.copyfileobj(r.raw, f)

        session.close()

        if save_tags:
            tags_file = os.path.join(save_dir, f'{name}.txt')
            f = open(tags_file, 'w', encoding="utf-8")
            f.write(', '.join(json["tags"]))
            f.close()


    def search_cleaner(self, json):
        clean_data = []

        for media in json['data']:
            if media['file_url'] is None:
                continue

            clean_data.append({
                'id': media['id'],
                'rating': media['rating'],
                'preview': media['preview_url'],
                'file': media['file_url'],
                'type': media['file_type'].split('/')[0],
                'format': media['file_type'].split('/')[1],
                'width': media['width'],
                'height': media['height'],
                'size': media['file_size'],
                'tags': self.tags_cleaner(media['tags'])
            })

        return clean_data


    def tags_cleaner(self, json):
        clean_data = [o['name_en'] for o in json]
        return clean_data