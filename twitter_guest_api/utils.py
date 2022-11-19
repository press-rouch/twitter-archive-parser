"""Utilities for downloading from Twitter"""

import json
import logging
import re

# https://developer.twitter.com/en/docs/twitter-api/v1/tweets/post-and-engage/api-reference/get-statuses-show-id
SHOW_STATUS_ENDPOINT = "https://api.twitter.com/1.1/statuses/show.json"
SHOW_STATUS_ENDPOINT = "https://api.twitter.com/1.1/statuses/lookup.json"
# https://developer.twitter.com/en/docs/twitter-api/v1/accounts-and-users/follow-search-get-users/api-reference/get-users-show
SHOW_USER_ENDPOINT = "https://api.twitter.com/1.1/users/show.json"
# Undocumented!
GUEST_TOKEN_ENDPOINT = "https://api.twitter.com/1.1/guest/activate.json"
BEARER_TOKEN_PATTERN = re.compile(r'"(AAA\w+%\w+)"')

def send_request(url, session_method, headers):
    """Attempt an http request"""
    response = session_method(url, headers=headers, stream=True)
    if response.status_code != 200:
        raise Exception(f"Failed request to {url}: {response.status_code} {response.reason}")
    return response.content.decode("utf-8")

def get_guest_token(session, headers):
    """Request a guest token and add it to the headers"""
    guest_token_response = session.post(GUEST_TOKEN_ENDPOINT, headers=headers, stream=True)
    guest_token_json = json.loads(guest_token_response.content)
    guest_token = guest_token_json['guest_token']
    if not guest_token:
        raise Exception(f"Failed to retrieve guest token")
    logging.info("Retrieved guest token %s", guest_token)
    headers['x-guest-token'] = guest_token

def get_response(url, session, headers):
    """Attempt to get the requested url. If the guest token has expired, get a new one and retry."""
    response = session.get(url, headers=headers, stream=True)
    if response.status_code == 429:
        # rate limit exceeded?
        logging.warning("Error %i: %s", response.status_code, response.text.strip())
        logging.info("Trying new guest token")
        get_guest_token(session, headers)
        response = session.get(url, headers=headers, stream=True)
    return response

def initialise_headers(session, url):
    """Populate http headers with necessary information for Twitter queries"""
    headers = {}

    # One of the js files from original url holds the bearer token and query id.
    container = send_request(url, session.get, headers)
    js_files = re.findall("src=['\"]([^'\"()]*js)['\"]", container)

    bearer_token = None
    # Search the javascript files for a bearer token and query ids
    for jsfile in js_files:
        logging.debug("Processing %s", jsfile)
        file_content = send_request(jsfile, session.get, headers)
        find_bearer_token = BEARER_TOKEN_PATTERN.search(file_content)

        if find_bearer_token:
            bearer_token = find_bearer_token.group(1)
            logging.info("Retrieved bearer token: %s", bearer_token)
            break

    if not bearer_token:
        raise Exception("Did not find bearer token.")

    headers['authorization'] = f"Bearer {bearer_token}"

    get_guest_token(session, headers)
    return headers

class TwitterGuestAPI:
    """Class to query Twitter API without a developer account"""
    def __init__(self, session):
        self.headers = initialise_headers(session, "https://www.twitter.com")

    def get_account(self, session, account_id):
        """Get the json metadata for a user account"""
        query_url = f"{SHOW_USER_ENDPOINT}?user_id={account_id}"
        response = get_response(query_url, session, self.headers)
        if response.status_code == 200:
            status_json = json.loads(response.content)
            return status_json
        logging.error("Failed to get account %s: (%i) %s",
                      account_id, response.status_code, response.reason)
        return None

    def get_tweet(self, session, tweet_id, include_user=True, include_alt_text=True):
        """
        Get the json metadata for a single tweet.
        If include_user is False, you will only get a numerical id for the user.
        """
        query_url = f"{SHOW_STATUS_ENDPOINT}?id={tweet_id}&tweet_mode=extended"
        if not include_user:
            query_url += "&trim_user=1"
        if include_alt_text:
            query_url += "&include_ext_alt_text=1"
        response = get_response(query_url, session, self.headers)
        if response.status_code == 200:
            status_json = json.loads(response.content)
            return status_json
        logging.error("Failed to get tweet %s: (%i) %s",
                      tweet_id, response.status_code, response.reason)
        return None
