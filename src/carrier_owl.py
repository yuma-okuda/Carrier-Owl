from webdriver_manager.firefox import GeckoDriverManager
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import NoSuchElementException
import os
import time
import yaml
import datetime
import slackweb
import argparse
import textwrap
from bs4 import BeautifulSoup
import warnings
import urllib.parse
from dataclasses import dataclass
import arxiv
import requests
# setting
warnings.filterwarnings('ignore')


@dataclass
class Result:
    url: str
    title: str
    title_trans: str
    abstract: str
    words: list
    score: float = 0.0


def calc_score(abst: str, keywords: dict) -> (float, list):
    sum_score = 0.0
    hit_kwd_list = []

    for word in keywords.keys():
        score = keywords[word]
        if word.lower() in abst.lower():
            sum_score += score
            hit_kwd_list.append(word)
    return sum_score, hit_kwd_list


def search_keyword(
        articles: list, keywords: dict, score_threshold: float
        ) -> list:
    results = []
    
    # ヘッドレスモードでブラウザを起動
    options = Options()
    options.add_argument('--headless')

    # ブラウザーを起動
    driver = webdriver.Firefox(executable_path=GeckoDriverManager().install(), options=options)
    
    for article in articles:
        url = article['arxiv_url']
        title = article['title'].replace('\n', ' ')
        abstract = article['summary']
        score, hit_keywords = calc_score(abstract, keywords)
        if (score != 0) and (score >= score_threshold):
            title_trans = get_translated_text('ja', 'en', title, driver)
            abstract = abstract.replace('\n', '')
            abstract_trans = get_translated_text('ja', 'en', abstract, driver)
            # abstract_trans = textwrap.wrap(abstract_trans, 40)  # 40行で改行
            # abstract_trans = '\n'.join(abstract_trans)
            result = Result(
                    url=url, title=title,title_trans=title_trans, abstract=abstract_trans,
                    score=score, words=hit_keywords)
            results.append(result)
    
    # ブラウザ停止
    driver.quit()
    return results


def send2app(text: str, slack_id: str, line_token: str) -> None:
    # slack
    if slack_id is not None:
        slack = slackweb.Slack(url=slack_id)
        slack.notify(text=text)

    # line
    if line_token is not None:
        line_notify_api = 'https://notify-api.line.me/api/notify'
        headers = {'Authorization': f'Bearer {line_token}'}
        data = {'message': f'message: {text}'}
        requests.post(line_notify_api, headers=headers, data=data)


def notify(results: list, slack_id: str, line_token: str) -> None:
    # 通知
    star = '*'*80
    today = datetime.date.today()
    n_articles = len(results)
    text = f'{star}\n \t \t {today}\tnum of articles = {n_articles}\n{star}'
    send2app(text, slack_id, line_token)
    # descending
    for result in sorted(results, reverse=True, key=lambda x: x.score):
        url = result.url
        title = result.title
        title_trans = result.title_trans
        abstract = result.abstract
        word = result.words
        score = result.score

        text = f'\n score: `{score}`'\
               f'\n hit keywords: `{word}`'\
               f'\n url: {url}'\
               f'\n title:    {title}'\
               f'\n title_trans:    {title_trans}'\
               f'\n abstract:'\
               f'\n \t {abstract}'\
               f'\n {star}'
        
        
        

        send2app(text, slack_id, line_token)


def get_translated_text(from_lang: str, to_lang: str, from_text: str, driver) -> str:
    '''
    https://qiita.com/fujino-fpu/items/e94d4ff9e7a5784b2987
    '''
    DEEPL_API_KEY =  os.getenv("DEEPL_API_KEY") or args.deepl_api_key

    sleep_time = 1
    from_text = 'phone'

    params = {
            'auth_key' : DEEPL_API_KEY,
            'text' : from_text,
            'source_lang' : from_lang, # 翻訳対象の言語
            "target_lang": to_lang  # 翻訳後の言語
        }

    request = requests.post("https://api-free.deepl.com/v2/translate", data=params) # URIは有償版, 無償版で異なるため要注意
    try:
        result = request.json()['translations'][0]['text']
    except:
        result = from_text
    print(result)
    return result

def get_text_from_driver(driver) -> str:
    try:
        elem = driver.find_element_by_class_name('lmt__translations_as_text__text_btn')
    except NoSuchElementException as e:
        return None
    text = elem.get_attribute('innerHTML')
    return text

def get_text_from_page_source(html: str) -> str:
    soup = BeautifulSoup(html, features='lxml')
    target_elem = soup.find(class_="lmt__translations_as_text__text_btn")
    text = target_elem.text
    return text


def get_config() -> dict:
    file_abs_path = os.path.abspath(__file__)
    file_dir = os.path.dirname(file_abs_path)
    config_path = f'{file_dir}/../config.yaml'
    with open(config_path, 'r') as yml:
        config = yaml.load(yml)
    return config


def main():
    # debug用
    parser = argparse.ArgumentParser()
    parser.add_argument('--slack_id', default=None)
    parser.add_argument('--line_token', default=None)
    args = parser.parse_args()

    config = get_config()
    subject = config['subject']
    keywords = config['keywords']
    score_threshold = float(config['score_threshold'])

    day_before_yesterday = datetime.datetime.today() - datetime.timedelta(days=2)
    day_before_yesterday_str = day_before_yesterday.strftime('%Y%m%d')
    # datetime format YYYYMMDDHHMMSS
    arxiv_query = f'({subject}) AND ' \
                  f'submittedDate:' \
                  f'[{day_before_yesterday_str}000000 TO {day_before_yesterday_str}235959]'
    articles = arxiv.query(query=arxiv_query,
                           max_results=1000,
                           sort_by='submittedDate',
                           iterative=False)
    results = search_keyword(articles, keywords, score_threshold)

    slack_id = os.getenv("SLACK_ID") or args.slack_id
    line_token = os.getenv("LINE_TOKEN") or args.line_token
    notify(results, slack_id, line_token)


if __name__ == "__main__":
    main()
