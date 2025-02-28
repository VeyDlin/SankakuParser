import html
from prompt_toolkit import print_formatted_text, HTML


class Logger:
    @staticmethod
    def success(message):
        print_formatted_text(HTML(f"<ansigreen>[OK]</ansigreen> {message}"))
    
    @staticmethod
    def error(message, err=None):
        error_details = f": {err}, {type(err)}" if err else ""
        error_details = html.escape(error_details) 
        print_formatted_text(HTML(f"<ansired>[ERROR] {error_details}</ansired>"))
    
    @staticmethod
    def warning(message):
        print_formatted_text(HTML(f"<ansiyellow>[WARNING]</ansiyellow> {message}"))
    
    @staticmethod
    def info(message):
        print_formatted_text(HTML(f"{message}"))
    
    @staticmethod
    def page_separator(page_num):
        print_formatted_text(HTML(f"<ansigreen>[------------------------ PAGE {page_num} END ------------------------]</ansigreen>"))
        print()
    
    @staticmethod
    def page_header(page_num):
        print_formatted_text(HTML(f"<ansigreen>[------------------------ LOAD {page_num} PAGE ------------------------]</ansigreen>"))