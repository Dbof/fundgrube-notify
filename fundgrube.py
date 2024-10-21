#!/usr/bin/env python3
import os
import json
import requests
import csv
from urllib.parse import quote
import argparse
from datetime import datetime
import logging
from pathlib import Path
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

LOGGER = logging.getLogger(__name__)

def setup_logger(loglevel):
    # setup logger
    FORMAT = '%(levelname)s - %(name)s: %(message)s'
    logging.basicConfig(level=loglevel, format=FORMAT)

class Posting:
    def __init__(self, base_url, posting_id, pim_id, name, original_url, posting_text, price, shipping_cost, discount_in_percent, outlet, **kwargs):
        self.base_url = base_url
        self.posting_id = posting_id
        self.pim_id = pim_id
        self.name = name
        self.original_url = original_url
        self.posting_text = posting_text
        self.price = price
        self.shipping_cost = shipping_cost
        self.discount_in_percent = discount_in_percent
        if outlet:
            self.outlet_id = outlet.get('id')
        else:
            self.outlet_id = None

    def get_direct_url(self):
        return f'{self.base_url}?outletIds={self.outlet_id}&text={self.pim_id}'

    def __str__(self):
        return f'{self.name} - {self.price} (\U0001F4E6 {self.shipping_cost}) ({self.discount_in_percent} %)'


class GameFilter:
    def __init__(self, search, **kwargs):
        self.search = search
        self.price = kwargs.get('price')

    def __repr__(self):
        return f"GameFilter(include={self.search}, price={self.price})"

def read_games_from_json(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
        games = [GameFilter(item['include'], **item) for item in data]
    return games

def request_get(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0',
        'Accept': '*/*',
        'Accept-Language': 'en-GB,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Referer': 'https://www.mediamarkt.de/de/data/fundgrube?text=Switch%5D',
        'Connection': 'keep-alive',
    }

    return requests.get(url, headers=headers)

def mail_notify(new_count: int, posting_list, error: Exception = None) -> None:
    """Notify the user about new articles via email, if set up.

    Args:
        new_count: Number of new articles.
        posting_list: articles from the current run, ordered by timestamps.
        error: The error to notify the user about, should one have occurred.
    """
    mail_sender = os.getenv("MAIL_SENDER")
    mail_password = os.getenv("MAIL_PASSWORD")
    previous_error_file = Path("data/previous_error.txt")
    if previous_error_file.exists():
        with open(previous_error_file, "r") as file:
            old_error = file.read()
    else:
        old_error = None

    if mail_sender and mail_password and (new_count > 0 or error.__class__.__name__ != old_error):
        # only send mail if: new data, or error, or error fixed
        smtp_server = os.getenv("SMTP_SERVER", 'smtp.gmail.com')
        smtp_port = os.getenv("SMTP_PORT", 587)
        sender = f'Fundgrube Notifier <{mail_sender}>'
        receiver = os.getenv("MAIL_RECEIVER", mail_sender)

        if error:
            message_text = repr(error)
            subject = f"An error occured"
            with open(previous_error_file, "w") as file:
                file.write(error.__class__.__name__)
        elif new_count > 0:
            message_text = " \n".join([f'{post}: {post.get_direct_url()}\n' for post in posting_list])
            subject = f"{new_count} new items"
        else:
            message_text = str("Previous error fixed")
            subject = f"Error fixed"
            os.remove(previous_error_file)

        LOGGER.debug(f"Mail message:\n{message_text}")
        message = MIMEText(message_text, "plain", "utf-8")

        if mail_sender == receiver:
            message['Subject'] = "Fundgrube: " + subject
        else:
            message['Subject'] = subject
        message['From'] = sender
        message['To'] = receiver

        smtp_client = smtplib.SMTP(smtp_server, smtp_port)
        smtp_client.starttls()
        smtp_client.login(mail_sender, mail_password)
        smtp_client.sendmail(sender, [receiver], message.as_string())
        smtp_client.quit()
        LOGGER.info('Mail sent')


def read_results_from_csv(old_file):
    existing = Path(old_file).exists()

    result_dict = {}
    with open(old_file, mode='r') as results_file:
    # datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        csv_reader = csv.DictReader(results_file)

        for row in csv_reader:
            result_dict[row['Id']] = datetime.strptime(row['Date'], '%Y-%m-%d %H:%M:%S')

    return result_dict


def save_results(findings, old_file):
    """Save old results to CSV file

    Args:
        findings: List of Posting objects
        old_file: Filename of old results file
    """
    existing = Path(old_file).exists()

    with open(old_file, mode='a') as results_file:
        results_writer = csv.writer(results_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)

        if not existing:
            results_writer.writerow(['Date', 'Id', 'Name', 'Price', 'Url'])

        now = datetime.now()
        for find in findings:
            results_writer.writerow([now.strftime('%Y-%m-%d %H:%M:%S'), find.posting_id, find.name, find.price, find.get_direct_url()])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Get a list of Fundgrube objects that match your filters')
    parser.add_argument('config_file', type=str, help='Path to config.json file')
    parser.add_argument('--old_results_file', type=str, default='old_results.csv', help='Path to old_results.csv file')
    parser.add_argument(
        '--debug',
        help="Print lots of debugging statements",
        action="store_const", dest="loglevel", const=logging.DEBUG,
        default=logging.ERROR,
    )
    parser.add_argument(
        '--verbose',
        help="Be verbose",
        action="store_const", dest="loglevel", const=logging.INFO,
        default=logging.ERROR,
    )

    base_mm = 'https://www.mediamarkt.de/de/data/fundgrube'
    base_sa = 'https://www.saturn.de/de/data/fundgrube'


    args = parser.parse_args()
    # setup logger
    setup_logger(args.loglevel)

    # load filters
    filter_list = read_games_from_json(args.config_file)

    # add already scanned games
    if Path(args.old_results_file).exists():
        old_dict = read_results_from_csv(args.old_results_file)
    else:
        old_dict = {}

    findings = []
    for fil in filter_list:
        search_text = quote(fil.search, safe='')

        for base_url in [base_mm, base_sa]:
            url = f'{base_url}/api/postings?limit=32&offset=0&orderBy=new&recentFilter=text&text={search_text}'
            if fil.price:
                url += f'&priceMax={fil.price}'

            req_fundgrube = request_get(url)
            js_fundgrube = json.loads(req_fundgrube.text)

            # extract postings
            posting_list = list(js_fundgrube.get('postings'))
            LOGGER.info('Postings found on %s: %i', base_url, len(posting_list))

            for post in posting_list:
                p = Posting(**post, **{'base_url': base_url})

                # filter by using old results
                entry = old_dict.get(p.posting_id)
                # if entry does not exist, it was not already found
                if entry is None:
                    findings.append(p)

    LOGGER.info('New findings: %i', len(findings))
    if len(findings) > 0:
        # save findings to local log file
        save_results(findings, args.old_results_file)

        mail_notify(len(findings), findings)
