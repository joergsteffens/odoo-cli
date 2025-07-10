#!/usr/bin/env python

import logging
import requests
import sys
from pprint import pprint, pformat

try:
    import configargparse as argparse
except ImportError:
    import argparse


def getArgparser():
    argparser = argparse.ArgumentParser(
        description="odoo api.", formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    if "configargparse" in sys.modules:
        argparser.add_argument(
            "-c", "--config", is_config_file=True, help="Config file path."
        )
    argparser.add_argument(
        "-d", "--debug", action="store_true", help="enable debugging output"
    )
    argparser.add_argument(
        "--url", default="https://bareos.odoo.com", help="URL of odoo server"
    )
    argparser.add_argument("--database", "--db", required=True, help="odoo database")
    argparser.add_argument(
        "--username", "--user", required=True, help="odoo username (email address)"
    )
    argparser.add_argument("--apikey", required=True, help="odoo api key")

    subparsers = argparser.add_subparsers(dest="command")
    get_customers = subparsers.add_parser("customers")
    get_active_subscriptions = subparsers.add_parser("active_subscriptions")
    get_subscription_credentials = subparsers.add_parser("subscription_credentials")
    get_support_customers = subparsers.add_parser("support_customers")
    return argparser


class odoo_api:
    def __init__(self, baseurl, db, username, api_key):
        self.logger = logging.getLogger()
        self.url = baseurl + "/jsonrpc"
        self.db = db
        self.username = username
        self.api_key = api_key
        self.uid = self._auth()

    def _auth(self):
        uid = self.json_rpc(
            {
                "service": "common",
                "method": "authenticate",
                "args": [self.db, self.username, self.api_key, {}],
            },
        )

        if not uid:
            raise RuntimeError("Login failed")
        self.logger.debug(f"login uid:  {uid}")
        return uid

    def json_rpc(self, params):
        headers = {"Content-Type": "application/json"}
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": params,
            "id": 1,
        }
        response = requests.post(self.url, json=payload, headers=headers)
        response.raise_for_status()
        if "error" in response.json():
            raise RuntimeError(pformat(response.json()))
        return response.json()["result"]

    def execute_kw(self, model, method, args=None, kwargs=None):
        # model	str	Name of the model (e.g. 'res.partner')
        # method	str	Name of the method to call (e.g. 'search_read', 'create')
        # args	list	Positional arguments (like search domain or record values)
        # kwargs	dict (opt.)	Optional keyword arguments like fields, context, etc.
        if args is None:
            args = []
        result = self.json_rpc(
            {
                "service": "object",
                "method": "execute_kw",
                "args": [self.db, self.uid, self.api_key, model, method, args, kwargs],
            },
        )
        return result

    def get_customers(self, args):
        return self.execute_kw(
            "res.partner",
            "search_read",
            [[["customer_rank", ">", 0]]],
            {"fields": ["name", "email"], "limit": 10},
        )

    def get_active_subscriptions(self, args):
        return self.execute_kw("res.partner", "get_active_subscriptions_api")

    def get_subscription_credentials(self, args):
        return self.execute_kw("res.partner", "get_subscription_credentials_api")

    def get_support_customers(self, args):
        return self.execute_kw(
            "res.partner",
            "get_support_customers_api",
        )


if __name__ == "__main__":
    logging.basicConfig(
        format="%(levelname)s %(module)s.%(funcName)s: %(message)s", level=logging.INFO
    )
    logger = logging.getLogger()

    parser = getArgparser()
    args = parser.parse_args()
    if args.debug:
        logger.setLevel(logging.DEBUG)

    odoo = odoo_api(args.url, args.database, args.username, args.apikey)

    method_map = {
        "customers": odoo.get_customers,
        "active_subscriptions": odoo.get_active_subscriptions,
        "subscription_credentials": odoo.get_subscription_credentials,
        "support_customers": odoo.get_support_customers,
    }

    if args.command in method_map:
        result = method_map[args.command](args)
        pprint(result)
    else:
        parser.print_help()
