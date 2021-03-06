__author__ = "geduldig"
__date__ = "June 8, 2013"
__license__ = "MIT"


from requests.exceptions import ConnectionError, ReadTimeout, SSLError
from requests.packages.urllib3.exceptions import ReadTimeoutError, ProtocolError
from .TwitterError import *
import requests
import time


class TwitterPager(object):

    """Continuous (stream-like) pagination of response from Twitter REST API resource.
    In addition to Public API endpoints, supports Premium Search API.

    :param api: An authenticated TwitterAPI object
    :param resource: String with the resource path (ex. search/tweets)
    :param params: Dictionary of resource parameters
    """

    def __init__(self, api, resource, params=None):
        self.api = api
        self.resource = resource
        self.params = params

    def get_iterator(self, wait=5, new_tweets=False):
        """Iterate response from Twitter REST API resource. Resource is called
        in a loop to retrieve consecutive pages of results.

        :param wait: Floating point number (default=5) of seconds wait between requests.
                     Depending on the resource, appropriate values are 5 or 60 seconds.
        :param new_tweets: Boolean determining the search direction.
                           False (default) retrieves old results.
                           True retrieves current results.
        :param version: override default API version or None (default)

        :returns: JSON objects containing statuses, errors or other return info.
        """
        elapsed = 0
        while True:
            try:
                # REQUEST ONE PAGE OF RESULTS...
                start = time.time()
                r = self.api.request(self.resource, self.params)
                it = r.get_iterator()
                if new_tweets:
                    it = reversed(list(it))

                # YIELD FOR EACH ITEM IN THE PAGE...
                item_count = 0
                id = None
                for item in it:
                    item_count += 1
                    if type(item) is dict:
                        if 'id' in item:
                            id = item['id']
                        if 'code' in item:
                            if item['code'] in [130, 131]:
                                # Twitter service error
                                raise TwitterConnectionError(item)
                    yield item

                data = r.json()

                # CHECK FOR NEXT PAGE OR BAIL...
                if self.api.version == '1.1':
                    # if a cursor is present, use it to get next page
                    # otherwise, use id to get next page
                    is_premium_search = self.params and 'query' in self.params and self.api.version == '1.1'
                    cursor = -1
                    if new_tweets and 'previous_cursor' in data:
                        cursor = data['previous_cursor']
                        cursor_param = 'cursor'
                    elif not new_tweets:
                        if 'next_cursor' in data:
                            cursor = data['next_cursor']
                            cursor_param = 'cursor'
                        elif 'next' in data:
                            # 'next' is used by Premium Search (OLD searches only)
                            cursor = data['next']
                            cursor_param = 'next'

                    # bail when no more results
                     # Ads api returns 'next_cursor': None
                    if cursor == 0 or not cursor:
                        break
                    elif cursor == -1 and is_premium_search:
                        break
                    elif not new_tweets and item_count == 0:
                        break
                else: # VERSION 2
                    if 'meta' not in data:
                        break
                    meta = data['meta']
                    # Break if next_token but no results
                    if (not new_tweets and 'next_token' not in meta) \
                            or ('result_count' in meta and meta['result_count'] == 0):
                        break

                # SLEEP...
                elapsed = time.time() - start
                pause = wait - elapsed if elapsed < wait else 0
                time.sleep(pause)

                # SETUP REQUEST FOR NEXT PAGE...
                if self.api.version == '1.1':
                    # get a page with cursor if present, or with id if not
                    # a Premium search (i.e. 'query' is not a parameter)
                    if cursor != -1:
                        self.params[cursor_param] = cursor
                    elif id is not None and not is_premium_search:
                        if new_tweets:
                            self.params['since_id'] = str(id)
                        else:
                            self.params['max_id'] = str(id - 1)
                    else:
                        continue
                else: # VERSION 2
                    if new_tweets:
                        self.params['since_id'] = meta['newest_id']
                    else:
                        self.params['pagination_token'] = meta['next_token']

            except TwitterRequestError as e:
                if e.status_code < 500:
                    raise
                continue
            except TwitterConnectionError:
                continue
