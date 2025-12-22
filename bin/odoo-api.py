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
        "-v", "--verbose", action="store_true", help="verbose output"
    )
    argparser.add_argument(
        "--url", default="https://bareos.odoo.com", help="URL of odoo server"
    )
    argparser.add_argument("--database", "--db", help="odoo database")
    argparser.add_argument(
        "--db_name_endpoint_token", help="secret key to get odoos database name"
    )
    argparser.add_argument("--apikey", required=True, help="odoo api key")

    subparsers = argparser.add_subparsers(dest="command")
    search_list = subparsers.add_parser("list")
    search_list.add_argument("model")
    show = subparsers.add_parser("show")
    show.add_argument("model")
    show.add_argument("id")
    reinit = subparsers.add_parser("reinit")
    reinit.add_argument("model")
    get_customers = subparsers.add_parser("customers")
    get_active_subscriptions = subparsers.add_parser("active_subscriptions")
    get_subscription_credentials = subparsers.add_parser("subscription_credentials")
    get_support_customers = subparsers.add_parser("support_customers")
    mail_add = subparsers.add_parser("mail-add")
    mail_add.add_argument("email", type=argparse.FileType("r"))
    return argparser


def get_db_name(baseurl, token):
    response = requests.get(
        baseurl + "/.well-known/odoo-db", headers={"X-DB-TOKEN": token}, timeout=5
    )
    response.raise_for_status()
    dbname = response.json()["dbname"]
    return dbname


class odoo_api:
    def __init__(self, baseurl, api_key, db=None):
        self.logger = logging.getLogger()
        self.baseurl = baseurl + "/json/2"
        self.api_key = api_key
        self.db = db
        self.headers = {
            "User-Agent": "odoo-api " + requests.utils.default_user_agent(),
            "Authorization": f"bearer {self.api_key}",
        }
        if self.db:
            self.headers["X-Odoo-Database"] = self.db

    def json2(self, odoo_model, odoo_method, *args, **kwargs):
        # AFAIK, the odoo json2 API uses named parameter,
        # not no args without name.
        # Still, keep args as paramter for completeness.
        if args:
            raise RuntimeError(f"args given ({args}), but not expected.")

        data = {}
        if kwargs:
            data = kwargs.copy()

        response = requests.post(
            f"{self.baseurl}/{odoo_model}/{odoo_method}",
            headers=self.headers,
            json=data,
        )
        response.raise_for_status()
        return response.json()

    def get_version(self, args):
        return self.json2(
            "web", "version",
        )

    def get_customers(self, args):
        return self.get_version(args)
        return self.json2(
            "res.partner",
            "search_read",
            domain=[["customer_rank", ">", 0]],
            fields=["name", "email"],
            limit=10,
        )

    def get_active_subscriptions(self, args):
        return self.json2("res.partner", "get_active_subscriptions_api")

    def get_subscription_credentials(self, args):
        return self.json2("res.partner", "get_subscription_credentials_api")

    def get_support_customers(self, args):
        return self.json2(
            "res.partner",
            "get_support_customers_api",
        )

    def search_list(self, args):
        return self.json2(
            args.model,
            "search_read",
            fields=["id", "name", "display_name"],
            order="id ASC",
        )

    def show(self, args):
        # not working:
        # return self.execute_kw(
        #     args.model,
        #     "read",
        #     [[ args.id ]],
        #     #{"fields": ["name"]},
        # )
        result = self.json2(
            args.model,
            "search_read",
            domain=[["id", "=", args.id]],
            # {"fields": ["name"]},
        )

        if args.verbose:
            return result
        return [
            {k: v for k, v in record.items() if v not in ("", [], None, 0, 0.0)}
            for record in result
        ]

    def reinit(self, args):
        return self.json2(
            args.model,
            "recompute_fields",
        )

    def mail_add(self, args):
        message = args.email.read()
        return self.json2(
            "mail.thread",
            "message_process",
            model=False,
            message=message,
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

    # if (not args.database) and (not args.db_name_endpoint_token):
    #     parser.error(
    #         "At least one of --database or --db_name_endpoint_token is required"
    #     )

    database = args.database
    if not database and args.db_name_endpoint_token:
        logger.debug("try to detect database")
        database = get_db_name(args.url, args.db_name_endpoint_token)
        logger.debug(f"using database: {database}")

    odoo = odoo_api(args.url, args.apikey, database)

    method_map = {
        "customers": odoo.get_customers,
        "active_subscriptions": odoo.get_active_subscriptions,
        "subscription_credentials": odoo.get_subscription_credentials,
        "support_customers": odoo.get_support_customers,
        "list": odoo.search_list,
        "show": odoo.show,
        "reinit": odoo.reinit,
        "mail-add": odoo.mail_add,
    }

    if args.command in method_map:
        result = method_map[args.command](args)
        pprint(result)
    else:
        # raise RuntimeError(f"unsupported command {args.command}")
        print(f"unsupported command '{args.command}'\n")
        parser.print_help()
