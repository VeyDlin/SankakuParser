from abc import ABC, abstractmethod
from selenium import webdriver
import os
import requests
import shutil


class SankakuParserBase(ABC):
    def __init__(self):
        self._driver = None


    def __del__(self):
        if self._driver:
            self._driver.quit()


    def init_driver(self, use_profile=True, debug_window=False):
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--enable-javascript")

        if use_profile:
            profile_dir = os.path.join(os.getcwd(), ".web_profile")
            if not os.path.exists(profile_dir):
                os.makedirs(profile_dir)
            chrome_options.add_argument(f"--user-data-dir={profile_dir}")
            chrome_options.add_argument("--profile-directory=Default")

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

        self._driver = webdriver.Chrome(options=chrome_options)


    def _clear_all_site_data(self):
        # Clear cookies
        self._driver.delete_all_cookies()
        
        # Execute JavaScript to clear storage
        self._driver.execute_script("""
            // Clear local storage
            window.localStorage.clear();
            
            // Clear session storage
            window.sessionStorage.clear();
            
            // Clear IndexedDB
            if (window.indexedDB && window.indexedDB.databases) {
                window.indexedDB.databases().then(databases => {
                    databases.forEach(db => window.indexedDB.deleteDatabase(db.name));
                });
            }
            
            // Clear cache storage (for service workers)
            if ('caches' in window) {
                caches.keys().then(names => {
                    names.forEach(name => caches.delete(name));
                });
            }
        """)
        
        # Clear Chrome cache (requires special permissions)
        self._driver.execute_cdp_cmd('Network.clearBrowserCookies', {})
        self._driver.execute_cdp_cmd('Network.clearBrowserCache', {})
        
        # Refresh to apply
        self._driver.refresh()


    def download(self, info, save_dir, name=None, save_tags=False):
        if name is None:
            name = info['id']

        session = self._get_requests_session()

        response = session.get(info['file'], stream=True)

        with response as r:
            media_file = os.path.join(save_dir, f'{name}.{info["format"]}')
            with open(media_file, 'wb') as f:
                shutil.copyfileobj(r.raw, f)

        session.close()

        if save_tags:
            tags_file = os.path.join(save_dir, f'{name}.txt')
            f = open(tags_file, 'w', encoding="utf-8")
            f.write(', '.join(info["tags"]))
            f.close()


    def _get_requests_session(self, site_url=None):
        session = requests.Session()

        selenium_user_agent = self._driver.execute_script('return navigator.userAgent;')
        session.headers.update({'user-agent': selenium_user_agent})

        if site_url:
            from urllib.parse import urlparse
            parsed = urlparse(site_url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            session.headers.update({
                'Referer': site_url,
                'Origin': origin,
            })

        for cookie in self._driver.get_cookies():
            session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'])

        access_token = next(
            (obj for obj in self._driver.get_cookies() if obj['name'] == 'accessToken'),
            None
        )
        if access_token:
            session.headers.update({'Authorization': f"Bearer {access_token['value']}"})
             
        return session


    def _tags_cleaner(self, tags):
        return [o.replace("_", " ") for o in tags]


    def _get_driver(self):
        return self._driver
    
    
    @abstractmethod
    def check_auth(self, user=None, delay=30):
        pass


    @abstractmethod
    def auth(self, user, password, delay=30):
        pass


    @abstractmethod
    def search(self, tags):
        pass


    @abstractmethod
    def next(self):
        pass


    @abstractmethod
    def auto_tag(self, text):
        pass


    @abstractmethod
    def get_full_info(self, info):
        pass