"""Utilities for downloading from Twitter"""

import json
import logging

# https://developer.twitter.com/en/docs/twitter-api/v1/tweets/post-and-engage/api-reference/get-statuses-show-id
SHOW_STATUS_ENDPOINT = "https://api.twitter.com/1.1/statuses/show.json"
LOOKUP_STATUS_ENDPOINT = "https://api.twitter.com/1.1/statuses/lookup.json"
# https://developer.twitter.com/en/docs/twitter-api/v1/accounts-and-users/follow-search-get-users/api-reference/get-users-show
SHOW_USER_ENDPOINT = "https://api.twitter.com/1.1/users/show.json"
LOOKUP_USER_ENDPOINT = "https://api.twitter.com/1.1/users/lookup.json"
# Undocumented!
GUEST_TOKEN_ENDPOINT = "https://api.twitter.com/1.1/guest/activate.json"
BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

BATCH_MAX = 100

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

def initialise_headers(session):
    """Populate http headers with necessary information for Twitter queries"""
    headers = {}
    headers['authorization'] = f"Bearer {BEARER_TOKEN}"

    get_guest_token(session, headers)
    return headers

class TwitterGuestAPI:
    """Class to query Twitter API without a developer account"""
    def __init__(self, session):
        self.headers = initialise_headers(session)

    def get_accounts(self, session, account_ids):
        """Get the json metadata for multiple user accounts"""
        accounts = {}
        while account_ids:
            account_batch = account_ids[:BATCH_MAX]
            account_ids = account_ids[BATCH_MAX:]
            id_list = ",".join(account_batch)
            query_url = f"{LOOKUP_USER_ENDPOINT}?user_id={id_list}"
            response = get_response(query_url, session, self.headers)
            if response.status_code == 200:
                response_json = json.loads(response.content)
                for entry in response_json:
                    accounts[entry["id_str"]] = entry
            else:
                logging.error("Failed to get accounts: (%i) %s",
                              response.status_code, response.reason)
        return accounts

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
