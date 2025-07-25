from SankakuParserBase import SankakuParserBase
from urllib.parse import quote_plus
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import requests
import json
import re
from bs4 import BeautifulSoup


class IdolSankakuParser(SankakuParserBase):
    def __init__(self):
        super().__init__() 
        self.search_params = "auto_page=t&page=1"
        self.last_next_id = ""
        self.last_search_tags = ""


    def check_auth(self, user=None, delay=30):
        driver = super()._get_driver()
        driver.get("https://idol.sankakucomplex.com/home")
        present = EC.presence_of_element_located((By.CSS_SELECTOR, f"#user-index"))
        WebDriverWait(driver, delay).until(present)

        user_img = driver.find_elements(By.CSS_SELECTOR, f"#user-index .user-home-heading img")
        if not user_img:
            return False
        
        if user:
            title = user_img[0].get_attribute('title')
            if title != user:
                self._clear_all_site_data()
                return False
            
        return True


    def auth(self, user, password, delay=30):
        driver = super()._get_driver()
        try:
            driver.get("https://idol.sankakucomplex.com/users/login")
    
            present = EC.presence_of_element_located((By.CSS_SELECTOR, "form input[name='user[name]']"))
            WebDriverWait(driver, delay).until(present)

            time.sleep(3)

            email_input = driver.find_element(By.CSS_SELECTOR, "form input[name='user[name]']")
            password_input = driver.find_element(By.CSS_SELECTOR, "form input[name='user[password]']")
            submit_button = driver.find_element(By.CSS_SELECTOR, "form input[type='submit']")

            email_input.send_keys(user)
            password_input.send_keys(password)

            submit_button.click()

            present = EC.presence_of_element_located((By.CSS_SELECTOR, f"#user-index img[title='{user}']"))
            WebDriverWait(driver, delay).until(present)
        except Exception as e:
            raise Exception('Wrong username or password')
        
        time.sleep(1)


    def search(self, tags):
        self.last_search_tags = quote_plus(tags)
        data = self._get_html(f'https://idol.sankakucomplex.com/posts?{self.search_params}&tags={self.last_search_tags}')
        return self._search_cleaner(data)
    

    def auto_tag(self, text):
        try:
            words =  text.strip().split()  
            last_word = words[0] if words else ""
            if last_word == "":
                return []

            encoded_tag = quote_plus(last_word)
            data = self._get_html(f'https://idol.sankakucomplex.com/tags/autosuggest?tag={encoded_tag}&version=1&type=posts', with_driver=False)

            soup = BeautifulSoup(data, 'html.parser')
            tags = []
            for li in soup.find_all('li', class_='ui-menu-item'):
                tag_value = li.get('data-autocomplete-value')
                if tag_value:
                    tags.append(tag_value)

            return tags
        except Exception as e:
            return []


    def next(self):
        if self.last_next_id is None:
            return []

        data = self._get_html(f'https://idol.sankakucomplex.com/posts?{self.search_params}&tags={self.last_search_tags}&next={self.last_next_id}')
        return self._search_cleaner(data)
    

    def get_full_info(self, media):
        data = self._get_html(f'https://idol.sankakucomplex.com/posts/{media["id"]}')
        soup = BeautifulSoup(data, 'html.parser')

        # Find media link
        media_link = soup.find('a', id='image-link')
        if media_link:
            # Image case
            href = media_link.get('href')
            if not href:
                raise ValueError("Media link has no href attribute")
            if href.startswith('//'):
                media_url = 'https:' + href
            else:
                media_url = href
        else:
            video = soup.find('video', id='image')
            if video:
                # Video case
                src = video.get('src')
                if not src:
                    raise ValueError("Video has no src attribute")
                if src.startswith('//'):
                    media_url = 'https:' + src
                else:
                    media_url = src
            else:
                raise ValueError("No media (image or video) found")
            
        # Extract file extension from URL
        file_name = media_url.split('?')[0].split('/')[-1]
        if '.' not in file_name:
            raise ValueError("Cannot determine file format from URL")

        file_format = file_name.split('.')[-1].lower()

        # Find tags
        tag_links = soup.find_all('a', class_='tag-link')
        if not tag_links:
            raise ValueError("No tag links found")

        tags = []
        for link in tag_links:
            tag_name = link.get_text(strip=True)
            if tag_name:
                tags.append(tag_name)

        tags = list(dict.fromkeys(tags))

        return {
            'id': media['id'],
            'file': media_url,
            'format': file_format,
            'tags': super()._tags_cleaner(tags),
            'request_full_info': False
        }
    

    def _get_html(self, url, with_driver=True):
        if with_driver:
            session = self._get_requests_session()
            response = session.get(url)
            session.close()
            return response.text
        else:
            return requests.get(url).text
    

    def _search_cleaner(self, data):
        soup = BeautifulSoup(data, 'html.parser')

        next_page_div = soup.find('div', attrs={'next-page-url': True})
        if next_page_div:
            next_page_url = next_page_div.get('next-page-url')
            match = re.search(r'next=([^&]+)', next_page_url)
            if match:
                self.last_next_id = match.group(1)
        else:
            self.last_next_id = None
        

        clean_data = []
        scripts = soup.find_all('script', string=re.compile(r'Post\.register'))
        for script in scripts:
            script_content = script.string
            match = re.search(r'Post\.register\((.*?)\);', script_content, re.DOTALL)
            if match:
                try:
                    post_data = json.loads(match.group(1))
                    if 'id' in post_data:
                        clean_data.append({
                            'id': post_data['id'],
                            'request_full_info': True
                        })
                except json.JSONDecodeError:
                    continue

        return clean_data