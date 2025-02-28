import html
from InquirerPy.utils import get_style
from prompt_toolkit import print_formatted_text, HTML


class Logger:
    @staticmethod
    def e(message):
        return html.escape(str(message))

    @staticmethod
    def s(message, style_name):
        style = get_style().dict.get(style_name, '#abb2bf')
        return f'<style fg="{style}">{Logger.e(message)}</style>'

    @staticmethod
    def success(message):
        print_formatted_text(HTML(f"{Logger.s('[OK]', 'input')} {message}"))

    @staticmethod
    def error(message, err=None):
        error_details = f": {err}, {type(err)}" if err else ""
        print_formatted_text(HTML(Logger.s(f'[ERROR] {message}{error_details}', 'fuzzy_prompt')))

    @staticmethod
    def warning(message):
        print_formatted_text(HTML(f"{Logger.s('[WARNING]', 'marker')} {message}"))

    @staticmethod
    def info(message):
        print_formatted_text(HTML(message))

    @staticmethod
    def page_separator(page_num):
        print_formatted_text(HTML(Logger.s(f'[------------------------ PAGE {page_num} END ------------------------]', 'input')))
        print()

    @staticmethod
    def page_header(page_num):
        print_formatted_text(HTML(Logger.s(f'[------------------------ LOAD {page_num} END ------------------------]', 'input')))